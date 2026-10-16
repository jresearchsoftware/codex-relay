# Task 103 Step 5 managed pool qualification

These are Task-local preparation and readback tools for Decisions
[6194778463](https://github.com/jresearchsoftware/codex-relay/issues/103#issuecomment-6194778463)
and [6194977824](https://github.com/jresearchsoftware/codex-relay/issues/103#issuecomment-6194977824),
under the actual protected manual admission. They do not allocate a Step,
authenticate, publish, register a runner, alter services or invoke a model.
The owner manual execution performs authorized TEST operations. They do not
edit or reinterpret Step 3 evidence.

## Current frontier and private setup

The initial read-only October 15 inspection found both dedicated TEST
installations at `cc7de20b820fde999127fefc4f10425d621a180a`, with their old
distinct-UID primary/second runners active and both admission gates open with
`active: []` and `unknown: []`. This is historical setup evidence, not the new
candidate's qualification. Refresh it immediately before mutation.

The existing SSH channel is Debian WSL to root at `195.201.83.241`; preserve
its known-host verification. The two protected configurations are
`/etc/codex-relay-test/consumer.json` and
`/etc/codex-relay-test-two/consumer.json`. Only their exact repository bindings
are permitted: `jresearchsoftware/codex-relay-testbed` (1407614568) and
`jresearchsoftware/codex-relay-testbed-2` (1409883950). Credentials stay outside
this repository, workers and evidence exports. Existing private config and key
locations belong in the manual execution's private setup, not tracked inputs.

The native source/validation root for this phase is
`/home/hortonolite/codex-relay-task103-step5-01a1400f`. Use the already qualified
private Node 22 and Rust 1.90 toolchains. Their presence does not qualify TEST
installation or account quota. The prior scoped stager hardcodes the old
primary/second topology; do not run it unchanged for a managed pool.

The new `stage-test-installation.py` is a pure, explicitly bounded adapter of
that unchanged Step 3 preparation function. It requires its exact old source
invariants before replacing the two-slot check and the namespace-specific
runner-user check. `plan.json` records both stager hashes, all copied-template
deltas, the exact Git archive and Reviewer binary hashes, the guard and execution
wrapper hashes, and lifecycle limits. It preserves the original per-namespace
Codex user, uses common General Runner user `relay-test-general-runner`, and
creates only the configured physical members of `relay-test-managed-pool`.

After the parent commits the exact candidate and builds the locked Reviewer,
prepare both bundles locally (no remote operation occurs):

```sh
SRC=/home/hortonolite/codex-relay-task103-step5-01a1400f
python3 "$SRC/docs/evidence/task103-step5/stage-test-installation.py" \
  --source-root "$SRC" --revision "$CANDIDATE" --consumer-revision "$TESTBED_MAIN" \
  --prior-config /tmp/task103-scoped-test-one-cc7de20/configuration.json \
  --admin-key-file "$ADMIN_KEY_FILE" --admin-app-id "$ADMIN_APP_ID" \
  --admin-installation-id "$ADMIN_INSTALLATION_ID" --capacity 2 \
  --reviewer-binary "$REVIEWER_BIN" --cargo-version "$ACTUAL_CARGO_VERSION" \
  --output /PRIVATE/NEW-step5-stage-one
python3 "$SRC/docs/evidence/task103-step5/stage-test-installation.py" \
  --source-root "$SRC" --revision "$CANDIDATE" --consumer-revision "$TESTBED_TWO_MAIN" \
  --prior-config /tmp/task103-scoped-test-two-cc7de20/configuration.json \
  --admin-key-file "$ADMIN_KEY_FILE" --admin-app-id "$ADMIN_APP_ID" \
  --admin-installation-id "$ADMIN_INSTALLATION_ID" --capacity 2 \
  --reviewer-binary "$REVIEWER_BIN" --cargo-version "$ACTUAL_CARGO_VERSION" \
  --output /PRIVATE/NEW-step5-stage-two
```

`ADMIN_KEY_FILE` is the existing Windows-private PEM's `/mnt/c/.../*.pem` path;
the preparer copies only the path binding and never opens that file. Use actual
read-back App/installation IDs and consumer main SHAs. The adjacent
`NEW-step5-stage-one.owner-config.json` and corresponding second owner config
are private inputs for the ordinary owner CLI, not product source.

Review each bundle's `plan.json`, refresh original admission/containment facts,
then the parent stops only the verified TEST services. Copy each complete bundle
to a new root-private host directory and run its `./run-stage.sh` once. The
generated guard also requires all shared pool services stopped, reads the
original installed admission status, and refuses active/unknown attempts or a
non-open lifecycle. Only then does it preserve old config/manifests, claims and
original per-slot journal directories under
`/var/lib/<namespace>/task103-step5-retained-local-state/before-CANDIDATE`.
Directory renames preserve bytes and metadata; no journal or Outcome is edited.
An interrupted install requires inspection, not automatic reuse of this adapter.

The wrapper verifies that both host mount targets already exist as protected
regular files **before** launching its private systemd mount namespace. It
never creates `/usr/bin/node` or `/usr/bin/bwrap`. New persistent tool drop-ins
target only the shared TEST pool units. Existing dedicated Reviewer drop-ins
remain in place. The bundle installs physical runner software and unit files
without registration/activation. Registration, tokens and activation remain
the ordinary trusted owner Apply operation; this scoped installation does not
prove standalone bootstrap, upgrade or busy lifecycle behavior.

The TEST services use private Node/bwrap overlays on a host with a shared root
filesystem. The October 15 readback still found the historical host-visible
root-owned `0644`, zero-byte `/usr/bin/bwrap` mount target. Do not create another
global tool target, install a global package or call that whole-host
noninterference. Dedicated namespace resources and TEST-only runner/group
targets require positive verification before each mutation.

## Prepare genuine fixture authority

Run from the exact candidate source with Node 22:

```sh
node docs/evidence/task103-step5/prepare-smoke.mjs charters /PRIVATE/NEW-fixtures 120
node docs/evidence/task103-step5/prepare-smoke.mjs decision /PRIVATE/same-a.observed.json /PRIVATE/same-a.decision.json 120
```

The first command emits new one-file charters for `same-a`, `same-b`, `cross-a`
and `cross-b`. After ordinary Issue creation, the observed input to the second
command is `{variant, issue: COMPLETE_NATIVE_ISSUE, repository:
COMPLETE_NATIVE_REPOSITORY, main: COMPLETE_NATIVE_MAIN_COMMIT}`. Publish its
`{repository,record}` with the current TEST `publish_task_authority`, then
read back the exact trusted Decision and body digest. No ready label exists
yet. Actual owner **User** ready events, not TEST App events, launch fixtures.
Writer alone resolves the real run/attempt/Step. Reuse no consumed old fixture.
The bounded profile remains `gpt-6.1-sol / medium / Subagents Off`; actual model
identity is `UNAVAILABLE` without runtime metadata.

## Install and read back one physical pool

Use the new candidate's admitted TEST installation and pool Apply path. Preserve
old TEST state/evidence before replacing the idle legacy topology. One pool
identity is `environment.generalRunner.name`; both repository installations
refer to that same identity and capacity. Start with capacity 2. One pool owns
the physical registrations and services, while each repository retains its
separate controller/Writer and immutable per-attempt authority. Task 85's
generalized Writer repository selection is not required or inferred.

The collector expects protected consumer `generalRunnerPool.desiredCapacity`
and the stable 32 internal `executionSlots` (`primary`, `pool-2` through
`pool-32`). Only the desired number of physical runners is active. Physical
names are the pool name, then `<pool-name>-2`, etc.; service names are
`<pool-name>-pool-1.service`, etc. It checks installed source through each
`/opt/<namespace>/current` exact release and protected `deployment-config.json`.
The scripts do not accept caller-selected privileged launcher paths.

Through direct local TEST Admin App authentication, collect **all pages** of
the exact group's metadata, selected repositories and runners, then create a
private `native-pool.json` with:

```text
{
  native_reads_complete: true,
  group: COMPLETE_NATIVE_GROUP_OBJECT,
  repositories: ALL_NATIVE_SELECTED_REPOSITORY_OBJECTS,
  runners: ALL_NATIVE_GROUP_RUNNER_OBJECTS
}
```

Preserve original API readbacks and command provenance privately. Restrict the
group to the two exact TEST repository IDs and exact trusted routing/recovery
workflow refs on `refs/heads/main`; no public/all-repository or candidate-ref
access. A default `gh` user token is not proof of TEST Admin App access. Verify
the actual App/installation and runner read permissions before mutation. Do not
put token bytes in this JSON, command logs or workflow inputs. Native group
metadata and API pagination completeness remain operator attestations.

Preserve historical TEST registrations when useful. The complete group readback
may include them only when they are offline, not busy, outside the managed pool
name and without its scheduling label. The collector and verifier reject an
extra eligible physical member. This proves the active pool's bound without
deleting historical registrations merely to fit an expected inventory count.

## Collect actual processes and protected records

Copy the exact source directory structure to the TEST host so the Step 5
collector can import its unchanged sibling Step 3 collector. Place the sanitized
native pool readback below a root-private directory. `CANDIDATE` below is the
actual committed source SHA installed on both TEST namespaces, not a planned SHA.

```sh
python3 docs/evidence/task103-step5/collect-host.py observe \
  --candidate "$CANDIDATE" --native-pool /root/PRIVATE/native-pool.json \
  --duration 900 --output /root/PRIVATE/NEW-observation

python3 docs/evidence/task103-step5/collect-host.py snapshot \
  --candidate "$CANDIDATE" --native-pool /root/PRIVATE/native-pool.json \
  --run codex-relay-test:ACTUAL_RUN_ID \
  --run codex-relay-test-two:ACTUAL_RUN_ID \
  --output /root/PRIVATE/NEW-terminal-snapshot
```

Start the bounded collector before owner ready events and let it complete.
Use a fresh window after capacity or protected config changes: changing config
inside a closed overlap window makes its completeness claim fail. The collector
reads no credential file or transcript. It reads only explicit sandbox path
values from the actual process environment, discards all other entries without
exporting them, and checks actual directory device/inode/UID/GID/mode inside the process
mount namespace. Protected per-slot configuration binds the runner UID, runtime
UID and work-group GID. Sandbox directories may be runner-owned or runtime-owned;
their private `0770`/`02770` permissions and the observed process primary and
supplementary groups must prove owner or group read/write/search access. Distinct
sandbox paths cannot share an inode, except `HOME` and `CODEX_HOME` naming the
same path. No raw environment or argv is stored. It retains only bounded
machine fields from original claim/journal records; synthetic fixture records
are refused. Missing attribution, mutable config, unsafe/missing protected
parents or incomplete source reads become gaps, not invented observations.

The original `6883490` observation window failed with `SANDBOX_DIRECTORY_OWNER`:
its collector incorrectly required runtime ownership of runner-created shared
work directories. Preserve that failed window unchanged. This correction does
not repair its observations or qualify its overlap; use a fresh complete window
and separately admitted new fixture attempts after installing the corrected head.

For native Issue events/comments, PR comments and jobs use complete paginated
reads. The jobs input is `{total_count: N, jobs: ALL_NATIVE_JOB_OBJECTS}` after
combining all pages without dropping the total. Select the actual execution
job's observed ID, not a skipped companion. Inspect native annotations and
warnings separately; a successful job does not prove that none occurred.

Create the verifier manifest from observed values only:

```text
{
  collected_by: "owner-local-manual", native_reads_complete: true,
  candidate: ACTUAL_INSTALLED_CANDIDATE,
  installed: "NEW-observation/installed.json", native_pool: "native-pool.json",
  host_observations: "NEW-observation/protected-host-observations.json",
  execution_inventory: "NEW-observation/protected-execution-inventory.json",
  cases: [{
    name: "same-a", repository: "jresearchsoftware/codex-relay-testbed",
    task: OBSERVED_ISSUE, run_id: OBSERVED_RUN, job_id: OBSERVED_JOB,
    owner: VERIFIED_OWNER_LOGIN,
    routing_workflow: VERIFIED_ROUTING_PATH, base_branch: "main",
    writer_actor: {id: OBSERVED_ID,login: "jresearch-relay-test-writer[bot]",type: "Bot"},
    reviewer_actor: {id: OBSERVED_ID,login: "jresearch-relay-test-reviewer[bot]",type: "Bot"},
    files: {issue: "same-a.issue.json", events: "same-a.events.pages.json",
      comments: ["same-a.issue-comments.pages.json", "same-a.pr-comments.pages.json"],
      run: "same-a.run.json", jobs: "same-a.jobs.json", pr: "same-a.pr.json",
      claim: "NEW-terminal-snapshot/codex-relay-test-RUN.claim.json",
      journal: "NEW-terminal-snapshot/codex-relay-test-RUN.journal.json"}
  }, ...],
  pairs: [{kind: "same-repository",cases: ["same-a","same-b"]},
          {kind: "cross-repository",cases: ["cross-a","cross-b"]}]
}
```

```sh
node docs/evidence/task103-step5/verify-smoke.mjs /PRIVATE/manifest.json /PRIVATE/NEW-receipt.json
```

This reuses Step 3's exact current-v4 native authority/actors, immutable
admission, real native Codex usage, original journal/claim, distinct terminal
Writer Outcome and exact open result PR head checks. It additionally verifies
actual native job runner ID/name/group membership in one physical pool, same
non-root model UID, separate cgroups/checkouts and actual sandbox directory
inodes. At least two identical scan timestamps contain both real Codex processes;
an observation gap is not bridged. Global observed occupancy includes all
attributed TEST models across both repositories. Discrete samples do not prove
account quota, a continuous resource allocation bound or simultaneous remote
GPU/network computation. A receipt does not imply independent acceptance.

## Additional live lifecycle probes

Preserve complete native/protected readbacks around each bounded operation in
the existing private qualification output, rather than editing protected
journals or making a new task ledger. The overlap receipt above deliberately
does not label these separate dimensions PASS:

| Probe | Real operation and required observation |
| --- | --- |
| Registration-token-free Apply / idempotence | Invoke owner Apply using only the protected TEST App configuration. Record native runner IDs, pool manifest, unit bindings and count before/after. Repeat once after inspecting success: same IDs/count and no per-runner token input. |
| Capacity increase | Apply 2 to 3 once; observe exactly one new physical registration/service shared by both repo bindings. Three is a global count, not three per repository. Restore a closed config window before collecting overlap. |
| Busy contraction | While a genuine fixture occupies the surplus member, Apply 3 to 2. Observe retained busy process/native job, delayed retirement and no task loss/reinference. After its terminal Writer result, perform the supported reconciliation and verify only that exact surplus registration/service retires. A deliberate active-job stop is excluded. |
| Pending / cancellation | Hold configured capacity with independent real Tasks and ready one additional bounded Task. Observe waiting, subsequent native execution and original event binding. Cancel a separate queued Task before reserve; inspect native terminal status and complete protected absence. Use the supported native cancellation after reservation and observe exact child containment/terminal Outcome. |
| Original-attempt recovery | Use the supported original-run recovery interface for a real retained interrupted/cancelled attempt. Preserve original run/Step/admission/slot, one invocation and one canonical Outcome; inspect the publication receipt before any retry. Never seed an uncertain journal or rerun model inference for evidence. |
| Upgrade / drain | On dedicated TEST only, exercise the candidate's supported lifecycle with active and idle pool state. Verify admission/drain behavior, unchanged registration identities when retained, original-attempt recovery and no invisible second pool. |
| Optional repository identity | A separate protected repository runtimeUser override may use the same pool. Collect actual UID and functional permissions without changing Task-controlled identity. This is a separate optional identity probe; the default pair above must still demonstrate a shared UID. |

Report exact unavailable live capability, warning surfaces or protected-boundary
limitations. No source test, old distinct-UID overlap or mock fulfills these
live observations. PROD adoption, merge, release and closure remain separate.

## Offline checks

```sh
node --test docs/evidence/task103-step5/offline-check.mjs
python3 -m unittest discover -s docs/evidence/task103-step5 -p 'test_*.py' -v
```

These use deterministic in-memory records and path-only environment sentinels.
They exercise shared UID acceptance and rejection of native identity changes,
wrong source/group/access, missing native usage, duplicate publication/inference,
unobserved intervals, directory aliasing and omitted occupancy. They are not
native qualification evidence.

When namespace two intentionally retains `relay-test-two-codex`, mark its
cross pair `identity_mode: "repository-override"`. The verifier then requires
the two actual UIDs to differ and reports that specific optional mapping probe.
It does not relabel it shared-default-UID evidence. Omitted `identity_mode`
means `shared-default` and strictly requires the same configured non-root UID.
The same-repository default pair always keeps that shared-default requirement.
