# Change Request CR-24-serialization

Executable REQUEST_CHANGES (contract 2.0).

Repository: example-org/sample-project

Pull request: #25

Reviewed and required starting head: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`

## Remediation profile

Thread name: Task 24 — Step 2 — Reviewer-owned CR serialization

Supplied Step: 2

Codex model: future-model

Codex reasoning effort: max

Subagents: Off

## Findings

### CR12-F1 — major

Problem: A valid CR required a manual validation heading rename.

Impact: Synthetic case A stopped with CURRENT&#95;VALIDATION&#95;MISSING.

Remediation: Reviewer must serialize structured validation before publication.

Acceptance criteria:

- The published form is admitted without heading repair.

Evidence:

- Synthetic case A: parser-incompatible validation heading.

### serialization_gap_2 — major

Problem: Repeated compatibility prose was reconstructed as duplicate executable data.

Impact: Synthetic case B stopped with CONTRACT&#95;DUPLICATE&#95;VALUE.

Remediation: Keep structured executable values separate from repeated prose.

Acceptance criteria:

- Stable finding IDs and supplied Step round-trip unchanged.

Evidence:

- Synthetic case B: duplicate compatibility data during admission.

## Required validation

- diff-check
- github-test-validate
- remediation-tests
- routing-tests
- rust-reviewer-tests-format
- secret-scan

## Completion and publication requirements

- Commit useful changes and stop for fresh independent exact-head review.

## Protected boundaries

- No production mutation, deployment, canary, merge or Issue closure.
- Preserve Reviewer identity and exact-head publication.

## Owner-policy reconciliation

- No allowed&#95;paths authority. Subagents: Off.
- No allowed&#95;paths authority. Subagents: Off.
- Model and effort pass through; Subagents permission is separate.

## Completion outcomes

Success: `TASK_24_CR_SERIALIZATION_IMPLEMENTED_PENDING_REVIEW` — Implementation is complete and awaits independent review.

Blocked: `TASK_24_CR_SERIALIZATION_BLOCKED` — Preserve useful commits and explain the concrete blocker.

## Reviewer-owned execution data

```reviewer-executable-cr
{
  "change_request": {
    "blocked_outcome": "Preserve useful commits and explain the concrete blocker.",
    "blocked_token": "TASK_24_CR_SERIALIZATION_BLOCKED",
    "change_request_id": "CR-24-serialization",
    "codex_effort": "max",
    "codex_model": "future-model",
    "completion_requirements": [
      "Commit useful changes and stop for fresh independent exact-head review."
    ],
    "findings": [
      {
        "acceptance_criteria": [
          "The published form is admitted without heading repair."
        ],
        "evidence": [
          "Synthetic case A: parser-incompatible validation heading."
        ],
        "id": "CR12-F1",
        "impact": "Synthetic case A stopped with CURRENT_VALIDATION_MISSING.",
        "problem": "A valid CR required a manual validation heading rename.",
        "remediation": "Reviewer must serialize structured validation before publication.",
        "severity": "major"
      },
      {
        "acceptance_criteria": [
          "Stable finding IDs and supplied Step round-trip unchanged."
        ],
        "evidence": [
          "Synthetic case B: duplicate compatibility data during admission."
        ],
        "id": "serialization_gap_2",
        "impact": "Synthetic case B stopped with CONTRACT_DUPLICATE_VALUE.",
        "problem": "Repeated compatibility prose was reconstructed as duplicate executable data.",
        "remediation": "Keep structured executable values separate from repeated prose.",
        "severity": "major"
      }
    ],
    "owner_policy_reconciliation": [
      "No allowed_paths authority. Subagents: Off.",
      "No allowed_paths authority. Subagents: Off.",
      "Model and effort pass through; Subagents permission is separate."
    ],
    "protected_boundaries": [
      "No production mutation, deployment, canary, merge or Issue closure.",
      "Preserve Reviewer identity and exact-head publication."
    ],
    "remediation_thread_title": "Task 24 — Step 2 — Reviewer-owned CR serialization",
    "required_validation": [
      "diff-check",
      "github-test-validate",
      "remediation-tests",
      "routing-tests",
      "rust-reviewer-tests-format",
      "secret-scan"
    ],
    "starting_state_requirements": [],
    "step": 2,
    "subagents_allowed": false,
    "success_outcome": "Implementation is complete and awaits independent review.",
    "success_token": "TASK_24_CR_SERIALIZATION_IMPLEMENTED_PENDING_REVIEW"
  },
  "pull_request": 25,
  "repository": "example-org/sample-project",
  "reviewed_head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "schema_version": "2.0"
}
```
