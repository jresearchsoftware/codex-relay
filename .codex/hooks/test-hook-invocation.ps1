#requires -Version 7.2
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$candidateRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$config = Get-Content -Raw -LiteralPath (Join-Path $candidateRoot '.codex/hooks.json') | ConvertFrom-Json
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('fixture-hook-launch-' + [guid]::NewGuid().ToString('N'))
$fixtureRepo = Join-Path $testRoot "repository with spaces and 'quote"
$nestedCwd = Join-Path $fixtureRepo 'nested directory'
$pwshPath = (Get-Command pwsh -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION_FAILED:$Message" }
}

function Invoke-RegisteredCommand($Handler, $Payload) {
    Assert-True ($Handler.type -eq 'command' -and $Handler.command.StartsWith('pwsh ')) 'registration does not use PowerShell Core'
    Assert-True ($Handler.command -notmatch 'powershell\.exe|wsl\.exe|ExecutionPolicy') 'platform-specific launcher remained'
    $start = [Diagnostics.ProcessStartInfo]::new()
    # Exercise the registered string through the platform shell, not a rewritten
    # -File approximation. This simulates command dispatch, not a Codex lifecycle.
    if ($IsWindows) {
        $start.FileName = 'cmd.exe'
        $start.Arguments = '/d /s /c ' + $Handler.command
    }
    else {
        $start.FileName = '/bin/sh'
        $start.ArgumentList.Add('-c')
        $start.ArgumentList.Add($Handler.command)
    }
    $start.WorkingDirectory = $nestedCwd
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        Assert-True ($process.Start()) 'registered command did not start'
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.WriteLine(($Payload | ConvertTo-Json -Compress))
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(10000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw 'HOOK_COMMAND_TIMEOUT'
        }
        $output = $stdout.GetAwaiter().GetResult()
        $errorText = $stderr.GetAwaiter().GetResult()
        Assert-True ($process.ExitCode -eq 0 -and [string]::IsNullOrWhiteSpace($errorText)) "registered command failed: $errorText"
        Assert-True ([Text.Encoding]::UTF8.GetByteCount($output) -le 8192) 'registered command exceeded output bound'
        if (-not [string]::IsNullOrWhiteSpace($output)) { return ($output | ConvertFrom-Json) }
        return $null
    }
    finally { $process.Dispose() }
}

try {
    New-Item -ItemType Directory -Path $nestedCwd -Force | Out-Null
    $fixtureHooks = Join-Path $fixtureRepo '.codex/hooks'
    New-Item -ItemType Directory -Path $fixtureHooks -Force | Out-Null
    foreach ($name in @('long-session-checkpoint.ps1', 'decision-boundary-stop.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $fixtureHooks $name)
    }
    Copy-Item -LiteralPath (Join-Path $candidateRoot '.gitignore') -Destination (Join-Path $fixtureRepo '.gitignore')
    git init --quiet --initial-branch=main $fixtureRepo
    Assert-True ($LASTEXITCODE -eq 0) 'fixture initialization failed'
    git -C $fixtureRepo remote add origin https://github.com/example-org/relay-fixture.git
    Assert-True ($LASTEXITCODE -eq 0) 'fixture origin setup failed'
    git -C $fixtureRepo -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath= commit --quiet --allow-empty -m fixture
    Assert-True ($LASTEXITCODE -eq 0) 'fixture commit failed'
    git -C $fixtureRepo check-ignore --quiet .codex/local/checkpoint-probe
    Assert-True ($LASTEXITCODE -eq 0) 'local recovery state is not ignored'

    $sessionA = 'fixture-launch-a'
    $sessionB = 'fixture-launch-b'
    $payload = @{session_id=$sessionA; cwd=$nestedCwd; hook_event_name='SessionStart'; source='startup'}
    foreach ($source in @('startup', 'resume', 'clear')) {
        $payload.source = $source
        $announced = Invoke-RegisteredCommand $config.hooks.SessionStart[0].hooks[0] $payload
        Assert-True ($announced.hookSpecificOutput.additionalContext -match "LONG_SESSION_ACTIVE_SESSION_ID=$sessionA") 'session binding failed'
    }
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $fixtureRepo '.codex/local'))) 'announcement created unnecessary recovery state'

    $helper = Join-Path $fixtureHooks 'long-session-checkpoint.ps1'
    $write = & $pwshPath -NoProfile -NonInteractive -File $helper -Mode Write -RepositoryRoot $fixtureRepo -SessionId $sessionA -DiagnosticFrontier 'Portable launch fixture frontier.' | ConvertFrom-Json
    Assert-True ($LASTEXITCODE -eq 0 -and $write.written) 'fixture checkpoint write failed'
    $payload = @{session_id=$sessionA; cwd=$nestedCwd; hook_event_name='PreCompact'; trigger='auto'}
    $captured = Invoke-RegisteredCommand $config.hooks.PreCompact[0].hooks[0] $payload
    Assert-True ($captured.systemMessage -match 'CHECKPOINT_CAPTURED') 'registered capture failed'
    $capturedBytes = [IO.File]::ReadAllText($write.path)

    $payload = @{session_id=$sessionB; cwd=$nestedCwd; hook_event_name='SessionStart'; source='compact'}
    $foreign = Invoke-RegisteredCommand $config.hooks.SessionStart[1].hooks[0] $payload
    Assert-True ($foreign.hookSpecificOutput.additionalContext -eq '') 'foreign session observed recovery context'
    Assert-True ([IO.File]::ReadAllText($write.path) -ceq $capturedBytes) 'foreign invocation changed the checkpoint'
    $payload.session_id = $sessionA
    $recovered = Invoke-RegisteredCommand $config.hooks.SessionStart[1].hooks[0] $payload
    Assert-True ($recovered.hookSpecificOutput.additionalContext -match 'Portable launch fixture frontier') 'registered recovery lost the frontier'
    Assert-True (-not (Test-Path -LiteralPath $write.path)) 'registered recovery did not consume its own note'

    $payload = @{session_id=$sessionA; cwd=$nestedCwd; hook_event_name='Stop'; stop_hook_active=$false; last_assistant_message='CR_12_001_BLOCKED: missing diagnostic frontier.'}
    $reminder = Invoke-RegisteredCommand $config.hooks.Stop[0].hooks[0] $payload
    Assert-True ($reminder.decision -eq 'block') 'registered Stop did not issue a diagnostic reminder'
    $payload.stop_hook_active = $true
    Assert-True ($null -eq (Invoke-RegisteredCommand $config.hooks.Stop[0].hooks[0] $payload)) 'registered Stop repeated continuation'

    Write-Output ("PASS: registered pwsh commands, stdin, nested/spaced/quoted checkout, ignored state, session isolation, capture/recovery and bounded Stop; OS={0}; pwsh={1}; nativeLifecycle=NOT_TESTED" -f [Runtime.InteropServices.RuntimeInformation]::OSDescription, $PSVersionTable.PSVersion)
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
        $expectedTestRoot = Join-Path ([IO.Path]::GetTempPath()) (Split-Path -Leaf $testRoot)
        if ($resolvedTestRoot -ne [IO.Path]::GetFullPath($expectedTestRoot) -or
            (Split-Path -Leaf $testRoot) -notmatch '^fixture-hook-launch-[a-f0-9]{32}$') { throw 'UNSAFE_FIXTURE_CLEANUP' }
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
