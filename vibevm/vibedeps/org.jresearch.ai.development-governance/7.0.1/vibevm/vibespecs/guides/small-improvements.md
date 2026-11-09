# Use the opt-in small-improvement backlog

This guide illustrates [SI-001–SI-008](../protocols/small-improvements.md).
The protocol owns the obligations. Examples grant no permission to change
labels, instructions, Task scope or another repository.

## Adopt deliberately

During the project's own reviewed versioned upgrade, select this topic explicitly
in human-owned AGENTS or equivalent guidance. For example, adapt this route to
the project's pinned slot:

> We adopt `small-improvements.md` for candidate capture and discovery while
> preparing suitable source-changing Tasks, first source-changing Steps or
> relevant CRs. Read that complete protocol through our locked package route.
> Local Task admission, protected boundaries and tracker closure ownership remain.

Do not paste a second copy of the protocol. The compact package boot supplies
the conditional route; installing the package alone selects no topic. Reconcile
existing local rules and label permissions during the adoption change. The
receiving Task's normal owner/architect planning path performs discovery and
notifies the owner; the executor implements only admitted scope.

## Capture, look up and propose

An ordinary Issue might say:

> Small improvement: correct the CSV example header
>
> The documented header differs from the supported exporter output (link to
> evidence). Change the example and its fixture together. Deferred because the
> current PR is already approved. Verify the example against the fixture in the
> next related source-changing Task. Label: `small-improvement`.

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
Read relevant candidates, then notify the owner, for example:

> Found #12 (CSV example) and #18 (unrelated UI change). Propose including #12
> in Task #40's exporter correction with its fixture check. Leave #18 pending.
> #12 is a scope proposal until accepted in Task #40's authority.

An empty queue or no relevant candidate requires no forced inclusion. Analysis-only
work skips this discovery unless a broader accepted local rule applies. After
selection, link #12 and Task #40/its PR in both directions; use neutral related-to
links where automatic closing would bypass local ownership. Combined tests and
one independent exact-result review cover the complete change. Keep #12 open
until the accepted integrated result exists. If only the header example lands
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
3. Walk an ordinary source-changing opportunity, an analytical Task, a candidate
   outside scope and a cancelled/partial receiver. Verify effective routing,
   ordinary checks and Git rollback. File checks and tabletop walks do not prove
   model compliance or runtime application. Use the consumer's exact-head review.

For **Docs Evolution Review**, retain its broader `planning-required` rule:
consider all open marked Issues before the next executable Task/Step, including
analytical work; preserve include/schedule, reasoned deferral, closure/supersession,
its label-removal conditions and no automatic injection/second ledger. SI's
narrower source-changing trigger does not replace it. Reconcile the two label
lifecycles explicitly if adopting SI; do not mass relabel existing work. Preserve
project layering, original-item promotion traceability and native Reviewer
ownership. Existing CD routing is not a duplicate queue to delete.

For **Codex Relay**, retain native trusted Task Decisions/admission, Writer and
Reviewer identities, exact-head acceptance, retained compatibility and TEST/PROD
permissions. Existing CD routing does not establish a small-improvement queue.
Adopting SI needs a separately accepted consumer route and any authorized local
label setup; no bot/controller or automatic Task injection is implied. Assess
actual dependency compatibility rather than updating solely for a major number.

Those consumers' owners own future adoption and deduplication; this guide neither
assigns executable work nor claims either project has migrated. A project may
decline or defer adoption and retain its current canonical policy.
