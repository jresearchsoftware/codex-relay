# Task 189 Step 2: restrictive worker source collection

Authority: [Task 189](https://github.com/jresearchsoftware/codex-relay/issues/189),
[reopening Decision](https://github.com/jresearchsoftware/codex-relay/issues/189#issuecomment-6386486969)
and [starting-state Decision](https://github.com/jresearchsoftware/codex-relay/issues/189#issuecomment-6386566315).
Manual admission: `run-40111095914`, Step 2, digest
`f4341c04e9216d32ffb942e0b6f78a2637b0179474600f0b2cf1afcd6dbf5e41`.
Accepted starting source: `ecbdf25e81e8e57901a895de3b03d9b21f0bbe95`.

## Problem and implemented boundary

The accepted Step 1 diagnosis and deployment stand. Its successful private-mode
negative fixture demonstrated the remaining product gap: a completed worker
could create ordinary task source that the separate runner UID could not read.
Group defaults cannot overcome explicit modes, ACLs or atomic replacement.
The reopening Decision expressly authorizes bounded privileged reads of this
task-owned checkout, superseding the earlier mandatory-denial restriction.

Automatic routing now requests `collect-progress` through the existing fixed
root Writer. Writer independently reads the admission-derived runner journal,
checks its exact envelope digest and returned/contained execution, rejects
terminal ordinary attempts, and derives the checkout from its own admission.
The caller cannot select a path, UID, executable or containment assertion.
It reuses the existing retained-source collector and returns the existing
bounded observation/bundle. No new sudo command, ACL repair, source permission
change, exclusion list, persistent collection ledger or worker elevation is added.
Only collection receipts may exceed the ordinary 1 MiB transport limit, within
the existing 145 MiB bundle-transport bound.

Directory descriptors, no-follow reads, same-device/single-link regular-file
checks and byte/entry/depth bounds remain enforced. Symlink targets are not
opened. Git runs only in a fresh trusted repository with imported bounded object
bytes, never against worker config, hooks, index, filters or alternates. Writer
still validates commit ownership, paths/modes and every introduced blob before
normal non-force publication. Root filesystem access does not grant publication
of arbitrary source or access to outside-workspace credentials.

Read-only recollection can reconcile an existing publication intent; it does
not authorize another push. Explicit publication recovery uses the same reader
with the original native owner recovery authorization, contained successful
execution, original collection head and exact recovered candidate. Consumed
uncertain recovery remains blocked; published recovery may recollect only its
exact stored result. Historical prepublication recovery retains its own gates.

[Issue 171](https://github.com/jresearchsoftware/codex-relay/issues/171) and its
Decisions were read before implementation. Its earlier group-inheritance repair
is retained. The newer Owner Decision selects 189 for this continuation; this
change neither launches duplicate 171 work nor closes or rewrites that Issue.

## Real native installed TEST proof

The exclusively allocated `codex-relay-test` namespace initially had an open
gate, `active=[]`, `unknown=[]` and no pending operation. The public upgrade
passed from `c01c42d264cacccce2e84d756c4b59ed380e7c28` to implementation commit
`22251da11b98a486f8e062bc2f778dbd55f96397`, with matching workflow projection,
same-operation installed verification and gate resume. TEST consumer commit:
`a55ac356310588b961f0da9625c1d323b3974c2e`. Existing compatible projected workflow
bytes required no additional changes. Configured running capacity remained two;
the 32 provisioned slot definitions are not 32 executing workers.

A fresh genuine owner command admitted [TEST Task 84](https://github.com/jresearchsoftware/codex-relay-testbed/issues/84),
Step 1, [run 40114725055](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/40114725055),
slot `pool-2`. The worker implemented and committed a public Python generator,
tests and actual generated index using private temporary-file creation and
atomic replacement. It deliberately left the final nested source private.

- Protected runner journal: child started, returned, containment `reaped`;
  collection `clean=true`, `preserved=true`, diagnostic `null`.
- Retained `fixtures/task189-private` and `nested` directories: UID 978,
  GID 973, mode `0700`. Final `nested/INDEX.md`: UID 978/GID 973, mode `0600`.
- Post-collection ordinary runner identity UID 980/GID 976 still receives
  access denial reading that source. No chmod/chown repair was performed.
  Root readback verifies the exact required public content; SHA-256
  `04bb2d0bd915fc9827b525023ac951106feaa6fc64ff13522591e0ae68ad23c5`.
- One Writer publication produced [PR 85](https://github.com/jresearchsoftware/codex-relay-testbed/pull/85)
  at `5537caeb219fc2ab759940e826c3181c8f18a019` and canonical
  [Outcome 6387124269](https://github.com/jresearchsoftware/codex-relay-testbed/pull/85#issuecomment-6387124269).
  Protected body SHA-256:
  `59c7a9fabdeae886aa33683686da8999698ac11f0bab7a0296346c0bca94c08d`.
  Native PR readback verified `draft=false` at that same head.
- [Exact-head TEST CI 40114918412](https://github.com/jresearchsoftware/codex-relay-testbed/actions/runs/40114918412)
  passed. Supported Reviewer evidence verified both target bindings and all
  required warning surfaces, with `none_observed`. UI-only service/pre-execution
  surfaces remain excluded; this is no claim about uninspected UI banners.

The worker mentioned launcher `.codex-sandbox/` residue. Complete collection was
clean and host readback found that sandbox absent after finalization; the claim
does not establish leftover source or a collector exclusion.

TEST admission inherited `gpt-6.1-sol / xhigh`, Subagents On from configured
defaults. The fixture's prose budget recommended medium/Off but supplied no
trusted profile amendment. The original admission was preserved without replay
or a substitute profile; actual backend model/effort remains `UNAVAILABLE`.
This budget-authoring limitation affects cost, not the demonstrated filesystem
and publication result. The parent profile remains unchanged.

Handback retains the verified TEST installation, open gate, capacity two,
`active=[]`, `unknown=[]` and completed controller/handoff. TEST fixture PR/Issue
remain open and unapproved. No original failed worker was replayed, historical
Outcome changed, product PR merged or PROD installation performed. TEST uses
different actors, repositories, App/runner resources and source from PROD;
its success does not establish PROD adoption or repair.

## Validation and remaining acceptance

Native Linux source validation: `npm test` 1218 passed / 7 conditional skips;
deployment pytest 1432 passed / 371 conditional skips; Rust fmt and 159 locked
tests passed; three-consumer qualification, tracked candidate scan and whitespace
checks passed. Pytest reported the same 19 passlib/Jinja2 deprecation warnings;
these do not change source correctness or the installed operational proof.
The complete 19-test privileged collection group passed under Linux root with
actual distinct identities. It covers private atomic replacement, named-user
POSIX ACL denial, symlinks/hard links, unchanged source metadata, historical
ordinary-UID denials, read-only scratch and recovery without worker replay.
An additional targeted depth-limit assertion also passed with 129 private
nested directories. These tests do not grant host-wide filesystem authority.

The later report and depth-test additions do not change the executable modules
qualified at installed `22251da...`. Final exact-head native CI and independent
review bind the complete PR. One bounded implementation-helper audit checked
the collection/recovery boundary; it supplies no native independent acceptance.
The canonical parent Outcome identifies the final source head and checks.

Implementation and TEST qualification do not complete Task 189's closure gates:
independent exact-head approval, authorized integration, owner-triggered PROD
Apply and relevant installed operational verification remain separate.
