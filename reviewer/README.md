# Reviewer MCP service

This is a deliberately minimal custom Streamable HTTP transport, using pinned `axum 0.7.9` rather than an MCP crate because the required wire protocol is small and version-sensitive. It implements the narrow request/response subset of the [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): JSON-RPC POST, JSON/SSE `Accept` negotiation, origin rejection, and no SSE GET session. It exposes exactly `check_pr_review_target` and `submit_pr_review`.

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
the instance. Both tool schemas constrain the caller's required repository to
that value, and both tools compare it exactly before contacting GitHub. There
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
optional; Subagents defaults Off. No interactive ChatGPT model/effort is needed.

Reviewer validates the input before contacting GitHub, then renders a canonical
human-readable CR plus the version `2.0` execution data inside the same native
review. It checks the live PR binding and exact head, and verifies the returned
CR body and native review state before reporting publication success. Duplicate
keys, unknown fields, malformed identifiers, duplicate finding IDs/validation,
invalid tokens/Step, unsafe text and payload/rendering overflow fail closed.
Operation identity binds the rendered body and all findings; repeated calls
retain existing duplicate suppression and uncertain-publication recovery.

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
