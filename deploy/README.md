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
| `environment.generalRunner.scope`, `environment.generalRunner.group` | Optional general-runner registration scope and its dedicated organization runner group; omitted scope preserves repository registration |
| `environment.localApply` | Either `{ "configPath": "deploy/relay.json" }` for a versioned consumer checkout, or `{ "source": "installed" }` for protected self-dogfood configuration |
| `environment.compatibilityLinks` | Optional old invocation paths retained during a consumer's workflow migration |
| `environment.ingress.publicAddresses` | Explicit public IPv4/IPv6 addresses for ACME; independent of SSH `target.host` |
| `environment.tls.source` | Optional protected existing certificate/key references, validated before reuse |
| `environment.tls.acme` | Optional contact and HTTP-01 webroot for the admitted shared Docker ingress |
| `environment.reviewerCredential.sourceKeyFile` | Optional existing owner-provisioned Reviewer App private-key reference |
| `environment.writerCredential.sourceKeyFile` | Optional existing owner-provisioned Writer App private-key reference |
| `environment.codexCredential.sourceTokenFile` | Optional existing owner-provisioned Codex access-token reference |

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

### Fresh-owner preparation

Create and install distinct Writer and Reviewer Apps for the selected consumer
with the permissions in the [integration reference](../docs/integration-reference.md).
Record only their IDs, identities and protected key-file references in one
owner-controlled `relay.json`. Configure strict SSH host/key identities,
public DNS/ingress and the chosen runner policy. Before registration, prove the
external runner-group workflow/ref restrictions described in the
[activation boundary](../docs/self-dogfood-workflows.md#activation-boundary).
Repository labels and a workflow's `if` expression cannot establish that policy.

Before installation, prepare the distinct App installations and repository
permissions listed in the integration reference, record the intended production
and general runner groups, and restrict scheduling outside candidate-controlled
YAML to the configured trusted workflows at `refs/heads/<baseBranch>`. Include
the supported production deployment workflow in the production group's policy.
Keep candidate validation on disposable runners. Place owner-provisioned App
keys and the Codex token at the protected references in the durable config;
registration tokens are supplied later only for missing runners. Configure the
public DNS address set and the owner-controlled ingress before TLS issuance.

`validate` reports invalid local schema/identity/path prerequisites. The
[inventory and bootstrap interface](#inventory-and-clean-install) reports
reusable target state, missing inputs, invalid state and owner-admin handoffs.
`check` reports installation plans; `tls-check` validates protected TLS/CA state.
Unavailable App/runner-policy verification is an explicit owner-admin handoff,
not a claim that policy is missing or that local validation proved it.

The supported sequence is:

```text
GitHub preparation -> durable config -> inventory -> required external inputs
-> bootstrap derives workflow artifacts -> consumer review/publication
-> bootstrap installs -> scoped credential/TLS bootstrap -> ingress
-> Reviewer activation -> runner registration/enablement -> qualification -> post-check
```

The first installation installs fixed bootstrap helpers. Each protected transition uses
the same public entrypoint and explicit authorization flags from the tables
below; separate capabilities need only their relevant credentials. Reuse the
durable nonsecret config, accepted source and proven existing state on subsequent
invocations. A private ignored wrapper may hold the config path and current
optional registration-token arguments for operator convenience. It is never
product configuration or execution authority. Ordinary logs and durable
configuration must not contain those tokens.

### Inventory and clean install

Reproduction starts with one accepted exact Relay source, one durable nonsecret
owner configuration and explicitly external protected prerequisites. An empty
target needs no installed runtime, workflow copies or projection manifest.
Acquire a clean consumer checkout for its ordinary review/publication process;
its commit is independent of the exact product source checkout.

```sh
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --resolved-revision "$target_sha" --phase inventory
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer --resolved-revision "$target_sha" \
  --phase bootstrap --authorize-bootstrap
```

`inventory` is read-only, including on pre-current installations. It reads only
configured/product-owned paths, compares durable intent with a protected
digest-bound snapshot when available, and identifies reusable local runner
registration. Protected credential/TLS results are metadata observations;
scoped credential, TLS and live App qualification still verify their contents
and remote identity. `ownerAdmin` lists the separate GitHub and ingress
verification handoffs. A successful observation grants no mutation authority.

`bootstrap` runs inventory and derives deterministic workflow artifacts from
the selected exact source and configuration. If the consumer does not yet
contain that projection, it writes a review directory under `--log-root`
(optionally selected with `--projection-output`) and returns
`RELAY_DEPLOYMENT_PENDING=WORKFLOW_REVIEW_REQUIRED` before host mutation.
Review/reconcile and publish those files through normal consumer authority,
then rerun the same command from the clean consumer checkout containing them.
The derived directory is an output, never an independent reproduction input.
Existing consumer-owned files are left intact; managed drift and edited
proposals fail closed. Local proposals do not constitute review or merge proof.

With the matching accepted consumer projection and explicit install authority,
bootstrap performs ordinary install and a separate clean post-check under the
same host deployment lock. Without `--authorize-bootstrap`, it reports the
remaining install authorization transition. It does not register runners or
activate services. Complete the credential/TLS, ingress and activation phases
below only to the extent admitted by the owner, then run the final `post-check`.
The result distinguishes installation from operational activation/qualification.

For an explicitly owner-authorized replacement of a pre-current installation,
use the same interface with `--phase reinstall --authorize-reinstall`. Inventory
must prove equivalent installed consumer identity and unambiguous local
registration and protected state. A valid protected snapshot compares complete
environment intent when available. Its absence is reported as an unavailable
comparison for owner review of the selected durable configuration; it is not
another required generated artifact. Invalid or different snapshots, unknown
runtime units and unsupported overrides block before mutation. The defensive scan also
classifies unknown top-level `/etc/systemd/system/*.service` symlinks: targets
must remain in protected `/etc/systemd/system`, `/usr/lib/systemd/system` or
`/lib/systemd/system` unit roots (including the proven `/lib -> usr/lib` alias).
Bounded unit-link chains and verified `/dev/null` masks are classified without
arbitrary traversal; dangling, unsafe or unclassifiable links report
`REINSTALL_UNKNOWN_UNIT_UNCLASSIFIABLE` and require inspection of top-level
systemd service links. Regular foreign units need not meet Relay's managed-unit
ownership/mode policy: otherwise safely readable current content is inspected
through protected parents with no-follow opens, a 1 MiB limit and metadata
rechecks. Namespace references in non-comment lines block retirement regardless
of the foreign file's owner or permissions. Mutable or differently owned foreign
files with unrelated inspected content continue with
`REINSTALL_FOREIGN_UNIT_WARNING`. The warning identifies the original unit and
inspected target, UID/GID, mode and other listed accounts that can write through
the group (including primary and supplementary membership), or unavailable group
lookup. An owner-only listed group is distinguished from listed other writers;
the current account listing is not proof against future or unlisted identities.
Review the unit's provenance and writers: content and group membership can change
after inspection. This warning does not authorize changing the foreign unit.
Uninspectable content, detected read-time mutation, unsafe parents/link chains,
non-regular targets and multiple hard links remain fail closed.
Known Relay-managed units still require their regular-file topology. The scan
does not inventory all vendor units or expand mutation authority.
The helper admits active idle runner services only after proving their exact
unit, Unix identity, MainPID ancestry, cgroup, executable and argument chain
(`run.sh -> run-helper.sh -> Runner.Listener run`). Missing or duplicate chain
roles and any extra cgroup member (regardless of UID, including child cgroups)
block admission. Each active runner cgroup must
contain exactly that three-process chain, revalidated under the production
operation lock before reservation. Real or ambiguous jobs,
Codex execution and unknown processes block before reservation or service
mutation; no manual stop/disable is required for proven idle listeners.
After reserving recovery evidence, decommission stops/disables
the proven managed services, retires activation markers and moves the managed
runtime into a protected recovery archive. The recovery timer is observed through
its explicit stable `ActiveState`/`SubState`; service-only PID properties may be
absent on a timer. A running/transitioning timer still blocks admission, and
the associated recovery service is checked independently. The timer is stopped
first and must then be `inactive/dead` or `failed/failed`. Every managed service
must have MainPID and ControlPID zero, and all runner/runtime identities must be process-free
after stop before the archive move. It retains complete intended runner
directories at their original paths, all `/etc` and `/var/lib` consumer state,
external credentials, TLS, and Writer/Reviewer durable evidence. Fresh apply
and clean post-check follow while the host lock remains held. The validated
same-invocation reinstall continuation restores the normal recovery timer during
fresh apply; an unfinished apply record still prevents its helper from starting
Reviewer or runners. Generic recovery without that journal binding stays
deferred. Its activation-relative deadline supplies a fresh first tick when
retained boot history and forgotten recovery-service timestamps leave no
deadline after reinstall; the existing unit-relative interval supplies later
ticks. Both clean and ordinary production post-check require the timer to be
active/enabled and waiting with a finite monotonic deadline, or running its
callback, through read-only inspection. An elapsed timer with no scheduled tick
fails this gate. Reactivation and live qualification remain explicit owner
transitions.

Retirement reserves the normal production operation plus a bounded reinstall
recovery journal before its first mutation. Unknown or failed transitions retain
both evidence and retired bytes; the command does not erase or blindly retry
them. Diagnose the reported stage before a separately authorized recovery.
After a clean install/post-check, the journal is retained with the retired
runtime as historical evidence. No consumer-specific workflow hash catalog or
legacy provenance exception is involved. The same path applies to each known
pre-current installation only after its own inventory and owner authorization;
one consumer's state is never evidence for another's reinstall.

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

The supported public deployment surface must be complete enough to express this
contract. A reusable protected artifact is only operationally reusable when the
public configuration can reference its validated source without inventing a
private-backend override. Product-owned bootstrap must be reachable through the
public deployment entrypoint rather than by asking consumers to invoke internal
Ansible playbooks.

Keep staged qualification least-privilege as well. A Reviewer-only or
publication-disabled qualification step must not require unrelated Writer keys,
Codex tokens, runner credentials or other secrets merely because one broad
interactive helper happens to provision them together. Ask for each external
credential only when the admitted stage actually needs it.

Do not conflate independent network identities. The SSH deployment target and
the public ingress/DNS address may differ; if both shapes are supported, the
public configuration and validation must represent the distinction explicitly
rather than silently treating an SSH hostname as an ACME IP address.

The public entrypoint provides the following separate owner transitions. Run
the ordinary `check` and authorized `apply` of the accepted exact revision
first, inspecting their plan; bootstrap mutations require that same installed
revision and refuse active/recovery operation evidence. The host operation lock
covers each mutation, including the entire ingress adapter run. Nothing here
implicitly activates Reviewer, registers runners or enables publication.

| Phase | Additional flag | Scope |
| --- | --- | --- |
| `tls-check` | None | Inspect TLS/CA presence and validate any existing pair; missing state is pending |
| `tls-prepare` | `--authorize-tls-prepare` | Prepare the OpenAI client CA from fixed official URLs and pinned fingerprints |
| `tls-dry-run` | `--authorize-tls-dry-run` | Prepare CA if absent and qualify the configured shared-ingress HTTP-01 path against ACME staging |
| `tls-issue` | `--authorize-tls-issue` | Reuse a valid pair, or issue after a matching successful dry run and publish protected managed files |
| `reviewer-credentials` | `--authorize-reviewer-credentials` | Stage only the configured Reviewer App key; identical existing key is a no-op |
| `writer-credentials` | `--authorize-writer-credentials` | Stage only the configured Writer App key as root-only material; identical existing key is a no-op |
| `codex-credentials` | `--authorize-codex-credentials` | Stage only the configured Codex access token for its isolated runtime identity; identical existing token is a no-op |
| `ingress` | `--authorize-ingress` | Validate and project TLS/CA, install the namespace's MCP fragment, test and reload the admitted shared ingress |

For example, inspect readiness through the same public interface:

```sh
python3 deploy/relay-deploy.py --config /path/to/consumer/deploy/relay.json --phase tls-check
```

`tls-check` uses temporary protected helper files, removed on completion; it
does not fetch CA material, issue certificates, change trust/credentials or
reload services. Mutating phases require live owner authority as well as their
matching CLI flag. A dry run is also a mutation: it can create an ACME staging
account and temporarily reload the challenge fragment. A flag is not approval
to run unaccepted source.

To reuse an existing certificate, add this under `environment`:

```json
"tls": {
  "source": {
    "certificateFile": "/etc/owner-tls/reviewer-fullchain.pem",
    "privateKeyFile": "/etc/owner-tls/reviewer-private-key.pem"
  }
}
```

Explicit sources must be regular root-owned files below protected parents,
with certificate mode 0600/0640/0644 and private-key mode 0600/0640. Symlinks,
untrusted chains, invalid dates, missing matching DNS SANs and mismatched keys
fail closed. The system CA store validates server trust; the OpenAI client CA
is a distinct mTLS trust input. Omitting `tls` preserves the legacy canonical
`/etc/letsencrypt/live/<serverName>` source: only its protected same-generation
Certbot archive links are admitted. Explicit `tls: {}` selects managed files
under `/etc/<namespace>/certs/` without authorizing issuance.

For new issuance, use `acme` instead of `source` and extend the existing ingress
object with the complete public DNS address set (all examples are synthetic):

```json
"tls": {
  "acme": {
    "email": "owner@example.invalid",
    "challenge": "webroot",
    "webroot": "/srv/shared/web-root"
  }
},
"reviewerCredential": {"sourceKeyFile": "/root/owner-input/reviewer-app.pem"}
```

Set `environment.ingress.publicAddresses` to an explicit array such as
`["198.51.100.20", "2001:db8::20"]`. It must match the observed DNS A/AAAA set.
`target.host` is solely the SSH endpoint and is never an ACME address fallback.
The supported issuance topology is the configured, pinned Docker nginx shared
ingress, with its existing configuration directory mounted at
`/etc/nginx/conf.d`, the explicit webroot mounted at `/var/www/html`, and public
ports 80/443. Relay does not stop ingress or create another public listener.
The webroot must be inside the declared ingress ownership root.

Bootstrap checks effective nginx routing, refuses conflicting or ambiguous
routes, installs only a temporary namespace-owned HTTP challenge fragment,
tests/reloads nginx and probes a fresh challenge through every admitted public
address before invoking Debian Certbot. Successful nginx validation may report
nonfatal warnings from existing cohosted virtual hosts; bootstrap does not
rewrite their configuration to silence those warnings. Nonzero validation
exits and conflicting server-name diagnostics still block, as do ambiguous
effective routes and failed public challenge probes. Certbot uses isolated account/state
directories, pinned Let's Encrypt endpoints and no directory hooks; ambiguous
inherited configuration is rejected. A global `/etc/letsencrypt/cli.ini` is
admitted only when its protected bytes exactly match the known Debian package
default; modified or unknown configuration blocks issuance because Certbot can
merge its options and hooks. Relay does not remove foreign configuration.
A successful dry run is bound to the
exact source head, hostname, contact, addresses, ingress and CA inputs. Live
issuance requires that binding. The temporary fragment is removed and ingress
revalidated on completion. Changed or unknown concurrent state is retained and
reported blocked for inspection, never blindly removed or retried.

An existing valid pair is reused. An existing invalid pair, foreign CA bundle
or different destination App key blocks instead of silently rotating it.
If managed TLS publication is interrupted after the private key is durable,
rerun the same authorized `tls-issue` operation. It completes the pair only
when the root-owned, single-link 0600 key exactly matches the fully validated
same-generation lineage in this namespace's Certbot state. Certificate-only,
foreign, mismatched or unsafe partial state remains blocked. The temporary
challenge fragment is retired and nginx revalidated before pair publication.
Reviewer credential staging accepts only an existing protected RSA App key,
verifies the installed Reviewer App/installation/file references, and creates
the root-owned Reviewer-readable destination with an atomic no-replace rename.
TLS component publication uses the same primitive: destination creation leaves
no second hardlink to retire. Retrying `reviewer-credentials` after interrupted
publication accepts identical protected material as a no-op; hardlinked or
different credentials remain blocked. Unsupported atomic no-replace publication
fails closed. Staging does not request Writer, Codex or runner secrets and does
not activate Reviewer.

Writer and Codex provisioning use their own explicit phases so that a later
activation stage preserves an already qualified Reviewer key. Add only the
needed protected source references under `environment`, for example:

```json
"writerCredential": {"sourceKeyFile": "/root/owner-input/writer-app.pem"},
"codexCredential": {"sourceTokenFile": "/root/owner-input/codex-access-token"}
```

These references name existing files on the deployment target; do not put
secret bytes in configuration or command arguments. Writer staging requires a
single-link root:root 0600 source with root-owned ancestors that are not writable
by other users. It validates this source before any destination mutation,
verifies the installed App identity, and writes a root:root 0600 key. This
Writer-only source restriction leaves Reviewer source admission unchanged.
Codex staging accepts one nonempty printable token line of at most 16 KiB, with optional
LF/CRLF, and writes only the namespace's fixed `codex-credentials/access-token`
with its configured runtime user/group and mode 0600. The Codex source is a
single-link root:root 0600 file; source ancestors are root-owned and not writable
by other users. The destination's existing runtime-owned 0700 parent is a
separate, explicitly validated boundary. Both phases preserve source bytes,
use the installed exact-head operation lock, refuse active/recovery operations,
publish without replacement, and leave different or unsafe existing material
untouched. Provision Codex authentication before admitting runners or workers;
the deployment operation lock does not serialize model execution. Neither phase
rotates a credential, registers a runner, starts a model call or activates a
service. Qualify the Writer's installed App identity and repository permissions
through the fixed `relay-writer-app-qualification` helper after staging. Do not
use the legacy all-credential interactive helper for a scoped provisioning step.

`environment.codexTokenRequired: false` permits unauthenticated installation
and staged Reviewer qualification only. The accepted launcher still requires
the fixed access-token file and recreates an isolated home for every worker;
the flag does not enable anonymous model calls or reuse an owner's interactive
login. Token presence and metadata checks do not prove remote authentication.

After separately authorized ingress and Reviewer activation, perform live
server-side qualification and a final ordinary `post-check` with no unexpected
drift. Local fixtures prove the implementation contract; live cohosted proof
and clean-environment standalone qualification remain separate evidence.

A thin trusted bootstrap may fetch the requested `main`, commit or tag, resolve
`FETCH_HEAD^{commit}` once and check out that immutable commit. A first
installation invokes:

```sh
python3 deploy/relay-deploy.py --config /path/to/consumer/deploy/relay.json \
  --requested-revision main --resolved-revision "$resolved_sha" \
  --phase bootstrap --authorize-bootstrap
```

This derives any missing workflow review proposal. After consumer review and
publication, the same invocation performs the installation.

The product verifies its clean exact Git checkout and the consumer configuration
checkout. Every source export, build, manifest, operation and post-check uses
that one Relay SHA. Selection is not a consumer review/approval gate: accepted
channel governance belongs to the Relay repository. Advancing a channel does
not change durable owner configuration or the installed version. An owner
upgrade explicitly updates the workflow projection and runtime together.

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

## Workflow projection and pinned runtime

Keep four revisions distinct: the accepted product source used for an install,
the exact installed Relay revision, the consumer repository commit carrying
Task/CR authority, and any newer accepted/released product revision. A newer
Relay commit does not invalidate a working installed revision. Normal routing
and recovery neither consult moving `main` nor compare the consumer workflow
SHA with the installed product SHA. No warning or degraded success is emitted
merely because an update exists. There is currently no authoritative latest
release lookup, so no update-available note is emitted.

Canonical product sources are [routing](workflows/routing.yml.in),
[publication recovery](workflows/recovery.yml.in), and the supported installed
self-dogfood [production reconciliation](workflows/production.yml.in). Consumer
configuration supplies repository/owner/ref, runner identities/groups/labels
and installation namespace. Candidate validation is specific to each consumer
and is not projected. The `.github/workflows/` copies are versioned installation
artifacts; product changes edit the templates. Self-dogfood uses this same rule.

From a clean checkout of one owner-selected **accepted exact product target**:

```sh
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer --resolved-revision "$target_sha" \
  --phase workflow-project --authorize-workflow-projection
```

This local operation writes the managed workflows and
`.github/relay-workflows.json`, which binds the source repository, consumer
repository, workflow contract and deterministic output digests. It does
not commit, push, merge, install or activate anything. The manifest is a drift
baseline, not acceptance authority. Review and publish the generated change
through the consumer's normal authority. No credential or registration token
belongs in either file. The owner configuration can remain outside Git when
`--consumer-root` supplies the separate clean consumer checkout.

Every existing managed byte must match the previous manifest before an update;
unmanaged collisions, direct edits, path changes, unsafe files and partial
projection stop for reconciliation instead of being overwritten. Interrupted
writes report changed paths; inspect the worktree before retrying. Bootstrap
derives a separate review proposal when the consumer has no managed manifest,
including when older consumer workflows occupy the intended paths. Resolve
those differences through the normal consumer review/publication process.

The product-owned [workflow contract](workflows/contract.json) versions only the
interface used by the three workflows: installed routing/recovery invocation,
environment/input meanings and the production helper argument. Change its
identity only for an interface compatibility change; ordinary implementation,
documentation, build or release revisions do not change it. Each workflow
resolves `current` once, verifies the exact release path against the installed
public source identity, and requires that release's workflow contract to match
before invoking code. The installed revision is still logged and bound to the
production helper; it is not embedded in consumer workflow bytes.

When content, workflow contract and consumer inputs are unchanged, a different
product SHA yields identical files and manifest, so bootstrap/reinstall requires
no consumer PR. Actual managed content or compatibility changes yield a bounded
proposal and stop for normal consumer review/merge. File digests remain solely
as the previous managed drift baseline. Schema-1 SHA-bound manifests are read
and drift-checked for a one-time schema-2 migration; they are not treated as
current projection. Existing SHA-bound consumers, including self-dogfood,
migrate through this same supported projection interface. Product template
changes do not publish that consumer diff or continue production operations.

After the projection is reviewed and merged, verify the clean consumer checkout:

```sh
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer --resolved-revision "$target_sha" \
  --phase workflow-verify
```

For self-dogfood, retain a separate clean product checkout at `$target_sha` and
a consumer checkout at the commit containing the reviewed projection. Those
SHAs normally differ; embedding the future projection commit's own SHA would
create an impossible circular binding. Publishing product templates alone does
not migrate an installed consumer. Existing legacy self-dogfood workflows stay
unchanged until this explicit owner transition.

### Subsequent-invocation failed reinstall recovery

After diagnosing a retained `DECOMMISSIONED` clean-reinstall journal and its
matching failed `apply` record, an explicitly authorized owner may use a clean
exact product checkout that implements this recovery interface:

```sh
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer --resolved-revision "$controller_sha" \
  --phase reinstall-recover --authorize-reinstall-recovery \
  --reinstall-recovery-target "$retained_target_sha"
```

The controller revision and retained operation target are separate identities.
This command never retargets the original journal or installs the controller
revision. Inside the protected boundary it derives the journal digest, verifies
the exact retained target, configuration, matching operation, retired source and
partially installed target, and requires contained admission and runtime state.
It stops only the configured recovery timer after proving all other managed
services and execution are stopped. Foreign units remain outside its mutation
scope. Unsupported stages, changed configuration, unsafe paths, mismatched
operation evidence, unknown admission, or incomplete containment fail closed.

Recovery archives both original records byte for byte in the existing retired
runtime archive. It leaves credentials, registrations, retired runtime bytes,
activation evidence and admission state intact; it does not activate services or
reopen admission. Its result includes the original service/activation intent
needed to assess a separately authorized installation and activation. A new
target requires a subsequent ordinary authorized `reinstall` from its own clean
committed source, with the reviewed compatible workflow projection. Historical
activation intent must be assessed before restoring previously active services;
an inactive or unregistered component is not implicitly activated.

A completed disposition cannot be replayed. Missing or partially archived
records require diagnosis; the command neither resets them nor guesses that an
interrupted operation completed. Source selection remains governed by the
canonical owner authority and is not granted by this recovery flag.

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

The ordinary owner surface for an installed self-consumer is the projected
**Owner Relay lifecycle** GitHub workflow. Choose `apply` to bind accepted
public Relay `main` once, reconcile an already installed exact target or upgrade
to that immutable target, and finish this sequence under the existing host mutex:

`OPEN -> QUIESCE -> DRAIN -> APPLY -> ACTIVATE/VERIFY -> RESUME -> OPEN`

The protected coordinator resolves the target anonymously and never follows
later movement of `main`. It verifies the frozen consumer dispatch's reviewed
projection against the exact selected source. Identical workflow bytes and
contract remain compatible across product revisions; a changed projection
requires ordinary consumer review/merge before apply and causes no automatic
publication. That consumer transition is authority, not a low-level deployment
command the owner must reproduce for each compatible update.

Source installation and retained-release reconciliation normalize the fixed
owner-lifecycle Python closure (`owner_lifecycle.py`, `lifecycle.py`, `config.py`,
`installed_config.py`, `deployment_lock.py`) to root:root `0644`, its `deploy`
parent to root:root `0755`. The existing directory tasks protect `reviewed-source`
and its release parents, retaining their assigned groups and modes. Other
archived source modes remain unchanged. The fixed bootstrap still rejects
writable, non-root-owned or aliased code and unsafe substitution parents before
executing root Python. This requires no additional owner action. An older
installed helper that already fails this bootstrap cannot apply its own repair;
install the accepted correction through a separately authorized supported public
deployment/reconciliation operation before qualifying the ordinary workflow.

Quiesce atomically closes the root-owned admission gate using the existing Writer
lock. Already admitted automatic controllers retain their reservation through
child containment, publication and terminal evidence; queued/new Tasks and CRs
cannot launch Codex. Drain releases that lock between observations, waits up to
30 minutes for valid work and rejects unknown execution or publication evidence.
No service or runner is stopped to drain. Registered runners remain online.

Managed apply snapshots actual service activity and uses the existing supported
upgrade backend. It consolidates try-restart of the previously active Reviewer
and production dependency, verifies the real executable and process adoption,
installed identity, service health, recovery timer, preserved activation intent,
and exact projected workflows before reopening admission. The general runner
is transport and retains its PID/start identity across planned Reviewer
transitions; its initial readiness check is preserved. Inactive/unregistered
components remain inactive. A general transport software, unit or group change
requiring restart fails closed for explicit recovery instead of killing the job.

The operation emits phase/count progress without model calls. An ordinary apply
runs one mutable primitive, with no mandatory pre-check or immediate equivalent
post-check. Its own final runtime proof is required. Bootstrap/reinstall retain
their independent clean-state post-check; an explicit `post-check` remains useful
for later installed qualification, diagnosis and recovery.

Choose `stop` for `OPEN -> QUIESCE -> DRAIN -> QUIESCED`, without disabling or
unregistering runners. Choose `resume` after that graceful stop to independently
revalidate the same installed accepted revision and current runtime/projection
with the public read-only post-check, then reopen admission. It does not repeat
mutable apply. Ordinary resume rejects retained uncertain apply/recovery state.
Root-only `relay-admission status` provides bounded state and pending/unknown
counts for diagnosis. Missing, malformed or untrusted state fails closed. The
same gate retains original activity/enablement intent across failed activation
and rollback; failed services cannot become an inferred intention to leave
them off.

The supported low-level upgrade primitive remains available for explicitly
selected accepted targets and recovery through the same lifecycle:

```sh
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer --resolved-revision "$target_sha" \
  --phase upgrade --authorize-upgrade
```

The primitive verifies the projection before contacting the target, establishes
quiesce/drain under the host apply lock and validates the protected existing
installation and owner configuration. Only source revision
selection may differ from the protected configuration snapshot. Credentials,
runner registration, service activation intent, TLS/mTLS, consumer identity and
Writer/Reviewer separation are preserved. Configuration changes are separate
owner reconciliation. Upgrade never supplies tokens, registers runners or
implicitly starts inactive components. Existing operation/recovery evidence blocks
an upgrade; diagnose it through the existing recovery interface. Failed or
ambiguous apply/activation/verification never becomes a successful upgrade receipt.

Ordinary owner apply verifies the workflow target and permits first installation
or reconciliation of the same installed revision. Changing the installed
revision requires `upgrade`. Moving Relay `main` does not trigger either action.
The old fixed local-apply reconciliation helper remains an implementation/recovery
interface with its existing ABI. It is not a competing ordinary workflow.

Rollback uses the same exact-target upgrade primitive with a previously
qualified compatible revision that supports this contract and its reviewed
projection. Existing release trees and durable Writer/Reviewer state are
retained; no destructive release cleanup is disguised as rollback. Pre-current
installations use the inventory and authorized clean-reinstall path above.
Without a protected deployment snapshot, inventory reports that complete prior
environment comparison is unavailable. The authorized clean-reinstall path
uses the selected durable owner config and independently checks installed
consumer/units/runner scope; it never manufactures a snapshot from guessed
state. Keep the prior supported recovery path and exact source available.

After diagnosing a failed operation and safely dispositioning any retained
production mutation record through its existing interface, an owner may use
`upgrade --authorize-upgrade --authorize-lifecycle-recovery
--lifecycle-recovery-operation <retained-UUID>` from the exact previously accepted
target source. This reuses the closed admission operation and existing upgrade
primitive, proves no active/unknown execution, and resumes only after the restored
revision passes the same-operation final proof. Failed or uncertain rollback
stays quiesced. No automatic rollback, record reset or blind retry is supplied.
If the originally active general transport has been lost, apply does not start
it: restore that transport through its existing protected owner boundary or a
separately admitted recovery before attempting this path. A generic rerun is
not evidence that transport or execution containment is known.
An installation lacking this admission primitive requires separately admitted
rollout/qualification before the normal lifecycle surface can be used; this
source implementation does not qualify a live installation.

`activate --authorize-reviewer-activation` and
`runner-enable --authorize-runner-enable` and
`general-runner-enable --authorize-general-runner-enable` are explicit owner transitions after
the existing credential/registration gates. No key is provisioned or rotated by
ordinary apply. Stale operation disposition remains evidence-bound through
`stale-dispose`; an apply disposition requires the observed completed phase and
exact state hash. Diagnose an interrupted operation before any retry. No blind
reset, force retry, registration or unrelated proxy/network management occurs.

The general runner defaults to repository registration. Consumers that need an
organization runner group's external workflow restrictions can explicitly select
organization registration with a dedicated group, for example:

```json
"generalRunner": {
  "name": "sample-relay-general-runner",
  "user": "sample-relay-general-runner",
  "scope": "organization",
  "group": "sample-relay-control"
}
```

The group must differ from the production runner's group. Repository scope does
not accept an organization group. Registration scope changes neither the general
runner's Unix identity, isolated filesystem namespaces nor fixed sudo boundary.
The owner must separately restrict the general group to the one consumer
repository and its exact trusted routing/recovery workflow refs, excluding
candidate validation. Production requires its own independently admitted
workflow/ref allowlist. Selecting a group does not create it or prove its ACL.
Apply does not register, migrate or re-register either runner; an existing
registration that disagrees with the selected scope remains blocked. Changing
an admitted consumer's scope requires explicit owner acceptance and external
qualification before registration or enablement.

### Ephemeral runner registration

Use the public registration phase after installing the exact accepted product:

```sh
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer --phase runner-register \
  --authorize-runner-register --runner-registration-token "$fresh_token"
python3 deploy/relay-deploy.py --config /path/to/owner/relay.json \
  --consumer-root /path/to/consumer --phase general-runner-register \
  --authorize-general-runner-register --general-runner-registration-token "$fresh_general_token"
```

Both token options are optional. The installer first validates and reuses an
already registered intended runner without consuming a token. Otherwise it
transports the one-run input through protected SSH stdin to the installed
helper; the token is never written to config, inventory, deployment state or
normal logs. Run these commands without shell tracing. A missing or recognized
expired/invalid required token reports `fresh registration token required`.
Replace the token and rerun the same authorized phase. Valid registration is
reused, so a token refresh does not duplicate runners. Existing partial or
mismatched registration and uncertain transport results require inspection
before any retry; they are not treated as permission to register again.
Before invoking the registration command, the helper reserves a root-owned,
token-free pending marker bound to the intended runner. An unknown command
result keeps that marker and blocks another registration attempt. A subsequent
matching complete local registration reconciles it without invoking registration
again; a proven pre-mutation authentication rejection permits a fresh token.
There is no automatic force/clear bypass for an unknown remote result.

Registration does not enable a service. Follow it with the separately authorized
`runner-enable` or `general-runner-enable` phase after validating external
scheduling restrictions. Reuse proves local intended registration metadata;
GitHub availability and runner-group ACLs remain independent live evidence.

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
Source/channel upgrades use the protected owner lifecycle and the existing public primitive; this preserves
credential-free source access on private production hosts.

### Protected self-dogfood reconciliation

A self-dogfood consumer may keep deployment configuration private and select
`"localApply": {"source": "installed"}`. This mode requires the consumer and
product source repositories to match and uses `main`. It is mutually exclusive
with `configPath`; existing checkout-based consumers keep their current contract.

Owner apply for every consumer stores the validated deployment input as
`<exact release>/deployment-config.json`, owned by `root:root` with mode `0600`.
The existing artifact manifest binds its SHA-256 digest and original consumer
revision. Configuration contains only references to credentials; the snapshot
does not contain credential bytes. Its content is suppressed in deployment logs
and diffs. The source repository and workflow never receive this configuration.
Changes to it still require owner deployment through the public interface.

The fixed `relay-production-local-apply <product-SHA>:<consumer-SHA>` command
then reconciles the installed product using that protected snapshot. The single
typed argument binds both the projected product and the native dispatch commit.
The helper validates the exact installed release against the product component
before executing its code; a concurrent release switch fails closed. The
original configuration's consumer revision remains provenance and is not
replaced by the workflow SHA. There is no runner checkout, caller-selected
config, target, executable, inventory, credential, or source-upgrade option.

Before reserving an apply operation, the installed code revalidates the exact
release, protected configuration digest and current GitHub `main` under the
existing production transition lock. A changed release/configuration, a stale
consumer dispatch (current `main` no longer matches that dispatch), invalid
metadata, active operation or
unavailable remote verification fails closed before install changes. Current
consumer `main` may differ from the installed product revision. The GitHub read
uses normal TLS validation without a host credential. This mode therefore requires a publicly readable
repository. The ordinary operation record and live-lifecycle preservation rules
still apply; a workflow does not activate or restart its own runner.

Public owner apply and installed reconciliation also hold the same host apply
mutex for the complete operation. This excludes a concurrent apply of the same
source SHA with different configuration; the durable recovery record alone does
not provide that exclusion. Losing the owner transport lock holder stops the
controller backend and retains ordinary recovery evidence; it does not prove
that every remote descendant has stopped. Installed-mode apply refuses a retained
operation by default. After diagnosing the interruption and establishing a safe
recovery boundary, the owner may explicitly use `--authorize-apply-recovery` with
public owner `apply` for the matching recorded apply/head. This flag is forbidden
for the fixed runner helper and local reconciliation. It is not automatic retry
or authority to discard an unknown operation. Legacy checkout-mode recovery is
unchanged.

Review the lifecycle projection and install/qualify its selected accepted product
before dispatching the new owner workflow. Routine compatible accepted updates
then use its single `apply` action; the protected coordinator invokes this same
public upgrade interface. The legacy installed helper remains bounded to
reconciliation. See the public consumer's
[workflow and activation contract](../docs/self-dogfood-workflows.md).

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

Use the [supported Node toolchain](../CONTRIBUTING.md#local-validation), Node
22 or newer. The installed-runtime proof rejects an unavailable or unsupported
active Node before downloading artifacts or entering its disposable namespaces.

Run product/runtime tests and the deployment suites from the repository root:

```sh
python3 -m pytest -q deploy/tests deploy/ansible/tests
python3 deploy/ansible/tests/qualify_codex_cli.py
node --import ./consumer/test-support/consumer-env.mjs --test deploy/ansible/tests/codex-launcher-*.test.mjs \
  deploy/ansible/tests/diagnostics-*.test.mjs deploy/ansible/tests/diagnostic-snapshot.test.mjs
sudo python3 deploy/ansible/tests/installed_runtime_proof.py
```

The governed standalone CLI is pinned to **0.160.0**. The credential-free
release qualifier downloads that exact official release into a temporary home
and exercises the real binary against a deterministic loopback Responses
service. It verifies JSONL events, native thread IDs and usage counters,
stdin task bytes, strict schema delivery and Relay semantic-result extraction,
non-zero provider failure, isolated homes, and effective workspace/network
policy. No model call, login or production installation occurs.

The probe also preserves native limitations: missing backend usage becomes
native zero counters; the CLI requests the output schema but Relay must still
validate the returned result; and Ultra resolves through the native model
catalog rather than necessarily reaching the provider as `ultra`. Subagents
On/Off remains the resolved task instruction; the existing launcher does not
toggle the native `multi_agent` feature. These observations do not establish
live model access, backend effort, subagent compliance or OS sandbox enforcement.
The installed proof below independently covers launcher environment, Git
identity, containment, diagnostics and cleanup under the real Unix boundary.

The installed proof uses private mount/PID/network namespaces, real Unix users,
sudo, actual templates and product source. Fake GitHub/Codex transport avoids
publication and model calls. Operation-recovery and loaded-process regressions
retain the prototype's useful lifecycle/security lessons. Old tests asserting
the removed private shell wrapper, consumer bundle lock and destructive
teardown are replaced by the product entrypoint/selector tests.

Local qualification does not prove a consumer's real Apps, mTLS or live host.
Those must be qualified separately on exact candidate identities before an
owner declares that deployment successful.

A standalone first-install readiness claim should eventually include a
clean-environment proof in addition to upgrade/cohosted-consumer evidence.
That qualification is independent work and does not block a cohosted deployment
task unless its live authority explicitly requires standalone-install proof.
Track the dedicated clean-environment qualification separately (currently
Task #15); incidental state retained from another consumer must not become a
documented prerequisite merely because that proof is deferred.
