# Task workflow

The canonical Relay user manual is maintained in the
[Codex Relay Skill](../packages/codex-relay/skill/SKILL.md). Read its
[workflow](../packages/codex-relay/skill/references/workflow.md) and only the
conditional references needed for the current action. The separately packaged
manual is guidance, not proof that a consumer installation or connected App is
qualified. [Guidance maintenance](relay-guidance.md) covers source assembly and
provenance; product contracts remain the implementation references below.

## Owner acceptance and execution routes

See the manual's [owner acceptance and execution routes](../packages/codex-relay/skill/references/workflow.md#owner-acceptance-and-execution-routes)
for verified owner acceptance by merge, expressly authorized standalone/manual
work and the distinction from Relay-admitted results. Internal continuation
mechanics live in the [owner adapter contract](../contracts/README.md#authorized-continuation-after-independent-acceptance).

## From Task to completion through Relay

Follow the manual's [authoring and admission](../packages/codex-relay/skill/references/workflow.md#author-and-admit-current-work),
[result publication](../packages/codex-relay/skill/references/workflow.md#one-canonical-outcome)
and [independent acceptance and continuation](../packages/codex-relay/skill/references/workflow.md#independent-acceptance-and-authorized-continuation).
Implementers use the [authority](../contracts/README.md#github-native-task-authority),
[routing](../controller/README.md) and [Reviewer capability](../reviewer/README.md#current-protocol-capabilities)
contracts. The [Issue template](../.github/ISSUE_TEMPLATE/codex-task.md) remains
the repository authoring baseline.

## Decisions, closure and subsequent work

See the manual's [decisions and closure](../packages/codex-relay/skill/references/workflow.md#decisions-closure-and-subsequent-work).
Internal definitions live in [Task authority](../contracts/README.md#github-native-task-authority)
and [closure authoring](../contracts/README.md#closure-policy-authoring).

## Native PR Change Requests

See the manual's [Change Requests and remediation](../packages/codex-relay/skill/references/workflow.md#change-request-and-remediation).
The [controller contract](../controller/README.md#same-cr-continuation-after-a-blocked-result)
defines same-CR continuation after a blocked result; the
[Reviewer contract](../reviewer/README.md#independent-review-and-finding-provenance)
defines independent finding provenance.

## Visible evidence, warnings and recovery

See the manual's [warning evidence and recovery](../packages/codex-relay/skill/references/diagnostics.md)
and [canonical Outcome](../packages/codex-relay/skill/references/workflow.md#one-canonical-outcome).
Repository development retains its [execution policy](execution-policy.md),
[warning disposition](execution-policy.md#execution-warning-disposition) and
[TEST Environment Authority](execution-policy.md#test-environment-authority).

## Installed and in-flight compatibility

See the manual's [installed protocol and retained-attempt compatibility](../packages/codex-relay/skill/references/compatibility.md).
Internal v4 and retained-v3 definitions remain in the
[authority contract](../contracts/README.md#github-native-task-authority).
Repository [AGENTS.md](../AGENTS.md) and
[CONTRIBUTING.md](../CONTRIBUTING.md#keep-workflow-documentation-current) retain
local development instructions and documentation-maintenance obligations.
