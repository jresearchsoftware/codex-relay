# Relay guidance for people and Codex

The Relay product Skill supplies practical Task, Decision, Change Request,
Outcome and independent-review guidance without a Relay source checkout or a
VibeVM runtime. People can read its [workflow](../packages/codex-relay/skill/references/workflow.md)
and [examples](../packages/codex-relay/skill/references/examples.md) directly.
The [Task workflow guide](task-workflow.md) remains the product entrypoint.

Guidance version **0.1.0** describes accepted Relay source contract
`4847c368ae5ea956fd6370bee207c8e4a176e8e0`: `relay-workflows-v3`, authority v4,
and retained admitted v3/legacy attempts. This new guidance is a source candidate;
its presence does not prove source acceptance, an external package publication,
an installed-v4 upgrade or consumer adoption. Select a reviewed immutable Relay
Git revision when obtaining an artifact. Never use a moving `latest` during
normal execution. Workflow/service installation and guidance updates are separate.

## Two equivalent delivery forms

| Form | Obtain and install | Normal use |
| --- | --- | --- |
| Standalone native Skill | Copy `guidance/artifacts/standalone/codex-relay` from the selected exact Relay revision. Use its bundled Python projector or review and copy the complete folder into `.agents/skills/codex-relay`. | Codex and people read local Markdown, schemas and pinned shared references. No VibeVM, registry, Relay checkout or network is required to read guidance. Live GitHub authority and connected operations still need their normal access. |
| VibeVM/VPM flow `org.jresearch.ai/codex-relay` `0.1.0` | Candidate package is `guidance/artifacts/vpm`; it declares the native `development-governance =2.1.0` version dependency. The generated consumer example pins both Git source roots, including shared distribution `4211f55dcaeb3077d6abdbfba53a42ed848351b2`. Resolve with VibeVM 1.0.7, then explicitly project. | Committed native Skill/slot/reference files are readable offline; VibeVM is maintenance tooling only. |

There is no published external Relay Skill package/tag from this candidate.
The VPM qualification uses a disposable local distribution repository and the
actual pinned shared dependency; it does not publish or manufacture public
availability. Future publication needs its own accepted source/version and
authorized distribution action. A consumer can inspect this candidate locally
without depending on a live registry.

Both forms contain byte-identical Skill files, exact schemas and the complete
attributed shared dependency payload/receipt. `PROVENANCE.json` binds the selected
contract revision, source input hashes, generated files and immutable shared
source/distribution. The enclosing selected Git commit identifies the artifact;
the manifest does not claim its own enclosing commit was already accepted.

## Standalone installation, update and rollback

Python 3.11 or newer is needed only for the optional deterministic projector.
From an extracted artifact, inspect the local diff first:

```sh
python3 codex-relay/scripts/project.py install --target /path/to/consumer --bootstrap --diff
python3 codex-relay/scripts/project.py install --target /path/to/consumer --bootstrap --apply
```

The default is a plan without writes; `--apply` changes only the owned Skill and,
with `--bootstrap`, one small routing block in AGENTS. Without `--bootstrap`,
AGENTS is untouched. Existing human bytes, other Skills and project overlays are
preserved. The projector refuses a foreign target, malformed/foreign markers,
changed managed bytes, duplicate `codex-relay` names in target repository
`.agents/skills`/legacy `.codex/skills` using ordinary single-line plain/quoted
frontmatter names, link/reparse traversal and a newly managed
path colliding with local content. User/global/ancestor Skill catalogs remain
client-owned, as is general YAML parsing; inspect unusual metadata forms and
those catalogs when the client reports a duplicate. It does not
silently merge instructions. Resolve a collision
by reviewing and preserving local work before another projection.

Select a specific new artifact version/revision, run the same plan and review
the diff, then apply through the consumer's ordinary repository review process.
Rollback uses the complete previous selected artifact and the same command;
there is no moving resolver. Remove using a saved artifact's projector:

```sh
python3 codex-relay/scripts/project.py remove --target /path/to/consumer --diff
python3 codex-relay/scripts/project.py remove --target /path/to/consumer --apply
```

Removal verifies the installation receipt and owned hashes, removes only owned
files/block, and preserves locally added files and neighboring Skills. The
small receipt is local projection ownership, not Task authority or a runtime
ledger. A partially interrupted update is visibly drifted; preserve the work
and restore the consumer's reviewed Git state before retrying. There is no
background repair, auto-update or authority bypass. If copying manually, use
ordinary Git diff/review/revert for equivalent ownership and rollback; do not
overwrite an existing Skill folder blindly.

## VibeVM/VPM installation and maintenance

Use the qualified, hash-checked [VibeVM pin](../toolchain/vibevm.json), not an
unverified `vpm` executable. Start from generated
`guidance/artifacts/vpm-consumer.toml.in`: it declares both Relay and shared as
explicit immutable Git source roots. Replace the Relay URL/revision with an
owner-selected actual distribution source. Preserve the exact shared root pin;
the candidate is not a published URL. VibeVM 1.0.7 follows the package's native
string version edge but ignores transitive Git-table source declarations. The
explicit two-root source adapter is required for this supported tool; it avoids
a registry or unpinned dependency rather than claiming native transitive Git
resolution. Qualification verifies the actual two-package lock and bytes.
Resolve in a disposable staging copy first
when generated boot/client changes require review:

```sh
vibe --json install --no-default-registry --assume-yes
vibe --offline --json skill list
vibe --offline --json skill install --skill codex-relay --agent codex --scope project --dry-run
vibe --offline --json skill install --skill codex-relay --agent codex --scope project --yes
```

Native install resolves slots/lock and can add VibeVM managed client blocks and
boot files while preserving human text. Package acquisition does not project
the Skill; native `skill install` explicitly projects into
`.agents/skills/codex-relay`. Review all generated changes together before
consumer adoption. Native ownership receipts govern native projection. Use one
projection owner at a time; do not switch between native and standalone writers
over the same folder. Remove the existing owned form first.

For update or rollback, explicitly select the intended compatible package
version/revision, resolve in staging, inspect lock/slot/Skill diff and project
using the same native command. Native `skill uninstall --skill codex-relay
--agent codex --scope project --yes` verifies its receipt and preserves unowned
additional files. Remove/revert package graph and routing changes together
through Git when removing VPM adoption. Restoring committed slots permits
offline reinstall/projection in a fresh clone. Cold offline acquisition of a
remote Git dependency without its slots/cache is not promised.

Do not use `vibe package` as a consumer reconciliation command: the pinned
tool's lifecycle auto-projection can overwrite edited managed Skill bytes.
The supported explicit `skill install` path detects drift. `vibe check` alone
does not prove file reachability, provenance or accepted authority; the
qualification checks compare complete bytes and actual projected files.

## Discovery, JIT use and local precedence

Codex scans repository `.agents/skills` from the current directory through the
Git root. Use `$codex-relay` explicitly or let the description select the Skill
for a Relay workflow. Only metadata is discovered initially; read SKILL.md and
the reference needed for the current action. The source folder contains only
authored content; assembly supplies local `references/product` and
`references/shared` paths described by the Skill. Those generated paths are
ordinary files after either supported installation.

Current [official Codex guidance](https://learn.chatgpt.com/docs/build-skills)
documents this discovery and progressive loading. The authentic Windows/Linux
client checks are recorded with limits in the
[client qualification](relay-skill-client-qualification.md). Local discovery
does not prove model compliance. A repository Skill does not synchronize
ChatGPT Project Instructions or install an MCP connection.

Keep consumer instruction precedence, checks, requested profiles, language,
approval/merge policy and overlays. Relay's source-development AGENTS defaults
and optional hooks are not universal consumer rules. The generated small
AGENTS block routes relevant work; it grants no authority. Shared topic adoption
is explicit: [ownership mapping](relay-guidance-ownership.md) identifies the two
existing adopted topics and the still-unactivated bundled references.

## Optional ChatGPT Project bootstrap

An owner may review and manually apply this text using their supported settings
interface; generating it changes no settings:

```text
For Codex Relay governed work, use the product guidance from the exact reviewed
Relay revision selected by this project. Read the supplied codex-relay/SKILL.md
and only its relevant local references. Read current canonical GitHub authority
and the admitted handoff; the guidance is not Task authority or proof of an
installed compatible service. Preserve local owner policy and required native
Writer/Reviewer identities. Stop if a required connected capability is missing.
```

Attach the complete selected artifact and its PROVENANCE.json through the
client's supported file/context mechanism; a repository path alone does not
make files available to ChatGPT. This manual bootstrap has no qualified
automatic Project-settings synchronization claim.

## Authoring and qualification

### Installation-preparation guidance and the pinned artifact

The source deployment contract now requires Relay orchestration to publish a
separate reviewable routing/recovery-and-manifest PR in every explicitly
owner-managed repository configured for an installation, including inactive
targets. Target owners retain acceptance, merge, activation and governance.
A central product PR or read-only proposal does not satisfy that publication
requirement, and inactive consumers do not block a safe Apply. Read the
[per-repository preparation contract](../deploy/README.md#per-repository-installation-preparation)
when authoring installation work; deriving workflow files and publishing their
PRs remain distinct operations.

The committed Skill source and generated delivery artifacts remain version
`0.1.0`, with `guidance/source.json` and their `PROVENANCE.json` identifying
accepted contract revision `4847c368ae5ea956fd6370bee207c8e4a176e8e0` and
`relay-workflows-v3`. Those artifacts predate this installation-preparation
clarification and do not contain it. Their existing source hashes and bounded
qualification evidence are preserved; this source change does not establish
external publication, consumer adoption or a newer accepted contract revision.

Once the implementing product source has independent acceptance at an exact
immutable revision, update the authored Skill's relevant workflow reference and
entrypoint routing, deliberately select a new guidance version and that accepted
contract revision in `guidance/source.json`, and regenerate both delivery forms
with the existing builder below. Keep the workflow-contract identity unless its
ABI changes; guidance wording does not itself change `relay-workflows-v3`.
The regenerated guidance must also describe the existing managed-pool v4 path
and derive projections from the validated target installation configuration;
the historical v3 pin does not qualify a managed-pool installation.
Run the artifact consistency and affected discovery/behavioral qualification
against those exact generated bytes before separately authorized distribution
publication or consumer update. Do not rewrite the pinned `0.1.0` artifacts to
claim that this candidate was already accepted.

Edit only `packages/codex-relay/skill` for Relay wording and
`guidance/source.json` for the deliberately selected contract/dependency/version.
The narrow adapter copies exact shared payload/schema bytes and the optional
standalone projector; it does not replace VibeVM resolution or native Skill
generation. Do not edit generated copies under `guidance/artifacts`.

```sh
python3 scripts/build-relay-guidance.py
python3 scripts/build-relay-guidance.py --check
python3 scripts/test-relay-guidance.py
python3 scripts/qualify-vibevm.py
python3 scripts/test-qualify-vibevm.py
python3 scripts/qualify-relay-guidance-vpm.py --vibe /absolute/path/to/verified/vibe
python3 scripts/qualify-relay-skill-client.py --codex /absolute/path/to/codex --skill guidance/artifacts/standalone/codex-relay
```

Keep full existing candidate validation and independent exact-head review.
These opt-in maintenance checks do not add a mandatory operator startup step,
invoke a model, qualify production or publish a package. The candidate's
qualification covers standalone Windows/Linux lifecycle, actual VibeVM pinned
graph/projection and native Codex discovery; external distribution publication,
broader clients and installed-runtime behavior remain distinct.
