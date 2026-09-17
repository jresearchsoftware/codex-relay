# Optional developer recovery and diagnostic helpers

These PowerShell Core helpers support long Codex development sessions. They are
not Relay runtime authority, admission, deployment configuration, a transcript
store or a progress ledger. Work does not depend on a checkpoint. Read the live
Issue/CR and revalidate exact Git/runtime facts after recovery.

## Invocation and activation

Use PowerShell Core 7.2 or newer (`pwsh`) and Git on PATH in the environment
running Codex, on Windows or Debian/WSL. WSL uses its own Linux installations.
The [registration](../hooks.json) invokes `pwsh` directly with one quoted
PowerShell command; Git-root resolution happens inside PowerShell. It works
from a repository subdirectory and with spaces in the checkout path. It does
not require Windows PowerShell, a Windows launcher or a PowerShell-to-WSL bridge.
For direct use, run `pwsh -NoProfile -NonInteractive -File <script> <arguments>`
from the checkout, or invoke the script in an existing PowerShell Core session.

The [official Codex hook contract](https://learn.chatgpt.com/docs/hooks) defines
repository hook discovery, JSON stdin, event matchers and output. Repository
hooks require project trust and review/trust of the exact hook definitions.
Changed definitions need renewed trust; they are not retroactive in an already
running session. Inspect and trust them with the host's hook UI (`/hooks` in
the CLI), then use a fresh session. This repository does not change user/global
configuration, trust records or Relay runner settings. Disabling hooks leaves
manual helper use and ordinary development available.

## One-shot diagnostic read

In PowerShell Core:

```powershell
& ./.codex/hooks/targeted-diagnostic-read.ps1 -SearchPath ./runtime/src -Pattern 'threadTitle'

# If ambiguous, keep the returned locations and select one id in one follow-up:
$locations = & ./.codex/hooks/targeted-diagnostic-read.ps1 -SearchPath ./runtime/src -Pattern 'threadTitle'
$locations | & ./.codex/hooks/targeted-diagnostic-read.ps1 -Mode Read -Ids m1
```

An unambiguous match returns its bounded slice immediately; ambiguity returns
only identifiers and path/line locations. Pass that JSON to at most one `Read
-Ids` selection, not a fresh search with invented ids. `Discover`, `Select` and
`Slice` remain compatibility modes, not the ordinary three-call protocol.

The helper enforces repository confinement, protected `.git`/`.codex/local`
paths, regex timeouts and sensitive-content rejection. Bounds per search are
2,000,000 lines and 64 MiB of content, 250,000 lines per file, 20 recorded
matches and 12 returned locations. Each source line is capped at 320 characters
plus a truncation marker; input/output is capped at 8 KiB. Exhausted budgets
are reported as `truncated`. File coverage is not limited to the first 40 files.
Use a narrow source path; this is not an unrestricted repository dump or a
general-purpose secret scanner.

## Session-owned checkpoint

The ignored `.codex/local/long-session-checkpoints/` directory contains one
SHA-256-keyed path per session; a raw session id never becomes a path component.
Every read, write, recovery, invalidation and deletion resolves the actual
session id. Foreign sessions see no active checkpoint and cannot overwrite or
delete another session's file. There is no repository-wide singleton fallback.
`-CheckpointPath <base-file>` is for fixtures and creates session-keyed siblings.

Ordinary work needs no checkpoint operation. If an irreconstructible diagnostic
frontier is worth saving, use one validated atomic write:

```powershell
& ./.codex/hooks/long-session-checkpoint.ps1 -Mode Write -SessionId '<active-session-id>' -DiagnosticFrontier 'The next useful bounded observation and why it matters.'
```

The helper derives repository identity from the GitHub `origin`, branch, head,
schema and timestamp. No network call is made. A checkout without a recognizable
GitHub origin cannot create a validated checkpoint. Never put credentials,
protected diagnostics, transcripts or a task ledger in the frontier. Validation
happens before atomic replacement; a rejected write preserves the previous note.
`Path`, `Validate` and `Delete` accept the same `-SessionId`. Use `Invalidate`
only for a concrete no-replay/stale-frontier invariant, never as routine write
choreography. Branch and head are provenance to revalidate, not hard recovery
gates. Notes and captures expire after 24 hours; files are bounded to 8 KiB,
frontier to 2,000 characters, optional next action to 1,000 and recovery JSON
projection to 4 KiB.

Registered events:

| Event | Helper behavior |
| --- | --- |
| `SessionStart(startup/resume/clear)` | Announce the active session id and optional writer/diagnostic commands. |
| `PreCompact(auto)` | Capture an already valid note for that session only; never invent a frontier. |
| `SessionStart(compact)` | Project the captured note as bounded recovery context and delete only that session's consumed file. |
| `Stop` | Check a terminal BLOCKED summary against the [development stop contract](../../docs/execution-policy.md#developer-stop-evidence); at most one reminder, guarded by `stop_hook_active`. |

Missing notes are silent; malformed, stale, sensitive or unavailable notes yield
a bounded unavailable result and do not block work. Cleanup failure is reported;
it never authorizes replay of a consumed mutation. The hooks do not parse unstable
transcripts, run Codex, publish to GitHub, change Step or extend mutation authority.
The Stop shape check is a reminder, not evidence of containment or correctness.

## Qualification

Run these from the repository root on each platform being claimed:

```sh
pwsh -NoProfile -NonInteractive -File .codex/hooks/test-targeted-diagnostic-read.ps1
pwsh -NoProfile -NonInteractive -File .codex/hooks/test-long-session-checkpoint.ps1
pwsh -NoProfile -NonInteractive -File .codex/hooks/test-decision-boundary-stop.ps1
pwsh -NoProfile -NonInteractive -File .codex/hooks/test-hook-invocation.ps1
```

The commands also work in Windows PowerShell Core. Fixtures are synthetic,
temporary and self-contained; no private Git commit, source repository or
model call is required. Tests exercise helper behavior, session isolation,
atomic validation, output bounds, path safety, Stop continuation limits, and
the actual registered command strings from a nested working directory with
spaces. Invoking those commands with fixture event JSON is deterministic
helper/launcher qualification, not observation of Codex emitting lifecycle events.

Report helper results with OS, PowerShell version and exact candidate head.
Native lifecycle acceptance is a separate observation for each Codex host and
platform: after definition trust, a fresh Codex App session must show native
evidence of the `Stop` hook and its bounded continuation, plus actual
`PreCompact(auto)` and `SessionStart(compact)` capture/recovery if claiming that
path. CLI evidence does not establish App acceptance; Windows evidence does not
establish Linux acceptance. This candidate claims no native lifecycle proof on
either platform. Do not force context inflation to manufacture that proof.
