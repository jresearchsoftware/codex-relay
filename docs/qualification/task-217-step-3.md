# Task 217 — Step 3 qualification

This remediation retains the complete shared TEST lock/unlock implementation,
the [bounded real TEST host exercise](task-217-step-1.md), and the
[Step 2 validation repairs and protected-test limits](task-217-step-2.md).
The 13 lock tests passed again, including contention, holder-only release,
handled failure cleanup, abandoned ownership and normal reuse. This execution
did not access the shared TEST installation or change TEST/PROD services.

## Corrections and release classification

The [dated CLI assessment](task-217-cli-maintenance.md) records one official
stable comparison and the compatible **0.160.0 -> 0.167.0** disposition. The exact
pin, both owning Ansible assertions, current qualification assertions and coupled
fixtures agree. The AGENTS pointer and canonical CLI policy now trigger on a
product change needing subsequent owner-controlled Apply after accepted merge,
even when Apply is not a Task completion action. Documentation-only work remains
excluded. There is no recurring updater, capability audit or added Apply action.

Guidance **4.1.1** is a **PATCH** from independently accepted **4.1.0** at
`6fb8fc447fe56d9e5d67dd539d8aad289faf0666`. The canonical Skill manual, example
and directly affected contract clarify the existing automatic route: the owner's
PR `codex-ready-auto` command passes through Writer, which derives, executes and
verifies `begin-remediation` before admission/worker execution. Reviewer returns
an action, not evidence of its execution. The clarification adds no owner Draft
operation or runtime mechanism. Relay-admitted manual and standalone/direct
manual boundaries remain distinct.

Both delivery forms were generated deterministically. The actual checkout's
native registry, lock, slot, boot index, Skill and receipt were updated through
VibeVM 1.0.11 and passed structural/native verification. Frozen 4.1.0 and earlier
registry bytes, the included Shared 5.0.0 snapshot, native `>=2.5.0` requirement,
project Shared 7.0.0 selection and accepted protocol contract pin
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4` remain intact. The complete 4.1.1
native export hash is
`sha256:d9e85f939816b7f048e77f0e5608720498272118a7fecc35cc973fb3c9934730`.

Release readiness used the accepted Shared Publisher implementation
`414077e956aa47b18ddc436f68c3245b508baf46`, without modifying it. All eight
integration tests passed. Its native fixture used its separately hash-verified
VibeVM 1.0.7, exported the actual candidate, finalized only to a disposable local
bare repository, verified immutable same-source retry, and installed a fresh
consumer with exact package bytes and retained owner policy. The exporter checked
42 files including its distribution receipt; payload SHA-256 was
`07875a554d355e80b4b4eedfa6da81fcab70aee851a343e960bbcaeaaa2831b2` for source
`f4fae247d7e2f2d83664005e33b92d6feb69596e`. Later evidence-only documentation
does not change that payload. This is synthetic readiness/local transport proof,
not successful source CI, external publication or consumer adoption. The existing
Shared Publisher accepted-main workflow remains the later publication path after
independent acceptance and owner-authorized merge.

## VibeVM acquisition

The browser download timed out and the exact tag-metadata API returned HTTP 504.
The anonymous release listing identified the exact 1.0.11 musl asset ID
`704909893`, browser URL and unchanged SHA-256. The fallback now uses that reviewed
ID directly, avoiding a redundant unavailable tag lookup, and still requires the
pinned digest before writing an executable. Pins without an ID retain exact
metadata matching; malformed IDs and mismatched bytes fail closed. Ten focused
acquisition tests passed. The final complete downloader acquired and verified
84,617,936 bytes with the original digest; native packaging probes used them.

Upstream availability remains a material limitation: a separate exercise with
an injected browser failure reached the real pinned asset API, which returned
HTTP 504 through all bounded attempts. The fallback is not a promise that both
upstream routes are always available. No credentials, mirror, floating release
or integrity exception was used. The publisher's older pinned binary also needed
bounded retries before successful digest verification.

## Validation environment and limits

Checks ran as the ordinary governed Linux worker: Node 22.23.3, Python 3.11.2
and Cargo/Rust 1.90.0. Task-local pytest/PyYAML, private synthetic consumer input,
UTF-8 locale, umask 0022 and `/tmp` were used. The first Node run's five socket
failures came from the inherited overlong temporary path; the corrected complete
run passed. The first deployment run also inherited that path and a non-UTF-8
locale (172 failed, 1809 passed, 738 skipped); it is superseded by the corrected
run below. Installed `mawk`/`gcc` were exposed through task-local command wrappers,
and synthetic certificate checks used `OPENSSL_CONF=/dev/null`. No system
configuration, original source permissions or privileges were changed.

Final local evidence:

- Complete Node suite: **1287 passed, 7 skipped**.
- Cargo formatting and **159 Rust tests** passed; three-consumer qualification,
  candidate scanning and whitespace checks passed.
- Complete deployment/Ansible run: **1958 passed, 738 skipped, 23 failed,
  18 deprecation warnings**. One failure read the old 0.160.0 role assertion
  before its correction during that run. Both owning role assertions and the
  pin-coupled staging fixture were corrected; the affected deployment/runtime/
  staging revalidation passed **32 tests, 29 native/root-only skipped**.
- The remaining **22 protected-context failures** match Step 2: six
  consumer-drift cases reject mapped ownership of root namespace tools
  (`CONSUMER_PUBLICATION_PATH_UNSAFE`); eleven recovery cases require private
  evidence with equal protected UID/GID (`REINSTALL_RECOVERY_EVIDENCE_UNSAFE`),
  while this worker is UID 983/GID 979; four pool cases reject mapped protected
  source ancestry (`MANAGED_POOL_ELIGIBILITY_PARENT_UNSAFE`); one native ACL case
  cannot encode the unmapped foreign UID (kernel `EINVAL`). The full suite is
  **not green**. No protected check was weakened or privilege escalation tried.
- The real selected official CLI probe, 33 Python CLI contracts and 35 Node
  launcher/result tests passed, as detailed in the CLI evidence.
- Lock tests: **13 passed**. Download tests: **10 passed**. Standalone projection/
  deterministic builder tests: **17 passed**. Native verifier counterexamples:
  **19 passed**. Native VibeVM/self-adoption and VPM delivery probes passed,
  covering exact regeneration, consumer protocol routing, minimum dependency,
  update, rollback, repeat/offline use, drift, collisions and removal. The Skill
  frontmatter validator passed. Shared Publisher's **8 integration tests** and
  the local native export/retry/consumer-install exercise passed.

Task-local traces remain in ignored `.codex-sandbox/task217`, including
`npm-test-final.log`, `pytest-final.log`, `pytest-cli-pin-focused.log`, Cargo,
qualification, native/VPM and publisher logs. Disposable qualifier fixture paths
are recorded by those logs; their local distribution refs are test data only.

Material warnings remain for the next owner/independent review boundary:

- Codex 0.167.0 reserves managed `permissions.network` for shared constraints;
  previously named managed profiles may need upstream-compatible migration.
  The bounded probe did not exercise every administrator policy combination or
  native tool execution. A later installed-host adoption must assess its actual
  managed configuration. Historical Task 96 installed-0.160.0 proof is not
  relabelled as 0.167.0 proof.
- The official installer/binary's `/tmp` PATH-helper alias warning remains;
  direct execution was qualified, aliases were not.
- Intermittent upstream download failures remain as described above; the
  implementation retains bounded attempts and mandatory digest verification.
- Native GitHub Outcome/job/controller annotations cannot be inspected through
  this worker's credential/publication boundary. This is an evidence gap, not
  a claim that no execution warnings exist. Writer/native exact-head CI and
  independent review retain their required warning acquisition/disposition.

Requested parent profile: `gpt-6.1-sol` / `xhigh`; one implementation helper used
requested `gpt-6.1-sol` / `high` within Subagents On. Actual backend model/effort
telemetry is **UNAVAILABLE**. Helper results are implementation evidence, not
independent acceptance.

Useful source changes are ordinary task-owned commits for trusted Writer import.
No external publication, PR mutation/merge, Issue closure, release, Apply,
installed-host deployment or PROD action was performed. Root/sudo-only
installed-runtime proof remains for native exact-head CI after Writer publication;
independent exact-head acceptance and authorized integration remain pending.
