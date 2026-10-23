# Relay guidance source and delivery contract

The authored user manual is the
[Codex Relay Skill](../packages/codex-relay/skill/SKILL.md). Its
[workflow](../packages/codex-relay/skill/references/workflow.md),
[examples](../packages/codex-relay/skill/references/examples.md) and
[installation instructions](../packages/codex-relay/skill/references/installation.md)
own user actions. This document owns source maintenance and provenance;
[task-workflow.md](task-workflow.md) retains internal contract navigation.

## Version and provenance

Guidance **3.0.0** changes the native packaging contract: it removes the
bundled `references/shared` protocol tree and routes to the consuming project's
resolved Shared dependency instead. This removed path and changed routing make
it a major Relay release; the Shared package's major number does not determine
Relay's version. The standalone form retains its immutable Shared 4.0.0
snapshot. Both forms retain the same Relay product behavior.

The selected independently accepted Relay product-contract baseline is
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`. Exact schema/workflow/tool contract
files come from that immutable revision rather than candidate copies. Managed
pool ABI remains `relay-workflows-v4`; SERIAL remains `relay-workflows-v3`.
Current authority v4 and retained admitted v3/legacy attempts stay distinct.
This delivery change does not change deployed runtime semantics.

Independent exact-head acceptance and merge establish the first-party source
release. Before independent acceptance, 3.0.0 is a candidate. Native source
self-adoption travels with the accepted commit; it is neither external package
publication nor another consumer's adoption. Frozen accepted registry payloads,
including 2.0.1, remain unchanged. New output does not rewrite historical
admission, Outcome, review or publication identities.

[guidance/source.json](../guidance/source.json) separates the native Shared
SemVer requirement from the standalone snapshot and its exact identities:

| Identity | Selected value |
| --- | --- |
| Standalone Shared coordinate/version | `org.jresearch.ai/development-governance` `4.0.0` |
| Accepted producer source | `99034dd708e5d0201060986b561ada4d2cffd453` |
| Public distribution commit | `f14da40725cd35fb3117ae84a506256505340787` |
| Complete native distribution tree hash | `sha256:d27a004b5f2dcc8ae0f7fd33289d97be1eab84ddbdf54d7e880cc6def7ad3746` |

[AGENTS](../AGENTS.md) adopts all nine applicable complete topics;
[ownership bindings](relay-guidance-ownership.md) retain product-specific
Task/Decision/CR, admission, Writer/Reviewer, exact-result and protected-operation
mechanics. Shared protocol presence alone does not adopt them for another
consumer. Package versioning and frozen distribution meaning belong to the
pinned [Package Versioning protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/4.0.0/vibevm/vibespecs/protocols/package-versioning.md).
Native release and qualification mechanisms remain here and in
[self-adoption](self-adoption.md).

Both delivery forms derive from one authored manual and contain the same
product schemas and contract baseline. Their complete trees differ deliberately.
Standalone includes the attributed immutable Shared payload/receipt. Native
contains `references/shared-protocols.md`, which directs readers to the
consumer's reviewed `vibe.lock`, resolved versioned Shared slot and complete
required protocols. Native has no competing fixed protocol bundle or fixed
4.0.0 JIT route. This is local file navigation, not a runtime resolver.

`PROVENANCE.json` identifies its delivery form and binds the accepted product
contract, authored input hashes and generated files. Standalone provenance
identifies its included snapshot; native provenance identifies the dependency
requirement without pretending that the producer selected every consumer's
lock. The consumer's own native lock and installed metadata identify its actual
selection. The enclosing Git commit identifies the guidance artifact; the
receipt does not assert that its enclosing candidate is already accepted.

## Authoring and qualification

Edit `packages/codex-relay/skill` for user wording and `guidance/source.json` for
selected versions/identities and native compatibility requirement. The
deterministic builder copies exact accepted schemas and workflow/tool contracts
into `guidance/artifacts/standalone/codex-relay` and `guidance/artifacts/vpm`.
It adds the Shared snapshot and optional projector only to standalone, and
emits delivery-specific `references/shared-protocols.md` routes. Do not hand-edit those outputs. Native VibeVM remains
the resolver and Skill projector.

The manual's installation-preparation path binds the accepted
[deployment contract](../deploy/README.md#per-repository-installation-preparation):
per-owner-managed-target proposals, actual managed-pool configuration and
separate generation, authorized publication and activation. Maintain these
product bindings together with affected workflow changes.

Producer/candidate governance follows the pinned complete
[Self Adoption protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/4.0.0/vibevm/vibespecs/protocols/self-adoption.md)
and [native accepted-source binding](self-adoption.md#accepted-source-binding-and-ordinary-use).
Use the existing Task/PR and checks:

```sh
python3 scripts/build-relay-guidance.py
python3 scripts/build-relay-guidance.py --check
python3 scripts/test-relay-guidance.py
python3 scripts/qualify-vibevm.py
python3 scripts/test-qualify-vibevm.py
python3 scripts/qualify-relay-guidance-vpm.py --vibe /absolute/path/to/verified/vibe
python3 scripts/qualify-relay-skill-client.py --codex /absolute/path/to/codex --skill guidance/artifacts/standalone/codex-relay
```

Also use native self-adoption qualification and the applicable complete candidate
checks. The builder is deterministic and offline; native VPM qualification uses
isolated fixtures and immutable acquisition with explicit update/rollback,
without publication. The [client contract](relay-skill-client-qualification.md)
distinguishes discovery/parser checks and bounded behavioral evaluation from
model compliance. Candidate results belong in its native checks, PR and Outcome.
Unsupported clients, missing actual projection and installed-runtime behavior
remain evidence gaps until qualified; source acceptance supplies no deployed
runtime or external publication proof.

## Deliberate Shared dependency updates

The [compatibility assessment](relay-skill-compatibility.md) justifies the native
lower bound from required protocol semantics and their accepted history, not a
package major number. The supported VibeVM SemVer
requirement permits one resolved dependency to satisfy the consumer and Relay.
It does not silently adopt topics or guarantee compatibility with unknown
future releases. Relay's own root policy deliberately remains on Shared 4.0.0;
a consumer that has deliberately adopted Shared 5.0.0 keeps its own selection.

On an intentional Shared update, assess changes in actually used protocols,
including applicability, exceptions and Relay bindings. A compatible or
irrelevant change updates the consumer's manifest/lock as needed; it does not
require a new Relay Skill version or a release decision in the Shared producer.
A material change requiring different Relay behavior, guidance, interfaces or
packaging needs a corresponding Relay correction and version. Keep exact
source/lock/slot identity for rollback and read committed files during execution.
Do not resolve `latest`. The standalone snapshot changes only through a new
immutable Relay artifact with its own provenance.

## Shared Publisher and immutable publication

Task #169 owns the historical 2.0.1 publisher integration and publication
evidence. This change reuses that accepted mechanism for a new immutable
version; it neither replays that Task nor rewrites earlier versions.

`vibe-publisher.json` binds the explicit public export inventory, MIT rights
reference, source repository ID, Public CI workflow and sole destination
`https://github.com/jrs-vibevm/org.jresearch.ai.codex-relay.git`.
The thin `Publish accepted Relay guidance` caller invokes the reusable
[Shared Publisher](https://github.com/jresearchsoftware/shared-governance/blob/5a1e5de66388501235fc9ffd23d45efb34df2b85/docs/shared-publisher.md)
at full accepted pin `5a1e5de66388501235fc9ffd23d45efb34df2b85` after successful
Public CI for the exact main push. It passes only that triggering SHA, binding
and coordinate; the named `DEVELOPMENT_GOVERNANCE_PUBLISH_TOKEN` is provided
only to the shared publisher's isolated finalization. No local release engine,
selector or duplicate publisher is installed. Unprivileged Public CI uses that
same pinned implementation to check candidate source before acceptance.

A reviewed, owner-authorized merge uses the existing successful-main source
transition path. `initial_publication` is not selected for this new payload.
An unchanged/non-package commit is a strict `NO_PACKAGE_CHANGE`, including
later binding-only edits; it cannot opportunistically publish old source.
A consumer-only Shared update creates no Relay release or new publisher gate.

The deterministic builder includes `guidance/dependency-closure`'s native
schema-7 lock and complete frozen Shared slot in the public VPM export solely
as release-closure evidence required by the accepted publisher. These nested
files are not the consumer's root lock, an active boot route or a fallback
protocol source. The projected native Skill includes no Shared protocol tree. These
were generated by pinned VibeVM 1.0.7 from
`guidance/dependency-closure.toml.in` in isolated storage with
`vibe --json install --no-default-registry --assume-yes`. For deliberate
maintenance, use that template as the isolated project's `vibe.toml`, inspect
its resolved source/hash and slot, then copy only native `vibe.lock` and
`vibevm/vibedeps` into the closure input. Preserve the deliberately selected immutable
closure identity and review the input/export diff together. This producer
release evidence is separate from another consumer's selected Shared lock; the
native Skill reads that consumer's authoritative slot. Native timestamps
are retained provenance; ordinary offline builds copy the committed input
bytes reproducibly. Native publication neither resolves nor repairs closure.
The standalone Skill and VPM `skill/` differ in shared routing, included
snapshot and delivery-specific provenance; product contract parity remains
required.

After independent exact-head approval and owner-authorized squash merge,
verify the main-push CI and publisher run, immutable `v3.0.0` tag, public
`DISTRIBUTION.json`, package files/digests and a native external consumer
acquisition using `vpm-consumer.toml.in` with the confirmed URL and immutable
distribution commit. Source acceptance and local fixture success do not prove
publication, token write permission or external acquisition. The Issue remains
open until those real results satisfy its completion conditions.

For a failed release, preserve the exact failed accepted source SHA and
publisher implementation pin. Use `Publish accepted Relay guidance`'s
same-source retry input on main; it rechecks first-parent membership and
matching completed push CI. Do not retry against current main or rewrite a
version tag. An existing tag is a safe no-op, not proof a different source was
published; compare its files/receipt before claiming recovery. If current main
has changed the publisher pin, reconcile the original supported same-pin replay
before dispatch. Missing destination access/rights remains an owner setup
boundary; never create tokens, broaden permissions or select another repository.
Consumer install, update, rollback, drift and removal stay on the existing
standalone/native paths in the Skill's installation reference.
