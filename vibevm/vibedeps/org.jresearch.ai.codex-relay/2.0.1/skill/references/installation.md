# Obtain and maintain Relay guidance

Guidance, an installed Relay service and live Task authority are separate.
Select an independently accepted immutable Relay Git revision containing the
desired guidance version. `PROVENANCE.json` records the accepted product
contract and shared dependency plus hashes of the authored and generated files.
Its contract revision is the behavior baseline, not the enclosing guidance
release revision. Do not resolve a moving `latest` during execution.

Version **2.0.0** becomes a first-party source release only on independent
acceptance and squash merge. Repository self-adoption travels with that accepted
source; it is not an external Skill registry/package/tag publication or proof
that another consumer adopted it. An unmerged artifact remains a candidate. The 2.0.0 major reflects changed
shared governance semantics. Frozen accepted 1.0.0 registry bytes remain
unchanged for identity and rollback. The selected product-contract baseline is
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`; it is separate from the
enclosing accepted guidance release.

## Choose a delivery form

| Form | Source in the selected Relay revision | Normal use |
| --- | --- | --- |
| Standalone native Skill | `guidance/artifacts/standalone/codex-relay` | Copy or explicitly project the complete folder into `.agents/skills/codex-relay`. Read local files without VibeVM, registry, Relay source checkout or network. |
| VibeVM flow `org.jresearch.ai/codex-relay` `2.0.0` | `guidance/artifacts/vpm`, with sibling `vpm-consumer.toml.in` | Resolve the selected package and explicitly project its native Codex Skill. Commit ready files; ordinary use reads them offline. |

Both contain identical Skill/reference/schema/provenance files, including the
exact Shared Governance 4.0.0 payload. Relay source adopts all nine applicable
complete topics through its accepted policy and product bindings. Another
consumer selects its own adoption through accepted local guidance; installing
files alone neither adopts topics nor installs services or changes settings.
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
Preserve its explicit Shared Governance Git root at
`f14da40725cd35fb3117ae84a506256505340787`, version `=4.0.0`.

VibeVM 1.0.7 follows string version edges but ignores transitive Git-table source
declarations. Both explicit immutable Git source roots in the consumer template
are necessary for the supported external acquisition path. The source project
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
the same native command. Native removal verifies its receipt and preserves
unowned additions:

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
the current action. Generated `product` and `shared` references are ordinary
local files in both delivery forms. A repository Skill does not itself
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
