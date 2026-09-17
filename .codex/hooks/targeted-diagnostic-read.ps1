#requires -Version 7.2
[CmdletBinding()]
param(
    # Read is the default while the legacy compatibility modes remain available.
    [ValidateSet('Read', 'Discover', 'Select', 'Slice')]
    [string]$Mode = 'Read',
    [Alias('Path', 'TargetPath')]
    [string]$SearchPath,
    [string]$Pattern,
    [string]$InputPath,
    [string[]]$Ids,
    [ValidateRange(1, 20)]
    [int]$MaxMatches = 20,
    [ValidateRange(1, 3)]
    [int]$MaxSelections = 3,
    [ValidateRange(0, 3)]
    [int]$Before = 2,
    [ValidateRange(0, 4)]
    [int]$After = 3,
    [string]$RepositoryRoot,
    [switch]$IgnoreCase,
    [Parameter(ValueFromPipeline = $true)]
    [string]$PipelineJson
)

$ErrorActionPreference = 'Stop'
$MaximumOutputBytes = 8192
$MaximumInputBytes = 8192
$MaximumLineCharacters = 320
$MaximumLinesScannedPerFile = 250000
$MaximumTotalLinesScanned = 2000000
$MaximumTotalBytesScanned = 64MB
$MaximumReturnedLocations = 12

# Read is the normal operation. Discover/Select/Slice remain bounded
# compatibility modes for existing callers, but the common path does not need
# model-mediated phase transitions or hand-carried intermediate JSON.
$script:PipelineInput = if ($PipelineJson) { @($PipelineJson) } else { @($input) }

function Get-RepositoryRoot {
    if ($RepositoryRoot) {
        try {
            return (Resolve-Path -LiteralPath $RepositoryRoot -ErrorAction Stop).Path
        }
        catch {
            throw 'REPOSITORY_ROOT_INVALID'
        }
    }

    $root = (& git rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $root) {
        throw 'NOT_IN_GIT_REPOSITORY'
    }
    try {
        return (Resolve-Path -LiteralPath $root.Trim() -ErrorAction Stop).Path
    }
    catch {
        throw 'REPOSITORY_ROOT_INVALID'
    }
}

function Get-PathComparison {
    if ([IO.Path]::DirectorySeparatorChar -eq '\') {
        return [StringComparison]::OrdinalIgnoreCase
    }
    return [StringComparison]::Ordinal
}

function Get-FullPath([string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        throw 'DIAGNOSTIC_PATH_INVALID'
    }
    try {
        return [IO.Path]::GetFullPath($Candidate)
    }
    catch {
        throw 'DIAGNOSTIC_PATH_INVALID'
    }
}

function Trim-DirectorySeparators([string]$Path) {
    return $Path.TrimEnd([char[]]@('\', '/'))
}

function Assert-PathWithinRoot([string]$Root, [string]$Candidate) {
    $rootFull = Get-FullPath $Root
    $candidateFull = Get-FullPath $Candidate
    $rootTrimmed = Trim-DirectorySeparators $rootFull
    $isFilesystemRoot = [string]::IsNullOrEmpty($rootTrimmed) -or
        ($rootTrimmed.Length -eq 1 -and $rootTrimmed[0] -in @('\', '/'))
    if ($candidateFull -eq $rootFull -or $isFilesystemRoot) {
        return
    }

    $separator = [IO.Path]::DirectorySeparatorChar
    $rootWithSeparator = $rootTrimmed + $separator
    if (-not $candidateFull.StartsWith($rootWithSeparator, (Get-PathComparison))) {
        throw 'DIAGNOSTIC_PATH_OUTSIDE_REPOSITORY'
    }
}

function Get-RelativePath([string]$Root, [string]$Candidate) {
    $rootFull = Get-FullPath $Root
    $candidateFull = Get-FullPath $Candidate
    Assert-PathWithinRoot $rootFull $candidateFull
    try {
        $rootForUri = (Trim-DirectorySeparators $rootFull) + [IO.Path]::DirectorySeparatorChar
        $rootUri = [Uri]::new($rootForUri)
        $candidateUri = [Uri]::new($candidateFull)
        return [Uri]::UnescapeDataString($rootUri.MakeRelativeUri($candidateUri).ToString()).Replace('\', '/')
    }
    catch {
        throw 'DIAGNOSTIC_RELATIVE_PATH_FAILED'
    }
}

function Test-ProtectedRelativePath([string]$RelativePath) {
    return $RelativePath -match '(?i)(^|/)\.git(/|$)' -or
        $RelativePath -match '(?i)(^|/)\.codex/local(/|$)'
}

function Assert-ContainedFile([string]$Root, [string]$Candidate) {
    try {
        $item = Get-Item -LiteralPath $Candidate -Force -ErrorAction Stop
        $isReparsePoint = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        if ($isReparsePoint -or $item.LinkType -or $item.Target) {
            $target = $item.ResolveLinkTarget($true)
            if ($null -ne $target) {
                Assert-PathWithinRoot $Root $target.FullName
            }
        }
    }
    catch {
        if ($_.Exception.Message -like 'DIAGNOSTIC_*') {
            throw
        }
        throw 'DIAGNOSTIC_SYMLINK_INVALID'
    }
}

function Resolve-SearchFiles([string]$Root) {
    if (-not $SearchPath) {
        throw 'SEARCH_PATH_REQUIRED'
    }

    try {
        $resolved = (Resolve-Path -LiteralPath $SearchPath -ErrorAction Stop).Path
        Assert-PathWithinRoot $Root $resolved
        $item = Get-Item -LiteralPath $resolved -Force -ErrorAction Stop
        Assert-ContainedFile $Root $resolved
    }
    catch {
        if ($_.Exception.Message -eq 'DIAGNOSTIC_PATH_OUTSIDE_REPOSITORY') {
            throw
        }
        throw 'DIAGNOSTIC_PATH_INVALID'
    }

    if ($item.PSIsContainer) {
        try {
            $allFiles = @(
                Get-ChildItem -LiteralPath $resolved -File -Recurse -Force -ErrorAction Stop |
                    Where-Object {
                        $relative = Get-RelativePath $Root $_.FullName
                        -not (Test-ProtectedRelativePath $relative)
                    } |
                    Sort-Object FullName
            )
        }
        catch {
            if ($_.Exception.Message -like 'DIAGNOSTIC_*') {
                throw
            }
            throw 'DIAGNOSTIC_FILE_ENUMERATION_FAILED'
        }
    }
    else {
        $relative = Get-RelativePath $Root $item.FullName
        if (Test-ProtectedRelativePath $relative) {
            throw 'DIAGNOSTIC_PATH_PROTECTED'
        }
        $allFiles = @($item)
    }

    if ($allFiles.Count -eq 0) {
        throw 'DIAGNOSTIC_NO_FILES'
    }

    return [pscustomobject]@{
        all_count = $allFiles.Count
        files = $allFiles
        truncated = $false
    }
}

function Assert-SafeOutput([string]$Raw) {
    $sensitivePatterns = @(
        '(?i)\\?"(?:authorization|cookie|password|private[_-]?key|secret|token)\\?"\s*:',
        '(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----',
        '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}',
        '\bsk-[A-Za-z0-9_-]{12,}',
        '\bgh[pousr]_[A-Za-z0-9]{12,}'
    )
    foreach ($patternValue in $sensitivePatterns) {
        if ($Raw -match $patternValue) {
            throw 'SENSITIVE_CONTENT_REJECTED'
        }
    }
}

function Write-BoundedJson($Value) {
    $json = $Value | ConvertTo-Json -Depth 8 -Compress
    if ([Text.Encoding]::UTF8.GetByteCount($json) -gt $MaximumOutputBytes) {
        throw 'DIAGNOSTIC_OUTPUT_TOO_LARGE'
    }
    Assert-SafeOutput $json
    [Console]::Out.WriteLine($json)
}

function Read-JsonInput {
    if ($InputPath) {
        try {
            if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf -ErrorAction Stop)) {
                throw 'INPUT_PATH_NOT_FOUND'
            }
            $inputItem = Get-Item -LiteralPath $InputPath -Force -ErrorAction Stop
            if ($inputItem.Length -gt $MaximumInputBytes) {
                throw 'DIAGNOSTIC_INPUT_TOO_LARGE'
            }
            $raw = Get-Content -Raw -LiteralPath $InputPath -ErrorAction Stop
        }
        catch {
            if ($_.Exception.Message -like 'INPUT_*' -or $_.Exception.Message -like 'DIAGNOSTIC_*') {
                throw
            }
            throw 'INPUT_PATH_NOT_FOUND'
        }
    }
    else {
        $parts = @($script:PipelineInput | ForEach-Object { [string]$_ })
        if ($parts.Count -eq 0) {
            throw 'PIPELINE_INPUT_REQUIRED'
        }
        $raw = $parts -join [Environment]::NewLine
    }

    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw 'PIPELINE_INPUT_REQUIRED'
    }
    if ([Text.Encoding]::UTF8.GetByteCount($raw) -gt $MaximumInputBytes) {
        throw 'DIAGNOSTIC_INPUT_TOO_LARGE'
    }
    Assert-SafeOutput $raw
    try {
        $document = $raw | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw 'INPUT_INVALID_JSON'
    }
    if ($null -eq $document -or $document -is [System.Array]) {
        throw 'INPUT_INVALID_JSON'
    }
    return $document
}

function Get-RequestedIds {
    $requestedIds = @()
    foreach ($idValue in @($Ids)) {
        foreach ($candidate in ([string]$idValue -split ',')) {
            if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                $requestedIds += $candidate.Trim()
            }
        }
    }
    return $requestedIds
}

function Assert-Location([object]$Location) {
    if ($null -eq $Location) {
        throw 'SELECTION_LOCATION_INVALID'
    }
    $id = [string]$Location.id
    if ($id -notmatch '^m[0-9]{1,6}$') {
        throw 'SELECTION_ID_INVALID'
    }
    $relativePath = $Location.path
    if ($relativePath -isnot [string] -or [string]::IsNullOrWhiteSpace($relativePath) -or $relativePath.Length -gt 512) {
        throw 'SELECTION_PATH_INVALID'
    }
    $lineValue = $Location.line
    if ($lineValue -is [string]) {
        if ($lineValue -notmatch '^[0-9]+$') {
            throw 'SELECTION_LINE_INVALID'
        }
        $line = [int64]$lineValue
    }
    else {
        try {
            $line = [int64]$lineValue
            if ([double]$lineValue -ne [double]$line) {
                throw 'SELECTION_LINE_INVALID'
            }
        }
        catch {
            throw 'SELECTION_LINE_INVALID'
        }
    }
    if ($line -lt 1 -or $line -gt $MaximumLinesScannedPerFile) {
        throw 'SELECTION_LINE_INVALID'
    }
}

function Get-LocationDocument([object]$Document, [string]$RequiredPhase = 'locations') {
    if ($Document.phase -ne $RequiredPhase) {
        throw "${RequiredPhase.ToUpperInvariant()}_INPUT_REQUIRED"
    }
    if ($null -eq $Document.matches) {
        throw 'SELECTION_LOCATIONS_REQUIRED'
    }
    foreach ($location in @($Document.matches)) {
        Assert-Location $location
    }
    return $Document
}

function Get-SelectionDocument {
    $document = Read-JsonInput
    if ($document.phase -ne 'select') {
        throw 'SELECTION_INPUT_REQUIRED'
    }
    if ($null -eq $document.selections) {
        throw 'SELECTIONS_REQUIRED'
    }
    foreach ($selection in @($document.selections)) {
        Assert-Location $selection
    }
    return $document
}

function Get-SelectedLocation([object]$Document, [string]$Id) {
    $locations = @($Document.matches)
    $match = @($locations | Where-Object { [string]$_.id -eq $Id }) | Select-Object -First 1
    if ($null -eq $match) {
        throw 'SELECTION_ID_NOT_FOUND'
    }
    Assert-Location $match
    return $match
}

function Get-SelectedFile([string]$Root, [string]$RelativePath) {
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        [IO.Path]::IsPathRooted($RelativePath) -or
        $RelativePath -match '^[A-Za-z]:[\\/]') {
        throw 'DIAGNOSTIC_SELECTION_PATH_INVALID'
    }
    $separator = [string][IO.Path]::DirectorySeparatorChar
    $normalizedRelative = $RelativePath.Replace('\', $separator).Replace('/', $separator)
    if (Test-ProtectedRelativePath ($RelativePath.Replace('\', '/'))) {
        throw 'DIAGNOSTIC_PATH_PROTECTED'
    }
    try {
        $candidate = [IO.Path]::GetFullPath([IO.Path]::Combine($Root, $normalizedRelative))
        Assert-PathWithinRoot $Root $candidate
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf -ErrorAction Stop)) {
            throw 'DIAGNOSTIC_SELECTION_FILE_MISSING'
        }
        Assert-ContainedFile $Root $candidate
        $resolved = (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
        Assert-PathWithinRoot $Root $resolved
        $resolvedRelative = Get-RelativePath $Root $resolved
        if (Test-ProtectedRelativePath $resolvedRelative) {
            throw 'DIAGNOSTIC_PATH_PROTECTED'
        }
        return $resolved
    }
    catch {
        if ($_.Exception.Message -like 'DIAGNOSTIC_*') {
            throw
        }
        throw 'DIAGNOSTIC_SELECTION_FILE_MISSING'
    }
}

function Limit-Line([string]$Line) {
    if ($Line.Length -le $MaximumLineCharacters) {
        return [pscustomobject]@{ text = $Line; truncated = $false }
    }
    return [pscustomobject]@{
        text = $Line.Substring(0, $MaximumLineCharacters) + '...[line-truncated]'
        truncated = $true
    }
}

function Get-BoundedSlice([string]$Root, [object]$Location) {
    Assert-Location $Location
    $lineNumber = [int]$Location.line
    $filePath = Get-SelectedFile $Root ([string]$Location.path)
    $startLine = [Math]::Max(1, $lineNumber - $Before)
    $endLine = $lineNumber + $After
    $lines = @()
    $lineWasTruncated = $false
    $currentLine = 0
    try {
        foreach ($line in [IO.File]::ReadLines($filePath)) {
            $currentLine++
            if ($currentLine -gt $MaximumLinesScannedPerFile) {
                break
            }
            if ($currentLine -gt $endLine) {
                break
            }
            if ($currentLine -ge $startLine) {
                $limited = Limit-Line $line
                $lines += $limited.text
                if ($limited.truncated) {
                    $lineWasTruncated = $true
                }
            }
        }
    }
    catch {
        throw "SLICE_READ_FAILED:$($Location.path)"
    }
    if ($lines.Count -eq 0) {
        throw 'SELECTION_LINE_NOT_FOUND'
    }
    return [ordered]@{
        id = [string]$Location.id
        path = [string]$Location.path
        selected_line = $lineNumber
        start_line = $startLine
        end_line = $endLine
        line_truncated = $lineWasTruncated
        lines = $lines
    }
}

function Find-Matches([string]$Root, [object]$Regex, [object]$FileSet) {
    $matches = @()
    $cachedSlices = @()
    $matchCount = 0
    $scanned = 0
    $truncated = [bool]$FileSet.truncated
    $totalLines = 0
    $totalBytes = 0

    foreach ($file in @($FileSet.files)) {
        if ($totalLines -ge $MaximumTotalLinesScanned -or $totalBytes -ge $MaximumTotalBytesScanned) {
            $truncated = $true
            break
        }
        $scanned++
        $relative = Get-RelativePath $Root $file.FullName
        Assert-ContainedFile $Root $file.FullName
        $lineNumber = 0
        $fileTruncated = $false
        $recentLines = @()
        $pendingSlices = @()
        try {
            foreach ($line in [IO.File]::ReadLines($file.FullName)) {
                $lineNumber++
                $lineBytes = [Text.Encoding]::UTF8.GetByteCount($line) + 1
                if ($lineNumber -gt $MaximumLinesScannedPerFile -or
                    $totalLines -ge $MaximumTotalLinesScanned -or
                    $totalBytes + $lineBytes -gt $MaximumTotalBytesScanned) {
                    $truncated = $true
                    $fileTruncated = $true
                    break
                }
                $totalLines++
                $totalBytes += $lineBytes

                $limited = Limit-Line $line
                if ($pendingSlices.Count -gt 0) {
                    $remainingSlices = @()
                    foreach ($pendingSlice in @($pendingSlices)) {
                        $pendingSlice.lines += $limited.text
                        if ($limited.truncated) {
                            $pendingSlice.line_truncated = $true
                        }
                        $pendingSlice.remaining--
                        if ($pendingSlice.remaining -le 0) {
                            $slice = [ordered]@{
                                id = $pendingSlice.id
                                path = $pendingSlice.path
                                selected_line = $pendingSlice.selected_line
                                start_line = $pendingSlice.start_line
                                end_line = $pendingSlice.end_line
                                line_truncated = $pendingSlice.line_truncated
                                lines = @($pendingSlice.lines)
                            }
                            $cachedSlices += [pscustomobject]$slice
                        }
                        else {
                            $remainingSlices += $pendingSlice
                        }
                    }
                    $pendingSlices = $remainingSlices
                }

                if ($Regex.IsMatch($line)) {
                    $matchCount++
                    if ($matches.Count -lt $MaxMatches) {
                        $matchId = "m$($matches.Count + 1)"
                        $matches += [ordered]@{
                            id = $matchId
                            path = $relative
                            line = $lineNumber
                        }
                        $initialLines = @($recentLines | ForEach-Object { $_.text }) + @($limited.text)
                        $initialTruncated = $limited.truncated -or @($recentLines | Where-Object { $_.truncated }).Count -gt 0
                        $remaining = $After
                        $pendingSlice = [pscustomobject]@{
                            id = $matchId
                            path = $relative
                            selected_line = $lineNumber
                            start_line = [Math]::Max(1, $lineNumber - $Before)
                            end_line = $lineNumber + $After
                            line_truncated = $initialTruncated
                            lines = $initialLines
                            remaining = $remaining
                        }
                        if ($remaining -le 0) {
                            $cachedSlices += [pscustomobject][ordered]@{
                                id = $pendingSlice.id
                                path = $pendingSlice.path
                                selected_line = $pendingSlice.selected_line
                                start_line = $pendingSlice.start_line
                                end_line = $pendingSlice.end_line
                                line_truncated = $pendingSlice.line_truncated
                                lines = @($pendingSlice.lines)
                            }
                        }
                        else {
                            $pendingSlices += $pendingSlice
                        }
                    }
                    else {
                        $truncated = $true
                        $fileTruncated = $true
                        break
                    }
                }

                $recentLines += [pscustomobject]@{
                    text = $limited.text
                    truncated = $limited.truncated
                }
                if ($recentLines.Count -gt $Before) {
                    $recentLines = @($recentLines | Select-Object -Last $Before)
                }
            }
        }
        catch {
            throw "DISCOVERY_READ_FAILED:$relative"
        }
        foreach ($pendingSlice in @($pendingSlices)) {
            $cachedSlices += [pscustomobject][ordered]@{
                id = $pendingSlice.id
                path = $pendingSlice.path
                selected_line = $pendingSlice.selected_line
                start_line = $pendingSlice.start_line
                end_line = $pendingSlice.end_line
                line_truncated = $pendingSlice.line_truncated
                lines = @($pendingSlice.lines)
            }
        }
        if ($matches.Count -ge $MaxMatches -or $fileTruncated -and
            ($totalLines -ge $MaximumTotalLinesScanned -or $totalBytes -ge $MaximumTotalBytesScanned)) {
            break
        }
    }

    return [pscustomobject]@{
        matches = $matches
        match_count = $matchCount
        matches_returned = $matches.Count
        files_considered = $FileSet.all_count
        files_scanned = $scanned
        files_skipped = $FileSet.all_count - $scanned
        lines_scanned = $totalLines
        bytes_scanned = $totalBytes
        slices = $cachedSlices
        truncated = $truncated
    }
}

function New-Regex {
    if ([string]::IsNullOrWhiteSpace($Pattern) -or $Pattern.Length -gt 200) {
        throw 'PATTERN_REQUIRED_OR_TOO_LONG'
    }
    $options = [Text.RegularExpressions.RegexOptions]::None
    if ($IgnoreCase) {
        $options = [Text.RegularExpressions.RegexOptions]::IgnoreCase
    }
    try {
        return [regex]::new($Pattern, $options, [TimeSpan]::FromMilliseconds(250))
    }
    catch {
        throw 'PATTERN_INVALID'
    }
}

function Write-LocationsResult([object]$Scan, [string]$Phase = 'locations', [string]$Contract = 'bounded_ambiguous_locations') {
    $returned = @($Scan.matches | Select-Object -First ([Math]::Min($Scan.matches.Count, $MaximumReturnedLocations)))
    $truncated = [bool]$Scan.truncated -or $Scan.matches.Count -gt $returned.Count
    while ($true) {
        $document = [ordered]@{
            phase = $Phase
            contract = $Contract
            operation = 'read'
            files_considered = $Scan.files_considered
            files_scanned = $Scan.files_scanned
            files_skipped = $Scan.files_skipped
            lines_scanned = $Scan.lines_scanned
            bytes_scanned = $Scan.bytes_scanned
            match_count = $Scan.match_count
            matches_returned = $returned.Count
            truncated = $truncated
            matches = $returned
        }
        $json = $document | ConvertTo-Json -Depth 8 -Compress
        if ([Text.Encoding]::UTF8.GetByteCount($json) -le $MaximumOutputBytes) {
            Assert-SafeOutput $json
            [Console]::Out.WriteLine($json)
            return
        }
        if ($returned.Count -le 1) {
            throw 'DIAGNOSTIC_OUTPUT_TOO_LARGE'
        }
        $returned = @($returned | Select-Object -First ($returned.Count - 1))
        $truncated = $true
    }
}

function Write-SliceResult([object[]]$Slices, [string]$Selection = 'deterministic', [object]$Scan = $null) {
    $result = [ordered]@{
        phase = 'slice'
        contract = 'bounded_selected_content'
        operation = 'read'
        selection = $Selection
        before = $Before
        after = $After
        slice_count = $Slices.Count
        slices = $Slices
    }
    if ($null -ne $Scan) {
        $result.files_considered = $Scan.files_considered
        $result.files_scanned = $Scan.files_scanned
        $result.files_skipped = $Scan.files_skipped
        $result.lines_scanned = $Scan.lines_scanned
        $result.bytes_scanned = $Scan.bytes_scanned
        $result.match_count = $Scan.match_count
        $result.truncated = $Scan.truncated
    }
    Write-BoundedJson $result
}

$root = Get-RepositoryRoot

switch ($Mode) {
    'Read' {
        $requestedIds = @(Get-RequestedIds)
        if ($requestedIds.Count -gt 1) {
            throw 'SELECTION_ID_REQUIRED_OR_TOO_MANY'
        }

        if ($requestedIds.Count -eq 1) {
            $document = Get-LocationDocument (Read-JsonInput)
            $location = Get-SelectedLocation $document $requestedIds[0]
            $slice = Get-BoundedSlice $root $location
            Write-SliceResult @($slice) 'explicit'
            break
        }

        $regex = New-Regex
        $fileSet = Resolve-SearchFiles $root
        $scan = Find-Matches $root $regex $fileSet
        $isDeterministic = $scan.match_count -eq 1 -and
            $scan.matches.Count -eq 1 -and
            -not $scan.truncated
        if ($isDeterministic) {
            $cached = @($scan.slices | Where-Object { $_.id -eq $scan.matches[0].id }) | Select-Object -First 1
            $slice = if ($null -ne $cached) { $cached } else { Get-BoundedSlice $root $scan.matches[0] }
            Write-SliceResult @($slice) 'deterministic' $scan
        }
        else {
            Write-LocationsResult $scan
        }
        break
    }
    'Discover' {
        $regex = New-Regex
        $fileSet = Resolve-SearchFiles $root
        $scan = Find-Matches $root $regex $fileSet
        Write-LocationsResult $scan 'discover' 'identifiers_and_locations_only'
        break
    }
    'Select' {
        $requestedIds = @(Get-RequestedIds)
        if ($requestedIds.Count -lt 1 -or $requestedIds.Count -gt $MaxSelections) {
            throw 'SELECTION_IDS_REQUIRED_OR_TOO_MANY'
        }
        $document = Get-LocationDocument (Read-JsonInput) 'discover'
        $selected = @()
        foreach ($id in $requestedIds) {
            if (@($selected | Where-Object { $_.id -eq $id }).Count -gt 0) {
                throw 'SELECTION_IDS_INVALID_OR_DUPLICATE'
            }
            $location = Get-SelectedLocation $document $id
            $selected += [ordered]@{
                id = [string]$location.id
                path = [string]$location.path
                line = [int]$location.line
            }
        }
        $selectionResult = [ordered]@{
            phase = 'select'
            contract = 'selected_locations_only'
            selection_count = $selected.Count
            selections = $selected
        }
        Write-BoundedJson $selectionResult
        break
    }
    'Slice' {
        $document = Get-SelectionDocument
        $selections = @($document.selections)
        if ($selections.Count -lt 1 -or $selections.Count -gt $MaxSelections) {
            throw 'SELECTION_COUNT_INVALID'
        }
        $slices = @()
        foreach ($selection in $selections) {
            $slices += Get-BoundedSlice $root $selection
        }
        Write-SliceResult $slices 'legacy-selected'
        break
    }
}
