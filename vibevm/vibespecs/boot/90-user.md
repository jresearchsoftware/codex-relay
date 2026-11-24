# Local routing conventions

Apply human-owned root AGENTS once. It explicitly adopts all eleven complete
Shared Governance 12.5.0 protocols, each under its own conditional trigger.
The immutable package boot pointer supplies full protocol routes; product
mechanisms and supported exceptions are in docs/relay-guidance-ownership.md.
Read the canonical Relay Skill for relevant product workflows, architecture or
component contracts only when their surfaces matter. Ordinary startup reads
committed ready files offline; no resolver, cache or owner command is required.
Candidate generation does not replace the independently frozen accepted
source binding. Native Task/CR, Writer/Reviewer and protected operations remain
Relay-owned. See docs/vibevm.md for deliberate routing maintenance.
Small Improvements is adopted for standing bounded inclusion at the first
suitable source-changing opportunity. Analysis-only work skips the scan. Load
GitHub repository governance when relevant settings decisions arise, and Human
Command Interaction when assigning human shell or administrative work. Use the
complete Shared topics and their bindings in docs/relay-guidance-ownership.md.
Repository policy and native
consumer routing are distinct from the standalone Skill's frozen Shared snapshot;
that snapshot is not a missing-slot fallback. The ownership mapping also binds
the current closure semantics and the bounded fallback for qualified legacy combinations.

Root AGENTS explicitly adopts the installed landscape-subagents 1.1.0 flow for
permitted useful delegation in Relay development. Follow its conditional boot
before substantial work with Subagents On and Task/runtime permission; installation
alone grants no delegation. The landscape-model-guidance 1.1.0 boot routes only
model/effort recommendation and evidence work. Recommendations do not change
Relay defaults, allowlists or admitted parent/child profiles. Local bindings and
version/rollback semantics are in docs/codex/SUBAGENTS.md and docs/vibevm.md.

## Preserve the product boundaries

- Edit Relay-managed workflow behavior in `deploy/workflows/*.yml.in`, never
  the installed `.github/workflows/` projection as product source. Use the
  [public projection interface](../../../deploy/README.md#workflow-projection-and-pinned-runtime)
  from an exact accepted product revision; generated consumer changes retain
  ordinary owner review/merge authority. Product CI remains consumer-owned.
- Keep consumer policy, model defaults, credentials, runner configuration and
  operations in consumer-owned configuration. Use synthetic examples here.
- Resolve model, reasoning effort and Subagents once at admission. Omitted
  effort/Subagents fields use the defaults in [root AGENTS](../../../AGENTS.md) unless explicitly
  overridden by the live Task/CR; they need not be repeated in each admission
  or handoff. These are the execution-profile fields for launch cards, task
  metadata and handoffs;
  an effort identifier does not imply an additional capability switch. Do not
  silently substitute profiles or consult a moving external recommendation
  during execution. Record actual model/effort only when runtime evidence
  exposes them, otherwise `UNAVAILABLE`; requested values are not actual-value
  proof. Record whether subagents were used within the admitted permission.
- Keep owner, worker, Writer and Reviewer responsibilities separate. Review
  acceptance is independent and bound to the exact candidate head.
  Interactive ChatGPT review model/effort is not governance metadata: do not
  require or record it in CRs, handoffs, publication or Outcomes.
- Preserve reservation-before-mutation, replay suppression, non-force Git
  publication, safe paths/modes and scanning of every introduced blob.
- Never run trusted Git against model-modified metadata. Import bounded object
  bytes into a fresh trusted repository and validate them.
- Source changes and local tests do not authorize deployment, credentials,
  service changes, merge, Issue closure or release. Do not claim those proofs.
  Operational control inside an explicitly isolated disposable TEST sandbox is
  separately granted by the standing
  [TEST Environment Authority](../../../docs/execution-policy.md#test-environment-authority).
- For product and ordinary consumer lifecycle operations, follow the
  [first-install/bootstrap and deployment contracts](../../../deploy/README.md)
  just in time for install, upgrade, reinstall or activation work. Reuse only
  validated supported protected state; product-owned bootstrap must remain
  reachable through the public interface, and true external prerequisites stay
  owner-provided. A private-backend-only requirement is a source/interface
  defect, not authority to bypass the public path. Keep clean-environment
  qualification separately admitted when it needs distinct infrastructure;
  successful work on an already prepared host does not prove standalone
  bootstrap or retroactively gate an unrelated task. Disposable TEST cleanup
  and rebuilding follow TEST Environment Authority; public lifecycle interfaces
  and production recovery procedures are optional inside that sandbox.
- Prefer existing GitHub/Git records over a new ledger, registry or workflow
  engine. Add machinery only for a demonstrated product requirement.

## Validate and hand off

For newly admitted schema-v4 manual work, submit structured results through the
bounded owner-connected `submit_manual_outcome` MCP capability to protected
Writer. Writer publishes one canonical Outcome; a public owner result-copy
comment is unnecessary. Retained schema-v3 attempts keep their supported
publication/recovery path. No-PR qualification uses independent Task Approval;
source PRs require independent native exact-head review. Keep material findings,
warnings, evidence gaps and limitations visibly readable before one folded
canonical machine block. Preserve full handoff prompt bytes and historical body
hashes; rendering changes grant no execution or publication authority.

If a required connected App/Reviewer/Writer tool is missing or exposes an
outdated input schema, stop the affected native operation and identify the
capability and qualified installation needed. An authorized standalone/manual
route follows the Task workflow guide; it cannot fabricate native admission or
replace an admitted attempt's publication/recovery. Never substitute legacy/v3
publication or routing for new v4 work. The caller checks its available tools; the server cannot observe a stale
client cache or an inaccessible connected App. See the
[capability contract](../../../reviewer/README.md#current-protocol-capabilities).

Use Linux for the runtime and filesystem boundary tests. Run affected suites
during corrections and the complete candidate checks before handoff:

```sh
git diff --check
npm test
python3 -m pytest -q deploy/tests deploy/ansible/tests
cargo fmt --manifest-path reviewer/Cargo.toml --check
cargo test --manifest-path reviewer/Cargo.toml --locked
python3 scripts/qualify.py
python3 scripts/check-candidate.py
```

The candidate check scans tracked files; stage intended additions before using
it. Do not stage unrelated work. Local contract tests do
not qualify consumer sudo wrappers, process isolation, credentials, ingress or
a production service.
Native checks and independent review remain separate evidence.

Describe the problem and final behavior in the PR. Report the exact final head,
material validation evidence and limitations in one top-level Codex Outcome on
the canonical authority. Link required native checks instead of restating their
reconstructible status; do not add an Outcome update solely to announce CI PASS.
Distinguish implementation complete from independent acceptance. Do not post a
Reviewer verdict for your own work.

Material execution warnings remain mandatory decision inputs at the next owner
or independent review boundary, including when the durable handoff is green.
Inspect and disposition them under
[execution warning disposition](../../../docs/execution-policy.md#execution-warning-disposition).
A successful orchestration status does not resolve a warning. If a required
primary warning or annotation surface cannot be inspected, state the evidence
gap and do not claim that no warnings were observed.

Future task files include `## Recommended model budget` with recommended model,
effort, rationale and escalation/de-escalation conditions. The task author
resolves the model explicitly or delegates it to the admitted consumer
configuration, using the ordinary project profile above unless overridden.
Omitted effort/Subagents fields inherit the defaults in [root AGENTS](../../../AGENTS.md); an explicit
live Task/CR may override either.
An interactive prompt cannot change the user's UI model/effort selection.
Keep task-specific authority and execution evidence in the live Issue/PR,
not a duplicate registry.
