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

For another consumer on the same host, opt in to isolated service identities:

```json
"instance": {"reviewerPort": 18787, "publicationEnabled": false}
```

Place this object under `environment`. The port above is synthetic: select an
unused unprivileged port from owner-controlled host/ingress configuration.
Relay derives the Reviewer, recovery service/timer, production runner, general
runner and retired Controller/proxy unit names from `environment.namespace`,
using the suffixes `-reviewer`, `-reviewer-recovery`, `-runner`, `-general-runner`,
`-controller` and `-openai-mtls-proxy`. Configuration, state, credentials and
runtime paths stay in that namespace. All consumer paths must be under its
`/opt`, `/etc` or `/var/lib`
roots. Supply distinct Unix users, groups, runner identities and ingress for
each consumer; do not reuse an existing consumer's namespace or credentials
directory. Preflight rejects existing units bound to another installation or
an installed Reviewer configuration bound to another repository.

Omitting `instance` preserves legacy unit identities, port 8787 and publication
configuration. Never opt an existing consumer into namespaced units as an
implicit migration: it needs a separate owner-controlled lifecycle plan.
For a new consumer, keep `publicationEnabled: false` through credential,
configuration, identity and ingress qualification. This sets
`REVIEWER_RELAY_ENABLED=false`; the valid runtime config still admits read-only
target checks. Enabling publication is a separate owner-authorized config
change after qualification. Service activation still requires the existing
explicit activation gate. Ordinary apply does not register or activate runners.
This setting does not authorize a native verdict or manage shared ingress/TLS.

### First-install bootstrap and reusable state

Treat missing install-time state according to ownership before asking the owner
for another path or artifact. A fresh environment is expected to lack many
runtime-generated files.

1. **Reusable protected state.** If a supported existing artifact is present,
   validate and reuse it instead of regenerating it merely because the consumer
   is new. For TLS this means a certificate/key pair that matches the configured
   hostname, is currently valid, has an acceptable chain, matches its private
   key, and satisfies the required ownership/modes. A retained Let's Encrypt
   lineage from an earlier installation is valid input when it passes those
   checks; it is not required to exist.
2. **Product-managed bootstrap.** If no qualifying TLS pair exists and the live
   deployment authority permits TLS provisioning, use the supported protected
   Let's Encrypt/ACME path for the configured hostname. The OpenAI client CA
   bundle is also product-managed bootstrap state: prepare it from the pinned
   official OpenAI CA sources and fingerprints rather than searching unrelated
   protected paths for a pre-existing copy.
3. **External owner prerequisites.** Ask the owner only for state Relay does not
   own or cannot create: target/SSH identity, DNS, ACME contact identity when
   issuance is needed, GitHub App creation/installation and private-key input,
   the selected ingress topology or externally managed terminator, and later
   ChatGPT connector creation/connection.

Never guess or scan arbitrary protected paths for credentials, keys or
certificates. Missing product-owned bootstrap state is not evidence that an
operator must already have provisioned it somewhere else.

A read-only check may report missing bootstrap state as pending. Materializing
certificates, trust or credentials remains a production mutation and still
requires live authority; this contract does not broaden Task/CR scope.

Current pre-release limitation: the source contains TLS preparation logic,
including official OpenAI CA preparation and explicit ACME phases, only in the
internal Ansible backend. The public `deploy/relay-deploy.py` interface does not
currently expose those phases. Because `deploy/ansible/` is not a consumer API,
do not solve that gap by instructing consumers to invoke private playbooks
directly. Treat it as a deployment-interface defect to be corrected under
appropriate source authority. Likewise, standalone HTTP-01 issuance requires
the admitted public listeners to be available; a cohosted ingress that cannot
safely yield that path needs a supported issuance integration or an explicitly
managed external certificate source, not an arbitrary-path search.

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
Retained bootstrap directories can also precede their intended owners and
groups. Check mode inspects those identities read-only and reports pending
directory reconciliation as a change until all exist. With materialized
identities, ordinary directory checks still detect permission drift; apply
always enforces the configured ownership and modes after creating accounts.
The later runner role checks the retained shared state parent's type, root
owner and mode even when its group is still only planned. That pending group
assignment counts as a change; apply still requires and enforces the real group.

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

A first apply that stopped before creating the installation/configuration roots
has a separate, narrow `bootstrap-only` recovery shape. Read-only `check` reports
its exact state hash and still exits blocked. It requires absent consumer
accounts, groups, units, listener, log root and sudoers rule; only the protected
empty staging directory, operation lock and exact local-apply drop-in may exist.
Every governed unit's persistent and runtime drop-in directory and systemd
`DropInPaths` are checked. Unknown contents block both inspection and disposition;
only the exact persistent production-runner `production-local-apply.conf` is
admitted. Protected empty drop-in directories may exist. Their presence and
metadata, the admitted file's metadata/content and systemd observations are
bound into the state hash, so changed evidence requires a fresh owner binding.
Unknown state is never discarded. After inspecting that evidence, an authorized
owner can invoke the new accepted source with:

```sh
python3 deploy/relay-deploy.py --config /path/to/owner-config.json \
  --phase stale-dispose --authorize-stale-disposition \
  --stale-phase apply --stale-head "$recorded_sha" \
  --stale-apply-shape bootstrap-only --stale-state-hash "$observed_hash"
```

Do not assert `--stale-completed-phase apply` for this unfinished installation.
The bootstrap transition rechecks the shape and exact hash under the existing
host lock, durably archives the old record, and only then retires it. It retains
all bootstrap files and does not create users, install helpers or touch services.
A fresh check/apply of the accepted source is a subsequent owner action. The
completed-release recovery contract and its required evidence remain unchanged.

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
