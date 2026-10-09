# Task workflow

Use this guide for a Task on a qualified installation with GitHub-native
authority enabled. It describes the current repository product, not a separate
consumer Skill or adapter distribution; that work remains Task #91. Detailed
rules live in the [authority](../contracts/README.md#github-native-task-authority),
[routing](../controller/README.md) and [Reviewer](../reviewer/README.md) contracts.

## From Task to completion

1. **Write the Issue charter.** Task N is GitHub Issue #N. Describe the problem,
   goal, scope, protected boundaries and exactly one closure field:
   `Issue closure policy: keep-open` or `Issue closure policy: close-authorized`.
   Explain any remaining work that keeps it open. Include exactly one standalone
   `Authority model: github-native-v1` line. Start fresh work with `step-1`;
   the [repository Issue template](../.github/ISSUE_TEMPLATE/codex-task.md) supplies
   that label baseline. Issue creation does not launch work.
2. **Publish a complete trusted Task Request.** The owner-authorized caller uses
   Reviewer `publish_task_authority` with `repository` and a structured
   `record` of kind `task-request`, schema version `3.0`. Resolve Step, route,
   model/effort/Subagents, purpose, scope, validation, boundaries, closure policy,
   branch, exact base/head, applicable existing PR and selected references before
   publication. The [normal Request example](../examples/task-authority.md#new-task-request)
   shows a complete record. For repository execution, all starting facts are
   explicit; only manual non-repository work may set branch/base/head all null.
   The trusted publisher verifies the live charter digest, native identities
   and current Request chain, then projects Step labels and the bounded existing
   PR title. A pasted block in an ordinary comment has no authority.
3. **Launch the chosen route.** Apply `codex-ready-auto` to the Issue for an
   automatic Request, or `codex-ready-manual` for a manual Request. The command
   must match its `route` and current Step projections; `step-N` alone grants
   no execution. Trusted routing validates the native owner event and consumes
   it once. Automatic execution runs an isolated credential-free worker;
   manual routing produces a copyable handoff for an owner-launched session.
   Optional owner `workflow_dispatch` remains a fallback, with inputs matching
   the same authority. See [admission and routing](../controller/README.md).
4. **Inspect the Writer Outcome.** The worker preserves ordinary task commits
   and reports local validation; trusted Writer imports bounded object bytes
   into fresh Git, scans every introduced blob, revalidates authority and
   publishes without force. Writer owns the typed `outcome`, bound to the exact
   Request, attempt and immutable result. It appears on the unique durably bound
   PR, or the Issue before PR creation and for legitimate no-PR/no-change work.
   An ambiguous PR publication cannot fall back to the Issue. Successful
   execution handoff makes the PR Ready for review; active or blocked execution
   stays Draft. Ready proves neither CI success nor independent acceptance.
   Manual non-source results use Writer's bounded
   [manual-outcome authorization path](../controller/README.md#issue-publication-and-worker-handoff);
   that authorization publishes the result and cannot amend execution scope.
5. **Review independently at the exact result.** Inspect the complete candidate
   against charter, current Request and applicable Decisions/CR. Compare material
   findings with the starting/base state and retain provenance; passing checks
   alone do not establish acceptance. For a genuine PR, the independent caller
   publishes native exact-head `APPROVE` or a typed PR Change Request. For an
   Task-scoped implemented result, including no-PR work or a disposed artifact
   PR, publish Issue `task-approval` bound to the current Task Request, its Step,
   trusted Writer Outcome and identical immutable results. This does not replace
   a genuine PR's native acceptance. Issue `task-review` findings are evidence
   for a next Task Request,
   not an executable PR CR. Approval never advances Step or creates a PR.
6. **Complete through the authorized owner channel.** After verified independent
   acceptance, owner orchestration calls the existing
   [post-review continuation helper](../contracts/README.md#authorized-continuation-after-independent-acceptance).
   It re-reads authority, exact head, required checks, readiness and boundaries
   before a separately authorized squash merge, then verifies the native result.
   Reviewer publishes the verdict/policy; its `execution_supported: false`
   receipt means the service performs neither merge nor closure. The worker
   also has no merge/close authority. Explicit Issue closure requires
   `close-authorized`, Task-complete continuation, independent acceptance and
   no remaining work. Migrated PRs use `Related to #N` even when closure is
   authorized, so merge cannot close the Task prematurely.

## Decisions and subsequent work

Keep the Issue as a stable charter. A substantive accepted amendment is a
trusted scoped `decision`, not an instruction hidden in discussion. The
[Decision example](../examples/task-authority.md#decision-and-replacement-request)
shows how to publish an amendment and normalize it into a complete successor
Request. Put its returned native reference in `decisions`; copy the amended
semantic values into the Request itself. Publishing a Decision alone does not
launch work or rewrite an already selected Request. Closure authority still
comes from the charter.

Each next Request explicitly `supersedes` the exact current Request/CR native
reference. There is one linear chain, not selection by newest comment or largest
Step. Same-phase continuation may keep Step; a new phase advances precisely by
one. A new PR CR advances by one; correction/recovery of the same CR identity,
PR and reviewed head may retain it. Approval increments nothing. The typed
publisher projects labels/titles; do not run legacy owner metadata helpers for
a migrated Task or fix authority by changing a label alone.

Select only relevant native sources in `context`. Source references contain
`kind`, immutable native `id`, `parent` and `sha256` of the entire native body,
including publication markers. Use returned publisher references or trusted
native reads; a comment's number/URL or JSON-only digest is insufficient.
Ordinary selected comments and prior Outcomes remain evidence. They cannot
fill omitted execution fields. A PR-scoped Decision requires that exact
`existing_pr`; carrying its semantics beyond that PR needs an explicit
Task-scoped Decision. Superseded or body-edited references cannot remain active.

## When PR review requests changes

Review the exact current PR head, aggregate material findings, and preview them
through the owner-authorized review path before publication. For a migrated Task,
use Reviewer `publish_task_authority` with a complete `change-request` record:
PR parent, `existing_pr`, `change_request_id`, `reviewed_head_sha`, the identical
`starting_head`, stable findings, predecessor and full execution snapshot. The
[PR remediation example](../examples/task-authority.md#pr-change-request-and-remediation)
shows these bindings. A Task finding without a PR instead uses `task-review`
and a later complete Task Request; do not manufacture a PR to obtain a CR.

Successful publication creates the native `CHANGES_REQUESTED` review and
synchronizes Step/title projections. Its bounded Writer lifecycle action verifies
Draft for that same CR/head before remediation. Owner orchestration can invoke
the action directly; routing also enforces it during admission. Apply the ready
label matching the CR's route to the existing PR only after verified publication
and synchronization. Remediation preserves that branch/PR and starting-head
gate. The next Outcome identifies the new candidate, which requires new
exact-head review; approval of the old head cannot accept it.

## Warnings, blockers and continuation

Before review, continuation, merge or closure, inspect Outcomes and applicable
execution-time job/check/controller annotations through supported APIs. Preserve
each material warning's source, impact, disposition, next action and evidence
gaps, plus Outcome limitations. Unavailable required evidence is a stated gap;
green status is not warning disposition. UI-only service/pre-execution banners
are outside mandatory automated acquisition. See the
[warning policy](execution-policy.md#execution-warning-disposition) and Reviewer
`read_pr_review_evidence` for bounded native evidence reads.

Blocked work may still preserve useful commits. Fix a clear in-scope local
failure within the admitted execution; uncertain authority, head/publication or
containment stops progress. Do not blindly rerun the workflow or worker.
[Publication recovery](../controller/README.md#writer-publication-recovery)
reconciles the retained attempt through separate owner authorization without
another model execution.

Requests may declare `continuation: {hold, task_complete, next}`. Omission means
no hold, incomplete Task and no next action. An explicit hold stops automatic
continuation. `next` selects an already-published exact current Request, or a
bounded same-Task direction Decision for preparation after acceptance/merge.
The owner helper executes only already-authorized actions, without another
confirmation; it cannot invent scope, re-execute the accepted Request or ignore
unresolved checks. Known same-Task next work keeps the Issue open. Source
completion, review acceptance, merge, closure, deployment and release remain
distinct decisions.

## Compatibility and local policy

GitHub-native authority is explicit opt-in. Qualify the paired
Reviewer/controller with `relay-workflows-v2` and enabled
`githubNativeAuthorityEnabled` before migration. Finish or drain any admitted
legacy execution first; publish a complete first Request and verify projections
before the next ready event. Unmarked Issues retain legacy mutable Issue-body
execution fields, label-led Step preparation and native CR1/CR2 compatibility.
Typed comments alone do not migrate a Task; mixed authority paths fail closed.
See the [migration contract](../contracts/README.md#github-native-task-authority).

The product owns typed/native provenance, exact-head acceptance, safe publication
and actor separation. This repository's [AGENTS.md](../AGENTS.md) adds local
development policy such as English GitHub publication, its default
`gpt-6.1-sol` / `xhigh` / Subagents On profile, candidate checks and manual task
renaming. Consumers retain their own effective profile, checks and operations;
the complete Request records the resolved choices. Future workflow changes must
follow the [same-Task documentation rule](../CONTRIBUTING.md#keep-workflow-documentation-current).
