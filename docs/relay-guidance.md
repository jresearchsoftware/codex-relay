# Relay guidance source and delivery contract

The authored user manual is the
[Codex Relay Skill](../packages/codex-relay/skill/SKILL.md). Its
[workflow](../packages/codex-relay/skill/references/workflow.md),
[examples](../packages/codex-relay/skill/references/examples.md) and
[installation instructions](../packages/codex-relay/skill/references/installation.md)
own user actions. This document owns source maintenance and provenance;
[task-workflow.md](task-workflow.md) retains internal contract navigation.

## Version and provenance

Guidance **2.0.0** is a major source candidate adopting the complete applicable
Shared Governance 4.0.0 contract. The selected independently accepted Relay
product-contract baseline is
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`. Exact schema/workflow/tool contract
files come from that immutable revision rather than candidate copies. Managed
pool ABI remains `relay-workflows-v4`; SERIAL remains `relay-workflows-v3`.
Current authority v4 and retained admitted v3/legacy attempts stay distinct.
This governance migration does not change deployed runtime semantics.

Independent exact-head acceptance and merge establish the first-party source
release. Before that, 2.0.0 is a candidate. Native source self-adoption travels
with the accepted commit; it is neither external package/tag publication nor
another consumer's adoption. The frozen accepted 1.0.0 registry payload remains
unchanged. New 2.0.0 output does not rewrite historical admission, Outcome,
review or publication identities.

[guidance/source.json](../guidance/source.json) selects exact identities:

| Identity | Selected value |
| --- | --- |
| Shared coordinate/version | `org.jresearch.ai/development-governance` `4.0.0` |
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

Both delivery forms contain byte-identical Skill files, exact schemas and the
complete attributed Shared payload/receipt. `PROVENANCE.json` binds the accepted
contract, authored input hashes and each generated Skill file. The enclosing
selected Git commit identifies the guidance artifact; the receipt does not
assert that its enclosing candidate is already accepted.

## Authoring and qualification

Edit `packages/codex-relay/skill` for user wording and `guidance/source.json` for
selected versions/identities. The deterministic builder copies exact accepted
schemas, workflow/tool contracts, Shared payload and the optional standalone
projector into `guidance/artifacts/standalone/codex-relay` and
`guidance/artifacts/vpm`. Do not hand-edit those outputs. Native VibeVM remains
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
