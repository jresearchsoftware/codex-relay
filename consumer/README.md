# Relay consumer contract

One Relay artifact serves one explicitly configured consumer per process.
Set `RELAY_CONSUMER_CONFIG` to an absolute path to a deployment-owned JSON file
matching [the validator](consumer-config.mjs). There is no repository search or
implicit consumer fallback. [Example](fixtures/example.json) and
[isolated canary](fixtures/canary.json) are non-secret qualification inputs;
their paths and IDs do not authorize access to any deployed system.

| Consumer input | Used by |
| --- | --- |
| `repository`, `owner`, `baseBranch` | API paths, owner admission, PR binding, exact base observation and Git fetch/publication |
| `taskBranchPrefix` | Task branch admission and omitted-branch derivation |
| `writerApp`, `reviewerApp` | Separate App slugs, numeric App/installation IDs and expected bot actors |
| `writerIdentity`, `remediationIdentity` | Worker commit author/committer and trusted object validation |
| `routingWorkflow`, `recoveryWorkflow`, `validationWorkflow` | Exact native workflow identity checks and lookups |
| `defaultProfile` | Consumer-owned resolution of omitted authoring fields at admission |
| `paths`, `runtimeUser` | Installed helpers, state/credential locations and non-root worker identity |
| Optional `validationNames` | Up to 32 unique bounded consumer check IDs; declare the same list in Reviewer config |

The configuration is loaded once, validated and frozen. Its digest accompanies
every admitted attempt. A different or missing digest cannot resume publication,
including blocked-admission replay. Existing pre-configuration attempts must be
reconciled under their original reviewed release before cutover; do not invent
a digest or discard publication reservations. An admitted worker executes its
resolved explicit model/effort. Relay never reads a moving Model Landscape.

The privileged Writer receives its configuration path from the root-owned
`env -i` wrapper. It verifies root ownership and non-writable ancestors before
credential access. Request JSON cannot select configuration, executable paths,
credentials or repository. Keep configuration outside the worker checkout and
worker-writable directories. Never share credentials or state roots across
consumers. Installed wrappers and sudoers must bind the same reviewed paths.

Reviewer uses its deployment-owned `reviewer-mcp.json`: `repository`,
`baseBranch`, `reviewCheckName`, `writerActor`, and `githubApp` are required.
Its App and installation IDs must match its credential environment; the live
App ID/slug, returned review actor and returned check slug must match the
configuration. Bind settings, operator-recorded artifact metadata and the separate Reviewer
database remain deployment inputs. The [integration reference](../docs/integration-reference.md)
lists the complete runtime config, environment and publication-mode contract.
The configuration must stay fixed for the
lifetime of that instance and its retained publication state.

Product invariants remain fixed: same-repository heads/bases (fork execution is
unsupported), exact heads, separate owner/Writer/Reviewer authority, bounded
payloads, secret redaction, safe Git paths and regular-file modes, non-force
publication and reservation-based duplicate suppression. `step-N`,
`codex-ready-auto`, `codex-ready-manual`, the historical CR validation tokens and
terminal status values are protocol vocabulary. The historical
`jresearchsoftware-reviewer-relay:v1` comment marker is a retained wire namespace
for duplicate recovery; it grants no organization or App authority. The local
`refs/remotes/main` import ref is a private alias for the configured base SHA.

Consumer workflows own runner labels/groups, event wiring, effective model
policy and deployment decisions. Relay owns the deployment implementation. The [rendering examples](../examples/README.md)
are synthetic inputs; the [deployment interface](../deploy/README.md) implements
installation and owner-authorized lifecycle operations.

## Qualification

Run `python3 scripts/qualify.py` from the repository root with Cargo,
Node and Python available, plus OpenSSL for temporary fixture certificates. It builds one
production Reviewer binary, starts it for all three configurations with full
certificate verification and publication disabled, and verifies bound tool
schemas and rejection of missing identity/cross-repository input. It also
builds one Reviewer test executable, runs the real
handlers against loopback mock GitHub for all three consumers, roundtrips the actual
published CR bytes into Node, and exercises routing/Writer Git publication and
replay with the same unchanged modules. It records hashes of both executables
and the candidate source before/after. The inventory API consumer uses its own
Python/type/API check IDs through Reviewer schema/rendering and Node admission.
This is local contract qualification;
it does not assert production deployment, paid model execution or native CI.

Run root `npm test`, Reviewer `cargo fmt --check` and `cargo test --locked`,
and the [candidate checks](../AGENTS.md). A consumer must separately qualify
its installed wrappers, process isolation, trusted workflows and ingress.
