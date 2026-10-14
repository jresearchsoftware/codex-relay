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
