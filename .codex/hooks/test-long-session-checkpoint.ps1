#requires -Version 7.2
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'long-session-checkpoint.ps1'
$candidateRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$powerShellExecutable = (Get-Command pwsh -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('fixture-checkpoint-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION_FAILED:$Message" }
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function New-HookPayload(
    [string]$EventName,
    [string]$Session,
    [string]$Trigger,
    [string]$Source,
    [string]$TurnId
) {
    $payload = [ordered]@{
        session_id = $Session
        cwd = $repoRoot
        hook_event_name = $EventName
    }
    if ($TurnId) { $payload.turn_id = $TurnId }
    if ($Trigger) { $payload.trigger = $Trigger }
    if ($Source) { $payload.source = $Source }
    return ($payload | ConvertTo-Json -Depth 8 -Compress)
}

function Invoke-ExternalScript([string[]]$ScriptArguments) {
    $raw = & $powerShellExecutable -NoProfile -NonInteractive -File $scriptPath @ScriptArguments 2>&1 | Out-String
    return [pscustomobject]@{
        exit_code = $LASTEXITCODE
        output = $raw
        json = if (-not [string]::IsNullOrWhiteSpace($raw)) { try { $raw.Trim() | ConvertFrom-Json } catch { $null } } else { $null }
    }
}

function Invoke-ExternalHook([string]$Mode, [string]$Payload) {
    $arguments = @(
        '-Mode', $Mode,
        '-CheckpointPath', $checkpointBase,
        '-RepositoryRoot', $repoRoot
    )
    $raw = $Payload | & $powerShellExecutable -NoProfile -NonInteractive -File $scriptPath @arguments 2>&1 | Out-String
    return [pscustomobject]@{
        exit_code = $LASTEXITCODE
        output = $raw
        json = if (-not [string]::IsNullOrWhiteSpace($raw)) { try { $raw.Trim() | ConvertFrom-Json } catch { $null } } else { $null }
    }
}

function Get-SessionPath([string]$OwnerSessionId) {
    return (& $powerShellExecutable -NoProfile -NonInteractive -File $scriptPath -Mode Path -CheckpointPath $checkpointBase -RepositoryRoot $repoRoot -SessionId $OwnerSessionId).Trim()
}

try {
    $repoRoot = Join-Path $testRoot 'synthetic repository'
    git init --quiet --initial-branch=main $repoRoot
    Assert-True ($LASTEXITCODE -eq 0) 'fixture Git initialization failed'
    git -C $repoRoot remote add origin https://github.com/example-org/relay-fixture.git
    Assert-True ($LASTEXITCODE -eq 0) 'fixture origin setup failed'
    git -C $repoRoot -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath= commit --quiet --allow-empty -m fixture
    Assert-True ($LASTEXITCODE -eq 0) 'fixture commit failed'
    $checkpointBase = Join-Path $testRoot 'checkpoint.json'
    $sessionA = 'fixture-session-a'
    $sessionB = 'fixture-session-b'
    $sessionC = 'fixture-session-c'
    $pathA = Get-SessionPath $sessionA
    $pathB = Get-SessionPath $sessionB
    $pathC = Get-SessionPath $sessionC

    Assert-True ($pathA -ne $pathB -and $pathB -ne $pathC) 'session checkpoint paths were not distinct'
    Assert-True ($pathA -notmatch [regex]::Escape($sessionA)) 'raw session id leaked into checkpoint path'

    $writeA = Invoke-ExternalScript @(
        '-Mode', 'Write', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionA, '-DiagnosticFrontier', 'Inspect the session-owned checkpoint.',
        '-NextSafeReadOnlyAction', 'Read the bounded fixture result.'
    )
    Assert-True ($writeA.exit_code -eq 0) "session A direct write failed: $($writeA.output)"
    Assert-True ((Test-Path -LiteralPath $pathA -PathType Leaf) -and -not (Test-Path -LiteralPath $pathB -PathType Leaf)) 'session A write created the wrong ownership surface'
    $storedA = Get-Content -Raw -LiteralPath $pathA | ConvertFrom-Json
    Assert-True ($storedA.schema_version -eq 3 -and $storedA.session_id -eq $sessionA) 'direct writer did not create the compact schema'
    Assert-True (-not ($storedA.PSObject.Properties.Name -contains 'status') -and -not ($storedA.PSObject.Properties.Name -contains 'authority')) 'compact checkpoint retained semantic ledger fields'
    Assert-True ($storedA.repository -eq 'example-org/relay-fixture' -and $storedA.head -match '^[0-9a-f]{40}$') 'trusted identity fields were not derived'

    $validBytes = [IO.File]::ReadAllText($pathA)
    foreach ($badFrontier in @('"token": "synthetic-only"', ('x' * 2001))) {
        $rejected = Invoke-ExternalScript @(
            '-Mode', 'Write', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
            '-SessionId', $sessionA, '-DiagnosticFrontier', $badFrontier
        )
        Assert-True ($rejected.exit_code -ne 0) 'invalid frontier was accepted'
        Assert-True ([IO.File]::ReadAllText($pathA) -ceq $validBytes) 'rejected write changed the valid checkpoint'
    }
    Assert-True ((Get-Item -LiteralPath $pathA).Length -le 8192) 'checkpoint exceeded byte limit'

    $writeB = Invoke-ExternalScript @(
        '-Mode', 'Write', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionB, '-DiagnosticFrontier', 'Keep session B isolated.'
    )
    Assert-True ($writeB.exit_code -eq 0) "session B direct write failed: $($writeB.output)"
    $beforeB = Get-Content -Raw -LiteralPath $pathB

    $refreshA = Invoke-ExternalHook 'Refresh' (New-HookPayload 'PreCompact' $sessionA 'auto' $null 'turn-a')
    Assert-True ($refreshA.json.systemMessage -match 'CHECKPOINT_CAPTURED') "session A capture failed: $($refreshA.output)"
    $beforeAWithCapture = Get-Content -Raw -LiteralPath $pathA
    $foreignRecovery = Invoke-ExternalHook 'Recover' (New-HookPayload 'SessionStart' $sessionB $null 'compact' 'turn-b')
    Assert-True ($foreignRecovery.json.hookSpecificOutput.additionalContext -match 'CHECKPOINT_CAPTURE_MISSING') 'session B observed session A capture'
    Assert-True ((Get-Content -Raw -LiteralPath $pathA) -eq $beforeAWithCapture) 'foreign recovery changed session A state'
    Assert-True ((Get-Content -Raw -LiteralPath $pathB) -eq $beforeB) 'foreign recovery changed session B state'

    $recoverA = Invoke-ExternalHook 'Recover' (New-HookPayload 'SessionStart' $sessionA $null 'compact' 'turn-a')
    $recoverContext = $recoverA.json.hookSpecificOutput.additionalContext
    Assert-True ($recoverContext -match 'LONG_SESSION_RECOVERY_CHECKPOINT_VALID') 'same-session recovery failed'
    Assert-True ($recoverContext -match 'Inspect the session-owned checkpoint') 'recovery omitted the irreconstructible frontier'
    Assert-True ($recoverContext -notmatch '"status"|"authority"|"objective"|"consumed_mutations"') 'recovery projection exposed the semantic ledger'
    Assert-True (-not (Test-Path -LiteralPath $pathA -PathType Leaf)) 'same-session recovery did not delete its own consumed checkpoint'
    Assert-True ((Get-Content -Raw -LiteralPath $pathB) -eq $beforeB) 'same-session recovery changed a foreign checkpoint'
    Assert-True ([Text.Encoding]::UTF8.GetByteCount($recoverContext) -lt 5000) 'recovery context exceeded registered limit'
    $replay = Invoke-ExternalHook 'Recover' (New-HookPayload 'SessionStart' $sessionA $null 'compact' 'turn-a')
    Assert-True ($replay.json.hookSpecificOutput.additionalContext -eq '') 'consumed checkpoint was replayed'

    $invalidStatus = '{"schema_version":3,"session_id":"fixture-session-b","status":"invalid"}'
    Write-Utf8NoBom $pathB $invalidStatus
    $invalidValidation = Invoke-ExternalScript @(
        '-Mode', 'Validate', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionB
    )
    Assert-True ($invalidValidation.exit_code -ne 0 -and $invalidValidation.output -match 'INVALID_FIELD:status') 'invalid status was accepted by checkpoint validation'
    $invalidArgument = Invoke-ExternalScript @(
        '-Mode', 'Write', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionB, '-DiagnosticFrontier', 'Write only the supported frontier.',
        '-Status', 'invalid'
    )
    Assert-True ($invalidArgument.exit_code -ne 0 -and $invalidArgument.output -match 'parameter') 'writer exposed an unvalidated status input'
    $repairB = Invoke-ExternalScript @(
        '-Mode', 'Write', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionB, '-DiagnosticFrontier', 'Replace the corrupted optional note.'
    )
    Assert-True ($repairB.exit_code -eq 0) "direct writer could not replace corrupted own state: $($repairB.output)"
    $repairedB = Get-Content -Raw -LiteralPath $pathB | ConvertFrom-Json
    Assert-True (-not ($repairedB.PSObject.Properties.Name -contains 'status')) 'repair writer created an invalid status field'
    Assert-True (@(Get-ChildItem -LiteralPath $testRoot -Filter '.checkpoint-*.tmp' -Force).Count -eq 0) 'validated write left a temporary file'

    $invalidate = Invoke-ExternalScript @(
        '-Mode', 'Invalidate', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionB, '-BoundaryId', 'fixture-optional-boundary-1',
        '-Reason', 'A concrete stale-frontier fixture boundary.'
    )
    Assert-True ($invalidate.exit_code -eq 0 -and $invalidate.output -match '"invalidated":true') 'optional invalidation failed'
    Assert-True (-not (Test-Path -LiteralPath $pathB -PathType Leaf)) 'invalidation did not remove only the active session file'

    $writeAAgain = Invoke-ExternalScript @(
        '-Mode', 'Write', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionA, '-DiagnosticFrontier', 'Check own delete isolation.'
    )
    $writeBAgain = Invoke-ExternalScript @(
        '-Mode', 'Write', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionB, '-DiagnosticFrontier', 'Keep the foreign file.'
    )
    Assert-True ($writeAAgain.exit_code -eq 0 -and $writeBAgain.exit_code -eq 0) 'isolation fixture setup failed'
    $deleteB = Invoke-ExternalScript @(
        '-Mode', 'Delete', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionB
    )
    Assert-True ($deleteB.exit_code -eq 0 -and $deleteB.output -match '"deleted":true') 'session B delete failed'
    Assert-True ((Test-Path -LiteralPath $pathA -PathType Leaf) -and -not (Test-Path -LiteralPath $pathB -PathType Leaf)) 'session B delete touched the wrong checkpoint'

    $corruptA = Get-Content -Raw -LiteralPath $pathA
    Write-Utf8NoBom $pathA '{broken'
    $corruptRecovery = Invoke-ExternalHook 'Recover' (New-HookPayload 'SessionStart' $sessionA $null 'compact' 'turn-a')
    Assert-True ($corruptRecovery.json.hookSpecificOutput.additionalContext -match 'CHECKPOINT_INVALID_JSON') 'corrupt recovery did not fail safely'
    Write-Utf8NoBom $pathA $corruptA

    $stale = $corruptA | ConvertFrom-Json
    $stale.written_at = [DateTimeOffset]::UtcNow.AddHours(-25).ToString('o')
    Write-Utf8NoBom $pathA ($stale | ConvertTo-Json -Depth 8)
    $staleRecovery = Invoke-ExternalHook 'Recover' (New-HookPayload 'SessionStart' $sessionA $null 'compact' 'turn-a')
    Assert-True ($staleRecovery.json.hookSpecificOutput.additionalContext -match 'CHECKPOINT_STALE_TIME') 'stale note was accepted'
    Write-Utf8NoBom $pathA $corruptA

    $missingCapture = Invoke-ExternalHook 'Refresh' (New-HookPayload 'PreCompact' $sessionC 'auto' $null 'turn-c')
    Assert-True ($missingCapture.json.systemMessage -eq '') 'missing checkpoint capture was not quiet'

    $announce = Invoke-ExternalHook 'Announce' (New-HookPayload 'SessionStart' $sessionC $null 'startup' 'turn-start')
    $announceContext = $announce.json.hookSpecificOutput.additionalContext
    Assert-True ($announceContext -match 'LONG_SESSION_ACTIVE_SESSION_ID=fixture-session-c') 'active session id was not announced'
    Assert-True ($announceContext -match 'validated atomic') 'announce omits the simple checkpoint write path'
    Assert-True ($announceContext -match 'targeted-diagnostic-read\.ps1') 'announce omits the one-shot diagnostic path'
    Assert-True ($announceContext -notmatch 'Invalidate.*Write replacement') 'announce requires invalidation choreography'
    Assert-True ($announceContext -notmatch 'Discover.*Select.*Slice') 'announce requires the three-phase diagnostic protocol'
    Assert-True ($announceContext -notmatch 'draft\.json|"status"|"authority"|"objective"') 'announce exposes the retired checkpoint ledger'

    $deleteC = Invoke-ExternalScript @(
        '-Mode', 'Delete', '-CheckpointPath', $checkpointBase, '-RepositoryRoot', $repoRoot,
        '-SessionId', $sessionC
    )
    Assert-True ($deleteC.exit_code -eq 0 -and $deleteC.output -match '"deleted":false') 'missing session delete did not remain nonblocking'
    Assert-True (Test-Path -LiteralPath $pathA -PathType Leaf) 'foreign delete removed session A state'

    $hooksConfig = Get-Content -Raw -LiteralPath (Join-Path $candidateRoot '.codex/hooks.json') | ConvertFrom-Json
    Assert-True ($hooksConfig.hooks.PreCompact[0].matcher -eq '^auto$') 'PreCompact matcher is not auto-only'
    Assert-True ($hooksConfig.hooks.PreCompact[0].hooks[0].command -match '-Mode Refresh') 'PreCompact command does not use capture mode'
    Assert-True ($hooksConfig.hooks.SessionStart[0].matcher -eq '^(startup|resume|clear)$') 'SessionStart startup matcher is missing'
    Assert-True ($hooksConfig.hooks.SessionStart[0].hooks[0].command -match '-Mode Announce') 'SessionStart startup command does not announce the session'
    Assert-True ($hooksConfig.hooks.SessionStart[1].matcher -eq '^compact$') 'SessionStart compact matcher is missing'
    Assert-True ($hooksConfig.hooks.SessionStart[1].hooks[0].command -match '-Mode Recover') 'SessionStart compact command does not use recovery mode'

    Write-Output 'PASS: compact session-owned checkpoint, direct validated atomic write, foreign-session isolation, safe corruption recovery, own-file invalidation/delete, and quiet session announcement'
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
        $expectedTestRoot = Join-Path ([IO.Path]::GetTempPath()) (Split-Path -Leaf $testRoot)
        if ($resolvedTestRoot -ne [IO.Path]::GetFullPath($expectedTestRoot) -or
            (Split-Path -Leaf $testRoot) -notmatch '^fixture-checkpoint-test-[a-f0-9]{32}$') { throw 'UNSAFE_FIXTURE_CLEANUP' }
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
