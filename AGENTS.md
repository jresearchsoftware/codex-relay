# Developing Codex Relay

These instructions govern **owner-admitted Relay/Codex development**. Ordinary
human contributors use [CONTRIBUTING.md](CONTRIBUTING.md); they do not need
Task/Step admission, an installed Relay consumer, Codex UI tools or these
optional developer hooks to propose a change.

Read the live canonical Issue or Change Request, the exact starting head/base
and relevant native checks before changing code. Repository files explain the
product; the admitted task defines the goal and allowed external actions.
Read [architecture](docs/architecture.md) before changing orchestration or a
trust boundary, and the affected component contract before changing its API.

## Task identity and startup rename

`Task N` is canonical GitHub Issue `#N`, not a separately allocated number.
Use these complete titles, with a concise purpose:

- Implementation: `Task N — Step S — <purpose>`.
- Remediation: `Task N — Step S — CR-N-NNN — <CR purpose>`.

Preserve an exact title supplied by live task/CR authority, including an
explicit phase qualifier. Step is a positive, explicitly resolved value.
For Relay admission the canonical Issue has exactly one `step-S` label;
the existing PR must agree. Fresh work starts at `step-1`. The owner chooses
continuation Steps; a new executable CR advances synchronized S to S+1 through
the [owner metadata procedure](contracts/README.md#owner-step-metadata-procedure).
Retrying execution or repairing publication of that same CR keeps its Step;
approval does not increment it. Never infer Step from prose, old Outcomes,
commits, runs or the largest historical Step. Missing or conflicting admission
metadata needs reconciliation. Step labels alone do not launch work or grant
authority. The [Issue template](.github/ISSUE_TEMPLATE/codex-task.md) supplies
the authoring baseline; its creation is not admission or dispatch.

For an owner-launched manual session, rename the current Codex task at startup
to the exact title resolved from live task/Change Request authority above.
Use the native task-title tool once with only `title` (omit `threadId`); search
deferred tools if it is not initially visible. Recording the title only in a
prompt, PR or Outcome is insufficient. When the current native tool surface can
read back the persisted title, compare it with the exact requested title. A
successful rename call alone does not prove persisted state. Report the call
result and any read-back mismatch, truncation or unavailable verification
truthfully. An unavailable/failed rename or unverified exact title is
non-blocking; do not repeat the rename to chase a match. Preserve the supplied
Task/Step identity; never infer a new Step from history. Automatic runtime
execution already passes its resolved title to Codex and does not require a
worker to discover or invoke the UI rename tool.

## Canonical checkout and safe Git handoff

Before applying an existing PR's starting-head gate, read its live repository,
branch, base and required SHA. Inspect the current checkout, worktrees, dirty
state and unpublished commits. Safely fetch the canonical branch and switch
to it only when local work is preserved; a clean branch that only lags can be
fast-forwarded. Then compare both local canonical HEAD and refreshed remote
head with the required SHA. An incidental initial branch is not a mismatch.
Never reset, force-push, discard, absorb unrelated work or replace the branch/PR
to satisfy a gate. A real mismatch or unsafe unpublished work is a concrete
boundary. Trusted normalization applies before worker access; a model-modified
worker checkout must still use the trusted import boundary below.

Before any terminal result, including BLOCKED, reconcile task-owned changes
and preserve useful progress in substantive commits. Publish safe, authorized
unpushed task commits to the existing task branch; automatic workers hand them
to Writer. Leave unrelated changes untouched. Remove only confirmed disposable
residue; use ignores for repeatable generated artifacts without hiding work.
If a safe commit/push or clean handoff is impossible, report exactly what stays
local and the authority, branch, permission or security boundary. Never create
empty or metadata-only commits merely to record status. Explain material
execution warnings even when the result is green.

## Execution context and shells

Identify the actual execution environment before choosing command syntax and
paths. Use the shortest qualified parser/transport path that preserves the
admitted boundary. From Windows, use `wsl.exe --distribution <distro> --exec`
with the Linux executable and its arguments when Linux execution is needed.
When already inside Debian/Linux, execute directly; do not add a WSL hop or an
unnecessary shell. Use native Linux paths there. Runtime/filesystem boundary
checks need a native Linux filesystem as described in
[CONTRIBUTING.md](CONTRIBUTING.md#local-validation).

Use PowerShell Core (`pwsh`) for PowerShell-oriented work on Windows or
WSL/Linux when Bash is not the implementation boundary. Use Bash when a
source-controlled `.sh` entrypoint or Bash-specific behavior requires it.
Prefer direct argument passing or a script file (`pwsh -File` or `bash <script>`)
over nested command strings. Do not carry non-trivial commands, JSON, patches
or Markdown through multiple shells for reinterpretation; use files, structured
tool arguments or a single native parser. This routing rule does not replace
an admitted entrypoint or authorize a different credential/security boundary.

For material PowerShell-to-native calls, propagate failure immediately before
dependent work. `$ErrorActionPreference = 'Stop'` alone does not establish that
native nonzero exits stop execution. Use supported native error propagation or
capture `$LASTEXITCODE` immediately and throw/exit on unexpected failure.
Handle intentionally expected nonzero results explicitly; do not let a later
successful command hide the material command's failure.

## Work within the admitted goal

Use [progress-bounded execution](docs/execution-policy.md): inspect evidence,
make a justified correction, run relevant validation and continue while the
next action is clear and authorized. Preserve useful work. Stop when progress
needs a human decision, authority is uncertain, the next material correction
is ambiguous, the same action fails without new evidence, or prior execution
or external mutation is unknown or uncontained.

Do not create nested workers or subagents unless the task separately authorizes
them. An inner correction does not itself need a new Issue, Step or execution.
Never convert this rule into a Relay retry loop. A manual task may publish
through its explicitly authorized owner channel; an automatic worker delegates
publication to Writer.

## Minimum sufficient ceremony

Use the least complex process that preserves source truth, reproducible checks,
authority and independent acceptance. Prefer live Issue/CR, PR diff, exact Git
facts, native checks and one Outcome over duplicate ledgers, receipts or packets.
A self-contained packet needs a concrete independent purpose. Do not add a
commit, review pass, gate or state transition when existing evidence proves the
same invariant; stronger controls need a concrete risk or authority reason.

Aggregate related findings, use targeted checks while correcting them, and run
the required full candidate set once before handoff unless a later change or
new failure justifies repetition. Close active references when moving an
entrypoint, identifier, shell or execution context. Deterministic PASS does not
replace independent judgment. Keep inner corrections within the admitted goal
and the progress-bounded stops above.

Promote accepted reusable decisions through the next suitable authorized,
bounded Task/Change Request when the correction is independently useful.
Do not require completion of the unrelated remainder of a later backlog item
or create a separate ceremony-only task. Keep the correction within the
admitted goal and put it in the existing policy or component contract.

Optional [developer hooks](.codex/hooks/README.md) provide bounded diagnostic
reads, session-owned recovery and a bounded Stop reminder. They are not Relay
runtime authority. A missing checkpoint is silent and nonblocking. When useful,
write only the irreconstructible diagnostic frontier through the validated
atomic writer; never store secrets, transcripts or a parallel task ledger.
After recovery revalidate mutable authority and exact Git/runtime facts.

## Preserve the product boundaries

- Keep consumer policy, model defaults, credentials, runner configuration and
  operations in consumer-owned configuration. Use synthetic examples here.
- Resolve model, reasoning effort and Subagents once at admission. These are
  the execution-profile fields for launch cards, task metadata and handoffs;
  an effort identifier does not imply an additional capability switch. Do not
  silently substitute profiles or consult a moving external recommendation
  during execution. Record actual model/effort only when runtime evidence
  exposes them, otherwise `UNAVAILABLE`; requested values are not actual-value
  proof. Record whether subagents were used within the admitted permission.
- Keep owner, worker, Writer and Reviewer responsibilities separate. Review
  acceptance is independent and bound to the exact candidate head.
- Preserve reservation-before-mutation, replay suppression, non-force Git
  publication, safe paths/modes and scanning of every introduced blob.
- Never run trusted Git against model-modified metadata. Import bounded object
  bytes into a fresh trusted repository and validate them.
- Source changes and local tests do not authorize deployment, credentials,
  service changes, merge, Issue closure or release. Do not claim those proofs.
- Prefer existing GitHub/Git records over a new ledger, registry or workflow
  engine. Add machinery only for a demonstrated product requirement.

## Validate and hand off

Use Linux for the runtime and filesystem boundary tests. Run affected suites
during corrections and the complete candidate checks before handoff:

```sh
git diff --check
npm test
python3 -m pytest -q deploy/tests deploy/ansible/tests
cargo fmt --manifest-path reviewer/Cargo.toml --check
cargo test --manifest-path reviewer/Cargo.toml --locked
python3 scripts/qualify.py
python3 scripts/check-candidate.py
```

The candidate check scans tracked files; stage intended additions before using
it. Do not stage unrelated work. For hook changes also run the PowerShell Core
checks and state the platform evidence described in the
[hook contract](.codex/hooks/README.md#qualification). Local contract tests do
not qualify consumer sudo wrappers, process isolation, credentials, ingress or
a production service.
Native checks and independent review remain separate evidence.

Describe the problem and final behavior in the PR. Report the exact final head,
validation results and limitations in one top-level Codex Outcome on the
canonical authority. Distinguish implementation complete from independent
acceptance. Do not post a Reviewer verdict for your own work.

Future task files include `## Recommended model budget` with recommended model,
effort, rationale and escalation/de-escalation conditions. The task author
resolves an explicit profile or delegates omitted fields to the admitted
consumer configuration; there is no repository-specific model default here.
An interactive prompt cannot change the user's UI model/effort selection.
Keep task-specific authority and execution evidence in the live Issue/PR,
not a duplicate registry.
