# Task 115 native publication flow and rendering evidence

This source candidate implements the accepted flow in [Task 115](https://github.com/jresearchsoftware/codex-relay/issues/115), admitted through [Request 6109630038](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6109630038). The observations below were read from current GitHub records on 2026-10-11. Historical bodies, native IDs and their digests were not changed. Source behavior, local tests, native rendering and installed qualification are distinct evidence.

## Real events and the resulting flow

| Representative existing event | Old flow | New flow and benefit |
| --- | --- | --- |
| Task 109 diagnosis: [Request](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6103031443), [handoff](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6103044336), [owner result](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6103150895), [Writer Outcome](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6103154278), [no-PR approval](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6105790006) | Publish a full Request, launch, publish a handoff, copy result JSON to an owner comment, copy the result to a Writer Outcome, independently approve the result. | Resolve the charter and trusted Decisions at admission. Keep the durable manual handoff, submit result JSON through the narrow protected interface, publish one Writer Outcome, retain one independent no-PR approval. New launches no longer require the public Request or owner result copy. |
| Task 109 source correction: [Decision](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6105910112), [replacement Request](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6105915198), [PR 110](https://github.com/jresearchsoftware/codex-relay/pull/110) | Normalize an authorized Decision into another full public Request before execution. | Publish the durable Decision delta once; bind its exact native reference and digest in the protected execution snapshot. A genuine source PR and independent exact-head review remain. |
| Task 109 host qualification direction: [Decision 6106309295](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6106309295), [Request 6106313887](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6106313887), [Decision 6106329052](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6106329052), [Request 6106333263](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6106333263), [PR 112](https://github.com/jresearchsoftware/codex-relay/pull/112) | Repeat the complete scope/profile snapshot after each bounded Decision; implementation and protected qualification are separate historical artifacts. | Keep the semantic Decisions; omit the new redundant Request copies. Preserve exact source/projection/install distinctions. Admission simplification does not grant host, credential or production mutation authority. |
| Task 109 final qualification: [handoff](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6107050657), [owner result](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6107090779), [Writer Outcome](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6107092913), [Task Approval](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6107231032) | A 13,387-character owner result is copied into a 13,602-character Writer record, followed by a 14,057-character JSON-led acceptance record. | Remove the new owner-result transport comment. Present execution substance and warning dispositions before one folded canonical record. Keep the independent qualification acceptance and its exact result binding. |
| PR 87 [native CR review 5444930055](https://github.com/jresearchsoftware/codex-relay/pull/87#pullrequestreview-5444930055) | A native REQUEST_CHANGES record makes the operator parse JSON to find the deployment-interface blocker, correction and five acceptance criteria. | Keep the exact-head native review. Show the problem, impact, required correction, all criteria, finding evidence and boundaries before the canonical JSON fold. Remediation overrides stay within Task authority. |
| Task 89 [automatic Request 6041828085](https://github.com/jresearchsoftware/codex-relay/issues/89#issuecomment-6041828085) | A full scope/profile Request is a public prerequisite for automatic execution. | A fresh authorized ready event resolves charter/Decisions and defaults through Writer admission. The historical Request remains readable and valid for compatible retained attempts. |
| Task 84 [BLOCKED Outcome 6053796188](https://github.com/jresearchsoftware/codex-relay/issues/84#issuecomment-6053796188) and [large qualification Outcome 6076612965](https://github.com/jresearchsoftware/codex-relay/issues/84#issuecomment-6076612965) | The material boundary and respectively three/four warnings plus ten limitations are primarily in JSON; later historic resumptions reused the selected Step. | Preserve the old bytes. New Outcomes show all warning sources, impacts, dispositions, next actions, evidence gaps and limitations. A genuinely new execution after BLOCKED receives a fresh Step; replay of the same admitted attempt cannot allocate a Step or launch again. |

Necessary authority, execution and independent acceptance events survive. New mandatory replacement Requests and owner-authored manual-result transport copies vanish. Existing handoffs change only presentation around their copyable prompt. Decisions and reviews do not allocate execution Steps; labels and Actions run names remain projections. A PR implementation uses native exact-head acceptance; no-PR qualification retains an independent Task Approval. Neither publication path merges or closes an Issue.

## Source presentation and compatibility

`contracts/src/publication-rendering.mjs` renders the validated record deterministically. Visible English includes purpose/status/verdict, Task and admitted Step where available, scope, boundaries, Decision amendments, CR corrections/criteria/evidence, warning disposition/evidence gaps, limitations and the next independent acceptance boundary. No validation success, actual runtime model or authorization is inferred.

The normal machine section is one collapsed `<details>` containing the single canonical `relay-authority` JSON fence. HTML, Markdown punctuation, links, mentions and injected fences in untrusted visible text are neutralized; canonical JSON bytes remain unchanged. Empty evidence does not create a PASS claim. If the expanded human summary would exceed the supported native body size, the renderer uses an explicitly identified open canonical-JSON fallback rather than truncating or hiding material facts.

The explicit `legacy-v1` renderer reproduces the committed schema-v3 fixture exactly. It preserves historical native body/hash semantics; changing the default renderer does not authorize rewriting existing comments or reviews. Reservation recovery must retain the original intended body/version and reconcile its exact native bytes. New v4 Outcomes bind the protected authority snapshot and `admissionBinding`, with no synthetic public Request field.

`foldManualHandoff` wraps only the existing text fence and supports a delimiter longer than literal prompt backtick runs. Tests compare every copyable byte before and after wrapping, including CRLF and raw fence/HTML evidence, preserve the standard visible header/lifecycle marker and prove idempotent wrapping. Malformed or ambiguous prompt fences remain open and unchanged. This is source evidence; it does not establish the actual GitHub expand/copy affordance.

## Focused validation and its limits

Native Debian Node 22.20.0 targeted validation passed 111/111 tests with zero skips for the publication renderer, historical authority parsing, controller Outcome, core publication and Task-authority suites at the tested development snapshot. An earlier Windows controller invocation stopped at `CONSUMER_CONFIG_INVALID`; no Windows runtime qualification is claimed. Additional standalone manual-result and admission-allocation tests passed 21/21 on native Debian with zero skips. After synchronizing the current owned renderer/Outcome/tests and contract dependencies, the combined owned suites passed 36/36 with zero skips; `git diff --check` also passed. These are development-snapshot observations, not final-head native CI or independent acceptance.

The direct-result tests cover v3/v4 compatibility, one Writer-Bot Outcome for Issue/no-PR and closed disposable PR results, absence of an owner-source read, immutable replay claims, lost-response reconciliation, no blind POST retry, current PR-head binding, blocked Draft ordering, authority/admission tampering and exact body/Writer readback. The ordinary broker rejects a caller-supplied capability before reading protected state. Fakes exercise the manual module and model the existing comment reservation protocol; they do not independently qualify a root Writer lock, deployed ingress, TLS identity or live GitHub delivery.

Admission-allocation tests cover no premature Step from charter/Decision/ready-label records, a fresh Step after BLOCKED, rejection of unresolved or uncertain previous publication, rejection of unknown prior metadata/overflow, exclusion of rejected or unrelated admissions and unchanged retained records. Pure allocation tests do not alone prove cross-process serialization or that all installed callers hold the publication lock.

The additional schema-v4 prepublication inspection suite passed 5/5 on native Debian with zero skips; the existing schema-v3 prepublication suite passed 37/37 in the same development snapshot. It checks exact authority/admission/Step binding, immutable terminal records, changed body/Writer/parent/marker rejection, persisted digest provenance, changed native run/source/journal rejection and zero collection/publication without fresh owner authorization. This focused fake inspection does not prove a live protected recovery or grant authorization to perform one.

The shared Node/Rust fixture contains current v3/v4 Request/Decision/CR/Outcome/Approval/review examples and malicious text with exact expected presentation. The Rust helper reported exact parity for all twelve fixtures. Complete candidate checks and native CI belong to the final candidate verification; this report does not imply they passed from Node evidence alone.

## Read-only TEST repository inspection

GitHub metadata identifies [codex-relay-testbed](https://github.com/jresearchsoftware/codex-relay-testbed) as **private**, owned by `jresearchsoftware`, unarchived and explicitly described as a disposable isolated Relay TEST consumer with no production credentials/state. Its README and AGENTS require TEST-only identities/paths, supported public lifecycle operations, retained historical authority and separate independent acceptance. Main contains the existing TEST scaffold. Historical PR 2 is closed at `91e29c09ac089dfd10dbaf6e8feeb42a9171395e`; Issue 1 stays open. These records were inspected without mutation and are not Task 115 fixtures.

The tracked TEST consumer configuration names `codex-relay-testbed`, a separate `codex-relay-test` environment namespace, TEST controller/Writer/Reviewer identities and runner groups, and TEST ingress `codex-relay-test.jresearch.org` on port 18787. It also names a shared ingress container, so repository separation is insufficient evidence of current host isolation. These are read-only configuration observations, not installed state or credential proof.

Repository metadata proves the intended repository identity and documented boundary, not current host/runtime isolation. Before any live Task-owned TEST fixture or installed operation, inspect the supported public inventory/configuration and current authenticated TEST identity, establish ownership/recovery and confirm that no shared/production state is targeted. No root operation, installation, credential/permission change, model/Relay execution or live GitHub publication was performed for this focused assignment.

## Remaining native qualification

### Supported TEST inventory observation

After the owner identified the existing TEST consumer, a separate clean checkout
of `codex-relay-testbed` main at
`52d66305557a74264cd0f5b82ec0b90804baa98c` was created outside the product tree.
Its README requires the selected exact product's public deployment entrypoint.
The unchanged public entrypoint ran from a separate clean native Debian source
checkout at the configuration's selected accepted revision
`afb2cbdbcb82294604c51ec0ce4c2a62cf272a49`:

```sh
python3 deploy/relay-deploy.py \
  --config /mnt/q/work/task115-test-consumer-01a12b33/deploy/relay.json \
  --requested-revision afb2cbdbcb82294604c51ec0ce4c2a62cf272a49 \
  --resolved-revision afb2cbdbcb82294604c51ec0ce4c2a62cf272a49 \
  --phase inventory
```

The sanitized public result was:

```json
{
  "status": "blocked",
  "blockers": ["configuration-different"],
  "readOnly": true,
  "mutationAuthorized": false,
  "configuration": {"consumer": "equivalent", "deployment": "different", "status": "different"},
  "installed": {"status": "present", "revision": "dbfea1889da994791a5b6c05d97a71405d21eac5"}
}
```

The accompanying `RELAY_DEPLOYMENT_RESULT=PASS;phase=inventory;authority=read-only`
and exit 0 mean that observation completed; the JSON blocker remains material.
An owner-authorized read-only comparison of the literal nonsecret installed
snapshot verified its SHA-256 against the exact release manifest, its protected
0600 single-link file and current release/identity binding. After the public
inventory's source-selector exclusion and default-effort normalization, the
only differing key was `environment.reviewerRepositories`: the installed
snapshot explicitly listed `codex-relay-testbed`, `codex-relay`,
`shared-governance` and `codex-relay-testbed-2` under owner `jresearchsoftware`;
the tracked TEST configuration omitted that field. Narrowing or retaining
those existing capabilities needs explicit current Task authority before
configuration reconciliation; neither this diagnosis nor inventory grants it.
Protected credential/TLS state was reported only as reusable metadata. Both
local runner registrations were reported reusable without a fresh token;
current GitHub installation permissions, runner-group restrictions and
DNS/ingress remained explicit owner-admin verification gaps. No install,
upgrade, reconciliation, activation, TLS/ingress operation or permission change
was attempted, and no secret/key contents were read.

A read-only TEST MCP `check_pr_review_target` on the freshly re-read historical,
closed/merged PR 2 confirmed authenticated App slug
`jresearch-relay-test-reviewer`, expected actor
`jresearch-relay-test-reviewer[bot]`, exact head
`91e29c09ac089dfd10dbaf6e8feeb42a9171395e` and `ready_for_review: false`.
This proves that bounded TEST transport/identity observation, not new workflow
qualification. The exposed connector had four existing review/authority tools
and no `submit_manual_outcome`. Its repository schema also listed other
repositories, so the README's TEST-only intent cannot establish a current
TEST-only server allowlist. Those other targets were not probed. The
configuration mismatch and missing new capability leave installed Task 115
qualification unproven.

### Authorized TEST consumer preparation

The current v3 [Decision 6110064799](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110064799)
and [successor Request 6110068398](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110068398)
authorize bounded consumer/runbook reconciliation in the same active manual
Step 1, preserving existing credentials, shared infrastructure and immutable
historical attempts. Their read-back body SHA-256 values are respectively
`1d662713e73803586945c7644601f8029d8398447f571b6bfd9a43b4212c4468` and
`e9eb320876b41a34e03d9e8f033280be36fa72c109cbe96d42bb41cf32d1b978`.

[TEST draft PR 3](https://github.com/jresearchsoftware/codex-relay-testbed/pull/3)
at `1602f1cdc765f844eebacc5d750cfa4667ce3ccb` records the exact existing
four-repository Reviewer allowlist and Task-115-only TEST fixture/call boundary.
It changes only `deploy/relay.json` and README; eight native Debian unittest
checks and whitespace validation passed. It does not change App capabilities,
keys, Task 76 history or installed state. The old configured `afb2cbdb...`
entrypoint rejects the allowlist field with
`INVALID_DEPLOYMENT_CONFIG:environment`; its source predates that supported
configuration. Read-only inventory from a separate clean exact already
installed `dbfea188...` checkout, explicitly selected in both revision
arguments, reports `status: observed`, no blockers and equivalent
consumer/deployment intent. This observation changes no installation target.
Published product candidate selection, workflow projection, supported TEST
upgrade and live capability qualification remain separate next actions.

### Original Task 115 Writer publication binding

The qualified owner SSH transport reached the fixed installed public
`/opt/codex-relay/relay-writer-controller` with no command arguments and only
this read-only request on stdin:

```json
{"operation":"publication-state","runId":38144146016,"attemptId":"run-38144146016"}
```

The installed release/manifest identity is
`b4cb4943d52dd375d8c6800959b3264fad082cb8`. The wrapper matches its public
template and five relevant installed source files match the exact published
Git blobs. The repository-bound receipt confirms Task 115, Step 1, manual Issue
route and branch `codex/task-115-step-1`, with no publication intent, published
head or recovery. It retains the original schema-v3 Request 6109630038 and
body digest `baead0f01eb40853eff28791cbb067d703f811037fa26e25b8c121d52e4d4bde`.
Its immutable authority digest is
`1e4d521f871f38cd415fab03d010dd9e83e00612d14bcea75b5cf19520673142` and consumer
digest is `4955dd18448f0859b43f28111e89a534ab83f4070124deab7d191b59df073837`.

No manual Outcome publication was invoked. The live same-Step successor
Request does not rewrite that admitted binding. Installed manual publication
revalidates current native authority; the changed selected Request may therefore
be an actual authority boundary before final publication. That implication is
source analysis, not a claimed observed publication failure. No journal rebind,
new execution, other Task read or direct credential access was used.

Real GitHub Issue comments and native reviews must establish readable default rendering, malicious-text neutrality, canonical parser/digest readback and convenient expansion/copy of the full manual handoff using GitHub's code-block copy affordance. If folding fails that test, keep the complete prompt open by default. Successful source tests do not supply this evidence. Any live fixture must be disposable, Task-owned and isolated; historical #84/#89/#109 and PR #87/#110/#112 records are read-only references.

Independent exact-head source acceptance, any separately authorized installed qualification and honest warning disposition remain outstanding until their native records exist. Task 115 stays keep-open under its current charter. This source report grants no deployment, release, merge, Issue closure or unrelated continuation authority.
