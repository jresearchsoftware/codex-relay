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
and `resume`, plus the explicit bounded `recover` action described below.
Neither product nor configuration merge deploys automatically.
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
Its protected manifest's consumer revision records the receiving repository at
installation time. Read-only verification retains that historical revision under
the host and pool locks; a later receiving HEAD, including publication of the
generated integration, remains a separate compatibility observation and does
not require installation or rewriting the original receipt.

The protected `deployment-source.json` is a fixed source locator and owner
binding. It is not another configuration store. Actual target identity,
protected paths, schema, credentials, runtime permissions and external access
still require validation. Routine desired changes have no installed-intent
equality precondition or separate config-reconciliation ceremony.
An isolated TEST qualification pin survives Apply verification, unchanged-pair
replay and resume only when the trusted frozen receipt proves that exact
candidate and configuration. Resume retains the original verified installation
receipt; Git configuration and workflow inputs cannot introduce a pin.

## Preparation before cutover

For a Git-managed install, the existing host/pool locks cover a read-only
compatibility phase and real isolated candidate preparation before admission
quiesces. The installer validates the frozen source/configuration pair, old
resource and service bindings, Unix identities and destinations, retained
attempt history, configured credential material, App access and applicable
runner policy. A changed desired consumer requires terminal proof or a verified
historical Task disposition for every manual attempt whose consumer binding
would change. A code-only change keeps
its original consumer binding and does not invent that additional barrier.

On a proven fresh target with no current installation, the owning base-package
task first prepares its product prerequisites. It creates no Relay accounts,
helpers, configuration or service units. This preserves public first-install
bootstrap; missing product-managed compiler/Node packages do not become a new
owner credential or private-backend requirement. Actual candidate loader and
runtime qualification still follow; package presence does not prove Node 22.
An absent release pointer alone is insufficient: active orphan namespace
services or retained admission/publication/execution history require diagnosis
of the original installation. Provisioned credentials and empty state roots
remain valid fresh-install inputs. No protected history is removed to make the
target appear fresh.

The candidate source, pinned Reviewer build/toolchain, Runner and Codex packages
are prepared and sealed in a private operation directory. Preparation executes
the real build, package validators and loaders; it does not change `current`,
active configuration, installed helpers, service units, registrations or shared
toolchain/package prefixes. Protected replacement stages beside the old install
root so retiring that root cannot retire its candidate. No new public phase or
extra workflow approval is required.
The shared artifact role creates both stable public aliases,
`bin/relay-routing.mjs` and `bin/relay-publication-recovery.mjs`, for ordinary
and staged installations. The private seal requires every fixed runtime alias,
its contained target and public payload read/traversal bits. After consumption
and consumer publication, the controller imports both aliases with the actual
General Runner identity and a clean environment, without invoking admission or
recovery. A missing alias or unreadable import closure fails installation;
root-only source imports do not establish runner readability. This preserves
the private stage's `0700` parent and existing runner privileges.
Retrying the same operation preserves its prior private stage before creating a
new one; a live or unproven Writer holder prevents that preservation step.

A prerequisite or build failure reports a bounded cause and supported next
action while retaining the old entrypoint. Correct the prerequisite through
the existing version's supported owner procedure, then retry the same selected
Git inputs. Do not resolve missing terminal history by editing protected attempt
files, writing a fictional Outcome or clearing admission state. If the old
version cannot perform the required correction, the installer stops for a
separately qualified owner transition.

After the bounded drain, the installer revalidates the relevant host/policy,
frozen Git, old consumer and sealed payload evidence. Ordinary consumer
publication and active installation share the existing Writer kernel mutex;
the private lease is verified against that actual mutex, process and frozen
target. A new manual attempt during drain is rechecked before active writes.
If this final proof fails before active cutover, the original open admission
bytes can be restored only with proof that the old consumer, source, helpers,
units, services and protected inputs remain valid. Attempt and journal records
are retained, including the new attempt that caused the abort.

The initial SERIAL-to-pool transition keeps its separately authenticated old
history and existing retirement protocol. Protected replacement temporarily
releases the Writer lease for its owning retirement helper, then reacquires it
before candidate installation. Replacement that also changes the consumer
digest currently stops before retirement: its fresh-install consumer path
cannot safely rebind a retained gate. Use a compatible lifecycle transition
where supported, or a separately qualified replacement preserving that history.

Real activation, process identity, socket/mTLS readiness, runner readiness and
installed Git-pair verification remain post-installation checks. A failure
after the active mutation boundary retains the original operation and its
specific forward-recovery evidence. Preparation does not certify those future
results or provide a generic rollback of a partially installed system.

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

### Bounded recovery with a separately accepted controller

#### Continuing the consumer-publication frontier

If an already reserved bounded operation stopped after publishing the desired
release/consumer but before its admission digest and running Reviewer advanced,
use the same public `--phase install --authorize-install-recovery` command and
original operation/retained-target arguments with `--continue-install-recovery`.
`--resolved-revision` identifies the independently accepted corrected controller;
the protected reservation retains the exact desired product/configuration pair.
The new controller does not rewrite that pair or the prior controller identity.
Use the original frozen configuration bytes. This flag grants no PROD authority.

The supported frontier requires the desired release already installed, an
`applying` same-operation gate with the old or desired digest, an unchanged
`reserved` continuation and original backend, and authentic consumer-before and
desired staging files. Protected identity/credential/source evidence and native
Task/live-effect eligibility are revalidated. Changed evidence, an interrupted
archive, another operation or unrelated installation-template changes refuse
before further installation effects. This is not a generic partial-upgrade
engine.

The controller stages its corrected reader, completes only the missing consumer
digest transition under the Writer mutex, and continues the existing controller
role and installation tail. It skips completed prerequisite/runtime/artifact
installation and release switching. The standard final checks prove the actual
Reviewer executable, services and frozen Git pair before archiving the original
backend. The old Reviewer PID/start identity and original executable must still
be proven. An already advanced runtime, or equal original/desired executable
bytes without configuration-reload proof, receives a precise refusal before
effects rather than a duplicate restart or an assumed activation. Verified
same-operation admission and continuation
completion precede resume. Failures before verified resume keep admission closed;
an interruption afterward requires current readback, with evidence preserved.

Consumer-transition diagnostics contain bounded elapsed-time and native-reader,
original-reader and composite-inventory counters. Historical envelopes are
validated in bounded batches, with one composite snapshot and exact-record
native disposition reuse per locked action. A subsequent action performs fresh
Task reads; reopening, authority changes and pending/live effects remain blockers.
The controller observation ceiling is 180 seconds, matching preflight. Cancellation
kills its process group, including original-reader descendants. This ceiling
does not substitute for a short measured transition or establish recovery.

#### Starting bounded recovery

When a failed Git Apply has already installed its original product target but
retains the same closed admission UUID, a corrected accepted product may continue
that operation. A matching `apply / RECOVERY_REQUIRED` backend record may remain;
the lifecycle gate may also retain recovery after the backend already completed:

```sh
python3 deploy/relay-deploy.py --phase install \
  --resolved-revision <accepted-controller-and-final-product-SHA> \
  --config /path/to/accepted-config-checkout/prod/relay.json \
  --consumer-root /path/to/consumer \
  --authorize-install-recovery \
  --install-recovery-operation <original-UUID> \
  --install-recovery-target <original-product-target-SHA>
```

The flag explicitly selects continuation to the independently authenticated
final Git pair; it does not make a candidate accepted or authorize a PROD
operation. The retained target, controller revision and final product/config
pair remain distinct evidence fields. This bounded route requires the original
installed product to be the retained target and supports the known deployment
epoch/capabilities without changing physical consumers, credential bindings or
service intent. The controller and final product revision coincide in this
route. Other target combinations require their own supported classification;
they are not inferred from a flag or a moving branch.

Before any transition, the installer proves the protected original manifest,
Git-config receipt, configuration snapshot, current consumer, source graph,
credentials and exact backend/gate identity under the deployment locks. A missing
consumer-before backup is not itself a blocker when these original/current
contexts are authenticated. The corrected staged controller checks current
Task dispositions and all live/publication effects under the real Writer mutex.
It never replays Codex or invents native completion receipts.
Closed Tasks use their current native disposition directly. An abandoned open
route still needs the existing protected historical-disposition adapter's exact
acknowledgement of active trusted Decisions, revalidated against current authority
and local effects. An earlier in-memory diagnostic classification does not create
that persistent acknowledgement. This is the existing Step 4 interpretation
mechanism described below, not another owner Decision or terminal Outcome.

One protected operation-specific continuation receipt preserves the original
gate/backend bytes and binds the selected controller/final pair. The existing
same-UUID recovery target transition is explicit; the original backend record's
target and bytes remain unchanged. Backend validation consumes that exact
receipt, rather than treating two different source identities as equal. Reopened
Tasks, changed authority, source/config/credential drift, unknown live effects,
conflicting operations and incompatible transitions still fail closed.

For a gate-only retained operation, the same receipt proves and retains the
original backend's absence. It does not fabricate old record or archive bytes.
Before Apply, an unexpectedly appearing record refuses. The ordinary Ansible
Begin boundary may then create only its exact desired-target apply record under
the existing locks. Final installed verification removes that matching record
and records completion through the same receipt; the original gate UUID and
first snapshot remain unchanged throughout.

The ordinary staged installation, service-intent preservation and runtime checks
remain mandatory. Only successful installed-pair verification permits the backend
to archive its original record byte for byte and remove the active record name.
The installer independently reads back the final Git pair, verifies the same
admission operation and final continuation receipt, then resumes admission.
An interruption preserves closed admission and evidence. An exact reserved
continuation may be revalidated; partial receipt/archive completion requires
diagnosis and is not permission to repeat installation or reset a journal.

#### Already restored registered runners

An original inactive service snapshot remains immutable after the owner repairs
and restarts an existing registered Runner outside the failed operation. Current
activity alone is not new activation authority. For this diagnosed case the
bounded recovery command above additionally accepts
`--retained-runner-maintenance /path/to/owner-declaration.json`:

```json
{
  "operationId": "12345678-1234-1234-1234-123456789abc",
  "retainedTarget": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "runners": {
    "production": {"runnerId": 55, "runnerName": "example-production-runner"},
    "slot-pool-2": {"runnerId": 75, "runnerName": "example-general-runner-pool-2"}
  }
}
```

The owner explicitly attests the original IDs/names and completed maintenance;
do not generate this declaration from whatever services happen to be active.
The installer binds it to the existing operation-specific continuation receipt
and frozen final Git pair. It introduces no second journal and never changes
the original `previousActive`, backend bytes or historical attempts. The
declaration must cover exactly the newly active components. Only already loaded,
enabled Production or configured existing managed-pool runners are eligible;
new, foreign, unregistered, renamed or ambiguously active components refuse.

Before reconciliation and again before final acceptance, the controller proves
the original UUID, empty active/unknown work, exact service/Unix identity,
preserved managed-pool IDs, consistent effective native-update settings, a valid
local version, and matching online/idle GitHub registration/group eligibility.
Unavailable GitHub or Reviewer evidence refuses closed. Original transport
checks extend to the restored pool members and Production process.

This route preserves the live Reviewer and Runner processes. It is deliberately
limited to a correction whose staged Reviewer executable, configuration and unit
remain identical to the running installation. A required Reviewer restart,
configuration/unit change, lost listener, changed process or changed declaration
refuses instead of stopping repaired healthy runners. Ordinary upgrades retain
their existing restart behavior. Continue only through a separately authorized
owner operation with an independently accepted controller; this declaration does
not authorize PROD work, admission reset, re-registration or deployment retry.
The post-consumer-publication continuation flag does not accept a new maintenance
declaration; an interrupted maintained recovery needs diagnosis of its retained
receipt and actual runtime before selecting any further supported action.

This differs from expert `reinstall-recover`, which dispositions a separate
decommissioned clean-reinstall journal and does not install or activate its
controller revision. Neither interface permits raw protected-history edits.

#### Protected private recovery transport and older installed helpers

The generated private owner workflow's `recover` action transports the same
bounded operation through the existing fixed sudo helper and ephemeral workflow
token. It reads the explicit owner maintenance declaration from the fixed sibling
`<localApply.configPath>.runner-maintenance.json` in the **same reviewed private
configuration commit** as the desired config. For example, `prod/relay.json` uses
`prod/relay.json.runner-maintenance.json`, with exactly the declaration shape
above. The owner attests the original operation/retained target and exact repaired
IDs/names; neither workflow nor coordinator derives intent from current activity.
Publish the declaration and generated workflow through the private repository's
normal review/merge process. A file's presence does not affect ordinary Apply,
stop or resume and does not authorize a recovery dispatch.

`recover` authenticates the native owner dispatch and both Git sources before
staging the declaration as private temporary data. It invokes public `install`
with all four explicit recovery arguments, using the declared original UUID and
retained target and the independently frozen accepted final product/config pair.
The installer owns locks, protected preflight, immutable continuation evidence,
activation checks and verified admission reopening. The transport never resets
admission, synthesizes a backend record, stops healthy runners or replays work.
Missing/invalid Git attestation, changed identities or unavailable live proof
refuse rather than falling back to Apply or resume. `recover` reports the same
verified Git-pair completion only after the public installer succeeds.

An older installed helper cannot execute its own new grammar. After independent
source acceptance and separate owner authorization, the supported **local root**
bootstrap from a clean exact accepted product checkout is:

```sh
python3 deploy/relay-deploy.py --phase owner-lifecycle-bootstrap \
  --authorize-owner-lifecycle-bootstrap --connection local \
  --resolved-revision <accepted-public-main-SHA> \
  --config /path/to/owner-held/relay.json
```

This refreshes only the existing fixed helper under the installation's deployment
lock. It proves the protected current release/source locator, owner and Git source,
fetches a fresh anonymous exact accepted-main controller into root-protected
`/var/lib/<namespace>/owner-lifecycle-controllers/<SHA>`, and atomically publishes
and reads back the helper. The owner-held config supplies the existing locator
binding; it cannot replace private Git desired state. No token, new sudoers rule,
privilege grant, service mutation, release switch, admission change or history
edit is part of bootstrap. Ordinary commands keep using installed code; only
`git:recover` uses the accepted bootstrap controller and separately proves the
original installed release. Normal successful installation replaces the helper
with its ordinary installed-source implementation.

An unrecognized existing helper, unsafe code/path, changed source, busy lock or
interrupted unpublished controller refuses with retained evidence for diagnosis.
An already published identical controller/helper is verified and reused. This
command is not an unqualified direct-root deployment fallback: bootstrap and the
later genuine owner-triggered recovery each require their own existing protected
authority. Source/TEST success does not grant either PROD operation.

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

The digest-transition inventory includes manual history. Published pre-handoff
refusals and completed historical Writer results keep their original receipt
classification. A Task currently closed as `completed` or `not_planned` by its
verified configured owner can make an otherwise abandoned manual handoff
nonblocking. This records lifecycle eligibility, without asserting that the
original execution completed or never started. No Outcome, cancellation,
admission or journal is created or rewritten.

For an open Task, a protected owner adapter can acknowledge that particular
attempt's withdrawal or route switch from exact existing trusted Task Decisions.
The adapter interprets the explicit owner direction; the runtime does not infer
permission from prose keywords, a newer Step, changed profile or a missing
receipt. `createInstalledTaskDisposition({allowAcknowledgement:true})` supplies
the root-only expert adapter. Under the existing Writer kernel lock, the adapter
must verify the original record and absence of any matching runner journal,
then call `acknowledge(record, {reason, sources})` with exact active native
Decision references and recheck the journal. This optional internal operation
uses already authorized direction; it requires no new owner prompt, Task,
Decision or manual Start/Cancel ceremony. Workers and ordinary admission inputs
cannot enable it.

The small root-owned `historical-manual-dispositions-v1` cache beneath the
existing claim root binds repository, Task, run/attempt, original consumer and
record/envelope hashes to the exact native Task/Decision evidence. It is an
auditable observation, never desired configuration or execution authority.
Every preflight, final transition and later old-digest inventory rereads GitHub
through a repository-scoped Writer App token with metadata, Issues and PR read
permissions. Current Issue bytes,
native owner identity, complete closure/reopen events, trusted Task authority
and referenced PR authority must match. Reopening, changed authority, revoked
sources or changed local effects invalidates reuse. An unavailable/incomplete
native read fails with a specific `HISTORICAL_TASK_*` diagnostic; there is no
offline freshness exemption. Closed Tasks use durable native state directly.

A real worker journal, active/uncertain execution, pending publication or
recovery and conflicting ownership still block, even when the Task closes.
Original identities and supported publication/recovery paths remain intact.
`status` and preflight report `manualAttempts.historical` separately from
`manualAttempts.actionable`; missing native receipts remain visible without
reappearing as actionable blockers on unchanged-source upgrades. Ordinary
automatic counts retain their meaning. Code-only Apply with an unchanged
consumer digest preserves the old manual bindings without requiring a new
digest transition.

For same-consumer `status`, unavailable native Task authority is informational:
`manualAttempts.errors` identifies the affected run and
`HISTORICAL_TASK_AUTHORITY_UNAVAILABLE`; the attempt remains actionable and no
historical disposition is claimed. Required transitions and old-digest
eligibility still fail closed. Malformed evidence, unsafe cache and unreadable
journals are never downgraded. A code-only operation does not gain a new native
authority prerequisite merely from optional status diagnostics.

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

Git consumer publication failures retain their existing `error_code` and may
also include `controller_diagnostic`: a fixed action, failure category, exit
code and, when available, the controller's bounded error code. For example,
`consumer-transition-check` / `ADMISSION_NOT_DRAINED` identifies unresolved
history before consumer publication. Raw child output, arguments and private
paths are not included. An error after consumer replacement retains the
recovery-required classification and its original operation; its diagnostic
does not authorize a blind retry or reopening admission.

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
