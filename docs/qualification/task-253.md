# Task 253: first-install and unchanged-input Apply qualification

This records evidence for admitted manual Step 2, `run-43578199509`, under
[Task 253](https://github.com/jresearchsoftware/codex-relay/issues/253) and
[PR 254](https://github.com/jresearchsoftware/codex-relay/pull/254). The accepted
starting source is `feefb6cf13daaf1c027e24d0a51fe834d68d26ba`. Source acceptance,
installation and Task closure remain separate. No PROD Apply is authorized.

## Implemented behavior and retained limits

- First-install credential and CA preparation precede ACME dry-run/issuance;
  issuance precedes the readiness Apply. Existing-install missing/partial TLS
  refusal and exact pending-pair recovery remain binding.
- The site prepares Bubblewrap and shared slot prerequisites once while retaining
  all 32 fixed routes, private destinations and namespace probes. Repository
  ancestors are deduplicated within a slot without traversing retained descendants.
- A configuration Git commit with identical validated input bytes can use the
  complete locked read-only post-check before atomically promoting its existing
  installed receipt. A fresh ready marker is preserved when present; completed
  historical upgrades without that marker rely on the same full readiness proof.
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
- The intermediate inactive-bootstrap full check remains. Existing negative
  tests use it to detect post-materialization drift; equivalent shorter proof
  was not established. Ordinary upgrade already has one full traversal.

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

Corrected-source process preservation, changed-policy and original-operation
recovery cases, corrected provenance, and unassisted fresh ACME qualification
remain in progress. This snapshot asserts no final installed qualification,
independent acceptance or PROD improvement. Requested profile is Sol/xhigh with Subagents On;
implementation helpers were used. Actual runtime model/effort telemetry is
unavailable. The native chat rename succeeded but readback exposed a truncated
title; Task/Step/admission identity remains exact and that navigation limit is
nonblocking.
