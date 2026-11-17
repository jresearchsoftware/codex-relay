# Task 244 Step 5: Apply proof independent of diagnostic capture

This remediation starts from reviewed head
`96bf732acf9fd75fa229adf455ce2b2526aaf45c` on the existing Task branch and
addresses CR-244-001 F1. The earlier [Step 4 inventory](task-244-step-4.md)
remains applicable to unchanged paths; this report supplies changed-path proof,
not a new claim of whole-Task acceptance or installed qualification.

## Cause and correction

The non-Git owner coordinator returned the public deployment child's bounded
stdout transcript as semantic verification input. Once output exceeded 256 KiB,
the middle was omitted. A real, successful child could therefore emit the exact
workflow-projection proof in that middle and still be refused after host effects.
The regression below directly observes that the marker is absent from the
retained transcript while present in the complete child output.

`deploy/lifecycle_process.py` now recognizes caller-supplied exact stdout proof
lines while draining the complete original stream. It retains only the matched
expected lines, independently of the bounded diagnostic head/tail and byte
counts. The existing bounded line parser handles chunk boundaries and rejects
oversized-line fragments; stderr and prefixed/suffixed lookalikes cannot supply
proof. A final EOF-terminated exact line is recognized. Reader/forwarding errors,
timeout, cancellation, nonzero exit and uncertain cleanup retain their existing
failure behavior; a matching line does not turn those failures into success.

`deploy/owner_lifecycle.py` requests the three exact lines bound to its frozen
target and consumer. After successful child completion it requires all matches
and the existing protected installed-state verification before admission resumes.
A missing marker keeps admission closed and attaches the bounded original
stdout/stderr, byte counts, zero exit and missing expected lines to the existing
protected causal reporter. No marker or arbitrary child output is newly exposed
to Actions. Git-pair Apply keeps its existing independent verification route.
There is no retry, extra operation, model call or new diagnostic store.

## Focused evidence

`deploy/tests/test_owner_lifecycle.py` runs the actual child observer inside the
existing synthetic non-Git owner Apply coordinator:

- A successful child writes over 400 KB of stdout, with exact projection proof
  in the omitted middle and the installed/lifecycle proofs at the end. The
  diagnostic capture remains bounded, installed verification runs, and admission
  reopens after one child invocation.
- Missing, altered, wrong-revision, wrong-consumer and prefixed/suffixed markers
  refuse same-operation verification, retain original child evidence and missing
  proof observations, and leave admission recovery-required without resume.
- Even with all three valid markers, a child exit of 7 preserves the native
  exit/stderr cause and leaves admission closed without installed verification.
- An actual private-log readback verifies the missing expected marker, original
  byte counts and truncation, and redaction of a synthetic stderr credential.

`deploy/tests/test_lifecycle_process.py` separately injects read boundaries,
stderr-only proof, EOF, CRLF, oversized-line fragments and recovery at the next
newline. Existing real-child tests continue to cover flushed live progress,
quiet waits, bounded evidence, timeout/cancellation and cleanup uncertainty.
The focused owner/process/Git-owner suites passed **91 tests and 41 subtests**.

These are credential-free Linux fixture tests, including real subprocesses and
the actual non-Git owner composition. Admission, source acquisition and installed
state are synthetic capabilities. They do not run an installed root Apply or
qualify sudo wrappers, host services, production effects or a protected journal.
No shared TEST contour was accessed.

## Candidate validation and continuation

| Check | Observed result |
| --- | --- |
| Focused owner/process/Git-owner suites | 91 passed; 41 subtests passed, including the final nonzero-exit and private-log readback additions. |
| Full Node suite | 1,343 passed; seven skipped; zero failed. |
| Locked Reviewer suite | 190 passed with short TMPDIR; Cargo formatting passed. |
| Full deployment and Ansible suite | **2,460 passed, 1,010 skipped, 35 failed**, 497 subtests passed. This run preceded the final two focused test additions; those passed in the focused rerun. Functional source was unchanged. The full suite is **not green**. |
| Three-consumer qualification | `THREE_CONSUMER_PASS`; handler-source digest `8aa8d30c273f453ff1185753e90c76466598c2e359b6c8835a47e8dc73a19753`, unchanged because these corrections affect deployment composition. |
| Candidate and whitespace | Tracked candidate scan and `git diff --check` passed. |

All 35 deployment failures were inspected and match the five unchanged groups
documented in Step 4; none reaches this correction's proof matcher:

| Fixture group | Count | Original failure evidence / disposition |
| --- | ---: | --- |
| Consumer drift | 6 | `CONSUMER_PUBLICATION_PATH_UNSAFE`: protected tool requires UID 0, observed UID 65534. |
| Install recovery | 12 | `REINSTALL_RECOVERY_EVIDENCE_UNSAFE`: recovery reader requires GID equal to owner UID 990, observed GID 986. |
| Managed pool | 4 | `MANAGED_POOL_ELIGIBILITY_PARENT_UNSAFE`: unmocked protected root-parent ownership check refuses the unprivileged fixture before its simulated API classification. |
| Native default ACL | 1 | `os.setxattr(..., system.posix_acl_default, ...)` returns `EINVAL`. |
| General component proof | 12 | Eleven fixtures fail `source-directory-metadata` (allowed UIDs 0/65534, observed 990); a read-only reproduction of the native process-map case shows `source-file-metadata` expecting UIDs 0/990, observed 65534. |

These retained safety refusals require capable-host/native reconciliation;
neither source permissions nor protection checks were relaxed. The suite also
reported the upstream Ansible `crypt` deprecation warning on Python 3.11.

The ordinary-mode disposable checkout under the ignored execution sandbox keeps
the candidate source identical while avoiding the supplied checkout's shared
source modes. Temporary Unix socket fixtures use `TMPDIR=/tmp`; the original
checkout's permissions remain unchanged. Python test dependencies are confined
to the execution sandbox. An initial Rust run with the inherited long TMPDIR
failed the existing socket-bind test (189 passed, one failed); using the short
temporary root passed all **190** locked Reviewer tests. This is a fixture
environment correction, not a product source fix or evidence from a green rerun
about the separate historical Reviewer journal incident.

The routine official stable CLI endpoint still selected `rust-v0.169.0` on
2026-11-17, matching the existing qualified dependency; its pin is unchanged.
Frozen Skill 9.0.0 is unchanged. A read-only helper inspected the changed proof
recognition and coupled producer/callers under requested `gpt-6.1-sol/high`;
that inspection is implementation evidence, not native independent acceptance.

Writer publication, native exact-head CI and independent exact-head acceptance
remain separate continuation boundaries. The worker is UID 990 and has no
root/sudo installed-runtime capability. Current-run job/controller annotations
were not acquired by this credential-free worker; warning absence is not claimed.
Task 244 remains open for its existing completion conditions, including the
distinct remaining #248/#256 client/projection obligations. No release, PROD
Apply, original-incident replay or historical Outcome rewrite was performed.
