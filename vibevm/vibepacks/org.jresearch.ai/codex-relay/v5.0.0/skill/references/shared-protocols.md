# Shared protocol source: consumer-locked native dependency

This native Skill requires `org.jresearch.ai/development-governance` with the SemVer requirement recorded
in `PROVENANCE.json` (`shared_requirement`) and the package manifest.
The dependency is deliberately selected by the consumer; never infer an upper
bound solely from a package-major number.

The coordinate is `org.jresearch.ai/development-governance`.
Use the consuming project's reviewed `vibe.lock` as the single protocol identity.
Locate that project's root (the root whose `vibe.toml` admitted this Skill), read
its `vibe.lock`, and select the unique `development-governance` package in group
`org.jresearch.ai`. Use its exact `version`, `content_hash`, `source_url` and
`source_ref` where present. Read committed files under that same project root:
`vibevm/vibedeps/org.jresearch.ai.development-governance/<locked-version>/`.
The slot's `.vibe-slot.toml` source hash must match the lock's `content_hash`;
missing, ambiguous or drifted files require restoration of reviewed consumer
state, not another bundled source, a runtime resolver or a `latest` lookup.
Do not infer the selected protocol version from this Relay artifact's provenance.

Read each triggered complete file below inside the selected slot; conditions
remain in SKILL.md and local adoption remains consumer-owned:
- `vibevm/vibespecs/protocols/task-handoff.md`
- `vibevm/vibespecs/protocols/independent-review.md`
- `vibevm/vibespecs/protocols/contract-and-decision-maintenance.md`
- `vibevm/vibespecs/protocols/context-loading.md`
- `vibevm/vibespecs/protocols/proportional-controls.md`
- `vibevm/vibespecs/protocols/requirement-authority.md`
- `vibevm/vibespecs/protocols/package-versioning.md`
- `vibevm/vibespecs/protocols/self-adoption.md`
- `vibevm/vibespecs/protocols/github-repository-governance.md`

The minimum compatible layout is Shared Governance 2.5.0. The manual uses
protocol section names available there and in later assessed versions rather
than numeric clause anchors first added in 3.0.0. Read the selected complete
text and its applicable local Relay bindings; newer governance wording alone
does not require selecting a newer dependency or replacing product authority.

The package's nested `vibe.lock` and `vibevm/vibedeps` are frozen publisher
release-closure evidence. They are not the consuming project's lock or active
protocol route. Never read their snapshot as a fallback or apply its boot as a
second policy. The Skill contains no shared protocol bundle. Deliberate consumer
updates assess used semantics, applicability, exceptions and Relay bindings;
compatible or irrelevant changes, including a package major, need no new Relay
release. Material Relay behavior, interface, guidance or packaging changes do.
An open lower bound is not a promise of compatibility with unknown future releases.
