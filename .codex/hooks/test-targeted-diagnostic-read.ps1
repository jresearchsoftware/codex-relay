#requires -Version 7.2
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'targeted-diagnostic-read.ps1'
$powerShellExecutable = (Get-Command pwsh -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$testContainer = Join-Path ([System.IO.Path]::GetTempPath()) ('fixture-diagnostic-test-' + [guid]::NewGuid().ToString('N'))
$testRoot = Join-Path $testContainer 'repository'
New-Item -ItemType Directory -Path $testRoot | Out-Null

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION_FAILED:$Message" }
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Invoke-Helper(
    [string[]]$HelperArguments,
    [string]$InputText = $null
) {
    if ($null -ne $InputText) {
        $raw = $InputText | & $powerShellExecutable -NoProfile -NonInteractive -File $scriptPath @HelperArguments 2>&1 | Out-String
    }
    else {
        $raw = & $powerShellExecutable -NoProfile -NonInteractive -File $scriptPath @HelperArguments 2>&1 | Out-String
    }
    $json = $null
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
        try {
            $json = $raw.Trim() | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            $json = $null
        }
    }
    return [pscustomobject]@{
        exit_code = $LASTEXITCODE
        output = $raw
        json = $json
    }
}

try {
    $sourcePath = Join-Path $testRoot 'source.ps1'
    $testPath = Join-Path $testRoot 'tests.ps1'
    $docsPath = Join-Path $testRoot 'docs.md'
    $secretPath = Join-Path $testRoot 'secret.ps1'
    $symlinkPath = Join-Path $testRoot 'outside-link.txt'
    Write-Utf8NoBom $sourcePath (@(
            'param()'
            '# source fixture'
            'Write-Output "noise"'
            '# selected source signal'
            ('# needle source ' + ('x' * 1000))
            'Write-Output "after"'
        ) -join [Environment]::NewLine)
    Write-Utf8NoBom $testPath (@(
            '# tests fixture'
            '# noise'
            '# needle test signal'
        ) -join [Environment]::NewLine)
    Write-Utf8NoBom $docsPath (@(
            '# docs fixture'
            '# needle docs signal'
            '# another needle docs signal'
        ) -join [Environment]::NewLine)
    Write-Utf8NoBom (Join-Path $testRoot '.git') 'protected fixture path'
    Write-Utf8NoBom $secretPath (@(
            '# needle secret signal'
            '"token": "not-a-real-secret"'
        ) -join [Environment]::NewLine)
    for ($index = 0; $index -lt 45; $index++) {
        $noisePath = Join-Path $testRoot ('{0:D2}-noise.ps1' -f $index)
        Write-Utf8NoBom $noisePath "# unrelated fixture $index"
    }
    $lateTargetPath = Join-Path $testRoot 'zz-late-target.ps1'
    Write-Utf8NoBom $lateTargetPath '# late-file-signal'

    $common = @('-RepositoryRoot', $testRoot)
    $direct = Invoke-Helper ($common + @('-SearchPath', $sourcePath, '-Pattern', 'needle'))
    Assert-True ($direct.exit_code -eq 0) "one-shot deterministic read failed: $($direct.output)"
    Assert-True ($direct.json.phase -eq 'slice' -and $direct.json.operation -eq 'read') 'deterministic read did not return a slice result'
    Assert-True ($direct.json.selection -eq 'deterministic') 'deterministic read was not classified as deterministic'
    Assert-True ($direct.json.slice_count -eq 1 -and $direct.json.slices[0].lines -match 'needle source') 'deterministic read omitted source content'
    Assert-True ($direct.json.slices[0].line_truncated) 'long source line was not bounded'
    Assert-True ([Text.Encoding]::UTF8.GetByteCount($direct.output.Trim()) -le 8192) 'deterministic read exceeded the output bound'

    $late = Invoke-Helper ($common + @('-SearchPath', $testRoot, '-Pattern', 'late-file-signal'))
    Assert-True ($late.exit_code -eq 0) "late-file read failed: $($late.output)"
    Assert-True ($late.json.selection -eq 'deterministic' -and $late.json.slices[0].path -eq 'zz-late-target.ps1') 'a match after the first 40 files was missed'
    Assert-True ($late.json.files_considered -gt 40 -and $late.json.files_scanned -gt 40) 'late-file regression did not scan beyond the old file cap'

    $ambiguous = Invoke-Helper ($common + @('-SearchPath', $testRoot, '-Pattern', 'needle', '-MaxMatches', '20'))
    Assert-True ($ambiguous.exit_code -eq 0) "one-shot ambiguous read failed: $($ambiguous.output)"
    Assert-True ($ambiguous.json.phase -eq 'locations' -and $ambiguous.json.contract -eq 'bounded_ambiguous_locations') 'ambiguous read did not return compact locations'
    Assert-True ($ambiguous.json.match_count -eq 5 -and $ambiguous.json.matches_returned -eq 5) 'ambiguous read did not report all fixture locations'
    Assert-True ($ambiguous.output -notmatch 'needle source|needle test|needle docs|needle secret') 'ambiguous read leaked source content'
    foreach ($match in @($ambiguous.json.matches)) {
        Assert-True ($match.id -and $match.path -and ($match.line -gt 0)) 'ambiguous location is incomplete'
        Assert-True (-not ($match.PSObject.Properties.Name -contains 'text') -and -not ($match.PSObject.Properties.Name -contains 'content')) 'ambiguous location emitted content'
    }

    $sourceMatch = @($ambiguous.json.matches | Where-Object { $_.path -eq 'source.ps1' }) | Select-Object -First 1
    Assert-True ($null -ne $sourceMatch) 'source location was not returned for the bounded follow-up'
    $followup = Invoke-Helper ($common + @('-Mode', 'Read', '-Ids', [string]$sourceMatch.id)) ($ambiguous.output.Trim())
    Assert-True ($followup.exit_code -eq 0) "single selection follow-up failed: $($followup.output)"
    Assert-True ($followup.json.selection -eq 'explicit' -and $followup.json.slices[0].lines -match 'needle source') 'selection follow-up did not return the requested slice'

    $discovery = Invoke-Helper ($common + @('-Mode', 'Discover', '-SearchPath', $testRoot, '-Pattern', 'needle', '-MaxMatches', '20'))
    Assert-True ($discovery.exit_code -eq 0 -and $discovery.json.phase -eq 'discover') 'compatibility discovery mode failed'
    $discoverySelection = @($discovery.json.matches | Where-Object { $_.path -eq 'tests.ps1' }) | Select-Object -First 1
    $selected = Invoke-Helper ($common + @('-Mode', 'Select', '-Ids', [string]$discoverySelection.id)) $discovery.output.Trim()
    Assert-True ($selected.exit_code -eq 0 -and $selected.json.phase -eq 'select') 'compatibility selection mode failed'
    $legacySlice = Invoke-Helper ($common + @('-Mode', 'Slice', '-Before', '1', '-After', '1')) $selected.output.Trim()
    Assert-True ($legacySlice.exit_code -eq 0 -and $legacySlice.json.phase -eq 'slice' -and $legacySlice.json.slices[0].lines -match 'needle test') 'compatibility slice mode failed'

    $directSlice = Invoke-Helper ($common + @('-Mode', 'Slice'))
    Assert-True ($directSlice.exit_code -ne 0 -and $directSlice.output -match 'PIPELINE_INPUT_REQUIRED') 'unselected compatibility slice did not fail safely'

    $outside = Join-Path $testContainer 'fixture-outside.txt'
    Write-Utf8NoBom $outside 'needle outside'
    $outsideResult = Invoke-Helper ($common + @('-SearchPath', $outside, '-Pattern', 'needle'))
    Assert-True ($outsideResult.exit_code -ne 0 -and $outsideResult.output -match 'DIAGNOSTIC_PATH_OUTSIDE_REPOSITORY') 'outside search path was accepted'

    $protected = Invoke-Helper ($common + @('-SearchPath', (Join-Path $testRoot '.git'), '-Pattern', 'needle'))
    Assert-True ($protected.exit_code -ne 0 -and $protected.output -match 'DIAGNOSTIC_PATH_PROTECTED') 'protected search path was accepted'

    $traversalDocument = '{"phase":"locations","matches":[{"id":"m1","path":"../fixture-outside.txt","line":1}]}'
    $traversal = Invoke-Helper ($common + @('-Mode', 'Read', '-Ids', 'm1')) $traversalDocument
    Assert-True ($traversal.exit_code -ne 0 -and $traversal.output -match 'DIAGNOSTIC_PATH_OUTSIDE_REPOSITORY') 'selected path traversal was accepted'

    try {
        New-Item -ItemType SymbolicLink -Path $symlinkPath -Target $outside -ErrorAction Stop | Out-Null
        $symlinkDocument = '{"phase":"locations","matches":[{"id":"m1","path":"outside-link.txt","line":1}]}'
        $symlink = Invoke-Helper ($common + @('-Mode', 'Read', '-Ids', 'm1')) $symlinkDocument
        Assert-True ($symlink.exit_code -ne 0 -and $symlink.output -match 'DIAGNOSTIC_PATH_OUTSIDE_REPOSITORY|DIAGNOSTIC_SYMLINK_INVALID') 'symlink escape was accepted'
    }
    catch {
        if ($_.Exception.Message -like 'ASSERTION_FAILED:*') { throw }
    }

    $secret = Invoke-Helper ($common + @('-SearchPath', $secretPath, '-Pattern', 'needle'))
    Assert-True ($secret.exit_code -ne 0 -and $secret.output -match 'SENSITIVE_CONTENT_REJECTED') 'sensitive source content was emitted'

    Write-Output 'PASS: one-shot deterministic and ambiguous reads, late-file coverage beyond 40 entries, one-selection follow-up, compatibility phases, path confinement, protected paths, line/output bounds, and secret rejection'
}
finally {
    if (Test-Path -LiteralPath $testContainer) {
        $resolvedContainer = (Resolve-Path -LiteralPath $testContainer).Path
        $expectedContainer = Join-Path ([IO.Path]::GetTempPath()) (Split-Path -Leaf $testContainer)
        if ($resolvedContainer -ne [IO.Path]::GetFullPath($expectedContainer) -or
            (Split-Path -Leaf $testContainer) -notmatch '^fixture-diagnostic-test-[a-f0-9]{32}$') { throw 'UNSAFE_FIXTURE_CLEANUP' }
        Remove-Item -LiteralPath $testContainer -Recurse -Force
    }
}
