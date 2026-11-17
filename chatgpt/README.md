# Relay's ChatGPT Project Instructions

This directory is Relay's consumer binding for the accepted Shared Governance
10.0.0 generator. It is repository guidance, not a new Relay Skill release or
runtime change. The [Task 101 Decision](https://github.com/jresearchsoftware/codex-relay/issues/101#issuecomment-6718773565)
authorizes this integration. Candidate files do not govern their own execution
or review. Source acceptance, live settings application and Task completion are
separate facts; Task 101 stays open for actual owner-controlled reconciliation
and accepted integration.

The human-owned [custom.md](custom.md) supplies ChatGPT's role and local routes;
[binding.json](binding.json) supplies identity, paths, budget and optional cache
selection. [instructions.md](instructions.md) is the complete generated desired
Project Instructions, including its marker. Shared policy remains in the selected
Shared slot, repository policy in root AGENTS and its owning contracts, and
product methodology in the accepted Relay Skill. This consumer neither forks
the generator nor duplicates the product bundle owned by Task 91.

## Deliberate maintenance

Use Python 3.11+ and Git only at maintenance time. Ordinary chats read accepted
files through supported GitHub capabilities. No VibeVM binary, new registry,
background service or per-message integrity check is required. Read the
[generic interface](../vibevm/vibedeps/org.jresearch.ai.development-governance/10.0.0/tools/chatgpt/README.md)
for input validation, exit codes, exact diffs and cache removal behavior.

First establish the independently accepted exact source and authority through
the current Task/review and Git evidence. Freeze that source for the effort;
`main`, local HEAD and an evidence URL alone do not prove acceptance. Then run
from the repository root (replace both placeholders with verified values):

```sh
python3 vibevm/vibedeps/org.jresearch.ai.development-governance/10.0.0/tools/chatgpt/project.py update \
  --repository . --binding chatgpt/binding.json \
  --accepted-sha <accepted-full-SHA> --authority-anchor <current-authority-URL>
```

Use `check` for read-only drift detection. Exit 0 means current, 1 means stale
output, and 2 means invalid/unavailable inputs. `update` reports exact changes;
repeating it with the same effective inputs returns `NO_OP` and leaves unchanged
files untouched. Edit binding/custom, never generated policy. Commit and review
inputs and outputs together in the ordinary PR. This is not a new global CI gate.

Task 194 updates the immutable generator/base and local closure/project-context
guidance as a source candidate. Its projection invocation freezes accepted Relay
`4f0990c4b676a45f7e37d37ecb10fecc871b7a25` with Task 194 authority; candidate
text is not independently accepted or live-applied by generation. Changed complete
text retains TH-029 owner reconciliation after accepted integration.

Task 244's capability and Small Improvements candidate was projected against
accepted `7f95a60c485ccf40025dae78f652adc8df3b19ea` with its
[owner Decision](https://github.com/jresearchsoftware/codex-relay/issues/244#issuecomment-6943093940).
The unchanged 8,000-character budget still applies; generation does not verify
or update live Project Settings.

The first projection used accepted starting source
`b9de15342525da0144edf18b457f7e640a9bf087` (Shared 7.0.0 adoption, PR 214),
under the Task 101 Decision above. The native validator consumes its committed
INDEX schema 1, lock schema 7 and slot receipts schema 1. Toolchain selection is
VibeVM **1.0.11**; the retained lock's `generated_by = "vibe 1.0.7"` is historical
metadata, not a claim that this task ran that version. No resolver or lock edit
is needed to generate this projection. Native OS/package conditions remain
intact and do not select client roles.

On material accepted base/custom/binding, product, dependency or routing changes,
regenerate/check against the deliberately selected accepted source. VibeVM alone
resolves direct/transitive dependencies and visibility at update/install time;
this integration consumes committed closure and never chases versions itself.
The existing [VibeVM runbook](../docs/vibevm.md) owns those updates. An ordinary
consumer update needs no new Relay release when the product bytes/contract stay
unchanged. An unchanged Instructions output creates no new settings action just
because a dependency or SHA advanced. Prior live reconciliation gaps remain open.

## Optional Sources

The default direct bootstrap plus canonical GitHub retrieval uses no cache.
To qualify an optional cache, deliberately set `cache_enabled` to true and choose
explicit accepted repository paths in `cache_selection`, then use the same
command. It emits `sources.md` ready for optional owner upload and
`sources-manifest.json` with exact revision, paths, hashes and canonical links.
Select only useful ChatGPT entry material; referenced full policies still need
to be read when triggered. The generator validates existing native closure; it
does not independently resolve a transitive dependency graph.

Review cache diffs separately from Instructions diffs. Cache-only changes do
not require Instructions reapplication. Disabling cache removes only the two
named generated cache outputs, including locally edited copies; preserve useful
edits in authored sources first. Do not maintain a second package registry.

An upload is an owner action. Verify through supported client evidence whether
ChatGPT can address and inspect the selected Sources and identify their revision;
no complete enumeration/version API is assumed. Missing, stale or uncertain
Sources fall back to canonical GitHub. Without GitHub, qualify read-only
analysis and disclose revision uncertainty; stop protected actions needing live
authority or exact-head evidence. Neither generated hashes nor static tests prove
actual Source addressability, freshness or model behavior.

## Acceptance and owner settings handoff

Independent exact-head review covers semantic parity and source/generated diffs
before source integration. This does not mutate or prove any live ChatGPT UI.
After accepted merge, compare the **complete accepted** instructions.md with
supported current live evidence. If different or unconfirmed, provide its entire
raw Markdown in one complete copyable `markdown` fence for owner review and
manual application, preserving/reconciling unknown live rules. Do not substitute
a patch, excerpts or a link for the replacement text. Report precisely which
Instructions text or selected Sources need owner action.

For an owner-provided export, exact comparison is available without UI writes:

```sh
python3 vibevm/vibedeps/org.jresearch.ai.development-governance/10.0.0/tools/chatgpt/project.py compare \
  --repository . --binding chatgpt/binding.json --live-export /path/to/owner-export.md --live-format raw
```

Use `fenced` for one complete Markdown fence. An export comparison alone never
proves UI currentness. Obtain supported readback or sufficiently attributable
owner confirmation of the actual live content before claiming a match. No
settings mutation, Source upload or invented confirmation is authorized here.
The current live Instructions and Sources were not supplied or inspected in
this execution; semantic transfer from unknown live rules remains unverified.
This gap holds Task completion after merge, not source PR review or merge.

## Local evidence and remaining client qualification

Run the consumer scenarios with `python3 scripts/test-chatgpt-project.py` and the
repository's ordinary required candidate checks. The scenarios exercise actual
Relay inputs, deterministic regeneration, changed custom text, optional cache,
accepted-source isolation, native routing failures and export comparison. They
are local implementation evidence, not independent acceptance or live-client proof.

Small Improvements planning follows accepted root AGENTS and the
[Relay binding](../docs/relay-guidance-ownership.md#small-improvements-binding),
through the locked Shared 10.0.0 protocol. The authored custom guidance supplies
the ChatGPT planner route; the generator remains unchanged. The same suite
checks authored/generated instruction coverage with these tabletop fixtures:

| Planning situation | Expected disposition from the instructions |
| --- | --- |
| Suitable source Task; relevant bounded candidate on a later result page | Use `repo:jresearchsoftware/codex-relay is:issue is:open label:small-improvement`, inspect all pages, assess relevant Issues/dependencies/conflicts/ownership, and automatically include eligible candidates under Relay's standing preference after recording selected IDs, bounded scope and provenance in authenticated receiving authority. |
| First source-changing Step after analysis; relevant CR | Discover at preparation; a CR still cannot enlarge Task-wide authority. |
| Analysis-only work | Skip discovery; no tracker prerequisite. |
| Unchanged subsequent Step or inner correction | Skip ceremonial rescanning; refresh on materially changed scope/information. |
| Empty results, or only irrelevant/conflicting/unowned candidates | Continue the original work without forced inclusion or a queue-empty gate. |
| Suggested/linked/labelled candidate without receiving authority | Do not implement; selection needs explicit receiving Task/Decision/CR authority. |
| Selected candidate pending integration, cancelled receiver or partial delivery | Preserve source Issue links, provenance, label and open state; record the exact remainder/disposition. |
| Deferred correction without label capability | Report the gap; do not claim it queued. |

These are instruction coverage and tabletop evidence, not an executable planner
or proof of automatic model compliance. Keep actual discovery, owner selection,
included/excluded candidate dispositions and receiving links in the existing
Task/PR/Outcome records, rather than a second backlog here. Selection and local
tests do not establish accepted integration or authorize source-Issue closure.
After accepted merge, the full-text settings handoff above still applies; no
new execution Step is needed solely to repeat an unchanged handoff.

The following owner/client exercises remain explicit acceptance evidence:

| Exercise | Required observation |
| --- | --- |
| Normal discussion and new Task planning | Relevant complete accepted guidance is retrieved JIT; planning alone allocates no Step. |
| Exact-head PR assessment | Live authority, entire candidate and primary checks/warnings are inspected; native verdict requires the qualified independent capability. |
| ChatGPT lacks a deployment App; assigned Codex has an already authorized shell/SSH path | Apply the [shared capability distinction](../packages/codex-relay/skill/references/workflow.md#owner-acceptance-and-execution-routes) and accepted shell routing; the missing App alone does not block the Codex operation. No additional probe or credentials are implied. |
| Required Codex transport is actually unavailable or unauthorized | Stop the affected operation and identify that concrete capability/authority boundary; another client's tools do not supply it. |
| Dependency/transitive update | Reviewed VibeVM closure is consumed; meaningful output diff or no-op determines the actual settings/cache action. |
| Missing/stale Sources | Canonical retrieval works without mandatory upload; version uncertainty is visible. |
| GitHub unavailable | Qualified read-only discussion remains possible; protected actions stop. |
| Settings handoff | Full accepted replacement is delivered; owner applies and confirms actual live content, reconciling unknown existing rules. |

The generic adapter already provides retrieval routing and optional cache outputs;
no extra ChatGPT Skill is selected. A future Skill needs evidence of material
client benefit, without duplicating substantive policy. No model probe, native
ChatGPT Source API or Settings readback is claimed by these local scenarios.
