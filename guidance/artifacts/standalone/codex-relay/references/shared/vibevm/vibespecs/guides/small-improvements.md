# Adopt standing delegation for the small-improvement backlog

This guide illustrates [SI-001–SI-008](../protocols/small-improvements.md).
The protocol owns the obligations. Explicit project adoption supplies its bounded
same-repository inclusion authority; examples grant no additional permission to
change labels, instructions, protected Task authority or another repository.

## Adopt deliberately

During the project's own reviewed versioned upgrade, select this topic explicitly
in human-owned AGENTS or equivalent guidance. For example, adapt this route to
the project's pinned slot:

> We adopt `small-improvements.md`, including standing authorization to include
> all bounded eligible same-repository candidates at the first suitable authorized
> source-changing Task, first source-changing Step after analysis, relevant CR or
> new source-changing PR opportunity. Read the complete protocol through our locked
> package route. No per-candidate permission or advance notification is required.
> Local Task admission, protected boundaries and tracker closure ownership remain.

Do not paste a second copy of the protocol. The compact package boot supplies
the conditional route; installing the package alone selects no topic. Reconcile
existing local rules and label permissions during the adoption change. The
normal planning/execution path performs discovery and implementation under this
standing delegation. It does not start a Task or override an explicit current Task
exclusion, owner hold, protected action or native admission boundary.

## Capture, look up and include

An ordinary Issue might say:

> Small improvement: correct the CSV example header
>
> The documented header differs from the supported exporter output (link to
> evidence). Change the example and its fixture together. Deferred because the
> current PR is already approved. Verify the example against the fixture in the
> next suitable authorized source-changing opportunity. Label: `small-improvement`.

Use the exact label, irrespective of the title. For example, replacing
`OWNER/REPOSITORY` with the owning repository:

```text
repo:OWNER/REPOSITORY is:issue is:open label:small-improvement
```

An existing authorized GitHub CLI path can use:

```sh
gh issue list --repo OWNER/REPOSITORY --state open --label small-improvement --limit 100
```

Inspect the complete result set, following pagination if needed; a truncated
list is not a complete lookup. Existing web search works too; no CLI is required.
Read and assess all candidates. An ordinary receiving result might report:

> Included #12 (CSV example) and #18 (UI text correction) in Task #40's PR under
> our adopted standing delegation. Verified the CSV example against its fixture
> and the UI text against the supported workflow. #23 remains pending because it
> depends on an unresolved exporter format decision; that decision belongs in its
> ordinary owner-authorized work before the correction can be included.

The UI correction need not share the exporter's topic or be necessary to its main
objective. Include every reasonably implementable, safe, independently actionable
candidate that meets the protocol's bounds. Assess combined risk and reviewability;
record concrete reasons and the next route for deferred work. No per-candidate
permission, amendment, separate Task/Step/PR or notification before implementation
is required. Keep an already approved PR undisturbed solely for minor additions;
use a future suitable opportunity. Urgent or genuinely required corrections use
their ordinary authority and fresh-result review path.

An empty queue or no eligible candidate requires no forced inclusion. Analysis-only
work skips this discovery unless a broader accepted local rule applies. Do not
repeat scans per internal commit or for an already assessed opportunity without
material change or new information. Link #12/#18 and Task #40/its PR in both
directions; use neutral related-to links where automatic closing would bypass
local ownership. State the source Issue IDs and delivered corrections in the PR
and Outcome where used. Combined tests and one independent review of the combined
exact head cover the complete change. Keep #12 open until the accepted integrated
result exists. If only the header example lands
but its required fixture remains unfinished, record that partial result and keep
the remainder discoverable. Cancelled receiving work returns the candidate to
pending discovery; scheduling does not prove delivery.

## Consumer upgrade and deduplication

Source acceptance, public release, dependency update, topic adoption and live
application are distinct. No consumer migration follows from package availability.
Each interested consumer's owner separately authorizes its upgrade/adoption:

1. Refresh its accepted instructions, package/Skill routes, related Issue/PR
   discussion, label meaning, unfinished items and local exceptions. Compare
   obligations and triggers, not matching words or the word "follow-up".
2. Map the shared discovery/capture/disposition behavior to SI; retain CD for
   accepted reusable-decision promotion, TH for execution/results and RA for
   authority. Adopt pinned accepted content and remove only proven equivalent
   active local duplicates in the same reviewed change. Keep a minimal shared
   route and justified local bindings; preserve history and unfinished Issues.
3. Walk an ordinary source-changing opportunity with an eligible candidate on a
   different topic, an analytical Task, an explicit Task exclusion, an already
   approved PR and a cancelled/partial receiver. Verify effective routing,
   ordinary checks and Git rollback. File checks and tabletop walks do not prove
   model compliance or runtime application. Use the consumer's exact-head review.

For **Docs Evolution Review**, retain its broader `planning-required` rule:
consider all open marked Issues before the next executable Task/Step, including
analytical work; preserve include/schedule, reasoned deferral, closure/supersession,
its label-removal conditions and no second ledger. Its existing no-automatic-
injection rule remains authoritative until the consumer's reviewed adoption
explicitly reconciles it with SI's standing delegation. SI's narrower
source-changing trigger does not silently replace the broader planning trigger.
Reconcile the two label lifecycles explicitly if adopting SI; do not mass relabel
existing work. Preserve project layering, original-item promotion traceability
and native Reviewer ownership. Existing CD routing is not a duplicate queue to delete.

For **Codex Relay**, retain native trusted Task Decisions/admission, Writer and
Reviewer identities, exact-head acceptance, retained compatibility and TEST/PROD
permissions. Existing CD routing does not establish a small-improvement queue.
Adopting SI needs a separately accepted consumer route that authorizes its standing
bounded inclusion and any authorized local label setup. It does not launch Tasks,
require a bot/controller or override native admission. Assess
actual dependency compatibility rather than updating solely for a major number.

Those consumers' owners own future adoption and deduplication; this guide neither
assigns executable work nor claims either project has migrated. A project may
decline or defer adoption and retain its current canonical policy.
