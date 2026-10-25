# Relay guidance source and delivery contract

The authored user manual is the
[Codex Relay Skill](../packages/codex-relay/skill/SKILL.md). Its
[workflow](../packages/codex-relay/skill/references/workflow.md),
[examples](../packages/codex-relay/skill/references/examples.md) and
[installation instructions](../packages/codex-relay/skill/references/installation.md)
own user actions. This document owns source maintenance and provenance;
[task-workflow.md](task-workflow.md) retains internal contract navigation.

## Version and provenance

Guidance **4.1.0** is a compatible additive candidate for the Task #63 ordinary
intent-driven installation and private Git-pair Apply guidance. Existing expert
phases and other consumers' owner-file/checkout paths remain supported. No
mandatory private repository is imposed on public consumers. The new wording
adds post-install integration artifacts, same-operation config changes and safe
cutover boundaries without granting deployment or external policy authority.
Source support still needs independently accepted compatible product installation
and qualification; this guidance candidate does not claim PROD cutover.

Frozen accepted **4.0.0** registry bytes remain unchanged. The bundled Task
authority schemas and SERIAL/parallel workflow identities retain their exact
accepted `61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4` contract pin; Task #63 changes
installer composition rather than those protocol identities. Candidate
installation wording is not a claim that the older pinned product already
implements the new installer. Native source self-adoption uses a new 4.1.0
identity and does not publish a package or activate any service.

Guidance **4.0.0** ships the immutable Shared Governance 5.0.0 standalone
snapshot and clarifies the existing
[manual result PR Step-label procedure](../packages/codex-relay/skill/references/workflow.md#manual-result-pr-step-labels).
Under PV-002/PV-004 the whole package is **MAJOR** against frozen 3.1.0:
the shipped `references/shared/tools/chatgpt/project.py` no longer writes or
uses ownership receipts, changes its status schema from 2 to 4 and replaces
the old refusal of edited generated outputs with source-reviewed regeneration.
Those documented bundled helper interfaces change even though native Relay
protocol consumption remains compatible. This classification follows the actual
payload contract, not Shared's major number. The optional helper's
[upstream instructions](../guidance/artifacts/standalone/codex-relay/references/shared/tools/chatgpt/README.md)
describe its changed maintenance path. Relay's own standalone installer and
native Skill receipts retain their contracts; no live settings are applied.

The Step-label clarification itself is a patch: it carries the accepted interim
manual executor responsibility into the canonical manual without a runtime gate,
new permission or materially new mandatory operator work. Automatic Step/title
projection remains Task #177's separate work. Native Shared compatibility stays
`>=2.5.0` with consumer-owned exact selection. The standalone snapshot and nested
publisher closure evidence use Shared 5.0.0. Frozen accepted 3.1.0 and earlier
payloads remain unchanged; the unaccepted 3.1.1 candidate is replaced by 4.0.0.

Guidance **3.1.0** added the compatible explicit v4 manual publication path: no
PR-body admission digest or unrelated-PR scan. This is a minor expansion of the
supported workflow, with no new mandatory owner action. The accepted 3.0.0
registry remains immutable. Source acceptance does not deploy Writer.

Guidance **3.0.0** changed the native packaging contract: it removes the
bundled `references/shared` protocol tree and routes to the consuming project's
resolved Shared dependency instead. This removed path and changed routing make
it a major Relay release; the Shared package's major number does not determine
Relay's version. That release's standalone form retains its immutable Shared
4.0.0 snapshot. Both forms retain the same Relay product behavior.

The selected independently accepted Relay product-contract baseline is
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`. Exact schema/workflow/tool contract
files come from that immutable revision rather than candidate copies. Managed
pool ABI remains `relay-workflows-v4`; SERIAL remains `relay-workflows-v3`.
Current authority v4 and retained admitted v3/legacy attempts stay distinct.
This delivery change does not change deployed runtime semantics.

Independent exact-head acceptance and merge establish the first-party source
release. Before independent acceptance, 4.1.0 is a candidate. Native source
self-adoption travels with the accepted commit; it is neither external package
publication nor another consumer's adoption. Frozen accepted registry payloads,
including 2.0.1, remain unchanged. New output does not rewrite historical
admission, Outcome, review or publication identities.

[guidance/source.json](../guidance/source.json) separates the native Shared
SemVer requirement from the standalone snapshot and its exact identities:

| Identity | Selected value |
| --- | --- |
| Standalone Shared coordinate/version | `org.jresearch.ai/development-governance` `5.0.0` |
| Accepted producer source | `d0b3d67ef94a5537ebd4a2bbf4a38e3a6629c0c9` |
| Public distribution commit | `30a23f467c30c41fec918204cbbf2ecfffd7bef5` |
| Complete native distribution tree hash | `sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9` |

[AGENTS](../AGENTS.md) adopts all nine applicable complete topics;
[ownership bindings](relay-guidance-ownership.md) retain product-specific
Task/Decision/CR, admission, Writer/Reviewer, exact-result and protected-operation
mechanics. Shared protocol presence alone does not adopt them for another
consumer. Package versioning and frozen distribution meaning belong to the
pinned [Package Versioning protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/package-versioning.md).
Native release and qualification mechanisms remain here and in
[self-adoption](self-adoption.md).

Both delivery forms derive from one authored manual and contain the same
product schemas and contract baseline. Their complete trees differ deliberately.
Standalone includes the attributed immutable Shared payload/receipt. Native
contains `references/shared-protocols.md`, which directs readers to the
consumer's reviewed `vibe.lock`, resolved versioned Shared slot and complete
required protocols. Native has no competing fixed protocol bundle or producer-pinned
JIT route. This is local file navigation, not a runtime resolver.

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

The manual's installation-preparation path binds the selected
[deployment contract](../deploy/README.md#per-repository-installation-preparation):
actual managed-pool configuration, complete consumer/private deployment output
trees, and separate authorized publication and activation. The ordinary
installer requires no pre-install workflow publication. Maintain these
product bindings together with affected workflow changes.

Producer/candidate governance follows the pinned complete
[Self Adoption protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/self-adoption.md)
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
future releases. Relay's own root policy, new standalone snapshot and
release-closure evidence select Shared 5.0.0. Other consumers
retain their own deliberate selections.

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

Tasks #169, #174 and #179 retain their historical integration, release and
qualification evidence. Task #184 migrates the current publisher integration;
it changes no frozen package bytes, selected Shared protocols or package version
and does not itself produce a Relay release.

`vibe-publisher.json` binds the explicit public export inventory, MIT rights
reference, source repository ID, Public CI workflow and sole destination
`https://github.com/jrs-vibevm/org.jresearch.ai.codex-relay.git`.
The thin `Publish accepted Relay guidance` caller invokes
`jresearchsoftware/shared-governance/.github/workflows/vibe-publisher.yml@main`
after successful Public CI for the exact main push. The
[accepted Shared Publisher contract](https://github.com/jresearchsoftware/shared-governance/blob/414077e956aa47b18ddc436f68c3245b508baf46/docs/shared-publisher.md)
distinguishes the independently selected producer source from the executing
publisher. Pass only the triggering accepted source SHA, binding and coordinate;
there is no caller publisher-selection input. Each execution uses
`job.workflow_repository` and `job.workflow_sha` to check out its own exact
publisher implementation, checks out the producer independently at `source_sha`,
and reports both immutable identities. Moving publisher main does not change
the producer source being released. Unprivileged Public CI checks exact candidate
source with an independently identified accepted publisher checkout.

`scripts/test-relay-publisher.py` exercises that selected implementation with
exact Relay source and disposable transitions. Its `--publisher-sha` asserts
the resolved checkout, rather than choosing another implementation. For the
optional native export/install fixture, use the same recorded publisher SHA
and the native binary verified against that checkout's `toolchain/vibevm.json`:

```sh
python3 scripts/qualify-relay-publisher.py --publisher /path/to/accepted/shared-governance \
  --publisher-sha RESOLVED_PUBLISHER_SHA --source-ref EXACT_RELAY_SOURCE_SHA \
  --vibe /path/to/verified/vibe
```

This fixture uses synthetic readiness and local distribution writes only; it
does not prove source CI acceptance or live publication.

The named `DEVELOPMENT_GOVERNANCE_PUBLISH_TOKEN` is supplied only to isolated
shared-publisher finalization, never through `secrets: inherit`. No local release
engine or duplicate publisher is installed. Public-file approval, redistribution
rights and the producer binding remain source-owned. The publisher rechecks
exact source-main membership, matching successful completed push CI and the
triggering run where applicable. It stages without publication credentials and
publishes main and a new version tag with one atomic non-force push; existing
tags stay immutable.

A reviewed, owner-authorized merge uses the existing successful-main source
transition path. `initial_publication` is not selected for ordinary new releases.
An unchanged/non-package commit is a strict `NO_PACKAGE_CHANGE`, including
binding-only edits that retain the export inventory and package mapping; it
cannot opportunistically publish old source.
A consumer-only Shared update creates no Relay release or new publisher gate.

The current tree-v1 contract qualifies required direct/transitive dependency
closure from a native schema-7 `vibe.lock` and complete frozen versioned Shared
slots committed beneath the package root at the exact producer source SHA.
These source-time qualification inputs need not appear in the export inventory
or public payload. Only explicitly approved files are exported. Deliberate
vendoring remains supported, but exported slots must include their complete
shipped inventories; unexported files cannot complete a partial export.

Relay's existing frozen payloads deliberately include
`guidance/dependency-closure`'s lock and Shared slot as nested public release
evidence. Their inventory and bytes remain immutable. The old publisher's export
requirement is historical, not a current universal requirement. A future thin
Relay package that omits this evidence needs separate authorized packaging work
and a new appropriately classified version; this integration migration does not
make that change. The nested evidence is not the consumer's root lock, active
boot route or fallback protocol source. The projected native Skill includes no
Shared protocol tree and reads the consumer's authoritative selected slot.

The closure inputs were generated by pinned VibeVM 1.0.7 from
`guidance/dependency-closure.toml.in` in isolated storage with
`vibe --json install --no-default-registry --assume-yes`. For deliberate future
maintenance, use that template as the isolated project's `vibe.toml`, inspect
its resolved source/hash and slot, then copy only native `vibe.lock` and
`vibevm/vibedeps` into the closure input. Review any authorized input/export diff
together. Native timestamps remain provenance; offline builds copy committed
input bytes reproducibly. Publication inspects this evidence without resolving
or repairing it. VibeVM 1.0.7 still rejects `dev-requires` and inline
`optional=true`; publisher support does not widen native manifest syntax.
A thin package's consumer resolves its own requirements through configured
registries or explicit Git roots. Offline acquisition requires retained native
consumer evidence/cache or a supported local source; thin publication promises
no self-contained offline bundle. Standalone and native product-contract parity
remains required despite their different routes, inventories and provenance.

For an actual new release, verify its exact main-push CI and publisher run,
immutable version tag, public `DISTRIBUTION.json`, package files/digests and
native external acquisition using `vpm-consumer.toml.in` with the confirmed URL
and immutable distribution commit. Historical `v3.0.0` qualification remains
historical evidence. Source acceptance and local fixture success do not prove
publication, token write permission or external acquisition; completion follows
the actual Task's authorized conditions.

For a failed release, preserve the exact failed accepted source SHA and recorded
publisher identity. Prefer rerunning the failed job or a specific job to retain
the original reusable-workflow commit. Rerunning all jobs or a new same-source
dispatch may resolve newer accepted publisher main. Each execution records its
resolved implementation and repeats source/CI/export qualification; reports
staged by a different implementation cannot be finalized. The caller's retry
input selects the same accepted producer SHA, never current main. An existing
tag is a safe no-op, not proof a different source was published; compare its
files/receipt before claiming recovery. Never rewrite a version tag. Missing
destination access/rights remains an owner setup boundary; never create tokens,
broaden permissions or select another repository. Consumer installation,
update, rollback, drift and removal retain the Skill's existing paths.
