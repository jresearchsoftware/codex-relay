# Task 199 execution-state simplification

Task: <https://github.com/jresearchsoftware/codex-relay/issues/199>.
Accepted implementation/governance baseline:
`512b2b5ea2867b92958580f17f6aee24c23b1fba`.
The candidate's canonical Outcome and native checks own its final execution
results; this document records the source assessment and qualification scope.

## Manual and automatic execution

Both routes resolve the same Task authority and allocate one execution Step.
Manual work hands the admitted identity to the owner executor and accepts a
bounded result claim through Writer. Automatic work additionally reserves a
physical slot, launches a credential-free worker, contains it, preserves its
collection and asks Writer to import/publish the result. Those additions protect
real process, filesystem and publication effects; they need no second Task
history. Investigation, corrections and tests remain inside that execution.
Clearing the latest obstacle returns work to the complete effective Task goal.

Task #57 is still an unlaunched audit with no published findings at the source
assessment date. Its relevant questions about duplicated history, upgrade gates
and recovery cost informed this assessment; implementation authority is #199.

## State inventory and disposition

| Existing surface | Concrete purpose | Candidate disposition |
| --- | --- | --- |
| GitHub Issue/Decisions/PR/reviews/Outcome | Durable Task authority, history and independent acceptance | Remains canonical. No new local Task ledger. |
| Writer `publication-v2` records | Immutable admission/Step, consumed event, exact mutation intentions, result and publication recovery | Retained unchanged. Idle lifecycle reads original identity and current effects; it no longer requires old Task closure or a new historical disposition. |
| Runner per-attempt journals and collected work | Execution ownership, child/containment and preserved source | Retained. Unknown execution or missing proof still holds the affected resource. Complete trusted controller receipts do not require an obsolete journal again. |
| `admission-v1` / `admission-pool-v1` | Installation-scoped quiesce/drain, operation UUID, selected target and verified resume | Retained separately from Task history under the existing Writer lock. |
| SERIAL-to-pool compatibility receipt and frozen original consumer/source | Original namespace, envelope and resource ownership; supported old recovery | Retained. Old pool rows can be structurally read for lineage/effects, while old-digest mutation and execution remain forbidden. |
| `historical-manual-dispositions-v1` and native Task reader | Optional historical interpretation/diagnosis | Removed from the normal installed admission/status/transition factory. Existing expert adapter/cache remain available with their original freshness rules when explicitly used. |
| PR lifecycle receipts | Pending exact native CR/head Draft or Ready effect | Retained; a PR state projection supplies no execution or merge authority. |
| Publication/prepublication recovery records | Frozen original operation, intended bytes and ambiguous native effects | Retained. Incomplete or uncertain recovery still prevents full drain; no blind mutation retry. |
| Reviewer SQLite publication reservations | Decisive POST identity, frozen review meaning and auxiliary check recovery | Unchanged; Reviewer remains separate from owner integration and Writer publication. |
| Cross-repository publication namespaces, resource slots and locks | Prevent resource/ref collisions without treating unrelated Task history as active work | Retained. Global lifecycle observes concrete effects; scoped admission excludes proven unrelated resources before dependent reads. |
| Owner continuation effect journal | Reserve/reconcile one exact approval-bound squash effect | One compact owner-local operation per native approval, using existing atomic-write/lock primitives. It is never a prerequisite for admitting an unrelated Task or upgrading Relay. |

An untouched structurally valid manual handoff with no matching journal or
pending result/publication effect is nonblocking. Its historical execution is
still unknown. The candidate writes no cancellation, negative-start proof,
fictional Outcome or historical acknowledgement. Completed records, native
authority, original source and recovery identities are not rewritten or deleted.

The current and preserved original SERIAL classifiers both retain pending
relationship/readiness/success-Outcome/ready-consumption effects. Malformed
terminal receipts remain unresolved. Physical containment/collection can release
a slot before publication completes; the exact ref/PR and global lifecycle keep
their separate publication guard.

## Owner continuation boundary

The previous exported helper had no operational caller/native ports. The
candidate adds an authenticated owner one-shot command and real GitHub read,
reservation, guarded squash and readback ports. The Reviewer still only publishes
review/check evidence. The owner orchestration passes its transient semantic
assessment bound to the exact authority/review/head, then the command independently
verifies native facts. The merge-only mode does not invent Task completion or
perform Issue closure/follow-up execution.

A connected Reviewer call cannot itself launch a local process. The supported
owner sequence is verified publication (or exact original publication recovery),
then the owner command without another merge question. A caller lacking that
configured command/transport has an explicit capability boundary. Source tests
alone do not establish remote client wiring or installed TEST behavior.

## Guidance and environment evidence

The project selects immutable Shared Governance 7.0.1, with complete payload and
semantic assessment in [the compatibility contract](../relay-skill-compatibility.md).
The original 7.0.0 slot is retained as inactive evidence. Native VibeVM reports an
orphan-slot warning for that deliberate preservation; active routes select only
7.0.1. Relay Skill 4.2.0 is a separate compatible workflow addition; frozen 4.1.1
registry bytes and standalone Shared 5.0.0 remain unchanged.

The routine official CLI comparison on 2026-11-08 found selected 0.167.0 equal to
the latest stable [official release](https://github.com/openai/codex/releases/tag/rust-v0.167.0).
No CLI bump or capability-review claim is introduced.

Initial nonroot deployment tests on WSL encountered a host `/tmp` that was not
writable by the test UID. The observed failures and their resolution remain
execution evidence; they are not relabeled as a passing run. A private Linux
mount namespace supplies ordinary tmpfs `/tmp` semantics for the final tests
without changing the workstation's global directory or weakening assertions.
Root-dependent skips and any remaining installed/client limitations must be
reported with the final result.

Generated ChatGPT Instructions differ. Generation and a subsequent NO_OP check
do not prove live Settings application. TH-029 reconciliation remains an
owner-reviewed/manual action after source acceptance/integration.
