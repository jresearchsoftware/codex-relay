#requires -Version 7.2
[CmdletBinding()]
param(
    [ValidateSet('Path', 'Validate', 'Write', 'Invalidate', 'Delete', 'Refresh', 'Recover', 'Announce')]
    [string]$Mode = 'Recover',
    [string]$CheckpointPath,
    [string]$RepositoryRoot,
    [string]$SessionId,
    [string]$DiagnosticFrontier,
    [string]$NextSafeReadOnlyAction,
    [string]$BoundaryId,
    [string]$Reason,
    [Parameter(ValueFromPipeline = $true)]
    [string]$HookInput
)

$ErrorActionPreference = 'Stop'
$SchemaVersion = 3
$MaximumBytes = 8192
$MaximumAgeHours = 24
$MaximumRecoverySummaryBytes = 4096
$MaximumFrontierLength = 2000
$MaximumNextActionLength = 1000

# Hook commands receive JSON on stdin. Direct PowerShell tests use pipeline
# input, while a child process launched by the Codex hook uses Console input.
$script:PipelineInput = if ($HookInput) { @($HookInput) } else { @($input) }

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

function Assert-SessionId([string]$Value, [string]$Name = 'session_id') {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Length -gt 256 -or $Value -match '[\r\n]') {
        throw "INVALID_FIELD:$Name"
    }
}

function Assert-SafeContent([string]$Raw) {
    $sensitivePatterns = @(
        '(?i)\\?"(?:authorization|cookie|password|private[_-]?key|secret|token)\\?"\s*:',
        '(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----',
        '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}',
        '\bsk-[A-Za-z0-9_-]{12,}',
        '\bgh[pousr]_[A-Za-z0-9]{12,}'
    )
    foreach ($pattern in $sensitivePatterns) {
        if ($Raw -match $pattern) {
            throw 'SENSITIVE_CONTENT_REJECTED'
        }
    }
}

function Get-SessionCheckpointKey([string]$OwnerSessionId) {
    Assert-SessionId $OwnerSessionId
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($OwnerSessionId)
        $digest = $sha256.ComputeHash($bytes)
        return ([BitConverter]::ToString($digest) -replace '-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-CheckpointPath([string]$Root, [string]$OwnerSessionId) {
    Assert-SessionId $OwnerSessionId
    $sessionKey = Get-SessionCheckpointKey $OwnerSessionId
    if ($CheckpointPath) {
        try {
            $basePath = [IO.Path]::GetFullPath($CheckpointPath)
            $parent = [IO.Path]::GetDirectoryName($basePath)
            $leaf = [IO.Path]::GetFileName($basePath)
            if ([string]::IsNullOrWhiteSpace($parent) -or [string]::IsNullOrWhiteSpace($leaf)) {
                throw 'CHECKPOINT_PATH_INVALID'
            }
            $extension = [IO.Path]::GetExtension($leaf)
            $stem = [IO.Path]::GetFileNameWithoutExtension($leaf)
            if ([string]::IsNullOrWhiteSpace($extension)) {
                $extension = '.json'
            }
            return Join-Path $parent ($stem + '.session-' + $sessionKey + $extension)
        }
        catch {
            if ($_.Exception.Message -eq 'CHECKPOINT_PATH_INVALID') {
                throw
            }
            throw 'CHECKPOINT_PATH_INVALID'
        }
    }
    return Join-Path (Join-Path (Join-Path (Join-Path $Root '.codex') 'local') 'long-session-checkpoints') ($sessionKey + '.json')
}

function Get-GitValue([string]$Root, [string[]]$Arguments) {
    $value = (& git -C $Root @Arguments 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $value) {
        throw "GIT_QUERY_FAILED:$($Arguments -join ' ')"
    }
    return (@($value) -join [Environment]::NewLine).Trim()
}

function Get-RepositorySlug([string]$Root) {
    $remote = Get-GitValue $Root @('remote', 'get-url', 'origin')
    if ($remote -notmatch '(?i)(?:github\.com)[:/](?<slug>[^/\s]+/[^/\s]+?)(?:\.git)?$') {
        throw 'CHECKPOINT_REPOSITORY_UNVERIFIED'
    }
    return $Matches.slug.ToLowerInvariant()
}

function Get-RequiredText($Object, [string]$Name, [int]$MaximumLength = 2000) {
    $value = $Object.$Name
    if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value) -or $value.Length -gt $MaximumLength) {
        throw "INVALID_FIELD:$Name"
    }
    Assert-SafeContent $value
    return $value
}

function Get-OptionalText($Object, [string]$Name, [int]$MaximumLength = 2000) {
    $value = $Object.$Name
    if ($null -eq $value) {
        return $null
    }
    if ($value -isnot [string] -or $value.Length -gt $MaximumLength) {
        throw "INVALID_FIELD:$Name"
    }
    if ($value.Length -gt 0) {
        Assert-SafeContent $value
    }
    return $value
}

function Assert-InputText([string]$Value, [string]$Name, [int]$MaximumLength, [bool]$Required) {
    if ($null -eq $Value) {
        if ($Required) {
            throw "INVALID_FIELD:$Name"
        }
        return
    }
    if ($Value.Length -gt $MaximumLength -or ($Required -and [string]::IsNullOrWhiteSpace($Value))) {
        throw "INVALID_FIELD:$Name"
    }
    if ($Value.Length -gt 0) {
        Assert-SafeContent $Value
    }
}

function ConvertTo-UtcDateTime([object]$Value, [string]$Name) {
    try {
        if ($Value -is [DateTimeOffset]) {
            $parsed = $Value
        }
        elseif ($Value -is [DateTime]) {
            $parsed = [DateTimeOffset]$Value
        }
        else {
            $parsed = [DateTimeOffset]::Parse(
                [string]$Value,
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::RoundtripKind
            )
        }
    }
    catch {
        throw "INVALID_FIELD:$Name"
    }
    return $parsed.ToUniversalTime()
}

function Test-Property($Object, [string]$Name) {
    return $null -ne $Object -and $null -ne $Object.PSObject.Properties[$Name]
}

function Assert-AllowedProperties($Object, [string[]]$Allowed) {
    foreach ($property in @($Object.PSObject.Properties.Name)) {
        if ($property -notin $Allowed) {
            throw "INVALID_FIELD:$property"
        }
    }
}

function Assert-Capture($Capture, [string]$ExpectedSessionId) {
    Assert-AllowedProperties $Capture @('event', 'trigger', 'session_id', 'captured_at', 'turn_id')
    if ($Capture.event -ne 'PreCompact') { throw 'INVALID_FIELD:capture.event' }
    if ($Capture.trigger -ne 'auto') { throw 'INVALID_FIELD:capture.trigger' }
    $captureSessionId = Get-RequiredText $Capture 'session_id' 256
    Assert-SessionId $captureSessionId 'capture.session_id'
    if ($captureSessionId -ne $ExpectedSessionId) {
        throw 'CHECKPOINT_CAPTURE_SESSION_MISMATCH'
    }
    $capturedAt = ConvertTo-UtcDateTime $Capture.captured_at 'capture.captured_at'
    if ($capturedAt -gt [DateTimeOffset]::UtcNow.AddMinutes(5)) {
        throw 'CHECKPOINT_CAPTURE_FUTURE'
    }
    if ($capturedAt -lt [DateTimeOffset]::UtcNow.AddHours(-$MaximumAgeHours)) {
        throw 'CHECKPOINT_CAPTURE_STALE'
    }
    Get-OptionalText $Capture 'turn_id' 256 | Out-Null
}

function Assert-Checkpoint($Checkpoint, [string]$Root, [string]$ExpectedSessionId = $null) {
    if ($null -eq $Checkpoint -or $Checkpoint -is [System.Array]) {
        throw 'CHECKPOINT_INVALID_JSON'
    }
    Assert-AllowedProperties $Checkpoint @(
        'schema_version', 'session_id', 'repository', 'branch', 'head',
        'diagnostic_frontier', 'next_safe_read_only_action', 'written_at', 'capture'
    )
    if ($Checkpoint.schema_version -ne $SchemaVersion) { throw 'INVALID_FIELD:schema_version' }
    $checkpointSessionId = Get-RequiredText $Checkpoint 'session_id' 256
    Assert-SessionId $checkpointSessionId
    if ($ExpectedSessionId -and $checkpointSessionId -ne $ExpectedSessionId) {
        throw 'CHECKPOINT_SESSION_MISMATCH'
    }
    $repository = Get-RequiredText $Checkpoint 'repository' 512
    if ($repository.ToLowerInvariant() -ne (Get-RepositorySlug $Root)) {
        throw 'CHECKPOINT_STALE_REPOSITORY'
    }
    Get-RequiredText $Checkpoint 'branch' 256 | Out-Null
    $head = Get-RequiredText $Checkpoint 'head' 64
    if ($head -notmatch '^[0-9a-f]{40}$') { throw 'INVALID_FIELD:head' }
    Get-RequiredText $Checkpoint 'diagnostic_frontier' $MaximumFrontierLength | Out-Null
    Get-OptionalText $Checkpoint 'next_safe_read_only_action' $MaximumNextActionLength | Out-Null

    $writtenAt = ConvertTo-UtcDateTime $Checkpoint.written_at 'written_at'
    if ($writtenAt -gt [DateTimeOffset]::UtcNow.AddMinutes(5) -or
        $writtenAt -lt [DateTimeOffset]::UtcNow.AddHours(-$MaximumAgeHours)) {
        throw 'CHECKPOINT_STALE_TIME'
    }
    if (Test-Property $Checkpoint 'capture' -and $null -ne $Checkpoint.capture) {
        Assert-Capture $Checkpoint.capture $checkpointSessionId
    }
    return $Checkpoint
}

function Read-Checkpoint([string]$Path, [string]$Root, [string]$ExpectedSessionId = $null) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw 'CHECKPOINT_MISSING'
    }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Length -gt $MaximumBytes) {
        throw 'CHECKPOINT_TOO_LARGE'
    }
    $raw = Get-Content -Raw -LiteralPath $Path
    Assert-SafeContent $raw
    try {
        $checkpoint = $raw | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw 'CHECKPOINT_INVALID_JSON'
    }
    Assert-Checkpoint $checkpoint $Root $ExpectedSessionId | Out-Null
    return $checkpoint
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Write-CheckpointAtomically([string]$Path, [string]$Root, $Checkpoint) {
    Assert-Checkpoint $Checkpoint $Root $Checkpoint.session_id | Out-Null
    $json = $Checkpoint | ConvertTo-Json -Depth 8
    Assert-SafeContent $json
    if ([Text.Encoding]::UTF8.GetByteCount($json) -gt $MaximumBytes) {
        throw 'CHECKPOINT_TOO_LARGE'
    }
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temporary = Join-Path $parent ('.checkpoint-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        Write-Utf8NoBom $temporary $json
        Read-Checkpoint $temporary $Root $Checkpoint.session_id | Out-Null
        Move-Item -LiteralPath $temporary -Destination $Path -Force | Out-Null
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function New-Checkpoint([string]$Root, [string]$OwnerSessionId, [string]$Frontier, [string]$NextAction) {
    Assert-SessionId $OwnerSessionId
    Assert-InputText $Frontier 'diagnostic_frontier' $MaximumFrontierLength $true
    Assert-InputText $NextAction 'next_safe_read_only_action' $MaximumNextActionLength $false
    $checkpoint = [ordered]@{
        schema_version = $SchemaVersion
        session_id = $OwnerSessionId
        repository = Get-RepositorySlug $Root
        branch = Get-GitValue $Root @('rev-parse', '--abbrev-ref', 'HEAD')
        head = Get-GitValue $Root @('rev-parse', 'HEAD')
        diagnostic_frontier = $Frontier
        written_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    if ($null -ne $NextAction -and $NextAction.Length -gt 0) {
        $checkpoint.next_safe_read_only_action = $NextAction
    }
    return [pscustomobject]$checkpoint
}

function Copy-CheckpointWithCapture($Checkpoint, [string]$OwnerSessionId, [string]$TurnId) {
    $copy = [ordered]@{
        schema_version = $Checkpoint.schema_version
        session_id = $Checkpoint.session_id
        repository = $Checkpoint.repository
        branch = $Checkpoint.branch
        head = $Checkpoint.head
        diagnostic_frontier = $Checkpoint.diagnostic_frontier
        written_at = $Checkpoint.written_at
    }
    if (Test-Property $Checkpoint 'next_safe_read_only_action' -and $null -ne $Checkpoint.next_safe_read_only_action) {
        $copy.next_safe_read_only_action = $Checkpoint.next_safe_read_only_action
    }
    $capture = [ordered]@{
        event = 'PreCompact'
        trigger = 'auto'
        session_id = $OwnerSessionId
        captured_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    if ($null -ne $TurnId -and $TurnId.Length -gt 0) {
        $capture.turn_id = $TurnId
    }
    $copy.capture = [pscustomobject]$capture
    return [pscustomobject]$copy
}

function Get-RecoverySummary($Checkpoint) {
    $projection = [ordered]@{
        session_id = $Checkpoint.session_id
        repository = $Checkpoint.repository
        branch = $Checkpoint.branch
        head = $Checkpoint.head
        diagnostic_frontier = $Checkpoint.diagnostic_frontier
        written_at = $Checkpoint.written_at
    }
    if (Test-Property $Checkpoint 'next_safe_read_only_action' -and $null -ne $Checkpoint.next_safe_read_only_action) {
        $projection.next_safe_read_only_action = $Checkpoint.next_safe_read_only_action
    }
    if (Test-Property $Checkpoint 'capture' -and $null -ne $Checkpoint.capture) {
        $projection.captured_at = $Checkpoint.capture.captured_at
    }
    $json = $projection | ConvertTo-Json -Depth 6 -Compress
    if ([Text.Encoding]::UTF8.GetByteCount($json) -gt $MaximumRecoverySummaryBytes) {
        throw 'RECOVERY_SUMMARY_TOO_LARGE'
    }
    Assert-SafeContent $json
    return $json
}

function Write-JsonResult($Value) {
    $Value | ConvertTo-Json -Depth 10 -Compress
}

function Get-RawHookInput {
    $parts = @($script:PipelineInput | ForEach-Object { [string]$_ })
    if ($parts.Count -gt 0) {
        return ($parts -join [Environment]::NewLine)
    }
    if ([Console]::IsInputRedirected) {
        $raw = [Console]::In.ReadToEnd()
        if (-not [string]::IsNullOrWhiteSpace($raw)) {
            return $raw
        }
    }
    throw 'HOOK_INPUT_REQUIRED'
}

function Read-HookPayload {
    $raw = Get-RawHookInput
    Assert-SafeContent $raw
    try {
        $payload = $raw | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw 'HOOK_INPUT_INVALID_JSON'
    }
    if ($null -eq $payload -or $payload -is [System.Array]) {
        throw 'HOOK_INPUT_INVALID_JSON'
    }
    return $payload
}

function Get-HookSessionId($Payload) {
    $sessionId = Get-RequiredText $Payload 'session_id' 256
    Assert-SessionId $sessionId
    return $sessionId
}

function Assert-HookEvent($Payload, [string]$EventName, [string]$FieldName, [string]$FieldValue) {
    if ((Get-RequiredText $Payload 'hook_event_name' 256) -ne $EventName) {
        throw "INVALID_HOOK_EVENT:$EventName"
    }
    if ((Get-RequiredText $Payload $FieldName 256) -ne $FieldValue) {
        throw "INVALID_HOOK_$($FieldName.ToUpperInvariant()):$FieldValue"
    }
}

function Get-OptionalHookTurnId($Payload) {
    $turnId = Get-OptionalText $Payload 'turn_id' 256
    if ($null -eq $turnId -or [string]::IsNullOrWhiteSpace($turnId)) {
        return $null
    }
    Assert-SessionId $turnId 'turn_id'
    return $turnId
}

function Remove-OwnCheckpoint([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    Remove-Item -LiteralPath $Path -Force
    return $true
}

$root = Get-RepositoryRoot

switch ($Mode) {
    'Path' {
        Assert-SessionId $SessionId
        Get-CheckpointPath $root $SessionId
        break
    }
    'Validate' {
        Assert-SessionId $SessionId
        $path = Get-CheckpointPath $root $SessionId
        try {
            $checkpoint = Read-Checkpoint $path $root $SessionId
            Write-JsonResult ([ordered]@{
                valid = $true
                path = $path
                session_id = $checkpoint.session_id
                bytes = (Get-Item -LiteralPath $path).Length
                has_capture = (Test-Property $checkpoint 'capture' -and $null -ne $checkpoint.capture)
            })
        }
        catch {
            Write-JsonResult ([ordered]@{ valid = $false; path = $path; session_id = $SessionId; reason = $_.Exception.Message })
            exit 1
        }
        break
    }
    'Write' {
        Assert-SessionId $SessionId
        $checkpoint = New-Checkpoint $root $SessionId $DiagnosticFrontier $NextSafeReadOnlyAction
        $path = Get-CheckpointPath $root $SessionId
        Write-CheckpointAtomically $path $root $checkpoint
        Write-JsonResult ([ordered]@{
            written = $true
            path = $path
            bytes = (Get-Item -LiteralPath $path).Length
            session_id = $SessionId
        })
        break
    }
    'Invalidate' {
        Assert-SessionId $SessionId
        if ($BoundaryId) { Assert-InputText $BoundaryId 'boundary_id' 256 $true }
        if ($Reason) { Assert-InputText $Reason 'reason' 1000 $true }
        $path = Get-CheckpointPath $root $SessionId
        $deleted = Remove-OwnCheckpoint $path
        Write-JsonResult ([ordered]@{
            invalidated = $deleted
            deleted = $deleted
            path = $path
            session_id = $SessionId
        })
        break
    }
    'Delete' {
        Assert-SessionId $SessionId
        $path = Get-CheckpointPath $root $SessionId
        $deleted = Remove-OwnCheckpoint $path
        Write-JsonResult ([ordered]@{
            deleted = $deleted
            path = $path
            session_id = $SessionId
        })
        break
    }
    'Refresh' {
        try {
            $hook = Read-HookPayload
            Assert-HookEvent $hook 'PreCompact' 'trigger' 'auto'
            $hookSessionId = Get-HookSessionId $hook
            $hookTurnId = Get-OptionalHookTurnId $hook
            $path = Get-CheckpointPath $root $hookSessionId
            $checkpoint = Read-Checkpoint $path $root $hookSessionId
            $captured = Copy-CheckpointWithCapture $checkpoint $hookSessionId $hookTurnId
            Write-CheckpointAtomically $path $root $captured
            Write-JsonResult ([ordered]@{
                systemMessage = "LONG_SESSION_PRECOMPACT_CHECKPOINT_CAPTURED event=PreCompact trigger=auto session_id=$hookSessionId"
            })
        }
        catch {
            $reason = $_.Exception.Message
            if ($reason -eq 'CHECKPOINT_MISSING') {
                Write-JsonResult ([ordered]@{
                    systemMessage = ''
                })
                break
            }
            Write-JsonResult ([ordered]@{
                systemMessage = "LONG_SESSION_PRECOMPACT_CHECKPOINT_UNAVAILABLE reason=$reason. Automatic compaction remains allowed; reconstruct from canonical/live authority and exact Git facts."
            })
        }
        break
    }
    'Recover' {
        try {
            $hook = Read-HookPayload
            Assert-HookEvent $hook 'SessionStart' 'source' 'compact'
            $hookSessionId = Get-HookSessionId $hook
            $path = Get-CheckpointPath $root $hookSessionId
            $checkpoint = Read-Checkpoint $path $root $hookSessionId
            if (-not (Test-Property $checkpoint 'capture') -or $null -eq $checkpoint.capture) {
                throw 'CHECKPOINT_CAPTURE_MISSING'
            }
            $summary = Get-RecoverySummary $checkpoint
            $deleted = $false
            $cleanup = 'true'
            try {
                $deleted = Remove-OwnCheckpoint $path
            }
            catch {
                $cleanup = "false reason=$($_.Exception.Message)"
            }
            $context = @"
LONG_SESSION_RECOVERY_CHECKPOINT_VALID
RECOVERY_SESSION_ID=$hookSessionId
CAPTURE_EVENT=PreCompact
CAPTURE_TRIGGER=auto
Session-owned optional recovery only. Revalidate mutable authority and Git/runtime facts; do not repeat consumed mutations. Continue from the recorded diagnostic frontier only when permitted.
CHECKPOINT_SUMMARY=$summary
LONG_SESSION_RECOVERY_CHECKPOINT_DELETED=$deleted
LONG_SESSION_RECOVERY_CLEANUP=$cleanup
"@
            Write-JsonResult ([ordered]@{
                hookSpecificOutput = [ordered]@{
                    hookEventName = 'SessionStart'
                    additionalContext = $context.Trim()
                }
            })
        }
        catch {
            $reason = $_.Exception.Message
            if ($reason -eq 'CHECKPOINT_MISSING') {
                Write-JsonResult ([ordered]@{
                    hookSpecificOutput = [ordered]@{
                        hookEventName = 'SessionStart'
                        additionalContext = ''
                    }
                })
                break
            }
            $context = "LONG_SESSION_RECOVERY_CHECKPOINT_UNAVAILABLE reason=$reason. Reconstruct from canonical/live authority and exact Git facts. Missing, malformed, stale, or foreign session state remains nonblocking; do not guess or repeat a consumed mutation."
            Write-JsonResult ([ordered]@{
                hookSpecificOutput = [ordered]@{
                    hookEventName = 'SessionStart'
                    additionalContext = $context
                }
            })
        }
        break
    }
    'Announce' {
        try {
            $hook = Read-HookPayload
            $source = Get-RequiredText $hook 'source' 64
            if ($source -notin @('startup', 'resume', 'clear')) {
                throw "INVALID_HOOK_SOURCE:$source"
            }
            if ((Get-RequiredText $hook 'hook_event_name' 256) -ne 'SessionStart') {
                throw 'INVALID_HOOK_EVENT:SessionStart'
            }
            $hookSessionId = Get-HookSessionId $hook
            $context = @"
LONG_SESSION_ACTIVE_SESSION_ID=$hookSessionId
Session-owned optional recovery is silent when absent. If a recovery note is genuinely useful, use one validated atomic `-Mode Write -SessionId <session-id> -DiagnosticFrontier <frontier>` call; the checkpoint is not task authority or a progress ledger.
For bounded diagnosis, use `.codex/hooks/targeted-diagnostic-read.ps1 -SearchPath <path> -Pattern <pattern>`. A deterministic match returns its bounded slice; an ambiguous result returns compact locations for at most one `-Ids` follow-up.
"@.Trim()
            Write-JsonResult ([ordered]@{
                hookSpecificOutput = [ordered]@{
                    hookEventName = 'SessionStart'
                    additionalContext = $context
                }
            })
        }
        catch {
            $reason = $_.Exception.Message
            Write-JsonResult ([ordered]@{
                hookSpecificOutput = [ordered]@{
                    hookEventName = 'SessionStart'
                    additionalContext = "LONG_SESSION_SESSION_BINDING_UNAVAILABLE reason=$reason"
                }
            })
        }
        break
    }
}
