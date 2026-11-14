# Task 57, Step 1: proportionality audit

Audit date: 2026-11-13. This is a bounded decision-preparation report, not a new
policy, control register, remediation authorization or independent acceptance.
Related to [Task 57](https://github.com/jresearchsoftware/codex-relay/issues/57).
The [Step 2 continuation](task-57-step-2.md) supplies primary run-log readback,
source clarifications and fresh validation; this report retains Step 1 provenance.
The Issue stays open. No runtime, validation, deployment or permission behavior
was changed by this Step.

## Decision summary

Retain preventive protection at the credential, privileged execution,
publication, exact-head, native authority and containment boundaries. The
strongest cost-reduction opportunity is repeated installation work, rather than
removing those protections. Start a separately authorized bounded implementation
with the demonstrably duplicate per-slot package reconciliation and useful
timing of the existing operation. Then use measured costs to select package
reuse and narrower reconciliation. Do not introduce a persistent skip cache or
another qualification action.

Ordinary upgrade already reuses its final runtime proof and does not mandate an
immediate equivalent post-check. Preserve Task 25's accepted lifecycle. The
reported Task 230 total of 3,054 seconds does not establish that all of its
separate qualification was redundant. A newer natural Apply sample exposes a
566-second APPLY interval and 116-second preparation interval, but neither
available public record contains the protected backend task timings needed to
attribute those intervals. That causal profiling obligation remains unproven;
the report supplies an executable first correction and an exact evidence request,
not a claimed diagnosis or demonstrated deployment speedup.

## State, authority and audit method

- Audited source: `5df7e0093d93c5a55b996e34cc83359da6b22a3e`, clean initial
  `codex/task-57` checkout. Report-only commits descend from that source; their
  hashes do not change the runtime state being assessed.
- The supplied admitted Task 57 / Step 1 identity and automatic route govern
  this execution. Historical run `43488568194` was not replayed. No Step was
  inferred from labels/history and no UI rename was needed for this automatic
  launch. Supplied launch title: `Task 57 — Step 1 — Audit proportionality of Relay security and validation controls`.
- Anonymous GitHub REST reads confirmed the live charter SHA-256
  `ace0ebbfe3da78befebfca3e1fde240096b3f9735f9d266afbfc3cdc96827911` and the
  single active Decision
  [6862381328](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6862381328).
  Its complete published body SHA-256 was
  `c0d0fd1febf0e2c46804e256370424a93b7b813da723774c7bfb3ddc1692695f`.
  The comments collection completed in one page. Discussion supplied evidence,
  not additional permission. No GitHub credential or connected GitHub identity
  was used.
- Criteria: complete adopted Shared Governance 7.0.1 proportional-controls,
  requirement-authority, context-loading, task-handoff, independent-review,
  contract/decision-maintenance and relevant repository-governance protocols;
  [Relay execution policy](../execution-policy.md), [architecture](../architecture.md),
  [deployment](../../deploy/README.md), [installation](../git-managed-installation.md),
  [controller/Writer](../../controller/README.md), [runtime](../../runtime/README.md),
  [Reviewer](../../reviewer/README.md), [authority](../../contracts/README.md),
  [consumer](../../consumer/README.md) and [integration](../integration-reference.md)
  contracts, checked against active consumers below. Broad inventory preceded
  challenge-case reconciliation. Historical requirements were not promoted into
  current policy merely because a test or old report retained them.
- Two blind read-only audit contexts, A (`/root/audit_a`) and B
  (`/root/audit_b`), received the same revision, policy questions, scope and
  prohibitions, without each other's conclusions or the parent's emerging
  findings. Each was explicitly assigned the full control-family inventory and
  eight challenge cases, concrete harm/cost/alternatives, source references,
  dispositions and uncertainty. A separate specialist (`/root/latency_trace`)
  traced deployment paths. All requested `gpt-6.1-sol / xhigh`; actual parent
  and child model/effort telemetry: **UNAVAILABLE**. Subagents were used within
  the admitted On permission. No helper wrote files, ran deployments/tests,
  used credentials/network or invoked Reviewer.
- This selected multiple audit passes, but did not obtain an external/cloud
  reviewer or independent ChatGPT conversation. The launch expressly forbids
  Reviewer invocation and credential use; an external service with a qualified
  safe repository-evidence channel was not established. Separate fresh contexts
  improve blind discovery, but share tooling, filesystem and requested model;
  correlated assumptions remain possible. They are implementation-side audit
  evidence, **not native independent acceptance**. Deliberative assessment and
  owner disposition of this report remain separate.
- The parent rechecked material recommendations against source, compared both
  passes and rejected unsupported generalizations. Public Task/bug records were
  read only; no Issues, comments, PRs or reviews were published. No PROD/TEST
  environment, private deployment repository, key, raw protected diagnostic,
  GitHub permission or service was accessed or changed.

## Active control-family inventory and assessment

Each row identifies a coherent active family, its canonical owner and actual
consumer, capability-to-harm path, residual/overlapping protection, operational
cost and cheapest acceptable direction. “High” confidence means the source
behavior and invariant are well supported; it never certifies a live host.
These are audit-local row numbers, not permanent control identifiers.

| Family; canonical contract and active evidence | Risk, impact, independent coverage and recovery | Cost and reconciled decision |
| --- | --- | --- |
| 1. Privileged configuration, credentials and fixed helpers. [Consumer contract](../../consumer/README.md); [loader/root ancestors](../../consumer/consumer-config.mjs#L119); [Writer helper](../../controller/src/privileged-writer-helper.mjs#L73); [fixed wrapper](../../deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2). | An untrusted caller substituting config, executable, environment or key paths could execute as root or publish with privileged credentials. Root parents, fixed cleared environments, configured repository selection and distinct Writer/Reviewer/worker identities block different substitutions. Credential theft/publication propagates and is expensive to recover; ordinary source review cannot replace this boundary. | Security-critical. Setup/debugging and rejected parent shapes cost work, but accepting worker-writable privileged code is unacceptable. **retain_preventive_control**, high. Centralize equivalent acquisition checks where useful; do not impose these host rules on ordinary owner workstation source ACLs, which current AGENTS already excludes. |
| 2. Workflow/event/run and external runner scheduling. [Controller contract](../../controller/README.md); [native admission](../../controller/src/live-authority.mjs#L107); [routing template](../../deploy/workflows/routing.yml.in); [policy reader](../../deploy/actions_policy.py#L74). | A foreign actor, fork, rerun or untrusted workflow reaching a persistent privileged runner can cross into installed capabilities. Workflow conditions, native run identity and external trusted-workflow/repository restrictions cover separate layers. Resulting compromise can be silent and installation-wide; labels are no substitute for ACLs. | Security-critical. Per-run identity checks remain; administrative policy requalification should follow relevant topology/workflow/policy changes, reusing qualified evidence otherwise. **retain_preventive_control / run_only_when_relevant**, high. Misleading inventory guidance is separately assessed below. |
| 3. Typed authority, protocol capability and frozen profile. [Authority contract](../../contracts/README.md#github-native-task-authority); [resolver](../../contracts/src/github-authority.mjs); [native source selection](../../controller/src/live-authority.mjs); [broker](../../controller/src/publication-broker.mjs). | Ordinary comments, edited Decisions, stale CRs or caller-selected profiles could authorize work/publication the owner did not select. Native Bot/parent/body binding and immutable admission prevent authority substitution. Independent review cannot retroactively authorize an unauthorized execution. Effects extend beyond local reversible edits. | Security-critical semantics with substantial schema/migration burden. **retain_preventive_control**, high. Clear capability diagnostics and bounded exact-original recovery are cheaper than new forms or redundant Decisions. Fresh legacy fallback would change the accepted trust contract and is not recommended. |
| 4. Step/title and Draft/Ready projections. [Controller numbering/handoff](../../controller/README.md); [projection/broker](../../controller/src/publication-broker.mjs#L77); [Step implementation](../../controller/src/step-metadata.mjs). | Incorrect projections confuse navigation and execution ownership. Some native run/target checks also use bounded names to bind the launch. Labels are not semantic Task authority, yet failed projection after reservation can strand an otherwise no-worker attempt. Durable admission and native actor/event checks independently protect authority. | Useful consistency, with disproportionate recovery pressure possible for display-only failures. **needs_owner_risk_decision**, medium on changing policy, high on coupling. Consider warning plus bounded repair only after separating display drift from actual target/numbering ambiguity; preserve current allocation and ambiguous-effect barriers until authorized. |
| 5. Per-attempt reservation, kernel exclusion and durable execution history. [Controller replay contract](../../controller/README.md); [attempt state](../../controller/src/attempt.mjs#L63); [exclusive/fsynced store](../../controller/src/attempt-store.mjs#L75); [kernel lock](../../controller/src/store-lock.mjs#L25). | Duplicate delivery or restart can launch a second model/worker or conflicting local execution. Kernel locks prevent overlap; durable reservation survives process death and prevents ambiguous relaunch. A lock alone cannot prove that a paid/external effect did not happen. Damage can propagate through publication; recovery must preserve the original attempt. | Security/correctness-critical. Journal/unknown-state burden is real but justified at this non-idempotent frontier. **retain_preventive_control**, high. Keep one record per actual effect and existing original-attempt recovery, without a parallel ledger or blind retry. |
| 6. Host/pool/Writer locks, admission quiesce and effect-based drain. [Lifecycle contract](../../controller/README.md#lifecycle-admission-and-drain); [admission control](../../controller/src/admission-control.mjs#L121); [lifecycle](../../deploy/lifecycle.py); [installer](../../deploy/intent_install.py). | Replacing trusted code/config while an old worker/publication is active can lose source, invalidate provenance or publish under incompatible authority. Idle runners/model exit do not prove containment and publication completion. Separate scopes for physical slots, refs and global lifecycle effects already reduce unrelated blocking. Unknown ownership still affects all resources it could own. | Critical production prevention; potentially long availability/recovery cost. **retain_preventive_control / replace_with_bounded_recovery**, high. Reuse valid terminal evidence, scope known conflicts and retain bounded same-operation recovery. Do not reopen completed Task history or introduce another drain gate. |
| 7. Untrusted Git import and non-force publication. [Writer contract](../../controller/README.md#issue-publication-and-worker-handoff); [fresh repository/import](../../controller/src/trusted-git.mjs#L97); [collection](../../controller/src/trusted-git.mjs#L311). | Root Git operating on model metadata could execute config/hooks/filters or follow alternate/replace objects. Importing bounded object bytes into fresh trusted metadata closes that path. Ancestry and non-force publication protect admitted history and foreign refs. Wrong publication is remotely visible but may be irreversible in effect. | Security-critical. Copying/scanning/storage cost is justified; ordinary root `git status` in the worker checkout is not equivalent. **retain_preventive_control**, high. Optimize bounded import internally while preserving complete observation and isolated trusted metadata. |
| 8. Commit identity, paths, file modes and introduced-blob scans. [Integration scan contract](../integration-reference.md#secret-scanning-policy); [chain validation](../../controller/src/trusted-git.mjs#L392); [safe paths](../../controller/src/execution-contract.mjs#L105); [candidate scanner](../../scripts/check-candidate.py). | A worker can publish foreign commits, unsafe paths, executable metadata types or secrets committed then deleted. Tip-only scans miss transient secret publication. Worker credential isolation and independent review overlap but do not prove every introduced blob safe. Publication leaks propagate and deletion does not undo exposure. | Security-critical publication policy plus bounded hygiene checks. **retain_preventive_control / retain_with_clearer_justification**, high. Both `100644` and `100755` are allowed; there is no blanket rejection of executable source. Symlink/submodule support would need its own design/risk decision. Never claim marker scans prove confidentiality. |
| 9. Regular files, no-follow, hard links, device/inode stability and acquisition bounds. [Collector contract](../../controller/README.md#collector-identity-and-separate-host-qualification); [descriptor reads](../../controller/src/trusted-git.mjs#L113); [regular-file gate](../../controller/src/trusted-git.mjs#L147); [installed config](../../deploy/installed_config.py#L25). | A privileged reader can be redirected to foreign/private bytes through aliases/races; FIFO/device reads can hang or cause side effects. No-follow descriptors, regular-file type, stable identity, bounded bytes and same-device traversal are complementary. In particular, copying bytes does not establish that a hard link belongs inside the authorized checkout. | Critical at root/untrusted acquisition. Blanket application to already sealed passive copies can be excessive. **retain_preventive_control** at that boundary; **simplify_equivalent_control** only with containment proof, high/medium. Existing [destination checking](../../deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py#L307) already reasons about wholly internal Cargo hard links; it is not authority to admit arbitrary aliases. |
| 10. Source provenance, package preparation, build identity and seals. [Installation contract](../git-managed-installation.md#preparation-before-cutover); [identity keys](../../deploy/relay-deploy.py#L82); [stage verification](../../deploy/install_preflight.py#L715); [stage seal](../../deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py#L202). | Wrong source/archive/build inputs or mutation between preparation and consume can install privileged foreign bytes. Frozen Git, pinned artifacts, sealed private stage, final locked verification and loaded-process proof cover different times and objects. Corruption can remain silent until privileged execution; rollback may itself be unsafe after cutover. | Critical provenance, costly broad packaging/traversal. **simplify_equivalent_control**, medium on savings. Preserve checks across actual mutation/trust gaps; consolidate only redundant scans inside one stable boundary. Reuse verified unchanged packages with full dependency/corruption invalidation, not version-only trust. |
| 11. Reviewer build/reuse and actual executable identity. [Artifact contract](../../deploy/README.md#lifecycle-upgrade-and-rollback); [reuse predicate](../../deploy/ansible/roles/relay_artifacts/tasks/verify-reviewer-reuse.yml#L60); [conditional Cargo](../../deploy/ansible/roles/relay_artifacts/tasks/main.yml#L174); [process proof](../../deploy/ansible/tasks/production-reviewer-process-validation.yml). | A new disk file or matching version does not prove the running publisher adopted the intended executable. Binary/provenance hashes and `/proc/MainPID/exe` address that distinct risk. Existing verified reuse already avoids compilation when all build inputs match. | Security-critical identity, conservative build invalidation. **retain_preventive_control** for artifact/process proof; **simplify_equivalent_control** for overbroad dependency keys, high/medium. All Reviewer tests and whole deployment roles currently participate in keys; narrow only after proving the actual compilation/recipe/toolchain closure. |
| 12. Worker UID/group, isolated homes and outer namespace. [Runtime contract](../../runtime/README.md); [isolation](../../deploy/ansible/roles/relay_codex_runtime/files/relay-codex-isolation.mjs); [launcher](../../deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2). | Model-controlled tools could read host credentials/sockets/other attempts or mutate privileged binaries. Fixed non-root identities, isolated per-attempt state and read-only OS/package mounts constrain that path. Network remains available. Installed Unix/namespace evidence is independent of source tests. | Security-critical, with real Linux/capability prerequisites. **retain_preventive_control**, high. Current Full Access removes an inner redundant native workspace restriction while preserving outer boundaries. Legacy serial Unix-only isolation is weaker and cannot be described as a checkout-only namespace. |
| 13. Containment, cancellation and bounded cleanup. [Runtime finalization contract](../../runtime/README.md#durable-diagnostics-and-sandbox-finalization); [finalizer](../../runtime/src/runtime-finalization.mjs); [dispatcher](../../controller/src/codex-dispatch.mjs); [cleanup](../../deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-cleanup.py.j2). | A dead controller can leave a model-UID child mutating files; pathname-only cleanup can delete a replaced/foreign sandbox. Inner group acknowledgement, outer disappearance and captured inode address separate sudo/UID/process boundaries. Exit status or a successful signal alone is insufficient. | Security-critical despite multi-pipe complexity. **retain_preventive_control**, high. Cleanup/time/entry limits should retain evidence and permit bounded diagnosis, never infer containment or authorize another worker. Disposable TEST cleanup is already explicitly cheaper within its verified sandbox. |
| 14. Diagnostic capsules, privacy, retention and warning completeness. [Warning policy](../execution-policy.md#execution-warning-disposition); [fallback](../../controller/src/diagnostic-fallback.mjs); [primary store](../../controller/src/diagnostic-store.mjs); [evidence reader](../../reviewer/src/github/evidence.rs). | Cleanup/crash before ordinary diagnostics can erase the causal frontier and prompt unsafe replays. Raw output can leak credentials. Minimal pre-effect persistence/redaction matters; complete execution-warning evidence informs independent acceptance. A diagnostic copy is not itself Task authority. | Useful defense in depth with capacity/fsync and recovery cost; eight fallback slots can block launches. **retain_with_clearer_justification / simplify_equivalent_control**, medium. Evaluate whether existing durable journal evidence can replace a particular mirror, but retain irreconstructible evidence before destructive cleanup. No verbose success-history ledger. |
| 15. Reviewer ingress, typed RPC, fixed API origin and separate identity. [Reviewer/integration contracts](../../reviewer/README.md); [certificate verification](../../reviewer/src/mtls_identity.rs); [RPC](../../reviewer/src/main.rs); [GitHub client](../../reviewer/src/github.rs). | Spoofed HTTP identity, caller-selected URLs/redirects, foreign targets or oversized requests could gain publication or leak tokens. Trusted mTLS termination, stripped headers, backend certificate checks, private listener and fixed destinations address distinct links. Backend forwarded certificate validation alone is not proof of private-key possession. | Security-critical trust boundary; certificate/private-network prerequisites are justified. **retain_preventive_control**, high. No evidence supports public bind or merging Writer/Reviewer credentials. Source qualification cannot certify live ingress or App grants. |
| 16. Decisive review/authority publication and auxiliary Check recovery. [Reviewer state contract](../../reviewer/README.md#native-authority-and-publication); [publication](../../reviewer/src/publication.rs); [store](../../reviewer/src/store.rs#L79). | A lost response followed by another decisive POST can duplicate/change native acceptance; moved head or forged Outcome can accept unrelated bytes. Durable decisive reservation and exact native readback have independent purposes. GitHub is authoritative for completed effects. | Critical decisive protection, proportionate auxiliary recovery. **retain_preventive_control**, high. Mirrored native receipt/event writes are already retired; one bounded identical Check repair and visible duplicate warning already embody cheaper recovery. Do not audit their removed machinery as an active defect or rebuild it. |
| 17. Payload, history, pagination and time budgets. [Reviewer acquisition contract](../../reviewer/README.md#native-authority-and-publication); [evidence bounds](../../reviewer/src/github/evidence.rs#L8); [attempt bounds](../../controller/src/attempt-store.mjs#L9). | Unbounded native histories/outputs can exhaust service resources; partial authority or omitted warnings can silently authorize wrong work. Fixed destinations, byte/deadline budgets, explicit truncation and adaptive authority paging already overlap. A truncated record is an evidence gap, not absence. | Availability defense in depth; numeric caps can reject legitimate long tasks. **simplify_equivalent_control**, medium; **insufficient_evidence** for changing particular numbers. Prefer bounded/adaptive complete acquisition and actionable gaps; warning-only is suitable for optional display, not incomplete authority/required warnings. No confirmed cap incident was reproduced here. |
| 18. Candidate checks, cross-consumer qualification and installed proof. [Validation contract](../../CONTRIBUTING.md#local-validation); [native CI](../../.github/workflows/relay-exact-head-validation.yml); [three-consumer qualifier](../../scripts/qualify.py); [installed scope](../../deploy/README.md#qualification). | Unit tests alone miss Rust/Node schema compatibility, actual binary/config loading, Unix privilege separation and real services. Hosted exact-head CI, cross-consumer fixtures and installed checks prove distinct invariants. Independent judgment and exact-head acceptance remain separate from green tests. | Useful prevention with large execution/dependency/baseline-debt cost. **run_only_when_relevant / simplify_equivalent_control**, high. Propose exact-artifact reuse and change-relevant broad suites through later authority; this audit does not waive current checks. A new source edit must not retroactively own unrelated environment debt. |
| 19. Optional hooks and passive guidance qualification. [Hook contract](../../.codex/hooks/README.md); [passive payload validator](../../scripts/qualify-vibevm.py#L170); [filesystem qualifier](../../scripts/qualify-runner-self-update.py#L253). | Optional checkpoints protect irreconstructible context; stale notes are not authority. Passive documents are read, not executed, so synthetic physical executable bits do not themselves yield privileged execution. Linux security tests still need actual Linux semantics; a pathname is not a filesystem capability. | Optional hardening is already the hook policy: **make_optional_hardening** (retain existing classification). Passive mode/path heuristics: **simplify_equivalent_control**, high on mismatch, medium on remedy. Prefer committed package modes and capability-based/native temporary qualification; never make hooks a launch gate or chmod original owner source. |

The consequence/cost comparison includes these shared failure and human factors:

- Families 1–3, 7–9, 12 and 15–16 can fail silently across privileged or remote
  boundaries; harm can reach every configured repository or expose credentials.
  Detection after publication is too late to undo disclosure or native effects.
  Friction can encourage direct root Git, broad runner ACLs, shared credentials
  or legacy routing, so keep the protected path usable and diagnostics precise
  while retaining prevention. Those bypass possibilities are risk judgments,
  not observed behavior by this owner.
- Families 5–6 and 13 involve uncertain continuing processes or external effects.
  Kernel-lock release is visible, but completed side effects may remain unknown;
  recovery cost can include installation downtime and preserved source. Long
  holds can encourage journal deletion/blind retries. Scoped effects and bounded
  original-operation recovery are cheaper than global historical holds, while
  missing containment or unknown publication cannot become warnings alone.
- Families 10–11 protect a similarly serious eventual executable boundary, but
  repeated preparation failures before cutover are generally visible and leave
  the old entrypoint available. Their download/build/maintenance cost and offline
  incompatibility encourage bypassing packaging or skipping updates. Reuse
  content-bound proof and consolidate stable observations; retain final loaded
  identity because wrong active bytes can propagate after cutover.
- Families 4, 14 and 17–19 include several different effects: cosmetic drift,
  optional notes and local test/format failures are visible and recoverable;
  lost irreconstructible diagnostics or incomplete authoritative acquisition
  have more serious evidence consequences. Treat each accordingly. Repeated
  false positives encourage chmod workarounds, disabled checks, copied stale
  evidence or abandonment. Keep optional tools optional, classify baseline debt,
  prefer bounded repair for projections and preserve truthful gaps for required
  evidence. No workaround frequency or maintenance-hour estimate was measured.

## Reconciled findings and mandatory challenge cases

All source behaviors below predate this report at the audited baseline. Unless
an existing defect is explicitly identified, recommendations are **proposed
optional changes**, not newly invented review blockers or permission to repair.
A/B attribution records discovery, not a vote. Parent verification and the
accepted risk/cost principle determine the disposition.

| Finding and challenge coverage | Audit provenance, observed fact versus judgment | Reconciled disposition, confidence and smallest direction |
| --- | --- | --- |
| WSL `/mnt/<drive>` and native filesystems (case 1). | A and B independently identified the path-prefix ban in `qualify-runner-self-update.py:256`; parent verified it. CONTRIBUTING requires native Linux for filesystem/security proof, not a blanket prohibition on editing source on Windows. AGENTS already excludes ordinary owner workstation source ACLs from this audit. The prefix can reject a native mount and does not prove semantics elsewhere. | **simplify_equivalent_control**, high/medium. Preserve Linux boundary tests; use native task-local temporary qualification or capability checks. Separate source editing/format checks from UID/inode/no-follow/namespace claims. No production filesystem expansion or original-file permission repair is proposed. |
| Regular files, hard links and aliases (case 2). | Both passes retain no-follow/regular/bounded acquisition; A highlights contained Cargo hard-link handling. Parent verified `trusted-git.mjs:147–170` and `relay-intent-stage.py:307–355`. B separately identifies the ordinary local projection reader's `nlink == 1` gate; its stable bounded reads and atomic output replacement do not modify a linked input inode. A blanket claim that all `st_nlink == 1` checks are unnecessary is rejected: root copying a foreign hard link can disclose bytes outside admitted scope. | **retain_preventive_control** at acquisition and secret/root-code boundaries; **simplify_equivalent_control** for proven contained immutable package aliases and separately assessed ordinary local text reads, high/medium. Parent verified [projection acquisition](../../deploy/workflow_projection.py#L55) and [replacement](../../deploy/workflow_projection.py#L299). Preserve no-follow, stable bytes and drift checks; do not generalize local acceptance to root acquisition. No global `nlink` removal. |
| Executable bits and mode checks (case 3). | A flags physical execute-bit rejection on passive packages (`qualify-vibevm.py:170–185`). B independently flags the same shape restriction in workflow templates/manifests/receiving text (`workflow_projection.py:55–68`); parent verified both consumers. Neither reader executes that text. In contrast Writer accepts both regular Git modes and staging normalizes Git archive modes. Installed executable/traversal bits and private credential modes protect real execution/privacy invariants. | **simplify_equivalent_control** for passive distribution validation; **remove_or_retire** the ordinary workflow text reader's executable-bit gate, high on source/medium on compatibility remedy. Preserve stable bounded no-follow acquisition, byte-drift/concurrent-change checks and deterministic `0644` output. **retain_preventive_control** on active installed artifacts. Claims of a current blanket source executable ban are rejected. |
| Ownership, ancestors and ordinary shapes (case 4). | Both passes distinguish privileged substitution from local source shape. Parent verified root config ancestors and final installed parent checks. Private-mode worker collection is already supported by fixed Writer, so the old “chmod all worker output” workaround is superseded. During this audit the test preload also rejected a group-writable synthetic checkout fixture; see validation. | **retain_preventive_control** for root code/config and credentials; **run_only_when_relevant** for evidence scope. Improve test fixture acquisition rather than weaken production config checks. Owner workstation ACL inheritance remains outside scope. No original source mode/owner changes. |
| Installation prerequisites and workflow publication (case 5). | Both passes refer to current ordinary install producing later-review integration artifacts. Parent verified expert bootstrap/reinstall still returns `WORKFLOW_REVIEW_REQUIRED` before installation (`relay-deploy.py:520–537`). Live [Issue 240](https://github.com/jresearchsoftware/codex-relay/issues/240) already records the accepted Task 63 mismatch and owns correction. | **replace_with_detection_or_warning** for unrelated, unused compatible workflow drift; high on existing behavior and bug ownership. Reuse Issue 240, preserve actual invoked-workflow compatibility and protected recovery. Do not create a duplicate, reopen Task 63/230 or exempt genuinely required workflow validation. |
| Journals, locks, receipts and recovery barriers (case 6). | A/B agree irreversible execution/publication and production cutover require durable intents. A emphasizes display and diagnostic mirrors; B identifies exact repeated hashing: [seal computes a digest then immediately verifies it](../../deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py#L375); [verify_stage](../../deploy/install_preflight.py#L715) verifies, then `check-destination` [verifies again](../../deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py#L387). Parent verified these paths, current scoped effects and retired Reviewer receipt mirrors. Revalidation across drain/mutation gaps has a distinct purpose. | **retain_preventive_control** for decisive effects and uncertain containment; **replace_with_bounded_recovery / simplify_equivalent_control** for visible local/projection/auxiliary effects and duplicate computation within one stable boundary, medium. Carry an in-memory verification result only within that bounded call; never reuse it across an unproven mutation interval, delete history or use age as permission. |
| Baseline/environment debt and mandatory broad validation (case 7). | Both passes flag all-tracked candidate scans and repeated broad suites; parent verified scanner/CI and established a clean baseline scan. Native CI additionally resolves a separate publisher's moving `main`, which can make producer readiness depend on another repository's state. This audit did not establish an incident attributable to that dependency. Actual local tooling limitations are disclosed below. | **run_only_when_relevant**, medium; **needs_owner_risk_decision** for changing the current universal mandatory set. Retain exact-head integration/secret checks, classify baseline/environment failures and reuse exact build artifacts; assess external-readiness sensitivity separately. Current checks are unchanged. No pre-existing debt is silently converted to this Step's remediation. |
| Historical assumptions and misleading administrative output (case 8). | A found stale active runtime README text describing the retired Issue/v3 path and CLI baseline; parent compared it to current architecture/runtime source. Parent confirmed inventory emits `onlyRepository` and public PROD workflow refs at `inventory.py:499–529`, despite the shared/private lifecycle contract. Live [Issue 241](https://github.com/jresearchsoftware/codex-relay/issues/241) already owns that defect; no live ACL mutation was established. | **remove_or_retire** stale active guidance, high; preserve frozen original-runtime recovery fixtures. Inventory prescriptions: **replace_with_detection_or_warning**, high, under Issue 241: state scoped verification and unknown full ACL instead of a destructive replacement target. Actual scheduling isolation remains preventive. |
| Control-induced deployment work and latency. | A/B agree on broad role/package/reuse-key costs. B independently traces repeated seal work and unchanged package preparation; the specialist additionally finds 31 duplicate per-slot APT calls. Parent verified the package call sites and fixed slot derivation. No pass proves their elapsed contribution to PROD. | **simplify_equivalent_control / run_only_when_relevant**, high on duplicate calls, medium on larger alternatives. The concrete first implementation candidate and measurement-dependent successors follow. Avoid new caches, services, fixed waits or timeout increases as a performance remedy. |
| Acquisition limits and diagnostic capacity. | A emphasizes legitimate-history ceilings and fallback slots; B does not supply a counterexample showing those exact limits failed. Parent verified 75-item evidence/500-record authority policies and eight-slot diagnostic contract. This disagreement is evidence sufficiency, not a reason to pick the strictest or most permissive answer. | **insufficient_evidence** to change particular caps; **retain_with_clearer_justification**, medium. On a demonstrated legitimate failure, use bounded complete pagination/recovery before raising/removing a limit. Incomplete required evidence must remain explicit. |

The passes agree on retaining the substantive protections in families 1–3,
5–9, 12–13 and 15–16. A's broader interest in projection/cap simplification is
kept as an owner/evidence question. B's repeated-hashing observation is bounded
by A's mutation-gap warning. Neither supports eliminating all stage verification.
The specialist's package deduplication was a material omission from the broad
passes; it gives the first follow-up a smaller risk surface than a general
changed-component skip mechanism. Both passes' possible Rust rebuild concern is
rejected as a diagnosis of the observed run because verified binary reuse exists
and actual branch/provenance evidence is unavailable.

## Task 230 and the next natural Apply: evidence and critical path

The [Task 230 owner completion report](https://github.com/jresearchsoftware/codex-relay/issues/230#issuecomment-6853749103)
reports installed product `93a48523ac0dc6310171ae39945497b83b017d8a`, consumer
projection `479e38f306d9a0c616da6a322911a17db4a78944`, Apply **1,590 s** and
separate post-check **1,464 s**, totaling **3,054 s (50m54s)**. These are operator
reports, corroborated as published text, not re-observed host timings. Its
completed recovery/qualification context is not a representative measured
code-only phase profile. Reported nonfatal Ansible temporary-directory fallback
warnings remain unmeasured; there is no basis to prescribe a separate fix.

The later [Task 57 baseline comment](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6862151203)
identifies natural deployment run `43479023265`, job `132070376138`, prior
product `93a48523ac0dc6310171ae39945497b83b017d8a`, target
`5df7e0093d93c5a55b996e34cc83359da6b22a3e` and private config
`dc17d8b9f904f6536d9d76568b94514ffd5afe87`. The parent independently checked the
local Git comparison: twelve files/two commits changed, including workflow
projection files; no `deploy/` or `reviewer/` file changed. That fact does not
prove installed package state, deployment inputs or actual reuse/restarts.
The private run/log was not accessed by this execution. Its marker provenance is
the owner's comment, not an independently downloaded complete run log.

| Reported UTC interval, 2026-11-13 | Seconds | What it establishes |
| --- | ---: | --- |
| Run creation 18:04:31 → protected step 18:04:36 | 5 | Queue/start/setup aggregate; not a phase-level host measurement. |
| Protected step start → plan 18:04:44 | 8 | Initial wrapper work. |
| Plan → source resolved 18:04:50 | 6 | Source-selection marker interval. |
| Source resolved → prepared preflight 18:06:46 | 116 | Preparation/preflight aggregate; package/build/fact split unknown. |
| Prepared → QUIESCE 18:06:49 | 3 | Transition overhead aggregate. |
| QUIESCE → DRAIN 18:06:57 | 8 | Gate/transport aggregate. |
| DRAIN → APPLY 18:07:17 | 20 | Drain and transition aggregate; not proof of 20 seconds waiting on work. |
| APPLY → ACTIVATE/VERIFY 18:16:43 | 566 | Final revalidation, backend composition/pool and internal activation/verification aggregate. |
| ACTIVATE/VERIFY → RESUME 18:16:44 | 1 | Marker interval. |
| RESUME → OPEN 18:16:46 | 2 | Verified gate transition aggregate. |
| OPEN → successful result 18:16:49 | 3 | Final readback/output aggregate. |
| Result → run completion 18:16:53 | 4 | Wrapper/job teardown aggregate. |
| Total | **742** | All observed wall time accounted for without assigning internal causes. |

The protected-step sum is **733 s**. The wrapper separately reports **715 s**;
the **18 s** difference lies within differently bounded clocks and is not
silently assigned to an Ansible role. The comment reports no separate post-check
inside this later run. Do not subtract unlike runs to claim an improvement or
reuse DocReview #130/#213 measurements as evidence of Relay's present cause.

### Source path and distinct assertions

1. [Strategy selection](../../deploy/intent_install.py#L178) distinguishes an
   equivalent exact Git pair/read-only verify, same-product reconciliation and
   compatible product upgrade. Code-only, config-only and combined changed-pair
   updates share preparation and composition; exact no-op verification is a
   different path. Version/diff size is not a safe selector by itself.
2. [Preparation](../../deploy/relay-deploy.py#L781) acquires/stages source,
   checks current effects/resources/policy, prepares prerequisites and seals
   candidate artifacts. [Runner staging](../../deploy/ansible/roles/relay_runner/tasks/intent-stage-package.yml)
   downloads/extracts/probes a package; [Codex staging](../../deploy/ansible/roles/relay_codex_runtime/tasks/intent-stage-package.yml)
   installs/probes its pinned distribution even when live components may be
   unchanged. Four fact-gathering entrypoints are reachable in the traced
   upgrade (two stage invocations, preflight and main site); actual counts and
   per-gather costs in this run need backend evidence. The second source stage
   verifies existing bytes rather than necessarily extracting again.
3. Reviewer reuse compares source, build-input/contract/toolchain and actual
   binary digests. Cargo runs only when reuse fails and the path is not staged
   consumption/check mode. A code-only controller edit can reuse the Reviewer;
   an unrelated deployment-role edit can invalidate its broad build key. Neither
   fact proves which branch ran on the host.
4. Host locking is nonblocking; [drain](../../deploy/install_preflight.py#L764)
   is bounded to 1,800 seconds and releases Writer locking between observations.
   A timeout ceiling is not elapsed waiting. After APPLY is printed,
   [final revalidation/composition](../../deploy/relay-deploy.py#L1000) still
   occurs; ACTIVATE/VERIFY prints after backend proof. Do not label the whole
   566 seconds Rust compilation, drain or service activation.
5. [Main site](../../deploy/ansible/site.yml) traverses base/runtime/artifact,
   bind/ingress/Codex/controller, all configured additional execution slots,
   Runner and pool work. [Configuration](../../deploy/config.py#L92) derives
   32 fixed internal slots independently of physical desired capacity; stable
   slot identities preserve retained-attempt recovery. Additional slot tasks
   repeat shared APT work and many per-slot operations. Recursive journal and
   toolchain ownership reconciliation can scale with retained state. These are
   observed source paths, not measured rankings of bottlenecks.
6. Apply's final proof includes intended installed source/config/Git pair,
   protected parents, Writer/launcher bindings, timer state, actual loaded
   Reviewer executable, previously active service adoption, pool readiness and
   preserved General transport identity. It clears operation evidence only
   after validation and emits `PRODUCTION_APPLY_VALIDATED`; the wrapper requires
   that same-operation proof before resume. Activation has bounded listener/
   service retries; their actual retry counts are unavailable.
7. [The wrapper](../../deploy/relay-deploy.py#L1123) runs another full backend
   `--check` only for `install_flow` (bootstrap/reinstall), retaining clean-state
   qualification. Ordinary upgrade reuses its own final proof. Explicit
   post-check traverses the broad site and can independently detect later drift,
   inconsistent read-only convergence and the post-check Writer runtime binding.
   For an ordinary upgrade, an immediate duplicate source/service/runner check
   adds no new temporal or component guarantee merely by being a second pass.
   Bootstrap/reinstall, graceful-stop resume and failed/partial recovery have
   separate reasons for read-only inspection. Keep those reasons explicit.
8. [Outer Git result readback](../../deploy/owner_lifecycle.py#L219) verifies
   installed pair/effective consumer after installer completion. This bounded
   readback is distinct from rerunning the complete playbook and must remain
   in a safe single-pass success path. Public [Task 25](https://github.com/jresearchsoftware/codex-relay/issues/25)
   owns that minimal ordinary lifecycle; this report does not redefine it.

### Missing causal proof and exact next evidence

No Task 230 raw Apply/post-check logs or sanitized per-task timing profile was
found in the repository. Its committed qualification reports concern earlier
recovery work, not these final production durations. The newer public evidence
also explicitly lacks host task timings. Private run access/protected host
inspection is outside this worker's capability and authority.

The existing [profiling helper](../../deploy/ansible/tests/profile_qualification.py)
counts task/fact boundaries and explicitly reports unavailable task wall times;
its local timed experiment covers only operation-clear, not deployment. Existing
`run_backend()` reports 30-second heartbeat totals, not task durations.
[Backend environment recreation](../../deploy/ansible_transport.py#L38) strips
arbitrary `ANSIBLE_*` overrides; [Ansible config](../../deploy/ansible/ansible.cfg)
does not enable task profiling. Telling the owner to set `profile_tasks` in the
caller environment would not establish that it reached this backend.

The smallest missing evidence is an owner-authorized sanitized timing extract
from the **existing** two operations, bound to operation UUID, source/config
pair and run/job. Include timestamps/durations for every backend invocation,
role/task/fact gather (including skipped/retried/failed/waiting/queued work),
stage/package/build provenance, lock/drain observations, Runner activity,
service restart/retry counts, installed-state verification and outer readback.
Account for gaps between subprocesses as well as task durations. Exclude task
arguments, environment, host-private paths, credentials and raw diagnostics.
Unavailable timestamps must remain unavailable. Do not start an additional PROD
Apply, replay, load test or credential read to fill this gap.

## Prioritized follow-up candidates and acceptance

These are proposals for subsequent canonical authority, not this Step's work.
No numerical performance SLA is asserted before profiling.

| Priority/dependency | Minimal executable scope | Required proof and cost target |
| --- | --- | --- |
| P1, independent low-risk correction | Remove duplicate `apt: bubblewrap; state: present` in [execution-slot.yml:48](../../deploy/ansible/tasks/execution-slot.yml#L48). The identical owning package task already precedes the loop at [site.yml:117](../../deploy/ansible/site.yml#L117), under the same manage-packages condition. Keep the fixed 32-slot contract, per-slot reconciliation and all namespace probes. Current production source has only this site caller. | Eliminate **31 duplicate APT module invocations per full managed site traversal**, including relevant check paths. Preserve missing-package installation before probes, management-disabled behavior, APT-failure stop, primary/all-slot namespace proofs, safe paths/ownership, capacities 1/32 and recovery UUID/closed-gate behavior. This is an exact call-count target; elapsed savings remain to be measured. No cache, new gate or operator action. |
| P1 measurement, alongside that correction | Add bounded built-in phase/task durations to the existing deployment output path ([wrapper](../../deploy/relay-deploy.py#L183), fixed backend config/transport), without task arguments, private payloads, new service, dependency or ledger. First reuse any naturally existing sanitized timings; new source instrumentation applies only to subsequent already authorized runs. | On the same qualified disposable fixture, alternate baseline/candidate repetitions with identical input pairs and initial state. Record warm/cold cache state, build/reuse provenance, full task/call counts, preparation, facts, main composition, pool, waits and readback. Include code-only/config-only/combined/no-op and failure/recovery paths. Set the wall-time reduction target to measured removed-call cost and observed variance; report end-to-end time, not just a microbenchmark. |
| P2, after measured attribution | Reuse unchanged Runner/Codex packages in the private preparation path; narrow Reviewer rebuild invalidation to actual compilation and build-recipe inputs. Preserve fresh qualification when provenance or bytes fail. | Include package/distribution content, archive/installer/validator identity, toolchain/host/flags, Cargo manifest/lock and both embedded schemas. Test unchanged reuse, each relevant change invalidating reuse, corrupt/missing package fallback, foreign mode/link refusal and actual loaded binary. Version equality alone is insufficient. Expected saving is the measured preparation/build/restaging portion; no source evidence yet supplies seconds. |
| P2, if role traversal dominates | Reduce duplicate target transports/fact gathers and reconcile unchanged slot/role inputs once per operation, retaining final locked production checks. Start with same-boundary consolidation rather than skipping entire security roles. | Inventory and preserve each independently timed invariant and invalidation source, including shared state/credentials, external policy changes and installed drift. Test cold install, drift, capacity/config changes, concurrent admission, interrupted cutover and forward recovery. No persistent validity cache or unused-slot removal without separate accepted contract analysis. |
| P2, existing authority owners | Reuse Issue 240 for unused compatible workflow publication coupling; Issue 241 for destructive-looking stale ACL guidance. Retire misleading active legacy runtime text in the same eventual source/guidance maintenance. | Validate actual invoked-workflow incompatibility still blocks and inventory never claims a complete ACL target without evidence. Preserve other consumers, private lifecycle and frozen old-attempt recovery. Neither completed Task 63 nor Task 230 is reopened, and no duplicate issue is needed. |
| P3, owner/evidence decisions | Consider projection warning/repair, passive mode/capability qualification, targeted validation and bounded acquisition/diagnostic refinements. | Identify the affected supported guarantee and actual encountered cost before changing it. Preserve exact-head/current authority, complete required warnings, decisive POST reservation, secret boundaries and unknown containment. An optional weaker assurance must be named as an owner risk decision, not smuggled in as cleanup. |

For the first follow-up, the normal path must still finish one authoritative
Apply proof plus bounded outer readback without an extra equivalent post-check.
Negative tests must leave admission closed on wrong source/config, corrupted
staged bytes, failed service/process adoption, lost lock, unknown active attempt
and ambiguous publication. Recovery must preserve the same operation and
original attempt histories. Compare measured total latency with the representative
742/733/715-second baseline only after input/cache/state equivalence is established.
No longer timeout, fixed wait or extra diagnostics alone satisfies the performance
goal; the first patch must remove the known repeated work and demonstrate its
measured effect.

## Owner decisions, warnings and limitations

- Authorize the P1 source correction/measurement scope separately if selected;
  larger changed-component work depends on actual measured costs. Decide
  explicitly whether any display consistency guarantee may degrade to warning
  plus repair. Report acceptance does not adopt these recommendations.
- The Task 230 causal timing request remains **insufficient_evidence**, as does
  phase-level attribution for the next natural Apply. Existing owner timing
  reports are usable baselines, not proof of a bottleneck or fast-path success.
- No live App grants, runner ACLs, ingress/mTLS, Unix isolation, installed
  service/process adoption, production recovery or wall-time reduction was
  proven. No live attack experiment, synthetic PROD benchmark, deployment,
  merge, release or Issue closure occurred.
- Required native job/check/runtime execution-warning surfaces were not
  available through this launch's permitted evidence channel. The report cannot
  claim no execution warnings. Known Task 230 temporary-directory warnings are
  retained as unprofiled operator evidence; no additional corrective obligation
  is inferred. Test/tooling warnings and skipped proof are recorded below.
- Coverage is across materially distinct active control families and their
  consumers, not line-by-line penetration testing of every helper or a complete
  historical provenance audit. External systems, private config contents,
  consumer-specific custom validation and effective GitHub rules/bypass actors
  were not audited. Historical DocReview latency techniques were not treated as
  current Relay evidence or permission to reopen those Tasks.

## Local validation

Only this Markdown audit artifact is intended for delivery. No regression test
or new mandatory audit framework was added. Initial baseline candidate scanning
passed: 1,448 tracked files, 2,345 local links. Linux unprivileged execution
used UID 990, Node 22.23.3, Python 3.11.2 and Rust/Cargo 1.90.0; Node differs
from the recorded checked 22.20.0 baseline while meeting the declared minimum.
The required commands were attempted without privilege escalation. Test setup
exposed baseline environment/fixture assumptions; no original source permissions,
Git config, hook, remote or product behavior was changed to make a check pass.

| Check | Observed result and limit |
| --- | --- |
| `npm test` | Final run: **1,168 passed, 0 failed, 7 skipped** (1,175 tests). Used a private copy of the synthetic example config, private temporary root and ordinary `022` fixture umask. Initial default fixture loading failed because the checkout fixture was group-writable; `077` also exposed fixtures expecting exact `0644` files. The focused migration suite then passed 37 tests with one skip under `022`. |
| `cargo fmt --manifest-path reviewer/Cargo.toml --check` | **PASS**. |
| `cargo test --manifest-path reviewer/Cargo.toml --locked` | **159 passed**, no failures. The default `cc` linker alias was missing; explicit existing `/usr/bin/gcc` via process-only compiler/linker environment succeeded. Locked dependencies and repository configuration were unchanged. |
| `python3 scripts/qualify.py` | **THREE_CONSUMER_PASS**, including actual service binary and loopback handlers. The first attempt encountered a missing system OpenSSL configuration; process-only `OPENSSL_CONF=/dev/null` allowed its explicitly configured disposable fixture certificates. This proves synthetic configuration/transport, not installed TLS or production credentials. |
| Python deployment suites | Final full attempt: **1,807 passed, 157 failed, 809 skipped** in 183.53 seconds. No full-suite PASS is claimed. The earlier inherited temporary/umask attempt produced 1,454 passes, 502 failures, 809 skips and 8 setup errors; private-root `077` reduced that to 1,805 passes, 159 failures and 809 skips. These are fixture/environment investigations, not separate source candidates. |
| Targeted actual Ansible transport | **9 passed, 5 skipped** with UTF-8 process locale. Ansible core 2.17.14 is present; the inherited C locale prevents it starting, explaining the representative `ANSIBLE_TARGET_OPERATION_UNPROVEN` results in earlier full attempts. This is a focused correction check, not a green full-suite result. |
| Report formatting/link/structure | Staged candidate scanner **PASS**: **1,449 tracked files, 2,447 local links**. `git diff --check` and staged whitespace check passed. Nineteen family rows, all ten requested dispositions and the complete 742-second timing arithmetic were checked. |

Python initially lacked pytest/pip/ensurepip. A temporary task-owned directory
received pytest 8.3.5 and its missing wheel dependencies with downloaded wheel
hash verification, without system package installation. Remaining failures were
reported as environment/fixture-related, including protected ownership checks.
The original raw failure records are not retained in this deliverable. Step 2's
source check did not substantiate the earlier specific checkout-helper ancestry
explanation for `consumer_drift.restore()`; that attribution and the causes of
all 157 failures remain unverified. No complete per-case baseline diagnosis is
claimed, and installed/root-only skips remain unproved. This grants no authority
to weaken installed protection or change source ownership.
The report is the only intended source delta; complete passing deployment
qualification and native independent review are not claimed.

Terminal anonymous authority refresh retained the same charter hash and exactly
the two inspected comments (baseline evidence and trusted Decision), without a
next comments page. No authority change was observed in that bounded refresh.
No product-source correction was made for the failing baseline Python checks;
the next qualified native/local validation must retain these gaps rather than
claiming this execution established full deployment proof. Causal production
profiling remains blocked at the unavailable sanitized-existing-log boundary.
