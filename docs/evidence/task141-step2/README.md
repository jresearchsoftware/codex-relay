# Task 141 Step 2 — Phase B projection preparation

The accepted Phase A product used for this preparation is exactly
`5845433f3bae8c74a32f8234466fd98eb2268464`. Phase B prepares a Relay source PR
and external opt-in proposals. It grants no installation, consumer activation,
runner administration, credential, merge or release authority. Task 141 remains
open for external owner dispositions and the separately authorized Phase C
rollout. This document is supporting evidence for the canonical Writer Outcome,
not another Task contract or an independent acceptance record.

## Self-dogfood projection

The public `workflow-project` interface ran successfully while the product and
consumer checkout were clean at that exact accepted SHA. It added the explicit
`RELAY_REPOSITORY: jresearchsoftware/codex-relay` environment binding already
present in the accepted routing/recovery templates and refreshed their schema-2
manifest digests. No template, eligibility policy or lifecycle workflow changed.
The repository selector is checked against protected consumer configuration; it
does not enroll another repository or enlarge the runner group's trusted set.

Projection inputs reconstruct only the existing public workflow wiring. Start
with `deploy/tests/test_consumer_workflows.py:self_config()` and set
`environment.generalRunner.scope` to `organization` and its `group` to
`codex-relay-general-runner`, as recorded in the prior committed workflows.
All unrelated example deployment/App/host fields are synthetic and unused by
projection. This reconstruction is not a read or assertion of installed owner
configuration. The temporary full input was private (`0600`) and remained local.

The invocation, with absolute paths to that local input and the clean checkout,
was:

```sh
python3 deploy/relay-deploy.py --config "$PROJECTION_INPUT" \
  --consumer-root "$CONSUMER_CHECKOUT" \
  --resolved-revision 5845433f3bae8c74a32f8234466fd98eb2268464 \
  --phase workflow-project --authorize-workflow-projection
```

Both public result markers were PASS. Direct `workflow_projection.verify` and
byte-for-byte rendering/manifest checks bind the prepared files to those inputs
and the accepted templates. Before installation, the reviewed clean consumer
commit must also pass the public `workflow-verify` command from a separate clean
checkout of the exact accepted product. No reviewed consumer merge or installed
verification is claimed here.

| Managed file | SHA-256 after projection |
| --- | --- |
| `.github/workflows/codex-relay-routing.yml` | `09feb465605bdbc416521bbf2b2fe00b9e4affd77d11dbc0c5740500476d3a2e` |
| `.github/workflows/manual-writer-publication-recovery.yml` | `79b8c33dd43164f970c3186a09903f30b11c7a6b4d4f3076a43817aebb6805be` |
| `.github/workflows/manual-main-production-deploy.yml` | `7c4dc6ef95407e64f9e4e27915ee56d9e2b2f6d64a56f60058fe7dd0b25a43da` (unchanged) |

The workflow ABI remains `relay-workflows-v3`. Schema-v4 Task governance and the
v4 workflow ABI are distinct. Configured execution slots (including slots
derived from managed-pool configuration) select the latter; this session has no
qualified installed slot/pool configuration. Switching self-dogfood to v4 now
would invent that operational evidence. A future reviewed v4 projection must
use real owner-selected configuration and a compatible qualified installation.
No live capacity, overlap or consumer adoption follows from these artifacts.

## Proposals and rollout disposition

The [consumer proposals](consumer-workflow-proposals.md) cover Shared Governance,
Model Landscape and DocReview without writing to those repositories. Shared
Governance's public main/governance was inspected at a pinned revision; its
native publication and acceptance choices require explicit local reconciliation
before an optional Relay lane. Landscape and DocReview public reads returned
404. Their proposals preserve the Task-supplied direct-main research and native
corporate/model/reviewer boundaries, and identify unavailable accepted-governance
evidence as a prerequisite to a concrete external admission. No external PR or
workflow was created, merged or activated.

The [lifecycle analysis](lifecycle-runner-analysis.md) identifies the third
self-dogfood workflow as protected owner lifecycle transport on General,
separate from Production. Its singleton `RUNNER_NAME` guard fails if a future
managed scheduler selects another member. Phase B preserves it and specifies
owner choices and qualification before six-member rollout. The analysis also
distinguishes Task 85's unresolved successor-Step admission from lifecycle drain:
Phase C must inspect original protected records/readers, while Task 140 retains
its independent remediation ownership.

The next owner/review boundary must retain these limits: independent exact-head
source acceptance and owner continuation are outstanding; all external
adoption/merge decisions are independent; actual PROD/shared mutation needs
explicit published target-specific authority. No installation inventory or
operational qualification of App access, runner restrictions, native concurrency
or recovery was performed. Local validation diagnosed ambient filesystem,
systemd-unit and cgroup coupling as described below; those observations do not
establish rollout readiness.
GitHub/runtime primary warning annotations were unavailable under this worker's
no-credentials/no-publication boundary; their absence is not asserted. Trusted
publication/review must inspect the supported primary warning surfaces.

## Local validation

Validation runs unprivileged on Linux. Node 22.20.0, Rust/Cargo 1.90.0 and Python
3.11.2 were available through local tool paths; pytest 8.4.2 was loaded from an
existing tool package without installation or host changes. Test scratch space
was placed outside the source checkout. The initial focused run used the
session's checkout-contained temporary directory and hit the existing
`projection-output-outside-checkouts` rule; rerouting scratch space resolved it.

Three bounded helpers supported proposal research, lifecycle analysis and a
focused consistency check. Subagents were used within admitted permission;
actual model/effort runtime evidence was unavailable (`UNAVAILABLE`). Requested
profile values are not actual-profile proof. Source tests and helper analysis
do not replace native CI or independent review.

The following checks passed:

- Exact accepted product input comparison, deterministic workflow bytes and all
  manifest hashes; the owner lifecycle file remains byte-identical.
- Focused projection, consumer workflow, managed workflow and production
  workflow tests: **29 passed**.
- `cargo fmt --manifest-path reviewer/Cargo.toml --check` and
  `cargo test --manifest-path reviewer/Cargo.toml --locked`: **133 passed**.
- `python3 scripts/qualify.py`: **THREE_CONSUMER_PASS**, using synthetic consumers,
  isolated Git and loopback mock GitHub; no installed or live consumer proof.
- `python3 scripts/check-candidate.py` after staging additions, and whitespace
  checks of both staged and working changes.

Full-suite results were not green in this sandbox. With a private synthetic
consumer copy, `umask 0022` and UTF-8 locale, the final complete `npm test` run
reached **971 passed, 2 failed, 2 skipped**. The remaining failures are:

- `manual root helper refuses a nonroot caller before Writer access` directly
  references the checkout's `0660`, `nobody:nogroup` synthetic consumer fixture;
  the secure loader rejects it before the intended helper assertion.
- `retained release containing the adapter verifies its exact graph before
  preserving original SERIAL context` copies the group-writable checkout
  source and hits `SERIAL_POOL_COMPATIBILITY_SOURCE_UNSAFE`.

The initial session umask `0007` also made newly created SERIAL fixtures unsafe;
using `0022` resolved those additional failures. No original checkout permissions
or security checks were changed to bypass either remaining failure.

The complete deployment/Ansible suite with corrected fixture umask and private
consumer input reached **1209 passed, 100 failed, 349 skipped**. A UTF-8 retry of
those failures reached **32 passed, 68 failed, 41 deselected**. Its output also
identified Ansible attempting to create temporary directories outside the
worker's writable roots. With task-local `ANSIBLE_LOCAL_TEMP` and
`ANSIBLE_REMOTE_TEMP`, the final failed-test retry reached **54 passed, 14 failed,
39 deselected**. The remaining failures have these observed causes:

- Two fixture `chown` calls and one native ACL `setxattr` return `EINVAL` in the
  worker sandbox.
- Four eligibility tests expect a group/ref rejection but encounter
  `MANAGED_POOL_ELIGIBILITY_PARENT_UNSAFE` first: the sandbox's `/` and `/opt`
  have UID 65534, while the protected path reader requires root ownership.
- Three positive preflight fixtures use the real `/etc/systemd/system` default.
  A read-only diagnostic using the exact source-matched fixture arguments
  exposed `RELAY_INSTANCE_UNIT_COLLISION` beneath their generic rejection.
  The tests do not isolate all unit names from ambient installed units.
- Four SERIAL host fixtures mock service state but leave `Host.removal_stopped`
  reading absolute `/sys/fs/cgroup` paths. The example General Runner cgroup
  exists with processes, so the real stopped proof rejects the mocked inactive
  state before the fixture's expected disable call. No processes were signaled.

These failures are retained, not counted as passes. No protected state or
permissions were repaired. Eighteen full-suite warnings were Jinja invalid-escape
deprecations. The complete deployment suite still needs a qualified environment;
passing another native check does not establish that this full suite ran. The
required exact-head native CI and root/sudo boundary proof remain outstanding
after trusted publication. No privilege escalation or installed-runtime mutation
was attempted.
