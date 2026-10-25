# Git-managed installation and Apply

The ordinary public entrypoint is `deploy/relay-deploy.py --phase install`.
It selects the supported installation strategy from observed host state and
performs its internal phases under the existing deployment locks. Expert
`inventory`, `bootstrap`, `upgrade`, `reinstall`, `post-check`, credential,
registration and diagnostic primitives remain available through the
[deployment contract](../deploy/README.md).

From a clean, explicitly selected accepted product checkout:

```sh
python3 deploy/relay-deploy.py --phase install \
  --resolved-revision <exact-product-SHA> \
  --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer
```

Other consumers may retain their supported owner-file/checkout configuration.
This owner's private deployment repository is not a prerequisite for every Relay
installation. Required credentials and external access must already be supplied
within the operation's authority; the command does not acquire new privileges.

## Private owner lifecycle

For self-dogfood PROD, reviewed private Git is the sole source of desired
configuration. The selected configuration uses:

```json
"localApply": {
  "source": "git",
  "repository": "jresearchsoftware/codex-relay-deployment",
  "configPath": "prod/relay.json"
}
```

The private repository contains that nonsecret configuration and one generated
`manual-main-production-deploy.yml`, offering owner-triggered `apply`, `stop`
and `resume`. Neither product nor configuration merge deploys automatically.
`GITHUB_SHA` identifies the reviewed private configuration commit. Product source
is resolved independently from the configured public repository: omitted/main
selects its frozen accepted main; an exact SHA must be proven on that accepted
lineage. PR refs and arbitrary workflow source/revision inputs are excluded.
An exact development candidate is permitted only through the separately
provisioned protected isolated-TEST qualification binding, not a workflow input.

The workflow passes its ephemeral repository-scoped token through the fixed
sudo helper's standard input. Its native permissions are `contents: read` and
`actions: read`, needed to retrieve the private config and attest the actual
owner `workflow_dispatch` run. The privileged child receives no token in argv
or its environment. Public product acquisition is anonymous. There is no new
static private-config credential or access granted to candidate CI/workers.
The coordinator verifies private repository identity/visibility, main, workflow
path, run/head identity and original/triggering owner before using the bytes.
If the consumer repository is private, its configured Writer App supplies a
separate short-lived token scoped to that one repository with read permissions.
The protected key stays within the installation namespace; the token is revoked
after acquisition. The private configuration token is not reused for this read.

Both exact commits, the config blob/content hash and dispatch provenance are
frozen together. A code-only, config-only or combined change uses the same
Apply. `consumer.defaultProfile` and Reviewer target changes are ordinary Git
intent; old installed values are not retained merely because they differ.
Manual host config edits are overwritten by the next Apply. The protected
deployment snapshot and `gitConfigReceipt` in the artifact manifest attest the
result and support diagnosis/recovery; they never select desired values.
An unchanged exact Git pair with equivalent installed configuration takes the
read-only verification path. It retains the original installation attestation
and does not restart services merely because a new workflow run requested it.

The protected `deployment-source.json` is a fixed source locator and owner
binding. It is not another configuration store. Actual target identity,
protected paths, schema, credentials, runtime permissions and external access
still require validation. Routine desired changes have no installed-intent
equality precondition or separate config-reconciliation ceremony.
An isolated TEST qualification pin survives Apply verification, unchanged-pair
replay and resume only when the trusted frozen receipt proves that exact
candidate and configuration. Resume retains the original verified installation
receipt; Git configuration and workflow inputs cannot introduce a pin.

## Strategy, compatibility and recovery

The installer distinguishes absent state, same-product reconciliation,
compatible lifecycle upgrade and supported protected replacement. A known
unfinished fresh installation can continue only with the same proven frozen
pair and its retained pending marker. A failed lifecycle operation can continue
through the same ordinary command when the installed reader proves its original
UUID, the same frozen product target, authentic current consumer and empty
active/unknown inventory. The installer rechecks source, physical resources and
any matching backend record under the existing host and pool locks, then uses
the existing recovery engine with that UUID. It never silently retargets the
operation or clears a gate. Other uncertain or unsupported recovery
states stop with preserved evidence and one supported next action; a blocker
string or repeated invocation alone is not proof that replay is safe.

[Installation metadata](../deploy/installation-contract.json) declares a strict
deployment epoch and known capabilities, retained in installed manifests.
Pre-metadata revisions use one bounded legacy lifecycle boundary,
`e1f00e828242c794c013ce8f555578d03564a441`, with proven Git ancestry; there is no
table of every source/target SHA pair. Unknown metadata, unproven lineage and
unsupported transitions fail closed. Historical SERIAL v3 consumers remain
compatible when a target adds the recognized optional parallel v4 capability.
The target-aware interpreter validates that known shape; it does not ask an old
installed parser to understand future fields or ignore arbitrary extra keys.

Desired consumer changes transition the admission digest under the same
publication lock and lifecycle UUID after complete drain proof. Existing
envelopes, original source, native result receipts and recovery identities stay
unchanged. Migrated SERIAL installations retain their original compatibility
receipt and a hash-bound frozen target consumer snapshot; the live consumer
and current pool gate are checked separately. Completed older pool records
remain readable only with their exact terminal proof. New Writer mutations
must use the current digest. Known legacy runtime-directory hardening runs
before admission; it preserves the proven lock inode and rejects other shapes.

Fresh installation composes supported protected credential/TLS preparation,
installation, activation, runner readiness and final verification when their
inputs are available. App installation/permissions, runner-group repository and
exact workflow/ref ACLs, DNS/ingress authority and missing external credentials
remain real external handoffs. A successful source test or runner registration
does not prove those policies.

Failure output reports the exact target, proven prior revision, chosen strategy,
failing stage, known mutation/recovery state, retry disposition and retained log
path when available. Unknown mutation is reported as unknown. Recovery records
are not erased and admission is not reopened on unproven success.

## Repository integration output

Installation generates a complete repository-relative integration directory.
The result identifies its `directory`, managed `files` and compatibility status.
Git mode also returns a separate `deploymentDirectory` for the private
lifecycle workflow. Publish each directory's contents in its receiving
repository through that repository's normal change process. The completed host
installation needs no second installer run merely because publication followed
installation. The contract is the tree, not a fixed workflow count.

Existing managed bytes must match their recorded drift baseline. Compatible
older workflows can continue; stale-compatible output identifies an available
repository update. An incompatible workflow fails at execution with an explicit
outdated-integration diagnostic until the generated integration is published.
The installer does not silently rewrite or publish consumer-owned workflows.
Publication and external prerequisites remain separate from host installation.

## Reviewed PROD cutover

This source interface does not establish that PROD has adopted it. Until a
qualified owner cutover, the existing public owner lifecycle entrypoint remains
the installed operation surface. Do not delete that working entrypoint merely
because a replacement template exists.

Prepare/review the private config and replacement workflow, inspect the actual
runner registrations and selected repository/workflow-ref policies, qualify
the private entrypoint and installed helper binding, then retire the public
owner workflow and stale projections/policy entries through their authorized
reviewed paths. Do not leave two active privileged Apply entrypoints or an
unqualified replacement. Reuse a proven runner/helper topology; a file move,
runner label or successful YAML run does not qualify external ACL isolation.

Task #63 source work and disposable TEST proof authorize no live PROD Apply,
PROD/shared policy change, product merge, release or Issue closure. PROD Apply
requires the separately owner-triggered qualified private workflow and exact
pair readback. TEST stays isolated and disposable; it acquires no permanent
configuration repository, lifecycle workflow or final-state requirement.
