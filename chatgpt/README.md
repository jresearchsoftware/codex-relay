# Relay's ChatGPT Project Instructions

This directory is Relay's consumer binding for the accepted Shared Governance
7.0.0 generator. It is repository guidance, not a new Relay Skill release or
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
[generic interface](../vibevm/vibedeps/org.jresearch.ai.development-governance/7.0.0/tools/chatgpt/README.md)
for input validation, exit codes, exact diffs and cache removal behavior.

First establish the independently accepted exact source and authority through
the current Task/review and Git evidence. Freeze that source for the effort;
`main`, local HEAD and an evidence URL alone do not prove acceptance. Then run
from the repository root (replace both placeholders with verified values):

```sh
python3 vibevm/vibedeps/org.jresearch.ai.development-governance/7.0.0/tools/chatgpt/project.py update \
  --repository . --binding chatgpt/binding.json \
  --accepted-sha <accepted-full-SHA> --authority-anchor <current-authority-URL>
```

Use `check` for read-only drift detection. Exit 0 means current, 1 means stale
output, and 2 means invalid/unavailable inputs. `update` reports exact changes;
repeating it with the same effective inputs returns `NO_OP` and leaves unchanged
files untouched. Edit binding/custom, never generated policy. Commit and review
inputs and outputs together in the ordinary PR. This is not a new global CI gate.

The first projection uses accepted starting source
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
python3 vibevm/vibedeps/org.jresearch.ai.development-governance/7.0.0/tools/chatgpt/project.py compare \
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

The following owner/client exercises remain explicit acceptance evidence:

| Exercise | Required observation |
| --- | --- |
| Normal discussion and new Task planning | Relevant complete accepted guidance is retrieved JIT; planning alone allocates no Step. |
| Exact-head PR assessment | Live authority, entire candidate and primary checks/warnings are inspected; native verdict requires the qualified independent capability. |
| Dependency/transitive update | Reviewed VibeVM closure is consumed; meaningful output diff or no-op determines the actual settings/cache action. |
| Missing/stale Sources | Canonical retrieval works without mandatory upload; version uncertainty is visible. |
| GitHub unavailable | Qualified read-only discussion remains possible; protected actions stop. |
| Settings handoff | Full accepted replacement is delivered; owner applies and confirms actual live content, reconciling unknown existing rules. |

The generic adapter already provides retrieval routing and optional cache outputs;
no extra ChatGPT Skill is selected. A future Skill needs evidence of material
client benefit, without duplicating substantive policy. No model probe, native
ChatGPT Source API or Settings readback is claimed by these local scenarios.
