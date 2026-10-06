# Native Change Request authority

Native Reviewer identity/head selection and common attempt orchestration live in
`../controller/src`. This directory retains CR parsing and the repository secret
scanner. Native review content is authority; incidental Markdown and thread-title
dash style do not define a security boundary. Execution state and Outcome publication belong to the controller. Run `npm test`.

Executable `REQUEST_CHANGES` uses contract `2.0`. The Reviewer caller sends
`change_request` as structured tool input; repository, PR and reviewed/starting
head come from the trusted top-level target fields. Reviewer validates the
complete input before any GitHub request and renders both the readable native
review and its `reviewer-executable-cr` JSON block. The native review is the
only Change Request authority. The caller does not author headings or YAML.

The shared [bounded definition](../reviewer/src/executable-cr-v2.json)
supplies the tool's typed schema, bounds and native validation names to Rust and
Node. It is included in both runtime source identities. Both validators support
only the keywords and formats in that checked-in definition. Text limits count
UTF-8 bytes; descriptions are single-line NFC text. Findings retain their supplied
stable IDs (a letter followed by letters, digits, `_` or `-`), up to 30 findings.
Validation is a nonempty set of supported native check names, independently of
repeated compatibility prose. Additional starting-state requirements may be
empty because the exact starting head is already bound. Effort and Subagents
may be omitted by authors. The shared schema encodes the execution defaults
from [AGENTS.md](../AGENTS.md#work-within-the-admitted-goal); Node admission and
Rust rendering use those same values. Reviewer renders resolved launch metadata;
downstream validation and worker launch preserve it, including explicit overrides.
Existing rendered reviews keep their explicit values; the historical fixture
still tests its intentional overrides. Authoring defaults affect unresolved
fields only. Use the paired Reviewer/Node revision for the new optional fields.
Step is a positive safe integer matching the current remediation launch profile
and persistent Issue/PR labels. A new CR uses current N+1; execution and CR
transport retries keep that CR's Step. History never supplies Step.
Model and effort remain bounded argument identifiers with backend capability
truth. Subagents permission is separate. There is no task path allowlist or
interactive review profile.

Validation names are bounded identifiers, not proof that a check ran or that
this repository supplies a consumer's deployment checks:

| Contract name | Validation owner/surface |
| --- | --- |
| `routing-tests`, `diagnostics-tests` | `controller/` suites |
| `issue-writer-tests` | `runtime/` suite |
| `remediation-tests` | `contracts/` suite |
| `rust-reviewer-tests-format`, `rust-format` | `reviewer/` Cargo tests/format |
| `diff-check`, `secret-scan` | Git diff check and tracked credential scan |
| `dispatcher-worker-integration`, `workflow-static`, `ansible-tests`, `github-test-validate` | Consumer-supplied installed-runtime, workflow, deployment or native CI checks |

These historical names remain accepted. The optional deployment-owned
`validationNames` array adds up to 32 unique IDs matching
`[a-z][a-z0-9-]{0,63}` in both Node and Reviewer config. The tool advertises their
union with the table above; each CR still requests 1–12 unique names. Unknown or
undeclared IDs are rejected by both sides. No ID is interpreted as a shell command;
consumer validation code owns its meaning. See the
[integration contract](../docs/integration-reference.md#consumer-validation-identifiers).

The `2.0` native representation, historical enum and byte-for-byte fixture are
preserved: configured vocabulary is an extension, not a new serialization.
Old binaries fail closed on extended config/custom IDs; deploy the paired
Reviewer/Node revision before opting in. Existing configs with no declarations
keep their behavior and consumer digest. A changed config requires attempt
reconciliation. The shared schema is a `contracts/` concern even though its
physical JSON file remains under `reviewer/src/` for Rust compilation.

Only request applicable checks. A consumer must supply its own checks and
report their results; this candidate does not include deployment roles or
pretend that local tests satisfy an installed-runtime proof.

The consumer checks the canonical JSON encoding, including duplicate keys,
version and target binding, and reads findings and validation directly from it.
Existing `1.0` YAML/native reviews remain readable through the historical parser;
the current Reviewer publishes only `2.0` executable CRs. Unknown versions,
multiple execution blocks and mixtures of old/new contracts fail closed.

The [semantic input fixture](test/fixtures/executable-cr-v2-input.json) and
[canonical native form](test/fixtures/executable-cr-v2.md) cover launch metadata
and native review authority admission. All identities and task numbers are synthetic. Node tests admit that form through the current routing
controller. Rust tests compare the rendered bytes, intercept the actual mock
GitHub publication and pipe it into that same consumer, and reject the shared
invalid corpus before any mock GitHub request. Run `npm test` here and
`cargo fmt --check && cargo test --locked` in `reviewer/`; Cargo tests
require Node for the cross-language checks. Consumer native exact-head CI must retain a separate installed-runtime proof
boundary; local tests do not qualify its deployment adapters.

## Owner Step metadata procedure

Steps decompose progress toward the Task's authorized goal and boundaries as
work evolves; completing a Step does not complete the Task. One Codex thread
may span successive Steps. Historical Task descriptions do not govern future
Step decomposition. See [Task identity and startup rename](../AGENTS.md#task-identity-and-startup-rename).
The Issue body remains the current Task contract; the native review body is the
sole executable CR authority, with the canonical Issue linked for Task identity.
Implementation branch, commit and PR flow remains Codex-owned under
[the Git handoff policy](../AGENTS.md#canonical-checkout-and-safe-git-handoff).

Task producers and updates preserve exactly one explicit `Issue closure policy`
field in the canonical Issue: `keep-open`, or `close-authorized` only with owner
authority. Approval, Step completion and CR outcome tokens do not authorize
closure. Missing, malformed or conflicting metadata selects `keep-open` with
a visible warning; record owner reconciliation in the Issue body.
`keep-open` means known work or evidence remains after implementation. Nearby
prose should explain why the Issue stays open and what outcome would make closure appropriate.
This adds no required structured field, parser gate or automatic closure rule.

### Executable CR publication and synchronization

1. For a **new** executable CR, read the current linked Issue and PR, requiring
   exactly one valid `step-N` on each, with equal N. Put N+1 in structured
   `change_request.step` and its launch thread title. Preserve exact reviewed
   head, findings, profile, validation and boundary authority. The optional owner
   `prepare` helper performs these authoring reads without mutating metadata.
2. Publish through the reserved Reviewer tool. The Reviewer validates the exact
   repository, linked Issue, PR and reviewed head before native publication.
   After verified publication, the same Reviewer operation ensures `step-(N+1)`
   exists, replaces each target's Step label while preserving unrelated labels,
   updates the bounded `Task <Issue> · Step <N+1> · <CR ID> · <CR purpose>` PR title and
   re-reads the targets. Successful `REQUEST_CHANGES` includes verified metadata
   synchronization; ordinary owner orchestration no longer performs post-CR writes.
3. A failed or uncertain review publication uses the existing duplicate/recovery
   path. Partial synchronization also resumes that **same native review ID** and
   authored Step, allowing only N or N+1, without another review or increment.
   Changed head/review/binding or malformed/multiple labels fails closed. Apply
   the ready label only after synchronization succeeds. `APPROVE` changes no Step.

The Reviewer App now needs `actions:read` for admission/active-work reads and
`issues:write` for bounded Step label synchronization, alongside existing
`metadata:read`, `pull_requests:write` and `checks:write`. Tokens remain restricted
to the configured repository. These source permissions do not approve a live
App permission update or deployment; an existing consumer requires separately
authorized permission reconciliation and upgrade. Native CR versions `1.0`
(readable) and `2.0` (published) remain unchanged.

### Explicit owner new-phase preparation

For an explicitly owner-authorized **new implementation phase** of the same Task,
including a reopened or split continuation, deterministic preparation reads the
canonical Issue's current Step N and advances precisely to N+1. An existing PR
is optional; when supplied it must link that exact Issue in the configured
repository and keep its branch, base and head binding. Preserve unrelated labels
and update only the bounded canonical Task/Issue/Step PR title. No phase is
inferred from history, prose, prior Outcomes or a largest-ever Step.

For [Issue-authorized implementation continuation](../controller/README.md#issue-authorized-implementation-continuation),
record the current goal and explicit starting head, existing branch and applicable
PR binding in the canonical Issue. An execution retry or continuation of the same
unfinished phase keeps the current Step. Only an explicitly owner-authorized new
implementation phase advances it through this procedure, including the existing
PR when one is present. This uses Issue authority without manufacturing a Reviewer
CR; metadata preparation alone grants no launch authority.

[`step-synchronization.mjs`](src/step-synchronization.mjs) verifies `/user` is the
configured human owner (`User`), rejecting Writer/Reviewer App identities. Its
bounded request accepts only the stated operation and fields:

- `{operation:"prepare",pullRequest}`: read-only N+1 authoring assistance for a new CR.
- `{operation:"advance-phase",issueNumber,currentStep,newPhaseAuthorized:true}`:
  explicit owner new-phase preparation. Optional `pullRequest` requires a
  single-line NFC `purpose` of 1–512 UTF-8 bytes; the helper constructs and bounds
  the title instead of accepting arbitrary titles or other metadata.
- `{operation:"keep-step",issueNumber,currentStep,pullRequest?}`: explicit read-only
  bypass for execution retries and continuation within the same phase. Never call
  `advance-phase` for those retries.
- `{operation:"recover-legacy-review",pullRequest,reviewId,legacyPublicationRecoveryAuthorized:true}`:
  exceptional, explicitly owner-authorized migration reconciliation only, as
  described below; it does not replace normal Reviewer post-CR synchronization.

`currentStep` binds the exact N to N+1 operation. A partial native label/title
failure can resume that same request with only N/N+1 labels; repeating it cannot
advance to N+2. Re-read verification exposes partial failures before launch.
Phase requests cannot supply labels, body changes, arbitrary metadata or review
IDs. The separate legacy recovery request accepts only the exact review ID and
explicit migration authorization, never a new CR or arbitrary metadata. The
former owner `synchronize` operation is retired; Reviewer publication is the sole normal post-CR metadata writer.

The optional Linux adapter uses the caller's ordinary owner `GITHUB_TOKEN`:

```sh
node contracts/src/step-synchronization.mjs < metadata-request.json
```

This helper grants no launch, review publication, merge, deployment or Issue-close
capability. Step labels alone never launch work. GitHub has no transaction across
an Issue and PR; serialize metadata operations and retain fail-closed admission
until labels, title and applicable authority agree.

### Legacy publication migration recovery

New Reviewer operations retain the exact Issue/PR Step binding and initial PR
title before native publication. A historical published SQLite record may lack
that binding or its initial-title field. The
Reviewer may accept such a record only when both labels and the canonical
explicit-CR-ID title are already synchronized; it never invents an old anchor
or silently mutates a newly linked Issue. Existing authority hashes must still
match when upgrading an older anchor. Otherwise it returns
`LEGACY_STEP_BINDING_REQUIRED` and preserves the original native review.

After this error, the owner can explicitly authorize the bounded
`recover-legacy-review` helper operation. It verifies the configured `/user`
human owner, exact current decisive Reviewer `CHANGES_REQUESTED` ID, repository,
PR, canonical linked Issue and unchanged reviewed head. Step comes solely from
that same executable review body. Only its N/N+1 metadata is eligible; unrelated
labels and current Task/CR authority are preserved. The helper re-reads binding,
review, labels and canonical title after updates. Repeating this migration repair
cannot author a review, infer a Step, advance again or launch work.

Then replay the **original Reviewer payload** through its existing
publication-recovery path, retaining the same native review ID and Step.
Changed authority, missing/malformed/multiple labels or ambiguous publication
needs owner reconciliation. Do not invoke this exception for current Reviewer
operations or normal post-CR synchronization; the former general `synchronize`
owner operation remains retired.

Remediation follows [progress-bounded execution](../docs/execution-policy.md)
inside the admitted worker. Contract counts and Step metadata bind authority;
they do not limit local correction iterations or authorize automatic retries.
