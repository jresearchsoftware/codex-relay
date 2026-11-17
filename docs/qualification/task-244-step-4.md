# Task 244 Step 4: causal evidence and live lifecycle audit

This execution starts at accepted main
`126565c6b5ec9c508238fdd8ddede41587724c08`, under Decision 6959384601.
PR #274 and PR #276 remain accepted historical evidence. This is a new source
candidate, not a replay or rewrite of their attempts. The supplied native launch
identifies Task 244 Step 4. Publication, native exact-head CI and independent
acceptance belong to Writer and Reviewer after this local handoff.

## Coverage and corrections

The audit used the complete changed-file sets of `d205691` (PR #274: 263 files,
171 outside installed/frozen guidance projections) and `126565c6` (PR #276:
six files), then followed the actual current callers, generated source closures
and subprocess/task boundaries. Frozen Skill 9.0.0 and its installed/exported
bytes are unchanged. Prior tests and inventories are reused where behavior is
unchanged; the following table identifies new observations and corrections,
rather than treating the older inventory as an absence-of-defects proof.

| Boundary inspected | Concrete finding / disposition | Evidence destination and regression |
| --- | --- | --- |
| Routing, live authority, pre-admission target rejection and event parsing | Existing predicate reasons, trusted-target restriction, failed BLOCKED Actions result and no execution/replay/label-consumption controls are retained. Controller recording had omitted the actual error and accepted malformed recorder receipts; corrected. | Existing protected controller primary/fallback archives; `controller/test/host-failure-diagnostic.test.mjs`, entrypoint admission-order and causal tests. No new target-bound Outcome before binding. |
| Controller checkpoints, checkout, runtime, collection and publication | Durable checkpoints alone supplied no live wait observation. Existing transition timing now emits fixed operation starts/waits/completion/failure to stderr while the operation runs. | Ordinary workflow stderr plus existing transition records; `controller/test/runtime-progress.test.mjs` exercises real entrypoint operations and quiet pending work. Semantic stdout remains the existing envelope. |
| Writer/API/native receipts | Malformed/misbound zero-exit Writer output lost native evidence; clipped diagnostic receipts could be mistaken for complete JSON; helper wait was unbounded. Original output, counts and truncation now survive; clipped receipts are refused and the existing recorder call is bounded. | Existing causal archive and independent unavailable notice; host-failure, causal and wrapper tests. Publication uncertainty and one-call reservation remain unchanged. |
| Runtime finalization, fallback and wrapper readers | Cleanup causal evidence could become the primary archive cause. Both-store failures lacked an independent observed-but-not-retained notice. Readers treating all stderr as one JSON object lost classification when notices preceded it. | Original cause remains primary, cleanup is separate; terminal envelope readers consume the final complete result. `runtime/test/durability.test.mjs`, controller diagnostic-durability, wrapper and coupled consumer-preflight/serial-reader regressions. |
| Rust Reviewer helper I/O | Stdin submission preceded output drains; excess stdout stopped being drained. Both could turn an available early native failure into timeout. | Concurrent bounded drains preserve stderr, native exit and byte counts; `reviewer/src/manual_outcome.rs` regressions exercise large stdin/early stderr and oversized stdout. Mutation uncertainty and reservation behavior remain unchanged. |
| Reviewer task/panic/store boundary | Default panic output was unbounded/unredacted; retained review-body SQLite reads used `expect`. | Existing protected tracing/journal gets a bounded redacted panic cause and location, without swallowing the panic/JoinError; store errors remain typed causes. `reviewer/src/diagnostics.rs` and `step_sync.rs` regressions. Existing HTTP 422 early classification and detached response capture remain covered. |
| Ansible controller startup / receipt | Both controller streams were DEVNULL. Missing/invalid receipts removed the only actionable startup output. | Existing private operation spools now drain bounded prefixes/tails, retain sanitized fsynced `failure.log`, counts and exact receipt/exit/OS observations before cleanup. `deploy/tests/test_transport_causal_evidence.py` reads actual stored evidence, including the actual `LC_ALL=C` Ansible locale refusal. |
| Native local target, interrupted channels and guard cleanup | Oversized/unsafe output collapsed to a code; secondary cleanup could mask the first error. Guard stderr was discarded. DRAIN's stdin-before-stderr ordering could deadlock with a valid small Linux pipe. | Same private transport evidence; original return classification and unknown target effects are preserved. Native root tests are updated; unprivileged tests inject store failure, timeout, late error and 4 KB pipe backpressure. No retry is inferred from a missing receipt. |
| Deployment reporter itself | Preconfiguration/nonroot paths had no durable destination despite writable local storage. Prefix-only projection discarded late failure messages already captured in memory. Broken formatting/summary streams and mid-credential capture edges also needed handling. | Reuses private temporary deployment logs when configured log/journal is unavailable; independent bounded recorder failures if all stores fail. Head/tail projection follows redaction. `deploy/tests/test_failure_evidence.py` covers fsync/store/formatter/public-stream failure, unknown exceptions, counts, late causes and partial-secret redaction. |
| Owner preflight, source Git, admission, Apply and quiet children | Code-only wrappers lost captured child output; line iteration blocked quiet waits; stderr forwarding was not constrained to public records. Malformed zero-exit proof refusals also lost observations. | Existing reporter plus bounded first/last child capture. `lifecycle_process.py` observes one owned child/session, fixed live waits and source-owned progress/pointer records. Real child tests cover split live DRAIN, quiet work, output overflow, stdin backpressure, cancellation, ignoring descendants, callback/read-start failure and unexpected exceptions. |
| Source staging, eligibility and provenance | Optional preparation/loaded-input/native optimization fallbacks silently discarded their observed causes. Several generated programs reduced exceptions to binding flags before the caller could retain them. | Existing reporter is frozen into private generated calls, before reduction; recovered fallback remains successful on the ordinary full path. Source stage/upgrade/provenance tests retain existing eligibility and target-binding rules. No alternate operation is issued after ambiguous submission. |
| Reinstall, recovery, installed probes and pool authorization | Native systemctl, Node, Git, signing and admission failures were reduced to generic require codes after capture, or used DEVNULL. | Chained native causes preserve current public codes. `test_lifecycle_causal_probes.py` reads protected cause records; existing reinstall/pool/publication suites cover trust and classification. Expected missing Git object is recorded as recovered only after authenticated fetch succeeds. |
| Actual consumer publication process | Captured failure output was replaced by a public wire code at `_execute` and again at `main`. | Both layers retain the cause; actual process entrypoint loads the same source's existing reporter. Stdout remains the single safe JSON result; reporter failure has an independent stderr notice. Publication tests cover native nonzero, timeout, parser and reporter acquisition failure. |
| Generated owner Actions workflows | Token stdin and stdout stream errors could be overwritten by a later zero exit. | Sticky transport failure produces a failed job and truthful unknown summary; stream errors record bounded OS code, signal only the owned transport and await its real close. Generated workflow tests exercise both event orders and stream error. |

The coupled deployment inspection also covered `bounded_recovery`,
`clean_reinstall`, `install_recovery`, `partial_install_recovery`,
`pre_apply_recovery`, `intent_install`, `install_preflight`, `source_stage`,
`source_upgrade_general`, `source_upgrade_packages`, `installed_state`,
`pool_authorization`, `pool_eligibility`, `pool_migration`, retained
`serial_pool_installation`/`serial_pool_host`, `provenance`, and the changed
Ansible publication/identity/diagnostics/service templates. Expected absent
optional files and untrusted peer discovery stay refusals/skips under their
existing contracts. They do not import foreign source or create target authority.
This is concrete boundary inspection with regression evidence, not a claim of
production-host coverage or every possible unobserved host failure.

## Operator readback and live delivery

The supported read paths are documented in [deployment guidance](../../deploy/README.md).
A `protected-transport/relay-ansible-operation-…` reference resolves to the
original controller's private operation directory under its original temporary
root. A preconfiguration `existing-private-deployment-log` causal reference also
resolves under that temporary root; ordinary backend logs resolve under the
configured deployment log root. The original Unix owner or authorized host
administrator reads them. Raw spools/request data remain private, while public
output supplies a bounded phase, evidence pointer and inspection instruction.
Both early and late causes survive; unknown effects remain unknown.

Tests observe output **before releasing** quiet children and remote helpers.
Existing DRAIN inventory tests retain separate two-task completions, changing and
unchanged pending sets and unavailable inventory. New tests exercise the parent
and generated workflow delivery path, rather than inspecting only final text.
An elapsed wait is neither a percentage/ETA nor evidence of installed success.
No additional model calls or recurring service was introduced.

## Qualification and remaining boundaries

Final standard-check results are recorded below after the combined candidate run.
Unprivileged fixture tests exercise real Linux children, actual local/synthetic
SSH Ansible, private durable file readback, native failure injection and valid
receipts. This is isolated fixture qualification, with no shared TEST contour,
PROD credentials, external mutations or original incident replay. The worker is
UID 990 and cannot run root/sudo installed-runtime qualification. Native
exact-head CI must supply that separately; local checks do not qualify installed
sudo wrappers, host containment, real journal policy or service activation.

Validation uses a disposable ordinary-mode Git checkout and `TMPDIR=/tmp`,
`LC_ALL=C.UTF-8`, `umask 022`. The supplied shared checkout's tracked fixture
modes reject protected-config preflight, and its setgid/long temporary hierarchy
breaks native socket/progress fixture assumptions. Original source modes were
preserved. Python dependencies are confined to the ignored execution sandbox.
Root ownership/GID and filesystem ACL assumptions remain genuine worker limits;
no security check was relaxed to make them green.

The routine upstream check on 2026-11-17 identified official stable
[rust-v0.169.0](https://github.com/openai/codex/releases/tag/rust-v0.169.0), matching
the unchanged selected CLI dependency. No frozen guidance payload changes, CLI
bump, release, installation or activation is part of this source result.
Helpers used the requested `gpt-6.1-sol/high` profile for bounded implementation
and peer inspection; they provide implementation evidence, not independent
native acceptance. Actual model/effort telemetry is unavailable.

Task #244 remains open pending accepted integration, applicable native proof and
completion reconciliation. #248/#256 retain their distinct client live-text and
private projection obligations; this source does not activate either. Writer
publication and independent exact-head review are still required. Primary
native warning/annotation surfaces for this new result do not exist before
publication and were not accessible for final-head inspection here; no warning
absence is claimed. Prior immutable Outcomes and material evidence gaps remain.
