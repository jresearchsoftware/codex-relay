# Task 243 Step 1: owner-run admission investigation

## Finding and limits

The failed predicate in Shared Governance run **43448389613** cannot be
reconstructed from the available evidence. No specific race, consumer setting
error, caller error or admission regression is established. The change adds a
bounded categorical diagnostic at the existing rejection surface; it does not
claim to fix the historical cause or complete Shared Governance Task 96.

The admitted Relay source is `479e38f306d9a0c616da6a322911a17db4a78944`.
The relevant `live-authority.mjs` and `launch-metadata.mjs` are unchanged from
the logged installed source `93a48523ac0dc6310171ae39945497b83b017d8a`.
The command-only title `Auto implementation · Task 96 · codex-ready-auto`
passes the existing matcher. A synthetic incident-shaped admission test
confirms that title without adding a Step to the native run name.

## Native evidence inspected on 2026-11-13

- [Original Issue events](https://api.github.com/repos/jresearchsoftware/shared-governance/issues/96/events?per_page=100):
  ready event `36041464753`, owner `foal`, `codex-ready-auto`,
  `2026-11-13T15:01:29Z`.
- [Original run](https://github.com/jresearchsoftware/shared-governance/actions/runs/43448389613):
  created `15:01:32Z`, first attempt, Issue event, branch `main`, actor and
  triggering actor `foal`, configured routing workflow path, command-only title.
  Later native readback reports `completed` / `success`; it is not the
  contemporaneous response observed by the admission guard.
- [Route job](https://github.com/jresearchsoftware/shared-governance/actions/runs/43448389613/job/131963758416):
  pool-6, logged installed source `93a48523`, workflow source `0b72349f`,
  rejection at `15:01:39Z`. The log exposes only `OWNER_RUN_NOT_ADMITTED`.
  The check's single execution annotation is the same BLOCKED warning and
  incorrectly points to a terminal Outcome that this unbound path cannot create.
- [Exact consumer workflow](https://github.com/jresearchsoftware/shared-governance/blob/0b72349f3ab0b2d88e836a6ba3d4fc675a87f75a/.github/workflows/codex-relay-routing.yml):
  the Issue expression generates the observed title and invokes the installed
  routing entrypoint under workflow contract v4.
- The [Task charter](https://github.com/jresearchsoftware/codex-relay/issues/243)
  retains the earlier branch-selection failure and corrected Decision as
  distinct historical evidence. This rejection is before Task authority
  resolution and does not establish another branch-selection error.

Protected consumer configuration and the original admission-time API response
were not available through the exposed connected owner tools. No protected
diagnostic stream was read or published. The public run/annotation evidence
does not identify which predicate failed; later readback cannot fill that gap.
The GitHub connector rejected its check-suite subresource URL, so the native
read-only `gh api` path was used for the check and its annotations.

## Implemented behavior

The guard preserves every predicate, its order and existing optional
`triggering_actor` semantics. A rejection carries its first failed predicate
as allowlisted `reason` through privileged Writer serialization, the local
adapter and routing JSON/Actions warning. Categories are documented in the
[controller contract](../../controller/README.md). No raw expected/observed
values, private configuration, arbitrary helper text or credentials are added.
Old helpers without a reason remain supported; unknown reasons are discarded.

An unbound rejection still reserves nothing, consumes no ready command,
starts no worker and authorizes no target-bound Outcome. The Actions wrapper
continues to return success for this handled domain stop. Its warning now
directs inspection of the original run and configured expectations and states
that no worker or target-bound Outcome was authorized. This is a diagnostic
correction explicitly within the charter, not a new approval or retry flow.
The owning controller guidance changes in the same PR; the product manual's
existing admission and publication routes require no new operator procedure.

## Validation and continuation boundary

Focused tests cover each predicate, first-failure order, realistic run statuses,
native target/title binding, no mutations on refusal, supported command-only
Task 96 admission, ready-event revalidation, and the complete helper-to-routing
diagnostic path including legacy and invalid reason inputs. Full candidate
validation is recorded with the final executor result and native PR checks.
These synthetic checks do not reconstruct the original API response or qualify
an installed host.

The independent Linux checkout, temporary files, Cargo cache and build outputs
belong exclusively to run-43453703128. No installed runner slot, shared TEST
installation, PROD service, credential or consumer run was changed or retried.
The routine [CLI maintenance assessment](../codex/cli-integration.md#task-243-routine-maintenance)
retains qualified 0.167.2 because the stable candidate changes project trust.

Any installation of this diagnostic requires independent exact-head source
acceptance and separately authorized owner Apply. Shared Governance owns a
future continuation command and its preserved PR 97. Do not replay the original
run or use this report as admission authority. If the refusal recurs after an
authorized update, its categorical reason can guide the corresponding native
run/configuration comparison without weakening the guard. No historical cause
or receiving-project completion is claimed.
