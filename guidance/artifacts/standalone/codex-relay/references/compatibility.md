# Installed protocol and retained-attempt compatibility

Read this when old records or an installation mismatch affect the requested
operation. Guidance version, runtime version, shared-policy adoption and client
discovery are distinct facts. An upgrade of one does not establish the others.

| Situation | Correct authority and permitted path |
| --- | --- |
| New work on a qualified paired v4 installation | Stable marked charter + active trusted v4 Decisions/applicable v4 CR; protected Writer admission. No new public Task Request. |
| Fresh unmarked/legacy Task or new v3 Request/CR chain on that installation | `CURRENT_PROTOCOL_REQUIRED`; stop before admission reservation, command consumption, Step projection, worker launch or fabricated blocked Outcome. Use current v4 authority or explicitly owner-authorized migration. |
| Marked Task with v3 Request history, now seeking new v4 admission | Active trusted Task-scoped v4 Decision newer than the latest v3 Request must explicitly amend purpose or scope. Closure/profile-only amendments do not suffice. Replace a latest applicable v3 CR with current v4 CR. Do not inherit old execution fields. |
| Exact old attempt already admitted | Preserve its original selected Request/native references, complete body hashes, Step, transport, projection and replay/currentness rules. Safe completion, Outcome publication/recovery and result acceptance remain supported. No fresh old-style execution. |
| Older qualified installation | Its accepted installed contract remains authoritative. Do not claim a source-only/partial upgrade activates v4 or rewrite old history. A connected capability gap stops the affected native operation; it grants no replacement result transport for an admitted attempt. |

Never combine legacy mutable-Issue authority with marked stable-charter authority.
The marker is exactly one standalone `Authority model: github-native-v1` line;
unknown/malformed/multiple markers fail closed. Typed comments, labels or a
Skill do not migrate a Task. Migration requires owner authority and a qualified
paired Reviewer/controller plus compatible workflow projection. Do not migrate
a charter while its old admitted execution remains in flight.

Explicitly owner-authorized standalone/manual work follows the
[manual's route policy](workflow.md#owner-acceptance-and-execution-routes).
It neither fabricates native admission nor replaces an existing attempt's
publication/recovery. Source-PR acceptance of an exact retained manual Request
does not publish a new v3 record or authorize a fresh old-style execution.

## Retained schema v3 details

After assembly, read the bundled exact retained schema
`product/github-authority-v1.json` only when the installed/exact-attempt
contract calls for it. The stable charter and one
complete selected trusted Task Request or native CR supply the execution
snapshot. Accepted Decision amendments must be normalized into that snapshot;
Decision publication alone does not rewrite a previously selected Request.

The explicit linear supersession chain selects the current complete Request,
not comment order or the largest Step. Forks, missing/edited predecessors,
duplicate records and cycles fail closed. A retained Task Request may keep Step
or explicitly advance by one; a new CR advances by one, with its narrow
same-CR/head/PR correction exception. These historical rules must not replace
v4 admission allocation.

Native source references carry kind/ID/parent/full-body hash. Trust requires the
configured publisher login, immutable positive native ID and Bot type, with
the matching repository and parent. CR review state and exact commit binding
also matter. Writer identity remains separate. Prose or a copied fence never
establishes identity. Preserve original bytes, source currentness and Step
through recovery; do not fabricate old admission snapshots.

Retained v3 admitted-result acceptance binds the exact selected Request, Step, trusted
Writer Outcome and identical immutable result. Closure remains the charter's
effective policy; a Decision alone cannot override it. Retained continuation
may carry `{hold, task_complete, next}` under its exact original contract;
v4 instead uses verified canonical completion and `{hold, next}`. Approval
never allocates Step or manufactures a new Request.

The historical owner `relay-manual-result` authorization-comment transport
remains available only where its supported retained contract requires it.
It is not a new-v4 prerequisite or workaround for missing
`submit_manual_outcome`. Exact reserved old Decision/CR publication recovery
is permitted; publishing a new old-schema governance chain is not.

## Preserve installation and local ownership

Select an explicit supported artifact version. Inspect the deterministic diff
and provenance before applying an update. Existing user AGENTS.md, Skills,
overlays and unrelated packages remain owner-controlled. Collision or managed
drift needs reviewable reconciliation; do not silently replace user content,
activate other shared topics, resolve moving latest during execution or edit
immutable dependency copies. Missing/drifted accepted files are an evidence and
routing gap; restore reviewed content through the supported version path.

Removal/rollback follows the delivery instructions and owned-file boundaries,
preserving local material and any active older admission. Neither delivery form
installs a live service, alters GitHub settings or synchronizes ChatGPT Project
Instructions. Source tests do not prove consumer ingress, credentials, socket
permissions, process isolation, service activation or production readiness.
