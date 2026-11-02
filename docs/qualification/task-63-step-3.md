# Task 63 Step 3: Git consumer publication recovery

Date: 2026-11-02. Accepted comparison: `b6edaaf4982df5b7dd6d56fd68b7ce7e34ccd7a9`.
Authority: [Task 63](https://github.com/jresearchsoftware/codex-relay/issues/63),
[diagnostic evidence](https://github.com/jresearchsoftware/codex-relay/issues/63#issuecomment-6583772562),
the [Step 3 Decision](https://github.com/jresearchsoftware/codex-relay/issues/63#issuecomment-6583905377),
the [manual continuity Decision](https://github.com/jresearchsoftware/codex-relay/issues/63#issuecomment-6584441512),
and the [preflight amendment](https://github.com/jresearchsoftware/codex-relay/issues/63#issuecomment-6584770902).
This is owner-authorized standalone manual Step 3. It has no native admission
or Writer Outcome; the retained native Step 2 projection remains unchanged.

## Read-only incident evidence

The installed product is the accepted comparison above. The desired private
configuration revision is `839b205a95690976b001935134c681d6ddf70dd1`.
Original operation `5f09cd11-11c0-427a-b9fa-db43692f635c` remains
`recovery-required`; its backend apply journal remains `RECOVERY_REQUIRED`.
No PROD recovery, installer, service, credential or ACL mutation was performed.
Both privileged lifecycle entrypoints remain ineligible as recorded by the
canonical incident evidence.

The authenticated compatibility reader returned 161 retained records. The
accepted classifier rejected these 21 manual records:

| Evidence class | Count | Candidate disposition |
| --- | ---: | --- |
| Writer admission refusal before authority resolution and handoff | 8 | Complete only with matching protected refusal and terminal native receipt |
| Completed manual results in accepted historical publication formats | 3 | Complete with their original protected receipt format |
| No terminal native Outcome | 10 | Unresolved; continue blocking consumer-digest changes |

Seven refusals have the current terminal body hash. The eighth, Task 103 run
38574568107, predates that copied field but has an exact `human-v1` native body
seal. [Writer comment 6169844603](https://github.com/jresearchsoftware/codex-relay/issues/103#issuecomment-6169844603)
matches that seal. Every refusal has matching envelope/record admission blocks,
null authority/branch/start head, and no handoff, submission or PR effect.

Task 74 run 37481335856 and Task 75 run 37494563487 retain the original v3
owner-authorization format: a five-field terminal manual Outcome plus the exact
authorization ID/hash, before body hashes and comment seals existed.
[Accepted publisher d11e7d6](https://github.com/jresearchsoftware/codex-relay/blob/d11e7d62dfcf663e665c99d99eea061eefa4a0d8/controller/src/publication-broker.mjs)
establishes that format. The current native authorization bodies and Writer
results were read back and matched their protected provenance.

Task 115 run 38389812008 retains the early direct-v3 submission digest/parent
and native body seal, before an unconditional `publishedResult` copy existed.
[Accepted publisher d3bdde7](https://github.com/jresearchsoftware/codex-relay/blob/d3bdde7a4d1d33eaa1b8601be9be084fc6316f98/controller/src/manual-outcome.mjs)
establishes that format. Native body SHA-256
`7094acaac2595fa47e4672a6777a4173217618e1263df8967b0b004e492218f0`
and canonical typed-result SHA-256
`acc2d69c2a6a25e1c8bb700ec360c9a4b08830dde77641d5d20e7c07b699d838`
match the original protected seals.

The ten unresolved original records remain:

| Original run | Task / Step |
| --- | --- |
| 37494098641 | Relay 75 / 1 |
| 37734406499 | Relay 84 / 3 |
| 38144146016 | Relay 115 / 1 |
| 38216521393 | Relay 115 / 2 |
| 38252046794 | Relay 115 / 3 |
| 38959797962 | Relay 85 / 2 |
| 39105109884 | Relay 141 / 11 |
| 39595014831 | Relay 169 / 3 |
| Withheld from public report | Other private consumer / 2 |
| 40175968131 | Relay 63 / 1 |

The private consumer's native identifiers remain in protected evidence. No
record has a terminal revocation/cancellation receipt. Some later Decisions
withdraw authority, describe no execution, or preserve known missing Outcomes;
these are not permission to fabricate terminal history. Task 141 also retains
ready-consumption uncertainty without a handoff receipt. Ordinary owner result
evidence for the oldest Task 75 phase does not manufacture a native Writer
completion. The correction preserves all ten barriers and their original
publication/authority boundaries.

Candidate helpers were evaluated only in memory against the authenticated PROD
inventory: all eleven proven completions/refusals are recognized, all ten
unresolved records remain, and previously complete manual records do not regress.
Before/after hashes of 168 relevant protected files matched; aggregate SHA-256:
`5ff7d28a7b3b94a11f15409fc54cc54842dbc3557069a550b53b850d345f0b1b`.
Candidate code was not installed in PROD.

## Original failure and bounded correction

The retained installation log proves the publication task failed with exit 1,
`CONSUMER_PUBLICATION_CONTROLLER_FAILED`, and zero stderr bytes, after 12.7
seconds. Its SHA-256 is
`1b92798f06c052c7592db261d0566f79dad0e26b09b1b582c8fe431682ae9019`.
The accepted publisher discarded child stderr; the log and relevant journal
window cannot recover its exact controller code. The retained manual inventory
is a reproducible sufficient precheck blocker, not a uniquely proven original
child cause. The current recovery-phase rejection is not evidence of the
original failure.

The classifier now recognizes the protected historical formats without editing
or backfilling records. V4 admission/result binding remains strict. Partial,
malformed and pending receipts remain unresolved. The publisher additionally
reports fixed-action/failure/exit metadata and only a complete bounded CLI error
envelope. Raw child streams, arguments and private paths are never published.
Post-replacement failures keep their recovery-required classification.

## Complete install-path classification

The preflight amendment applies to this same standalone Step 3. It does not
admit a new native execution, authorize another PROD attempt, activate the
retired public workflow or make Task 119 a prerequisite. The following owning
checks are classified across `intent_install.run` → `relay-deploy.run` →
`ansible/site.yml`; component validators remain their requirement owners.

| Surface | Before disruption | Final bounded revalidation / remaining dynamic proof |
| --- | --- | --- |
| Product/config authority and identity | Frozen commits, config blob/content, source tree, host identity, installed epoch/capabilities and selected strategy | Same local config bytes and clean exact product identity; staged tree and source receipt |
| Installed/foreign resource ownership | Inventory, selected-resource upgrade proof, protected roots, service identities, Nexus/listener boundary | Static old source/helper/config/unit bindings, service process identities and protected input metadata |
| Unix accounts and runtime paths | Existing UID/GID aliases, planned account/home/workgroup changes, active general transport restart barrier, runtime/tmp/arg0 and every runner/member destination | Same NSS/path/service observations; actual resulting UID/process isolation remains an installed runtime check |
| Retained attempt/publication compatibility | Real candidate admission reader against the authenticated old context; strict history check only for a changed consumer digest | Drain finishes before Writer mutex acquisition; actual current old consumer and history are rechecked under that mutex |
| Live consumer drift | Read-only private mount view authenticates old baseline from its protected original evidence; selected Git still exclusively supplies desired values | Existing bounded restoration runs only after preparation; final canonical consumer must require no restoration and match the proven old digest |
| Credentials and App access | Configured source or retained protected material, modes/ownership, real key parsing, existing App qualification and repository scope | Same material metadata and desired App qualification; no new grant or credential acquisition is invented |
| TLS and external ingress | Existing owning certificate/key validator, required ingress/Docker identity; fresh ACME inputs are distinguished from completed issuance | Future ACME issuance and live mTLS/listener proof are explicit dynamic steps, not a preflight PASS claim |
| Runner/workflow policy | Existing managed-pool App/runner/group/repository/workflow qualification before any SERIAL retirement | Rechecked under existing host/pool locks; exact old idle runner binding is rechecked by its owning transition before stop |
| Reviewer source, toolchain and build | Actual isolated source acquisition, full Git-tree validation, pinned Rust acquisition/reuse and real locked Cargo build | Sealed full release and toolchain, real Node import closure and Reviewer native loader; live consume performs no download/build |
| Runner and Codex distributions | Actual isolated download, archive/installer/layout/version qualification and sealed package trees | Both complete package seals and destination compatibility rechecked before live consume; no live Runner version probe that writes `_diag` |
| Existing target/partial release | Protected destination structure and all prospective copy collisions | Revalidated before candidate files are consumed; same-SHA preparation stays outside the active release |
| Pre-cutover race/abort | Original open gate and unchanged old installation captured as private disposable evidence | Actual Writer kernel holder plus old consumer/static/service/credential proof permits exact original gate restoration; no attempt or journal is rewritten |
| Replacement | Candidate staged outside the root that retirement archives; original retirement inventory/locks retained | A changed-consumer replacement is an explicit pre-cutover unsupported boundary; no late fresh-path gate rebind is attempted |
| Installed activation and effects | Only prerequisites can be certified | Real current pointer, installed manifest/Git pair, executable/PID, namespace/sudo/socket/timer/mTLS/runner readiness remain mandatory postchecks with the original operation's forward-recovery boundary |

No new dispatch/admission ledger or generic post-mutation rollback is introduced.
The original PROD operation and its ten unresolved terminal-history proofs
remain protected gates. Unknown old contexts, external changes that prevent
proof of old availability, and unsupported replacement rebindings return a
specific owner handoff instead of claiming safe automatic retry.

The publisher's protected same-UUID backup pair is tested after consumer rename,
including execution under the real Writer lease. This is distinct from full
installer recovery. If both the installed manifest and actual consumer already
describe the new digest while admission still binds the old digest, and the
bootstrap cannot authenticate its old context, the ordinary installer stops at
`CONSUMER_PREFLIGHT_BASELINE_GATE_MISMATCH` before further live effects. It does
not reinterpret the new snapshot as old authority. That frontier needs an
evidence-bound protected recovery of the original operation; this change does
not certify a generic automatic rollback/forward-recovery engine. The observed
PROD incident currently retains the old consumer digest and no publication
backup, so that separate post-rename fixture is not a claimed PROD diagnosis.

## Isolated Linux qualification

[The root/Linux qualifier](../../deploy/ansible/tests/test_git_consumer_history_recovery.py)
uses actual publisher, validator, admission CLI, protected publication stores,
journals and Writer flock in a fresh disposable filesystem namespace. Its
synthetic history has 140 completed automatic records/journals and the 21 manual
shapes above. It compares the accepted source, verifies unchanged history bytes
and inodes, preserves the ten unresolved barriers before backup/replacement,
checks same-digest Apply, and exercises a controlled failure after consumer
rename followed by real same-UUID transition recovery and idempotent replay.

Debian Linux root with Node 22.23.3 ran all four qualifier cases and all sixteen
[publisher tests](../../deploy/ansible/tests/test_publish_git_consumer.py)
successfully, with no skipped cases. The synthetic source receipt is explicitly
not a release/adoption claim. WSL Node 22.20.0 separately passed the targeted
controller/compatibility suites. The full candidate checks and exact-head CI
are recorded with the ordinary result and native PR checks.

This qualifies the affected real process/filesystem boundary. It does not claim
a live installation upgrade, privileged workflow dispatch, restored PROD
functionality or an end-to-end PROD cutover. Existing prepared TEST services and
repositories were not mutated. No new Task 119 recovery subsystem was added.

## Remaining protected boundary

Source review may assess this bounded correction independently. PROD still
requires owner-qualified reconciliation of the ten unresolved original records
and a separately qualified recovery/Apply of the retained operation after exact
source acceptance. Do not blind-retry installation, erase history, switch the
release pointer, force admission open or enable either lifecycle entrypoint.
Issue 63 remains open pending the remaining cutover and real operation proof.
