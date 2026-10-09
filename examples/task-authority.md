# Typed Task authority examples

These synthetic examples accompany the [Task workflow guide](../docs/task-workflow.md).
They describe one Issue #42, its resulting PR #43, base A (40 `a` characters)
and candidate B (40 `b` characters). No example grants live authority or
recommends a model. Replace `consumer-selected-model` with the resolved,
backend-supported consumer model; validation IDs must be supported or declared
by that consumer.

Use Reviewer `publish_task_authority` with `{repository, record}`, passing
one complete JSON record below as `record`. The service renders a canonical
`relay-authority` fence and verifies native bindings; do not post these as
ordinary owner comments or send legacy CR2 input for a migrated Task. The
[shared definition](../contracts/src/github-authority-v1.json) owns the schema.
Publication still needs the qualified enabled paired installation and owner
authorization described in the [Reviewer contract](../reviewer/README.md).

## New Task Request

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
`renderAuthorityRecord(record)` output with no appended publisher marker.
In a live call, copy the returned `reference`: its digest includes all native
provenance bytes, not just the JSON. Never reuse these synthetic IDs/digests.

## Decision and replacement Request

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

## PR Change Request and remediation

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
