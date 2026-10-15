# Task 103 Step 3 real automatic TEST smoke preparation

These tools prepare independent disposable TEST Task charters/Decisions and
reconcile collected evidence offline. They do not publish, authenticate, install,
set ready labels, reserve Steps, seed protected state, invoke a model, accept,
merge or clean up. Product authority remains Decision
[6173381429](https://github.com/jresearchsoftware/codex-relay/issues/103#issuecomment-6173381429)
and the actual protected Step 3 admission. There is no second governance Task.

## Prepare and execute through the existing v4 path

1. Run `node docs/evidence/task103-step3/prepare-smoke.mjs charters OUTPUT 120`.
   This creates `same-a`, `same-b` for testbed and `cross-a` for testbed plus
   `cross-b` for testbed-2. Each is a separate genuine Task, a single output
   file, a separate branch, `gpt-6.1-sol / medium / Subagents Off`, and four
   foreground waits of 30 seconds. The allowed total hold is 60–180 seconds.
2. Once TEST installation, isolation and the native v4 capability are verified,
   use the authorized owner channel to create each independent Issue from its
   `*.issue.json`. Capture the complete native Issue, repository object and
   current base-branch commit with read-only GitHub API calls. No ready label yet.
   Save `{ "variant": "same-a", "issue": ISSUE_GET_OBJECT,
   "repository": REPOSITORY_GET_OBJECT, "main": COMMIT_GET_OBJECT }`.
3. Run `node docs/evidence/task103-step3/prepare-smoke.mjs decision OBSERVATIONS.json OUTPUT 120`.
   Pass the emitted `{repository,record}` to the current TEST
   `publish_task_authority` capability. Read back and verify the native Decision,
   trusted TEST Reviewer actor/App, complete body digest and effective profile.
   The generator checks the two exact repository IDs (1407614568, 1409883950),
   complete charter bytes, no ready label, open Issue and current SHA.
4. Launch the two same-repository Tasks with distinct real **owner User**
   `codex-ready-auto` events, close enough for their bounded holds to overlap.
   Writer must allocate the real Step and bind the real event/run/attempt.
   Collect trusted host observations while both actual `codex exec` processes
   exist. Wait for distinct terminal native Writer Outcomes. Then repeat with
   the two cross-repository Tasks on the same physical isolated TEST host.
   Keep protected journal/claims untouched. Do not replay a run for evidence.

New Issue numbers, event IDs, run IDs, Step values, actor IDs and admission
digests are observations, never parameters to invent. Authentication and all
external mutations belong to the parent manual execution. TEST App tokens are
not suitable substitutes for owner User ready-event authority. These scripts
must not be used to claim synthetic Task 115 fixture state as real inference.

## Collect and reconcile real readbacks

Use complete `gh api --paginate --slurp` reads for the exact fixture Issue's
`events` and `comments` endpoints and its Writer result PR's `comments` endpoint.
Get the exact Issue, run and PR objects. Read the original protected claim and
journal through the authorized host channel. Do not copy secret files or
process environments. Inspect native annotations and material warnings
separately; a successful run alone does not disposition them.

Create a JSON manifest in the collection directory with this shape. IDs below
are descriptions of **observed values**, not executable placeholders:

```text
{
  collected_by: "owner-local-manual",
  native_reads_complete: true,
  cases: [{
    name: "same-a", repository: "jresearchsoftware/codex-relay-testbed",
    task: OBSERVED_ISSUE_NUMBER, run_id: OBSERVED_RUN_ID, owner: VERIFIED_OWNER_LOGIN,
    routing_workflow: VERIFIED_CONSUMER_ROUTING_WORKFLOW_PATH, base_branch: "main",
    writer_actor: {id: OBSERVED_ID, login: "jresearch-relay-test-writer[bot]", type: "Bot"},
    reviewer_actor: {id: OBSERVED_ID, login: "jresearch-relay-test-reviewer[bot]", type: "Bot"},
    files: {issue: "same-a.issue.json", events: "same-a.events.pages.json",
      comments: ["same-a.issue-comments.pages.json", "same-a.pr-comments.pages.json"],
      run: "same-a.run.json", pr: "same-a.pr.json", claim: "same-a.claim.json",
      journal: "same-a.journal.json"}
  }, ...],
  pairs: [{kind: "same-repository", cases: ["same-a", "same-b"]},
          {kind: "cross-repository", cases: ["cross-a", "cross-b"]}],
  host_observations: "protected-host-observations.json",
  execution_inventory: "protected-execution-inventory.json"
}
```

The owner-local host collector records at least two live `/proc` observations
for each actual Codex process. Preserve the collection command/source and
sanitized raw observations as evidence. Attribute the process to the exact
protected attempt using its worker service/cgroup, runner slot and checkout;
do not infer attribution from timing alone. The observations JSON has
`source: "trusted-host-procfs"`, `complete_for_window: true`, and `samples` with:

```text
{observed_at: UTC_TIMESTAMP, repository: EXACT_REPO, run_id: EXACT_RUN,
 attempt: "run-EXACT_RUN", host: PHYSICAL_HOST_ID, execution_slot: EXACT_SLOT,
 pid: ACTUAL_CODEX_PID, uid: ACTUAL_UNPRIVILEGED_UID,
 proc_start_ticks: PROC_STAT_STARTTIME, executable: ACTUAL_PROC_EXE_ENDING_IN_CODEX,
 command_role: "codex-exec", cgroup: ACTUAL_PROC_CGROUP, process_state: PROC_STATE}
```

Inventory has `complete_for_window: true` and `attempts` containing
`{repository, task, step, attempt, ready_event_id, child}` for **all** protected
claims/journals/execution receipts in the fixture window, including duplicates,
blocked and canceled attempts. Derive each item from protected evidence, not
the expected plan. Preserve the original observations separately. Duplicate
suppression is bounded to that window; unexplained or unenumerated state stops
the proof. The script trusts the authenticated operator's collection and
completeness statements; it cannot authenticate a copied JSON file's origin.

Run `node docs/evidence/task103-step3/verify-smoke.mjs MANIFEST.json RECEIPT.json`.
It checks native owner event/run binding, trusted workflow/base ref, v4
admission digest, original charter/Decision bodies and actors, returned/reaped
execution, positive native Codex usage, exact fixture PR head, one distinct
Writer Outcome/body digest per attempt and one inference per consumed event and
Task/Step in the inventory. Overlap uses stable observed Codex PID/starttime
intervals, separate UID/cgroup/slot identities, and the same physical host.
Actions queue/run overlap or worker-written timestamps do not satisfy it.
Actual model/effort remain `UNAVAILABLE` unless runtime evidence exposes them;
requested profile and positive native usage do not prove the actual model ID.

## Additional bounded race probes

Record probe boundaries, exact inputs, native events and protected observations
before each probe. Do not call a deterministic test a live race qualification.

| Probe | Bounded genuine TEST observation |
| --- | --- |
| Same Task duplicate | If the qualified TEST interface supports duplicate delivery of the exact original native event, observe replay suppression without a second inference. A second owner ready event is a distinct command: observe its queued disposition while the first worker holds, preserve that owner work, and do not count it as duplicate-event proof. Do not relabel or rerun an uncertain attempt. If exact-event delivery is unavailable, report that live probe unavailable and retain deterministic coverage. |
| Cancel before/after reserve | Use separate short fixture Tasks. Cancel one queued native run before reserve and one after a verified reservation. Observe zero inference or exact child containment/terminal disposition; retain unknown state and use original-attempt recovery without re-inference. |
| Finite capacity/queue staleness | Hold exactly the configured capacity, add one genuine bounded fixture Task, and observe pending/backpressure and eventual native disposition. Verify no replacement or lost owner event; never create an unbounded queue. |
| Writer lock / journal diagnostics | Have real independent completions reach Writer together; observe protected waiting and unique claim/journal/diagnostic paths. Any deliberate lock hold uses only the existing TEST entrypoint and a short watchdog; do not edit lock state or introduce a private bypass. |
| Quiesce/drain / interruption | With two observed fixture workers, use the supported isolated TEST drain operation. Observe launch refusal/backpressure, original-worker containment and protected recovery. No unknown attempt is automatically re-inferred. |
| Base/head movement | After binding a fixture to its immutable base, advance TEST main with an independently authorized unrelated fixture result via its ordinary path. Observe safe old-base execution and unchanged task refs. A task-head conflict must stop safely; do not force, reset, or mutate another fixture's branch to create evidence. |
| Implementation + unrelated remediation | Use two genuinely independent TEST Tasks: one ordinary implementation and an existing fixture PR with a trusted exact-head native v4 CR. Observe overlap and separate Outcomes under their original authorities. These implementation-only charters do not manufacture remediation authority. |

Portable source race tests complement these probes, including reserve/preflight/
checkout/publication base movement and SERIAL compatibility. Missing live
capability, primary warnings, resource/quota limits, or unobservable process
attribution must be reported as an unqualified dimension, not a PASS.

Offline check: `node --test docs/evidence/task103-step3/offline-check.mjs`.
Its records and timestamps are explicitly deterministic in-memory inputs.
It validates all four Decisions and negative cases for forged/moved/duplicate
records, incomplete inventory, missing native model usage and absent overlap.
Passing it does not prove live admission, worker execution or acceptance.

## Read-only TEST host collector

Run `collect-host.py` only through the qualified root channel on the isolated
TEST host. It reads the root-owned `/etc/codex-relay-test/consumer.json` and
`/etc/codex-relay-test-two/consumer.json`, their fixed configured slots,
`systemctl show` metadata, numeric protected journals/Writer claims, and procfs.
It never reads credentials, tokens, environments or model conversations.

```sh
python3 collect-host.py observe --namespace codex-relay-test --namespace codex-relay-test-two --duration 900 --output /root/task103-observe-UNIQUE
python3 collect-host.py snapshot --namespace codex-relay-test --namespace codex-relay-test-two --run codex-relay-test:REAL_RUN_ID --run codex-relay-test-two:REAL_RUN_ID --output /root/task103-snapshot-UNIQUE
python3 collect-host.py --self-test
```

Output directories must be new children of a root-private directory under
`/root`; the collector creates them `0700` and JSON files `0600`. Observe is
bounded to 900 seconds with a two-second sampling interval and compact counts.
The primary services are exactly `codex-relay-test-general-runner.service` and
`codex-relay-test-two-general-runner.service`; additional slot services follow
the qualified namespace/slot contract. UID, exact service cgroup, checkout and
original claim/journal binding must all agree. Unknown slots, processes or
ambiguous attribution yield explicit gaps rather than timing-based assignment.

Before a slot's first reservation, its configured `attempts-v2` or shared
`publication-v2` leaf may not exist. The collector reports that as observed empty
only after no-follow inspection and access to every existing protected parent;
it never creates the leaf. `protected-sources.json` records the absent-leaf
observation and parent metadata. Missing parents, denied access, unsafe metadata
and aliases remain gaps. Disappearance of a directory or numeric record already
observed during the window also remains a gap, including a claim after its
journal appeared. Cached records revalidate metadata changes. The directory
and cache checks in `--self-test` require native root private fixtures; other
offline checks still run without root.

`protected-host-observations.json` and `protected-execution-inventory.json`
are compatible with the verifier. `protected-sources.json` preserves original
byte hashes, owners, modes and source metadata. Snapshot exports full immutable
v4 admission machine fields plus the required usage/receipts, omitting worker
input, result prose and diagnostics. Original native/protected records stay
untouched; exports are sanitized readbacks, never synthetic state. A complete
window is asserted only when collection finishes without unit, source or
attribution gaps. Procfs exit races can miss short invocations; absence of a
sample is not proof of zero inference. Snapshot run IDs must be actually
observed; root execution grants no non-TEST or model-launch authority.

## Concrete bounded native sequence (pending execution)

This is a Task-local qualification plan, not another workflow engine or a
product acceptance record. Product Task 103 Step 3 remains original attempt
`run-38607140200`, handoff comment `6174334004`, selected Decisions `6169903912`
and `6173381429`. Refresh mutable heads/installation facts before execution;
do not copy a moving product or consumer SHA from this plan. No model probe has
been established by preparation or deterministic root qualification.

The genuine existing success fixtures are testbed Issues **16 / same-a**,
**17 / same-b**, **18 / cross-a**, and testbed-2 **3 / cross-b**. At preparation
readback they were open, had no ready labels and no typed trusted Decision.
Their charters alone do not supply the planned exact branch/base/profile
Decision bindings. Publish/read back each prepared current-v4 Decision using
the actual Issue body and current consumer main before its owner-ready event.
Their requested profile is `gpt-6.1-sol / medium / Subagents Off`; actual model
and effort remain unavailable unless observed runtime metadata exposes them.

Create only the additional independent TEST fixtures needed below. Each gets a
stable `github-native-v1` charter, one explicit `keep-open` policy with remaining
evidence conditions, a trusted v4 Decision, a unique `codex/task-N-...` branch,
the actual starting/base SHA, and the same short profile. Writer alone allocates
Step on the real owner event. Q/C/S/I/L/K denote roles, not invented Issue
numbers. Ordinary smoke roles write only
`qualification/task103-parallel/ROLE-N.txt`, one constant ASCII marker plus LF,
verify bytes, commit and return normal structured results. L uses at most six
30-second foreground waits; R's declared private-mode probe is the exception
specified below. No extra fixture changes deployment/workflows or credentials.

| Order | Exact native action and fixture authority | Required observed evidence |
| --- | --- | --- |
| 0. Freeze/read back | Verify each TEST consumer's independent protected config, current release, Writer/Reviewer App/installation, slot UIDs, runner units, paths, workflow/ref restrictions, open gate and absence of unresolved target/slot attempts. Start a fresh bounded `collect-host.py observe` window. Activate only qualified dedicated TEST runtime through the parent's admitted installation operation. | Two repository-configured controller/Writer paths and distinct claim/journal/slot identities on the same physical host; actual capability and quota evidence. Shared App identity is not a one-Writer/many-repositories configuration. Source/root PASS is not live inference. |
| 1. Same repository | As the actual configured owner User, add `codex-ready-auto` once to testbed #16 and #17. Wait for two attributed actual Codex processes, not two queued jobs. If queue-age evidence must exceed 120 seconds, authorize the first pair's hold as 180 seconds in their trusted pre-admission Decision; explicitly supersede the charter's 120-second wait without editing the stable charter. | Two distinct native events/runs/Step admissions, two separate live PID/starttime/UID/cgroup/slot intervals, positive native model usage, two independently attributable terminal Writer Outcomes and exact result PR heads. |
| 2. Genuine replay / same-Task command | After #16's real protected claim says `readyConsumed: true`, replay only its original consumed `admit` through the registered Writer helper as its original configured runner user; stop after the helper receipt. Separately add one later owner ready event to #16 while its original run is active. Never rerun Actions or start another controller for the replay. | Replay returns `resumed: true` with the identical admitted attempt/profile/digest and no new Step/journal/process. The second native command is distinct, queues by Task and eventually receives a prior-attempt/prewritten-command refusal; record the actual code rather than assuming it. Exactly one inference for the original Task/Step/event. |
| 3. Capacity / queue / cancellation before reserve | With both slots observed occupied, ready a new Q (normal wait) and a new C (cancel before reserve). Add at most two S commands for the stale probe below. Cancel C using native Actions while its job is still waiting for a runner. Allow Q to start normally after a slot releases. | Finite two-worker capacity, bounded pending count, Q preserved rather than replaced, actual wait/admission timestamps, C's native canceled disposition and complete protected scans proving no claim/journal/Step/inference for C's exact run. A queue wait greater than 120 seconds must be measured; freshness uses run creation minus event creation, not job start. |
| 4. Stale queued event | On independent S, while no slot is free: ready once, capture run/event S1; remove/add the ready label once to create S2 after S1's native run creation; cancel S2 while queued. Let S1 reach Writer with the now-newer native event still visible. | S1 refuses the stale command before reservation/Step/worker; capture the actual `READY_EVENT_STALE` or other precise boundary, complete event chronology, both native run dispositions and absent exact-run protected state. S2 is canceled, not silently treated as work performed. No automatic retry or invented Outcome. |
| 5. Writer contention / interleaving | Once both workers are already admitted, hold only the existing verified TEST `publication-v2.lock` with bounded kernel `flock` for at most 15 seconds, with a 25-second watchdog, around an observed real publication boundary. Do not write its bytes or any claim/journal. | An actual blocked Writer/flock PID tied to the fixture runner cgroup and lock inode, measured acquisition/release/wait, eventual separate native Outcomes, intact per-slot journals and diagnostics. Merely scheduling a hold without observing a waiter does not qualify contention; natural concurrent completion may supply the observation instead. |
| 6. Main movement after checkout / before next admission | While #16/#17 hold in already established immutable checkouts, the explicitly authorized TEST owner makes one ordinary unrelated main commit, adding only a dedicated qualification marker and preserving workflows/configs and ancestry. Read back its exact parent/head. Keep #18's already authorized starting commit unchanged. | Original #16/#17 attempt/base/task-ref identities retained through publication; #18 later starts safely from the old admitted ancestor although live main advanced before its reserve/preflight/checkout. Other fine-grained timing boundaries remain the portable deterministic race tests unless actually observed. No product PR merge or self-approval. |
| 7. Cross repository | After the preceding target/slot attempts have known terminal receipts, ready testbed #18 and testbed-2 #3 close together. Collect both namespaces in one window. | Actual automatic Codex overlap across separately bound controllers/Writers on one host, distinct repository IDs/config digests/claim roots/UIDs/cgroups/journal and diagnostic paths, independent native Outcomes. Different Issue numbers do not establish native number-collision coverage; retained historic fixtures are not changed to create a collision. |
| 8. Genuine failed collection / original-attempt recovery | New R explicitly writes/commits its one fixture file, then sets only that file to mode `0600` as its runtime owner before returning success. This must cause an actual ordinary collector unreadability failure, not seeded state. Inspect the resulting real protected/native BLOCKED state. Obtain the retained candidate ID without running trusted Git against worker metadata; the supported importer must independently validate it. Use `inspect-prepublication`, post the exact generated fresh owner authorization, then `recover-prepublication` on the original recorded slot. Run new unrelated I concurrently with this publication-only recovery where slots permit. | Original real successful returned execution, `started` child and `reaped` containment; actual missing collection receipt, native BLOCKED Outcome, preserved bytes/journal, root importer observation, fresh native owner comment/digest, single non-force publication/recovery receipt and supported successor Outcome. Original BLOCKED history stays intact. No new model for R. If failure falls outside the supported prepublication predicates, preserve it and report the exact unsupported recovery dimension. |
| 9. Implementation plus unrelated remediation | First reconcile #16's correct original success evidence. Publish a trusted Task #16 Decision authorizing one operator-controlled TEST fault on its same single file and preserving the original correct Outcome. The parent makes one ordinary descendant/non-force fixture branch commit with a documented incorrect marker byte. A different independent fixture reviewer reads the unchanged canonical byte requirement and exact new head and, only if the mismatch is real, publishes a v4 native CR on that result PR. Ready that PR while independent I's real implementation worker holds. | Honest finding provenance: owner-injected current TEST defect after a previously correct result, not a finding against that historical head or a product self-review. Exact native CR ID/body/hash/head and live owner PR event; immutable new remediation admission/Step, overlapping implementation/remediation processes, separate attributable Outcomes. No fabricated acceptance/finding if the reviewer cannot substantiate the mismatch. |
| 10. Task-head movement | Use #17's own result PR only after its original proof is reconciled. A trusted continuation Decision declares a bounded next single-file update and explicitly authorizes an operator-controlled ordinary descendant ref-movement probe. Ready the Issue through the implementation-continuation path bound to that actual PR/head. During its real worker hold, advance only that fixture branch by one authorized ordinary commit; preserve the worker's starting commit and object bytes. | Exact before/after task ref and original admission; publication safely refuses the changed ref (record actual code), no force push/reset/rebase/foreign change, known containment and native terminal blocker, useful local candidate preserved. Do not claim the changed remote head is the original worker result. |
| 11. Quiesce / drain / resume | Ready two new L holds in one namespace. After both reserve, invoke its fixed root `relay-admission quiesce` with one operation UUID and the actually installed target SHA. Run `drain --timeout 240` while those admitted controllers finish. Once a slot becomes available but the gate remains quiesced, ready new T to observe `ADMISSION_QUIESCED`. Finish drain, run the public installed verification for the unchanged target, then only the same-operation `verified` and `resume` transitions. After T's non-admission is proven, one fresh owner event after resume may execute it. | Gate closes before new reservations; original workers complete/publish while drain releases the Writer lock; rejection has no invented Step/Outcome/inference; drain counts active/unknown and requires matching terminal receipts. Resume requires actual installed/runtime/projection proof, never a caller's fabricated PASS. Known owner work has explicit rejected/fresh-command dispositions. |
| 12. Interrupted worker / cancellation after reserve (last) | New K: after attributed model execution, signal only that exact verified Codex process using a stable pidfd and TERM, allowing the real controller/containment/diagnostic path to finish. Separately use one new cancel fixture: after a protected real reservation, use native Actions cancel, recording whether a child actually started. Run these after successful drain/recovery probes so uncertain state cannot contaminate their proof. | Real failure signals and starttime/UID/cgroup attribution, primary diagnostic/annotations, returned/reaped or explicit unknown status, original journal/claim/Outcome and retained useful progress. No automatic re-inference. Inspect original recovery capabilities; if unknown/uncontained state has no supported recovery, keep it intact, demonstrate the original Task/slot/drain refusal and report that exact blocker. No repair of protected JSON. |

This sequence intends at most fourteen model invocations and no more than two
simultaneously, with other native probes refusing before inference or performing
publication-only recovery. Preserve complete native waiting/canceled records.
Finite worker-pool saturation is the live resource probe; external model/API
quota exhaustion is not deliberately induced. Native queue `max`/overflow
semantics may reuse the unchanged accepted queue proof and exact projection
comparison. A 100/101-run overflow burst is not performed by this plan: if live
overflow itself is required, mark that dimension unqualified and prepare a
separate explicitly bounded native probe within this same Task instead of
claiming an observed overflow. Likewise, mocked rate limits, collision fixtures
and interrupted synthetic roots do not become live evidence.

### Existing entrypoints and exact operation forms

Only the parent performs these authorized external/host actions. Owner User
ready commands use `gh issue edit N --repo REPOSITORY --add-label codex-ready-auto`
or the equivalent PR label endpoint. Cancel uses
`gh run cancel REAL_RUN --repo REPOSITORY`; read complete native run/jobs/events
and comments afterwards. Neither operation uses TEST Admin App identity as a
substitute for the configured owner User. Stale-probe remove/add transitions
must capture both native event IDs and their creation timestamps.

Consumed-admission replay uses the existing
`controller/src/privileged-writer-helper.mjs` broker `admit` branch via the
fixed `/opt/NAMESPACE/relay-writer-controller` wrapper and original configured
runner user's ordinary registered sudo capability. The exact no-new-execution
request is derived from the consumed original claim:

```text
{operation:"admit", runId:ORIGINAL_RUN, target:ORIGINAL_TARGET,
 number:ORIGINAL_NUMBER, route:"auto", transport:"label",
 executionSlot:ORIGINAL_SLOT}
```

The existing-consumed branch returns the stored envelope before fresh admission,
allocation or dispatch. Do not copy a workflow token, forge `SUDO_UID`, call the
model/controller dispatcher, or use this form for a fresh run. Preserve its
private receipt and compare the complete immutable admission digest and process
inventory before/after the one replay.

The trusted TEST lock is exactly the configured `paths.claimRoot` plus
`/publication-v2.lock`, shared by the existing Writer and admission wrappers.
After confirming its existing inode/root ownership/mode, one fixture hold is
`timeout 25s /usr/bin/flock -w 1 EXACT_TEST_LOCK /usr/bin/sleep 15`.
Capture the kernel lock holder/waiter, service attribution and elapsed times.
Never select a lock path from Issue prose, create another mutex, clear a lock,
or save worker stdin, process environments or credential material.

Lifecycle operations use `/opt/NAMESPACE/relay-admission` and the source
`controller/src/admission-cli.mjs` / `admission-control.mjs`:

```sh
/opt/NAMESPACE/relay-admission status
/opt/NAMESPACE/relay-admission quiesce --operation UUID --target INSTALLED_SHA
/opt/NAMESPACE/relay-admission drain --operation UUID --timeout 240
/opt/NAMESPACE/relay-admission status --operation UUID
```

After real unchanged-target installed verification through the existing public
`deploy/relay-deploy.py --phase post-check` path with its actual owner TEST
configuration/consumer root, the same fixed helper accepts
`phase --operation UUID --phase verified --revision INSTALLED_SHA` then
`resume --operation UUID`. This TEST primitive is not proof that the separate
Owner Relay lifecycle GitHub workflow was qualified; that workflow's `stop` /
`resume` operation remains available where the qualified consumer exposes it.
Inside the admitted isolated TEST sandbox, the standing TEST authority also
permits an actual source-role identity, runtime/isolation and exact public
projection verification before these same primitive transitions. Record the
observed proof and its TEST adaptations; do not manufacture a PASS or claim
ordinary public production lifecycle qualification from this scoped path.
No `--phase stop` is invented for `relay-deploy.py`, whose phase list does not
contain stop/resume.

Publication recovery uses the actual configured recovery workflow, generated
from `deploy/workflows/recovery.yml.in`, invoking the installed
`bin/relay-publication-recovery.mjs` entrypoint. Dispatch `inspect-prepublication`
with the original `run_id`, `attempt_id`, exact `candidate_head` and recorded
`execution_slot`. Its bounded stdin operation is
`{operation:"inspect-prepublication",runId,attemptId,head}`. Post only the
generated authorization body as a fresh unedited owner User comment after the
original run and BLOCKED Outcome completed, then dispatch
`recover-prepublication` with the same original values and native
`authorization_id`; stdin is
`{operation:"recover-prepublication",runId,attemptId,head,authorizationId}`.
Inspect the native receipt/original preserved records before any follow-up;
uncertain consumed publication is never retried. A completed read-only replay
may establish suppression without another push or inference.

Task-head/main perturbations are explicitly authorized ordinary TEST owner Git
commits on their exact verified refs, preserving parentage and unrelated bytes.
Use no force, reset, source-owned product PR merge, other historic fixture PR,
credential workaround or model-modified Git metadata. CR publication uses the
current TEST `publish_task_authority` capability with an independently assessed
schema-v4 `change-request` record bound to the actual fixture PR/branch/base/
reviewed head. Finding text names the real TEST seed provenance and unmet
current requirement; it cannot assert independent product acceptance.

No further fixture-ready command follows an uncertain prior model execution.
Report each probe as observed PASS, known safe refusal, unsupported recovery,
unavailable capability, or not run. Core `verify-smoke.mjs` is for normal Issue
success pairs; fault, CR and recovery probes retain their actual event kinds,
original statuses and supported historical/successor Outcome shapes. Do not
alter those records to fit its normal-success assertions.
