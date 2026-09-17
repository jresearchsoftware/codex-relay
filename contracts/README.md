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
empty because the exact starting head is already bound. Subagents defaults Off.
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

The ChatGPT/owner orchestration that authors and publishes the review also
performs these small native metadata operations. They are not additional human
launch actions and do not grant the Reviewer App label permissions.

1. Read the linked canonical Issue and current PR. Require exactly one valid
   `step-N` on each, with equal N. For a **new** executable Change Request,
   put N+1 in structured `change_request.step` and its launch thread title.
   Preserve reviewed-head, findings, profile, validation and boundary authority.
2. Publish through the reserved Reviewer tool. A failed/uncertain publication
   needs its existing publication-repair procedure. Do not change Step on that
   basis or author another CR to repair transport. `APPROVE` changes no Step.
   Immediately before a new native CR publication, Reviewer verifies its Step
   is the current PR label plus one using its existing PR read. Its existing
   duplicate/republication path preserves the already-published CR's Step.
3. After successful native publication, use the ordinary owner-authenticated
   GitHub connection to re-read that exact review, the current decisive review,
   head and linked Issue. Ensure repository label `step-(N+1)` exists; replace
   the one Step label on Issue and PR, preserving unrelated labels. Update the
   PR's existing bounded `Task <Issue> · Step <N+1> · <CR purpose>` title so it
   is available in the next label event payload. Re-read both targets and head.
4. A partial failure leaves visible inconsistent metadata and blocks new launch.
   Resume synchronization of the **same native review ID** and its already
   authored Step; do not increment again. Only N or N+1 is eligible for this
   transport repair. Missing/malformed/multiple labels or changed review/head
   need owner reconciliation, not guesses. Apply a ready label only after sync.

[`step-synchronization.mjs`](src/step-synchronization.mjs) implements these reads
and metadata writes for an ordinary authenticated owner client. It has no
Reviewer publication, launch, merge, deployment or Issue-close capability. It
verifies `/user` is the configured owner (`User`), rejecting Writer/Reviewer App identities.
ChatGPT may perform the same native operations directly. An optional Linux
adapter reads a bounded JSON request on stdin with `operation: "prepare"` and
`pullRequest`, or `operation: "synchronize"`, `pullRequest` and the published
`reviewId`; it uses the caller's ordinary owner `GITHUB_TOKEN`:

```sh
node contracts/src/step-synchronization.mjs < metadata-request.json
```

This is a metadata helper, not a new workflow, Step registry or execution
transport. GitHub has no transaction across an Issue and PR; the final read and
fail-closed launch checks expose partial updates. Serialize owner metadata
changes; do not concurrently replace labels from multiple owner clients.

Remediation follows [progress-bounded execution](../docs/execution-policy.md)
inside the admitted worker. Contract counts and Step metadata bind authority;
they do not limit local correction iterations or authorize automatic retries.
