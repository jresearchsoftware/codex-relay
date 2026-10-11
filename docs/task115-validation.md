# Task 115 Step 1 validation and handoff evidence

This report belongs to the candidate commit carrying it. It records source and
qualification evidence; it is not independent acceptance, installation authority
or a second Task ledger. Canonical authority remains Task 115 and its current
trusted Request/selected Decision. Earlier observations below retain their
then-current heads and boundaries; the owner clarification and final bounded
handoff below update the current disposition. See the [current source and live TEST disposition](#current-source-validation-and-handoff-disposition);
earlier clean-install/public-recovery stops are historical. The implementation started at
`b4cb4943d52dd375d8c6800959b3264fad082cb8` on `codex/task-115-step-1`.

## Source behavior and compatibility

New GitHub-native admissions resolve the stable charter and active trusted
Decisions into an immutable schema-v4 snapshot in the existing protected attempt
journal. Writer allocates Step under reservation, and replay retains the same
snapshot. Public full Task Requests remain readable for schema-v3 history and
already admitted attempts. Native exact-head CRs remain independent review;
Task Decisions alone amend durable Task scope and effective closure policy.

Manual result submission uses a fixed nonroot MCP client and namespace Unix
socket to a capability-specific root Writer service. The ordinary worker helper
rejects this direct capability. The existing handoff supplies exact public
Outcome bindings so the caller does not need a protected journal read. Writer
reserves and verifies one immutable result and one Bot Outcome; it reconciles
uncertain delivery without inventing a new publication or execution.

New records render English substance, findings, warnings and limitations before
one canonical JSON block. Shared Node/Rust fixtures prove deterministic parsing
and rendering parity, including large-record fallback and unchanged historical
bytes. Native GitHub rendering proof is recorded separately from local tests.

## Validation completed before TEST candidate selection

The complete Node suite ran in native Debian WSL, Node 22.20.0, at
`/home/hortonolite/work/codex-task115-01a12b33`: `npm test` reported 757 tests,
756 passed, zero failed and one skipped. The complete initial run exposed six
candidate-era failures: the native Issue admission prematurely queried ambiguous
PR linkage outside the domain rejection boundary, and five display expectations
still required raw text despite the new escaping contract. The bounded correction
and targeted checks passed, followed by the complete passing suite.

`cargo fmt --manifest-path reviewer/Cargo.toml --check` and
`cargo test --manifest-path reviewer/Cargo.toml --locked` passed on native Linux;
109 Rust tests passed. No Rust code changed after that run. The fixed Unix socket
transport suite passed 7 tests, and rendered deployment capability checks passed
7 tests. These are local contract proofs, not installed credential/ingress proof.

`python3 scripts/qualify.py` reported `THREE_CONSUMER_PASS` for three synthetic
consumers using real handlers/modules, isolated Git and loopback mock GitHub,
without model calls or production credentials. Its source digest was
`58930dd888e6a4ab9a4a9d743bd477302cb72d64c8f772ae615ae2960de09438`.

The staged candidate scanner reported PASS for 484 tracked files and 296 local
Markdown links, with its declared JSON/link/bounded credential-marker scope.
Whitespace checks passed. Final staged files and native CI are checked again
at publication; native check records remain authoritative for CI status.

The full Python candidate run exposed 15 additional introduced fixture-context failures: the existing recovery execution fixture did not supply the new namespace values to StrictUndefined rendering. Those fixture contexts were corrected without weakening template validation. The complete rerun passed 885 tests, with 300 root/host/Ansible prerequisite skips and 19 deprecation warnings (crypt and existing Jinja regex escapes). Those warnings do not claim installed proof or their own regression provenance. Earlier full-run failures were
introduced validation expectations: the workflow fixture evaluator lacked the
new `contains` expression, and its nominal drift fixture used a contract value
that had become current. Those fixtures were corrected; 23 targeted tests passed.
Lifecycle/socket qualification then passed 265 tests with 24 prerequisite skips;
12 upgrade-socket tests passed separately. Three protected bootstrap fixture tests
also passed under native WSL root using disposable fixture state and fake systemd,
not a live installation.

## Execution warnings and protected boundaries

Requested parent profile is `gpt-6.1-sol`, effort `ultra`, Subagents On. Actual
model/effort proof is unavailable from the exposed runtime and remains
`UNAVAILABLE`; requested values are not actual-value evidence. Three bounded
subagents were used, with fresh assignments and no nested Relay/model execution.

The startup title tool accepted the exact Task/Step title once. The available
readback truncates the title, so exact persisted title verification is unavailable;
no repeated rename was attempted. The original routing run `38144146016` and
check `114483871675` succeeded, with no annotations observed at startup. That
routing result does not prove implementation or TEST success.

Task 115's additional TEST-only authority was published as trusted Decision
[6110064799](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110064799)
and complete same-Step successor Request
[6110068398](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110068398).
The protected PROD admission still binds original Request `6109630038`.
Read-only supported Writer `publication-state` confirmed that immutable binding;
no publication or journal edit was performed. Current installed schema-v3
manual publication revalidates current authority, so the successor creates a
source-confirmed currentness boundary: `manual-outcome` revalidates the original
authority digest before reading a result source or reserving a publication. The
digest includes the complete native Request reference and payload; identical
Step, branch and profile do not make the successor equal to the admitted Request.
`AUTHORITY_CHANGED` is the predicted result, not a claimed installed failure.
Changing the submitted result's Request would separately violate the immutable
envelope binding. No supported existing-attempt rebinding route was found in the
installed source. No unsupported
rebinding, PROD upgrade, new execution or arbitrary retry is authorized.

Independent exact-head source acceptance, Task completion, allowed merge,
installation, production qualification and closure remain distinct boundaries.
Task 115 stays open. Any unavailable root/host/ingress/caller proof and material
execution warning remains a decision input even after a durable Git handoff.

## Bounded audit corrections before publication

A supplementary implementation audit found three candidate-introduced risks in
the new manual path. An implemented non-Git result attached to an open source PR
could publish successfully before its Ready transition failed permanently; it is
now rejected before reservation/publication under the existing exact-Git-head
lifecycle invariant. Each direct Draft/Ready reread now also verifies its admitted
Request/admission marker, preserving the old owner-source path's binding check.
The new socket factory explicitly uses `Slice=system.slice`, retaining the
existing lifecycle detector's cgroup path for children whose MainPID has exited;
[systemd's service contract](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.service.xml)
documents the otherwise implicit per-template slice. These are bounded source
corrections, not independent review or proof of installed behavior.

## Installed-helper compatibility correction

One authorized isolated TEST upgrade of candidate `e3ade683...` stopped before
installation with `ADMISSION_SNAPSHOT_INVALID`. The candidate supplied a new
four-component snapshot to installed `dbfea188...`, whose pre-install helper
accepts exactly the original three keys. This is an introduced compatibility
defect, established by the exact installed source and the retained public log.

Correction `d11f65218eaa57e8fd48f753231e21088c87e94b` sends the original wire shape
only when native observation proves the new socket absent, inactive and disabled.
A present socket retains the complete four-component snapshot; unknown state is
rejected and recovery keeps the original saved activation intent. Targeted Linux
qualification passed 16 tests, then all five affected cases passed after the
final absence-state check. The three-consumer qualification passed again with
the unchanged component source digest recorded above. No Node or Rust component
changed relative to their complete passing runs.

Both required native checks passed at that exact correction head:
[Candidate checks](https://github.com/jresearchsoftware/codex-relay/actions/runs/38150552349/job/114502933369)
and [Codex CLI compatibility](https://github.com/jresearchsoftware/codex-relay/actions/runs/38150552349/job/114502933352).
Their primary check annotation endpoints were inspected and were empty. This
does not establish independent acceptance or complete installed TEST proof.

The TEST operation remains preserved as `recovery-required`, with no active or
unknown attempts. Recovery can select a corrected target through the existing
same-operation public interface. Genuine new Actions admission additionally
requires the compatible workflow projection in TEST `main`; current PR 3 has
v3 while `main` remains v2. At that observation, recovery and installation were
held pending the owner
disposition of this consumer review/merge boundary. No new Task 115 phase or
model execution was introduced.

The complete Python rerun with the corrected source passed 889 tests, with
300 prerequisite skips and the same 19 deprecation warnings, in 443.63 seconds.
It used `/usr/bin/python3` and the isolated supported Ansible 2.16.19 command
environment. The deployment-tools venv itself has no pytest module; the first
test launch exposed that local interpreter-selection mistake before collection,
and the explicit existing test interpreter corrected it without a host change.

The connected protected Reviewer read exact-head evidence for PR 118 at
`d11f652...`: target binding verified, required API surfaces complete, zero
check annotation warnings, and no associated Writer Outcome. Its
`none_observed` observation covers those inspected API surfaces. The actual
GitHub run summary was also inspected in signed-in Chrome: success and an empty
Annotations section. These observations do not erase the retained TEST failure,
unavailable actual-profile/title proof or protected publication boundary.

The native validation mirror initially contained mode-only copy artifacts from
Windows drvfs. All 484 index and working-file blobs matched the published source;
affected regular single-link files were owned by the session UID inside that
exact mirror. Only those confirmed duplicate modes were normalized to canonical
Git modes before a non-destructive fast-forward. This did not repair installed
permissions, alter another owner's files or discard useful content. The mirror
and product checkout were clean at the correction commit; later evidence edits
are ordinary Task-owned documentation awaiting the final substantive handoff.

## Legacy marker classification correction

The peer audit identified an introduced routing compatibility defect at
`e3ade68311d3c328b18ef840a4744d5bfd468bc5`, retained at `681f091...`, relative
to baseline `b4cb4943d52dd375d8c6800959b3264fad082cb8`. A quoted migration
marker in otherwise valid legacy prose incorrectly removed its Step display;
the unchanged trusted admission gate then rejected that run title. The template
now matches an actual dedicated marker line using LF padding and LF/CRLF
boundaries. Literal backslash-newline examples do not match. Malformed dedicated
authority still fails closed in the canonical resolver. Owner, triggering actor,
main ref, runner, workflow and fork guards are unchanged.

GitHub's documented [expression semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions)
support `format`, `fromJSON` and case-insensitive `contains`; tests evaluate the
actual template with those string semantics and pass the resulting title into
the real admission broker. Linux targeted workflow/projection checks passed
23 tests, and the launch-metadata suite passed 12 tests. A complete Node rerun
passed 760 tests, with one prerequisite skip and no failures. The three-consumer
qualification and tracked-file candidate scan also passed, with the same
component and Reviewer artifact digests above. No runtime Node or Rust module
changed in this correction; their existing complete qualification remains
applicable. These are source checks, not proof of installed TEST workflow
execution or independent acceptance.

## Owner clarification and bounded general requirement

Trusted replacement
[Decision 6112655517](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6112655517)
and same-Step complete
[Request 6112661946](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6112661946)
record the standing autonomous TEST authorization, the present handoff exception
and the bounded general publication requirement. Native readback verified Bot
actor `306850842` and body SHA-256 values
`d08cd6a43de555e2d7bc6678ba6060efb075cb19349c484b75bf55cf83037a80` and
`8a49967ddf924bec46220e05646936beee0d94cb7ad5d97bb3fb8c0ee593ba8b`.
Original admission, branch/base/starting head, Step and profile remain unchanged;
no new ready event, execution or protected journal edit accompanied publication.

The owner explicitly authorizes the complete supported TEST cycle, including
TEST PR review/merge, upgrades, activation, state recovery and E2E/fixes under
existing permissions. The single
[TEST Environment Authority](execution-policy.md#test-environment-authority)
section owns that model; other procedures route to it. Product PR #118 merge,
PROD/shared infrastructure and external permission/credential changes remain
outside this authorization. The earlier TEST merge hold is superseded, not a
new gate or a reason to request permission for each ordinary TEST operation.

The current Step may hand off PR #118 and committed evidence for independent
review while explicitly reporting the missing normal Writer Outcome and its
predicted `AUTHORITY_CHANGED` cause. No Writer Outcome is imitated and no failed
installed publication is claimed. This is a task-local exception, not acceptance
or permission to change PROD or the original admission.

A bounded source assessment finds the general correction crosses authority,
Outcome and independent-acceptance contracts. It needs separate immutable
execution provenance and explicit current trusted completion disposition bound
to the exact result, including material scope changes. Existing `supersedes`
links alone cannot establish that compatibility. Required future qualification
includes unchanged v3/v4, authorized and unauthorized successors, changed source
bytes, exact-head races, uncertain POST/duplicate suppression, immutable
admission and no execution replay. The owner explicitly excludes substantial
new development from Task #115 completion. The general requirement is durable
in the Decision; this candidate documents the limitation and defers the new
mechanism rather than weakening current authority checks.

## Staged Reviewer packaging correction and TEST recovery boundary

After the authorized TEST PR #3 merge, one supported same-operation recovery
to `44f97a8000eac6f3c6284b32c62f574d7b8edd7b` exposed a second introduced
deployment compatibility defect: staged Rust source requires
`../../contracts/src/github-authority-v4.json`, but the artifact role copied
only v1. Baseline `b4cb4943...` includes only v1; implementation `e3ade683...`
added the v4 include without its relocated staging input. The role now copies
both schemas with unchanged root/group ownership, mode 0640 and remote copy
semantics.

Meaningful native Linux fixture validation passed 14 tests with one existing
root prerequisite skip. The new fixture executes the actual selected Ansible
staging tasks under an unprivileged temporary identity, compiles the real Rust
include paths, removes v4 to reproduce the compiler failure and restores it.
The explicitly enabled full staged `cargo check --locked --offline` also
passed. This validates the source packaging correction, not a release build or
successful installed recovery. Two `unused_mut` warnings in `github.rs` during
the failed live build are pre-existing: that file's Git blob is unchanged from
the admitted baseline to `44f97a8...`; they are not Task #115 regressions.

The live recovery failed after 20 changed tasks. Its ordinary apply record
binds `44f97a8...`; admission operation
`73034a9b-47a1-4ec3-993a-166560bfd39e` remains recovery-required, with the
saved three-service activity intent and no active/unknown attempts. The current
release pointer remains `dbfea188...`. A justified supported read-only check
performed zero changes and reported `recovery-requires-disposition` with an
exact-phase/head-only mutation boundary. No retry or new fixture followed.

Source assessment finds no truthful existing public transition from this state:
ordinary upgrade/rollback rejects the retained apply record; matching owner
apply also rejects the old installed pointer; reinstall rejects the record;
reinstall recovery requires an absent DECOMMISSIONED journal. Completed-apply
stale disposition requires a pointer already at the failed target, and
bootstrap-only disposition excludes this existing consumer. None is applicable.
Runtime reconciliation precedes the failed artifact build, so an old pointer
and active services do not prove byte-equivalence of every installed wrapper,
configuration or unit. A sanitized TASK-name extraction of the retained public
log confirms changes to the stale-disposition helper, Reviewer activation
helper and Reviewer configuration contract, as well as operation reservation
and artifact staging. Exact current root-owned bytes/process adoption remain
an explicit evidence gap; 20 changed tasks are not a complete footprint proof.

The missing public capability is an evidence-bound disposition of failed
partial apply before pointer transition, preserving the original record and
same lifecycle UUID without claiming completed apply. A safe extension must
verify exact old/failed/successor sources, protected record ownership/bytes,
old release/process binding, known partial footprint, preserved activation
intent and no active/unknown execution under the existing host lock. That
material product recovery extension is not silently introduced as a TEST
exception. Standing TEST autonomy is already resolved; the boundary is the
unsupported protected recovery contract, not a request to reauthorize ordinary
TEST actions. The useful packaging fix and exact evidence are preserved for
review; installed manual socket, MCP Outcome and complete E2E remain unqualified.

The recovery capability gap is pre-existing and newly exposed by the introduced
Task 115 packaging failure, not an introduced recovery regression. The scoped
peer comparison used exact baseline
`b4cb4943d52dd375d8c6800959b3264fad082cb8`, failed TEST selector
`44f97a8000eac6f3c6284b32c62f574d7b8edd7b` and packaging correction
`18041a9ef3047130bf562025b31c30d502fe7d13`. Across all three, the ordinary
operation reservation, installed-revision apply preflight, exact-phase/head
record, recovery classifier, completed-apply stale-disposition task/helper and
bootstrap-disposition playbook are byte-identical. Representative Git blobs are
`18920a48b4807543543c34f96152f866b9a1ab6c` (operation reservation),
`672a2e5b49061134ad771c12d947ae2e95baa756` (apply preflight), and
`e51498b1fb15ce72bb5f478e7d383571766da3ff` (completed-apply disposition).
Task 115 changes to clean-reinstall/bootstrap concern manual socket/template
inventory; their existing no-record, DECOMMISSIONED, exact-operation/target and
established-runtime exclusion guards remain unchanged. This source comparison
does not establish the full actual footprint of the twenty live changes.

## Final bounded source correction and handoff

The adjacent reuse audit found that the new external v4 compile input was also
absent from `reviewerSourceTreeSha256`. A schema-only change could therefore
reuse a binary built with earlier authority semantics. The same introduced
`e3ade683...` / retained `44f97a8...` provenance applies; baseline `b4cb4943...`
has no external v4 compile dependency. Source identity now includes both v1
and v4 schemas. The existing exact-equality reuse gate and identity fields are
unchanged. Parameterized schema-only mutations prove invalidation for each
schema without conflating source and deployment build-input digests.

The first complete Python run after the staging correction exposed one
introduced fixture mismatch: it still selected the old singular Ansible task
name (`1 failed, 890 passed, 300 skipped`). The fixture now evaluates the
plural task's actual loop with `StrictUndefined` and verifies both relocated
schema bytes and Rust include paths. Thirteen affected staging/schema/reuse
tests passed. A read-only peer closure audit found both packaging findings
resolved in the four changed source/test files, with no additional material
finding in that bounded diff; it did not issue independent product acceptance.

The final native Linux candidate checks passed with Node 22.20.0, Cargo 1.90
and the supported isolated Ansible 2.16.19 command environment:

| Required check | Evidence |
| --- | --- |
| `git diff --check` | PASS for intended Task-owned source and evidence |
| `npm test` | 760 passed, 1 prerequisite skip, 0 failed; 26.22 seconds |
| `python3 -m pytest -q deploy/tests deploy/ansible/tests` | 892 passed, 300 prerequisite skips, 19 deprecation warnings; 231.28 seconds |
| `cargo fmt --manifest-path reviewer/Cargo.toml --check` | PASS |
| `cargo test --manifest-path reviewer/Cargo.toml --locked` | 109 passed, 0 failed; 6.09 seconds |
| `python3 scripts/qualify.py` | THREE_CONSUMER_PASS with the unchanged component/artifact digests above |
| `python3 scripts/check-candidate.py` | PASS for staged tracked source; declared JSON/link/credential-marker scope |

The Python warnings are the existing crypt deprecation and Jinja regex escape
deprecations. Prerequisite skips and local mock consumers do not qualify
installed process isolation, protected credential access or live ingress.
The later deployment identity/fixture correction changes no Node/Rust module;
their complete passing checks and three-consumer proof remain applicable.
Native CI and its primary annotations remain in the exact-head GitHub records.

The candidate preserves source fixes and sanitized TEST evidence in ordinary
Task commits. TEST PR 3 is merged; draft TEST PR 5 preserves the runbook work.
The source handoff is ready for independent review, but TEST recovery and the
live `submit_manual_outcome` E2E are blocked at the precise public capability
gap described above. No installed success, Writer Outcome, product acceptance,
product merge, Task completion or closure is claimed. The separate general
authority-change publication correction remains deferred under the current
trusted Decision and is not a Task 115 completion gate.

## Corrective continuation and evidence handoff

The current same-Step authority is trusted
[Decision 6113642915](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6113642915)
and complete [Request 6113666253](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6113666253).
Their native bytes and selected source references were verified. The current
starting-head gate `54ad87f3bfd6500b37a6257defb4ae0ef4bc84aa` matched clean
local/remote/live PR 118 heads after fetch. PR 118 is now ready, open and
unmerged, with Step 1 preserved; no original admission or execution marker
was rebound. Two fresh bounded read-only subagents audited the existing public
clean-install path and authority normalization, and one maintained the TEST
runbook. These did not launch Relay workers or expand authority.

The owner chose preserved-evidence TEST removal and clean installation instead
of developing general partial-upgrade recovery in Task 115. One fresh public
read-only inventory at the corrected starting head found equivalent consumer
and deployment configuration, the old installed pointer `dbfea188...`, and
the sole blocker `production-operation-recovery-present;inspect-before-retry`.
Its explicit `mutationAuthorized: false` and the independent public reinstall
guards stop this path before removal. No matching completed-apply, bootstrap or
DECOMMISSIONED reinstall-recovery shape exists. The
[qualification report](task115-qualification.md#owner-selected-clean-installation-current-protected-boundary)
preserves the exact receipt, hashes, publication uncertainty and required
protected action. No general recovery mechanism or guard bypass was added.

The current Request's native publication is verified, but its publisher and
one evidence-based same-record recovery returned
`AUTHORITY_PUBLICATION_UNCERTAIN`. The protected publisher journal's successful
completion is unavailable; no further retry/edit is claimed. This joins the
retained partial TEST operation, unqualified live manual socket/MCP/E2E,
consumer aggregation gaps and earlier material warnings as an explicit next
owner/review input. The original PROD admission remains bound to Request
6109630038; no Writer Outcome was submitted, published or imitated. The
task-local PR/committed-evidence exception remains operative.

Only evidence and TEST README were changed in this continuation. Runtime,
schemas and managed workflows retain the fully tested source bytes above;
the complete local suites and three-consumer proof remain applicable. At report
authoring, whitespace and staged candidate scanning passed for 485 tracked files
and 303 local links. Native checks for the carrying evidence commit remain a
pre-handoff requirement, with their results in the PR's exact-head GitHub records.
Task-owned changes use the existing ordinary non-force commit/push flow.
Private 0600 logs and protected recovery records are
retained at their existing access boundary, not committed, removed or repaired.
Product merge, independent acceptance, Task completion/closure, TEST removal,
clean install and live E2E remain unclaimed. The general recovery and
authority-change completion mechanisms are deferred, not implemented as
mandatory extensions of this Task.

## Current source validation and handoff disposition

The current same-Step trusted authority is
[Decision 6114003261](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6114003261)
and [Request 6114012178](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6114012178).
Their exact native bytes, selected reference and Reviewer Bot identity were
verified. They authorize permanent general TEST autonomy and direct cleanup
of disposable blocking state. The clean starting gate `7862bb742...` matched
local/remote/PR before ordinary task commits. This same Step and existing PR
preserve the original admission's Request 6109630038 and execution markers.

General TEST Environment Authority is now routed from AGENTS, deployment,
architecture and the shared execution prompt. Public production-safe lifecycle
interfaces are optional for sandbox cleanup/rebuilding; per-operation approval,
forensic retention and per-file ownership gates do not apply to disposable TEST.
Independent product source acceptance, original admission/publication identities
and external/PROD boundaries remain separate. Product PR 118 stays unmerged.

The complete required source check set was run at
`74660d74b888d1669ea54779e74667315cce1305` in a separate clean native Debian
checkout, leaving the installed-source deployment checkout at `5699432e`:

| Required command | Result |
| --- | --- |
| `git diff --check` | PASS |
| `npm test` | 760 PASS, 1 SKIP, zero failures |
| `python3 -m pytest -q deploy/tests deploy/ansible/tests` | 892 PASS, 300 SKIP, 19 warnings |
| `cargo fmt --manifest-path reviewer/Cargo.toml --check` | PASS |
| `cargo test --manifest-path reviewer/Cargo.toml --locked` | 109 PASS |
| `python3 scripts/qualify.py` | THREE_CONSUMER_PASS |
| `python3 scripts/check-candidate.py` | PASS, 485 tracked files / 307 local links at this checked source head |

The recorded environment was Node 22.20.0, npm 11.19.1, Python 3.11.2,
pytest 7.2.1, Rust/Cargo 1.90.0 and Ansible Core 2.16.19. All seven commands
returned 0, from 2026-10-11 21:59:25 to 22:04:06 UTC. Twelve nonsecret local
log/metadata files were verified against their SHA-256 manifest; its digest is
`c0549a25239db6535c63775a9683fe70612fb063f647be4b5ea244859b28d105`.
Qualification digests: source
`7d9a47699db128ad2b03dac5eb2d14d4aa8405f990999843454c962228f3ceb1`,
Reviewer `82e7036dfc188f9add29f1ccebd25419b9bf1504875197c8bb285075e25f5eeb`,
Reviewer test `746fe78a7e13f1e2a1c83b651263b9012a75e1901c12d98be1e78755db89567d`.
Final evidence-only edits receive whitespace, staged scanner and exact-head
native CI checks; they change no runtime code. Whitespace and the staged scanner
passed with 486 tracked files / 314 local links for the final evidence additions.
A bounded read-only peer audit found no material evidence inconsistency or
credential marker in these additions; it did not repeat host checks or provide
independent acceptance.

The root-identity synthetic UID-separation npm case was skipped, not escalated.
The `-q` Python summary does not enumerate the 300 skip reasons; these are
not reported as PASS. One Python `crypt` and 18 installed-system Jinja2 escape
deprecation warnings remain explicit. The validation shell wrapper returned 1
only after all checks/logging completed because a PowerShell pipe appended CR
to its final `exit 0`; direct subsequent log/manifest verification returned 0.
That harness artifact is recorded separately from the seven successful checks.
Baseline Rust `unused_mut` declarations and earlier unresolved execution warning
evidence retain their existing disposition; green source/CI does not erase them.

The [current TEST qualification report](task115-qualification.md#completed-clean-test-installation-and-live-manual-outcome-qualification)
records direct sandbox cleanup, public clean bootstrap/activation/operational
post-check PASS at installed `5699432e`, preserved external credentials/permissions,
and [native Writer publication receipts](task115-live-manual-outcome.json).
Two disposable protected admission-shaped fixtures exercised the installed
MCP frontend, fixed client, Unix socket/root Writer, TEST App and actual GitHub
Outcomes. Native Bot/body/result/count read-back and replay/conflict/binding/PR/TLS
negative checks passed. No real admission, ready command, new Task/Step, worker
or model execution occurred. The fixture used a separate synthetic private CA;
official connected TEST read-only MCP identity/transport was verified separately.
Its four-tool connector catalog still makes official `submit_manual_outcome`
invocation unavailable. This is an explicit connected-client qualification gap,
not a claim of full official transport/tool acceptance.

The sole runtime delta after installed `5699432e` is the source-tested shared
execution prompt sentence routing disposable TEST to the general authority.
Manual Outcome, frontend, socket, Writer, admission and managed workflow bytes
are unchanged; installed revision and final source head are not conflated.
The new prompt was not traversed by another model execution. Temporary fixture
services/keys/state/synthetic records were removed after collection, native
history retained and official TEST services/socket verified active. TEST PR 5
is merged; README-only TEST PR 8 was reviewed at `3793f79f5c5915469a7b909ce711b334b982daa1`
after eight unit tests and its native candidate check, then ordinarily merged to
TEST main `f6af49649a35ff0bdd6728e22e99c1c13258ae5d` under standing TEST authority.

Current Request native publication is verified by complete body hash and Bot
identity, but the publisher returned `AUTHORITY_PUBLICATION_UNCERTAIN`; its
protected journal completion is unavailable. No retry or protected journal edit
was used. The original PROD admission's schema-v3 binding would return
`AUTHORITY_CHANGED` after successor authority. No Task 115 Writer Outcome was
submitted, published or imitated. The owner-authorized PR 118/committed-evidence
handoff exception remains the completion channel for this Step. General production
upgrade recovery is deferred to Task 119; substantial authority-change completion
development is not made a completion gate here.

Independent exact-head product acceptance, official new-tool connected-client
qualification/disposition, product merge, Task completion and closure remain
unclaimed. Requested parent profile remains gpt-6.1-sol/ultra; actual model/effort
and exact persisted full title proof remain UNAVAILABLE. Bounded subagents were
used under the admitted On permission, without Relay fan-out or expanded authority.
Task-owned source/evidence and TEST commits use ordinary non-force publication;
unrelated worktrees and external protected logs remain outside cleanup.
