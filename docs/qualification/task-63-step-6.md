# Task 63 Step 6: Consumer transition and exact partial continuation

Date: 2026-11-04. Authority: the owner Step 6 direction in
[Task 63](https://github.com/jresearchsoftware/codex-relay/issues/63), including
the standing standalone/manual and pre-disruption Decisions. The starting
accepted `main` is `97a04f9bfe1a7f05015ea02fd8407e591722c8dd` (PR #198).
This is standalone source/TEST work, without native execution admission or a
Writer Outcome. Task 63 and private Deployment Task 2 remain open.

## Cause and correction

The original composite reader launched a fresh original Node process for every
historical envelope. Repeated inventory/classification paths repeated that
work, and native Task evidence performed sequential independent reads and
repeated immutable actor/authentication acquisition. The publisher's old
60-second deadline could expire after the durable consumer rename.

Original envelope validation now runs in bounded batches (256 envelopes and
2 MiB maximum per batch, with the existing individual envelope limit). One
composite inventory and exact-record disposition promises are reused within a
single locked action. Repository tokens and immutable actor identities are
reused within that action, and independent evidence reads run concurrently.
The next command rereads Task/closure/reopen/authority evidence. This does not
introduce an offline disposition, a persistent freshness exemption or a new
Task authority cache.

Opt-in diagnostics expose only fixed numeric timing/call counters. Ordinary
CLI error JSON remains unchanged. The publisher retains bounded failure codes
and kills/reaps the transition process group, including original-reader
descendants. Its observation ceiling is now 180 seconds, consistent with
preflight; the measured optimization, rather than that ceiling, addresses the
failure.

## Focused process/filesystem regression

Linux uses Node 22.20.0, Python 3.11.2 and Rust/Cargo 1.90.0. The real original
reader and protected SERIAL/current stores run inside private mount/network/PID
namespaces with 161 records: 140 completed automatic, 11 completed/refused
manual and ten historical missing-receipt records.

The unoptimized all-original fixture took 117.39 seconds overall. The mixed
fixture with 400 ms latency on each native evidence read reached the original
60-second post-rename deadline. Corrected final regression measurements:

| Fixture | Before-rename check | After-rename transition |
| --- | ---: | ---: |
| 161 original records | 1.654 s | 1.639 s |
| Mixed original/current, 400 ms native latency | 6.189 s | 5.717 s |

The corrected action made six original-reader calls and one composite inventory,
instead of launching a reader per envelope. Both fixtures preserve every
original history byte and inode. The mixed fixture cancels after rename,
refuses newly reopened native Task evidence, then completes the same operation
after that explicit fixture condition is removed. Separate regressions prove
descendant cancellation prevents a delayed child effect, actor reuse does not
hide a reopened Task, other-consumer boundaries remain enforced, and changed
backup/config/pair/backend/gate/operation/archive/runtime evidence refuses.

## Exact continuation contract

The public installer accepts `--continue-install-recovery` together with the
existing explicit recovery authorization, original operation and retained-target
flags. It proves only the reported frontier: desired release/consumer already
installed, applying old-or-desired-digest gate, same reserved receipt, unchanged
original backend, authentic backup/staging bytes and the original Reviewer
executable still running. Controller acceptance is independent of the frozen
final product/config pair. PROD requires the corrected controller in accepted
public main; the original protected TEST receipt permits exact candidate proof.

Completed release/artifact/prerequisite installation is skipped. The existing
controller reconciliation and complete installation/runtime tail finish the
remaining work. Complete runtime/service/Git-pair proof precedes byte-exact
original backend archival, continuation completion and admission resume.
An advanced runtime, equal old/new executable without configuration-reload proof,
or partial archival receives a precise refusal. These narrower boundaries
deliberately leave generic recovery architecture to Task 119.

## Real isolated TEST failure and completion

The existing namespaced Debian TEST installation used the real Writer App,
native Task reads, installed service identities, shared runner transport and
the ordinary public installer. The desired pair remained product
`97a04f9bfe1a7f05015ea02fd8407e591722c8dd` plus disposable private TEST config
`57338d6730c2f6bbfe4bf2ff45c958414285019a`. Candidate controller
`0d16e3cdd44e8178ccb497d16de99872a49ec863` was independently identified; the
retained original target remained `b6edaaf4982df5b7dd6d56fd68b7ce7e34ccd7a9`.

The 161-record history combines four preserved earlier TEST records with
explicit synthetic historical envelopes. They do not claim genuine native
execution admission or model calls. A watchdog stopped only the exact isolated
TEST transition child after consumer rename. The original publisher reached its
real deadline and reported `CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY`;
the Ansible publication task took 78.14 seconds. Readback proved the reported
partial shape: desired disk release/consumer, applying old digest, reserved
receipt, unchanged unarchived original backend and old running Reviewer.

An altered synthetic publication record refused with a bounded
`ADMISSION_ATTEMPT_INVALID` diagnostic; restoring its exact original bytes
restored all 161 hashes/devices/inodes. The first positive continuation completed
the digest but caught a missing Ansible deployment-snapshot input before any
Reviewer restart. That input was corrected using the same frozen configuration;
fresh proof accepted the already-advanced digest and unchanged old runtime.
The same operation then completed in 458.73 seconds, including the existing
full runtime/slot/service validation tail. No completed release or artifact
installation was repeated, and the frozen product/config pair was unchanged.

Independent readback proved all 161 original history bytes/devices/inodes,
`complete` continuation, byte-exact original backend archive with no active
backend name, open admission with the desired digest, the desired Reviewer
executable in a replaced process, and the standard service/transport proof.
The final tail log SHA-256 is
`d81d77e1bb97bfee0c9c9418886d981a6b4f92d0064b3f4af4501c2dacde504d`.
Private raw logs remain in the protected TEST sandbox. This used the supported
owner-checkout route with an exact TEST Git receipt; it is not a new private
workflow dispatch or PROD recovery proof. Earlier accepted workflow,
credential, bootstrap and external-policy evidence is reused.

## Validation and limitations

The complete Linux Node suite passed in complementary root/ordinary runs:
1,289 passed with five conditional skips, and 1,287 passed with seven skips
(1,294 total cases). Rust formatting and all 159 locked tests passed.
Three-consumer qualification passed.

The full deployment/Ansible run produced 2,324 passes, three failures, nine
fixture errors and 11 conditional skips. The missing exact historical Git object
was acquired and all nine affected original-reader cases passed. The three
failures were corrected (opt-in diagnostic ABI and two explicit continuation
role expectations); the 55-case correction set passed. Final 161-record,
partial-frontier and real artifact-stage checks passed 32 cases; the additional
old-or-already-advanced gate-digest set passed all 13 cases separately. Ordinary
UID checks passed 31 cases. This records the full run and targeted corrections
honestly, rather than claiming a nonexistent single green full run. Two
Docker/systemd cases were not executed; accepted earlier unrelated qualification
is reused. Existing Python/Jinja deprecation warnings do not change runtime
behavior. Final candidate checks and native CI belong to the PR's exact head.

No PROD installation, retry, repair, service/config/credential mutation,
runner-policy change, source merge, release or Issue closure is performed.
No private PROD UUID, path or configuration is copied into this report.
After independent acceptance and source merge, the next separately authorized
private Deployment Task 2 operation must first reread its exact retained evidence
and old running executable, then use this continuation with the original frozen
pair. An unsupported/advanced frontier must stop without a blind full Apply.
