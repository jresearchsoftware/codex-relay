# Obtain and maintain Relay guidance

Guidance, an installed Relay service and live Task authority are separate.
Select an independently accepted immutable Relay Git revision containing the
desired guidance version. `PROVENANCE.json` records the immutable pinned product
contract, delivery form and shared source selection plus hashes of the authored
and generated files.
Its contract revision is the behavior baseline, not the enclosing guidance
release revision. Do not resolve a moving `latest` during execution.

Version **11.0.1** is PATCH from accepted 11.0.0. It clarifies how the
orchestration assistant acts on the owner's explicit instruction to start agreed
work through a supported owner-authenticated GitHub connection and verifies the
original launch. It adds no mandatory operator work and preserves existing authority
and admission. The native floor remains `>=12.1.0`, with exact Shared 12.1.0
in standalone and publisher closure evidence.

Version **11.0.0** was MAJOR from accepted 10.0.0. It removes blanket
independent review, squash merge and related process requirements for routine
disposable TEST work. Within established TEST authority, executors can expand
TEST resources and manage TEST-specific configuration on shared services while
protecting PROD and other users. Actual product acceptance, protected Relay
operations and the owning project's local authority retain their requirements.
The native floor remains `>=12.1.0`. Standalone and publisher closure evidence
carry exact Shared 12.1.0. Frozen 10.0.0 and earlier payloads retain their bytes.

Version **10.0.0** was MAJOR from accepted 9.0.0. The product
adopts GH-014 and HC-001–003, updates manual handoff presentation and removes
the constant `post_review_continuation.execution_supported` from the Reviewer
response. Consumers use the actual continuation authorization and effect fields.
The native floor is `>=12.1.0` because these operator interactions use the new
Shared rules. Standalone and publisher closure evidence carry exact 12.1.0.
Source acceptance, external publication and installed qualification remain
separate. Frozen 9.0.0 and earlier packages preserve their own bytes.
The 3.0.0 major removed the native Skill's bundled Shared protocol paths and
changed its supported dependency routing and packaging contract. It was not
caused by the Shared package's major number. Frozen accepted earlier registry
bytes, including 2.0.1, remain unchanged for identity and rollback. The selected product-contract
revision is recorded in `PROVENANCE.json`; it is separate from the enclosing
accepted guidance release. Candidate schema pins do not establish acceptance.

Version 4.0.0 updates the complete standalone snapshot to Shared 5.0.0. Its
bundled `references/shared/tools/chatgpt` helper removes ownership receipts and
changes status/update behavior; users of that optional helper should review
its included README before updating. These shipped interface changes determine
Relay's major version. Relay's own `scripts/project.py` installer receipts,
native Skill receipts and consumer-selected Shared requirement are unchanged.

Accepted version 7.0.0 was MAJOR from accepted 6.1.0: completing-PR versus verified-
condition closure timing changes, and Shared 8/9 result/evidence duties plus
Shared 10 project-context authority become part of the guidance. Native requires
`>=10.0.0` because RA-007 and its TH/CL semantics first appear there; historical
layout alone is insufficient. Standalone and publisher closure evidence update
to exact Shared 10.0.0. Frozen 6.1.0 and earlier payloads remain unchanged.
Source acceptance, external publication and installed qualification/activation
remain separate; preserve explicitly retained old admitted contracts.

Version 8.0.0 is MAJOR from accepted 7.0.0: new trusted boundary
prose or acceptance/validation requirements no longer implicitly terminate
admitted automatic source work or safe Writer publication merely by arriving.
Task #194's accepted closure workflow and Shared 10.0.0 semantics remain the
baseline. Already-admitted manual handoffs retain conservative predispatch
boundary/validation checks, and manual reporting records valid later Decision
drift. Structured safety holds, scope removal, exact identity/pin checks and
protected-effect guards remain. Task/Decision requirements govern the work and
independent acceptance; ordinary manual stop/control goes directly to Codex,
and automatic execution uses native Actions cancellation and containment.
See the [workflow control guidance](workflow.md).
This adds no live steering, new stop command or installed upgrade.
Frozen 7.0.0 and earlier package bytes remain unchanged.

## Choose a delivery form

| Form | Source in the selected Relay revision | Normal use |
| --- | --- | --- |
| Standalone native Skill | `guidance/artifacts/standalone/codex-relay` | Copy or explicitly project the complete folder into `.agents/skills/codex-relay`. Read local files without VibeVM, registry, Relay source checkout or network. |
| VibeVM flow `org.jresearch.ai/codex-relay` `11.0.1` | `guidance/artifacts/vpm`, with sibling `vpm-consumer.toml.in` | Resolve the selected package and explicitly project its native Codex Skill. Commit ready files; ordinary use reads them offline. |

Both retain the same Relay product contract and exact product schemas. The
standalone form includes an immutable, attributed Shared Governance 12.1.0
snapshot for offline use. The native Skill has a real Shared dependency and no
second protocol bundle: its generated `references/shared-protocols.md` directs
reading through the consumer's reviewed `vibe.lock` and selected Shared slot.
The complete trees and provenance therefore differ by delivery form.
The native package retains a nested frozen lock/slot only as publisher release
closure evidence. It is not the consumer's lock, an active boot route or a
protocol fallback; read only the consumer-selected Shared slot.
Relay development adopts all eleven complete topics. This product Skill adopts
the ten listed topics through its product bindings. Small Improvements remains
a separate local adoption. Another consumer selects its own adoption through
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

Use the hash-checked VibeVM 1.0.11 binary identified in the assembled
`product/vibevm.json`. Start from the generated `vpm-consumer.toml.in`; replace
the Relay URL/revision with an owner-selected actual immutable distribution
source. The template is not a claim of external package publication.
Select an explicit immutable Shared Governance Git source root and a compatible
consumer requirement under local authority. The template's Shared 12.1.0 source
is a reproducible example; a consumer with another deliberately selected
compatible Shared version keeps its own reviewed source and lock. Relay's supported SemVer lower bound is
declared in the native manifest; it does not pin consumers to the standalone
snapshot or impose an upper bound from the Shared major number.

The supported VibeVM acquisition path follows string version edges but ignores transitive Git-table source
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
