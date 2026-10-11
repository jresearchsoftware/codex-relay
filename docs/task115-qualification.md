# Task 115 bounded qualification observations

This note records source, TEST and original-publication observations for the
same owner-launched manual Step 1. It is evidence for the current Task/PR, not
another authority registry. No independent acceptance, product merge, Issue
closure, production installation or deployment is claimed.

## Current qualification disposition

Current trusted [Request 6112661946](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6112661946)
selects [Decision 6112655517](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6112655517).
Standing isolated TEST autonomy is resolved; ordinary TEST actions require no
repeat owner confirmation. TEST PR 3 was merged at `4598e746...`; draft
[TEST PR 5](https://github.com/jresearchsoftware/codex-relay-testbed/pull/5)
preserves the runbook correction at `adc3937...`.

The supported recovery to `44f97a8...` failed after partial apply, before the
release pointer changed from `dbfea188...`. Its retained exact-head record and
lifecycle operation `73034a9b-47a1-4ec3-993a-166560bfd39e` remain intact and
recovery-required. The following read-only check performed zero changes and
reported `recovery-requires-disposition`. Existing public interfaces provide
no applicable disposition for this partial state; further protected mutation
is stopped. The packaging/reuse corrections are source-qualified, but live
manual socket, MCP submission and complete E2E remain unqualified.

The current owner-authorized handoff uses PR 118 plus committed evidence,
explicitly without a normal Writer Outcome. The general authority-change
publication requirement is deferred and is not a Task 115 completion gate.
Earlier observations below retain their historical heads/authority; later
sections record each superseding fact rather than changing old evidence.

## Original admission and historical authority

The original launch was installed schema-v3 Request
[6109630038](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6109630038),
whose native body SHA-256 is
`baead0f01eb40853eff28791cbb067d703f811037fa26e25b8c121d52e4d4bde`.
Native run [38144146016](https://github.com/jresearchsoftware/codex-relay/actions/runs/38144146016)
completed its first owner-triggered Issue/manual handoff attempt at product
`b4cb4943d52dd375d8c6800959b3264fad082cb8`.

The owner later authorized bounded isolated TEST consumer/configuration work
through current v3 [Decision 6110064799](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110064799)
and same-Step [successor Request 6110068398](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110068398).
Their read-back body SHA-256 values are
`1d662713e73803586945c7644601f8029d8398447f571b6bfd9a43b4212c4468` and
`e9eb320876b41a34e03d9e8f033280be36fa72c109cbe96d42bb41cf32d1b978`.
No new ready event, execution, Step or admitted-journal rewrite accompanied
that authoring change.

## TEST configuration and read-only inventory

A separate clean TEST consumer checkout started from main
`52d66305557a74264cd0f5b82ec0b90804baa98c`. Its literal configuration identifies
`jresearchsoftware/codex-relay-testbed`, owner `foal`, namespace
`codex-relay-test`, distinct TEST Unix/App/runner identities, dedicated port
18787 and hostname `codex-relay-test.jresearch.org`. Owner SSH host
`195.201.83.241` and nginx topology are shared; TEST identity does not authorize
shared-ingress or production mutation. Configuration references were inspected;
private keys, tokens and credential contents were not read.

The supported public inventory ran from a separate clean native Debian checkout
at the then-configured accepted source
`afb2cbdbcb82294604c51ec0ce4c2a62cf272a49`:

```sh
python3 deploy/relay-deploy.py \
  --config /mnt/q/work/task115-test-consumer-01a12b33/deploy/relay.json \
  --requested-revision afb2cbdbcb82294604c51ec0ce4c2a62cf272a49 \
  --resolved-revision afb2cbdbcb82294604c51ec0ce4c2a62cf272a49 \
  --phase inventory
```

The result was `status: blocked`, blocker `configuration-different`, consumer
equivalent, deployment different, installed revision
`dbfea1889da994791a5b6c05d97a71405d21eac5`, `readOnly: true` and
`mutationAuthorized: false`. Exit 0 and the read-only PASS line meant that
observation completed, not that the blocker was resolved.

The explicitly authorized bounded comparison verified the protected literal
nonsecret deployment snapshot against its release manifest SHA-256, current
release/source identity, regular single-link 0600 file and protected parents.
After public inventory normalization, only
`environment.reviewerRepositories` differed: the installed snapshot listed
`jresearchsoftware/codex-relay-testbed`, `jresearchsoftware/codex-relay`,
`jresearchsoftware/shared-governance` and
`jresearchsoftware/codex-relay-testbed-2`; tracked configuration omitted it.

[TEST draft PR 3](https://github.com/jresearchsoftware/codex-relay-testbed/pull/3)
records those exact existing values and the README's Task-115-only TEST
fixture/call boundary. Its head is
`1602f1cdc765f844eebacc5d750cfa4667ce3ccb`; only configuration and README changed.
Eight native Debian unittest checks and whitespace validation passed. The
[native candidate check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38147715218/job/114494456644)
passed at that head. No App grant, credential, historical Task 76 artifact or
installed-state change occurred.

The subsequent README-only commit records the explicit TEST-local development
qualification disposition under the same Task authority. Its exact head is
`86f60dff90e3275948ac947a6d8d63811715017f`. Local consumer validation again
passed eight tests, the consumer checkout is clean, and its
[native candidate check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38148432830/job/114496598707)
passed at that exact head. These checks do not establish a later candidate or
installation.

The old `afb2cbdb...` entrypoint cannot represent the explicit allowlist and
returns `INVALID_DEPLOYMENT_CONFIG:environment`. To inspect matching current
intent, the public inventory ran from a clean exact already-installed
`dbfea1889da994791a5b6c05d97a71405d21eac5` checkout, with both revision arguments
explicitly set to that SHA. Its sanitized result was:

```json
{
  "status": "observed",
  "blockers": [],
  "readOnly": true,
  "mutationAuthorized": false,
  "configuration": {"consumer": "equivalent", "deployment": "equivalent", "status": "equivalent"},
  "installed": {"status": "present", "revision": "dbfea1889da994791a5b6c05d97a71405d21eac5"}
}
```

Both runner registrations were reported reusable without a fresh token.
Credential/TLS observations were metadata-only. Live App permissions,
runner-group ACLs and DNS/ingress remain separate owner-admin observations;
inventory does not inspect every retained operation journal.

The supported TEST `relay-admission status` reported version 1, phase `open`,
null operation/target, zero active attempts and zero unknown attempts. Its
consumer digest was
`18fdd7fa538be3aef3ee6000181018230c5120f7371d524707b362e8bff30a5c`.
No quiesce, drain, reset or journal clearing was invoked. These are bounded
read-only snapshots; a future upgrade must recheck state under its own lock.

Read-only TEST MCP inspection of historical closed/merged PR 2 confirmed exact
head `91e29c09ac089dfd10dbaf6e8feeb42a9171395e`, authenticated App slug
`jresearch-relay-test-reviewer` and `ready_for_review: false`. The exposed TEST
connector had four existing review/authority tools and no
`submit_manual_outcome`; its repository enum reflects the broader installed
allowlist. Other repositories were not probed through that connector.

## Original Task 115 public Writer state

The existing qualified owner SSH transport and strict host checking reached
the product's installed namespace. The current pointer/release manifest/source
identity bind exact product
`b4cb4943d52dd375d8c6800959b3264fad082cb8`. The fixed root-owned wrapper matches
the public template and selects `/etc/codex-relay/consumer.json` for repository
`jresearchsoftware/codex-relay` and owner `foal`.

Five relevant installed source files matched their exact published Git blobs:

| File | SHA-256 |
| --- | --- |
| `consumer/consumer-config.mjs` | `7c3bb6733c554d7e932dfdd35ef103d47ab00b09eec119495da127776b634547` |
| `controller/src/local-writer.mjs` | `19968b7d78627dead0707996ada10a80d100874ed14c65649e45171efb16e526` |
| `controller/src/privileged-writer-helper.mjs` | `80bb02dc0b07644dcadbe893351820ffb3c75e8fb6c4dc28f8b77784e4ee070d` |
| `controller/src/publication-broker.mjs` | `1a30ed0200b1094d35cdc64d975ade59fd996875c8d1cf596cf805f71f3575cb` |
| `deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2` | `eb89f14b018d527d78bee2b5c1f533b1490e91ee38565d11588d87935a635431` |

An initial diagnostic probe rejected the helper's root:root 0664 source mode.
That was the probe's overly strict assumption, not an observed public product
gate, unsafe-installation finding or regression. No mode was changed. Exact
manifest/source/blob parity and the installed public contract supplied the
required provenance; group-read-only deployment metadata remained protected.
Diagnostic read stamps excluded access time, which ordinary reads can change.

Only the fixed `/opt/codex-relay/relay-writer-controller` was invoked, with no
command arguments and this bounded stdin request:

```json
{"operation":"publication-state","runId":38144146016,"attemptId":"run-38144146016"}
```

The version-2 repository-bound receipt confirms Task 115 Step 1, manual Issue
route, branch `codex/task-115-step-1`, starting head `b4cb4943...`, no publication
intent, no published head and no recovery. The admitted Request remains
6109630038 with its original body digest. Immutable authority digest:
`1e4d521f871f38cd415fab03d010dd9e83e00612d14bcea75b5cf19520673142`.
Consumer digest:
`4955dd18448f0859b43f28111e89a534ab83f4070124deab7d191b59df073837`.

The live same-Step successor Request does not rewrite that stored binding.
Installed manual publication revalidates current native authority, so the
changed selected Request can be a genuine publication boundary. That is exact
installed-source analysis, not an observed manual-publication failure. No
`manual-outcome` request, credential read, journal rebind, new execution or
other production Task/global-journal inspection was performed.

## Next supported TEST action and limits

The consumer README and public deployment contract require an explicitly
selected exact product source under current owner authority, separate clean
product/consumer checkouts and reviewed/published compatible workflow bytes.
Current Task 115 authority explicitly permits implementation, tests and bounded
isolated TEST qualification before independent exact-head review. Accordingly,
the published candidate, after required local/native CI checks, is an
owner-selected TEST-local development qualification target. This task-local
disposition is not independent source acceptance, a general deployment-policy
change or production installation authority. The TEST README directs development
revisions through the explicit public source selector and retains denied
lifecycle-runner scheduling; the accepted-main lifecycle workflow is not used.

Once the exact published Task 115 product SHA is supplied, update the consumer
source selector to that SHA on its Task-owned branch. From a separate clean
exact product checkout, validate configuration, generate the supported
`workflow-project --authorize-workflow-projection`, inspect the bounded changes,
commit/publish them through the existing TEST PR and run `workflow-verify`.
Rerun public inventory; after exact ownership/configuration and safe state are
established, the admitted public action is:

```sh
python3 deploy/relay-deploy.py --config /path/to/TEST/deploy/relay.json \
  --consumer-root /path/to/clean/TEST/consumer \
  --requested-revision "$task115_product_sha" \
  --resolved-revision "$task115_product_sha" \
  --phase upgrade --authorize-upgrade
```

The public primitive verifies projection before target contact, obtains its
host apply lock, quiesces/drains valid attempts and checks protected operation
and recovery state. Only the source selector may differ from the equivalent
installed configuration. Credentials, registrations, activation intent,
TLS/mTLS, consumer identity and actor separation are preserved. Unknown or
retained failed operations require their supported diagnosis/recovery path;
there is no private backend, manual restart, permission repair or blind retry.

The inspected Debian controller has Git, Python, SSH and explicit Node 22.20.0.
Its default Ansible Core 2.14.18 was below declared `>=2.16,<2.18`, and
`ansible-lint` was absent. A separate unprivileged local environment at
`/home/hortonolite/work/task115-test-upgrade-tools-01a12b33` now contains
Ansible Core 2.16.19 and ansible-lint 26.9.0 from the declared requirements;
`pip check` and both version entrypoints succeeded. Invoking lint without the
environment's bin directory initially emitted a PATH-adjustment warning;
explicit per-invocation PATH selection of that environment and Node 22 resolved
it. No target or system-tool installation occurred. Candidate source/CI,
installed TEST upgrade,
actual manual socket/mTLS/identity delivery and real GitHub expand/copy
qualification remain unproven until their exact receipts exist.

## Exact development candidate preparation

The published product candidate is
`e3ade68311d3c328b18ef840a4744d5bfd468bc5` on
[source draft PR 118](https://github.com/jresearchsoftware/codex-relay/pull/118).
Both required native jobs at that exact head succeeded:
[Candidate checks](https://github.com/jresearchsoftware/codex-relay/actions/runs/38149407840/job/114499520587)
and [Codex CLI compatibility](https://github.com/jresearchsoftware/codex-relay/actions/runs/38149407840/job/114499520732).
This is the Task-authorized TEST-local development selector, not independent
acceptance or a production target.

The TEST selector/runbook commit is
`de1c5644e3700f85ee626dff65d8f631531b37e1`. An initial public projection with
that dirty selector correctly stopped at `clean-source` before writing files.
After committing it, projection on Windows drvfs stopped at
`workflow-regular-file`: the regular manifest was exposed as executable mode
0777. No permission bypass or product correction was applied. A separate clean
native Debian consumer clone supplied regular Git modes and the existing
manifest/digest baseline. Public `workflow-project` then succeeded, updating
only the two managed routing/recovery workflows and their manifest to
`relay-workflows-v3`.

The generated projection was inspected, committed and non-force published on
the existing TEST draft PR 3 at exact head
`7b0464ec250fa66a53d846d1475c54b7524e60b7`. Eight native Linux consumer tests,
whitespace validation and its
[native candidate check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38149675231/job/114500317455)
passed. Both consumer clones were clean. Exact-source public `workflow-verify`
passed, and `inventory` reported `observed`, no blockers, equivalent deployment
and consumer configuration, retaining installed `dbfea188...`. It still
reported owner-admin App/runner/ingress observations as unavailable; no broader
qualification is inferred.

One public `upgrade --authorize-upgrade` was invoked using the exact candidate,
clean native consumer and the qualified dependency environment. Its initial
public progress reached QUIESCE, DRAIN and APPLY, then the entrypoint stopped
with `INVALID_DEPLOYMENT_CONFIG:upgrade-apply-failed` and explicit
`next=diagnose-operation-before-retry`. It did not install the candidate.

The controller's retained public log is
`/home/hortonolite/work/task115-test-upgrade-logs-01a12b33/relay-e3ade68311d3-upgrade-en95pynm.log`.
Its relevant sanitized failure is:

```text
TASK [Retain the first activation snapshot in the exact protected admission operation]
/opt/codex-relay-test/relay-admission snapshot --operation 73034a9b-47a1-4ec3-993a-166560bfd39e
stderr: {"code":"ADMISSION_SNAPSHOT_INVALID"}
rc: 1
PLAY RECAP: ok=50 changed=0 unreachable=0 failed=1 skipped=11
```

Read-only supported `/opt/codex-relay-test/relay-admission status` then reported:

```json
{
  "version": 1,
  "phase": "recovery-required",
  "operationId": "73034a9b-47a1-4ec3-993a-166560bfd39e",
  "target": "e3ade68311d3c328b18ef840a4744d5bfd468bc5",
  "previousActive": null,
  "verifiedRevision": null,
  "active": [],
  "unknown": []
}
```

Post-failure public inventory still observes installed
`dbfea1889da994791a5b6c05d97a71405d21eac5`, equivalent configuration and no
inventory blockers. That inventory result does not resolve the protected
recovery-required admission operation. The failure is introduced by candidate
`e3ade683...` relative to installed `dbfea188...`: the old installed admission
helper accepts exactly `reviewer`, `production` and `general` service snapshot
keys, while the candidate's pre-install snapshot supplies a fourth
`manualOutcome` key to that old helper. The public log observes the three
existing services loaded/active/enabled and the new socket absent/inactive;
the failure occurs before its first activation snapshot is retained.

The exact operation and original source remain preserved. No retry, target
rebind, state reset, private backend, permission/service mutation or historical
fixture cleanup was attempted. A compatible source correction and an explicitly
qualified supported recovery path are needed before TEST qualification can
continue. New installed socket/Writer transport, connected MCP discovery and
a v4 manual-result fixture remain unqualified. Production was not upgraded and
the original Task 115 Writer publication binding was not changed.

The TEST README records this boundary in a subsequent documentation-only
commit, `b63236c0f4965f0c2636c04ceb1c59ad2eb6da2d`, published on the same draft
PR 3. The configuration and generated projection remain unchanged. The cited
projection/native-CI receipt above belongs to `7b0464e...`; later checks must
be read from their exact native candidate records.

## Supported same-operation TEST recovery disposition

The installed admission helper's `recovery-target` command deliberately permits
changing an exact target while `recovery-required`, bound to the same operation
and with no active/unknown attempts. It preserves `previousActive`; this is the
existing recovery interface, not an operation reset. Public `relay-deploy.py`
exposes it only inside `upgrade --authorize-upgrade
--authorize-lifecycle-recovery --lifecycle-recovery-operation <UUID>` after
checking bound status and obtaining the host apply mutex. It then returns the
same operation to APPLY, performs final verification and resumes only after
matching same-operation proof.

The first failed invocation's public operation inspection found no ordinary
production mutation record and failed before its begin task. The subsequent
read-only public `check` again reports `PRODUCTION_RECONCILIATION_STATE=STABLE`
and skips reading an absent ordinary record. The separately retained admission
gate remains `recovery-required`; `STABLE` here describes the ordinary
apply/activation journal and does not reopen admission or complete recovery.

Current Task 115 owner authority and its trusted Decision/Request cover verified
isolated TEST fixes and supported recovery. The scoped disposition is to select
the corrected published CI-green Task 115 development candidate as the TEST
recovery target in operation `73034a9b-47a1-4ec3-993a-166560bfd39e`, after its
consumer selector/projection are committed and publicly verified, status again
shows no active/unknown attempts, and the public guard confirms no intervening
ordinary mutation record. This does not claim independent source acceptance,
authorize production recovery or permit protected file edits. The selected
corrected target must be supplied explicitly; no recovery invocation has yet
been made. No install/rollback to the known broken `e3ade683...` is required by
the existing helper ABI merely to change target through this supported path.

The scoped recovery disposition is also published in the TEST README at
`6c7101111c5144a0b07858b87ce6fb37dcbf92ec`; its
[native consumer check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38150244453/job/114502015652)
passed. This documentation commit did not change the target, projection or
protected operation.

## New native fixture admission boundary

Read-only GitHub inspection confirms that TEST `main` still carries routing
blob `4576c3ccea631ed96e6adb7ef4e1df2356eba1c8` and workflow-manifest blob
`49ec662f3ff078741689379235f4ad346c289c28`, both from the old
`relay-workflows-v2` projection. PR 3's new projection is
`relay-workflows-v3`. The routing job requires owner `foal`, the corresponding
triggering actor and `github.ref == refs/heads/main`. It checks that the
installed release contract equals its explicit `EXPECTED_WORKFLOW_CONTRACT`
before routing; mismatch throws `INSTALLED_RELAY_IDENTITY_MISMATCH`.

Therefore, after a v3 workflow-contract installation, a ready-label or manual
dispatch through current `main` cannot create a new v4 manual admission using
the old workflow. Dispatching the unmerged PR branch fails the main-ref job
condition and is outside the existing only-main workflow runner restriction.
No alternate supported fixture admission route has been identified:
`publish_task_authority` authors native authority, while
`submit_manual_outcome` only submits results for an already admitted manual
attempt. Neither supplies a replacement run/admission authority.

Genuine new v4 manual-ready/Actions qualification consequently requires
independent consumer review and ordinary owner merge of compatible generated
workflows into TEST `main`. Current authority does not authorize that merge.
Compatible installation, socket/service qualification and connected capability
discovery remain separately admitted TEST activities, but cannot establish this
live Actions/one-Outcome fixture proof before the projection boundary is
resolved. No consumer merge, base-branch change, runner-policy change, fabricated
run environment, direct root worker or nested model execution was used.

## Completed read-only recovery diagnosis

The public `check` invoked from exact `e3ade683...` completed in 297 seconds:
`RELAY_DEPLOYMENT_RESULT=PASS;phase=check`. Its controller log is
`/home/hortonolite/work/task115-test-upgrade-logs-01a12b33/relay-e3ade68311d3-check-0ce74ckx.log`.
The recap was `ok=323 changed=14 unreachable=0 failed=0 skipped=144`; those
fourteen changes are Ansible check-mode plans, not performed installation.
`PRODUCTION_RECONCILIATION_STATE=STABLE` and the skipped ordinary-record read
confirm the absent mutation record at this observation. Bound public admission
status afterwards remains `recovery-required`, operation `73034a9b...`, target
`e3ade683...`, null activation snapshot/verified revision and no active/unknown
attempts. No recovery or admission reopening accompanied diagnosis.

## Corrected candidate prepared; target recovery held

The snapshot compatibility correction is published at exact product
`d11f65218eaa57e8fd48f753231e21088c87e94b`. Both required native jobs succeeded:
[Candidate checks](https://github.com/jresearchsoftware/codex-relay/actions/runs/38150552349/job/114502933369)
and [Codex CLI compatibility](https://github.com/jresearchsoftware/codex-relay/actions/runs/38150552349/job/114502933352).
The correction supplies the historical three-service snapshot to the old
installed helper when the new socket is absent, retaining existing service
intent before installation.

The separate TEST branch now selects that exact corrected development target
at `3fe97cc7b8bee890471216d5613fda9220929810` in the existing draft PR 3.
Both consumer checkouts are clean. The public exact-source `workflow-project`
and `workflow-verify` succeeded with that committed consumer head; projection
was already equivalent `relay-workflows-v3`, so no additional generated bytes
or empty projection commit were needed. Eight native Linux consumer tests,
whitespace validation and the
[exact-head native consumer check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38150735987/job/114503483855)
passed. The TEST PR description records the selected source, prior failure,
native proof and current limits.

This preparation changes no installed source, protected operation target,
activation, credentials or runner policy. Recovery, installation and TEST main
merge remain held for the owner's concrete consumer-PR disposition. The
original retained operation still requires fresh bound public status and the
same-operation guard before any subsequently authorized target action. No
new fixture or model execution was launched.

## Peer-audit finding before target recovery

A subsequent peer audit found a P2 legacy admission regression introduced in
the Task 115 routing template at `e3ade683...` relative to baseline
`b4cb4943...`, and retained through `681f091...`. The generated Actions
run-name expression used substring `contains` to detect
`Authority model: github-native-v1`. A valid legacy Issue quoting that marker
inside ordinary prose was consequently displayed as native authority, hiding
its legacy Step label. Trusted Writer still classified the Issue as legacy and
could reject the inconsistent native run title with `STEP_DISPLAY_MISMATCH`.
The baseline routing expression always displayed the legacy labels and did
not introduce that substring classification.

This is an introduced source/template compatibility defect, not an installed
TEST regression: the candidate has not been installed and TEST main still
uses v2. Prior deterministic CI success did not cover this quoted-marker case.
The product correction and meaningful projection/admission checks are being
prepared in the same Task. TEST PR 3 remains at `3fe97cc...`, and recovery,
installation and merge remain held. A corrected published CI-green target
must replace its selector and regenerate the routing/manifest projection
before a concrete final consumer review/merge or target recovery.

## Selected historical review inputs

The historical [Task 76 Writer Outcome](https://github.com/jresearchsoftware/codex-relay/issues/76#issuecomment-6022132933)
records `REINSTALL_FOREIGN_UNIT_WARNING` for pre-existing
`/etc/systemd/system/actions.runner.jresearchsoftware-ai-pr-flow-canary.debian-codexexp-01.service`,
then observed root:root mode 0664 outside TEST ownership. This is a retained
Task 76 warning, not a new Task 115 host observation, installation defect or
remediation authority. Current qualification stopped before installation and
does not dispose that historical warning. No foreign-unit read, permission
repair or service mutation was performed for this Task.

The old post-merge [native CI run 37536691150](https://github.com/jresearchsoftware/codex-relay/actions/runs/37536691150)
records an `ENOENT` `collectProgress` object-directory race on the unchanged
baseline/reviewed/accepted lineage `5a4b787...` / `2d0613c...` / `afb2cbdb...`.
The deleting process/cause remains undetermined; no introduced regression is
established by that record. Current Task 115 Node/native-CI success neither
changes the old native record nor resolves its cause. These selected historical
inputs remain immutable review context and do not expand current execution or
qualification scope.

## Final corrected consumer projection and retained boundary

Product correction `44f97a8000eac6f3c6284b32c62f574d7b8edd7b` replaces the
substring run-title classifier with standalone LF/CRLF native marker checks.
Both required exact-head native jobs passed:
[Candidate checks](https://github.com/jresearchsoftware/codex-relay/actions/runs/38152427265/job/114508442037)
and [Codex CLI compatibility](https://github.com/jresearchsoftware/codex-relay/actions/runs/38152427265/job/114508442174).
Source tests and the parent's read-only peer audit close the P2 in source;
the latter reports 56 expression/parser cases: 22 native LF/CRLF/mixed,
20 legacy and 14 malformed-parser rejections. This is peer source evidence,
separate from installed behavior and independent exact-head acceptance.

The TEST selector/README commit is `65d1e3e95c9ffba272ab14185d6f8feeef637b58`.
Supported exact-source public `workflow-project` regenerated only routing and
its manifest digest. Their inspected changes were committed and non-force
published in the same draft PR 3 at final consumer head
`944eda973981d94ec7cefd69a375ca71b116e1c6`. Routing SHA-256 now equals
`84229930ce49e2135a9c7254fb1ec1b63fac64592c6dd2f049528d60f8c5b635`;
recovery bytes remain at
`323aeb4544b5834ae1dafaec09d2ce4b5551f59b7cfab771f5b6b72e0f6ed342`.
Public exact-source `workflow-verify`, eight native Linux consumer tests,
whitespace validation and the
[native consumer check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38152709600/job/114509269890)
passed. The refreshed PR description reports the exact selector, proofs and
retained limits; PR 3 remains open/draft and unmerged.

The clean native product checkout is
`/home/hortonolite/work/task115-test-inventory-source-01a12b33` at `44f97a8...`;
the clean native consumer is
`/home/hortonolite/work/task115-test-consumer-01a12b33` at `944eda9...`.
The native consumer config is a regular single-link nonsymlink file, owner
UID/GID 1000, mode 0644, selecting exact `44f97a8...`. The Windows review
checkout is synchronized to the same published consumer head.

Fresh exact-source public inventory observes installed
`dbfea1889da994791a5b6c05d97a71405d21eac5`, equivalent consumer/deployment
configuration and no inventory blockers with `readOnly: true` and
`mutationAuthorized: false`. Bound public admission status still retains
operation `73034a9b-47a1-4ec3-993a-166560bfd39e`, target `e3ade683...`, phase
`recovery-required`, null activation snapshot/verified revision and no
active/unknown attempts. These observations do not clear the retained operation.
Owner-admin App/runner/ingress proof gaps remain explicit. No target recovery,
main merge, installation, new fixture, model call or production mutation
accompanied final projection preparation. Consumer review/merge and the
subsequently qualified same-operation recovery remain distinct pending gates.

## Connected TEST Reviewer evidence gap

The parent's fresh connected TEST `read_pr_review_evidence` call at exact
consumer PR 3 head `944eda973981d94ec7cefd69a375ca71b116e1c6` verified target
binding and reported zero check annotations. It nevertheless reported
`required_surfaces_complete: false` and `warning_observation: unknown`, with
`CANONICAL_ISSUE_AMBIGUOUS` and `GITHUB_EXECUTION_RUN_POINTER_UNAVAILABLE`.
PR 3 is a consumer configuration/projection PR, not a new admitted TEST
execution fixture. These are evidence gaps under the existing installed
schema-v3 aggregation contract; no Task 115 introduced regression is established
by this observation. No arbitrary Issue/Task linkage, remediation execution or
new authority was added to manufacture complete surfaces.

The separately scoped product PR 118 evidence at `44f97a8...` had complete
required API surfaces, zero check annotations and an empty inspected native UI
annotation surface. It does not resolve the consumer aggregation/run-pointer
gaps. Consumer native CI success and verified exact target likewise do not
establish global warning absence or independent Reviewer acceptance. The
unresolved TEST evidence gaps remain material inputs to the next review/owner
boundary alongside the preserved recovery-required operation.

## Canonical TEST autonomy and exact consumer merge

The resumed same-Step owner clarification is recorded by trusted
[Decision 6112655517](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6112655517)
and [successor Request 6112661946](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6112661946).
Live read-back verified Bot identity 306850842 and respective body SHA-256
`d08cd6a43de555e2d7bc6678ba6060efb075cb19349c484b75bf55cf83037a80` and
`8a49967ddf924bec46220e05646936beee0d94cb7ad5d97bb3fb8c0ee593ba8b`.
They explicitly authorize the verified isolated TEST full cycle, including
reviewed TEST PR merge and supported same-operation recovery, while excluding
product PR 118 merge, PROD, shared/foreign infrastructure and external App,
permission or credential changes. No original Task 115 admission/journal was
rewritten. The standing policy is the single
[TEST Environment Authority](https://github.com/jresearchsoftware/codex-relay/blob/6ae8f984aed8596411a62b6490d096c7030b6f0c/docs/execution-policy.md#test-environment-authority);
that policy commit changes documentation, not the selected TEST runtime source.

Fresh PR 3 inspection verified unchanged head `944eda9...`, base `52d6630...`,
five bounded configuration/runbook/projected files, native candidate CI success,
MERGEABLE/CLEAN status and no new findings from the prior scoped peer audit.
PR 3 was marked ready and squash-merged through the ordinary owner interface
with exact `--match-head-commit 944eda973981d94ec7cefd69a375ca71b116e1c6`.
No admin/force merge, branch deletion or self-authored Reviewer verdict was used.
GitHub read-back confirms merged by `foal` at 2026-10-11 19:14:18 UTC, exact
merge/main SHA `4598e74602b02247adebbaba71ecccf33958da9d`.
The [native main candidate check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38167160268/job/114551998276)
passed at that exact SHA.

Windows consumer `main` and the clean detached native consumer now match
`4598e746...`; the earlier reviewed branch is preserved. Exact-source public
`workflow-verify` passed for selected runtime `44f97a8...` and consumer
`4598e746...`. Fresh pre-recovery inventory still observed `dbfea188...`,
equivalent configuration and no blockers. Bound public status retained the
same recovery-required operation, old target `e3ade683...`, null activation
snapshot/verified revision and no active/unknown attempts. The consumer
main-projection prerequisite is resolved; the separate installed recovery and
MCP/one-Outcome proofs still require their actual receipts.

The exact source diagnosis is that `step_sync::linked_issue` recognizes one
same-repository `Related to #N` / closing-keyword reference in the PR body.
PR 3 instead points to its authorized cross-repository Task 115 URL, leaving
zero recognized same-repository IDs. The outcome source consequently remains
unavailable, which also prevents the execution source from establishing absence.
Comparison of installed-source revision `dbfea188...` with `44f97a8...` shows
that this linkage and incomplete-source behavior is unchanged. The synthetic
owner-authored native COMMENT is excluded by Writer-actor filtering. The gap
does not establish an introduced product defect and requires no fabricated
TEST Task link. Signed-in Chrome also showed success and an empty Annotations
section for native consumer run `38152709600`; that scoped UI observation
does not close the outcome/execution aggregation gap.

A final read-only peer comparison of consumer `944eda9...` against
`52d66305557a74264cd0f5b82ec0b90804baa98c` verified the complete five-file
diff, exact renderer/manifest bytes, canonical regular file modes, valid
configuration and unchanged protected guards. Its 56 marker and eight guard
cases passed, with no material findings in that bounded consumer audit. This
qualifies the prepared projection, not execution of the installed workflow,
independent product acceptance or permission to merge/recover the target.

## Supported recovery: staged Reviewer schema failure

The canonically authorized public `upgrade --authorize-upgrade
--authorize-lifecycle-recovery --lifecycle-recovery-operation
73034a9b-47a1-4ec3-993a-166560bfd39e` resumed that same retained TEST operation
with exact source `44f97a8000eac6f3c6284b32c62f574d7b8edd7b` and merged consumer
`4598e74602b02247adebbaba71ecccf33958da9d`. It passed the older installed
snapshot compatibility boundary and reached protected artifact staging. It
failed at the locked Rust Reviewer release build: `task_authority.rs:17`
includes `../../contracts/src/github-authority-v4.json`, but the artifact
staging task copies only `github-authority-v1.json`. This is a concrete Task
115 deployment packaging omission; local Rust builds have the full source
tree and therefore did not qualify this staged layout.

The backend recap was `ok=168 changed=20 unreachable=0 failed=1`; this is a
partially applied upgrade, not the earlier pre-install failure. The public
entrypoint returned `INVALID_DEPLOYMENT_CONFIG:upgrade-apply-failed` with
`next=diagnose-operation-before-retry`. The raw private log
`relay-44f97a8000ea-upgrade-m1o38pd6.log` is retained locally; no credential or
private configuration contents are reproduced here. The compiler also emitted
two `unused_mut` warnings at `github.rs:350` and `:399`; those same declarations
exist on installed source `dbfea1889da994791a5b6c05d97a71405d21eac5`, so these
warnings do not establish an introduced Task 115 regression.

Fresh bound public admission status reports `recovery-required`, the same
operation UUID and target `44f97a8...`, `verifiedRevision: null`, and empty
active/unknown attempt arrays. Unlike the first failed upgrade, its retained
`previousActive` snapshot now records Reviewer, production runner and general
runner as active, enabled and loaded. The current installed pointer still
names `dbfea1889da994791a5b6c05d97a71405d21eac5`. Those observations preserve
activation intent; they do not prove that the staged target is complete or
that the old installation was untouched. No retry, activation, release cleanup,
operation reset, fixture admission or MCP Outcome submission followed the
failure. Installed manual socket and new Reviewer capability remain unqualified.

Source inspection also identifies a separate recovery constraint: an ordinary
retained apply record binds its exact failed source head, while existing
stale-apply disposition requires a completed release at that recorded head.
The old current pointer cannot be asserted to be a completed `44f97a8...`
apply. The next action is supported read-only classification of the retained
ordinary operation, then an evidence-bound public recovery disposition; a
new corrected source does not itself authorize bypassing those guards.

The subsequent supported public `--phase check` confirmed an ordinary retained
`apply` record at exact `44f97a8...`. Its classifier observed Reviewer and
production runner active/enabled, listener present, activation authorized,
registration evidence valid, no reactivation required and planned scope
`preserve-reviewer-and-runner`. It explicitly reported
`mutation_boundary=matching-phase-and-exact-head-only` and
`apply_state_hash=not-applicable`. The read-only recap was `ok=45 changed=0
failed=0 skipped=17`; the public entrypoint deliberately remained blocked as
`recovery-requires-disposition`. The private log is
`relay-44f97a8000ea-check-yujl26bq.log`. This narrows the next recovery decision
without retiring the record or claiming that a different target is admitted.

The scoped source audit found no truthful existing public continuation for this
exact incomplete apply. Matching recovery would replay the broken `44f97a8...`
source; a different target or rollback conflicts with the retained ordinary
head binding. Reinstall decommission refuses that record, while reinstall
recovery requires a DECOMMISSIONED journal that this operation did not create.
Completed stale-apply disposition requires a current release at the recorded
head; bootstrap-only disposition requires absent runtime state. Neither shape
matches the observed old current pointer and existing installation.

`site.yml` runs `relay_runtime` before `relay_artifacts`; therefore the twenty
changed tasks can include managed wrappers, configuration or units before the
artifact failure and pointer switch. Observed active old services and the old
current pointer do not prove byte equivalence of the installation. No extra
protected file inspection or invented runtime inventory is claimed. The
retained raw logs, journal and activation intent remain preserved. Task 115
will correct and validate the packaging omission in source, but this bounded
Task does not invent a new partial-apply disposition protocol. Further host
mutation needs a precise supported recovery disposition; no reset, bypass,
retry, reinstall, activation or fixture admission is performed here.

The useful consumer runbook correction is committed and pushed as final head
`adc3937fa2f64e4d722cc3ca528a3fcdc10d5f71` on
`codex/task-115-test-recovery`, in draft
[TEST PR 5](https://github.com/jresearchsoftware/codex-relay-testbed/pull/5).
Its sole changed file is README: it references the single standing TEST policy,
replaces the obsolete PR 3 merge hold, distinguishes the two upgrade failures,
and records the actual partial-state/public-recovery boundary. The config,
selected source and projected workflows retain merged main `4598e746...` bytes.
Native Linux eight scenario/isolation tests and whitespace validation passed.
The [native candidate check](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/38168457362/job/114555825705)
completed successfully at exact `adc3937...`, with API check annotation count
zero. Windows branch and detached native
consumer match that published head and are clean; no unpublished consumer
commits remain. PR 5 remains draft and unmerged. This repository handoff
preserves progress without another host operation or a successful E2E claim.

Read-only native metadata inspection verified both new raw logs as UID/GID
1000, mode `0600`, regular non-symlink files with one link. They remain outside
the repositories and are not copied into publication or committed:

| Private log basename | Bytes | SHA-256 |
| --- | ---: | --- |
| `relay-44f97a8000ea-upgrade-m1o38pd6.log` | 127588 | `20e94501e46936beafe9f1986d5b24cfaf90633eba49e989d32f4fe6b62d3744` |
| `relay-44f97a8000ea-check-yujl26bq.log` | 10782 | `580163d7e1efd792561c10e40a64da31f33510355026b569e0a6fa23cfc4be50` |

A sanitized extraction of task headings and changed markers, excluding all
parameters, invocations and returned contents, identifies exactly twenty
changed tasks (29 changed item lines). Four are the ordinary operation
reservation and runtime installation of the stale-disposition helper,
Reviewer activation helper and Reviewer configuration contract. The remaining
sixteen are artifact namespace/object/source/build-input staging tasks,
including stable routing/recovery invocation paths and staged Writer,
dispatch and diagnostics artifacts. The observed task footprint confirms
managed helper/configuration changes before the failed build; it does not
prove every resulting byte, process identity or completed installation.
