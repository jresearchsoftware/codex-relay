# Reviewer MCP service

This is a deliberately minimal custom Streamable HTTP transport, using pinned `axum 0.7.9` rather than an MCP crate because the required wire protocol is small and version-sensitive. It implements the narrow request/response subset of the [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): JSON-RPC POST, JSON/SSE `Accept` negotiation, origin rejection, and no SSE GET session. It exposes `check_pr_review_target`, `submit_pr_review` and `read_pr_review_evidence`.

It reads the admitted bind, repository, base branch, check name and App settings
from `reviewer-mcp.json`. It publishes verdicts/findings authored by an external
ChatGPT review conversation; it does not perform the review itself. Current
ingress supports the OpenAI connector mTLS identity only. See the complete
[integration contract](../docs/integration-reference.md#reviewer-runtime-contract)
and [plain config](../examples/reviewer-mcp.json).

For credential-free local evaluation from the repository root, use:

```sh
python3 scripts/qualify.py
```

It generates temporary client certificates, config and SQLite state and exercises
the real binary with publication disabled, plus enabled mock-GitHub handlers.
An installed service is invoked as `reviewer-mcp-http --config /absolute/reviewer-mcp.json`
only after the consumer has supplied and qualified all required environment and
ingress. No public release artifact or supported installer exists yet.

Environment: `REVIEWER_MCP_CONFIG` (CLI alternative), `REVIEWER_CLIENT_CA_FILE`,
`GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY_FILE`,
`REVIEWER_RELAY_DB`, and `REVIEWER_RELAY_ENABLED`. Only exact `true` for the last
variable enables review/check publication; startup logs `publication_mode`.
The obsolete `mutation` config field is rejected, rather than implying an
enabled publisher is read-only. Disabled instances can still read GitHub targets
and initialize SQLite; they reject publication with `RELAY_DISABLED`.
App/installation credential IDs must agree with config. Keep durable DB/WAL state
private across restarts. `artifact.commit`/`artifact.sha256` are operator-recorded,
shape-validated metadata, not verification by the running binary. The consumer
owns TLS termination; the service also verifies the forwarded client certificate.
Do not bind this binary publicly.

The configuration's top-level `repository` is the sole repository authority for
the instance. All tool schemas constrain the caller's required repository to
that value, and all tools compare it exactly before contacting GitHub. There
is no repository default or separate CLI/environment override. Configuration
admission requires ASCII `owner/repository`: owner length 1–39 with letters,
digits and single internal hyphens; repository length 1–100 with letters,
digits and `._-`, excluding `.` and `..`. Values are not trimmed, decoded or
case-normalized. Missing, wrongly typed, malformed or different caller values
fail closed.

The admitted repository also reaches every installation-token request: its
repository name is the sole entry in GitHub's `repositories` restriction, and
the same `owner/repository` supplies subsequent GitHub API paths.

All GitHub REST requests use the shared stable `User-Agent: codex-relay-reviewer/0.1.0`.

`read_pr_review_evidence` accepts only `repository`, `pr_number` and
`expected_head_sha`. It works with publication disabled and makes no repository
mutation or model call. Its advertised output schema distinguishes `available`,
`absent`, `unavailable`, `permission_denied` and `truncated` for each source.
The reader verifies the PR binding before and after collection, returns native
check/suite/run identifiers and URLs, and projects exact-head Writer Outcomes
from the reviewed PR and canonical linked Issue, preserving the comment target
and native comment ID. An exact-head Writer Outcome's native
`Attempt: run-N` binds a relevant routing execution and its check-suite
annotations even when that workflow ran on the trusted base revision. Evidence
preserves the actual execution head separately from the reviewed candidate head.
Only allowlisted, bounded fields are returned;
raw logs, artifacts, annotation `raw_details` and protected diagnostics are
excluded. Text is bounded and known credential/protected-content markers are
redacted. Redaction is not proof that arbitrary private text is public.

Acquisition is limited to 256 KiB per response, 2 MiB aggregate transfer,
40 requests including authentication, three pages of 25 items per source,
250 annotations overall, five seconds per request and 30 seconds per read.
Every budget or source failure remains visible. No response URL, redirect,
caller-selected path or pagination cursor is followed.

Mandatory automated evidence covers warnings/annotations produced after actual
job, check or Relay/Reviewer runtime execution has begun and exposed through
supported GitHub/runtime APIs. The reader acquires supported
[check-run annotations](https://docs.github.com/en/rest/checks/runs#list-check-run-annotations),
exact-head check/run state, and bound Relay execution Outcome warning fields.
`required_surfaces_complete` reports completeness within that scope;
`warning_observation` is `observed`, `none_observed` or `unknown`.
A required in-scope source that is unavailable, permission-denied or truncated
prevents an absence claim. An empty successfully inspected source means absence
on that source; it does not establish absence on other sources.

GitHub service-level or pre-execution workflow annotations and platform policy
banners visible only in the UI are outside mandatory automated acquisition.
The `github_workflow_run_platform_annotations` source retains an explicit
`unavailable` limitation, native run links and `required_for_completeness=false`;
that excluded source alone does not make supported evidence incomplete or block
independent review. No rendered HTML scraping, browser cookies/session state or
public-repository fallback is used. API completeness or `none_observed` does not
prove that no UI-only warning exists. This exclusion can change only when GitHub
exposes a supported API suitable for public and private repositories. Evidence
completeness does not itself establish independent acceptance or warning disposition.

`submit_pr_review` has two action-specific inputs. `APPROVE` needs only the
target (`repository`, `pr_number`, `expected_head_sha`), action and a bounded
`review_body`; legacy non-executable `structured_findings` remain optional.
`REQUEST_CHANGES` requires a structured `change_request` instead of either
`review_body` or `structured_findings`. The tool exposes ordinary top-level
properties with required `repository`, `pr_number`, `expected_head_sha` and
string-enum `action`, without a root conditional schema. Rust enforces the
action-specific requirements and rejects mixed payloads before GitHub access;
the nested executable CR schema retains v2 and binds its validation enum to the
configured vocabulary. Optional `validationNames` must match Node consumer
policy; undeclared names fail closed. Supply semantic findings,
remediation profile, Step, validation names,
starting-state requirements, completion requirements, boundaries and outcome
tokens/descriptions. Owner-policy reconciliation and finding evidence are
optional; omitted effort/Subagents use the shared execution defaults described
in the [CR contract](../contracts/README.md). No interactive ChatGPT model/effort
is required or recorded as governance metadata.

Reviewer validates the input before contacting GitHub, then renders a canonical
human-readable CR plus the version `2.0` execution data inside the same native
review. It checks the live PR binding and exact head, and verifies the returned
CR body and native review state. For a new executable CR, synchronized Issue/PR
Step N supplies N+1. After native publication, the same Reviewer operation
ensures the Step label, replaces both targets' Step labels while preserving
unrelated labels, updates the bounded canonical Task/Issue/Step/CR-ID PR title and
re-reads the binding, labels and title before reporting success. Partial failures
resume the same native review ID and authored Step through existing publication
recovery; approval changes no Step. Ordinary owner post-CR synchronization is
retired. Owner new-phase choice remains separate from this bounded projection.
The configured human owner must author the canonical linked Issue. Deployment
projects that identity from the existing consumer `owner`; no new owner input is
needed. The existing operation binding retains the exact initial PR title, and
recovery accepts only that title or the canonical projection of the same CR.
A historical published SQLite record without the pre-publication Step anchor or
its exact initial-title field may continue only when labels and canonical title
are already fully synchronized. An existing anchor's authority hashes must
still match before the same operation can acquire the title field.
Otherwise `LEGACY_STEP_BINDING_REQUIRED` preserves the existing review for
[explicit bounded owner migration recovery](../contracts/README.md#legacy-publication-migration-recovery),
then replay of the original payload and native review ID. That exception grants
no new review, Step, execution or normal owner post-CR writer.
Duplicate keys, unknown fields, malformed identifiers, duplicate finding IDs/validation,
invalid tokens/Step, unsafe text and payload/rendering overflow fail closed.
Operation identity binds the rendered body and all findings; repeated calls
retain existing duplicate suppression and uncertain-publication recovery.

The minimum Reviewer installation permission set remains `metadata:read`,
`actions:read`, `issues:write`, `pull_requests:write` and `checks:write`:

| Permission | Supported purpose |
| --- | --- |
| `metadata:read` | Repository/installation identity and access qualification |
| `actions:read` | [List/get workflow runs](https://docs.github.com/en/rest/actions/workflow-runs), including run/check-suite/attempt binding for execution evidence in private repositories |
| `issues:write` | Deterministic post-CR Issue/PR Step-label synchronization; read access also supplies linked Issue authority and Outcome comments |
| `pull_requests:write` | Native review publication and bounded PR-title synchronization; read access supplies PR/head and decisive-review binding |
| `checks:write` | Reviewer check publication; read access supplies check suites/runs and annotations |

Excluding UI-only warnings does not remove the supported Actions run-binding
requirement. No Actions write or additional permission is needed. Repository
tokens are restricted to the configured repository; the evidence reader requests
a separate token with only read permissions for `metadata`, `pull_requests`,
`checks`, `actions` and `issues`. The host-local App qualification checks the exact
installation permission set and uses a metadata-only probe token; it does not
prove live evidence endpoint access. Live App permission reconciliation and
deployment require separate owner authorization; source implementation does not
grant those actions.
The native review body remains sole executable CR authority, linked to the
canonical Issue for Task identity. Native `1.0` read and `2.0` publication versions
remain unchanged.

See the [producer/consumer contract and fixtures](../contracts/README.md)
for the semantic example, compatibility boundary and local checks. Cargo tests
invoke the real Node admission consumer against an intercepted mock publication.
Source implementation and CI do not deploy the Reviewer or authorize a canary.

The Writer readiness contract is separate from Reviewer publication: the trusted Writer App must fetch live PR state immediately before `DRAFT -> READY_FOR_REVIEW` and return exact repository, Issue, PR, branch, base, expected/current head, open/unmerged/draft state, Writer actor, outcome, and timestamps. The Reviewer never performs this mutation.

GitHub App endpoints (`GET /app` and installation-token creation) use the short-lived App JWT. Repository endpoints use only the installation access token.

A consumer must expose only its trusted TLS terminator's exact `/mcp` location.
The consumer owns its reverse-proxy configuration. It must verify the OpenAI client certificate
chain, clear alternate caller-controlled client-certificate headers, overwrite
both `X-OpenAI-MTLS-Client-Cert` and `X-OpenAI-MTLS-Verified`, and forward to
the loopback Rust `/mcp` route. Rust requires exactly one verified marker and
one URL-encoded leaf certificate, then validates the exact SAN
`mtls.prod.connectors.openai.com` and client-auth EKU. Missing, duplicated,
malformed, spoofed, wrong-SAN, wrong-EKU, or oversized identity fails closed.
The Rust process accepts loopback or a deployment-validated private bridge
gateway (`private_gateway`, with `nexus_gateway` retained as a compatible mode
name). The network name is explicit configuration; public binds remain rejected.

The binary does not implement OAuth discovery, API-key authentication or
alternate public MCP routes. No secret or certificate material belongs in this
repository. The pinned client identity SAN above is a protocol boundary, not a
consumer hostname.
