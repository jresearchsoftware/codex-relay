# Task 141 Step 2 Phase B: owner lifecycle runner analysis

Source baseline: accepted product/start revision
`5845433f3bae8c74a32f8234466fd98eb2268464`, branch `codex/task-141`.
This is source evidence and a proposed qualification plan. No installation
inventory or operational qualification was performed; local test diagnostics
of filesystem, unit and cgroup coupling are recorded in the
[validation evidence](README.md#local-validation). No GitHub settings,
credentials or services were changed, and actual runner execution was not
qualified. The Phase B admission permits
preparation and analysis; it does not authorize changing the protected lifecycle
workflow or its guard, Apply, activation or external administration.

## Finding and immediate disposition

The owner lifecycle template selects the General Runner pool when managed pool
configuration is supplied, but its shell guard still requires the one original
General Runner name. Routing and recovery use the generated pool identity guard;
owner lifecycle does not. Consequently a lifecycle job scheduled to members 2–6
of a proposed six-member pool fails at its first `test`, before resolving the
installed release or calling the protected helper. Member 1 retains the original
name and passes that name check when its Unix identity also matches. This is a
source-derived failure path, not evidence of an observed installed failure.

Keep the existing guard and all protected restrictions in Phase B. Stop before
six-member activation or a claim that owner lifecycle works across the pool.
Completing this analysis and preparation does not require a guard change. An
owner-authorized disposition and qualification are needed before the future
rollout depends on a changed lifecycle scheduling contract.

## Existing workflows, ownership and scheduling

The third Relay-managed self-consumer workflow is the existing
`.github/workflows/manual-main-production-deploy.yml`, named **Owner Relay
lifecycle**. It is not a worker workflow or an arbitrary extra General Runner
allowlist entry. It offers only `apply`, `stop` and `resume`, with `contents: read`,
owner and triggering-owner checks, `workflow_dispatch`, the protected repository
and trusted base branch. It performs no checkout and downloads no candidate
action. See the [canonical template](../../../deploy/workflows/production.yml.in)
(lines 3–47) and [self-consumer contract](../../self-dogfood-workflows.md)
(lines 100–157).

| Surface | Purpose and ownership | General versus Production boundary |
| --- | --- | --- |
| Routing | Owner ready command; installed controller coordinates one admitted execution; Writer owns publication | General transport, fixed installed release; candidate code belongs in the worker sandbox |
| Publication recovery | Owner dispatch for an exact retained attempt; fixed installed Writer recovery entrypoint | General transport; managed recovery can use another active member while protected claims select original evidence |
| Owner lifecycle | Owner dispatch through one fixed protected coordinator for apply/stop/resume | Intentionally runs on General: Reviewer lifecycle changes can restart the dependent Production Runner |
| Exact-head validation | Repository-owned disposable candidate checks | GitHub-hosted validation; no access to either persistent runner |

The product owns `deploy/workflows/*.yml.in` and deterministic projection.
Consumers own reviewed workflow adoption, configuration, runner groups, external
policy and lifecycle authorization. The checked-in `.github/workflows/` files are
consumer projections, not the product editing surface; their presence does not
prove installed adoption. At this baseline the checked-in owner lifecycle file
declares `relay-workflows-v3`, the General group `codex-relay-general-runner`,
and the singleton name/user `codex-relay-general-runner`. The names “production”
in its filename/concurrency group do not place the job on Production. See
[architecture](../../architecture.md) (lines 341–351, 383–394),
[checked-in lifecycle](../../../.github/workflows/manual-main-production-deploy.yml)
(lines 22–47), and [workflow contract](../../self-dogfood-workflows.md)
(lines 24–29, 65–98).

For `localApply.source: installed`, projection includes this fixed third workflow
only for the protected `environment.repository` anchor. Configuration requires
that self-consumer source/repository and trusted branch remain `main`.
Plural Writer targets do not inherit lifecycle ownership. The pool trust contract
recognizes the anchor lifecycle ref optionally, with automatic workflows or by
itself. Selecting either routing or recovery requires both; configured targets
may remain inactive. See [config](../../../deploy/config.py) (lines 240–246),
[projection](../../../deploy/workflow_projection.py) (lines 163–169),
[pool contract](../../../deploy/managed_pool.py) (lines 34–67), and
[deployment contract](../../../deploy/README.md) (lines 161–191).

## Guard and protection paths

| Source path | Exact behavior and implication |
| --- | --- |
| [config.py](../../../deploy/config.py), lines 75–99, 338–349 | Managed configuration derives 32 stable internal resource slots, independently of desired physical capacity. Member 1 is `generalRunner.name`; members 2 onward append `-2`, `-3`, etc. All share the configured General Unix account. Pool and slot labels are deterministic. A desired capacity of six selects six physical members; it does not create six different Unix trust identities. |
| [managed_pool.py](../../../deploy/managed_pool.py), lines 52–67 | Each member has its own registration name, service and private physical state. The pool label is shared. Production is outside this pool. |
| [workflow_projection.py](../../../deploy/workflow_projection.py), lines 87–115 | Managed General selectors use the dedicated General organization group and pool label. `GENERAL_RUNNER_NAME` remains the original configured name. The default singleton guards compare name and Unix user exactly. |
| [workflow_projection.py](../../../deploy/workflow_projection.py), lines 117–162 | With slots, routing's `GENERAL_RUNNER_GUARD` becomes an exact name/user `case` over derived slots. Explicit-slot recovery binds its original slot; managed recovery reuses the pool selector/guard and removes the caller slot input. The derived allowlist has 32 resource identities; desired active capacity is enforced by managed registrations/services, not by shrinking this script. |
| [routing.yml.in](../../../deploy/workflows/routing.yml.in), lines 63–78; [recovery.yml.in](../../../deploy/workflows/recovery.yml.in), lines 51–71 | These templates consume the generated guards and selector tokens. |
| [production.yml.in](../../../deploy/workflows/production.yml.in), lines 33–47 | Lifecycle consumes `GENERAL_RUNS_ON_YAML` but directly compares `RUNNER_NAME` with `GENERAL_RUNNER_NAME` and Unix user with `GENERAL_RUNNER_USER`. It does not consume `GENERAL_RUNNER_GUARD`; pool scheduling therefore exceeds the accepted name set. |
| [production.yml.in](../../../deploy/workflows/production.yml.in), lines 48–71 | After identity checks it resolves root-owned installed source identity, exact release path and matching workflow ABI; validates action and native consumer SHA; invokes only the fixed sudo helper with `action:installed-SHA:consumer-SHA`. |
| [relay-owner-lifecycle.sudoers.j2](../../../deploy/ansible/roles/relay_runner/templates/relay-owner-lifecycle.sudoers.j2); [relay-owner-lifecycle.j2](../../../deploy/ansible/roles/relay_runner/templates/relay-owner-lifecycle.j2), lines 6–31 | The configured General Unix account has the narrow helper grant. The helper checks root and the typed argument, verifies protected installed files/parents, clears environment and enters the host mount namespace. It does not authenticate `RUNNER_NAME`; external trusted workflow access is essential when the Unix account is shared. |
| [owner_lifecycle.py](../../../deploy/owner_lifecycle.py), lines 121–209 | Coordinator verifies installed config under the namespace lock, freezes accepted main/native consumer SHA, verifies exact projected workflow bytes before quiesce, and uses same-operation apply/verify/resume. For managed Apply, pool preflight precedes gate mutation. No workflow-supplied config, executable or credential path is accepted. |
| [managed_pool.py](../../../deploy/managed_pool.py), lines 158–184; [pool_eligibility.py](../../../deploy/pool_eligibility.py), lines 98–148, 211–270 | Native group must have selected repositories and restricted exact workflow refs. Every selected repository/ref must be proved by prospective protected owner configuration or a qualifying protected installed peer snapshot. Unknown/candidate/tag/foreign refs and incomplete routing/recovery pairs fail closed. These checks read policy; they do not edit ACLs. |
| [relay-deploy.py](../../../deploy/relay-deploy.py), lines 612–623; [serial_pool_host.py](../../../deploy/serial_pool_host.py), lines 136–163, 240–257 | A required SERIAL-to-pool handover rejects local lifecycle/reconciliation and requires external owner Apply/authorized upgrade. It also refuses to stop a legacy runner carrying a worker or busy native job. Fixing the YAML name guard would not authorize migration from the listener being replaced. |

The [public dogfood trust contract](../../integration-reference.md#public-dogfood-trust)
requires protection outside candidate-controlled YAML. Names, labels, `if`, and
shell identity tests run after scheduling and cannot prevent an untrusted job
from reaching a privileged runner. Preserve the separate Production group and
its repository/exact trusted workflow/ref restrictions; it must not receive
routing, recovery or candidate jobs. Preserve the independent General group/ref
boundary, including lifecycle only at its owning anchor. See also
[self-consumer activation](../../self-dogfood-workflows.md#activation-boundary).

## Safe choices requiring owner disposition before rollout

These are task-local analysis options, not new authority or adopted policy:

1. **Defer pool activation and preserve current behavior.** Keep singleton
   lifecycle identity and the existing scheduling configuration, with installed
   qualification still requiring its own evidence. This is the immediate Phase B
   disposition and requires no source guard mutation.
2. **Retain singleton lifecycle execution inside a future pool.** An explicitly
   authorized product projection could select the stable primary member through
   its deterministic slot label while retaining exact name/user checks. Qualify
   primary availability, lifecycle transport continuity and the effect of shared
   work occupying that member. This changes observable scheduling/availability
   and needs canonical owner authority and independent review.
3. **Authorize lifecycle transport on multiple managed members.** A bounded
   product change could align its selector and exact configured name/user guard.
   Qualify every admitted identity and the protected helper path, especially
   shared-account privilege, live transport preservation and owner App key
   availability on the actual execution host. Do not replace exact identities
   with a wildcard or treat a pool label as trust proof.

Changing the guard, rerouting lifecycle to Production, silently dropping the
third workflow, broadening workflow refs or weakening external restrictions
would change a protected operator workflow. The current Phase B analysis does
not authorize those deltas. Root [AGENTS](../../../AGENTS.md#material-useroperator-contract-change-gate)
requires canonical owner disposition; absent that disposition a material change
would be `OWNER_DECISION_REQUIRED`. The cheapest acceptable current response is
the visible preparation/rollout boundary above, using existing Task/PR/review
records rather than another gate or state registry. This follows the
[proportional-controls protocol](../../../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/proportional-controls.md).

## Phase C prerequisites and qualification plan

The Task 141 Phase C target supplied in the admitted handoff is one
Writer/Reviewer serving all four authorized repositories, managed organization
General capacity six, and separate Production. One default non-root runtime
identity is sufficient unless trusted configuration selects per-repository
identities. This document supplies no installed proof for those targets.

Before actual shared/PROD mutation, use the existing protected owner-authorized
path and record explicit authority for the real target. Compare exact installed
revision/configuration, namespace and immutable admission bindings with the
selected accepted product/configuration. Inventory historical SERIAL attempts,
pending publications, original reader availability, native registrations,
services and admission state without rewriting them. Retain credentials and
protected original evidence. The [migration contract](../../serial-pool-migration.md)
(lines 24–41, 44–69, 81–124) specifies original readers, drain, handover and
same-operation forward recovery. Initial handover uses the external owner
deployment path; an installed General lifecycle job cannot replace itself.

Qualify the actual App installation/repository access and organization
Self-hosted runners permission, selected General repositories and exact trusted
workflow refs, and Production isolation. Candidate checks must remain unable to
reach either persistent runner. Do not infer adoption for all four repositories
from target configuration alone. Preserve optional inactive targets. The
[deployment contract](../../../deploy/README.md) (lines 156–191, 230–233) requires
the pool App key on the actual owner execution host; a workstation-only path
does not qualify an installed lifecycle job on another host. Credential binding
or ACL changes remain separately authorized owner operations, never workflow
inputs or files copied by this preparation.

For an authorized future source repair, use the existing focused suites
(`test_workflow_projection.py`, `test_managed_pool_workflows.py`,
`test_production_workflow.py`, `test_pool_eligibility.py`, `test_owner_lifecycle.py`
and affected lifecycle/migration suites) and the normal complete candidate
checks. Exercise a six-member lifecycle selection/guard matrix, singleton
compatibility, foreign name/user rejection, owner/ref/event rejection, unchanged
fixed helper/typed action arguments, exact release/ABI/projection failure, and
failure before mutation when App/group proof is absent. Existing tests establish
source test intent; they were not executed by this read-only investigation.

After exact-head independent source acceptance and separately authorized
installation, qualify real scheduling on the selected lifecycle transport,
General/Production separation, six physical services/registrations, concurrency
and isolated attempts, original-attempt recovery and drain. Exercise authorized
apply/stop/resume through the simplest supported owner path, preserving live
transport, retained first activity intent and quiesce on uncertain failure.
Source test PASS, a generated v4 projection, or workflow publication is not
installed v4 capability/activation proof. Reuse existing sufficient evidence at
the exact candidate; do not add a duplicate publication or approval process.

## Task 140 / Task 85 interaction

The admitted handoff identifies Task 140 as owner of the cancellation defect for
a manually admitted, never-executed Step, with Task 85 run `38964720803` reporting
`PRIOR_EXECUTION_UNRESOLVED` on later manual ready. Those are supplied Task facts;
this investigation did not inspect the live records or claim remediation.

The source distinguishes successor-Step admission from automatic lifecycle drain:

- [admission-step.mjs](../../../controller/src/admission-step.mjs), lines 5–17,
  rejects a previous admitted record without an Outcome or with unresolved
  publication/handoff intents, including manual records. A new admission cannot
  simply allocate a replacement Step over them.
- [admission-control.mjs](../../../controller/src/admission-control.mjs), lines
  123–171, validates records but skips manual routes in automatic execution
  inventory. Drain fails on unknown automatic work and waits for active work
  (lines 217–223). A pending owner-local manual publication therefore does not,
  solely by being manual and unresolved, prove that automatic drain is blocked.
- [serial_pool_installation.py](../../../deploy/serial_pool_installation.py),
  lines 150–163, invokes the original installed gate/parser/configuration.
  [Compatibility inventory](../../../controller/src/serial-pool-compatibility.mjs),
  lines 137–171, also runs the bound original reader. Current source behavior is
  not proof of the old installed reader's treatment of that exact record.

Phase C must classify the actual protected Task 85 record and original installed
reader before claiming safe drain or a migration blocker. Malformed records,
unknown host execution/containment or unresolved automatic publication remain
fail-closed boundaries. Preserve Task 85's original admission, Step, bindings
and supported publication path while Task 140 supplies its independently
authorized correction. Do not fabricate a Task 85 Outcome, delete its admission,
rewrite a digest, reopen a gate or use another route as a workaround. This
dependency assessment belongs in the existing Task authority/evidence; Phase B
does not resolve it or authorize a cancellation mechanism.
