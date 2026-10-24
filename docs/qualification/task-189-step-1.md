# Task 189: Task 68 collection and review-readiness incidents

Authority: [Task 189](https://github.com/jresearchsoftware/codex-relay/issues/189),
[Owner Decision](https://github.com/jresearchsoftware/codex-relay/issues/189#issuecomment-6384847149),
manual Step 1, `run-40098714571`. Accepted starting source:
`8db63ad052de637c648611b89f415a5c3142a399`. Diagnosis and source remediation share
this Step; independent acceptance, production adoption and original-result
recovery remain separate.

## Track A: unreadable generated tracked source

Incident: Shared Governance Task 68 Step 1,
[run 40082446961](https://github.com/jresearchsoftware/shared-governance/actions/runs/40082446961),
[historical BLOCKED Outcome](https://github.com/jresearchsoftware/shared-governance/issues/68#issuecomment-6382711491).
The protected Writer envelope identifies slot `pool-4`, original branch
`codex/task-68` and starting head `414077e956aa47b18ddc436f68c3245b508baf46`.
Installed product manifest and release resolve to
`c3ac51525d92edb6d8b8a8c5a2c5bc242df7b873`. Hashes of the installed collector,
broker and authority module exactly match those files at that source revision.

Read-only privileged inspection found the retained generated source
`vibevm/vibespecs/boot/INDEX.md` at mode `0600`, UID 983, GID 979. This was the
only retained non-Git entry without group read permission in the bounded tree
inventory. Its content SHA-256 was
`a01fc16a11d09fa63011f329a6a89ecb1e0badc172fd939ce25ee6797952e3d3`.
Its retained modification/change timestamps precede progress collection. These
timestamps and current metadata do not establish uninterrupted historical inode
custody or identify the original file-creation syscall.

The actual collector account has UID 985, primary GID 982 and supplementary GID
979. A guarded read under that account fails with `EACCES`; group membership
cannot override explicit `0600`. Running the **installed** `collectProgress`
against the retained checkout reproduces `TRUSTED_GIT_FAILED / GIT_LOCAL_FAILURE`,
`worktree-observation`, `source-read`, `open`, `EACCES`, with no stderr and no
publication. An incident-specific read-only `openat` trace records exactly one
denied open: `INDEX.md`, using `O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC`.
The original file's inode/mode/owner/size/timestamps were unchanged by the probe.
The relevant generated-directory parents were collector-owned UID 985/GID 979,
mode `2770`; traversal succeeded. No POSIX access ACL was present on the file,
it was on the checkout's device, and that host mount was not read-only. This
rules out a parent/group-traversal or read-only-mount explanation for the
reproduced open failure. The terminated worker's historical mount namespace
cannot be reconstructed from this current host observation.
The trace stays in the private diagnostic workspace; its SHA-256 is
`aad919f0e1c32a65f2466a02529098f8cdde9e3b354e58f9bb9b9704c8a04d4d`.

The collector [imports objects and then observes the complete worktree](https://github.com/jresearchsoftware/codex-relay/blob/c3ac51525d92edb6d8b8a8c5a2c5bc242df7b873/controller/src/trusted-git.mjs#L307).
This source file cannot be skipped merely because Git records mode `100644`.
The [guarded source read](https://github.com/jresearchsoftware/codex-relay/blob/c3ac51525d92edb6d8b8a8c5a2c5bc242df7b873/controller/src/trusted-git.mjs#L150)
correctly respects its filesystem permissions. The first demonstrated failing
boundary is producer output/reconciliation of a private-mode public generated
index, rather than the collector's identity or the Task 171 primary-group fix.
The exact historical generating call is not retained; do not claim that a
specific VibeVM syscall was traced during the original execution.

The `.codex-sandbox/` worker statement is not the demonstrated cause. Task 171's
group-inheritance correction is present and does not override private modes.
Task 164's explicit-private-mode distinction remains applicable; `.agents`
`EROFS` and Task 109's older `diff` failure/recovery are distinct mechanisms.
No original worker was replayed, file permissions repaired, result salvaged or
historical Outcome changed.

### Identity loss and correction

The raw retained branch ref contains
`934d967cacb83f3ac040c67229c33dd370954b4c`. This is a forensic lead, **not** a
qualified candidate, accepted execution or authorized recovery publication.
No trusted Git command was run against worker-controlled metadata.

The original collector reads/imports a head before worktree observation, but
returns `head`, `clean` and a bundle only after complete observation. Its
failure preview retained the category/actor but discarded that head and failing
object identity. Consequently the runner never recorded collection and Writer
had no publication intent/head; ordinary `inspect` could not supply a candidate.

The correction keeps intentional denial and adds bounded private diagnostic
frontier data: `observed-head-unaccepted`, a SHA-256 relative-path fingerprint,
numeric lstat UID/GID/mode/device/inode and tracked category. Paths/content do
not enter that preview; public Outcome projections still exclude it. The head
does not grant recovery eligibility, object ownership/secret qualification or
clean observation. Existing protected recovery checks remain mandatory.
Worker guidance now explicitly checks public generated indexes after atomic
replacement. It authorizes neither arbitrary permission repair nor guaranteed
prevention of every external tool's private mode.

## Track B: successful Outcome followed by an authority gate on Ready

Incident: manual `run-40084979299`, Shared Governance Task 68 Step 2,
[Writer Outcome 6383152754](https://github.com/jresearchsoftware/shared-governance/pull/72#issuecomment-6383152754),
exact result `9d42e494ee7ee36485b5cb74d5e44e0eb457aba2`.
The original admission and protected Writer receipt are retained. The receipt
records `IMPLEMENTED_PENDING_FRESH_REVIEW`, that exact head and Outcome ID,
with frozen published authority drift `boundaries, purpose` and
`review_required=true`. There is no lifecycle intent or verified Ready receipt.

The [additional Decision](https://github.com/jresearchsoftware/shared-governance/issues/68#issuecomment-6383144155)
requires owner discussion before APPROVE; it does not prohibit review readiness.
In the identical installed/current source, [manual reporting](https://github.com/jresearchsoftware/codex-relay/blob/c3ac51525d92edb6d8b8a8c5a2c5bc242df7b873/controller/src/manual-outcome.mjs#L87)
allows drift, publishes and reads back the Outcome, stores it, and calls
`transitionManual`. That callback's [first read](https://github.com/jresearchsoftware/codex-relay/blob/c3ac51525d92edb6d8b8a8c5a2c5bc242df7b873/controller/src/publication-broker.mjs#L745)
uses ordinary execution revalidation. Its [new-boundary guard](https://github.com/jresearchsoftware/codex-relay/blob/c3ac51525d92edb6d8b8a8c5a2c5bc242df7b873/controller/src/live-authority.mjs#L345)
throws `AUTHORITY_CHANGED` before reserving a lifecycle intent or calling GitHub
Ready. The original transport error response is not retained in the inspected
journal; the branch/guard, frozen drift and missing intent establish the mechanism.

New real-broker regressions fail against accepted starting source with
`AUTHORITY_CHANGED` and pass with the correction, for manual reporting and an
automatic approval hold arriving between Outcome publication and handoff.
This is not a demonstrated GitHub permission failure or version-skew issue.
The same strict final guard also affected automatic `complete-handoff`;
manual replay repeated the failure. No-PR reporting has no Ready transition.
Retained v3 publication/recovery paths are unchanged.

The correction revalidates durable-result handoff separately from scope,
validation and approval constraints. Exact starting pins, authentic original
and current authority, Task/PR/branch/base/head, current Step, sibling publication
and immutable claim/Outcome protections remain enforced. Source publication
retains its strict admitted/current intersection. BLOCKED stays Draft and a
superseded result cannot change successor lifecycle. Ready grants no APPROVE,
integration, closure or implementation of amended scope.

At investigation readback, PR 72 already had a separate Step 3 result at
`ee0dd56f78f37fb8a5bbdb904921694c82f3b586` and was Ready. This Task did not change
that PR, its branch, reviews or historical Outcomes. An evidence-reader request
at the historical Step 2 head correctly returned `STALE_HEAD`; that is not an
absence-of-warnings observation.

## Qualification and boundaries

### Additional manual-continuation defect found by native qualification

The first real manual continuation, TEST Task 81 Step 2,
`run-40102273406`, exposed a second guard omission in the same lifecycle:
an Issue-based continuation emitted its handoff while existing PR 83 was still
Ready. CR admission calls `prepareRemediation`; Issue continuation does not,
and manual execution skips the worker preflight that normally drafts its PR.
The existing-PR regression had masked this by assigning `pr.draft=true` after
manual source modification. The regression now requires verified Draft before
that modification, and handoff performs the exact-current-PR transition under
the existing lifecycle intent/isolation checks. It preserves completed or
superseded attempts and does not create another CR or Step.

For the initial Step 2 Ready/drift qualification only, the parent explicitly
set the disposable fixture PR Draft after recording this omission. A new trusted
Decision then added the approval hold. Native manual submission returned
`PUBLISHED`, readback verified the unchanged exact head was Ready, and one exact
replay returned `DUPLICATE_SUPPRESSED`, retaining Outcome 6385392949 and its body
SHA-256 `9c7920e7e163b73ddb86bb927e16a5df93511fb2c9d85d38b5c43902d4c7be16`.
The protected result records `boundaries,purpose` drift and review required.
This proves the original Ready correction, not the subsequently fixed initial
Draft guard. That guard was then qualified through a fresh manual admission on
the updated installation, without another model call or altered historical receipt.

### Native TEST evidence

The exclusively allocated `codex-relay-test` namespace had an open gate,
`active=[]`, `unknown=[]` and no unsettled Writer effects before use. The public
upgrade passed from `60fa9febe16fe46b521908848eac78a54716cabe` to initial candidate
`c0a196fe3046ea2fef2493fb3c0e7715a3c83476`, with matching projection, same-operation
verification and gate resume. The configured pool retained capacity two; its
32 provisioned slot definitions did not mean 32 executing/registered workers.

- Genuine automatic TEST Task 81 Step 1, `run-40102003937`, completed in slot
  `pool-2`: child started, containment reaped, clean collection, one Writer push,
  Outcome 6385326215, and PR 83 Ready at
  `625f700830d7cb1e42bcdd4f4a8b1506e3e5420e`. Native CI run 40102114899 passed.
  Host readback verified the actual generated index UID 978/GID 973, mode
  `0640`, after the fixture's explicit private temporary-file generation.
- Genuine negative TEST Task 82 Step 1, `run-40102186604`, deliberately retained
  its committed synthetic index at UID 978/GID 973, mode `0600`. It produced the
  expected orchestration failure `EACCES` and one BLOCKED Outcome 6385343745,
  no PR, publication intent or published head. Containment was reaped and the
  controller completed. The protected diagnostic persisted collector UID
  980/GID 976, tracked source mode `0600`, numeric inode facts, the expected
  path fingerprint and `observed-head-unaccepted=f703357404c9704fd38b162623986eb8f2fc3dd4`.
  The public Outcome excluded the preview and private metadata. No failed
  worker was replayed or its intentionally unreadable file repaired.

These are real native admissions, model executions, distinct actor identities
and GitHub Writer effects, separate from the credential-free installed fixture.
TEST has different numeric identities, repository/App/runner resources and
candidate source from PROD; successful TEST does not install PROD or qualify
the original historical candidate. The positive scenario demonstrates explicit
known-public-file reconciliation, not automatic permission broadening by Relay.

The second public upgrade passed from the initial candidate to
`c01c42d264cacccce2e84d756c4b59ed380e7c28`, again with same-operation verification
and gate resume. Fresh manual TEST Task 81 Step 3, `run-40103351587`, verified:

- native Writer `convert_to_draft` event 34133183732 at 14:38:27 UTC, before
  handoff comment 6385502392 at 14:38:32 UTC;
- unchanged exact head `625f700830d7cb1e42bcdd4f4a8b1506e3e5420e`, then a later
  trusted purpose/boundaries amendment retaining Deliberative approval;
- `PUBLISHED` Outcome 6385511193, SHA-256
  `cfb010d2b5096a1221a5f6e5c80017a315e2d9031d8c883919d3d053884bc5bc`,
  and native Writer Ready event 34133232258 at 14:39:33 UTC;
- exact replay `DUPLICATE_SUPPRESSED`, the same Outcome ID/body, null pending
  lifecycle intent and native PR readback `draft=false` at the same exact head.

The executor did not set Draft in Step 3. Supported TEST PR warning evidence
was complete with none observed; UI-only service/pre-execution surfaces remain
excluded. The negative run has the expected native exit-1 failure annotation,
not an unreported success. Worker statements about launcher `.codex-sandbox/`
residue were checked against complete clean positive collection and its absence
at host readback; they are not proof of an ignored path or an access failure.

Final TEST handback retains the qualified updated installation, configured
capacity two, open admission and `active=[]`, `unknown=[]`, with no pending
qualification lifecycle effects. Original negative evidence remains retained.
PROD still resolves to `c3ac51525d92edb6d8b8a8c5a2c5bc242df7b873`; original
Shared Governance Outcome body hashes still match their protected Writer receipts.

### Source validation and remaining limits

Final Linux source validation: Node 1213 passed / 5 privileged cases skipped;
deployment pytest 1432 passed / 371 conditional cases skipped / 19 existing
passlib/Jinja2 deprecation warnings; Rust fmt and 159 locked tests passed;
three-consumer qualification, tracked candidate scan and whitespace checks passed.
The privileged cross-UID/read-only-source cases ran separately under native
Linux root and passed, including the exact generated boot-index pathname.
Both installed-runtime composed proofs passed in private PID/mount/network
namespaces with synthetic external transport; `--runtime-only` deliberately
does not repeat separate runner-package metadata qualification. Skipped optional
cases are not installed-host proof; the genuine TEST operations above provide
their stated operational evidence. Baseline regressions reproduce both the
Ready `AUTHORITY_CHANGED` failure and missing initial Draft, and the old
collector fails the new diagnostic-frontier assertions.

The final report-only commit does not change the executable code qualified at
the installed `c01c42d...` revision. Independent exact-head review remains
required for the complete final PR. The original generating syscall and original
historical mount namespace remain unknown; no original candidate recovery,
PROD repair or universal prevention of external private modes is claimed.

The incidents are independent: private-mode generated source versus conflated
execution/approval authority at final readiness. Neither justifies elevated
ordinary collection, blanket exclusions or relaxing independent acceptance.

Native Linux root regressions exercise actual distinct UID/GID reads, protected
`0600` package/boot-index source, unchanged metadata, accessible group-readable
source and existing ignored/private residue rules. Ordinary broker tests cover
manual success/BLOCKED/drift/replay/changed pins, automatic post-Outcome drift,
existing-PR remediation and historical delivery. Private PID/mount/network
installed-runtime qualification uses real templates, sudo, dispatcher, launcher,
journals, collection and Writer code with synthetic external GitHub/Codex.
It is separate from genuine externally admitted automatic TEST execution.

The canonical Outcome binds final source/CI, installed TEST and native execution
identities, warnings and any remaining gaps. PROD is read-only throughout;
original attempts and other consumers remain unchanged. Original recovery and
PROD adoption require their existing separately authorized operations.
