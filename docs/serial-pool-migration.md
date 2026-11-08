# Retained SERIAL compatibility

Fresh SERIAL-to-pool migration is retired. Current installation and scheduling
use the managed pool, including capacity 1. The current deployment command does
not create migration reservations, compatibility receipts or target gates,
disable a legacy listener, remove its registration, or resume an unfinished
SERIAL cutover. A nonmanaged installation without a sealed completed receipt
stops for an explicit separately supported owner disposition.

## Compatibility readers

Existing completed cutovers keep their original evidence. The protected
`serial-pool-compat-v1.json` receipt, retired
`serial-pool-transition-v1.json` state, original consumer, source, deployment
snapshot, artifact manifest, old gate, publication records and journals remain
bound to their original bytes, hashes, identities and operation UUID.

The [read-only installed adapter](../deploy/serial_pool_installation.py) verifies
that sealed original context before invoking its original validators. Current
managed Apply and pool reconciliation still verify that the retained old
runner's metadata and service match the recorded binding, its service remains
stopped and disabled, and its native registration remains absent. The
[host adapter](../deploy/serial_pool_host.py) only observes those facts; it has
no stop, disable or DELETE capability. The
[evidence reader](../deploy/serial_pool_transition.py) hashes protected source
and reads seals without publishing or copying state. The historical filename
does not expose a new transition engine. The
[unmigrated-state guard](../deploy/pool_migration.py) prevents unowned SERIAL
artifacts from being adopted as a fresh managed pool.

The versioned [compatibility reader](../controller/src/serial-pool-compatibility.mjs)
classifies original and current physical stores. Only the receipt's sealed
original run IDs, attempt IDs and envelope hashes select the original graph.
The [program adapter](../controller/src/serial-pool-program.mjs) invokes the
fixed original Writer, manual Outcome or recovery entrypoint with its original
consumer and Unix identity. Original authority, candidate, admission and
recovery authorization still pass the original validators. Historical
admission and new execution from a retained record remain denied.

The original `admission-v1.json` stays sealed and closed. Current managed
admission uses `admission-pool-v1.json` and `publication-pool-v1` where the
receipt selects those paths; an installation without a receipt retains its
ordinary managed gate/store paths. Repository namespaces, current lifecycle
UUIDs, physical pool state and exact old-attempt publication stay separate.
A later ordinary managed lifecycle operation does not reactivate the original
cutover or change its receipt.

Do not edit historical gates, copy old records into current stores, replace
consumer digests, delete receipts/source bundles or reactivate the stopped old
listener. Unknown ownership, changed seals and mixed stores remain visible
blocking evidence. Preserving this compatibility grants no new execution,
deployment, merge, closure or cleanup authority.

## Regression coverage and evidence limits

[Retained evidence tests](../deploy/tests/test_serial_pool_evidence.py) exercise
native protected bytes and pre-execution seal rejection.
[Completed-cutover/current-pool tests](../deploy/tests/test_serial_pool_git_installation.py),
[read-only host tests](../deploy/tests/test_serial_pool_host.py) and
[bounded transport tests](../deploy/tests/test_serial_pool_transport.py) cover
later desired configurations, current digest/gate binding, absent legacy
registration, retired migration actions and unchanged historical evidence.
The controller compatibility/program/admission suites preserve original/current
reader selection and exact-attempt recovery. These source tests do not establish
new installed qualification or authorize PROD mutation. The
[managed-pool qualification contract](concurrency-scheduling.md#shared-managed-pool)
and [TEST authority](execution-policy.md#test-environment-authority) retain their
separate boundaries.
