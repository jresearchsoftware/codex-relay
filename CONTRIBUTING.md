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

For one focused suite, retain the test consumer preload:

```sh
node --import ./consumer/test-support/consumer-env.mjs --test controller/test/publication-recovery.test.mjs
node --import ./consumer/test-support/consumer-env.mjs --test consumer/test/security-contracts.test.mjs
```

| Change | Relevant contracts and checks |
| --- | --- |
| Routing, publication, recovery | `controller/README.md`, controller tests |
| Launcher/results/isolation | `runtime/README.md`, runtime and security-contract tests |
| CR wire or validation policy | `contracts/README.md`, Node CR tests, Reviewer tests and `scripts/qualify.py` |
| Reviewer config/transport/publication | `reviewer/README.md`, Cargo fmt/tests and qualification |
| Consumer config/examples/docs | `consumer/README.md`, portability tests, qualification, candidate scan |
| Optional developer hooks | Only for hook changes: suites in the [hook qualification contract](.codex/hooks/README.md#qualification) |

Local contract qualification does not qualify installed sudoers, wrappers,
process containment, App permissions, workflow runner restrictions or mTLS
ingress. Those require a separately authorized consumer deployment validation.
