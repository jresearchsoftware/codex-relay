# Relay deployment

Relay owns installation, build, release selection, permissions, services,
upgrade, rollback and verification. Consumers supply a versioned JSON input
and invoke `deploy/relay-deploy.py` from the selected Relay source. The
`ansible/` directory is an internal backend, not a consumer API. Consumers do
not copy or maintain its inventory, roles, tasks or handlers.

## Inputs and invocation

Start with [example.json](example.json). Its identities and host are synthetic.
The [validator and compiler](config.py) define configuration version 1:

| Input | Meaning |
| --- | --- |
| `source.repository`, optional `source.revision` | Trusted repository and deployment selector; omitted revision means `main` |
| `target` | Host, root SSH transport, existing key reference and known host/key fingerprints |
| `consumer` | The existing [runtime consumer configuration](../consumer/README.md), including separate Apps, repository, policy and credential file references |
| `environment` | Namespace, Unix identities, runner names/group/labels, existing ingress/network properties and consumer runtime options |
| `environment.compatibilityLinks` | Optional old invocation paths retained during a consumer's workflow migration |

Configuration contains literal data and secret **references**, never private
keys, tokens, templates, commands or backend variables. Unknown fields,
duplicate keys, unsafe paths and overlapping identities are rejected. The
runtime's existing validator remains authoritative for `consumer`.

A thin trusted bootstrap may fetch the requested `main`, commit or tag, resolve
`FETCH_HEAD^{commit}` once, check out that immutable commit, and invoke:

```sh
python3 deploy/relay-deploy.py --config /path/to/consumer/deploy/relay.json \
  --requested-revision main --resolved-revision "$resolved_sha" --phase apply
```

The product verifies its clean exact Git checkout and the consumer configuration
checkout. Every source export, build, manifest, operation and post-check uses
that one Relay SHA. Selection is not a consumer review/approval gate: accepted
channel governance belongs to the Relay repository. An advancing channel or
squash-merge SHA requires no consumer lock update.

Use a Linux controller with Git, Python 3, Node 22+, OpenSSH and Ansible Core
plus the dependencies in [ansible/requirements.txt](ansible/requirements.txt).
The target baseline is Debian 12. The controller uses the existing owner SSH
identity and strict host-key checking. The target needs no GitHub source
credential: Relay transfers a normal Git archive internally. There is no
consumer distribution bundle, installer hash lock or cached executable helper.

`--phase validate` validates local input without contacting the target.
`diagnose --issue-number N` reads bounded installed/runtime metadata without
loading installation roles. `check` plans reconciliation; a zero-change result
requires the stable-state proof. `apply` installs and verifies; `post-check`
verifies the selected installed identity and actual running Reviewer.

```text
requested_revision=main
resolved_revision=<Relay SHA>
consumer_revision=<consumer configuration SHA>
installed_revision=<same Relay SHA>
previous_revision=<previous Relay SHA, or none>
RELAY_INSTALL_RESULT=PASS
```

The installed manifest also records the Git tree, consumer revision, build
provenance and actual Reviewer binary hash. These are observations and build
reuse evidence, not a consumer security lock. Logs remain owner-local and
contain bounded non-secret configuration/runtime evidence.

## Lifecycle, upgrade and rollback

Normal apply reconciles installable state and preserves existing separately
authorized runner/Reviewer activation. It uses root-protected parents, durable
operation evidence and live-owner locks. Reviewer restart preserves an already
active dependent runner; the final gate hashes `/proc/MainPID/exe`, not merely
the new file on disk. Both runner instances must leave shared state parents
root-owned. Final identity/permission checks run after the entire composition,
before operation evidence is cleared.

Missing Reviewer groups are materialized by normal apply before artifact
ownership. Check mode reports planned-but-not-materialized state without
inventing accounts or hiding the Reviewer artifact ownership dependency.

Upgrade means acquire another selected revision and apply it. Rollback uses
the same operation with a previously qualified explicit SHA and its compatible
consumer configuration. Existing release trees and durable Writer/Reviewer
state are retained. There is no destructive release cleanup disguised as
rollback. Keep a clean known-good source checkout and configuration available;
pre-boundary installations can be restored with their original supported path.

`activate --authorize-reviewer-activation` and
`runner-enable --authorize-runner-enable` and
`general-runner-enable --authorize-general-runner-enable` are explicit owner transitions after
the existing credential/registration gates. No key is provisioned or rotated by
ordinary apply. Stale operation disposition remains evidence-bound through
`stale-dispose`; an apply disposition requires the observed completed phase and
exact state hash. Diagnose an interrupted operation before any retry. No blind
reset, force retry, registration or unrelated proxy/network management occurs.

The installed fixed local-apply helper retains the existing runner trust
boundary: one admitted consumer SHA, sanitized runner Git, root-owned staging,
fixed host namespace transition and no caller-selected executable or config
path. It reconciles that consumer input with the **explicit installed Relay
version**, reports that version, and defers live service changes until the
owner can act after the job. It does not claim to resolve remote `main`.
Source/channel upgrades use the owner bootstrap transport; this preserves
credential-free source access on private production hosts.

Existing ingress is described by consumer properties. Ordinary apply only
discovers and validates the configured Docker gateway when requested; it does
not take ownership of the foreign workload, certificates or container. Optional
backend TLS/proxy preparation code remains internal and outside ordinary apply.

Lifecycle readiness checks use `environment.ingress.service`. Both Reviewer
bind modes also apply to activation, runner enablement and stale-operation
recovery: `docker_gateway` requires the configured network/container and active
Docker service; `loopback` uses the local bind without gateway discovery or a
Docker-service prerequisite. The configured ingress must still be active.

## Qualification

Run product/runtime tests and the deployment suites from the repository root:

```sh
python3 -m pytest -q deploy/tests deploy/ansible/tests
node --import ./consumer/test-support/consumer-env.mjs --test deploy/ansible/tests/codex-launcher-*.test.mjs \
  deploy/ansible/tests/diagnostics-*.test.mjs deploy/ansible/tests/diagnostic-snapshot.test.mjs
sudo python3 deploy/ansible/tests/installed_runtime_proof.py
```

The installed proof uses private mount/PID/network namespaces, real Unix users,
sudo, actual templates and product source. Fake GitHub/Codex transport avoids
publication and model calls. Operation-recovery and loaded-process regressions
retain the prototype's useful lifecycle/security lessons. Old tests asserting
the removed private shell wrapper, consumer bundle lock and destructive
teardown are replaced by the product entrypoint/selector tests.

Local qualification does not prove a consumer's real Apps, mTLS or live host.
Those must be qualified separately on exact candidate identities before an
owner declares that deployment successful.
