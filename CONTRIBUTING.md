# Contributing

Ordinary human contributions do not require Relay installation, GitHub Apps,
Codex, owner task admission or production credentials. Open a bug/question Issue
for unclear behavior, or propose a focused PR with the problem, resulting
behavior and commands/results you checked. Use synthetic reproduction data.
See [SECURITY.md](SECURITY.md) for sensitive findings.

Work on a normal branch (or fork when the public repository exists). Keep
unrelated changes separate. Add regression coverage for changed behavior;
documentation corrections only need relevant consistency checks. The maintainer
reviews scope and trust boundaries before merge. `AGENTS.md` and `.codex/hooks/`
describe the owner's optional Codex workflow, not human contribution gates.

## Keep workflow documentation current

A Task that changes an operator/user-visible Relay workflow or its Task Request,
Decision, CR, Step, Outcome, admission, review or continuation contract must
update the relevant human documentation and examples in the same Task and PR,
or explicitly explain in that Task/PR why no documentation change is needed.
This includes remediation that changes those surfaces. Check instructions and
examples against the implemented behavior and governing component contracts;
keep consumer policy distinct from Relay protocol and qualify legacy behavior.
Use the existing PR description and review process, without a separate
documentation approval, CI gate or policy registry. Start the owner workflow at
the [Task workflow guide](docs/task-workflow.md).

## Execution environment and shell routing

Use syntax native to the environment where the command actually executes. Prefer
the shortest qualified transport that preserves the required implementation
language and authority: native Windows PowerShell for Windows-local work;
`wsl.exe --distribution <distro> --exec` with the Linux executable and arguments
when Linux execution is needed from Windows; direct execution when already in
Debian/WSL/Linux; and a source-controlled `.sh` entrypoint when Bash-specific
behavior is the implementation boundary. Use native Linux paths inside Linux and
do not add an unnecessary WSL or shell hop.

Use PowerShell Core (`pwsh`) for PowerShell-oriented work on Windows or Linux
when Bash is not required. Prefer direct argument passing, structured tool
arguments, stdin, or a script file (`pwsh -File` / `bash <script>`) over nested
command strings. Do not carry non-trivial JSON, patches, Markdown or commands
through multiple shells for reinterpretation.

A transport choice does not replace a source-controlled protected entrypoint or
authorize another credential/security boundary. For material PowerShell-to-native
calls, propagate failure immediately before dependent work:
`$ErrorActionPreference = 'Stop'` alone does not establish native fail-fast
behavior; use supported native error propagation or inspect `$LASTEXITCODE`
immediately and throw/exit on unexpected nonzero results. Handle intentionally
expected nonzero results explicitly so a later successful command cannot hide
the material failure.

Runtime/filesystem boundary checks require the native Linux filesystem described
below. A Windows-mounted checkout is not evidence for those Linux
filesystem/security invariants.

## Local validation

Run from the repository root on a native Linux filesystem, including WSL.
Node's declared minimum is 22; the checked toolchain is Node 22.20.0,
Rust/Cargo 1.90.0, Python 3.11.2, Git 2.39.5 and OpenSSL 3.0.18 on Linux x86_64.
Other version combinations are not qualified by that evidence. Cargo uses the
locked dependencies; Node uses built-in modules, with no npm install step.
The scan-policy test also uses Python 3. Consumer JSON must have POSIX permissions
that are not group/world writable. A Windows-mounted checkout is insufficient
for the Linux filesystem/security tests; use a native Linux checkout.

```sh
npm test
python3 -m pytest -q deploy/tests deploy/ansible/tests
cargo fmt --manifest-path reviewer/Cargo.toml --check
cargo test --manifest-path reviewer/Cargo.toml --locked
python3 scripts/qualify.py
python3 scripts/check-candidate.py
git diff --check
```

The candidate scanner reads tracked working-tree files, so stage intended new
files before running it. It checks JSON syntax, local Markdown links and bounded
credential markers; it does not certify absence of private knowledge or secrets.
Qualification uses temporary fixtures/keys and loopback mock GitHub; Cargo can
download locked build dependencies. No model calls or live GitHub writes occur.

The [Public CI workflow](.github/workflows/relay-exact-head-validation.yml) runs the Node,
Cargo, qualification, candidate-scan and whitespace commands above for pull
requests targeting `main` and pushes to `main`. The complete deployment pytest
suite remains separate. The candidate job also runs the root synthetic sandbox
cleanup qualification on its disposable hosted runner. Its stable
check name is `Candidate checks`. PR runs check out the exact PR head; push runs
check out the pushed commit. The whitespace step also checks the committed diff
against the PR base or the previous `main` head.

CI uses GitHub-hosted Ubuntu 24.04 with Node 22.20.0, Rust/Cargo 1.90.0 and
Python 3.11.16. Git and OpenSSL come from the runner image; the job records the
candidate SHA and resolved tool versions. Actions are pinned to full commit
SHAs, checkout credentials are not persisted, and workflow permissions are
limited to read-only repository contents. Public CI needs no configured secrets,
Relay installation or consumer state. Its candidate checks do not run the
consumer deployment. The `Codex CLI compatibility` job in the same exact-head
workflow runs the credential-free probe of the exact official Codex release and
targeted workflow, launcher and diagnostic tests under an ordinary UID. It uses
hosted disposable infrastructure and mock transport; it does not access a
consumer installation or call a model. The full deployment suite and
[disposable installed-runtime proof](deploy/README.md#qualification) retain
their separate validation scope and execution requirements.

The repository's separate [self-dogfood control workflows](docs/self-dogfood-workflows.md)
use an accepted installed Relay revision. Their presence does not qualify public
runner activation or permit candidate code on persistent privileged runners.

For one focused suite, retain the test consumer preload:

```sh
node --import ./consumer/test-support/consumer-env.mjs --test controller/test/publication-recovery.test.mjs
node --import ./consumer/test-support/consumer-env.mjs --test consumer/test/security-contracts.test.mjs
```

| Change | Relevant contracts and checks |
| --- | --- |
| Routing, publication, recovery | `controller/README.md`, controller tests |
| Launcher/results/isolation | `runtime/README.md`, runtime and security-contract tests |
| Task/Decision/CR authority or validation policy | `contracts/README.md`, Node authority/CR tests, Reviewer tests and `scripts/qualify.py` |
| Reviewer config/transport/publication | `reviewer/README.md`, Cargo fmt/tests and qualification |
| Consumer config/examples/docs | `consumer/README.md`, portability tests, qualification, candidate scan |
| Optional developer hooks | Only for hook changes: suites in the [hook qualification contract](.codex/hooks/README.md#qualification) |

Local contract qualification does not qualify installed sudoers, wrappers,
process containment, App permissions, workflow runner restrictions or mTLS
ingress. Those require a separately authorized consumer deployment validation.
