# Package versioning and release lifecycle

Apply this protocol to package lifecycle decisions only when the owning project
has adopted it. Reading or installing this package, including updating its lock,
does not replace an existing project-owned versioning policy or activate newly
added normative topics. Existing consumers retain their canonical policy until
their own accepted adoption change reconciles duplicates and local bindings.
A newly adopting producer explicitly selects this protocol in its human-owned
AGENTS or equivalent guidance. This package grants no execution, merge, review,
publication or consumer-adoption authority.

## Contract and version classification

One version identifies the whole published package. Classify the effect on its
published consumer contract, including applicability, exceptions, routing,
authority, supported environments, recovery and mandatory operator work:

| Category | Effect |
| --- | --- |
| PATCH | Contract-preserving corrections or editorial repairs. No materially new mandatory controls or narrowed workflows. |
| MINOR | Compatible additions. A new protocol is additive only if existing consumers' mandatory behavior and local authority remain intact; availability is separate from adoption. |
| MAJOR | Incompatible behavior, removed exceptions, narrowed supported environments, materially new mandatory work, or automatic replacement of local authority. A new file can still be breaking. |

For stable `X.Y.Z`, major gives `(X+1).0.0`, minor gives `X.(Y+1).0`,
and patch gives `X.Y.(Z+1)`. Under `0.x`, the contract is experimental:
breaking development changes may increment the minor (`0.1.0` to `0.2.0`),
but must be disclosed as breaking. Patches still preserve the declared contract.
Choosing `1.0.0` explicitly declares the stable compatibility contract; subsequent
breaking changes require a major. Never imply compatibility solely from a file
addition, numerical label, or inability to inspect unknown private policies.

Explain the intended category and mandatory-work impact in the existing PR or
release decision; multiple edits require at least the highest-impact category.
Apply proportional controls to new release gates. Do not disguise mandatory
operator controls as fixes. Versioned README/payload documentation describes
stable version-scoped facts and dated provenance; current approval, publication
and task status lives in its authoritative Issue/PR, workflow, tags or registry.
Repair misleading frozen documentation in a later version, retaining history.

## Source integration and publication

Source commits, accepted snapshots, authored versions and actual publication
are different events. The producer owns its release cadence: per-PR bumping or
release-boundary bumping can both be legitimate. A dependency on this package
does not impose this repository's cadence, PR process or automation on consumers.

Use a stable version-independent authoring root, with the authored version in
its manifest. Routine bumps do not copy/rename entire source trees. Distribution
tags and installed versioned slots are separate layouts. Parallel PR numbers
are proposals, not reservations. Before integration, reconcile the intended
bump against the then-current accepted release baseline, re-evaluate impact,
resolve conflicts, and repeat the owning project's review/checks if the head
changes. Under a per-PR cadence, apply each PR's category sequentially; do not
blindly select the larger number or discard another PR's increment. For example,
from `1.95.0`, major then minor gives `2.0.0` then `2.1.0`; minor then major gives
`1.96.0` then `2.0.0`; two patches give `1.95.1` then `1.95.2`.
Distinct maintenance lines require a real need and their own accepted arrangement;
ordinary parallel tasks need no multi-merge mechanism or duplicate authoring trees.

A producer may explicitly authorize automatic publication through its existing
reviewed merge decision. Then qualify the actual accepted merge/squash commit
and publish its new version; a merge still does not prove publication succeeded.
Tooling/research/docs outside the package do not create releases. Package payload
changes cannot reuse a frozen version: detect this before integration and retain
the release-boundary check. Other producers may use separately admitted release
decisions; this protocol grants neither model by itself.

Published `(group, name, version)` content is immutable. Publish frozen releases
to new version tags. If that tag already exists, skip the publisher and report
a successful repeat without changing any ref, even if a retry's source differs.
That no-op is not proof that changed source was published; the source reuse check
and review remain necessary. If a new tag is absent and publishing fails, report
failure visibly and retry the same accepted source commit. Fix a release defect
forward in a new version, retaining the old release. Never force-move an existing
frozen tag. A new `1.9.8` maintenance release after `2.0.0` is valid when its own
source line is admitted: publication order need not be global SemVer order.
Distribution default-branch payload means last published, not highest SemVer.

Restrict publishing credentials to authorized maintainers/workflows. Authorized
writers can still make mistakes; source review alone does not prevent tag reuse.
Use the smallest reliable no-overwrite boundary, including concurrent publication
when the selected publisher can replace tags. No release ledger, orchestration
service, extra approval ritual or per-file reviewer hash recalculation is required.
Reviewers assess authority, compatibility, the change and existing focused evidence.
Trust normal package transport/install unless a demonstrated defect requires a
targeted workaround. Separate one-time integration qualification from routine
releases and incident diagnostics; report upstream defects rather than permanently
retesting the package manager for every consumer.

## Dependencies and consumer updates

A frozen release must not silently incorporate mutable/snapshot dependencies.
At release time inspect the resolved installed graph actually included in the
release: every included package, including transitives, must be frozen with a
resolved identity and tool-produced content hash. Unused optional dependencies
and development-only dependencies excluded from the release are outside this
closure; a dependency actually included is checked regardless of its label.
An explicit justified exception must identify the dependency, impact and
accepted compensating protection in the owning release decision. Do not create
a standing exception registry or infer the closure merely from top-level ranges.
Use existing manifest/lock/slot evidence; manual per-file hashes are unnecessary.
A package with no dependencies has an empty closure.

Consumers deliberately update their manifest/lock under local authority:

| Constraint | Intended compatibility window |
| --- | --- |
| `=X.Y.Z` | One exact version; useful for explicitly reviewed content. |
| `~X.Y.Z` | Patch-only acceptance within `X.Y`; appropriate when minor governance additions require review. |
| `^X.Y.Z` | For `X >= 1`, compatible versions below the next major. Use only if that broader contract is acceptable. |
| `^0.Y.Z` / `^0.0.Z` | Below `0.(Y+1).0` for `Y > 0`; for `0.0.Z`, below `0.0.(Z+1)`. Pre-1.0 caret is narrower. |

A lock pins selected exact versions/content hashes; a range does not itself
update an existing lock. Consumer update and newly available protocol adoption
are separately owned decisions. Choose constraints for actual compatibility,
avoiding needless exact constraints that make dependency diamonds unsatisfiable.
Unified resolution selects one version per identity, normally the newest feasible
version subject to the current lock. Incompatible major/exact branches of a
diamond fail; there is no nearest-wins or simultaneous-version fallback. Resolve
the conflicting contracts explicitly, preserving local authority and provenance.

## VibeVM 1.0.7 implementation

`[package].version` is canonical; workspace members can name a stable source
root. Set `frozen = true` for published releases. `frozen = false` denotes a
snapshot; `frozen = true` alone does not protect Git tags. The direct
`vibe registry publish PACKAGE --repo-url URL` publisher can replace an existing
version tag, so the producer must guard its own admitted publication boundary.
Direct Git distribution needs no central registry. `publish = false` in this
flow disables automatic workspace enumeration; it does not disable explicit
direct publication. Generated versioned `vibedeps` slots are consumer state.

Use `vibe install` and intentional `vibe update` with the consumer's selected
requirements and `vibe.lock`. Schema-7 lock entries carry selected versions and
`content_hash`; installed manifests carry `frozen`. Resolve and inspect the actual
included closure with existing tooling when dependencies exist. VibeVM does not
impose a Maven-like universal snapshot-release prohibition. Conditional boot
controls reading/applicability, not selective installation or policy exclusion.
