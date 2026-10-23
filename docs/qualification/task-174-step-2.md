# Task 174 Step 2: compatibility-floor correction

This correction begins at `16c7ab5c1f4349e948cf4c5c131d297fe512f606`
under CR-174-001, admitted attempt `run-39955963241`. It supersedes Step 1's
minimum-version rationale and negative 3.0.0 fixture, while preserving that
historical report. The [compatibility assessment](../relay-skill-compatibility.md)
records source history, required layout, section navigation and later-version
behavior. Frozen prior releases and the standalone Shared 4.0.0 snapshot remain.

## Reproduction

Run on a native Linux filesystem using the hash-pinned VibeVM 1.0.7 binary
identified in `toolchain/vibevm.json`:

```sh
python3 scripts/build-relay-guidance.py --check
python3 scripts/test-relay-guidance.py
python3 scripts/test-qualify-vibevm.py
python3 scripts/qualify-vibevm.py --vibe /absolute/path/to/pinned/vibe
python3 scripts/qualify-relay-guidance-vpm.py --vibe /absolute/path/to/pinned/vibe
```

The bounded native qualifier acquires exact public Shared distributions and
records commands, native locks, slot receipts and generated file hashes in its
reported disposable evidence directory. Its 2.4.0-only fixture independently
checks the missing Context Loading file; resolver refusal alone is insufficient
evidence of technical incompatibility. Positive fixtures check all nine paths,
the section names used by the manual, unique consumer boot routing, exact
native projection, locked source identities and tool-produced content hashes.

## Observed native results

VibeVM 1.0.7 qualification passed on the isolated Linux checkout for this run.
All positive fixtures resolved Relay 3.0.0 with native package content hash
`sha256:297afba0242ec3ae2cd77448ac6bec4b112b72d9b3f8d229e9029dda60cbaaa6`.
The exact selected Shared identities were:

| Version | Distribution commit | Native content hash | Result |
| --- | --- | --- | --- |
| 2.5.0 | `d691c1b9ad8c1bdababbf15da4ec7c69399e1e02` | `sha256:ea95bc042f78ce2dc830f70e1656777ffdb4c6c40be944a4d1cd4b32ed236c88` | Lower bound, nine files, named sections, lock/slot/boot and Skill projection passed. |
| 3.0.0 | `b6fefd51c2c34e4001e1709c9c157dfa2296ad60` | `sha256:e6bebee92981594554cf3be735ac9f0d331d57ee66dd033e2b639a609cf145de` | Same checks passed; no numeric anchor dependency remains in the portable manual. |
| 4.0.0 | `f14da40725cd35fb3117ae84a506256505340787` | `sha256:d27a004b5f2dcc8ae0f7fd33289d97be1eab84ddbdf54d7e880cc6def7ad3746` | Same checks passed; standalone snapshot bytes match this immutable slot. |
| 5.0.0 | `30a23f467c30c41fec918204cbbf2ecfffd7bef5` | `sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9` | Same checks passed. |
| 2.4.0 | `5b33f826f0a9dbba5f61f5524060027dba9e02de` | `sha256:351533789a03787ab4b911aa4222cd25556e15f70520f0a6600200e411ad58af` | Acquired alone: eight files, no `context-loading.md`; adding Relay is refused by the resolver before lock or Skill mutation. |

Each positive fixture passed native check/validate without warnings. Intentional
Shared-only update 4.0.0 → 5.0.0 → 4.0.0 preserved Relay 3.0.0 and every projected
Skill byte. Repeated projection, explicit Skill update/rollback, offline
reinstall with an empty cache and retained slots, drift/collision refusal,
preserved local AGENTS/neighboring Skills and owned removal also passed.
The final fixture evidence is `/tmp/relay-guidance-vpm-6dhkyy4b/qualification.json`
on this workstation's Debian WSL filesystem; it is diagnostic local evidence,
not a portable artifact or a requirement for ordinary consumers.

Standalone projection passed 14 tests; first-party structural qualification
passed 17 tests; pinned native self-adoption passed exact regeneration, offline
reads, overlays and corruption counterexamples. The managed root VibeVM block,
standalone Shared snapshot, producer Shared 4.0.0 slot, release closure and
accepted Relay registry versions 1.0.0/2.0.0/2.0.1 are unchanged from the start.
The native lock's first-party source URL records this new generating checkout;
it is location metadata, not portable provenance or consumer dependency policy.

The full Node suite passed 1176 tests with four conditional skips. Cargo format
passed and the locked Reviewer suite passed 159 tests. `scripts/qualify.py`
passed its three-consumer qualification with actual handlers and isolated mock
GitHub. These checks used Node 22.20.0, Cargo/Rust 1.90.0 and Python 3.11.2 on
Debian WSL, running as the ordinary user on its native Linux filesystem.

## Limits

These file/tool fixtures do not prove model behavior, independent acceptance,
external publication, deployment, live client settings or consumer adoption.
The producer still adopts Shared 4.0.0 and retains that publisher closure;
the native Skill reads only the consumer-selected lock/slot. The temporary
manual PR label instruction is project-owned AGENTS prose until Task #177,
outside the managed VibeVM block and outside portable Skill guidance.
