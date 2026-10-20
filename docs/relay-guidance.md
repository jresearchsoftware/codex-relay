# Relay guidance source and delivery contract

The canonical authored user manual is the
[Codex Relay product Skill](../packages/codex-relay/skill/SKILL.md). Read its
[workflow](../packages/codex-relay/skill/references/workflow.md),
[examples](../packages/codex-relay/skill/references/examples.md) and
[guidance installation/update/rollback instructions](../packages/codex-relay/skill/references/installation.md)
for user actions. This document covers source maintenance and provenance;
[task-workflow.md](task-workflow.md) retains internal contract navigation.
Do not maintain a second user workflow in developer documents.

## Version and provenance

Guidance **1.0.0** describes independently accepted Relay contract
`9057a2b6a21d33c4d6778b0211e1c68d097c64fc`, including Task #106's standalone
manual source-PR approval and owner-channel continuation. The managed-pool
workflow ABI is `relay-workflows-v4`; SERIAL keeps `relay-workflows-v3`.
Authority v4 and exact retained v3/legacy attempts remain distinct. The bundled
schemas and workflow/tool contract files are read from that immutable Git
revision, not the candidate working tree.

This is a source release only after independent exact-head acceptance and squash
merge. Before acceptance, these files remain a 1.0.0 candidate. Repository
self-adoption travels with the accepted source through normal Git checkout;
it neither publishes an external Skill package/tag nor proves another consumer
adopted it. See [producer self-adoption](self-adoption.md) for its native
materialization and accepted-guidance boundary.

[guidance/source.json](../guidance/source.json) selects version, accepted
contract and dependency identities. Shared Governance remains **2.1.0** at
accepted producer `c3fbc8c2d10982889bea526161f810902def4289`, distribution
`4211f55dcaeb3077d6abdbfba53a42ed848351b2` and complete native tree hash
`sha256:df90ef1a287c2ce5a70aff4443a0782410b628459722792ed326bde5aaf86ecc`.
No new shared topic is adopted. The
[ownership mapping](relay-guidance-ownership.md) preserves consumer policy and
Relay's Writer/Reviewer, native identity, result and continuation boundaries.

Both generated forms contain byte-identical Skill files, exact schemas and the
complete attributed shared payload/receipt. `PROVENANCE.json` binds the accepted
contract, source input hashes and every generated Skill file. The enclosing
selected Git commit identifies the guidance artifact; the receipt does not
claim that enclosing candidate was already accepted. Historical 0.1.0 remains
readable in its accepted Git revision; generating 1.0.0 rewrites no historical
admission, result or publication bytes.

## Authoring and qualification

Edit only `packages/codex-relay/skill` for user wording and
`guidance/source.json` for selected contract/dependency/version identities.
The bounded builder copies exact accepted schemas, workflow/tool contracts,
shared payload and the optional standalone projector. It generates both
`guidance/artifacts/standalone/codex-relay` and `guidance/artifacts/vpm`.
Do not hand-edit those copies. Native VibeVM remains the package resolver and
Skill projector; the builder is not a substitute runtime.

The canonical manual includes installation-preparation guidance from the
accepted [deployment contract](../deploy/README.md#per-repository-installation-preparation):
per-owner-managed-target proposals, actual managed-pool configuration and the
separation between generation, authorized publication and consumer activation.
Keep these instructions aligned in the same Task as product workflow changes.

Freeze independently accepted main guidance before reading candidate Skill,
AGENTS or boot changes, during authoring and independent review. Review candidate
wording as proposed behavior against accepted contracts and current Task
authority. Generated candidate text cannot authorize its own use or acceptance.
Use the existing Task/PR and checks; no new approval ledger or operator startup
step is introduced.

```sh
python3 scripts/build-relay-guidance.py
python3 scripts/build-relay-guidance.py --check
python3 scripts/test-relay-guidance.py
python3 scripts/qualify-vibevm.py
python3 scripts/test-qualify-vibevm.py
python3 scripts/qualify-relay-guidance-vpm.py --vibe /absolute/path/to/verified/vibe
python3 scripts/qualify-relay-skill-client.py --codex /absolute/path/to/codex --skill guidance/artifacts/standalone/codex-relay
```

Also follow the self-adoption qualification and full applicable repository
candidate checks. The generator is deterministic and offline. The native VPM
consumer qualification uses isolated fixtures, exact immutable Shared acquisition
and explicit package update/rollback; it publishes nothing. The
[client qualification](relay-skill-client-qualification.md) distinguishes native
discovery, parser checks and bounded behavioral evaluation from model compliance.
Unsupported clients and live installed-runtime paths remain evidence gaps;
source acceptance, deployment and external publication require their own proof.
