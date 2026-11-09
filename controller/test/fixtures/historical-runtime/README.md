# Exact historical runtime test source

These two immutable source subsets keep original-operation regression tests
independent of Git checkout depth, deleted PR branches and squash-merge ancestry.
They are test data only: deployed recovery still verifies and invokes its own
protected original installed source. This does not revive historical admission
or add an installation dependency.

- `3f4d4348cfb05866b2108eadcc35b7a17153ff14`: Task 199 Step 1, the original
  runtime used by the retained SERIAL/pool fixtures.
- `f6431d612d464c511fdda97e7dea64ace7f03ac7`: the original plural-repository
  dispatch runtime used by the cross-consumer replay regression.

Each JSON contains the raw original commit, base64-encoded raw Git trees and
UTF-8 file bytes for exactly the paths previously selected by `git archive`:
`consumer`, `controller/src`, `runtime/src`, `contracts/src` and
`reviewer/src/executable-cr-v2.json`. Root/ancestor trees retain unselected
siblings' object IDs as proof, without retaining their content. Nothing is
patched or replaced with current runtime code.

[The test loader](../../historical-runtime.mjs) recomputes the original Git
commit ID, walks the selected tree entries, verifies each tree/blob ID, exact
file set and mode, then materializes the source. Missing, extra or changed
bytes fail before execution. Both commit IDs are pinned in the loader; changing
a JSON's claimed revision cannot repin it. Git SHA-1 object identity here is
historical provenance/integrity, not independent review or a release signature.
All tests run offline with no old Git objects or network acquisition.

For deliberate reproduction, acquire those public exact commits into a separate
repository (no credentials required) and run from the product root:

```sh
python3 controller/test/fixtures/historical-runtime/export.py /path/to/repository.git
node --test controller/test/historical-runtime.test.mjs
```

The exporter reads Git objects only and deterministically reproduces both JSON
files. It does not fetch, change refs/config, install source or rewrite history.
Review changes to retained bytes as provenance changes, not ordinary fixture
updates. Preserve the original commits and meaningful recovery tests.
