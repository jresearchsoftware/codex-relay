# Task 57, Step 3: measured evidence continuation

Date: 2026-11-13–14. Related to [Task 57](https://github.com/jresearchsoftware/codex-relay/issues/57) and [PR 246](https://github.com/jresearchsoftware/codex-relay/pull/246). This continues the [Step 1 inventory](task-57-step-1.md) and [Step 2 reconciliation](task-57-step-2.md). It records evidence and prepares owner decisions; it does not implement a product control change or authorize deployment recommendations.

**Result:** TEST reconstruction reached `reviewer-and-automatic` readiness and a subsequent ordinary reconciliation passed. Sanitized timings identify a fresh-install TLS-ordering defect and repeated-work costs. Unassisted fresh-install qualification, measured candidate improvement, production savings, PROD noninterference and independent native acceptance are not established. The [timing dataset](task-57-step-3-timings.json) preserves the bounded evidence.

## Identity and correction of the prior evidence statement

- Admitted attempt: `run-43507958608`, Task 57 / Step 3, manual route. Current trusted Decision: [6864949418](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6864949418). Starting result head: `ef11acce992258c2b302dc0c3a3780910a357d36`. Final published head, checks and the one canonical Writer Outcome are recorded in the PR/native publication records; this report does not predeclare them.
- Step 2 incorrectly attributed a general absence of sanitized timing evidence to an owner confirmation. That attribution is unsupported and must not be carried forward from either the report or the prior Outcome. The established fact is narrower: the inspected GitHub surfaces expose no task profile, and a sanitized historical host task extract was not obtained in that session. This does not prove that no historical host timing data exists.
- The owner subsequently clarified that TEST is a second Relay installation on the same server as PROD, authorized reconstructing/configuring that TEST installation, and supplied its dedicated deployment repository and second TEST consumer. The earlier missing-environment diagnosis did not establish that TEST was on a separate host or that the owner had to provide a profile.
- Helpers supply bounded evidence and configuration assessment. They do not provide independent native acceptance. Parent/helper actual runtime model and effort are **UNAVAILABLE** unless separately established by runtime evidence; requested profiles do not prove actual execution settings.
- Requested parent profile: `gpt-6.1-sol / xhigh / Subagents On`; historical-evidence helper effort `high`, validation helper `medium`; actual runtime profiles **UNAVAILABLE**. One startup title rename succeeded, but persisted readback was truncated to `Task 57 … security…`; this nonblocking UI limitation changes no admitted identity.

## Historical production evidence

The existing naturally authorized [run 43479023265 / job 132070376138](https://github.com/jresearchsoftware/codex-relay-deployment/actions/runs/43479023265/job/132070376138) was inspected through connected GitHub tools and read-only REST metadata. Attempt 1 contains one successful lifecycle job. The artifacts endpoint reports `total_count=0`; all 121 returned Actions log lines were available. No private raw historical host log, credential material or host-private configuration was read to obtain this evidence.

The log binds operation `f5360cf3-01b6-47ad-8b18-4920eff77ec3`, old product `93a48523ac0dc6310171ae39945497b83b017d8a`, target `5df7e0093d93c5a55b996e34cc83359da6b22a3e` and configuration `dc17d8b9f904f6536d9d76568b94514ffd5afe87`. It reports upgrade strategy, six ready pool members, same-operation verification and outer Git-pair proof. These observations describe that historical operation, not the present host.

| Clock boundaries, UTC on 2026-11-13 | Seconds | Meaning |
| --- | ---: | --- |
| Run created/started 18:04:31 → updated 18:16:53 | 742 | Independently retrieved run metadata; includes scheduling/setup/teardown boundaries. |
| Job started 18:04:35 → completed 18:16:53 | 738 | Job metadata interval. |
| First step command 18:04:36.7885481 → outer proof 18:16:49.6420684 | 732.854 | Displayed step-to-proof interval. |
| Wrapper's own deployment result | 715 | Wrapper-reported elapsed time; a different start boundary. |
| Source resolved 18:04:50.9078806 → prepared 18:06:46.9667985 | 116.059 | Preparation aggregate. |
| APPLY 18:07:17.4293670 → ACTIVATE/VERIFY 18:16:43.8330534 | 566.404 | Cutover aggregate, including backend and later pool work. |

The preparation interval contains a heartbeat at 18:06:18.1609485 reporting `backend-running;elapsed_seconds=30`. A later contiguous series, from 18:08:24.4195504 through 18:15:54.4757679, reports 30, 60, ..., 480 seconds. Thus at least **30 seconds of a preparation backend invocation** and at least **480 seconds of the main backend invocation** are directly supported. These are distinct invocations, giving a combined lower bound of 510 seconds in backend calls; they are not exact subprocess boundaries or exclusive task time.

[`run_backend`](../../deploy/relay-deploy.py#L183) starts a monotonic timer for one subprocess and prints while it remains running. Preparation uses the same wrapper, and the main backend is followed by pool reconciliation. Neither a missing heartbeat nor the final phase marker supplies an exact task end time. No role/APT/fact/Cargo/restart/retry breakdown follows from this series. The Actions log contains no task/role profile or separate post-check step.

The [Task 230 operator report](https://github.com/jresearchsoftware/codex-relay/issues/230#issuecomment-6853749103) separately reports 1,590 seconds Apply and 1,464 seconds post-check: 3,054 seconds combined. It explicitly identifies operator-reported protected-host evidence, including nonfatal Ansible temporary-directory warnings. It supplies no task profile and is neither a native Writer Outcome nor independent Reviewer approval. Its different operation and recovery/qualification context prevent using the newer run to claim a measured reduction from 3,054 seconds.

The historical Actions result names a private installer log. A subsequent read-only metadata check found one matching retained upgrade log, 2,317,796 bytes, modified at the historical APPLY end boundary. No file with `profile` or `timing` in its name was found in that one known lifecycle-log directory. This establishes retention of a log, not timestamp coverage or absence of timing data elsewhere. No log contents were read. The existing [profiling helper](../../deploy/ansible/tests/profile_qualification.py) counts boundaries but explicitly lacks task wall times, and also runs a local mutation experiment. It cannot retrospectively manufacture a deployment profile and was not invoked as a supposed passive PROD reader.

## Claimed TEST reconstruction and configuration

The parent execution verified that both old TEST installation namespaces were missing and acquired the shared TEST claim for this admitted attempt. The dedicated TEST deployment configuration and consumer repositories are:

- [codex-relay-deployment-testbed](https://github.com/jresearchsoftware/codex-relay-deployment-testbed)
- [codex-relay-testbed](https://github.com/jresearchsoftware/codex-relay-testbed)
- [codex-relay-testbed-2](https://github.com/jresearchsoftware/codex-relay-testbed-2)

The TEST fixture was updated and pushed without force at `89babb3078d15b24122cbd1673af8feb292e2fec`. Its limited configuration change selects accepted product `5df7e0093d93c5a55b996e34cc83359da6b22a3e` and adds the second TEST consumer to both Writer and Reviewer target lists. Namespace, accounts, port, dedicated Apps, key references, physical TEST pool and protected PROD boundaries retain their distinct identities. No secret values are included in this report.

A separate bounded helper assessed the full configuration and exact diff; schema validation and whitespace validation passed. No defect was found in those changes. This is config evidence, not a native acceptance verdict or proof of all external App permissions. One pooled installation serving both TEST consumers is supported. Its direct eligibility map covers both targets, avoiding a dependency on an absent second installation's protected peer proof. Capacity remains two physical TEST runners across the eligible repositories.

The parent verified the dedicated TEST Admin App identity and organization permission, and the General Runner group's selected-repository/trusted-workflow restrictions for the three TEST repositories. The separate TEST Production Runner group selects its one TEST repository and has restricted workflows with an empty workflow list: it denies workload execution rather than granting broad access. Only its registration was restored; no group/ACL expansion is claimed or performed by this configuration change.

The public installer was first exercised against the unchanged clean fixture. It accepted the frozen inputs and stopped for the missing fresh TEST Production Runner registration token, reporting `hostMutation=false`. This is a demonstrated external prerequisite, not a successful installation. The continuation uses the existing dedicated TEST Admin authorization on the target; ephemeral registration material stays in driver memory/stdin and is not written to argv, logs or this report.

The first workstation-controlled SSH installation was deliberately interrupted after 806.13 seconds (process-start to observed exit, at most one second polling uncertainty). It had not completed; its timing records are a censored sample, not an Apply success baseline. The public local continuation refused the retained partial state through its recovery barrier. The execution then recreated only the disposable TEST state under its existing claim, preserving the same marker inode, exact source/configuration, timing evidence and prepared Rust toolchain. This was a TEST reconstruction, not qualification of original-operation recovery. The subsequent fresh installation uses an on-server local controller and the original protected Git-pair receipt; no new Task or admitted Codex execution was created. Completed installation, reconciliation and handback evidence follows.

This is a same-server TEST installation. Shared APT cache activity, systemd manager daemon-reload and shared nginx reload occurred during the authorized TEST reconstruction/completion. Namespacing does not make those effects private to TEST. No PROD install, recovery or benchmark-only Apply is authorized by this report.

The assisted fresh continuation passed in **1,146.441414 seconds**. Its readiness Apply reported **630 seconds**, including a **460.605789-second / 1,753-record** main backend. The final active-runtime post-check reported **383 seconds**; its site callback measured **380.019630 seconds / 1,728 records**. Pool proof reported two ready members and no draining members. The protected manifest reached `installationState.stage=ready` at the frozen `5df7e009… / 89babb30…` pair; Reviewer, Production Runner and both General Runner services were active.

Read-only connected TEST Reviewer calls succeeded against testbed PR 97 at `30ffc1e34c84251cc66913c63e1d7d12074b4744` and testbed-2 PR 8 at `f42fc6e9b5d64475cae59f277912b7ea8742ad64`, through the configured App/mTLS route. They prove access to both configured repositories, not a new review verdict or a fresh Codex execution.

The existing configuration-repository README still described Task 63 ownership and an obsolete candidate. Its substantive runbook correction removes that competing ownership claim and documents the current two-consumer topology and existing public installation/projection routes. This produced configuration commit `36da91eb94ac5ea54ea2f52aa97c97df741aecbc`; the deployment JSON bytes and Git blob are unchanged. Applying that real documentation update selected ordinary `strategy=reconcile, phase=apply`, rather than `verify`. It passed in **625.592080 seconds**, with **613 CLI seconds** and a **424.281199-second / 1,756-record** main site. Final readback established product `5df7e009…` and configuration `36da91eb…`, no incomplete fresh-install state and four active TEST services. Both General Runner PID/start identities were preserved; TEST Reviewer and Production Runner were restarted. This does not establish that all restarts were necessary or all unchanged-content installs are no-ops.

**PROD noninterference is not proved.** PROD Reviewer was active at final readback, but its PID/start identity differed from the pre-TEST-activation snapshot. Read-only system-manager metadata records a restart at **2026-11-13 22:26:28.513250 UTC**, before the README reconciliation. The cause is unresolved; no attribution to TEST, shared ingress or another actor is made. The claim was safely released at **2026-11-13 23:04:07.944533 UTC** for the same holder, with subsequent `FREE` readback and four TEST services active. The dataset's `claim_release` receipt records this handback; no further TEST use followed the release.

## Timing method and completed measurements

A private controller-only PATH shim enables an aggregate Ansible callback after the backend recreates its environment. Product source and the default stdout/proof callback remain unchanged. The shim adds no task skips, fake results or altered success criteria. Evidence records are restricted to safe timings, task/role identifiers and outcome/skip/retry counters; task arguments, environment, result payloads, credential bytes and private paths are excluded.

The initial root-local composition failed after **1,096.464482 seconds**. Its inactive bootstrap passed and reported **1,012 seconds**, including a **442.946347-second / 1,734-record** mutating site pass and a **350.567545-second / 1,724-record** internal clean post-check. These are completed backend measurements inside an unsuccessful complete composition, not a successful end-to-end installation baseline. The later readiness Apply is measured separately after the following diagnosed prerequisite failure.

### Demonstrated fresh-install TLS ordering defect

After bootstrap, Reviewer/Writer/Codex credential staging passed (four seconds each) and CA preparation passed (six seconds). The next Apply preflight refused `HOST_TLS_ISSUANCE_STAGE_REQUIRED` before its cutover. This matches the accepted source's composition: [`fresh_completion`](../../deploy/intent_install.py#L326) schedules ACME dry-run/issuance, but the [scheduler](../../deploy/intent_install.py#L649) places them after readiness Apply. Bootstrap has already established an installed SHA, so the [host preflight](../../deploy/host_preflight.py#L668) correctly refuses a missing certificate on that apparently existing installation.

This is a pre-existing baseline contract defect exposed by this TEST execution; the introducing change is undetermined. It violates the existing [product-managed first-install ACME contract](../../deploy/README.md#first-install-bootstrap-and-reusable-state), rather than proving a need for another owner-supplied certificate or a weaker TLS control. The [mocked composition test](../../deploy/tests/test_intent_install.py#L501) asserts the problematic ordering without executing that coupled host preflight. Separate preflight tests do not cover bootstrap-to-second-Apply composition.

The execution retained the gate and used the existing public `tls-dry-run` and `tls-issue` commands within claimed TEST; both passed, reporting 14 and 15 seconds respectively. Fresh continuation then reached Apply. This assisted route does not qualify unassisted ordinary fresh installation. The smallest source follow-up moves those existing issuance phases after inactive bootstrap, credential staging and CA preparation, before readiness Apply; retain existing installation TLS refusal, final TLS validation, guards, pending markers and activation/pool/final-check proofs. No product fix is implemented in this audit.

Each invocation needs its own start/end identity. Callback task elapsed time must be labelled according to its observed boundaries, including include, handler, retry and failure handling; it must not silently become exclusive CPU or module time. Gaps between backend calls remain part of total elapsed cost.

| TEST evidence | Result and limit |
| --- | --- |
| Installation/readback | Assisted readiness and final current pair verified; unassisted ACME ordering fails. |
| Pool/handback | Two ready members; four active services; exact claim released, subsequent `FREE`. |
| Apply/post-check | Completed callback/operation timings retained in the dataset. |
| Attribution | Cold staged Reviewer build 82.897110 seconds; sealed artifact consumption in main, no main rebuild; all 32 routes traversed for capacity two. |
| Failure/recovery | Interrupted SSH sample censored; public recovery barrier retained; disposable reset is not original-operation recovery proof. |
| Comparison/target | No candidate implementation or measured savings; observed removed-work costs only bound proposed opportunities. |
| Shared-host limit | PROD restart observed, cause unresolved; no noninterference claim. |

Bootstrap's mutating site recorded 34 APT calls / **22.309371 seconds**; its 31 duplicate Bubblewrap calls cost **19.870010 seconds**. Other aggregates were repository ancestor inspection 64 / 25.815091 seconds and reconciliation 64 / 27.080230; General fixed sudoers 32 / 25.797562; common-plus-private slot parents 31 / 25.052661; physical Runner packages 2 / 23.770585. These include useful work and overlap role accounting; their whole totals are not removable cost. APT is not the dominant explanation. Reconstruction, steady-state Apply, qualification and callback/controller overhead remain separately labelled.

## Prioritized executable follow-up candidates

These are recommendations for subsequent canonical authorization, not changes implemented or new obligations established by this report.

1. **Repair the demonstrated ACME composition defect.** Reorder existing issuance before readiness Apply in `intent_install.py`. Couple the real host preflight to the composition test; retain existing-install missing/partial certificate refusal, issuance-failure stops, same-pair interrupted continuation and final ready-state proof. This repairs an existing supported first-install promise; it does not weaken TLS validation or add an owner prerequisite.
2. **Hoist proven shared work while retaining every fixed route.** In the owning site/slot tasks, install Bubblewrap once; reconcile unique managed-pool groups and the three common slot-parent directories once. In launcher repository-root reconciliation, deduplicate identical fixed ancestors within each slot. Keep all 32 route IDs, every slot-private path, credential destination/copy checks, launcher/sudoers bytes, namespace probe, retained descendants and final proof. Preserve direct-role/legacy and management-disabled/retained-continuation behavior. The 31 duplicate APT calls alone cost **19.870010 seconds** in the completed 442.946347-second bootstrap site pass: **4.49%**, a bounded gross opportunity, not a measured candidate saving or the principal explanation. Shared groups, common parents and repeated ancestors provide additional separately measured opportunities; do not sum overlapping categories.
3. **Assess one redundant full traversal inside ordinary fresh composition.** The intermediate internal clean post-check cost **350.567545 seconds** in this sample. Determine whether existing inactive-artifact/manifest readback supplies sufficient proof before credential staging, allowing that specific full traversal to be omitted while retaining the final post-check after all actual changes. Preserve expert bootstrap/reinstall behavior. The candidate must prove that an earlier defect cannot become a ready result or expose credentials through an invalid namespace. This is a distinct proof-equivalence question, not permission to remove a check globally.
4. **Assess README-only configuration provenance reconciliation.** The real documentation commit selected a full 625.592080-second reconciliation despite identical deployment JSON bytes/blob; its main site cost 424.281199 seconds. Determine whether the existing verified installed/configuration evidence can prove unchanged effective intent and update only the current Git provenance, retaining source/consumer/pair binding, changed-config refusal, live readiness, locks and recovery rules. Do not skip necessary drift detection or invent a second provenance ledger. This observed path suggests a concrete opportunity, not a measured candidate saving or proof that every restart was redundant.

For the equivalent-work candidate, verify exact call-count reductions and bytes/UID/GID/mode equivalence for capacity 1, 2 and 32. Exercise missing Bubblewrap and APT failure before probes, disabled management, credential symlink/hard-link/mode/owner/size cases, repository-parent aliases and untouched retained work. For the fresh-schedule candidate, exercise failures after bootstrap, during credentials/issuance, Apply, activation and pool reconciliation; keep changed-pair, lost-lock and unknown-effect refusals and same-pair recovery. Reuse existing tests and required candidate validation rather than adding a new registry, cache, gate or operator command.

Compare baseline and candidate using the same exact input pair, capacity, toolchain, cache/build condition and timing method. Record total elapsed time and removed invocation cost separately; choose a seconds target from that measured cost and variance. The observed 19.87-second and 350.57-second costs bound concrete opportunities but do not establish an end-to-end SLA. Preserve no-op/code-only/config-only/combined and failure/recovery behavior; unchanged Reviewer source must retain its content-keyed reuse proof.

Ordinary upgrade already omits the bootstrap-only extra `--check` traversal. Keep the same-operation backend, pool, loaded-process and outer Git-pair success proof. [Task 25](https://github.com/jresearchsoftware/codex-relay/issues/25) already rejects ceremonial duplicate pre/post checks; a separately requested later drift/recovery qualification remains legitimate. This audit neither reopens Task 25 nor declares every historical post-check redundant.

## Warnings, validation and handoff

Historical lifecycle check `132070376138` returned zero annotations, and its available Actions log contained no warning/error lines. This observation covers only those inspected GitHub surfaces. It does not negate Task 230's reported warnings or establish absence of host-private/UI-only warnings. Sanitized extraction inspected 15 TEST logs, with no oversized files omitted, and found **nine runner temporary-directory fallback warning lines**, zero foreign-unit audit warnings. Raw warning messages/paths were not exported. These warnings, assisted TLS boundary and unresolved PROD restart remain visible decision inputs. Final exact-head warning disposition belongs to the native review evidence.

Fresh full local checks at the unchanged starting executable head were reported by the parent execution as follows. They are separate from installed TEST qualification and independent native review.

| Check | Starting-head evidence |
| --- | --- |
| `npm test` | 1,168 passed, 7 skipped; no failures. |
| Python deployment/Ansible suites | 1,965 passed, 808 skipped; 467.41 seconds; passlib/`crypt` deprecation warning. |
| `cargo fmt --check` | PASS. |
| Locked Rust tests | 159 passed; no failures. |
| `scripts/qualify.py` | `THREE_CONSUMER_PASS`. |
| Candidate scanner and whitespace | PASS at starting executable head; final report checks are recorded in native validation evidence. |

The `crypt` warning remains visible dependency debt, not a passing Python 3.13 compatibility claim. Skipped host/root-only checks supply no installed proof. Final Markdown/link/scanner/whitespace validation, native checks, exact published head and the canonical Outcome belong to their PR/Writer records, without an invented result here. Native independent assessment remains a separate acceptance boundary. No merge, release or Issue closure is claimed.
