# Codex Relay 1.0.0 guidance package

Generated source candidate for `org.jresearch.ai/codex-relay`. It describes accepted
Relay contract `9057a2b6a21d33c4d6778b0211e1c68d097c64fc` with the exact pinned shared
dependency. `skill/PROVENANCE.json` binds every projected byte and authoring input.
Acceptance, package publication and consumer adoption remain separate.

Acquire this package by an explicitly selected immutable revision through the
supported VibeVM 1.0.7 package interface. The generated sibling
`vpm-consumer.toml.in` shows both required immutable Git source roots; the native
package declares the shared version edge, while 1.0.7 ignores transitive Git
source tables. Then explicitly project its Skill with
`vibe skill install --skill codex-relay --agent codex --scope project --yes`.
Ordinary Codex use reads the resulting files offline. See the source repository's
`docs/relay-guidance.md` for install, drift, update, rollback and removal evidence.
