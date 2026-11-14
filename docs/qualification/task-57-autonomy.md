# Task 57 engineering-autonomy qualification

This finite implementation record covers Task 57 Step 6, attempt
`run-43636144216`, from accepted source
`cfeb633c86408327bf9941a5dfaaa41f98706ac1`. The stable charter and trusted
Decision [6883528168](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6883528168)
adopt the [R1–R8 / D1–D6 plan](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6876030665).
Accepted source guidance remained frozen while candidate instructions were
regenerated. The exact final result belongs to the canonical Writer Outcome;
this report is implementation evidence, not independent acceptance.

## Required outcomes

| Outcome | Result and representative evidence |
| --- | --- |
| R1: ordinary Git work and truthful attribution | Normal merge graphs, amend/cherry-pick/rebase organization of unpublished work and original authorship are supported. Publication preserves the admitted frontier, exact task ref and non-force boundary. Every introduced reachable commit/tree/blob is scanned, including transient side-branch content absent from the final tree. See [Git autonomy tests](../../controller/test/git-autonomy.test.mjs) and [integration tests](../../controller/test/integration-reconciliation.test.mjs). |
| R2: main advancement | Verified descendant base movement is integration context; replaced/unrelated history, changed repository/base branch and movement of the task's own head remain rejected. Historical admitted input remains immutable. API list/detail races no longer treat base SHA movement as a different artifact. |
| R3: preserved candidates | Trusted import acquires only the missing reachable object closure, supports loose/packed refs and indexed packs, and never executes Git against worker metadata. A safely collected candidate survives inaccessible or unsafe unrelated residue with an explicit unknown worktree state. Cross-UID [generated package](../../controller/test/generated-package-collection.test.mjs), [private source](../../controller/test/privileged-collection.test.mjs) and [observation](../../controller/test/worktree-observation.test.mjs) tests preserve private bytes and modes. |
| R4: continuation and meaningful results | Unchanged authority needs no repetitive technical-continuation Decision. Fresh authenticated launch, new Step, native lineage, holds and unknown-effect reconciliation remain mandatory. Automatic/manual exact-head no-change remediation needs no cosmetic commit. Draft results can receive substantive CR findings; approval remains distinct and requires Ready. See [continuation](../../controller/test/blocked-cr-continuation.test.mjs), [no-change](../../controller/test/task-authority.test.mjs) and Reviewer tests. |
| R5: completion, resources and diagnostics | A contained cleanup failure retains the semantic result with a visible warning. Complete safe terminal evidence is archived through the existing primary diagnostic store before active capacity retires, including known pre-runtime failures. Retained resources are not deleted. Unknown child/cleanup, failed persistence and missing archive receipts remain protected. [Durability tests](../../runtime/test/durability.test.mjs) exceed eight successive failures without increasing capacity. |
| R6: native bindings | Exact Task/admission/PR/head and later native results govern identity. PR presentation is repaired or warned, without rewinding owner-maintained Issue numbering or replacing a later admission. Informational links and `steps-to-reproduce` do not create extra authority. Node and Rust agree on compatibility relationship grammar and current-v4 Unicode schema units; retained legacy executable-CR byte limits remain unchanged. |
| R7: bounded output and diagnostics | JSONL streams have separate record/result/diagnostic bounds; a long valid stream retains its late result and errors. Geometric buffers avoid per-fragment memory growth. Malformed raw records are rejected before forwarding; decoded values and property names are redacted. Unicode limits count codepoints while transport bytes remain independently bounded. Worker failure/validation context is retained with explicit clipping. Paginated authority/evidence scans reach relevant late records under declared work/byte/request/time bounds. |
| R8: instructions and tools | Automatic instructions grant ordinary task-owned methods while keeping credentials/publication separate. Manual and standalone routes retain their own authority. Fixed cc/c++/awk aliases point only into existing read-only `/usr`; OpenSSL uses neutral task-local configuration. The actual runtime budget is disclosed. Scrubbed automatic execution retains its 90-minute worker budget and 100-minute outer deadline; direct trusted runtime callers retain bounded overrides without forwarding controller environment settings. |

## Delegated investigations

| Investigation | Disposition |
| --- | --- |
| D1: Reviewer pre-send timeout | Confirmed and corrected. Cancellation before decisive sending refunds the reservation; cancellation after sending may begin retains reserved unknown-effect recovery. Four loopback HTTP fault cases exercise both sides through the actual current typed PR-review and Task-Decision handlers; identical retries recover exactly one decisive effect. |
| D2: correction and preservation | Direct support for legitimate histories and safe candidates removes the demonstrated false rejections. No fallback linearizer, transformed SHA, extra worker call or recovery service was added. A new execution retains its genuine identity. |
| D3: result after owner edits | Retained the existing exact current Writer-result requirement. Author strings cannot authenticate owner edits or supply an attributable current result. A changed head still needs a fresh bound result and independent exact-head assessment. No general bypass was added. |
| D4: representation and limits | A positive history beyond 128 commits demonstrates replacement of the arbitrary commit count with actual bounded graph/object/byte work. Marker-only PEM documentation no longer fails scanning; actual, partial and wrapped private-key material remains rejected. Published symlinks/gitlinks remain conditionally unsupported: safe internal targets need platform-aware target-graph validation, and external Git metadata remains outside the trusted import boundary. These optional representation extensions were not needed for R1–R8. |
| D5: tools and budgets | Real Bubblewrap execution compiled C through cc, ran awk and generated an OpenSSL CSR. Fixed aliases and neutral config avoid exposing host configuration/includes. Automatic runtime/outer duration remains 90/100 minutes; controller environment overrides are not forwarded and cannot shorten that outer default. Direct trusted runtime overrides remain bounded, with caller-owned outer deadlines. The owner-local smoke retains its separate two-minute bound. |
| D6: packaging | Compatible additive workflow guidance is MINOR 6.1.0. Existing source-tree hashes bind the actual owning contracts, with accepted baseline provenance; clean generation does not need an unmerged branch commit that squash integration might omit. Native/standalone artifacts, registry, slot, lock, boot and actual project Skill projection were regenerated. Frozen 6.0.0 registry bytes were preserved. |

## Validation and environment

The final full Node suite passed: **1,234 passed, five explicit skips**. The
three permission scenarios skipped as root were also exercised under UID 65534
with all five residue tests passing. Controller archive integration passed 62
focused durability tests. Final deployment and installed-proof counts belong
to the canonical Outcome. Rust formatting and **174 Rust tests** passed. Guidance generation and self-adoption tests passed,
as did hash-pinned VibeVM 1.0.11 native self-adoption and VPM compatibility,
update/rollback/offline/removal qualification. These tool checks do not prove
model compliance or activate an installed service.

Routine CLI maintenance selected official stable **0.169.0**, replacing 0.167.2.
All six credential-free official installer/loopback compatibility cases passed
under an ordinary Linux UID; no provider model call or credential was used.
Temporary-directory PATH-alias and old-release-cleanup warnings were observed;
direct execution passed without modifying an existing release.

The Debian host mounts `/run` with `noexec`, so deployment tests use a private
mount/PID namespace with executable synthetic `/run` and a private systemd-unit
directory, so fixed host-entry helpers remain inside the test root. Cross-UID source tests use a
private bind alias and task-owned `/tmp` fixtures, without changing owner source
permissions. The installed-runtime fixture stages the real routing aliases and
uses a traversable cwd and synthetic temporary storage for its runtime users.
The deliberate excessive-sudo-grant test asserts the current effective-policy
failure instead of an obsolete diagnostic string. Ten rapid metadata-mutation
failures were reproduced on untouched accepted source: this ext3 host can reuse
ctime/mtime ticks and inodes. The fixtures now establish an actual metadata
change before testing the existing guard; product guards are unchanged. These
tests do not prove detection of a changed-and-restored input with an identical
complete observed identity.

The installed public general-runner smoke producer still emitted a pre-native
Task-like envelope that current admission correctly rejected. It now uses a
separate fixed owner-local request, authenticated against the installed producer
and its exact root transition. It cannot supply Task/Step/admission, arbitrary
input or profile, or native publication authority. The existing public command,
two-minute boundary, model profile, containment and finalization remain. An
explicit mode correction on the newly generated task-local OpenSSL configuration
allows the model UID's existing shared group to read it under a restrictive
umask; host configuration and owner files are unchanged.

One maintained-activation fixture also invoked the system Python without pytest
while importing its own pytest-based test module. This was reproduced on the
accepted baseline and corrected only in the synthetic fixture to use its active
test interpreter; production interpreter selection is unchanged.

Deployment-suite and composed installed-runtime results are recorded in the
final canonical Outcome after completion. The latter installs actual candidate
roles/templates in private mount/PID/network namespaces and uses synthetic
GitHub/Codex transport. It does not establish a live paired-service upgrade,
production deployment, new App permissions, real model compliance or acceptance.

## Boundaries and handoff

The shared TEST marker was freshly claimed by this attempt only after free
readback; installed TEST routing identifies the dedicated testbed repositories.
The live TEST gate was read back open with no active or unknown controllers,
and no systemd jobs or active deployment frontend were observed. The exact
attempt-owned claim was released and the marker read back free, with admission
open/idle and production-operation state STABLE. Source,
private-namespace qualification and shared-service facts are separate evidence.
No PROD mutation, product merge, external package publication, credential change,
GitHub App/runner ACL change or Task closure was performed.

The title tool was called once; persisted display is truncated. Requested
parent profile is `gpt-6.1-sol / xhigh / Subagents On`; actual model/effort
telemetry is unavailable. Three helpers supplied implementation and verification
evidence, including a separate streaming assessment that found defects corrected
within this Step. They did not supply native independent acceptance.

Small Improvements discovery found #248, #250 and #251. Their separate guidance
and live-settings work was not admitted into this implementation. No candidate
was silently added or closed.

## Developer-hook removal

The owner selected complete removal within R8/D5, recorded in trusted
[Decision 6884460584](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6884460584).
The automatic registrations, all helpers and their tests/documentation were
removed together with active guidance references. No manual helper remains.
No special hook execution was performed. Private local files, global Codex
settings and immutable accepted historical evidence/packages were preserved.
