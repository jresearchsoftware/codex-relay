# Human command interaction examples

These examples illustrate [HC-001–HC-003](../protocols/human-command-interaction.md#HC-001)
only where that topic is explicitly adopted. Adapt the action to the actual
question, shell, output sensitivity and authority. The read-only examples need
no administrator rights, network access, saved report or separate operator tool.
They collect several independent facts in one action. A single command suffices
when it answers the question; a longer safe script is also one action.

## Bash: one pasted block, one transcript

An assistant diagnosing the current environment can say:

“Paste this entire block once into Bash as your ordinary user. Return the single
report from `BEGIN environment report` through `END environment report`, including
any errors. It reads the OS name, numeric user ID and disk space for the current
directory.”

```bash
bash <<'BASH' 2>&1
printf '%s\n' 'BEGIN environment report'
overall=0
check() {
    local name=$1 status
    shift
    printf '\n[%s]\n' "$name"
    if "$@"; then status=0; else status=$?; fi
    printf 'STATUS=%s\n' "$status"
    if [ "$status" -ne 0 ]; then overall=1; fi
}
check 'OS' uname -s
check 'User ID' id -u
check 'Current filesystem (KiB)' df -Pk .
printf '\nOVERALL=%s (0=all checks passed; 1=one or more failed)\n' "$overall"
printf '%s\n' 'END environment report'
exit "$overall"
BASH
```

The quoted here-document is one invocation. The child Bash contains the helper
and exits without closing the operator's interactive shell. Standard error and
standard output share the delimited transcript. Each check records its status
immediately; a failed `df` still permits the other independent results and makes
the overall child exit status 1. A missing command retains its diagnostic and
status 127. The final successful `printf` cannot erase a failure. These synchronous
commands have small output; this pattern is not a blanket transcript of secrets,
background jobs, binary output or unbounded logs.

## PowerShell: one formatted report

An assistant can instead say:

“Paste this entire `& { ... }` block once into PowerShell. Return the single report
between the BEGIN and END lines, including errors and OVERALL. It reads the time,
current location and filesystem drive space.”

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $report = New-Object 'System.Collections.Generic.List[string]'
    $state = @{ Failed = $false }
    function Add-Check([string] $Name, [scriptblock] $Probe) {
        $report.Add("`n[$Name]")
        $value = New-Object 'System.Collections.Generic.List[object]'
        try {
            try {
                & $Probe | ForEach-Object { $value.Add($_) }
            } finally {
                $report.Add(($value | Out-String -Width 160).TrimEnd())
            }
            $report.Add('STATUS=0')
        } catch {
            $report.Add(('ERROR: ' + $_.ToString()))
            $report.Add('STATUS=1')
            $state.Failed = $true
        }
    }
    $report.Add('BEGIN environment report')
    Add-Check 'Time' { Get-Date -Format o }
    Add-Check 'Location' { Get-Location | Select-Object -ExpandProperty Path }
    Add-Check 'Filesystem drives (bytes)' {
        Get-PSDrive -PSProvider FileSystem |
            Select-Object Name, Used, Free | Format-Table -AutoSize
    }
    $result = if ($state.Failed) { 1 } else { 0 }
    $report.Add("`nOVERALL=$result (0=all checks passed; 1=one or more failed)")
    $report.Add('END environment report')
    $report -join [Environment]::NewLine
}
```

The enclosing scope contains preference/helper changes; it emits one string
after formatting each section, avoiding mixed object-table formatting at the
interactive prompt. Nonterminating cmdlet errors become catchable failures here;
their message remains in the report and independent checks continue. OVERALL is
an explicit result, not the interactive shell's process exit code. A saved script
used by automation can additionally exit with that result in its own process.
Do not add `exit` to the pasted interactive block just to report status.
The per-check collection also retains output produced before a later failure;
the `finally` block formats that partial result before the error is recorded.

This example uses cmdlets. When adapting it to a native executable, capture
`$LASTEXITCODE` immediately after that invocation, before another native command,
and explicitly propagate a nonzero value into the report's failure result. A
native nonzero exit need not throw under `$ErrorActionPreference = 'Stop'`.
Preserve relevant standard error as well as success output, accounting for the
actual PowerShell version's stream behavior. Do not simply suppress errors or
assume that `Out-String` detects failure. Other bounded text or structured-report
approaches are equally suitable; `Out-String` is not required universally.

The syntax uses constructs available in Windows PowerShell 5.1 and PowerShell 7.
Runtime qualification and its platform limits belong to the producer's test
evidence; syntax compatibility alone is not Windows execution proof. For very
large drive lists, narrow the selection to the affected drive instead of flooding
the conversation. Choose report fields/width for the actual question.

## Stop at a real interactive or protected boundary

Suppose a Windows operator says: “Printing is failing; diagnose it.” A restart
could interrupt users and is not authorized by that diagnostic request.

In the first interaction, ask only for this read-only action and its single
report (the service name is fixed for this example):

```powershell
& {
    'BEGIN print service report'
    try {
        Get-Service -Name Spooler -ErrorAction Stop |
            Select-Object Name, Status | Format-List | Out-String
        'OVERALL=0'
    } catch {
        'ERROR: ' + $_.ToString()
        'OVERALL=1'
    }
    'END print service report'
}
```

Wait for the report. A missing service or access error needs interpretation;
do not append a restart as an automatic “repair.” If the returned evidence makes
a restart appropriate, the next interaction explains its disruption and asks
one question: whether the operator authorizes restarting this service now under
the applicable local procedure. That human choice is itself the one input for
that interaction. A No ends the proposed restart path. A Yes permits only the
authorized next action; it supplies neither administrative access nor an
exception to production/change/session boundaries.

Only after that choice and any required local authority is resolved should the
assistant provide the concrete restart-and-verification action for that actual
environment, then request its single report. Do not present that future action
alongside the initial diagnostic request. A Bash session diagnosing a daemon has
the same boundary: collecting facts in one block does not authorize `sudo`, a
service restart or a network change. Conversely, a safe deterministic condition
(for example, reporting a missing optional directory without probing inside it)
can remain inside the diagnostic block without a ceremonial extra exchange.

## Shell references

- [GNU Bash command grouping](https://www.gnu.org/software/bash/manual/html_node/Command-Grouping.html)
  explains group-wide redirection and list status.
- [PowerShell script blocks](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_script_blocks)
  describes invocation and returned output.
- [PowerShell output streams](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_output_streams)
  and [automatic variables](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_automatic_variables)
  describe streams and native exit status. These are shell references, not
  project authority or new operator prerequisites.
