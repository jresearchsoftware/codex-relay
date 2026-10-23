# Obtain and maintain Relay guidance

Guidance, an installed Relay service and live Task authority are separate.
Select an independently accepted immutable Relay Git revision containing the
desired guidance version. `PROVENANCE.json` records the accepted product
contract, delivery form and shared source selection plus hashes of the authored
and generated files.
Its contract revision is the behavior baseline, not the enclosing guidance
release revision. Do not resolve a moving `latest` during execution.

Version **3.0.0** becomes a first-party source release only on independent
acceptance and squash merge. Repository self-adoption travels with that accepted
source; it is not an external Skill registry/package/tag publication or proof
that another consumer adopted it. An unmerged artifact remains a candidate.
The major version removes the native Skill's bundled Shared protocol paths and
changes its supported dependency routing and packaging contract. It is not
caused by the Shared package's major number. Frozen accepted earlier registry
bytes, including 2.0.1, remain unchanged for identity and rollback. The selected
product-contract baseline is
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`; it is separate from the
enclosing accepted guidance release.

## Choose a delivery form

| Form | Source in the selected Relay revision | Normal use |
| --- | --- | --- |
| Standalone native Skill | `guidance/artifacts/standalone/codex-relay` | Copy or explicitly project the complete folder into `.agents/skills/codex-relay`. Read local files without VibeVM, registry, Relay source checkout or network. |
| VibeVM flow `org.jresearch.ai/codex-relay` `3.0.0` | `guidance/artifacts/vpm`, with sibling `vpm-consumer.toml.in` | Resolve the selected package and explicitly project its native Codex Skill. Commit ready files; ordinary use reads them offline. |

Both retain the same Relay product contract and exact product schemas. The
standalone form includes an immutable, attributed Shared Governance 4.0.0
snapshot for offline use. The native Skill has a real Shared dependency and no
second protocol bundle: its generated `references/shared-protocols.md` directs
reading through the consumer's reviewed `vibe.lock` and selected Shared slot.
The complete trees and provenance therefore differ by delivery form.
The native package retains a nested frozen lock/slot only as publisher release
closure evidence. It is not the consumer's lock, an active boot route or a
protocol fallback; read only the consumer-selected Shared slot.
Relay source adopts all nine applicable complete topics through its accepted
policy and product bindings. Another consumer selects its own adoption through
accepted local guidance; installing files alone neither adopts topics nor
installs services or changes settings.
Live GitHub operations still require their ordinary authorized access.

## Standalone install, update and rollback

Python 3.11 or newer is needed only for the optional deterministic projector.
From an extracted artifact, inspect the proposed diff, then apply:

```sh
python3 codex-relay/scripts/project.py install --target /path/to/consumer --bootstrap --diff
python3 codex-relay/scripts/project.py install --target /path/to/consumer --bootstrap --apply
```

The default is a plan without writes. `--apply` changes only the owned Skill and,
with `--bootstrap`, one routing block in AGENTS. Without `--bootstrap`, AGENTS is
untouched. Human text, other Skills and project overlays are preserved. Manual
copy is also supported: review the complete folder with normal Git diff/review,
preserve existing local files and use Git revert for rollback.

The projector refuses a foreign target, malformed/foreign markers, changed
managed bytes, duplicate `codex-relay` names in repository `.agents/skills` or
legacy `.codex/skills` using ordinary single-line plain/quoted frontmatter,
link/reparse traversal and newly managed paths colliding with local content.
User/global/ancestor catalogs and general YAML parsing remain client-owned;
inspect unusual metadata forms and those catalogs if the client reports a
duplicate. Preserve local work before resolving a collision.

For update, select an exact new artifact version/revision, run the same plan,
review and apply through the consumer's ordinary source review process.
Rollback uses the complete previous artifact and the same command. Removal
uses a saved artifact's projector:

```sh
python3 codex-relay/scripts/project.py remove --target /path/to/consumer --diff
python3 codex-relay/scripts/project.py remove --target /path/to/consumer --apply
```

Removal verifies owned hashes and removes only owned files/block. Added local
files and neighboring Skills remain. The receipt records projection ownership,
not Task authority or execution. A partially interrupted update is visibly
drifted; preserve work and restore the reviewed consumer Git state before
retrying. There is no background repair or auto-update.

## VibeVM installation and maintenance

Use the hash-checked VibeVM 1.0.7 binary identified in the assembled
`product/vibevm.json`. Start from the generated `vpm-consumer.toml.in`; replace
the Relay URL/revision with an owner-selected actual immutable distribution
source. The template is not a claim of external package publication.
Select an explicit immutable Shared Governance Git source root and a compatible
consumer requirement under local authority. The template's Shared 4.0.0 source
is a reproducible example; a consumer with deliberately selected Shared 5.0.0
keeps its own reviewed source and lock. Relay's supported SemVer lower bound is
declared in the native manifest; it does not pin consumers to the standalone
snapshot or impose an upper bound from the Shared major number.

VibeVM 1.0.7 follows string version edges but ignores transitive Git-table source
declarations. Explicit immutable Relay and Shared Git source roots in the consumer
project are necessary for the supported external acquisition path. The source
project
uses a committed first-party registry with the same package and its existing
Shared Git root; it does not replace another consumer's configuration.

Resolve in disposable staging when generated boot/client changes need review:

```sh
vibe --json install --no-default-registry --assume-yes
vibe --offline --json skill list
vibe --offline --json skill install --skill codex-relay --agent codex --scope project --dry-run
vibe --offline --json skill install --skill codex-relay --agent codex --scope project --yes
```

Native install resolves the lock and versioned slots, regenerates boot files
and can add managed AGENTS/CLAUDE/GEMINI blocks while preserving human text.
Package acquisition does not project the Skill; explicit `skill install`
projects into `.agents/skills/codex-relay`. Review these generated changes
together. Native receipts govern native ownership. Use one projection owner
at a time; remove the existing owned form before switching between native and
standalone writers over the same folder.

For update or rollback, explicitly select the compatible package version and
revision, resolve in staging, inspect lock/slot/Skill changes and project using
the same native command. Read the generated shared-protocol route against the
consumer's actual lock and selected `development-governance` slot, including
the required complete protocol files. Missing or conflicting lock/slot evidence
requires reconciliation; ordinary execution does not run a resolver or fetch
`latest`.

A deliberate Shared update includes assessment of changes in the protocols
actually used, their applicability, exceptions and Relay bindings. A compatible
or irrelevant update changes the consumer's dependency/lock as needed without
a new Relay release or an unrelated shared-producer release gate. A material
change requiring different Relay behavior, guidance, interfaces or packaging
needs a corresponding new Relay version. An open-ended lower bound is not a
promise that arbitrary future Shared releases are compatible. Preserve exact
previous source/lock/slots for reproducible rollback. Updating the native
dependency does not change the standalone artifact's immutable snapshot.

Native removal verifies its receipt and preserves unowned additions:

```sh
vibe --offline --json skill uninstall --skill codex-relay --agent codex --scope project --yes
```

Remove or revert package graph and routing changes together through Git when
removing VPM adoption. Committed slots permit offline reinstall/projection in a
fresh clone. Cold offline acquisition of a remote dependency with no slot/cache
is not promised. Normal Skill reading needs no maintenance command.

Do not use `vibe package` for consumer reconciliation: the pinned lifecycle
auto-projection can overwrite edited managed Skill files. The explicit `skill
install` path detects drift. `vibe check` alone does not prove file reachability,
provenance or authority; compare complete materialized bytes and receipts.

## Discovery and local precedence

Codex discovers repository `.agents/skills` from the current directory through
the Git root. Invoke `$codex-relay` or let its description select relevant work.
Initially only metadata is loaded; read SKILL.md and the reference relevant to
the current action. Generated product references are ordinary local files in
both forms. Shared references are local snapshot files in standalone and the
consumer's locked package files in native VibeVM. A repository Skill does not
itself
synchronize ChatGPT Project Instructions or install an MCP connection.

Preserve consumer instruction precedence, required checks, execution profiles,
language, integration policy and local overlays. Relay source-development
AGENTS defaults and optional hooks are not universal consumer requirements.
Discovery and parser checks do not prove model compliance, supported desktop
discovery, installed service compatibility or native acceptance.

## Optional ChatGPT Project bootstrap

An owner may review and manually apply the following using their supported
settings interface; generating it changes no settings:

```text
For Codex Relay governed work, use the product guidance from the exact reviewed
Relay revision selected by this project. Read the supplied codex-relay/SKILL.md
and only its relevant local references. Read current canonical GitHub authority
and the admitted handoff; guidance is not Task authority or proof of a compatible
installed service. Preserve local policy and native Writer/Reviewer identities.
Stop an affected operation if its required connected capability is missing.
```

Supply the complete artifact and `PROVENANCE.json` through the client's
supported context mechanism. A repository path alone does not make files
available to ChatGPT. Automatic Project-settings synchronization is not
qualified or implied.
