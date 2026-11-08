# Task 217 — Step 2 qualification

This continuation preserves the shared TEST lock implementation and its
[Step 1 shared-host exercise](task-217-step-1.md). It resolves directly blocking
CI acquisition and portable validation-fixture failures. This execution made no
new claim on the shared TEST installation and did not repeat the shared-host
exercise, install a candidate, or change TEST/PROD services.

## VibeVM acquisition

The pinned VibeVM 1.0.11 browser download repeatedly returned HTTP 504. The
anonymous GitHub release API identified the same tag, asset name and browser URL
and served 84,617,936 bytes with the unchanged pinned SHA-256
`5fe5b3efeb2eab7c7c49a8dc864864ffacac08a9d7be3dc9df0bc0bb15a8bd58`.
The complete helper exercised three failing browser attempts, API fallback,
digest verification and private executable mode successfully. No credential,
mirror, moving release or integrity exception was used.

Public CI now calls that helper. Its eight focused tests cover transient HTTP
and transport failures, interrupted reads, bounded retries, exact asset
selection, permanent failures and digest rejection on both routes. Existing
VibeVM regression tests (19) and the native pinned-tool probe passed, including
offline reads, exact regeneration, overlays and collisions. The probe uses
disposable copies; it does not qualify model behavior or consumer installation.

## Validation fixtures and environment

The pre-Apply primitive fixture now ignores its generated Python bytecode so
its unchanged clean-source protection reaches the intended engine. Negative
cases assert their exact refusal codes. The imported native incident fixture
retains its root/Linux requirement when reused from another module. Other
bounded fixture corrections handle private synthetic consumer configuration,
installed source modes, POSIX Git discovery, a development login whose primary
group has a different name, and slot ownership without unauthorized chown.
Production permission, admission and protected-source checks remain unchanged.

Validation ran as the ordinary governed worker on native Linux, using Node
22.23.3, Cargo 1.90.0 and Python 3.11.2. Pytest was acquired into task-local
ignored storage. Test invocations used umask 0022, UTF-8 locale, a private
synthetic consumer copy, and /tmp for suites that intentionally reject output
inside the source tree. The minimal host lacks the default OpenSSL config and
`cc` alias: synthetic certificate qualification used OPENSSL_CONF=/dev/null,
and Rust used the installed gcc through its linker setting. The installed mawk
also passed the readiness tests through a task-local awk command wrapper.
No original source permissions or system configuration were changed.

The complete Node suite passed: 1287 passed, 7 skipped. Cargo formatting and
all 159 Rust tests passed. Three-consumer qualification, frozen product checks,
26 surrounding workflow tests, candidate scanning and whitespace checks passed.
The repaired deployment/lock suites passed: 244 passed, 35 native-only skipped.
All 13 Ansible member planning/package-verification tests also passed after
using the fixture user's actual primary group.

The complete deployment/Ansible run finished with 1951 passed, 738 skipped,
30 failed and 18 deprecation warnings. The three member-package failures were
corrected and all 13 member tests passed afterward. Five shell cases lacked the
host's awk alias; targeted revalidation using the installed mawk through a
task-local wrapper passed (22 passed, 6 skipped across the affected suites).
The remaining 22 cases need capabilities this worker does not have:

- Six consumer-drift cases reject mapped ownership of protected namespace tools.
- Eleven retained-recovery cases require private evidence with equal protected
  UID/GID; this worker has distinct UID 983 and primary GID 979 and cannot create
  the required ownership.
- Four pool-qualification cases reject the governed checkout's mapped protected
  source/parent ownership before reaching the synthetic GitHub group response.
- One native ACL case cannot encode an unmapped foreign UID in this namespace
  (the kernel returns EINVAL).

These failures are not a green full-suite result. Product checks were retained;
native root-only installed-runtime proof remains for exact-head CI after Writer
publication. No privilege escalation or system permission repair was attempted.
The worker cannot inspect native GitHub execution annotations or Outcomes under
its credential/publication boundary, so warning absence is not established.
Independent exact-head acceptance and integration remain pending.

One implementation helper was used for download and deployment-fixture diagnosis
(requested gpt-6.1-sol/high). Its results are implementation evidence, not an
independent governance review. Actual model/effort telemetry is unavailable.
