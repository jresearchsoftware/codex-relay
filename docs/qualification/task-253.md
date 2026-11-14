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

## Remaining installed evidence at this snapshot

The new native source/provenance verifier's combined targeted Linux root suites
passed **293 tests, one skip** in 24.87 s before final candidate qualification.
This includes canonical Ansible template rendering, real Git archive/object-tree
reconstruction, exact derived Python cache checks, native sealed-stage
promotion/failure boundaries, distinct installed-reuse receipts, independent
Codex reference negative cases and scheduler selection/fallback/binding checks.
The existing Python `crypt`/passlib deprecation warning remains visible.
These focused checks do not substitute for the final full candidate set or
the still-pending measured public installer invocation.

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

The native fast source-promotion implementation and targeted host proof are
complete at this snapshot. End-to-end Apply timing, final
policy/fault/original-operation recovery and corrected provenance cases
remain in progress. This snapshot asserts no final installed qualification,
independent acceptance or PROD improvement. Requested profile is Sol/xhigh with Subagents On;
implementation helpers were used. Actual runtime model/effort telemetry is
unavailable. The native chat rename succeeded but readback exposed a truncated
title; Task/Step/admission identity remains exact and that navigation limit is
nonblocking.
