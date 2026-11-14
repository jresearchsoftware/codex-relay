# Task 253: first-install and unchanged-input Apply qualification

This records evidence for admitted manual Step 2, `run-43578199509`, under
[Task 253](https://github.com/jresearchsoftware/codex-relay/issues/253) and
[PR 254](https://github.com/jresearchsoftware/codex-relay/pull/254). The accepted
starting source is `feefb6cf13daaf1c027e24d0a51fe834d68d26ba`. Source acceptance,
installation and Task closure remain separate. No PROD Apply is authorized.

The owner's later trusted [purpose Decision](https://github.com/jresearchsoftware/codex-relay/issues/253#issuecomment-6877201325)
requires eligible small code-only changes to complete in **tens of seconds
end-to-end**, including preparation and necessary checks. A roughly 10–12%
reduction from 643 seconds does not meet that goal. Upgrade correctness and
security remain mandatory; equivalent current-input/drift proof can replace a
full Ansible traversal. This purpose amendment changes neither the original
Step/admission binding nor protected operational boundaries.

## Qualified native local milestone

The complete public TEST code-only Apply from `cb0e30a2...` to
`a0e03ab721e65d301c58398844b9b3f325c5bbb5` passed in **95.960380 s**, including
argument preparation, a new official pinned reference, all required checks and
final readback. All six observed TEST/pool/PROD service PID/start identities
were preserved, all 32 actual routes passed, and the exact installed Git pair
was verified. This is one actual result below 100 seconds, without extrapolating
a latency guarantee or PROD improvement. The accepted-source baseline below
was 643.395 s on the same TEST target/capacity with all 32 routes; these are
different exact source pairs with unchanged effective inputs in each operation.
The observed reduction is **85.1%**. See
[native Apply evidence](task-253-native-apply-a0.json) and
[non-overlapping timeline](task-253-native-timeline-a0.json).

Both baseline and candidate ran the public installer frontend on the same
remote Debian host as root with `--connection local`; WSL supplied preparation
and SSH launch. The change from accepted Ansible-local command transport to
qualified native-local transport is part of this product change. No WSL-to-host
frontend relocation is credited as product savings. See the retained-driver
[transport facts](task-253-performance-transport.json).

| Corrected installed case on `a0e03ab7...` | Complete E2E | Result |
| --- | ---: | --- |
| Same-pair no-op | 31.583764 s | Native verify; receipt and all seven managed bindings unchanged |
| README-only config commit | 27.340949 s | Native provenance; exact same JSON bytes, only manifest/receipt promoted |

Both cases acquired their own fresh required reference, retained all six active
process identities and avoided full-site traversal. The task-only early fallback
guard did not trigger and forced no proof. README commit
`bb76ead22b44e5866b395592561e33d84872abbd` retains exact JSON blob
`66933276a48270f2845a6d28ac88bcc84b395c9d` from the measured Apply's configuration.
See [no-op evidence](task-253-final-noop.json) and
[README-only evidence](task-253-final-readme.json).

The public installer frontend runs on the remote Debian TEST host; the separate
WSL validation checkout has a different kernel instance, CPU model and native
filesystem. WSL provides Git setup and SSH transport for the installed cases.
See [execution-resource facts](task-253-execution-resources.json). Remaining
full local candidate checks, bounded original-operation recovery, ordinary
recovery after genuine SIGTERM and final policy/restore qualification passed
below. Independent source acceptance remains separate.

| Additional actual TEST case | Complete E2E | Verified result |
| --- | ---: | --- |
| Bounded original-operation recovery | 507.239631 s | Original UUID, byte-equal original backend archive, all 32 probes |
| Genuine native stop/self-SIGTERM | 71.394251 s expected failure | Closed same-UUID frontier; actually stopped TEST Runner |
| Ordinary same-pair signal recovery | 492.454811 s | Same UUID, stopped Runner restored, all 32 probes |
| Actual policy JSON change | 511.478978 s | Full reconcile, owning policy updated, all 32 probes |
| Byte-exact original JSON restoration | 519.826053 s | Full reconcile, original bytes/blob/hash and policy restored |

The recovery/policy rows deliberately exercise the full path and are separate
from eligible code-only performance. Final installed product is `c94c20c1...`,
with configuration `fdef308c21aa9e7910ef4fe6c9bcb9ecffcf5df9`. All runtime/test
source code is frozen at `20f0fc70...`; later commits contain qualification
documentation/data only. No installation of a later documentation head is claimed.

## Recovery qualification

The subsequent native cutover to `ee52cff0490ab6d09727a7ce9bd1b79490cc7a82`
encountered a task-observer exception at post-cutover proof entry. The observer
incorrectly treated the cooperative TEST claim marker as a secret file: that
marker intentionally permits the TEST group to write. No marker mode or inode
was changed. The planned Runner stop/SIGTERM did **not** execute. All six service
identities remained active and unchanged. The original operation
`af3cf6ac-78db-466c-9024-a3d4e1ea334d`, exact target/config receipt, first activity
snapshot, source archive and journal remain preserved with closed admission and
the matching `apply / RECOVERY_REQUIRED` backend. See the
[interrupted frontier](task-253-nativefault-frontier.json).

The ordinary public same-pair recovery, with the observer fully disabled,
refused before backend mutation. Its normal `old-installation.json` snapshot is
699,095 bytes, within the producer's 32 MiB contract but beyond both legacy
retirement reader/parser limits of 64 KiB. The snapshot is root-owned, mode
0600, regular and singly linked, with the exact original UUID and target; it
has no predispatch bridge. The bridge classifier nevertheless reads the whole
snapshot through the small legacy reader. See the
[read-only classifier trace](task-253-native-recovery-classifier.json) and
[snapshot facts](task-253-native-recovery-snapshot.json). This is a product
producer/consumer defect, not a successful same-pair recovery. The correction
opts only this snapshot's strict byte reader and JSON parser into the existing
32 MiB normal-installation bound. Default legacy limits stay 64 KiB. Fourteen
focused tests passed, including the real producer reader accepting a roughly
699 KiB snapshot, unchanged original evidence, oversize refusal, duplicate JSON,
private-mode and link checks. Subsequent complete local checks and supported
bounded original-operation recovery passed as recorded below.

Read-only preparation for the supported corrected-controller recovery found a
second size mismatch before invoking it: the bounded recovery source-graph
reader applied its 512 KiB metadata cap to every public source blob. Three
existing historical-runtime fixtures are 1,065,228, 894,708 and 815,970 bytes.
The complete source graph is 22,583,118 bytes (21.54 MiB) and 1,896 entries, within that graph's
existing 64 MiB / 10,000-entry bound. Metadata files are below 512 KiB. No
recovery retry or state mutation was attempted on this finding. The graph
must remain complete; fixture exclusions or skipped blob verification are not
a remedy. See the [read-only cap evidence](task-253-bounded-recovery-caps.json).

The corrected public bounded recovery subsequently **passed in 507.239631 s**,
using the same original UUID `af3cf6ac-78db-466c-9024-a3d4e1ea334d`, retained target
`ee52cff...`, controller/final product `20f0fc705e8b67353fb14bd64891dce56b36055f`
and configuration `e371d5d407d68daa7d9ea8ef150f88a6579a56ef` (source-pin-only
semantic delta). The continuation completed and archived the original backend
**byte for byte**; the active record was removed. Both gates are open/idle and
STABLE; all six services are active/running with no pending unit reload. PROD
and both General runner process identities were preserved; TEST Reviewer and
Production services were correctly restarted/restored by full recovery. All 32
actual namespace probes ran successfully. This is a full recovery timing,
separate from the eligible code-only performance result. See the
[original-operation recovery evidence](task-253-bounded-recovery-20f.json).
The original observer attempt still does not establish Runner stop/SIGTERM;
a genuine native interruption and ordinary same-pair recovery were selected next.

The genuine native interruption from `20f0fc70...` to
`c94c20c15a215207a2de50f7a8e7fb6ef8788829` produced the expected public failure
after 71.394251 s. All 19 fault guards passed, including exact installed target,
canonical TEST claim, original gate/journal/manifest binding, kernel Writer lease
and separation of the frontend/guards/services from the native helper's process
group. The observer actually stopped only idle `codex-relay-test-runner.service`,
then executed `os.killpg(own, SIGTERM)` with the default handler. Current target,
snapshot/archive/receipt/journal and UUID
`f3bcd87f-f9f3-443a-8bab-7a0d02fed99b` were retained with idle closed admission and
the matching backend. The other five process identities were preserved; the
Writer lease released. See the [signal frontier](task-253-native-signal-fault.json).

The new snapshot is **705,463 bytes**, distinct from the earlier 699,095-byte
snapshot. Ordinary same-pair public recovery, with all observer/fault hooks
removed and no special recovery flags or new UUID, passed actual classification
through the corrected reader. Signal evidence records durable stop confirmation, the exact self-kill
call and all guards, followed by native child failure; the independent native
child signal exit-status was not captured. No second signal test is claimed.

The ordinary same-pair recovery **passed in 492.454811 s**, retaining UUID
`f3bcd87f-f9f3-443a-8bab-7a0d02fed99b` and exact product/configuration pair
`c94c20c15a215207a2de50f7a8e7fb6ef8788829` /
`ea65df1135ec5e6f0c8ee5fbb570b1a28df99fd4`. The actually stopped TEST Production
Runner was restored; all six services are active/running with no pending reload.
PROD and both General process identities were preserved; TEST Reviewer and
Production restarted/restored through full recovery. Both gates are open/idle
and STABLE, the backend record is absent, and the original 705,463-byte snapshot
is retained in the prior stage. All 32 actual namespace probes ran successfully.
The canonical TEST claim remains held for the remaining cases. See the
[same-UUID signal recovery evidence](task-253-native-signal-recovery.json).

The final actual `environment.reviewCheckName` JSON change passed in
**511.478978 s** on product `c94c20c1...` / configuration
`33dc51041cd17079b405297101dfb41c39fe8249`. The public plan selected
`reconcile / apply`, and the ordinary full backend ran; neither provenance nor
native code-only promotion handled this changed input. The requested policy
was confirmed in both `deployment-config.json` and its owning
`reviewer-mcp.json.reviewCheckName` field (`consumer.json` does not own that
field). TEST Reviewer/Production correctly restarted; PROD and both General
identities were preserved. All six services are active/running without pending
reload, both gates are open/idle/STABLE, and all 32 actual namespace probes ran.
See the [final policy evidence](task-253-final-policy.json).

The byte-exact original JSON restoration then **passed in 519.826053 s** through
full `reconcile`, on configuration `fdef308c21aa9e7910ef4fe6c9bcb9ecffcf5df9`.
Its actual bytes, SHA-256 and Git blob
`62b0b8d5c0d4edb3caa5aaf0b2eb3a8336d028c3` equal the original `ea65df11...`
configuration; the owning Reviewer policy is restored. Default profile and
source pin remain unchanged. All 32 actual probes passed. See the
[exact restoration evidence](task-253-final-restore.json).

Final bounded readback found all six services active/running without pending
reload, both gates open/idle/STABLE, no manager jobs, no dpkg audit problems and
no active backend or clean-reinstall journal. Installed source is unpatched and
all task frontends/fault/timing hooks are inactive. Both PROD and both General
PID/start identities are preserved from the initial baseline. The original
bounded backend archive remains byte-equal. The canonical helper verified and
released **only** Task 253 / `run-43578199509`'s own claim; readback is `FREE`, with
the marker inode and mode preserved. No further TEST access is planned. See
[final health and release facts](task-253-final-health-release.json).

Each of the four completed full recovery/policy/restore cases emitted two
existing Ansible temporary-directory permission/fallback warnings. No target
permission rewrite was used. Those completed backend logs contained no nginx,
unclassified warning, ignored failure, failed or unreachable recap entries;
the deliberate native public fault remains separately recorded as an expected
failure. The earlier 18 nginx warnings belong to the stopped fresh/shared-reload
assessment. `integration.compatibility=missing` persists: generated artifacts
remain available for normal receiving-repository publication, without a remote
workflow/config-main change or a live Actions-attestation claim. See the
[bounded warning classification and disposition](task-253-final-warnings.json).

## Implemented behavior and retained limits

- First-install credential and CA preparation precede ACME dry-run/issuance;
  issuance precedes the readiness Apply. Existing-install missing/partial TLS
  refusal and exact pending-pair recovery remain binding.
- The site prepares Bubblewrap and shared slot prerequisites once while retaining
  all 32 fixed routes, private destinations and namespace probes. Repository
  ancestors are deduplicated within a slot without traversing retained descendants.
- A configuration Git commit with identical validated input bytes can use
  sufficient locked current native proof before atomically promoting its existing
  installed receipt; older/unsupported capability retains the complete ordinary
  post-check. The identical-pair no-op shares this verifier. A fresh ready marker
  is preserved when present; completed historical upgrades without that marker
  rely on the same sufficient readiness proof.
  Corrupt/pending state refuses. Recovery cannot carry an old ready marker into
  a different desired pair.
- Reviewer provides frozen loaded-input evidence over a private Unix socket in
  its own process, authenticated by kernel peer credentials. The transient
  lifecycle proof checks loaded policy/CA/environment, executable/dependencies,
  unit/credential inputs and Production Runner startup state. Equivalent healthy
  processes can remain running; unavailable or changed evidence retains restart.
  An unavailable optional proof does not prevent ordinary Reviewer startup or
  relax network mTLS.
- Staged Codex consumption avoids duplicate verification within one protected
  call and avoids identical file/link writes after actual current verification.
  Acquisition/resealing across operations remains unchanged: version equality
  alone cannot prove native-updated Runner bytes or a previous operation's stage.
- Eligible source-only upgrades can replace the full site traversal with
  canonical desired file/identity/namespace checks and current native
  host/App/TLS/package/pool/loaded-process proof. An independent official pinned
  Codex reference lives only in the operation's private stage. Full Reviewer
  source/build/toolchain invalidation stays exact. The existing sealed release,
  locks, gate, original activity snapshot and recovery record protect promotion;
  complete current proof immediately precedes mutation and follows it before
  record clearance. Static stage checks do not repeat full external host checks.
  Installed Python caches are accepted only as exact current-interpreter
  compilations of canonical tracked source, including nested code metadata;
  their hashes/stat identities are separate from reconstructed Git identity.
- The intermediate inactive-bootstrap full check remains. Existing negative
  tests use it to detect post-materialization drift; equivalent shorter proof
  was not established. This retained fresh-install pass does not impose a full
  traversal on eligible source-only upgrades.

The owning [deployment contract](../../deploy/README.md),
[Git installation contract](../git-managed-installation.md) and
[Reviewer contract](../../reviewer/README.md) describe the supported behavior.

## Measured accepted-source baseline

The current execution first verified the configured TEST target, dedicated
instance/pool identities, exclusive shared TEST claim, existing reusable
registrations and credential sources. Before mutation, PROD admission was open
with no active/unknown effects, operation state was stable, manager jobs were
empty, relevant PROD units needed no reload, required packages were installed
and dpkg reported no incomplete repair. Ordinary upgrade keeps nginx management
disabled. These observations justify the bounded shared-host operation; naming
alone does not establish isolation.

The public installer upgraded the existing TEST installation from
`5df7e0093d93c5a55b996e34cc83359da6b22a3e` to accepted source
`feefb6cf13daaf1c027e24d0a51fe834d68d26ba`, with configuration
`36da91eb94ac5ea54ea2f52aa97c97df741aecbc`, capacity two and all 32 fixed routes.
The owner-checkout receipt checked the real product/configuration main refs and
committed bytes; it makes no workflow-dispatch attestation.

| Boundary | Observed duration |
| --- | ---: |
| Complete public install | 643.395 s |
| Main site backend | 428.736 s |
| Source-only stage backend | 13.055 s |
| Host preflight backend | 13.033 s |
| APT preflight backend | 4.410 s |
| Full artifact stage backend | 62.044 s |

These backend intervals are components, not a complete exclusive allocation of
the outer duration. The baseline callback did not separately start handler
timing, so its file aggregates cannot establish an exact activation interval.
The later candidate harness also records outer phase boundaries and handlers.

The baseline executed 32 Bubblewrap tasks and all 32 namespace probes. TEST
Reviewer and Production Runner changed PID/start identity; both General Runner
members retained theirs. Final inventory had no blockers, exact pair/readiness
and equivalent configuration. Both PROD Reviewer and Runner retained PID/start
identity and remained active at the final readback. This bounds observed
noninterference to the measured operation, not all future shared-host activity.
See the [sanitized baseline evidence](task-253-baseline.json).

Two nonfatal Ansible warnings reported unusable TEST runner temporary directories
and fallback to system temporary storage. No original permissions were changed;
their timing contribution is unknown. One receipt-path ancestor refusal occurred
before mutation; moving this attempt's receipt into root-private storage allowed
the same accepted pair to proceed. It is excluded from the successful duration.

## Source validation and CLI maintenance

On corrected recovery candidate
`20f0fc705e8b67353fb14bd64891dce56b36055f`, Node passed 1,169 tests with seven
skips; Rust formatting and all 163 tests passed; three-consumer qualification
returned `THREE_CONSUMER_PASS`; candidate scanning passed 1,511 tracked files.
The Reviewer production artifact SHA-256 is
`912992960bd84c93bff4e006bc6b596d44e2382721322ff7a011b3ab076fa8fa`.
An independent native source copy at that exact revision ran the complete
writer-repository, Codex-primary-group and sandbox-cleanup test files as actual
ordinary UID 1000: **53 passed, zero skipped**, including the cases skipped
under root. These are complementary local checks, not independent acceptance.
The complete root deployment-suite rerun passed **3,297 tests**, with 13 skipped
and one existing passlib/crypt deprecation warning, in 1,279.26 s. The seven
root-context skips were covered by the ordinary-UID run above. Four remaining
cases need Docker/systemd fixtures; two need explicit upstream-download opt-in.
No skip is represented as an executed test. The root run used Node 22.20.0,
Rust 1.90.0 and a private mount view containing synthetic public host identity;
the real host's SSH identity was not changed. All required local candidate
commands passed on this exact code revision. Later qualification-only commits
do not change those runtime/test sources.

The preceding complete run on `ee52cff...` returned 3,266 passed, 13 skipped
and 11 failed. The one recorded-entrypoint fixture unintentionally selected
the real local adapter under root; it now explicitly keeps its recorded target
transport. The ten provenance failures came from a transport seam rejecting the
new actual read-only probe and an inventory race tied to call ordinal. The
corrected fixtures execute the genuine old-capability fallback, retain the
32-slot/final-Ansible/provenance assertions and inject the race between the
owning inventory observations. All 13 provenance cases and the exact root
entrypoint regression passed before the full rerun. Production checks were not
disabled in response to these fixture failures.

The first complete root deployment run returned 2811 passed, 25 failed and
16 skipped. All 25 failures reproduced on the accepted source in bounded
comparisons. Besides the six host-preflight fixtures below, remaining fixtures
contained noncanonical pool inputs, retired SERIAL receipt expectations,
incomplete historical import graphs or an implicit writable-temporary-parent
assumption. Corrections preserve the negative and real transition assertions;
the corrected complete root rerun on `78796955c0350bbdc5b0f8ac9487064cbd1e0002`
passed 2923 tests, with 13 skipped and one existing passlib/crypt deprecation
warning. A later full candidate run still must cover subsequent source changes.

Two `test_partial_install_recovery.py` orchestration cases explicitly substitute
the loader for their unchanged historical SERIAL fixture, alongside the existing
compiler/backend transport substitutes. They verify ordering, original receipt
and incident-history preservation after that boundary; they do not establish
that today's public loader admits fresh SERIAL. Separate loader/native gate
tests remain applicable. Installed qualification in this Task concerns its
current exact pair, not acceptance of that historical incident.

Native Linux validation has passed Node (1169 passed, seven skipped), Rust
(163 passed), the three-consumer production-binary qualifier, candidate scanning,
and targeted provenance/process-adoption/ACME tests. The qualifier also starts
the actual binary with missing optional proof inputs: MCP remains usable,
unauthenticated requests still receive 403, no partial proof socket appears,
and the constant warning exposes no private input path.

Six existing host-preflight failures were reproduced on the accepted source and
corrected in test fixtures: legacy SERIAL labels/strict groups and old unit/root
names were being asserted against today's managed-pool example. The default pool
fixture remains; explicit legacy cases preserve their original invariants. The
corrected root host-preflight suite passed all 49 tests.

Routine CLI maintenance checked official stable 0.169.0. Its six-case
credential-free probe passed, but its changed project trust behavior disables
untrusted project-local configuration/MCP, while Relay's fresh task home does not
establish that trust. The probe's explicit `-c` MCP configuration does not cover
that gap. The qualified 0.167.2 pin remains; no client self-update or new deployment
permission follows from this assessment.

## Initial implementation installation

The public manual root installer then upgraded accepted `feefb6cf...` to
`cdc829f9e9501056c65ef794560fcde30e95b42b`. Its actual local TEST configuration
commit is `1f3412b75fd43871cf2c7f7e8eadb2fcf364537e`, with only the exact source
selector changed. The factual owner-checkout receipt uses `test-qualified-exact`
under this Task's isolated TEST authority; it asserts neither remote accepted-main
configuration nor a workflow-dispatch event.

The installation passed in 645.613 s. Main site took 356.377 s, while full
artifact preparation took 137.697 s because the Reviewer binary and its startup
inputs changed. Reviewer and Production Runner correctly restarted. Both General
Runner members and the observed PROD Reviewer/Runner retained PID/start identity.
The private socket returned a bounded schema-1 digest-only response to root;
kernel peer identity matched the actual Reviewer PID/UID, and a client running
as that same service UID received no proof. All 32 namespace probes executed;
one Bubblewrap task executed and 31 additional package tasks were skipped.
Two nonfatal temporary-directory fallback warnings remained. See
[sanitized implementation evidence](task-253-implementation.json).

This changed-binary installation is not the unchanged-component performance
sample. Review also identified the Production Runner's system trust-store
dependency: environment values alone cannot attest cached .NET/OpenSSL roots.
Its transient proof must cover unchanged trust-store content/topology since
startup before the first installed preservation test. Reviewer WebPKI roots are
compiled into its proved binary; its inbound client CA is separately captured.

## Intermediate unchanged-input cases

The subsequent code-only installation from `cdc829f9...` to
`284e3f1f783f12b31b88332d7cde63f67dbd426a` passed in 565.946 s, with a
363.795 s main site and reused Reviewer build. This is 77.449 s (12.0%) below
the measured 643.395 s accepted-source baseline, with shared-host/cache limits.
The initial loaded proof succeeded, but the post-install comparison selected
ordinary restart. Reviewer and Production Runner restarted safely; this result
does **not** qualify unchanged-process preservation. All 32 namespace probes
executed, with one Bubblewrap task and 31 additional package skips. See
[initial code-only evidence](task-253-codeonly-initial.json).

An identical-pair no-op passed in 306.029 s (291.224 s site), preserving all six
observed TEST/pool/PROD PID/start identities. Its read-only check skipped namespace
probe execution; it does not substitute for the real installation probes. See
[no-op evidence](task-253-noop.json).

A README-only configuration commit with the same JSON blob passed the initial
provenance path in 308.640 s (291.549 s site), preserving all six identities.
See [initial README evidence](task-253-readme-initial.json). Subsequent source
correction adds an explicit loaded-input proof before provenance promotion;
the earlier disk/post-check result alone does not qualify that corrected path.
Both read-only cases emitted one existing nonfatal temporary-directory fallback
warning. Generated consumer workflow publication remains separate; the observed
integration compatibility warning is not live Actions-dispatch qualification.

An actual `environment.reviewCheckName` policy change selected managed reconcile
on `284e3f1f...`, passing in 569.536 s (366.338 s site). Reviewer and Production
Runner correctly restarted. Restoring the exact original JSON passed in
559.724 s (354.394 s site), again requiring restart. Both operations executed
all 32 namespace probes, one Bubblewrap task and 31 additional package skips;
both pool and both observed PROD processes remained active with unchanged
PID/start. Each emitted two existing temporary-directory fallback warnings.
See [policy-change evidence](task-253-policy.json) and
[exact restoration evidence](task-253-restore.json).

## Intermediate native-proof and performance qualification

The new native source/provenance verifier's combined targeted Linux root suites
passed **293 tests, one skip** in 24.87 s before final candidate qualification.
This includes canonical Ansible template rendering, real Git archive/object-tree
reconstruction, exact derived Python cache checks, native sealed-stage
promotion/failure boundaries, distinct installed-reuse receipts, independent
Codex reference negative cases and scheduler selection/fallback/binding checks.
The existing Python `crypt`/passlib deprecation warning remains visible.
At this intermediate stage, those focused checks did not yet establish the
final full candidate set or the measured public installer result. Subsequent
complete checks and installed results are recorded above.

The complete native proof was then qualified against the healthy installed
`6b80e6ab...` TEST pair using a frozen six-module prototype and an actual official
Codex reference. Acquisition used the ordinary `get_url` HTTP agent with TLS
verification and took 8.010 s. Earlier targeted failures identified only the
prototype's unprotected `/var/tmp` source-parent location, a typed empty
`EnvironmentFiles` property omitted by systemctl's text formatter, the
installer's historical selection-link identity, and the distinction between
General retention and Production startup adoption. Corrections use owning
contracts and current source, without changing live expected bytes, pruning
history or weakening Production history checks.

The complete sequential proof passed in **33.311 s**; bounded parallel scheduling
then passed the same predicates in **16.879 s**, including final rechecks and
all 844 catalogue entries/32 native namespace probes. Components overlap, so
their wall durations are not additive. Both calls reused only the same
diagnostic operation's independently acquired reference after a complete actual
rehash; ordinary source promotion always acquires a fresh operation reference.
No Apply, admission or cutover occurred, and the binding and all six service
identities stayed unchanged. See [initial complete proof](task-253-native-proof-initial.json)
and [parallel complete proof](task-253-native-proof-parallel.json). This is
mechanism qualification, **not** the required end-to-end Apply benchmark.

The latest focused root run passed **230 tests**: parallel source proof including
the real Git roundtrip fixture, package equivalence, General component snapshots
and the unchanged strict Production suite. Simultaneous-error tests verify that
all futures finish and a hard binding failure cannot be hidden by an earlier
ordinary unsupported-profile result.

The first public native-path confirmation at `7dc23f1e...` stopped before sealing
or any live effect: a preexisting private stage `bin` directory retained mode
`0700`, so the real entrypoint readability check refused it. The complete
invocation took **71.144488 s**, including a fresh official reference; this failed
attempt is not a successful Apply benchmark. Installed source remained
`6b80e6ab...`, no recovery began and all six observed service identities remained
active and unchanged. See [failed public attempt](task-253-native-attempt-7dc.json).

The coordinator now validates private directory ownership/type and explicitly
sets their declared modes before sealing. A real frozen-helper extract/seal
regression covers an existing `bin=0700` under `umask 077`. Intermediate checks
now rehash only the immutable operation reference; complete live package and
runtime proofs remain at the initial, final pre-effect and post-effect frontiers.
The coordinator/package suites passed **90 tests**. General capture eliminates
duplicate byte reads within one capture using fresh descriptor/path metadata
checks, with no cross-call cache. Its **44 tests**, together with **101 unchanged
Production tests**, passed; overwrite with restored mtime, chmod, alias and inode
replacement refuse, and a second capture must hash bytes again. These corrections
still require a new successful public end-to-end measurement.

The unmodified complete target proof with these helpers passed in **15.404334 s**
(17.223944 s total read-only diagnostic). The same operation reference was fully
rehashed; no acquisition, Apply or cutover occurred. Current binding and all six
service identities remained unchanged. This reduces repeated General byte reads
within each independent capture while retaining the complete proof. See
[complete proof with local reread reduction](task-253-native-proof-memo.json).

The initial source-only Ansible preparation cost 12.937 s in the failed public
attempt. A bounded native batch now uses the exact frozen archive/tree helper,
canonical consumer template and six actual Node syntax checks in one private
stage transport. It retains the original source play for unsupported frontend
capabilities before submission, stops on a submitted failure, and preserves the
first-install prerequisites and later complete build path. The native batch and
public scheduler integration passed **53 focused Linux tests**, including actual
Ansible template-action byte parity, restrictive umask, each entrypoint's real
syntax failure, archive/tree/path refusal and no fallback after transport error.

The subsequent public native Apply from `6b80e6ab...` to
`c3efa9cef38e5ac8d392b70132689c092ff3cf29` passed with a fresh official reference,
an exact installed product/config pair and all six active service identities
preserved. It executed the canonical 32-route catalogue without full-site
fallback. Complete driver E2E was **158.550815 s** (wrapper 158.499495 s), so the
owner's tens-of-seconds objective remains **unmet**. Source preparation took
33.677 s, including 26.996 s in its remote prepare; native promotion took
52.975 s. Source-only batch preparation still cost 12.500 s, Writer acquisition
12.333 s, and two redundant frontend pool preflights 4.599/4.930 s. These are
observed phase walls, not additive independent savings. See
[successful native Apply](task-253-native-apply-c3ef.json).

The observer initially reported one route by counting an unrelated optional
runtime-user override array. The retained protected catalogue independently
requires and contains all 32 actual probes, each bound to its declared slot and
runtime identity. The evidence explicitly records that observer correction;
expected product data was not changed. See [actual route bindings](task-253-native-routes-c3ef.json).
A current-context complete proof then passed in **14.917369 s**, with the genuine
retained reference fully rehashed and no reacquisition or Apply. Original
promotion logs do not expose separate durations of its two proofs. See
[current read-only proof](task-253-native-current-proof-c3ef.json).

The successful install emitted the existing consumer-integration `missing`
compatibility warning. Generated artifacts still require ordinary publication
in the receiving repository; no remote workflow or configuration-main mutation
was performed, and the installer did not require another installation run.

Targeted follow-up separated unchanged predicates from transport overhead. A
bounded gzip source batch reduces the actual 22.24 MB tar's base64 payload from
29.66 MB to 8.24 MB (compression 0.135 s); the target refuses corrupt, truncated,
oversized, trailing and multi-member streams. Canonical lazy rendering retains
actual Ansible byte parity. The selected native path now owns its complete pool
preflight through initial/final/post proofs; fallback/fresh/reinstall/recovery
retain the original frontend checks. Scheduler regressions passed **41 tests**,
including native zero calls, ordinary fallback two calls and refusal before
quiesce. Guard readiness uses one bounded wait inside the existing target
transport; an isolated real-flock fixture improved from 2.394 s to 0.919 s while
retaining process ancestry, kernel lock, EOF and release behavior. Its new and
existing transport suites passed **22 tests**. These isolated results do not
establish another end-to-end Apply improvement.

Additional bounded target reads established that seal verification (0.370 s),
destination verification including seal (0.443 s), fresh critical snapshot
(0.552 s), activity observation (0.184 s), binding and source-tree reads are
small in this sample; see [retained-stage costs](task-253-native-retained-costs.json).
An actual isolated copy using the frozen helper took **11.240 s** for 1524
regular files/33,762,995 bytes. Its exact tree hash matched the retained sealed
source, with no live destination changes. See [copy measurement](task-253-native-copy-cost.json).

The initial host, pool, loaded and package readers can overlap without changing
their predicates: package assembly needs the loaded result only after all
native version probes and inner Codex/General readers have completed. Four
bounded readers preserve all joins, protected-error priority and final rechecks.
All **39 proof tests**, including real Git roundtrip, passed. The exact new
proof passed current installed TEST in **13.308109 s**, returning all 32 routes
and 844 entries; genuine reference and service identities remained unchanged.
See [overlapped complete proof](task-253-native-proof-overlap.json). These remain
targeted measurements; no elapsed E2E savings are inferred by summing them.

The coordinator can now atomically publish an already sealed payload to an
absent same-filesystem destination with kernel no-replace semantics. It preserves
the original mutation record before moving, revalidates the complete seal,
persists topology and both parent directories, and switches subsequent native
checks to the installed source name. Existing/unsupported destinations retain
the frozen copy consumer. All original UUID evidence stays in its private
stage. **45 coordinator tests** passed, including racing destination creation,
metadata/topology movement, fsync faults, immediate after-move/current faults,
remaining config/post-proof failures and ordinary same-operation create/recovery.
The owning artifact suite passed **19 tests, two skips**. The frozen helper and
all executable Ansible recipe bytes remain unchanged from `6b80e6ab...`.

The next complete public Apply to `cb0e30a2ee44582f5e53965ca0a57fc43124be47`
passed in **130.398785 s** (wrapper 130.343259 s), with exact installed Git pair,
32 routes, atomic sealed-payload move and all six process identities retained.
Writer acquisition improved from 12.333 s to 1.118 s; frontend pool preflight
calls were absent as selected native proof owned their predicates. Source stage
still took 11.423 s, source preparation 32.622 s and native promotion 38.527 s.
The tens-of-seconds goal remains unmet. See [second native Apply](task-253-native-apply-cb0.json).

The root timing observer was not selected because its task hook tested an
explicit `local` flag instead of the owning resolved connection. This was a
diagnostic binding error, not a candidate failure: no root proof/status timing
is claimed for this case. The hook now resolves connection through the existing
transport; five mock routing checks passed, without another Apply for profiling.
The existing timeline identifies a 13.161 s gap spanning locked drain-check and
phase-applying transition; an 11.608 s transport receipt lacks a command label,
so its exact attribution remains unproved. See [bounded timeline](task-253-native-timeline-cb0.json).

Follow-up measurements ruled out the initial source-tree and SERIAL hypotheses
for that entire gap: the protected source predicate took 0.615 s with an explicit
synthetic diagnostic trigger; actual installed status took 0.077 s and had no
SERIAL compatibility receipt or original/composite calls. A temporary genuine
TEST publication-lock holder measured direct bound status at 0.096 s versus
1.067 s through the existing Ansible command adapter. The holder released by
EOF and no live gate was changed. These are bounded diagnostics, not native
admission/history proofs or another Apply.

The qualified local/root adapter now uses the same source-controlled commands
directly after the original Debian/public-host-key proof on every command.
SSH, non-root and unsupported contexts keep Ansible. Its isolated private mount
namespace median was **0.0230 s** versus **0.9189 s** through Ansible, both with
the same actual target proof. Private input supplies complete EOF at launch;
bounded PIPE readers preserve completion through descendant EOF. Original
guarded-promotion tests cover main exit, guard loss, deadline and escaped channels;
unknown channels fail after bounded cleanup instead of claiming completion.

Catalogue construction reuses parsed canonical task nodes and compiled code
only inside its own build/environment. Rendered output is always fresh;
overlays, compiler/binding changes, static filter/test evaluation and late
undefined values retain native semantics. **35 tests** passed, including actual
Ansible byte parity. Two isolated catalogue builds fell from **4.801 s to
1.486 s** with the semantic guards enabled.

The combined exact-source Linux root run passed **254 tests, two skips** in
55.11 s, with the existing crypt deprecation. This run used Node 22 and a
synthetic protected public host key only in a private mount namespace. Its two
Cargo-dependent artifact fixtures were skipped because this targeted invocation
did not supply the Rust toolchain; the required full candidate run remains due.

The `4440f0dc...` code-only attempt passed installation in 574.523782 s with
ordinary restart. A task-only diagnostic added 3.434623 s of read-only work;
subtracting it is an extrapolation, not a separate successful benchmark. The
before proof was eligible; post-install recapture differed only in Reviewer
and Production service metadata. The callback retained component classes but
omitted the authorized public field names, so that finer historical frontier
is unavailable. No proof was accepted and restart remained mandatory. See
[intermediate code-only evidence](task-253-codeonly-444.json).

The source now compares only `Requires`, `BindsTo` and `PartOf` as their owning
systemd unit-set semantics require. Command arguments, environment files and
drop-ins keep their ordered comparison. A subsequent installed case must still
establish actual preservation; this source correction alone does not do so.

The subsequent `fa803e1d...` installation passed in 569.630431 s, again with
ordinary restart. Its 3.447694 s diagnostic recapture identified the public
`ExecStart` service field in both components, plus an unexpanded Production
process-identity class during the additional capture. The textual systemd
property mixes configured commands with execution history; the next source
uses typed `ExecStartEx`, retaining path, ordered argv, all flags and command
order. Runtime identity remains independently checked. No process proof was
weakened in response to the unlocalized class. See
[second intermediate evidence](task-253-codeonly-fa8.json).

The `6b80e6abd3e5e130bd975f4bec8570ccfec8e0cc` installation subsequently
qualified the corrected loaded-process proof: all three captures and the final
complete proof assertion passed, restart was skipped, and all six observed
TEST/pool/PROD PID/start identities were preserved. All 32 real namespace probes
executed. The complete public install took **584.591986 s**, including the
375.571824 s site backend; this proves process preservation and **does not meet
the tens-of-seconds goal**. See [corrected process evidence](task-253-codeonly-6b80.json).
Further field diagnosis uses bounded targeted reads before one confirming
end-to-end fast-path Apply, rather than repeated full Applies.

Unassisted fresh ACME qualification stopped before cleanup at a concrete shared
nginx boundary. The configuration glob changed after the eight current accepting
workers started, and no complete pre-worker set witness establishes which
foreign additions/removals a reload would activate. The evidence does not assert
that foreign bytes changed. No reload, fresh reset or cleanup was performed.
See [bounded shared-host evidence](task-253-fresh-boundary.json). Existing TEST
credential sources and registrations remain in place.

The native fast source-promotion implementation, end-to-end code-only timing,
same-pair no-op, README-only provenance, original bounded recovery, genuine
signal/same-UUID recovery, final policy/byte-exact restoration and complete local
candidate checks are qualified above. TEST is returned healthy and the own claim
is released. The unassisted fresh ACME gap remains explicit; no complete fresh
installation qualification, independent acceptance or PROD improvement is
claimed. Requested profile is Sol/xhigh with Subagents On;
implementation helpers were used. Actual runtime model/effort telemetry is
unavailable. The native chat rename succeeded but readback exposed a truncated
title; Task/Step/admission identity remains exact and that navigation limit is
nonblocking.
