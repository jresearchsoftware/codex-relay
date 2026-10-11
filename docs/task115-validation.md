# Task 115 Step 1 validation and handoff evidence

This report belongs to the candidate commit carrying it. It records source and
qualification evidence; it is not independent acceptance, installation authority
or a second Task ledger. Canonical authority remains Task 115 and its current
trusted Request/selected Decision. The implementation started at
`b4cb4943d52dd375d8c6800959b3264fad082cb8` on `codex/task-115-step-1`.

## Source behavior and compatibility

New GitHub-native admissions resolve the stable charter and active trusted
Decisions into an immutable schema-v4 snapshot in the existing protected attempt
journal. Writer allocates Step under reservation, and replay retains the same
snapshot. Public full Task Requests remain readable for schema-v3 history and
already admitted attempts. Native exact-head CRs remain independent review;
Task Decisions alone amend durable Task scope and effective closure policy.

Manual result submission uses a fixed nonroot MCP client and namespace Unix
socket to a capability-specific root Writer service. The ordinary worker helper
rejects this direct capability. The existing handoff supplies exact public
Outcome bindings so the caller does not need a protected journal read. Writer
reserves and verifies one immutable result and one Bot Outcome; it reconciles
uncertain delivery without inventing a new publication or execution.

New records render English substance, findings, warnings and limitations before
one canonical JSON block. Shared Node/Rust fixtures prove deterministic parsing
and rendering parity, including large-record fallback and unchanged historical
bytes. Native GitHub rendering proof is recorded separately from local tests.

## Validation completed before TEST candidate selection

The complete Node suite ran in native Debian WSL, Node 22.20.0, at
`/home/hortonolite/work/codex-task115-01a12b33`: `npm test` reported 757 tests,
756 passed, zero failed and one skipped. The complete initial run exposed six
candidate-era failures: the native Issue admission prematurely queried ambiguous
PR linkage outside the domain rejection boundary, and five display expectations
still required raw text despite the new escaping contract. The bounded correction
and targeted checks passed, followed by the complete passing suite.

`cargo fmt --manifest-path reviewer/Cargo.toml --check` and
`cargo test --manifest-path reviewer/Cargo.toml --locked` passed on native Linux;
109 Rust tests passed. No Rust code changed after that run. The fixed Unix socket
transport suite passed 7 tests, and rendered deployment capability checks passed
7 tests. These are local contract proofs, not installed credential/ingress proof.

`python3 scripts/qualify.py` reported `THREE_CONSUMER_PASS` for three synthetic
consumers using real handlers/modules, isolated Git and loopback mock GitHub,
without model calls or production credentials. Its source digest was
`58930dd888e6a4ab9a4a9d743bd477302cb72d64c8f772ae615ae2960de09438`.

The staged candidate scanner reported PASS for 484 tracked files and 296 local
Markdown links, with its declared JSON/link/bounded credential-marker scope.
Whitespace checks passed. Final staged files and native CI are checked again
at publication; native check records remain authoritative for CI status.

The full Python candidate run exposed 15 additional introduced fixture-context failures: the existing recovery execution fixture did not supply the new namespace values to StrictUndefined rendering. Those fixture contexts were corrected without weakening template validation. The complete rerun passed 885 tests, with 300 root/host/Ansible prerequisite skips and 19 deprecation warnings (crypt and existing Jinja regex escapes). Those warnings do not claim installed proof or their own regression provenance. Earlier full-run failures were
introduced validation expectations: the workflow fixture evaluator lacked the
new `contains` expression, and its nominal drift fixture used a contract value
that had become current. Those fixtures were corrected; 23 targeted tests passed.
Lifecycle/socket qualification then passed 265 tests with 24 prerequisite skips;
12 upgrade-socket tests passed separately. Three protected bootstrap fixture tests
also passed under native WSL root using disposable fixture state and fake systemd,
not a live installation.

## Execution warnings and protected boundaries

Requested parent profile is `gpt-6.1-sol`, effort `ultra`, Subagents On. Actual
model/effort proof is unavailable from the exposed runtime and remains
`UNAVAILABLE`; requested values are not actual-value evidence. Three bounded
subagents were used, with fresh assignments and no nested Relay/model execution.

The startup title tool accepted the exact Task/Step title once. The available
readback truncates the title, so exact persisted title verification is unavailable;
no repeated rename was attempted. The original routing run `38144146016` and
check `114483871675` succeeded, with no annotations observed at startup. That
routing result does not prove implementation or TEST success.

Task 115's additional TEST-only authority was published as trusted Decision
[6110064799](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110064799)
and complete same-Step successor Request
[6110068398](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6110068398).
The protected PROD admission still binds original Request `6109630038`.
Read-only supported Writer `publication-state` confirmed that immutable binding;
no publication or journal edit was performed. Current installed schema-v3
manual publication revalidates current authority, so the successor creates a
likely `AUTHORITY_CHANGED` publication boundary. This is an inference from
verified installed source, not a claimed failed publication. No unsupported
rebinding, PROD upgrade, new execution or arbitrary retry is authorized.

Independent exact-head source acceptance, Task completion, allowed merge,
installation, production qualification and closure remain distinct boundaries.
Task 115 stays open. Any unavailable root/host/ingress/caller proof and material
execution warning remains a decision input even after a durable Git handoff.

## Bounded audit corrections before publication

A supplementary implementation audit found three candidate-introduced risks in
the new manual path. An implemented non-Git result attached to an open source PR
could publish successfully before its Ready transition failed permanently; it is
now rejected before reservation/publication under the existing exact-Git-head
lifecycle invariant. Each direct Draft/Ready reread now also verifies its admitted
Request/admission marker, preserving the old owner-source path's binding check.
The new socket factory explicitly uses `Slice=system.slice`, retaining the
existing lifecycle detector's cgroup path for children whose MainPID has exited;
[systemd's service contract](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.service.xml)
documents the otherwise implicit per-template slice. These are bounded source
corrections, not independent review or proof of installed behavior.
