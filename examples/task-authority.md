# Typed Task authority examples

These synthetic examples accompany the [Task workflow guide](../docs/task-workflow.md).
They describe one Issue #42, its resulting PR #43, base A (40 `a` characters)
and candidate B (40 `b` characters). No example grants live authority or
recommends a model. Replace `consumer-selected-model` with the resolved,
backend-supported consumer model; validation IDs must be supported or declared
by that consumer.

For new `github-native-v1` work, the current stable charter and applicable trusted
Decisions supply authority. A complete public Task Request is not required.
Trusted Writer creates a schema `4.0` admission snapshot and allocates Step when
the existing owner ready command admits execution. Independent native CRs carry
no Step and need no replacement Request. Already admitted schema `3.0` attempts
retain their original Request/CR, Step and source bindings.

Use Reviewer `publish_task_authority` with `{repository, record}` for a complete
Decision, native CR or acceptance record. The service renders English substance
and one canonical `relay-authority` JSON block and verifies native bindings;
ordinary owner comments cannot substitute for typed publication. The
[current v4 definition](../contracts/src/github-authority-v4.json) and
[retained v3 definition](../contracts/src/github-authority-v1.json) own the schemas.
Submit a manual Outcome claim through the separately enabled
`submit_manual_outcome` capability; Reviewer does not publish Writer Outcomes.
Publication still needs the qualified enabled paired installation and owner
authorization described in the [Reviewer contract](../reviewer/README.md).

## Current v4 charter and minimal Decision

The stable Issue body in this synthetic scenario is exactly the following UTF-8
text, including its final newline. Its hash is
`397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6`:

```text
Authority model: github-native-v1

Goal: Document local validation and completion.
Scope: Repository documentation only.
Protected boundaries: No runtime changes or deployment.
Issue closure policy: close-authorized
```

The fictional owner has authorized this closure policy. It permits closure only
after verified independent acceptance and no remaining work; implementation,
admission, Step completion or merge does not establish Task completion.

When the owner accepts explicit coverage of no-change completion, publish the
following Task-scoped Decision through `publish_task_authority`. The Decision
amends current scope without allocating Step, launching work or requiring a full
replacement Request. Omitted execution-profile values use the admitted consumer
defaults. Ordinary selected evidence remains context, rather than Task authority.

```json
{
  "schema_version": "4.0",
  "kind": "decision",
  "repository": "example-org/sample-project",
  "task": 42,
  "parent": {"kind": "issue", "number": 42},
  "charter_sha256": "397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6",
  "purpose": "Include no-change completion in the documentation",
  "amendments": {
    "scope": ["Document the local validation workflow.", "Explain no-change completion."]
  },
  "supersedes": null,
  "context": []
}
```

Copy the returned native `reference` when a later record needs this exact source.
An explicit successor Decision uses that reference in `supersedes`; otherwise
active Decisions accumulate in native comment-ID order. Apply the existing
`codex-ready-auto` or `codex-ready-manual` command when the Task is ready for an
execution admission. Writer resolves and stores the current snapshot, allocates
Step, and projects labels/title. No additional authoring form or Request is needed.

## Current v4 independent PR Change Request

For a genuine PR #43 at candidate B, the independent reviewer compares the whole
candidate with observed native PR base A and publishes actionable findings.
This CR has no `step`, `supersedes`, complete Request or Task closure policy:

```json
{
  "schema_version": "4.0",
  "kind": "change-request",
  "repository": "example-org/sample-project",
  "task": 42,
  "parent": {"kind": "pull_request", "number": 43},
  "charter_sha256": "397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6",
  "purpose": "Correct no-change completion instructions",
  "change_request_id": "CR-42-001",
  "branch": "codex/task-42",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "reviewed_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "findings": [{
    "id": "F1",
    "severity": "major",
    "problem": "At candidate B, the guide requires a PR for every completed Task; base A contained no such instruction.",
    "impact": "An owner cannot use the supported no-change completion path.",
    "remediation": "Explain Issue-surfaced Writer Outcomes and Task Approval for no-change results.",
    "acceptance_criteria": ["The walkthrough permits no-change completion without an empty commit or artificial PR."],
    "evidence": ["Introduced at B (bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb); compared with A (aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)."]
  }],
  "overrides": {"validation": ["diff-check", "secret-scan"]},
  "context": []
}
```

The native review binds `CHANGES_REQUESTED` and `commit_id` B. Fresh publication
checks the observed PR base SHA; recovery retains its reserved exact body/base.
Reviewer changes no Step labels/title. The existing ready command admits
remediation; Writer verifies the native CR/head and Draft transition, then
allocates Step and supplies the execution handoff. Replaying that admission or
recovering its publication retains the same binding. Further acceptance requires
fresh independent review of the resulting exact head. CR execution overrides
cannot authorize unrelated work or Task closure.

## Current v4 manual Outcome and no-PR approval

This separate example reports a legitimate no-PR local qualification, rather
than PR remediation. Its fictional admission is `run-9003`, Step 1. The exact
authority and admission bindings belong to trusted Writer admission; a caller
copies the canonical `authority` object and `admission: {attempt, step, sha256}`
from the existing copyable manual handoff binding/template. No private attempt
store read or additional authoring step is required; the caller does not allocate
Step or replace these bindings. Synthetic IDs/hashes below illustrate
the shape only. Live records use the admitted bindings and returned native
references, including publisher provenance bytes; never reuse these examples.

The complete Outcome claim is:

```json
{
  "schema_version": "4.0",
  "kind": "outcome",
  "repository": "example-org/sample-project",
  "task": 42,
  "parent": {"kind": "issue", "number": 42},
  "charter_sha256": "397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6",
  "authority": {
    "charter": {"kind": "issue-body", "id": 4200, "parent": {"kind": "issue", "number": 42}, "sha256": "397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6"},
    "decisions": [{"kind": "issue-comment", "id": 4102, "parent": {"kind": "issue", "number": 42}, "sha256": "a95f0946b4c423897c7e351680bc08e5ae159ced950b9f28c998125befad1a20"}],
    "change_request": null,
    "compatibility_request": null,
    "sha256": "a514fd2e5d713fdcbd45e9f534487c0cc765b10f3d051059f0ee1734bf76e7ca"
  },
  "admission": {"attempt": "run-9003", "step": 1, "sha256": "033e865b8ee0889186bc346d73109a16940678a32c3571ebc8c0628b1083c6af"},
  "step": 1,
  "attempt": "run-9003",
  "status": "implemented",
  "result": {"kind": "qualification", "revision": "qualification-9003", "identities": [{"kind": "qualification-run", "id": "9003"}]},
  "warnings": [{
    "source": "local-qualification:9003",
    "impact": "This result supplies local evidence only.",
    "resolution": "Local evidence is retained for independent review.",
    "next_action": "Review the exact result and applicable remaining conditions.",
    "evidence_gaps": ["No installed or live deployment was qualified."]
  }],
  "limitations": ["No installed or live deployment evidence."],
  "summary": "The admitted local qualification completed; independent acceptance remains required."
}
```

Send that object as `result` to owner-managed OpenAI MCP `submit_manual_outcome`
with `repository: "example-org/sample-project"`, `task: 42`, `run_id: 9003`.
The tool accepts only those four fields; it supplies the protected fixed Writer
transport. No owner result comment, approval or second dispatch is required.
Writer verifies the admitted manual attempt, current sources, exact result and
unique artifact, and publishes or recovers one Writer Bot Outcome. The receipt
supplies its native ID, parent, URL and exact body hash. Execution claims remain
claims pending independent acceptance.

For this no-PR result, the independent reviewer copies the exact Writer Outcome
reference from the receipt and retains its material warnings and limitations.
The following construction produces a complete Task Approval from `outcome`, the
complete object above; `writerOutcomeReference` denotes that verified reference:

```js
const { attempt, status, ...acceptedResult } = outcome;
const approval = {
  ...acceptedResult,
  kind: 'task-approval',
  outcome: writerOutcomeReference,
  verdict: 'APPROVE',
  summary: 'The exact immutable qualification result meets its admitted acceptance criteria.'
};
const input = { repository: outcome.repository, record: approval };
```

Publish `input` through `publish_task_authority`. Disposition warnings based on
the actual review without dropping their source/impact or evidence gaps. A
`task-review` instead binds the same authority/admission/Outcome/result, uses
`verdict: 'REQUEST_CHANGES'`, and supplies bounded findings; it does not invent a
PR CR. An open implementation PR needs the existing native exact-head PR verdict
through `submit_pr_review`, rather than an extra Task Approval. Neither approval
form infers Task completion from `implemented` or `next: null`; owner orchestration
checks applicable completion conditions and remaining work before closure.

## Retained v3 compatibility examples

The historical examples below retain their schema `3.0` fields and Request/CR
chain for already admitted attempts and recovery. They are not prerequisites for
new v4 work. Their synthetic body digests use the historical `legacy-v1` renderer;
current publication uses human-readable rendering while recovery retains the
reserved original body. Do not rewrite an admitted v3 attempt or manufacture a
new complete Request merely to execute current v4 work.

### Historical new Task Request

The stable Issue body used for these examples is exactly the following UTF-8
text, including its final newline:

```text
Authority model: github-native-v1

Goal: Document local validation and completion.
Scope: Repository documentation only.
Protected boundaries: No runtime changes or deployment.
Issue closure policy: close-authorized
```

Start with the Issue's `step-1` baseline. The first Request has no predecessor,
no selected evidence and no existing PR. Its explicit completion intent permits
closure only after independent acceptance, safe merge where applicable and no
remaining work; it does not grant the worker merge/closure authority.

```json
{
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "boundaries": [
    "No runtime changes or deployment.",
    "Worker cannot publish, approve, merge or close Issues."
  ],
  "branch": "codex/task-42",
  "charter_sha256": "397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6",
  "context": [],
  "continuation": {
    "hold": false,
    "next": null,
    "task_complete": true
  },
  "decisions": [],
  "effort": "xhigh",
  "existing_pr": null,
  "issue_closure_policy": "close-authorized",
  "kind": "task-request",
  "model": "consumer-selected-model",
  "parent": {
    "kind": "issue",
    "number": 42
  },
  "purpose": "Document local validation and completion",
  "repository": "example-org/sample-project",
  "route": "auto",
  "schema_version": "3.0",
  "scope": [
    "Document the local validation workflow."
  ],
  "starting_head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "step": 1,
  "subagents": true,
  "supersedes": null,
  "task": 42,
  "validation": [
    "diff-check",
    "secret-scan"
  ]
}
```

For the fictional native Request comment ID 1001, define `firstReference` as:

```json
{
  "id": 1001,
  "kind": "issue-comment",
  "parent": {
    "kind": "issue",
    "number": 42
  },
  "sha256": "229c5c7bcc0566ed0efa1e66f127772b4fd8f3c58aaa1e24d5ccb345a5859b49"
}
```

The synthetic native body used for this digest is the exact
`renderAuthorityRecord(record, {rendererVersion: 'legacy-v1'})` output with no
appended publisher marker.
In a live call, copy the returned `reference`: its digest includes all native
provenance bytes, not just the JSON. Never reuse these synthetic IDs/digests.

### Historical Decision and replacement Request

Before execution, the owner accepts explicit coverage of no-change completion.
Publish this Task-scoped Decision; it amends scope without changing Step or
route and does not execute work by itself:

```json
{
  "amendments": {
    "scope": [
      "Document the local validation workflow.",
      "Explain no-change completion."
    ]
  },
  "charter_sha256": "397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6",
  "context": [],
  "kind": "decision",
  "parent": {
    "kind": "issue",
    "number": 42
  },
  "purpose": "Include no-change completion in the documentation",
  "repository": "example-org/sample-project",
  "schema_version": "3.0",
  "supersedes": null,
  "task": 42
}
```

For the fictional Decision comment ID 1002, the returned `decisionReference`
uses the same synthetic-body convention:

```json
{
  "id": 1002,
  "kind": "issue-comment",
  "parent": {
    "kind": "issue",
    "number": 42
  },
  "sha256": "00694eed9393b4d27a902c6324b7c18fc357f6aa68053400496138f4ee853b9d"
}
```

Construct the next **complete** Task Request from the first record and the
returned references. This JavaScript shows record construction, not a separate
Relay CLI or partial-patch publication API:

```js
const replacementRequest = {
  ...firstRequest,
  scope: decision.amendments.scope,
  decisions: [decisionReference],
  supersedes: firstReference
};
// Reviewer tool input:
const input = { repository: firstRequest.repository, record: replacementRequest };
```

Publish that record through the same tool. All original fields remain present;
its normalized `scope` must equal the selected Decision amendment. Step stays
1 because this replaces the same unexecuted phase. Replacing only label/body
prose, selecting the Decision without normalizing its values, or dropping the
predecessor is invalid. At fictional native comment ID 1003 its returned
`reference` is the predecessor in the CR below. A PR-scoped Decision would
instead require its exact PR in `existing_pr`; this example uses Task scope.

### Historical PR Change Request and remediation

The replacement Request executes and Writer produces PR #43 at B, with a
trusted Outcome bound to that Request. The independent reviewer compares the
entire candidate B with base A and finds the documentation defect in F1. With
owner-authorized publication, send this **complete** typed CR through
`publish_task_authority`. It supersedes comment 1003, advances Step to 2 and
retains the normalized Decision semantics. PR parent and `existing_pr` agree;
`reviewed_head_sha` and `starting_head` both identify B.

```json
{
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "boundaries": [
    "No runtime changes or deployment.",
    "Worker cannot publish, approve, merge or close Issues."
  ],
  "branch": "codex/task-42",
  "change_request_id": "CR-42-001",
  "charter_sha256": "397f0e98f0271fafc4daca0933202fc68ba87a2d489001f5e1110092fe3127b6",
  "context": [],
  "continuation": {
    "hold": false,
    "next": null,
    "task_complete": true
  },
  "decisions": [
    {
      "id": 1002,
      "kind": "issue-comment",
      "parent": {
        "kind": "issue",
        "number": 42
      },
      "sha256": "00694eed9393b4d27a902c6324b7c18fc357f6aa68053400496138f4ee853b9d"
    }
  ],
  "effort": "xhigh",
  "existing_pr": 43,
  "findings": [
    {
      "acceptance_criteria": [
        "The walkthrough permits no-change completion without an empty commit or artificial PR."
      ],
      "evidence": [
        "Introduced at B (bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb); compared with A (aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)."
      ],
      "id": "F1",
      "impact": "An owner cannot use the supported no-change completion path.",
      "problem": "At candidate B, the guide requires a PR for every completed Task; base A contained no such instruction.",
      "remediation": "Explain Issue-surfaced Writer Outcomes and Task Approval for no-change results.",
      "severity": "major"
    }
  ],
  "issue_closure_policy": "close-authorized",
  "kind": "change-request",
  "model": "consumer-selected-model",
  "parent": {
    "kind": "pull_request",
    "number": 43
  },
  "purpose": "Correct no-change completion instructions",
  "repository": "example-org/sample-project",
  "reviewed_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "route": "auto",
  "schema_version": "3.0",
  "scope": [
    "Document the local validation workflow.",
    "Explain no-change completion."
  ],
  "starting_head": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "step": 2,
  "subagents": true,
  "supersedes": {
    "id": 1003,
    "kind": "issue-comment",
    "parent": {
      "kind": "issue",
      "number": 42
    },
    "sha256": "43f7005decf24121d4b90abd4db3c1ded920c1ca086e2a2f1d4841370c178231"
  },
  "task": 42,
  "validation": [
    "diff-check",
    "secret-scan"
  ]
}
```

The native review must be trusted `CHANGES_REQUESTED` with `commit_id` B.
Reviewer publication verifies Issue/PR Step 2 and the bounded CR title; its
Writer lifecycle action verifies Draft for that same native CR/head. Apply
`codex-ready-auto` to PR #43 after successful publication/synchronization.
The worker fixes F1 on `codex/task-42`; Writer publishes the new head and
Outcome. Independent review must accept that new exact head. Recovery of the
same CR publication does not increment Step or execute another worker.

Without a genuine PR, publish `task-review` evidence on Issue #42, select that
evidence in a new complete Task Request, and use `task-approval` for the
implemented immutable result. Task findings are not a `change-request`, and
Task Approval does not merge a PR. See the
[no-PR acceptance contract](../contracts/README.md#github-native-task-authority).
