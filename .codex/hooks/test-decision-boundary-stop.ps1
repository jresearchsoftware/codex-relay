#requires -Version 7.2
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'decision-boundary-stop.ps1'
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$powerShellExecutable = (Get-Command pwsh -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        throw "ASSERTION_FAILED:$Message"
    }
}

function Invoke-Guard($Payload) {
    $raw = ($Payload | ConvertTo-Json -Depth 8 -Compress) | & $powerShellExecutable -NoProfile -NonInteractive -File $scriptPath | Out-String
    Assert-True ($LASTEXITCODE -eq 0) 'Stop helper failed'
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return $raw | ConvertFrom-Json
}

$hooksConfig = Get-Content -Raw (Join-Path $repositoryRoot '.codex/hooks.json') | ConvertFrom-Json
$stopHooks = @($hooksConfig.hooks.Stop)
Assert-True ($stopHooks.Count -eq 1) 'hooks.json does not contain exactly one Stop matcher group'
$stopCommands = @($stopHooks | ForEach-Object { $_.hooks } | ForEach-Object { $_.command })
$stopCommandMatches = @($stopCommands | Where-Object { $_ -match 'decision-boundary-stop\.ps1' })
Assert-True ($stopCommandMatches.Count -gt 0) 'Stop hook is not wired to the decision-boundary guard'

$activationReadme = Get-Content -Raw (Join-Path $repositoryRoot '.codex/hooks/README.md')
Assert-True ($activationReadme -match 'fresh\s+Codex App session') 'fresh App activation prerequisite is undocumented'
Assert-True ($activationReadme -match 'native\s+evidence\s+of\s+the\s+`Stop`\s+hook') 'native Stop evidence requirement is undocumented'
$projectRules = Get-Content -Raw (Join-Path $repositoryRoot 'docs/execution-policy.md')
Assert-True ($projectRules -match 'technical\s+`?BLOCKED`?\s+handoff\s+with\s+no\s+source\s+delta') 'canonical blocker-resolution obligation is undocumented'
Assert-True ($projectRules -match 'unresolved observability gap') 'canonical observability-defect invariant is undocumented'
Assert-True ($projectRules -match 'no source delta') 'canonical no-source-delta evidence invariant is undocumented'
Assert-True ($projectRules -match 'Technical\s+Blocker\s+Resolution\s+Contract') 'canonical technical blocker contract is undocumented'
foreach ($field in @('root_cause_status', 'reproduction_status', 'diagnosability_status', 'source_delta_status', 'cleanup_boundary_status')) {
    Assert-True ($projectRules -match [regex]::Escape($field)) "canonical technical blocker contract field is undocumented:$field"
}
$stopImplementation = Get-Content -Raw $scriptPath
Assert-True ($stopImplementation -notmatch 'technical blocker creates|observability failure') 'Stop hook duplicates canonical blocker-resolution policy'
Assert-True ($stopImplementation -match 'Technical Blocker Resolution Contract') 'Stop hook does not check the named technical blocker contract'

$normal = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = 'Implementation complete; focused checks PASS.'
    })
Assert-True ($null -eq $normal) 'normal completion was unexpectedly continued'

$premature = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = @'
Outcome: TASK_FIXTURE_BLOCKED
blocker_type: technical
source_delta_status: none_justified
The harmless mutation allowance is exhausted, so I will stop without checking the local failure.
'@
    })
Assert-True ($premature.decision -eq 'block') 'premature blocked outcome was not continued'
Assert-True ($premature.reason -match 'docs/execution-policy\.md') 'continuation reason omitted the developer contract'
Assert-True ($premature.reason -match 'bounded diagnostic') 'continuation reason omitted bounded diagnostic pass'
Assert-True ($premature.reason -match 'Technical Blocker Resolution Contract') 'continuation reason omitted the named blocker contract'
Assert-True ($premature.reason -notmatch 'Mutation authority exhaustion') 'Stop hook still duplicates blocker-resolution policy'

$boundedSecondPass = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $true
        last_assistant_message = 'Outcome: TASK_FIXTURE_BLOCKED; the first bounded continuation did not change the result.'
    })
Assert-True ($null -eq $boundedSecondPass) 'Stop continuation was not bounded by stop_hook_active'

$decisionGradeWithoutContract = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = @'
Outcome: TASK_FIXTURE_BLOCKED
blocker_type: technical
source_delta_status: none_justified
Established facts: the permitted read-only checks are complete and the runtime returned no further evidence.
Eliminated material hypotheses: the local source and available diagnostic path are not the failing boundary.
Diagnostic frontier: no material permitted read-only action remains.
Remaining permitted read-only actions: none.
Exact evidence/authority boundary: the only remaining evidence is behind an unavailable owner-controlled capability.
Next action: the owner must provide that exact authority before any protected operation.
No protected boundary remains in this prose note; the structured technical scope still applies.
'@
    })
Assert-True ($decisionGradeWithoutContract.decision -eq 'block') 'decision-grade shape without blocker contract was not continued'

$unclassifiedDecisionGrade = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = @'
Outcome: TASK_FIXTURE_BLOCKED
This is not a technical blocker and has no-source-delta in free prose only.
Established facts: the permitted read-only checks are complete and the runtime returned no further evidence.
Eliminated material hypotheses: the local source and available diagnostic path are not the failing boundary.
Diagnostic frontier: no material permitted read-only action remains.
Remaining permitted read-only actions: none.
Exact evidence/authority boundary: the only remaining evidence is behind an unavailable owner-controlled capability.
Next action: the owner must provide that exact authority before any protected operation.
'@
    })
Assert-True ($null -eq $unclassifiedDecisionGrade) 'ambiguous blocker scope was incorrectly forced to provide the technical no-delta contract'

$incompleteContract = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = @'
Outcome: TASK_FIXTURE_BLOCKED
blocker_type: technical
source_delta_status: none_justified
Established facts: the permitted read-only checks are complete and the runtime returned no further evidence.
Eliminated material hypotheses: the local source and available diagnostic path are not the failing boundary.
Diagnostic frontier: no material permitted read-only action remains.
Remaining permitted read-only actions: none.
Exact evidence/authority boundary: the only remaining evidence is behind an unavailable owner-controlled capability.
Next action: the owner must provide that exact authority before any protected operation.
Technical Blocker Resolution Contract:
- root_cause_status: historical cause remains unidentified from retained evidence.
- reproduction_status: closest safe reproduction is complete.
- diagnosability_status: future occurrences will retain private evidence.
- source_delta_status: source correction is committed and pushed.
'@
    })
Assert-True ($incompleteContract.decision -eq 'block') 'incomplete blocker contract was incorrectly accepted'

$decisionGrade = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = @'
Outcome: TASK_FIXTURE_BLOCKED
blocker_type: technical
source_delta_status: none_justified
Established facts: the permitted read-only checks are complete and the runtime returned no further evidence.
Eliminated material hypotheses: the local source and available diagnostic path are not the failing boundary.
Diagnostic frontier: no material permitted read-only action remains.
Remaining permitted read-only actions: none.
Exact evidence/authority boundary: the only remaining evidence is behind an unavailable owner-controlled capability.
Next action: the owner must provide that exact authority before any protected operation.
Technical Blocker Resolution Contract:
- root_cause_status: historical cause remains unidentified from retained evidence.
- reproduction_status: closest safe reproduction is complete.
- diagnosability_status: future occurrences will retain private evidence.
- source_delta_status: source correction is committed and pushed.
- cleanup_boundary_status: protected owner deployment and claim cleanup remain outstanding.
'@
    })
Assert-True ($null -eq $decisionGrade) 'decision-grade blocked outcome with the complete contract was incorrectly continued'

$sourceDeltaDecision = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = @'
Outcome: TASK_FIXTURE_BLOCKED
blocker_type: source-delta
source_delta_status: made
Established facts: the permitted read-only checks are complete and the runtime returned no further evidence.
Eliminated material hypotheses: the local source and available diagnostic path are not the failing boundary.
Diagnostic frontier: no material permitted read-only action remains.
Remaining permitted read-only actions: none.
Exact evidence/authority boundary: the source correction is committed and pushed; no protected evidence is required.
Next action: the owner must review the corrected source before any protected operation.
'@
    })
Assert-True ($null -eq $sourceDeltaDecision) 'source-delta decision-grade outcome was incorrectly forced to provide the no-delta contract'

$protectedBoundaryDecision = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = @'
Outcome: TASK_FIXTURE_BLOCKED
blocker_type: protected-boundary
source_delta_status: none_justified
Established facts: the permitted read-only checks are complete and the runtime returned no further evidence.
Eliminated material hypotheses: the local source and available diagnostic path are not the failing boundary.
Diagnostic frontier: no material permitted read-only action remains.
Remaining permitted read-only actions: none.
Exact evidence/authority boundary: the remaining owner-controlled authority is a protected boundary.
Next action: the owner must provide that exact authority before any protected operation.
'@
    })
Assert-True ($null -eq $protectedBoundaryDecision) 'protected-boundary decision-grade outcome was incorrectly forced to provide the no-delta contract'

$startingMismatch = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = 'TASK_FIXTURE_BLOCKED_STARTING_STATE_MISMATCH: origin/main cannot prove the admitted anchor.'
    })
Assert-True ($null -eq $startingMismatch) 'starting-state mismatch was incorrectly continued'

$crBlocked = Invoke-Guard ([ordered]@{
        hook_event_name = 'Stop'
        stop_hook_active = $false
        last_assistant_message = 'CR_12_001_BLOCKED: stopped without a diagnostic frontier.'
    })
Assert-True ($crBlocked.decision -eq 'block') 'CR terminal token bypassed the diagnostic reminder'

$wrongEvent = Invoke-Guard ([ordered]@{
        hook_event_name = 'SessionStart'
        stop_hook_active = $false
        last_assistant_message = 'TASK_FIXTURE_BLOCKED'
    })
Assert-True ($null -eq $wrongEvent) 'another lifecycle event triggered a Stop continuation'

$invalidPayload = 'not-json' | & $powerShellExecutable -NoProfile -NonInteractive -File $scriptPath | Out-String
Assert-True ([string]::IsNullOrWhiteSpace($invalidPayload)) 'invalid hook payload produced unsafe continuation output'

Write-Output 'PASS: bounded Stop decision guard, technical blocker contract, cheap-first continuation, decision-grade pass-through, starting-state exception, and fail-safe payload handling'
