# Consumer configuration examples

The [example](../consumer/fixtures/example.json) and
[canary](../consumer/fixtures/canary.json) and
[inventory API](../consumer/fixtures/inventory.json) consumers use synthetic repositories,
owners, App IDs, email addresses and filesystem paths. They are contract inputs,
not real installations or credentials. Their differing branches, identities,
workflow names, models and state paths exercise consumer isolation with the
same product artifact. The inventory API declares Python/type/API validation IDs.
No example recommends a model or grants access.

Use the plain [Reviewer config](reviewer-mcp.json) and
[diagnostics config](diagnostics.json) alongside the example consumer first.
They are checked with actual validators. Reviewer artifact hashes are synthetic
shape-valid metadata, not proof of a running binary; replace them with
operator-recorded evidence. There is no `mutation` field: only exact
`REVIEWER_RELAY_ENABLED=true` enables publication. See the
[complete ABI and environment](../docs/integration-reference.md).

[consumer.json.j2](ansible/consumer.json.j2) and
[reviewer-mcp.json.j2](ansible/reviewer-mcp.json.j2) show rendering boundaries for
Ansible/Jinja consumers as secondary examples. Every variable is a consumer-owned input. The templates
are not complete Ansible roles or a deployment playbook. Supply root-owned
configuration, fixed wrappers, users, runner/workflow wiring, App credentials,
ingress and operation procedures in the consumer installation.

Start with the [consumer contract](../consumer/README.md), replace all fixture
identities/paths, pin a qualified revision and independently validate the
deployment. Never share state roots or credentials between consumers.
