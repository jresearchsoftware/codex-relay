# Task 115 bounded qualification observations

This note records source, TEST and original-publication observations for the
same owner-launched manual Step 1. It is evidence for the current Task/PR, not
another authority registry. No independent acceptance, product merge, Issue
closure, production installation or deployment is claimed.

## Current authority and immutable admission

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
