# DocReview execution failures and existing-work readiness

Task: [Relay #173](https://github.com/jresearchsoftware/codex-relay/issues/173).
Evidence inspected on October 23, 2026, for admitted manual Step 1,
`run-39941420253`. Baseline accepted source:
`9bd60b27e23b98a0bcb58eac4f18af84098192ce`.

## Findings and responsibility

The incidents have several causes. DocReview's active instructions teach an
older protocol than its currently installed service. One reproducible Relay
product defect prevents an admitted manual continuation from reporting against
an existing PR whose body correctly retains the previous attempt's provenance.
Other incidents concern collector filesystem access, historical Task authoring,
runner scheduling and a separate Windows process-lifecycle defect. An open Issue
or a green Actions run alone does not identify a failed implementation.

| Symptom | Proven cause and responsible layer | Smallest correction / boundary |
| --- | --- | --- |
| Fresh #329 initially follows v3 authoring and encounters `CURRENT_PROTOCOL_REQUIRED` | Consumer instructions and authoring select complete v3 Requests on an installation already accepting v4; the protocol gate is intentional | Teach current v4 direction and exact retained-attempt recovery separately; do not publish another v3 chain |
| #329 Step 1 terminates with `TRUSTED_GIT_FAILED / EACCES` | Trusted Outcome identifies worktree observation after contained execution; worker-created package group/access was the product collector investigation in Relay #171 | Accepted #172 contains the primary-work-group repair; source acceptance is distinct from the old attempt's recovery |
| #329 Step 2 `submit_manual_outcome` returns `PR_AUTHORITY_CHANGED` | Manual Writer requires this attempt's digest in the existing PR body, despite protected admission already binding that PR and CR; the body retains Step 1's digest | Bounded source correction in this PR; deployment and original-attempt publication remain separate owner operations |
| #321 Step 3 `PR_AUTHORITY_CHANGED` | Historical publication failed at `collect-progress`; expected/observed PR authority is not present in inspected public records | Preserve the blocked Outcome and successful later standalone result separately; do not infer the #329 cause from the shared error code |
| #327 `STEP_LABEL_MISSING` | Historical admission/projection stopped before worker start | Preserve the original blocked event; current v4 Writer owns allocation/projection |
| #327 and adjacent Windows CI timeouts/locks | DocReview Windows direct-child/descendant teardown, subsequently corrected and accepted | No Relay authority migration or replay is indicated |
| #321/#323 closure warnings | Live bodies use formatted prose rather than the parser's exact standalone closure field | Safe keep-open; owner completion/closure disposition, with no historical charter rewrite during recovery |

## Source, installed and consumer identities

DocReview live `main` is
`1c74132345b6ba4b6c9062221dab82879dd8bd5a`; its only open PR is #330 at
`4090552adb00be4d5d54f7c986f602323f72cc9c`, Draft. Relay accepted `main` and this
Task's starting head were `9bd60b27e23b98a0bcb58eac4f18af84098192ce`.

Read-only inspection through the existing owner server channel established:

- The installed artifact manifest and reviewed-source provenance both identify
  `9bd60b27e23b98a0bcb58eac4f18af84098192ce`; previous installed revision is
  `61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`.
- Controller source tree SHA-256:
  `10356e90db7da65c82b57e80ee1564652fba4c194435f6baa8eba54d3c1e3efe`.
  The installed manual Outcome module SHA-256 is
  `a9fdb8e0ce0ae5935804e027cdfdeb19db28cb8ea254d7dd5290ba4357119184`.
- The active Reviewer's running executable and installed binary both match the
  manifest SHA-256
  `34b390bd1dc3d057d934e0ffe7658f6c519f93796eebd7236e492bcb687d414f`.
  Current native authority and manual Outcome capabilities are enabled.
- One immutable consumer configuration allowlists Relay, DocReview,
  Shared Governance and Model Landscape. Both inspected admissions bind consumer
  digest `3e19e3aa1f2e0939b301143aca79d1b8ae8f311dae077b300ed2cc2d1c2d1500`.
  The installed default profile remains `gpt-6-astra/max`; Task-specific profile
  resolution can override it. An adopted source default is not an installed default.
- Both repositories' tracked routing manifests select `relay-workflows-v4` and
  repository-specific generated workflow hashes. DocReview routing selects its
  own repository and the general runner pool, as Relay does for itself. The
  difference in consumer repository identity/hashes is expected, not evidence
  of a different publication protocol. No runner/App/org settings were changed.

These observations establish the current installed pair, not which revision
served every earlier request. Historical #321 run logs identify
`2cb84b4d0bd4bcbfbd0aa7d686c14aeaf59eba4a / relay-workflows-v2`. DocReview's
methodology still describes that older installation and pins public guidance
`f77478a51e4aec5cee16174dc6f2be768ccae087`. Guidance, workflow ABI, installed
runtime and shared-policy adoption are four independently moving identities.

## #329: exact manual publication mismatch

The trusted [Step 2 handoff](https://github.com/jresearchsoftware/docs-evolution-review/pull/330#issuecomment-6315829422)
and protected Writer admission agree on:

| Binding | Value |
| --- | --- |
| Attempt / Step | `run-39599176190` / `2` |
| Target / branch | PR `330` / `codex/task-329` |
| Native CR | review `5599549918`, CR-329-001 |
| Reviewed / starting head | `702900148836aecba462b104a7001cebca742221` |
| Admitted `existing_pr` | `330` |
| Admission SHA-256 | `06def3ae49d0a4e30885fa30681626bc56cb7bc41d05468194afae7cec873e17` |
| Authority SHA-256 | `635a3662132c4f3a17d35b79d809134f5081319cb090eac5f1b085a24fdcf816` |
| Final published Git head | `4090552adb00be4d5d54f7c986f602323f72cc9c` |

The protected record confirms native admission, consumed command and projected
Step, with no manual submission, pending Outcome comment or terminal Outcome.
Its inspected SHA-256 is
`d9ea8c8fb6f5c830cbdc0033a8ba37c437e10f2d10cbd38e083b15ae7b562db5`.
The admission digest was recomputed using canonical sorted, two-space JSON and
matches the public handoff.

PR #330's body instead has its original `run-39556927198` provenance and
`Execution admission digest: 5ef68ff015cb9da4ff26b272877de35ba2b08f3830122fe1da32f16bac98e522`.
`publishManualOutcome` checks for the Step 2 digest before reserving claims; this
predicate is false. Its lifecycle callback repeats that same predicate. Changing
the result to the old digest would violate the protected admission; editing the
historical PR provenance is not a supported recovery.

This is a proven source-level mismatch from the actual protected admission and
live PR, reproduced in isolated tests. The original client error is recorded in
Task #173; inspected Reviewer/manual-service journal windows contain no retained
matching error event or original expected/observed diagnostic. Therefore the
original invocation's internal branch is not independently replayed or claimed
as a captured diagnostic. No manual Outcome submission for #329 was retried.

The correction uses the exact existing PR already bound by a v4 CR/continuation
admission, while preserving marker verification for newly created artifacts and
retained-v3 operations. It keeps native authority, repository, Task, branch/base,
head and unique-target checks, immutable claims, reservation/readback and Ready
ordering. Previous attempt text is preserved. Tests exercise publication and the
coupled lifecycle path; no historical record is migrated. This is an internal
correction to an already supported manual continuation, not a new recovery route.

## Existing open work: next permitted action

The live open Issue inventory contains exactly #321, #323 and #329. #327 is
closed and is evidence only. The assessment concerns current permitted actions,
not permission to perform them from Task #173.

| Task | Delivered result | Current next action and predictable gate |
| --- | --- | --- |
| #321 | A1 PR #322 and final A2 PR #325 independently approved and merged; final A2 head `13d98d3e1fe6bd762e748f3808b65df12b34ad9e`, merge `1c74132345b6ba4b6c9062221dab82879dd8bd5a` | Owner completion/closure disposition. No report reimplementation. Fresh execution currently lacks an active v4 Task-scoped purpose/scope Decision newer than v3 Request `6241480534`, so it predicts `CURRENT_PROTOCOL_REQUIRED`. Exact Step 3 recovery cannot turn later standalone work into its original successful Outcome. |
| #323 | Trusted implemented Outcome, exact-head approvals, green CI and merged PR #324; head `d0e10997c471fce5b64f7d37856004384a3269f5`, merge `785aa82883309d67784cfd2b7ee824c40175b7fc` | Only owner disposition of findings/closure; keep-open was intentional. No new execution is needed for the completed research. Genuinely new research needs current v4 direction, not reuse of v3 Request `6218671105`. |
| #329 | Step 1 work recovered into PR #330; Step 2 source correction published at `4090552…`; no Step 2 Writer Outcome | Original-attempt publication remains blocked by the proven manual binding defect under the current installation. Separately authorized deployment/recovery is needed; this Task does not authorize it. After supported publication, independent exact-head review is still required. A new admission is not a substitute for the missing result. |

#321's [closure Decision 6308541960](https://github.com/jresearchsoftware/docs-evolution-review/issues/321#issuecomment-6308541960)
was bound to temporary charter digest
`99e732ea4f1af4de056868c4b6deb1c324661cb6468306f954607cbfb4cc341f`.
[Owner diagnostic 6308585749](https://github.com/jresearchsoftware/docs-evolution-review/issues/321#issuecomment-6308585749)
records `AUTHORITY_RECORD_BINDING_MISMATCH` and restoration of original charter
`1e65616b0d297f3abbd36cc0c07af933e0234c431d85a902869ec388e1d19c6d`.
The Decision grants no current closure authority. It does not poison all future
resolution: current resolvers exclude Decisions bound to another charter.
Cross-charter supersession correctly fails; a separately authorized independent
current-v4 Decision against the restored charter can establish current direction
without superseding or rewriting the inapplicable record. No such operation was
performed here.

## Chronology: why Requests and Decisions exist

| Time (UTC) / native record | Schema and purpose |
| --- | --- |
| Oct 16 14:11, #321 Request [6217346418](https://github.com/jresearchsoftware/docs-evolution-review/issues/321#issuecomment-6217346418) | v3 Step 1 A1; successful Writer Outcome `6217746234`, approval `5549701393`, merged PR #322 |
| Oct 16 15:19, #323 Request [6218671105](https://github.com/jresearchsoftware/docs-evolution-review/issues/323#issuecomment-6218671105) | v3 Step 1 FPF study; successful Outcome `6218902241`, CI `38924672563`, approvals `5550653032/5550653650`, merged PR #324 |
| Oct 16 16:44, #321 Request [6220268080](https://github.com/jresearchsoftware/docs-evolution-review/issues/321#issuecomment-6220268080) | v3 Step 2 A2 successor; successful Outcome `6220471645`, deliberative owner hold retained |
| Oct 17 21:35, #321 Request [6241480534](https://github.com/jresearchsoftware/docs-evolution-review/issues/321#issuecomment-6241480534) | v3 Step 3 existing-PR report continuation; [run 39071783230](https://github.com/jresearchsoftware/docs-evolution-review/actions/runs/39071783230) blocked at publication; [Outcome 6241646129](https://github.com/jresearchsoftware/docs-evolution-review/pull/325#issuecomment-6241646129) preserves durable `4dbeaa5…` |
| Oct 19 14:40, #327 [Outcome 6269900244](https://github.com/jresearchsoftware/docs-evolution-review/issues/327#issuecomment-6269900244) | `STEP_LABEL_MISSING`, worker not started; Actions success does not negate the blocked result |
| Oct 19 15:01 / 16:01, #327 Request `6270345404` / CR `5574296364` | v3 Step 1 implementation succeeded; separate Windows CI failed; Step 2 CR addressed that source defect |
| Oct 20 08:48 / 08:49, #327 [Decision 6287159699](https://github.com/jresearchsoftware/docs-evolution-review/issues/327#issuecomment-6287159699) / [CR 5582812592](https://github.com/jresearchsoftware/docs-evolution-review/pull/328#pullrequestreview-5582812592) | v4 current direction/CR; CR itself allocated no Step. Cancelled routing runs with no executed steps are scheduling evidence, not repeated worker failures |
| Oct 20 12:18, Shared Governance source `99034dd…` | Shared 4.0.0 policy source becomes available; this does not install or qualify Relay v4 |
| Oct 20–21, #321 [owner authorization 6300515436](https://github.com/jresearchsoftware/docs-evolution-review/pull/325#issuecomment-6300515436), [manual result 6301037978](https://github.com/jresearchsoftware/docs-evolution-review/pull/325#issuecomment-6301037978) | Authorized standalone follow-up, independently approved `5595165711`, CI `39492272242`, merged; preserves the blocked original Writer record |
| Oct 21 05:08, #321 Decision `6308541960` | v3 closure amendment bound to temporary charter; inapplicable after restoration, not a valid completed-result migration |
| Oct 21 06:22 / 06:24 / 06:25, #329 `6309530308`, `6309559387`, `6309568978` | Initial v3 Request, profile/scope Decision, complete successor Request normalizing that Decision under the old authoring route |
| Oct 21 06:40, #329 [Decision 6309787719](https://github.com/jresearchsoftware/docs-evolution-review/issues/329#issuecomment-6309787719) | Current v4 purpose/scope direction newer than the latest v3 Request; enabled fresh v4 admission without rewriting those Requests |
| Oct 21 07:58, Relay PR #168 merge `72f74c77e6a95623352ff30a01e9782fc3a0db46` | Relay adopts Shared Governance 4.0.0 after those #329 publications; shared adoption is not the origin of native schema-v4 capability |
| Oct 21 12:21 / 12:24, #329 CR `5599549918` / handoff `6315829422` | Native v4 CR and Writer-assigned manual Step 2; source correction and CI succeeded, manual publication did not |

The dates disprove Issue age or shared-package version as a migration criterion.
The operations differ because their installed capability, selected authority and
original-attempt bindings differ.

The Windows failures in [run 39072147067](https://github.com/jresearchsoftware/docs-evolution-review/actions/runs/39072147067)
and PR #326's [run 39039314261](https://github.com/jresearchsoftware/docs-evolution-review/actions/runs/39039314261/job/117415378469)
(head `ffc72a4e62da7bd8e9ee534f12a85b1788b9dc14`)
and #327's [run 39275891404](https://github.com/jresearchsoftware/docs-evolution-review/actions/runs/39275891404)
are separate from Relay publication. Accepted PR #328 waits on the original
borrowed `Popen._handle` despite cached `returncode`; cached status could otherwise
skip direct-handle waiting while process rundown continued. Final CI
`39434660545` passed, including 60 Windows stress executions. PR #328 was merged
and #327 closed on October 20. Historical lock ownership was not instrumented;
do not claim that the exact process holding each old directory was proven.

## Consumer guidance and loading audit

DocReview `main`'s old Relay pin is valid for historical semantics. Applying it
universally to fresh current-v4 work is misleading. These are proposed downstream
corrections requiring DocReview authority; no DocReview files were changed:

| Active source at `1c741323…` | Exact correction |
| --- | --- |
| [AGENTS lines 99–110](https://github.com/jresearchsoftware/docs-evolution-review/blob/1c74132345b6ba4b6c9062221dab82879dd8bd5a/AGENTS.md#L99-L110), methodology lines 35–42, Issue template lines 16–24 | Replace universal complete-Request/successor normalization with current charter + trusted v4 Decisions/applicable CR + protected Writer admission; retain exact old-attempt and older-qualified-installation exceptions |
| [Methodology lines 73–79](https://github.com/jresearchsoftware/docs-evolution-review/blob/1c74132345b6ba4b6c9062221dab82879dd8bd5a/docs-evolution-poc/methodology/relay-consumer-methodology.md#L73-L79), PROJECT-RULES lines 388–405 | Writer assigns a new Step for genuinely new execution, including after BLOCKED; same-attempt replay/recovery retains Step. Do not prepare v4 labels through the old owner phase procedure |
| [PROJECT-RULES lines 414–416](https://github.com/jresearchsoftware/docs-evolution-review/blob/1c74132345b6ba4b6c9062221dab82879dd8bd5a/docs-evolution-poc/PROJECT-RULES.md#L414-L416) | Distinguish domain-blocked admitted attempts from `CURRENT_PROTOCOL_REQUIRED`, which precedes reservation/consumption/projection and does not fabricate a blocked Outcome |
| [GIT-REVIEW-WORKFLOW lines 13–16](https://github.com/jresearchsoftware/docs-evolution-review/blob/1c74132345b6ba4b6c9062221dab82879dd8bd5a/docs-evolution-poc/GIT-REVIEW-WORKFLOW.md#L13-L16) | Scope the owner-channel manual-publication statement to its actual historical/standalone contract; admitted manual sessions still require Writer. It currently contradicts PROJECT-RULES lines 466–472 |
| [Methodology lines 141–147](https://github.com/jresearchsoftware/docs-evolution-review/blob/1c74132345b6ba4b6c9062221dab82879dd8bd5a/docs-evolution-poc/methodology/relay-consumer-methodology.md#L141-L147), template, consumer tests lines 268–303 | Retain `task_complete` only for retained v3; current v4 completion uses canonical conditions plus `{hold,next}`. Update the focused tests that enforce old wording |

Reconcile coupled active naming, ChatGPT handoff and process-bundle references
in that downstream change; preserve historical prompts and accepted record bytes.
Tracked DocReview `main` has no VibeVM boot tree or repository Relay Skill slot.
Its AGENTS/Serena navigation routes to the older methodology. This proves a
repository guidance route, not what any earlier model actually loaded. Client
Skills, ChatGPT settings and historical session context are unverified.

The accepted Relay [compatibility reference](../../packages/codex-relay/skill/references/compatibility.md)
already documents the correct distinctions and on-demand v4 Decision path.
No shared Skill/assembly/publishing edits are needed for the proven runtime fix;
Task #174 owns that concurrent work. A later consumer update should select one
accepted compatible guidance revision and update its active examples together,
rather than adding a parallel authority ledger or repeated repair ritual.

## Prevention and qualification boundaries

For completed research, seek owner disposition without rerunning completed research.
In particular, #321's closure still needs qualified reconciliation; a new
Decision alone does not prove completion of its blocked original attempt.
For an exact old admitted result, preserve its selected Request/CR/Step and use
its supported publication/recovery path. For genuinely new work on a marked
Task with v3 Request history, the existing supported mechanism is a Task-scoped
v4 purpose/scope Decision newer than the latest v3 Request, plus a current v4 CR
when applicable. A profile/closure-only amendment is insufficient. Unmarked
Tasks require explicitly authorized migration; history is not mass-converted.

This preserves operator cost: one current-direction Decision when new work is
actually chosen; no blanket per-Task migration, new state registry, mandatory
compatibility probe or replacement PR. Automatic conversion is not selected:
it would need semantic owner choices that old records cannot supply. Rewriting
old records destroys their native hashes. A legacy fallback weakens current
protocol guarantees. Neither is justified by these incidents.

Current protocol diagnostics already identify the v4 correction; stale consumer
guidance must expose that path. The remaining observability limitation is that
generic `PR_AUTHORITY_CHANGED` does not explain which predicate failed. A bounded
categorical reason is preferable to publishing raw claims, protected paths or
request bodies; it must not create another authority or imply automatic retry.

The manual-binding regressions cover existing CR/Issue continuation provenance,
publication before Ready, exact replay and adversarial target/currentness cases.
Full source candidate checks accompany the final candidate. Native CI records
retain their reconstructible results; executor validation is not independent
acceptance or installed proof.

## Source validation

Validation ran in this attempt's independent native Debian/WSL checkout, with
Node 22.20.0, Cargo 1.90.0 and Python 3.11.2. The npm CLI was invoked with the
explicit Linux Node binary; no dependency installation was needed.

| Check | Observed result |
| --- | --- |
| Pre-fix existing-PR reproduction | Both automatic-to-manual CR and Issue-continuation cases failed `PR_AUTHORITY_CHANGED` at the digest predicate |
| Final focused manual/recovery suites | 83 passed, including 24 new existing-PR/lifecycle/replay cases |
| Complete `npm test` | 1200 passed, 4 skipped, 0 failed |
| Deployment/Ansible pytest | 1430 passed, 371 skipped, 19 dependency deprecation warnings |
| Cargo format and locked tests | Format passed; 159 tests passed |
| `scripts/qualify.py` | `THREE_CONSUMER_PASS`, real modules/handlers with isolated Git and loopback GitHub |
| Candidate scanner and staged/working diff checks | Passed; intended additions included in tracked scan |

Skipped platform/root cases are not installed filesystem, containment or host
qualification. The focused run rechecked the final small lifecycle diagnostic
preservation change; full qualification and scanning were repeated after that
change. Sequential GitHub reads remain observations rather than atomic CAS.
Native exact-head CI is retained on the result PR; it does not establish
independent acceptance.

## Warnings, limitations and next decision

- Task #173 routing [run 39941420253](https://github.com/jresearchsoftware/codex-relay/actions/runs/39941420253)
  has a native `Codex admission` warning: closure normalized/defaulted to
  keep-open. The charter's closure field is embedded in a bullet with explanatory
  prose rather than the parser's exact standalone field. Resolved keep-open
  agrees with owner intent and this Task's admitted binding; no closure is
  attempted. Preserve the warning for review and correct future authoring in
  the owning authority flow rather than editing this admitted charter.
- #330 exact-head evidence reader completed supported API acquisition at
  `4090552…`: both CI jobs passed; no supported execution warning was observed.
  The Ubuntu runner-image migration notice remains a platform notice. No
  exact-head Writer Outcome exists for Step 2, so that acquisition does not
  prove publication or complete the missing original-attempt warning evidence.
- UI-only GitHub service/pre-execution banners are outside supported automated
  completeness. Protected original error expected/observed details remain
  unavailable as described above. No absence claim is made for those surfaces.
- The accepted #327 review retained a local unchanged Node test warning:
  `late_spawned_descendant_cannot_escape_cleanup_gate` did not observe the
  expected PID count. This is an observation/test limitation, not proof of an
  escaped process; final native Windows CI passed. It remains separate from
  the demonstrated Windows teardown defect and Relay authority failures.
- Only bounded nonsecret server metadata was read. No deployment, credential,
  runner/App/org permission, DocReview source/Issue/PR or historical record was
  changed. Synthetic/local tests do not qualify an installed fix.
- The source correction and report need independent exact-head assessment.
  Material compatibility/methodology recommendations remain Deliberative owner
  choices before formal approval. Report acceptance does not adopt downstream
  recommendations or authorize deployment/recovery, merge or closure.

The proposed next owner choices are an independently reviewed product correction
and separately authorized installation/recovery, a DocReview-owned active
guidance reconciliation, and completion/closure disposition for the already
delivered #321/#323 results. Task #173 remains keep-open for that disposition.
