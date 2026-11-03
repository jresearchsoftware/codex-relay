# Task 63 Step 4: Task-aware historical attempt disposition

Date: 2026-11-03. Independently accepted starting source:
`27fa6a65362745da8113425e39faf65ba83352bb` (merged PR #196).
Authority: [Task 63](https://github.com/jresearchsoftware/codex-relay/issues/63),
its owner Step 4 direction and
[standalone handoff](https://github.com/jresearchsoftware/codex-relay/issues/63#issuecomment-6603120636).
This is standalone/manual Step 4, with no new native admission or Writer
Outcome. Original native Step projections and history are preserved.

## Cause and correction

The earlier consumer-transition guard conflated two different facts: whether an
original manual execution has a native terminal receipt, and whether that
historical attempt still represents actionable lifecycle work. Missing terminal
receipts remain missing. A verified owner Task closure or exact interpretation
of a trusted withdrawal/route-switch Decision can now establish nonblocking
lifecycle history without changing `manualAdmissionComplete` or inventing an
execution result.

Native `completed`/`not_planned` closure is derived from the exact repository,
Task, owner identity and closure/reopening events. For an open Task, the protected
owner adapter interprets existing explicit owner direction once and records a
small exact-attempt acknowledgement under the existing claim root. It binds the
original consumer, envelope and whole record to current native source hashes;
it supplies no new authority. Ordinary admission/worker JSON cannot enable this
root-only interpretation. Historical Decision charter hashes remain part of the
unaltered evidence, rather than being rebound to a later Issue body.

Each use rereads native authority, including referenced original PRs, retained
legacy reviews and their native state. Reopening, source changes, withdrawn
sources or changed local effects invalidate reuse. Native read failures have no
offline acceptance fallback. Tokens use the existing protected Writer App and
only repository-scoped metadata/Issues/PR read permissions.

Real worker journals, uncertain execution, incomplete trusted result publication,
pending native mutation and conflicting ownership still block. Existing terminal
v3/v4 receipt formats remain valid; known original PR identity is distinct from
pending PR creation. SERIAL compatibility preserves original journal selection
and checks conflicting manual activity during ordinary global drain/resume as
well as digest changes. Old-digest records remain read-only. Status separates
missing-receipt history from actionable manual barriers.

This removes recurring investigation of unchanged history without adding a
mandatory owner Start/Cancel command, new Task authority, deployment ledger,
model call or generic recovery engine. The
[operator contract](../git-managed-installation.md#strategy-compatibility-and-recovery)
documents the protected adapter and cache lifecycle.

## Source qualification

Product code is frozen at `b836e6bf7daacb8e386bcb0c7f71a63bdf03d18f`.
Native checks and the ordinary standalone result on PR #197 record final-head
validation, warning disposition and actual TEST observations. Earlier
`ea03135a82d90bc122725d55a37b1cf68ef3dd4b` and
`d88a2d5eb0b547259c076c1ca9825430f8a7eb8d` runs are intermediate evidence;
their results do not replace final-code qualification.

An intermediate full root run exposed optional status diagnostics incorrectly
requiring native Task access in credential-free, network-isolated migration
fixtures. The correction retains informational unavailable-source diagnostics for
same-consumer status and strict refusal at required transitions. All nine affected
root cases passed in the targeted correction run; the old failed run is not
counted as final PASS. The private read-only mount/EACCES/EROFS proofs remain
operational tests rather than being replaced with stubs.

Targeted regressions cover owner `completed`/`not_planned` closure, open
withdrawal/route acknowledgement, issued and unissued handoffs, reopening and
authority drift, stale/foreign evidence, active journals appearing during a
read, pending results/publication/recovery, original PR bindings, private PR read
permissions, legacy CR dismissal, unrelated consumers, repeated transitions and
read-only retained SERIAL/pool records. Deterministic fixtures do not claim a
real admitted execution or independent acceptance.

The complete native Linux candidate set passed on the frozen product code:
`git diff --check`; npm (1,286 passed, seven root-only cases separately passed);
root deployment pytest (2,259 passed, eight conditional skips, six covered by the
ordinary-UID supplement); Rust formatting and 159 locked tests; three-consumer
qualification; and the tracked candidate scan. Two Docker/systemd cases remain
unexecuted because a disposable Docker systemd manager was unavailable. Existing
Python `crypt` and Jinja escape deprecations remain secondary warnings. Node
22.20.0, Rust/Cargo 1.90.0 and Python 3.11.2 were used on native WSL Linux.
Root UID-separation probes used a byte-identical Node/source qualification copy.

## Read-only original-history proof

The final-code native reader and safety predicate classified all ten original
records twice using current native Task/owner/Decision evidence: eight
`task-completed`, one `task-not-planned`, and one `route-switch`. The Task 63
acknowledgement selects its exact original attempt and active Decisions
6395315542, 6583905377 and 6584441512. No run IDs are hard-coded in product
classification. The other private consumer's identifiers are withheld here.

This probe used a separate acknowledgement cache wholly inside the allocated
disposable TEST sandbox. Original PROD record bytes, inode identities and absent
manual runner journals were compared before and after and remained unchanged.
No original attempt, PROD cache, configuration or lifecycle state was written.
The result is source/evidence qualification, not an installed PROD transition.

## Genuine isolated TEST boundary

The owner-designated TEST namespace was allocated exclusively to Task 63 during
qualification. Real owner-authored TEST Issues represent `completed`,
`not_planned`, still-open and explicitly abandoned routes. A trusted TEST
Reviewer Decision supplies the last route's exact native reference; no ready
label, real execution admission, model invocation or fictional terminal Outcome
was created. Protected local attempt records are explicitly synthetic historical
fixtures, not claims that Writer admitted those executions.

Installed-runtime probes classified closures and kept unacknowledged open Tasks
actionable; a root acknowledgement under the actual Writer flock made the
abandoned route nonblocking. Real reopening immediately restored the barrier.
Pending comment/PR publication, incomplete submission and unavailable native Task
source remained blocking, with unchanged gate, consumer and original fixtures.

A full public installer invocation against the reopened Task stopped in
`preflight-history` with
`INSTALL_PREFLIGHT_CONSUMER_HISTORY_REQUIRES_OLD_VERSION_RESOLUTION`,
`hostMutation=false`, `recovery=not-started`, and exact prior availability/state
preserved. Native owner reclosure supplied new evidence before the positive
transition; this was not a blind retry.

TEST source and configuration come from independently frozen Git fixtures using
`test-qualified-exact`; this Step uses direct owner qualification, not a new
GitHub Actions workflow dispatch. The prepared shared host uses the TEST-only
`relay_manage_base_packages=false` override, so this is not fresh-host bootstrap
proof. No runner registration, ACL or credential changes are required or claimed.

Ansible's TEST General Runner identity probe reported its known private temporary
directory EACCES and used the standard temporary-directory fallback successfully.
No permissions were widened. This warning remains visible for review even when
the complete operation succeeds.

The final exact-code public operation sequence was:

| Operation | Frozen configuration commit | Observed result |
| --- | --- | --- |
| Product/config transition to `b836e6bf7daacb8e386bcb0c7f71a63bdf03d18f`, effort `high` | `66eed3b35b266a28ea9b053abe234de497d778f5` | Install PASS; changed consumer digest; four historical fixtures unchanged |
| Same-pair Apply | Same commit | Read-only verify/post-check PASS; release, manifest, consumer, gate and Reviewer PID unchanged |
| Configuration-only transition back to effort `medium` | `693d715ded8bca0881ebe3011e41f547ab6cf8ac` | Reconcile/apply PASS; history reused without another acknowledgement |
| Reopened-Task public install against the high pair | `66eed3b35b266a28ea9b053abe234de497d778f5` | Required preflight refusal in 39.18 seconds; no host mutation or recovery; exact old availability preserved |

The final normal TEST installation is the frozen product code plus configuration
`693d715ded8bca0881ebe3011e41f547ab6cf8ac`. Consumer digest returned to
`4c3c06b6a329cea0ab64d54a679e9f5be3c524d3a598f212a8bba20003a35204`;
the high-pair digest was
`2acc42924ea5bffb435aa301072d559f44c81ccacf654cff0a0534d15e104d3e`.
Both TEST gates are open with empty automatic inventories, readiness passed,
and all three relevant lifecycle/pool/Writer locks were free on handback.
Original fixture bytes/inodes and journal observations remained unchanged.
Compared outside-TEST state was unchanged; this is the recorded comparison
scope, not a new global forensic claim. TEST ownership was released.

The sanitized primary summary was read back directly from protected TEST
evidence and its SHA-256 independently matched
`3c70d816c8780aa5949d14fe5f66262065c65950de58a97af70f74ff8b2afc74`.
The protected complete-evidence manifest hash is
`d3b3eb956d475a733d568125163c98ab2367840909604962a90866a009c4711b`;
final readback hash is
`fe0c135876dcb3a686300423650231215e1bfb3cbd4a3fa4d3cd2b3abfc6fb77`.
A separate final read confirmed the actual TEST release/manifest commit,
restored Git-config receipt and open target admission gate.

The final PR may add this qualification report after the frozen installed code.
That documentation-only head requires its own native CI and candidate/link check;
it is not misreported as a separately installed product revision. Supported
exact-head job/check annotations are inspected with the ordinary result. UI-only
service/pre-execution banners are outside that acquisition scope; no global
absence of execution warnings is claimed.

## Remaining protected operation

This source correction does not recover the original PROD operation
`5f09cd11-11c0-427a-b9fa-db43692f635c`. Its original installed target is
`b6edaaf4982df5b7dd6d56fd68b7ce7e34ccd7a9`; historical preflight eligibility
alone neither installs this correction nor changes that operation's gate,
backend journal, frozen sources or service activity intent.

The ordinary recovery adapter in `deploy/install_recovery.py` requires the same
exact target in the backend record and admission gate. Selecting a newer product
correction is not proof of that same-target recovery. Protected
[Deployment Task 2](https://github.com/jresearchsoftware/codex-relay-deployment/issues/2)
must revalidate current retained state, qualify the supported same-target recovery
or an explicitly bounded accepted-helper transition preserving the original UUID
and all old/new source bindings, and prove installed/configuration/service
readback before reopening admission. A missing authenticated old consumer context
and unsupported changed-consumer replacement remain precise independent stops.
Do not blind-retry, retarget the journal, edit history or enable a lifecycle
dispatcher to bypass them. Generic Task 119 completion is not a blanket
prerequisite to a separately qualified bounded recovery.

No PROD mutation, original-history rewrite, lifecycle dispatcher activation,
runner/ACL/credential change, source merge or Task closure is authorized or
claimed by this Step. Source implementation stops for independent exact-head
review; Task 63 remains open through its protected recovery and later cutover.
