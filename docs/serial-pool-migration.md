# SERIAL to managed pool migration

An external owner Apply or authorized upgrade can move a registered, safely
idle SERIAL installation to managed capacity. The transition keeps original
admission and publication readers under their original configuration while new
work uses the pool configuration. It does not rewrite historical digests or
authorize deployment outside the admitted environment. Source support and
synthetic regression evidence remain separate from installed qualification.

Use the existing [owner deployment command](../deploy/README.md#inputs-and-invocation)
with the same namespace, Unix users, paths and owner policy, adding the managed
pool configuration and selected exact product revision. Capacity 1 and 2 are
explicit regression cases. The installed runner cannot stop itself for this
handover; run the command from the external owner machine where its existing
SSH and pool App references are available. No new migration command, token
copy, record repair or runner-group permission change is required.

## Compatibility readers

These bindings serve different purposes. A deployment snapshot byte hash is not
the execution consumer digest, and neither replaces an authority body hash or an
attempt's immutable admission digest.

| Original evidence | Current readers and boundary | Transition requirement |
| --- | --- | --- |
| Release `deployment-config.json`, artifact manifest and `.relay-source.json` | [`installed_config.verify`](../deploy/installed_config.py) checks protected paths, exact release/current identity, original consumer revision and `deploymentConfigSha256`. [`pool_eligibility`](../deploy/pool_eligibility.py) discovers protected peer evidence; [`clean_reinstall`](../deploy/clean_reinstall.py) reads original release evidence for continuation. | Preserve original snapshot bytes and manifest bindings. A new release/configuration must not rewrite old release evidence or represent it as the new configuration. |
| Installed `consumer.json` and execution consumer digest | [`consumerDigest` and `resolveExecutionConsumer`](../consumer/consumer-config.mjs), loaded once by [`consumer.mjs`](../consumer/consumer.mjs). Managed desired capacity is excluded from its digest; identities, paths and the derived resource-slot topology remain bound. | SERIAL to managed topology changes the digest even at capacity 1. Capacity-only invariance in an already managed installation is insufficient proof of migration compatibility. |
| `admission-v1.json`, operation UUID, target and first service snapshot | [`createAdmissionControl`](../controller/src/admission-control.mjs) requires the configured digest and original operation, accounts for retained attempts, and retains the first activation intent. [`admission-cli`](../controller/src/admission-cli.mjs) constructs it from the loaded consumer. | Close/drain the original gate with its original configuration. Preserve its binding and first snapshot; installing the new consumer before resolving the old reader boundary cannot make that gate valid. |
| Installed lifecycle snapshot helper ABI | [`upgrade-lifecycle-snapshot.yml`](../deploy/ansible/tasks/upgrade-lifecycle-snapshot.yml) invokes the installed helper before replacement; activation and validation consume retained intent. The older helper accepted exactly `reviewer`, `production`, `general`. | Do not send derived managed slot keys to that old ABI. The existing absent-manual-socket compatibility projection only removes `manualOutcome`; it does not remove additional slot keys. Preserve present socket intent and the original first snapshot through recovery. |
| Protected Writer attempt envelopes, immutable admission/Request and authority references | [`validateEnvelope`](../controller/src/execution-contract.mjs) validates against the loaded digest/topology. [`createPublicationBroker`](../controller/src/publication-broker.mjs) checks the retained envelope digest in both bound operations and existing-attempt admission. [`createAttemptStore`](../controller/src/attempt-store.mjs) preserves records but does not supply digest compatibility. | Keep original bytes, hashes, run/attempt/Step, repository and slot bindings readable through an explicitly bound original configuration. Do not accept arbitrary historical digests or weaken ordinary envelope validation. |
| Controller journal, retained candidate, publication intent and recovery receipt | [`publication-recovery`](../controller/src/publication-recovery.mjs), [`prepublication-recovery`](../controller/src/prepublication-recovery.mjs), [`manual-outcome`](../controller/src/manual-outcome.mjs) and the Writer broker bind original authority, result and exact candidate. Admission drain also reads terminal/journal evidence. | Recovery must continue the original attempt and publication, including its original slot and owner authorization where required. No new inference, replacement attempt, relabelled Step, rewritten Outcome or duplicate publication. |
| General Runner registration, service and protected pool state | [`serial_pool_host`](../deploy/serial_pool_host.py) binds the original native registration, protected unit, runner metadata and actual process state. [`managed_pool`](../deploy/managed_pool.py) owns pool binding, durable mutation reservations and reconciliation. [`managed_pool_transport`](../deploy/managed_pool_transport.py) qualifies external authority before lifecycle and again before pool mutation. | A stopped service or renamed runner is not migration proof. Bind the original registration and safely idle process state before an authorized handover; preserve conflicting/unknown state rather than adopting it as a fresh pool. |

The versioned [compatibility reader](../controller/src/serial-pool-compatibility.mjs)
classifies the complete original and current physical stores before selecting a
record. Only sealed original run IDs, attempt IDs and envelope hashes select the
original graph. The [program adapter](../controller/src/serial-pool-program.mjs)
starts its fixed Writer, manual Outcome or recovery entrypoint with its original
consumer and Unix identity. It strips only the new transport slot selector;
original envelopes, authority, candidate and recovery authorization still pass
the original validators. Direct historical admission and inference are denied.
Ordinary current envelope validation remains unchanged.

## Apply and recovery sequence

1. **Read and qualify before mutation.** Under the existing deployment locks,
   establish the exact original installed release/configuration, registration,
   namespace and prospective pool binding. Retain current group/repository/ref
   eligibility checks and owner App permission qualification. Unknown ownership,
   ambiguous registration or a conflicting pool binding remains a visible stop.
2. **Quiesce and drain through the original installation.** Use its supported
   helper, digest and snapshot ABI. An idle remote runner alone does not prove
   that the model, controller, publication or containment boundary is resolved.
   Preserve original activity intent and operation identity before replacement.
3. **Install the bounded transition.** Establish the new managed configuration
   and physical capacity without rewriting old snapshots, admissions, journals
   or native records. Preserve original-run readers and recovery while ordinary
   new admissions use the new configuration. The previous SERIAL listener and
   the resulting pool must not create unintended simultaneous capacity.
4. **Recover by observation.** Retain sufficient durable evidence before each
   uncertain mutation. On interruption or lost acknowledgement, reobserve exact
   local and remote identities before continuing the same operation. Reapply
   must not duplicate registration/removal, reinterpret failed activation as
   original intent, or clear an unknown attempt to make progress.
5. **Validate before reopening.** Prove the installed configuration, physical
   registrations/services, retained original readers and expected lifecycle
   state. A failure keeps the existing recovery boundary visible. Ordinary
   Apply completion is separate from independent exact-head acceptance and
   real installed TEST qualification.

[`serial_pool_transition`](../deploy/serial_pool_transition.py) reserves the
operation before mutation in the original claim root's
`serial-pool-transition-v1.json`. Its phases are `reserved`, `prepared`,
`stop-intent`, `stopped`, `target-ready`, `remove-intent` and `retired`.
The private state binds the exact original native runner ID, protected unit and
registration hashes, repository, namespace, prospective configuration, target
revision and original operation UUID. An inactive but enabled old listener is
disabled under the same stop intent. A restarted listener fails the stopped
proof before backend or retirement work. No force termination is used.

After the original gate has drained and retained its first service snapshot,
the transition preserves the original source, private deployment snapshot and
manifest under `/opt/<namespace>/serial-compat-v1/<original-revision>/`.
It preserves the original consumer at `/etc/<namespace>/serial-consumer-v1.json`
and publishes the bounded public `/etc/<namespace>/serial-pool-compat-v1.json`
receipt. Same-revision Apply therefore cannot overwrite the original private
snapshot or source reader context. Declared deployment `compatibilityLinks`
retain their exact absolute link bytes and protected canonical source targets;
arbitrary source symlinks are rejected. Keep both the retained bundle and the
original canonical release. This migration does not authorize their cleanup.

The original `admission-v1.json`, `publication-v2` records and attempt journals
stay under their original digest. The original gate remains closed in
`applying` once sealed. New admission uses `admission-pool-v1.json` and
`publication-pool-v1` under the same existing Writer lock. Its independently
observed first snapshot records actual target service intent and peer listener
state. The old three-key helper never receives managed slot keys. A pending
owner-local manual attempt retains its original publication path; unresolved
host execution, unknown containment or malformed records still block draining.

After backend installation, pool reconciliation and runtime/activation identity
proof, retirement reobserves the exact original registration. Its durable
`remove-intent` permits an absent registration only for that same reserved
removal, so a lost DELETE response is inspected rather than repeated blindly.
The stopped old service and its protected metadata remain as retained evidence;
it is not an enabled orphan. Only the verified new gate is resumed.

On failure, retain the command's log and inspect the protected transition and
gate status using the installed admission helper. Reapply the same owner
configuration and exact target from the external owner command. The command
discovers and reuses the retained UUID; a conflicting explicit recovery UUID or
changed target/policy stops. If backend installation already completed, recovery
reconciles capacity, runs a read-only installed check, completes retirement and
resumes the same operation without applying the backend again. If retirement
already completed, the same final check and gate completion remain available.
Later ordinary pool lifecycle operations may use their own UUIDs.

Do not edit the historical gate, copy old records into the new store, replace
consumer digests, delete reservation/receipt files, rename the old registration,
or manually rerun an uncertain DELETE. Unknown ownership, active workers,
busy registration, unsafe filesystem metadata, missing original context,
changed owner policy and failed group workflow trust remain explicit stops.
The implemented recovery direction is forward completion; the command does not
reactivate the sealed SERIAL gate after cutover or invent a rollback admission.

## Regression coverage and evidence limits

The local Linux regression composes real configuration, migration,
admission, lifecycle and Writer modules in a synthetic filesystem. Separate
processes load SERIAL and managed configurations because consumer constants are
resolved at module import. External GitHub/Codex/package and systemd transport
may be substituted; replacing migration/preflight/lifecycle with canned success
receipts would remove the compatibility boundary being tested.

The composed cases and adjacent regressions include:

- [`test_pool_migration.py`](../deploy/tests/test_pool_migration.py) currently
  proves only rejection and preservation for active/inactive/unknown/interrupted
  SERIAL evidence. [`test_pool_eligibility.py`](../deploy/tests/test_pool_eligibility.py)
  supplies protected release/snapshot/manifest fixtures.
- [`test_installed_config.py`](../deploy/tests/test_installed_config.py) exercises
  the real configuration validator and native protected files.
  [`test_installed_config_publication.py`](../deploy/ansible/tests/test_installed_config_publication.py)
  covers exact private snapshot publication and interruption evidence.
- [`test_upgrade_lifecycle_activation.py`](../deploy/ansible/tests/test_upgrade_lifecycle_activation.py)
  runs actual Ansible lifecycle tasks with a real gate and a strict old
  three-component helper fixture. The combined old-helper/managed-slots
  migration cases are in
  [`test_serial_pool_lifecycle_activation.py`](../deploy/ansible/tests/test_serial_pool_lifecycle_activation.py),
  including first-snapshot replay, protected receipt checks and target peer PID
  continuity.
- [`test_managed_pool.py`](../deploy/tests/test_managed_pool.py) covers lost
  registration/removal/label responses and partial markers using real durable
  pool state and fresh-process reapplication.
  [`test_managed_pool_reinstall.py`](../deploy/tests/test_managed_pool_reinstall.py)
  supplies shared-listener preservation and same-operation final-resume cases.
- [`controller/test/fixture.mjs`](../controller/test/fixture.mjs) supplies a real
  synthetic Git remote and Writer broker.
  [`publication-recovery.test.mjs`](../controller/test/publication-recovery.test.mjs)
  and [`admission-control.test.mjs`](../controller/test/admission-control.test.mjs)
  supply original-attempt locks, retained receipts, first activity snapshot and
  fail-closed drain cases. The new compatibility suites compose these contracts
  across the configuration transition;
  successful recovery under one unchanged digest does not establish migration.

[`test_serial_pool_installation.py`](../deploy/tests/test_serial_pool_installation.py)
loads the genuine original Git archive and runs its original admission helper,
digest and envelope validators in private Linux mount/network/PID namespaces.
It covers capacities 1 and 2, same-revision snapshot/source preservation, mixed
terminal/manual/partial records, lost removal acknowledgement, reapplication,
new gate opening and original closed gate preservation. Core, host and transport
suites cover interruption and negative ownership/state boundaries. Controller
compatibility, program and admission suites exercise separate original/current
graphs, full store classification and fixed historical publication routes.
The public owner-flow suite covers ordering and same-operation completion.

[`test_pool_preflight.py`](../deploy/tests/test_pool_preflight.py) substitutes
the whole pool transport; the public CLI fixture in
[`test_deployment.py`](../deploy/tests/test_deployment.py) substitutes admission
and backend responses. These remain useful ordering tests, but cannot establish
the composed transition described above.

## Installed qualification boundary

The [installed runtime proof](../deploy/ansible/tests/installed_runtime_proof.py)
uses private namespaces, real Unix identities, sudo and product templates. Its
private PID 1 is Python, and it stages rather than activates systemd sockets;
it does not establish live migration, service activation or model overlap.

Actual isolated TEST evidence must observe the registered SERIAL starting
state, migration and safe interrupted/reapply behavior, original-run recovery,
and the resulting shared pool at the exact tested candidate. Parallel claims
also require simultaneous automatic model processes, bounded occupancy,
attributable terminal Outcomes and capacity reconciliation, including same-UID
isolation. Earlier distinct-UID overlap or local fixture success is insufficient.
Use the existing [pool qualification contract](concurrency-scheduling.md#shared-managed-pool)
and [TEST Environment Authority](execution-policy.md#test-environment-authority);
neither this design nor a TEST result establishes PROD deployment or independent
acceptance.
