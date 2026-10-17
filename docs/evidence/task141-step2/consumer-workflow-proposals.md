# Task 141 Step 2 — consumer workflow proposals

These are repository-specific, opt-in proposals prepared under Phase B. They
authorize no external repository change or execution. None of these external
consumers was cloned, configured, enrolled, installed or activated for this research. Public reads used
unauthenticated HTTPS with no GitHub App or credential-bearing GitHub client.
The selected accepted Relay product is
`5845433f3bae8c74a32f8234466fd98eb2268464`; an external repository's current
guidance does not change this execution's admitted profile.

## Public evidence and its limits

Observed on 2026-10-17; the main/PR association was recorded at 06:13:20 UTC.
Public API resolution and immutable raw-file reads were used;
no external checkout, remote, hook or configuration was created.

| Repository | Public main observation | Governance evidence and disposition |
| --- | --- | --- |
| `jresearchsoftware/shared-governance` | [`ec048fb39ae28cf2d747101466a603ddd062b1b0`](https://github.com/jresearchsoftware/shared-governance/commit/ec048fb39ae28cf2d747101466a603ddd062b1b0), committed 2026-10-16T05:23:10Z; [public resolution endpoint](https://api.github.com/repos/jresearchsoftware/shared-governance/commits/main) | Pinned root, boot, local handoff, self-adoption and release documents were read. [PR 42](https://github.com/jresearchsoftware/shared-governance/pull/42) merged this SHA on 2026-10-16T05:23:11Z. Its [attributed independent exact-head positive assessment](https://github.com/jresearchsoftware/shared-governance/pull/42#issuecomment-6203786666) binds candidate `a91e93aaa8df2aa471ba5f9f508bdfc7120f895e` and explicitly disclaims native GitHub approval/distinct authenticated reviewer identity. That limit is retained; it is not Relay Reviewer qualification. |
| `jresearchsoftware/codex-model-landscape` | Main SHA unavailable: [public commits endpoint](https://api.github.com/repos/jresearchsoftware/codex-model-landscape/commits/main) returned HTTP 404 | [Public repository page](https://github.com/jresearchsoftware/codex-model-landscape) and [raw main AGENTS](https://raw.githubusercontent.com/jresearchsoftware/codex-model-landscape/main/AGENTS.md) also returned HTTP 404. Current accepted governance, workflows and native acceptance evidence could not be verified. |
| `jresearchsoftware/docs-evolution-review` | Main SHA unavailable: [public commits endpoint](https://api.github.com/repos/jresearchsoftware/docs-evolution-review/commits/main) returned HTTP 404 | [Public repository page](https://github.com/jresearchsoftware/docs-evolution-review) and [raw main AGENTS](https://raw.githubusercontent.com/jresearchsoftware/docs-evolution-review/main/AGENTS.md) also returned HTTP 404. Current accepted governance, workflows and native acceptance evidence could not be verified. |

HTTP 404 does not establish whether a repository is private, absent or renamed.
The browser could not fetch the API endpoints; ordinary Python HTTPS reads
resolved the public Shared Governance evidence and reproduced the other two
404s. No authenticated fallback was attempted. Landscape's direct-main research
policy/no automatic Relay Task adoption and DocReview's native corporate,
reviewer and model boundaries below are constraints supplied by this Task, not
claims that their inaccessible current documents were independently inspected.

The Shared Governance content was frozen at the observed SHA rather than
re-read through moving `main`. Representative exact-file evidence:

| Immutable source | SHA-256 of fetched bytes |
| --- | --- |
| [Root AGENTS](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/AGENTS.md) | `d442f8a90ca3afabacea7fe58eb6a3825bc8c80c370f6ef305b88397b64fc83c` |
| [Native boot index](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/vibevm/vibespecs/boot/INDEX.md) | `8a616d6876874cc3613dca9ab22bd8957fa17770beffc208fb6b9c53395c4fc6` |
| [Authoring boot](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/vibevm/vibespecs/boot/00-authoring.md) | `131ef557d4319530410827479bba308d5f1f1d40cec424e705dbdaf96d2d6a3b` |
| [Installed 2.7.0 compact boot](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/vibevm/vibedeps/org.jresearch.ai.development-governance/2.7.0/vibevm/vibespecs/boot/development-governance.md) | `91a71390e3d5f64ce3b5f5d0f5acc3a7dcee173fb0f0414fc2939f03072f0e6e` |
| [Local manual handoff](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/docs/manual-task-handoff.md) | `e3b54b681ff3856788f8fc6906afc7fbd707bf0e7ad47e3da928a644a4c51a6d` |
| [Producer self-adoption](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/docs/self-adoption.md) | `93cc7ec527234aa98e7438e184e001fa351ac5a9a84821067be17ef536c37e50` |
| [Release policy](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/docs/releases.md) | `a217a7e9fbb720c06c0d407f5d0a52e254b4e62e82d0763493ea7ccd7ddd7987` |
| [Existing candidate workflow](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/.github/workflows/candidate.yml) | `2b59c405d42a35c40f8a327a162a2d618774f2eac38c72ee71a49194316177cd` |
| [Existing publication workflow](https://github.com/jresearchsoftware/shared-governance/blob/ec048fb39ae28cf2d747101466a603ddd062b1b0/.github/workflows/publish.yml) | `69e444ecd1dfe87fd8b264def8a442343d3d7559670e23a7a2cadd567770943b` |

## Supported preparation interface

The product contract is [workflow projection and pinned runtime](../../../deploy/README.md#workflow-projection-and-pinned-runtime),
with [deployment inputs](../../../deploy/README.md#inputs-and-invocation),
[consumer inputs](../../../consumer/README.md),
[CLI implementation](../../../deploy/relay-deploy.py) and
[renderer](../../../deploy/workflow_projection.py) at the selected product SHA.
Relay templates are product source; consumer candidate CI stays consumer-owned.

After a repository owner separately approves preparation, the public invocation
from a clean checkout of that exact accepted product is:

```sh
python3 "$RELAY_SOURCE/deploy/relay-deploy.py" \
  --config "$OWNER_CONFIG" \
  --consumer-root "$CONSUMER_CHECKOUT" \
  --repository jresearchsoftware/shared-governance \
  --resolved-revision 5845433f3bae8c74a32f8234466fd98eb2268464 \
  --phase workflow-project --authorize-workflow-projection
```

These variables are owner-supplied absolute paths to an accepted product
checkout, a complete validated deployment input, and a separate clean consumer
Git checkout. They are not existing consumer configuration discovered here.
For the other repositories, use their exact repository names in `--repository`
only after the repository-specific decisions below. No invocation against any
of these external repositories was performed in this work.

`--repository` selects an already configured target for projection/verification;
it neither adds that target nor transfers authority. The full version-1
deployment input remains required even for this local phase. It includes real
owner-selected `source`, `target`, `consumer` and `environment` fields; no real
host, namespace, App/installation ID, runner group, credential path or model is
inferred from a repository name. Secret references belong in owner-controlled
configuration, never generated workflow bytes or this proposal.

The intended paths for a later approved projection are:

| Repository | Proposed routing / recovery paths | Manifest | Consumer validation input |
| --- | --- | --- | --- |
| Shared Governance | `.github/workflows/codex-relay-routing.yml` / `.github/workflows/manual-writer-publication-recovery.yml` | `.github/relay-workflows.json` | Existing `.github/workflows/candidate.yml` is a candidate mapping; owner must confirm the native validation contract/check identities. |
| Model Landscape | Same proposed routing/recovery paths, reserved only for a separately authorized future Relay lane | `.github/relay-workflows.json`, only if that lane is adopted | Unknown; retain existing direct-main research validation. |
| DocReview | Same proposed routing/recovery paths, contingent on corporate/native governance compatibility | `.github/relay-workflows.json`, only if adopted | Unknown; preserve native corporate validation. |

These workflow names follow the product's synthetic example and are proposed
`consumer.routingWorkflow`/`consumer.recoveryWorkflow` values, not observations
of deployed policy. Owner review must check for collisions and select the actual
paths. `validationWorkflow` is a third distinct existing consumer workflow;
it is not rendered by Relay. Optional `validationNames` are bounded lowercase
consumer check IDs, not arbitrary GitHub display names, and must agree with
Reviewer configuration. In particular, do not copy the display name
`Candidate checks` into that field.

With ordinary consumer `environment.localApply.configPath`, projection emits
the configured routing/recovery pair and the manifest. The additional
`manual-main-production-deploy.yml` belongs only to supported installed
self-dogfood at the lifecycle anchor; no such workflow is proposed here.
`--projection-output` is not accepted for `workflow-project`; it is restricted
to bootstrap/reinstall proposal handling. This research proposes no lifecycle
operation as a way to obtain review files.

## Shared Governance: optional bounded engineering lane

**Proposal:** retain the accepted native manual workflow and consider a separate
opt-in Relay lane for explicitly selected repository implementation Issues.
The owner decides whether the benefit warrants changing that lane's authority
and publication mechanism. Neither the producer's automatic self-adoption nor
its package publication policy enrolls this repository or downstream consumers
into Relay.

The pinned root and local bindings keep substantive work Issue-owned, freeze an
independently accepted source-main guidance SHA, treat candidate instructions
as proposals, require independent exact-result assessment, and distinguish
acceptance, integration, release and consumer adoption. The existing
`candidate.yml` validates PR/main source; `publish.yml` publishes accepted
package changes after successful source-main checks. Both remain intact.
The owner-approved reviewed merge remains the package's publication trigger;
Relay source/workflow preparation grants no merge or release permission.

Before a Relay admission, the local owner must explicitly reconcile these
material surfaces rather than silently treating projection as adoption:

- Which Issues and work kinds use Relay and which retain the existing manual
  path; the local charter/Decision and protected admission binding for that lane.
- The existing full relevant chronology/minimal-prompt practice versus Relay's
  immutable admission snapshot and selected evidence. Required decision history
  must remain available; a different prompt is not authority to omit it.
- Native owner-channel publication versus the Relay Writer's canonical Outcome
  and schema-v4 manual submission capability. The local whole-result Outcome
  routing rule must be checked explicitly; Relay already supports PR-surfaced
  Outcomes, so a universal Issue-only mismatch is not asserted here.
- Attributed independent assessments under the local accepted policy versus
  Relay's separate native Reviewer/App requirements, including exact-head and
  identity evidence. Existing owner-account assessments do not prove that native
  requirement, and this proposal does not replace either acceptance rule.
- Existing Deliberative/Direct acceptance choices, closure intent, and the
  separation of independent source assessment from owner merge/publication.
  Adoption must not add implicit merge, closure or downstream adoption authority.

The public evidence supports preparing this concrete proposal. It does not
establish a deployed Relay configuration, App access, runner isolation or owner
agreement to any of those changes.

## Model Landscape: preserve direct-main research

**Proposal:** keep research on the Task-specified native direct-main path.
Prepare only an optional future engineering-lane design; do not convert research
into PR-required work, copy Relay Task/Step gates into its root policy, or add
automatic ready-label dispatch to research activity. A workflow proposal is not
automatic Relay Task adoption.

The owner must first make accepted local governance available for a separately
authorized read and identify its exact source revision, permitted work kinds,
publication path and independent research assessment. A decision to opt a
bounded engineering lane into Relay must explicitly preserve direct-main
research and explain which events could ever launch it. If accepted local
policy does not permit such a lane, retain the native workflow and leave the
reserved Relay paths absent. No repository-specific validation mapping, model
recommendation or existing workflow collision can be claimed from the failed
public reads. Research findings and model recommendations must not become a
moving runtime configuration source or alter an already admitted profile.

## DocReview: preserve native corporate review and model control

**Proposal:** remain at preparation-only status until the owner confirms a
compatible bounded lane under accepted local corporate and native governance.
Its current accepted source revision, corporate execution/data boundaries,
native reviewer authority, candidate checks and model selection are unverified
through the permitted public channel.

The Task describes this as a v2-to-current workflow proposal; that starting
version is supplied authority context, not a verified installed observation.
For the later owner-admitted migration, inspect the accepted existing workflow
paths, manifest, installed source/ABI and retained attempts first. Preserve
their original bytes and recovery bindings. Derive the current projection from
the selected accepted product and actual owner configuration, compare the full
v2/current diff, and review it under DocReview's own authority before integration.
Unmanaged old workflows or drift require a reviewable reconciliation proposal,
not direct overwrite. Manifest migration, workflow ABI selection and any Task
authority migration are separate compatibility decisions; YAML publication
alone establishes none of the installed or corporate qualifications.

The owner must identify the permitted execution environment and information
boundary, the actual reviewer/acceptance mechanism, and the owner-controlled
model/profile inputs. An optional Relay lane cannot substitute Relay's Reviewer
for a required native/corporate reviewer, route corporate material to an
unapproved service, or silently standardize DocReview onto another consumer's
model. Existing native review and model settings remain authoritative unless
the local owner separately authorizes a material change. No model choice,
credential reuse, corporate access or reviewer qualification is inferred here.
The reserved workflow/manifest paths remain absent until those facts and
decisions support a normal local reviewable proposal.

## Compatibility and review before any later adoption

Projection records schema-2 source/consumer identity, workflow contract and
output digests. The manifest is a drift baseline, not source acceptance or
installation authority. Existing managed bytes must match their previous
manifest; unmanaged collisions or partial projections require reconciliation
through the consumer's existing review path, never overwrite-by-assumption.

At this accepted Relay revision, ordinary serial projections use
`relay-workflows-v3`; configured execution slots, including derived managed-pool
slots, select `relay-workflows-v4`. Workflow ABI numbers are distinct from the
schema-v4 Task authority protocol. Runtime compatibility must be checked against
the actual installed public source/contract; a newer product main SHA alone
does not invalidate an existing installation or authorize its upgrade.

Plural `consumer.repositories` shares owner, profile, App identities, workflow
configuration and installation policy. Per-repository runtime users do not
create per-repository model or corporate authority. The three repositories must
not be added to a shared configuration on an assumption that their policies
match. Changing the repository list changes the execution digest; retained
attempts keep their original configuration/publication/recovery bindings.

For an approved consumer proposal, preserve local policy and native candidate
checks, inspect the entire generated diff and permission/event/runner bindings,
and obtain independent exact-head assessment under that consumer's rules.
Routing uses Issue labels, same-repository PR labels and explicit dispatch;
owner guards are not external runner scheduling restrictions. Public repository
runner access, App permissions and installed capability qualification remain
separate owner-controlled operational facts. Fresh Relay work requires the
qualified current authority path, not an invented legacy Request fallback.

After a separately authorized projection is reviewed and integrated, verify the
clean exact consumer commit through the same accepted product, configuration
and explicit target with `--phase workflow-verify` (omit
`--authorize-workflow-projection`). That checks committed generated bytes; it
does not establish deployment, native CI, corporate acceptance or live behavior.

No external PR, push, merge, activation, install, ACL, credential or protection
change, Reviewer invocation, Task 140/85 remediation, or external execution is
part of this proposal. The inaccessible Landscape/DocReview authority is a
visible evidence gap for their next owner boundary, not permission to manufacture
consumer configuration or to bypass their native workflows.
