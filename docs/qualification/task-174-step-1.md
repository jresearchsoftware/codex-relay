# Task 174 Step 1: guidance delivery qualification

The implementation starts from accepted Relay `9bd60b27e23b98a0bcb58eac4f18af84098192ce`.
This report records bounded local fixture evidence, not independent acceptance,
external publication, another consumer adoption or installed service qualification.
The compatibility rationale is [the semantic assessment](../relay-skill-compatibility.md).

## Native consumer resolution and routing

Reproduce on Linux with the hash-checked VibeVM 1.0.7 musl binary from
`toolchain/vibevm.json`:

```sh
python3 scripts/build-relay-guidance.py --check
python3 scripts/prepare-relay-self-adoption.py --check
python3 scripts/test-relay-guidance.py
python3 scripts/test-qualify-vibevm.py
python3 scripts/qualify-vibevm.py --vibe /absolute/path/to/pinned/vibe
python3 scripts/qualify-relay-guidance-vpm.py --vibe /absolute/path/to/pinned/vibe
```

The native qualifier uses disposable consumer Git repositories and isolated
settings/cache. Its actual generated Relay 3.0.0 payload has native tree hash
`sha256:11ee29327e2bab25256b663fd8015d900a24db52ed136a3ece64a0aeda5b37bd`.
The tool-produced consumer lock and matching slot metadata were verified for:

| Shared version | Exact public distribution revision | Native locked tree hash | Result |
| --- | --- | --- | --- |
| 5.0.0 | `30a23f467c30c41fec918204cbbf2ecfffd7bef5` | `sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9` | Resolution, projection and selected protocol routing passed. |
| 4.0.0 | `f14da40725cd35fb3117ae84a506256505340787` | `sha256:d27a004b5f2dcc8ae0f7fd33289d97be1eab84ddbdf54d7e880cc6def7ad3746` | The declared lower bound passed. |
| 3.0.0 | `b6fefd51c2c34e4001e1709c9c157dfa2296ad60` | No resolved lock | Resolver refused the graph as unsatisfiable before lock, Skill or local policy mutation. |

Each positive graph contains one selected Shared package. The boot INDEX reads
only that selected Shared slot. Native Skill projection contains no
`references/shared/**` bundle and uses the consumer lock route. Repeated/offline
projection, a fresh-cache reinstall from retained slots, update/rollback,
drift refusal, foreign collision refusal and removal with local additions passed.
Native validate/check reported no warnings or findings in these fixtures.
The qualifier emits commands, exact artifact hashes and selected locks to its
reported disposable evidence directory for inspection.

The distribution still contains the unchanged nested Shared 4.0.0 release
closure required by accepted Shared Publisher. It is explicitly non-authoritative
and has no active consumer boot/Skill route. This is not a claim of zero Shared
4.0.0 files in the complete distribution. The native dependency and consumer
selection remain `>=4.0.0` and the reviewed exact root lock respectively.

## Standalone and first-party ready files

The standalone projector suite passed all 14 tests, including the complete
committed artifact with no VibeVM on PATH, preserved human AGENTS/other Skills,
update/rollback, collision/drift checks and owned removal. The 17 first-party
structural tests passed; the pinned native self-adoption probe also passed
exact offline regeneration, overlays and corruption counterexamples. Relay's
own project-wide Shared selection remains 4.0.0. Accepted registry versions
1.0.0, 2.0.0 and 2.0.1 remain byte-identical to the starting source.

The existing native tool check alone still accepts some missing files and a
divergent recorded lock hash; the existing source/receipt/slot verifier catches
those cases. These are retained tool limitations, not new product guarantees.
No model behavior, live ChatGPT settings, protected deployment or external
publication is established by these file/tool probes. The optional publisher
fixture remains local, uses synthetic READY evidence and cannot establish real
source acceptance or external release authority. Current exact-head native
checks and independent review remain separate.
