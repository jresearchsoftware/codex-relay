# Task 169 Step 2: release preparation evidence

Date: 2026-10-21. Authority is the original Task #169 charter plus trusted
[Decision 6314092881](https://github.com/jresearchsoftware/codex-relay/issues/169#issuecomment-6314092881).
The independently accepted starting source is
`72f74c77e6a95623352ff30a01e9782fc3a0db46`; candidate instructions remain proposals.

## License, provenance and public inventory

Reviewed all files in the actual generated public export, including both copies
of the complete Shared Governance payload and native slot metadata. The committed
`guidance/licenses.json`, exported as `LICENSES.json`, identifies components,
licenses, preserved notices and exact upstream identities. The root MIT LICENSE
matches the accepted public Relay LICENSE. Product schema/workflow/tool JSON
comes from accepted Relay contract `61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`;
the Relay projector and authored Skill come from this source repository.

All 21 Shared distribution files were compared byte-for-byte with the public
immutable distribution `f14da40725cd35fb3117ae84a506256505340787` and accepted
slot. Its receipt binds producer `99034dd708e5d0201060986b561ada4d2cffd453`.
Its MIT LICENSE retains both shared-governance contributors and Codex Relay
contributors (derived governance text). The same notices remain in the Skill
mirror and native dependency closure. No separate incompatible license or
unattributed copied code was identified in the inspected exported materials.
The included Python tools use the standard library. FPF, VibeVM, OpenAI and
GitHub references are links; no FPF corpus, external executable or third-party
library is shipped. Public references and synthetic examples were inspected;
no private paths, keys or private-network URLs were found in the export.
This establishes the inspected provenance, not a legal certification of authorship.

The audit identified that extracting the previous Skill omitted Relay's own
root MIT notice. New 2.0.1 includes that notice inside both standalone and native
Skill projections, in their hashed inventory and the native include list.
The first accepted 1.0.0 and 2.0.0 registry bytes remain unchanged. The current
Decision's conditional redistribution authority and this evidence support the
binding's approved MIT acknowledgement; no unknown rights are silently cleared.

## Setup and release boundaries

Read-only GitHub evidence confirms destination
`jrs-vibevm/org.jresearch.ai.codex-relay` is public and currently empty (Git refs
API reports 409). It has no repository rulesets; branch main does not exist yet.
The caller's repository ID is `1374717037`. Repository-local Actions secrets are
empty, but **repository-scoped organization-secret availability** lists
`DEVELOPMENT_GOVERNANCE_PUBLISH_TOKEN`. Organization-wide secret listing was
403 and is unnecessary to establish this repository's availability. No secret
value was retrieved, created, changed or disclosed. Owner-account push access
is not proof of the named secret's destination scope/write permission. Its real
write permission can only be established by the reviewed accepted workflow;
that remains unverified before source acceptance. No credential/settings or
external distribution mutation was performed during source preparation.

The selected shared publisher pin
`5a1e5de66388501235fc9ffd23d45efb34df2b85` is an ancestor of accepted Shared
Governance main `99034dd708e5d0201060986b561ada4d2cffd453`. Its workflow and
publisher source are used directly, with no copied publication engine. The
new 2.0.1 transition uses ordinary publication; explicit initial publication
of old frozen source is not required or selected.

## Qualification interpretation

Pinned native VibeVM 1.0.7 binary SHA-256:
`20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240`.
Native schema-7 lock and frozen Shared slot were generated in isolated Linux
storage, then included as deterministic committed export inputs. Source-time
readiness uses the pinned shared implementation against exact Git objects.

Shared Publisher native fixtures cover direct/transitive closure and rejection,
ordinary no-op before API/destination work, first-parent source and matching push
CI, wrong source, license/rights, explicit old-source initial publication,
exact-source retry, tag collisions, atomic non-force failure and secret isolation.
These disposable fixtures exercise shared behavior; they do not prove live
Actions token permission, producer trigger execution or real publication.
The generated consumer template deliberately declares both immutable Git source
roots, as required by VibeVM 1.0.7. Nested slots qualify shipped closure but do
not replace the existing explicit consumer source-discovery requirement.

Final checks, exact candidate head, native Actions links, execution warnings and
local qualification results belong in the one canonical Writer Outcome and PR.
Source acceptance, real publication/readback, external consumer acquisition and
closure remain separate. Stop after this source handoff for independent review.

The reproducible actual-export fixture imports that exact upstream implementation:

```sh
python3 scripts/qualify-relay-publisher.py --publisher /path/to/pinned/shared-governance \
  --vibe /absolute/path/to/verified/vibe --source-ref FULL_CANDIDATE_SHA
```

It substitutes a synthetic READY decision and disposable local destination,
checks every native staged/tagged/installed byte, finalizes only into local Git,
then checks retry/no-op and a cold consumer using the supported two immutable
Git roots. It never verifies source-main CI or live publishing permissions.
Local `uploadArchive.allowUnreachable` belongs only to the disposable bare
fixture so the file transport can retrieve the exact commit. Use the peeled
release commit, not an annotated tag object, as the consumer immutable revision.
