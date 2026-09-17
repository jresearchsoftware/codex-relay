#requires -Version 7.2
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-JsonResult($Value) {
    $json = $Value | ConvertTo-Json -Depth 8 -Compress
    [Console]::Out.WriteLine($json)
}

function Test-TechnicalBlockerResolutionContract([string]$Message) {
    $marker = 'Technical Blocker Resolution Contract'
    $markerIndex = $Message.IndexOf($marker, [StringComparison]::OrdinalIgnoreCase)
    if ($markerIndex -lt 0) {
        return $false
    }

    # Keep this a bounded shape check. docs/execution-policy.md owns the meaning of
    # each value; the hook only requires a compact named block with content.
    $remainingLength = [Math]::Min(4096, $Message.Length - $markerIndex)
    $contract = $Message.Substring($markerIndex, $remainingLength)
    $requiredFields = @(
        'root_cause_status',
        'reproduction_status',
        'diagnosability_status',
        'source_delta_status',
        'cleanup_boundary_status'
    )
    foreach ($field in $requiredFields) {
        if ($contract -notmatch "(?im)^\s*(?:[-*]\s*)?$([regex]::Escape($field))\s*:\s*\S") {
            return $false
        }
    }
    return $true
}

function Test-TechnicalNoDeltaScope([string]$Message) {
    # Only explicit bounded markers establish the canonical contract scope.
    # An absent or ambiguous classification must not make this guard impose a
    # wider policy than docs/execution-policy.md.
    $technical = $Message -match '(?im)^\s*(?:[-*]\s*)?(?:blocker[_ -]?type|blocker[_ -]?class|failure[_ -]?class)\s*:\s*technical\s*$'
    $noDelta = $Message -match '(?im)^\s*(?:[-*]\s*)?source[_ -]?delta[_ -]?status\s*:\s*none_justified\s*$'
    $protectedBoundary = $Message -match '(?im)^\s*(?:[-*]\s*)?(?:blocker[_ -]?type|blocker[_ -]?class|boundary[_ -]?type)\s*:\s*protected(?:[_ -]?boundary)?\s*$'
    return ($technical -and $noDelta -and -not $protectedBoundary)
}

function Test-DecisionGradeBlocked([string]$Message) {
    if ($Message -match '(?i)(?:TASK|CR)_[A-Z0-9_]+_BLOCKED_STARTING_STATE_MISMATCH') {
        return $true
    }

    $hasTerminalBlocked = $Message -match '(?i)(?:TASK|CR)_[A-Z0-9_]+_BLOCKED\b|(?:^|\s)(?:status|outcome|result)\s*[:=]\s*BLOCKED\b|^\s*BLOCKED\b'
    if (-not $hasTerminalBlocked) {
        return $true
    }

    $hasEstablishedFacts = $Message -match '(?i)established[_ ]facts|facts established|установленн\w+\s+факт'
    $hasEliminatedHypotheses = $Message -match '(?i)eliminated(?: material)?[_ ]hypotheses|hypotheses eliminated|исключенн\w+\s+гипотез'
    $hasDiagnosticFrontier = $Message -match '(?i)diagnostic[_ ]frontier|frontier of diagnosis|диагностическ\w+\s+фронтир'
    $hasRemainingSafeAction = $Message -match '(?i)remaining.*(?:safe|permitted).*read[- ]only|safe read[- ]only (?:action|actions)|остаю\w*.*безопасн\w+.*чтен'
    $hasExactBoundary = $Message -match '(?i)no material permitted read[- ]only action remains|exact .*\b(?:evidence|authority|capability|security|credential)\b.*boundary|exact .*boundary|точн\w+.*границ\w+'
    $hasNextAction = $Message -match '(?i)next action|exact human decision|required authority|следующ\w+\s+действ\w+'
    $hasTechnicalBlockerResolutionContract = -not (Test-TechnicalNoDeltaScope $Message) -or (Test-TechnicalBlockerResolutionContract $Message)

    return ($hasEstablishedFacts -and $hasEliminatedHypotheses -and $hasDiagnosticFrontier -and $hasRemainingSafeAction -and $hasExactBoundary -and $hasNextAction -and $hasTechnicalBlockerResolutionContract)
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) {
        exit 0
    }

    try {
        $payload = $raw | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        exit 0
    }

    if ($payload.hook_event_name -ne 'Stop') { exit 0 }
    $message = [string]$payload.last_assistant_message
    if ([string]::IsNullOrWhiteSpace($message)) {
        exit 0
    }

    $stopAlreadyActive = $false
    if ($null -ne $payload.stop_hook_active) {
        $stopAlreadyActive = [bool]$payload.stop_hook_active
    }
    if ($stopAlreadyActive) {
        exit 0
    }

    if (Test-DecisionGradeBlocked $message) {
        exit 0
    }

    Write-JsonResult ([ordered]@{
            decision = 'block'
            reason = 'Decision-boundary guard: the terminal BLOCKED message lacks the diagnostic frontier or the conditional Technical Blocker Resolution Contract in docs/execution-policy.md. Continue once for a bounded diagnostic pass using permitted read-only evidence. This reminder grants no mutation, retry or protected authority; the live task and development contract retain those boundaries.'
        })
    exit 0
}
catch {
    # A malformed or unavailable stop payload must never create an automatic continuation.
    exit 0
}
