# Task 115 Step 3 remediation evidence

This report concerns F3/F4 under the current native
[CR-115-002](https://github.com/jresearchsoftware/codex-relay/pull/118#pullrequestreview-5490953732).
The complete native Request body SHA-256 is
`bca63319759a22eb837c38d4a513467b4f7b81e30f2783f19ffcb67b4144abc4`.
Its selected [Decision 6124295101](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6124295101)
hash is `edc97f46204af9759c295b551657901907a773498d294d058bb99e4692ce50e5`;
the stable Task charter hash is
`c36bf4e867ba254818d1e0807329ab50387c8e53eccdc2e751b9cbb5b87f646f`.
The separate native [Writer handoff](https://github.com/jresearchsoftware/codex-relay/pull/118#issuecomment-6124690488)
binds Step 3 and attempt `run-38252046794`.

The [retained authority verifier](evidence/task115-step3/verify-current-request.mjs)
reads complete paginated native Issue/PR records, verifies the trusted Reviewer
Bot identity, exact source hashes and supersession edges, and selects the current
complete schema-v3 Request. This execution follows that installed admission;
its source changes do not reinterpret the original admission as schema v4.
At startup local HEAD, refreshed remote and live PR all matched required head
`c5281d0d5cf561173ed34b94620c765d96188a7c` on `codex/task-115-step-1`;
the exact base is `b4cb4943d52dd375d8c6800959b3264fad082cb8`.

## Findings and final behavior

F3 is a gap in Task 115's new schema-v4 admission behavior that survived Step 2.
The unmarked legacy parser already existed on baseline
`b4cb4943d52dd375d8c6800959b3264fad082cb8`; the issue is its continued availability
for fresh executions after activating the new contract at reviewed head
`c5281d0d5cf561173ed34b94620c765d96188a7c`. F4 concerns the corresponding missing
fresh-publication guard and client instructions. Existing old-protocol support
on the baseline is not by itself an introduced regression.

On the qualified current pair, a fresh unmarked/legacy execution or an applicable
v3 Request/CR execution stops with `CURRENT_PROTOCOL_REQUIRED`. The refusal
cannot allocate a Step, reserve another execution, consume the ready command,
launch a runner or fabricate an old-protocol Writer Outcome. New native v4 work
resolves directly from current charter/Decisions, without selecting a v3 Request
as a compatibility input. A marked Task with v3 Request history needs an active
trusted Task-scoped v4 Decision newer than its latest v3 Request, explicitly
amending purpose or scope. Closure/profile-only changes do not establish that
direction. An applicable v3 CR needs a current v4 CR; a Task Decision cannot
translate its findings into new remediation authority.

Fresh Reviewer v3 Decision/Task Request/CR and legacy CR2 publication also fail closed
under the current native capability. Exact existing reserved operation recovery,
duplicate read-back and historical readers remain available. Older admitted
executions preserve their original envelopes, source references, Step, result
publication and recovery paths. No historical publisher/executor is deleted,
no Request is converted, and no migration bridge or version-support cutoff is
introduced.

Active historical trusted v3 Task Decisions still contribute their durable
semantic amendments until valid supersession. They are not new v3 publication
or an execution-bearing Request/CR fallback; dropping them would discard
accepted Task semantics. The fresh admission itself and new authoring use v4.

Outcome, approval and owner-continuation resolution retain the original
compatibility selector: a new admission with `compatibility_request: null` cannot
later infer a historical v3 Request, while a retained non-null source stays exact.
This closes the adjacent lifecycle failure exposed by the fresh-v4 gate without
changing old admission semantics.

The connected caller must inspect its available tools and input schemas for the
selected operation. Missing/outdated current typed authoring or manual Writer
submission capability is an actionable mismatch, never permission to use a v3
Request, CR2 or owner-result comment fallback. The server enforces what it can
observe; it cannot inspect an inaccessible connected App or stale client cache.
AGENTS, workflow, architecture, authority, controller, Reviewer and relevant
consumer/deployment instructions describe this same boundary.

The concrete risk is a silent downgrade that propagates obsolete executable
authority and conflicting Step/publication semantics. The existing marker and
schema readers did not prevent it. The accepted gate uses the installed native
capability and existing protected operation/admission records before mutation;
it adds no handshake, state ledger or support cutoff. Its operator cost is an
explicit current native direction or a visible installation/migration correction
when older work is incompatible. Task Decision 6124295101 explicitly authorizes
that material change; ordinary compatible current work adds no new step.

## Validation environment and evidence boundaries

Validation uses the native Debian filesystem at
`/tmp/task115-step3-validation-01a13034`, initially populated by an exact starting
Git archive and then synchronized with task-owned candidate files. Toolchain:
Node 22.20.0, Rust/Cargo 1.90.0, Python 3.11.2, Git 2.39.5. Node and Cargo are
selected through the existing user's toolchain directories; the shared host's
default Node 18 is not used for candidate tests. No permission repair or shared
host/runtime change is needed.

Focused native Node checks passed 228/228 plus the final forked-migration
assertion; focused Rust authority checks passed 49/49. The
[initial full Node run](evidence/task115-step3/logs/node-initial.txt) exposed three
historical fixture expectations that recreated a broker without explicitly
selecting their older qualified protocol. The new current gate correctly refused
those fresh legacy inputs before the fixtures' intended event/lifecycle checks.
The fixture recreations now explicitly select that historical qualification;
the gate is unchanged. The affected legacy/current suites then passed 88/88.
These failures were exposed by the authorized new gate, not evidence that its
historical completion path failed. New current-protocol negative and recovery
tests remain enabled.

The complete native Linux set passed on staged source tree
`cb94f2d1f5ccc9ad847324ab4167a5565d1011b8`:

| Check | Result | Evidence |
| --- | --- | --- |
| Node | 812 PASS, 1 SKIP, 0 FAIL | [full log](evidence/task115-step3/logs/node-full.txt) |
| Python deployment/Ansible source tests | 892 PASS, 300 SKIP, 19 dependency warnings | [full log](evidence/task115-step3/logs/python-full.txt) |
| Rust locked tests | 127 PASS | [full log](evidence/task115-step3/logs/rust-full.txt) |
| Rust formatting | PASS | [log](evidence/task115-step3/logs/rust-format.txt) |
| Rust release warning inspection | build PASS; 4 pre-existing warnings | [log](evidence/task115-step3/logs/rust-release-warnings.txt) |
| Three-consumer source qualification | PASS | [log](evidence/task115-step3/logs/qualify.txt) |
| Tracked candidate scan | PASS: 544 files, 335 local links | [log](evidence/task115-step3/logs/candidate.txt) |
| Working/staged whitespace | PASS | [command log](evidence/task115-step3/logs/diff-check.txt) and final Git checks |

The [reproduction script](evidence/task115-step3/run-source-checks.sh) records
the complete commands. Stored command logs remove only trailing whitespace to
meet the repository whitespace check; diagnostic content remains intact.
Qualification source digest is
`6102baf4894eeb85a6e9bed6ed9cb1df3366dbea5d015899bbeb2531684eb58a`;
the built Reviewer artifact digest is
`320f1373486bf562522837c047e4c8383fba9149f14cee71cb2ca4bf5156fb73`.
Later report/log/receipt additions do not alter the tested implementation.
Those additions passed the [final staged candidate scan](evidence/task115-step3/logs/candidate-final.txt)
before commit.
Required final-head native CI and its warning observation are linked in the
top-level committed-evidence handoff and PR description; reconstructible native
status is kept in those GitHub records.

Source/mock tests do not establish installed E2E behavior,
real Relay admission/model traversal, App upgrade, PROD qualification or
independent acceptance. Prior Step 1/2 isolated TEST evidence retains its
original revisions and scope; it is not relabeled as this candidate's live proof.

## Publication, warnings and remaining boundary

The available PROD connected tool surface exposes no `submit_manual_outcome`.
The retained manual-result publisher supports Task Request admissions, whereas
this attempt is a native PR Change Request and the original PR execution markers
must remain unchanged. TEST cannot substitute for this PROD admission. The
current CR explicitly permits the committed-evidence/PR handoff when governed
publication is unavailable. That handoff is not a Writer Outcome or a
Writer-verified Ready transition. Original Step 1/2 admissions, journals and
native history remain untouched; the original missing Step 1 Writer Outcome
is not waived or fabricated.

Material local warnings are the Python dependency deprecations (passlib/crypt
and Jinja lexer), 300 environment-dependent Python skips, one Node skip and four
Rust release warnings. The release warnings concern two unused mut bindings in
unchanged `reviewer/src/github.rs` and two test-only identifier helpers whose
definitions are unchanged from the reviewed starting head. They remain visible
for independent disposition; unrelated compiler cleanup is outside F3/F4.
These counts match the recorded Step 2 baseline; they do not prove every skipped
environment or installed boundary. The native warning reader covers supported
exact-head API sources, including the original Step 3 routing run. UI-only
service/pre-execution annotations remain outside automated completeness, so
global warning absence is not asserted.

Requested parent profile is `gpt-6.1-sol / ultra`; actual runtime values remain
`UNAVAILABLE`. Three scoped helpers were requested as `gpt-6.1-sol / xhigh`
(Node admission), `gpt-6.1-sol / xhigh` (Rust publication), and
`gpt-6.1-sol / high` (documentation). Subagents were used within the admitted
permission. The native title tool accepted the exact requested full title once;
read-back returned a truncated title, so exact persisted-title verification is
unavailable and non-blocking.

Task 115 stays `keep-open`. The next boundary is independent review of the
complete exact candidate against current charter/Decision/CR authority, including
warning disposition and the original missing-Outcome anomaly. Product merge,
PROD/App installation, Issue closure and unrelated continuation remain outside
this execution's authority.
