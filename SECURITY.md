# Security reporting

Codex Relay is pre-release; no released version or support SLA is promised.
The current source is the review target. Local contract qualification is not a
security audit or proof that a consumer installation is safe.

Do not post credentials, private source, exploitable operational details or raw
diagnostics in public Issues/PRs. Reproduce with synthetic repositories, keys,
tokens and local fixtures; do not test a live consumer without its owner's
authorization. For an affected installation, use the owner's already-established
confidential channel and include the exact Relay revision and sanitized impact.

The future public repository's confidential reporting channel has **not yet
been activated or verified**. Public-repository setup must enable and verify
GitHub private vulnerability reporting and bind its live “Report a vulnerability”
link here before claiming that channel is available. No security email address
is designated by this candidate. Until a verified private channel is available,
withhold sensitive details; a public question may request contact instructions
without disclosing the vulnerability.

Writer and Reviewer credentials, worker containment, trusted workflows and
privileged launchers are significant boundaries. See the
[integration reference](docs/integration-reference.md) for consumer obligations.
Publication scanning inspects every introduced blob for bounded GitHub-token
and private-key markers, including later-deleted blobs. Candidate scanning also
checks selected AWS/OpenAI-like markers in tracked tip files. Neither policy
detects all secrets, encoded values or private business knowledge; see the
[scan-policy limits](docs/integration-reference.md#secret-scanning-policy).
