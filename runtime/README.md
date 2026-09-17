# Governed Codex runtime and Issue authority

[The controller](../controller/README.md) owns ordinary Issue/remediation
orchestration. This component provides the governed Codex runtime, semantic
result schema, Issue parser and a small adapter for isolated runtime probes.
Run `npm test` here for the runtime contract tests.

The runtime uses the deployment-owned [consumer contract](../consumer/README.md)
for effective authoring defaults, commit identities, runtime user and paths.
The worker receives the exact resolved model/effort from immutable admission.
Every governed invocation receives the shared
[progress-bounded policy](../docs/execution-policy.md); it can make evidence-based
corrections within the admitted goal without a fixed correction count. This
never authorizes a duplicate execution or broadens publication/credential scope.
