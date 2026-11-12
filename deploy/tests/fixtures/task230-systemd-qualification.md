# Isolated Task 230 installation qualification fixtures

These scripts run only in an explicitly acknowledged, disposable root Debian
container with real systemd, a private cgroup namespace, and no network interface
except `lo`. They do not target a shared installation or use real credentials.
They are separate from the ordinary automated test suite.

`qualify_task230_systemd.py --isolated-disposable-container` adapts only Docker
provisioning/transport in the existing native lifecycle regression. It uses the
unchanged production unit and helper templates and actual systemd. Reviewer and
Runner business processes and credential-readiness are the existing synthetic
inputs. The fixture checks real non-root main processes, privileged start gates,
root-only operation evidence, activation, restart, recovery and failure
propagation. Its `/opt/lifecycle` bind is read-only and executable because the
assigned container's `/tmp` is `noexec`.

For a final source check, acquire a fresh clean Git clone from the exact candidate
bundle under `/qualification`, then run:

```sh
python3 deploy/tests/fixtures/qualify_task230_public_cli.py \
  --isolated-disposable-container --namespace t230-final \
  --source-root /qualification/final-source --expected-revision "$candidate_sha" \
  --reviewer-only --test-external-prerequisites
```

The script executes actual public CLI subprocesses for configuration validation,
workflow projection, committed projection verification and root-local inventory.
It also verifies the exact missing external App prerequisite and absence of a
source activation. This refusal is explicitly **not** a successful Apply. The
printed report contains the private fixture root, selected source path and exact
commit. Without `--source-root`, it makes a synthetic Git snapshot for fixture
debugging; such a snapshot never establishes final-head qualification.

To exercise the actual public installer with the separately supplied offline
prerequisites, use the printed fixture root and the same candidate SHA:

```sh
python3 deploy/tests/fixtures/qualify_task230_backend.py \
  --isolated-disposable-container --fixture-root "$fixture_root" --prepare \
  --config "$fixture_root/consumer/relay.json" \
  --consumer-root "$fixture_root/consumer" --resolved-revision "$candidate_sha" \
  --connection local --log-root /qualification/backend-final-logs --phase install
```

This fixture changes neither the installer backend nor service operations. Its
Ansible launcher adds explicit TEST prerequisite inputs: package management is
disabled for an already provisioned offline host, and the real Rust 1.90.0 prefix
and copied Cargo registry are selected. The actual locked Reviewer build, archive
extraction, artifact identities, manifests, root protection, units, sudo rules,
namespace probes and systemd operations remain active.

The following substitutions are intentional and must accompany any reported
result:

- GitHub pool permission and remote registration/label observations are local
  synthetic data. No real App private key or access token is supplied. Local pool
  `State`, `Host`, `reconcile`, registration execution under the Runner UID, and
  systemd startup use production code.
- The external Runner distribution is a small archive with a version probe,
  registration-marker writer and a service process. It does not connect to
  GitHub Actions or accept work.
- The Codex installer route serves the existing checked-in synthetic installer
  at the exact official URL. The real Ansible download, isolated install and
  package guard still run; the installer writes only the bounded synthetic
  package. A later operation seeds an existing TEST package before public
  preflight when needed, so it cannot change installation identity mid-operation.
- The configuration, repositories and SSH host key are synthetic TEST inputs.
  A final repeat uses a clean exact candidate source, a fresh namespace and
  distinct namespace-derived Unix identities and pool name.
- `--test-external-prerequisites` writes TEST-only RSA material and a short-lived
  self-signed server certificate beneath the private fixture root, and selects
  them through the normal configuration reference fields. `--reviewer-only`
  explicitly disables automatic publication in this synthetic consumer. Without
  it the fixture also provides a clearly synthetic Codex token and Writer key;
  their format is not evidence of external API access.
- Its named external ingress prerequisite is a real systemd service running
  Python's HTTP server under `nobody`, bound to loopback. It deliberately stands
  in for the consumer's external shared ingress; it does not establish nginx or
  Docker ingress qualification. Its original PID/start stamp is retained for
  preservation checks.
- `--seed-reviewer-credential` generates a TEST-only RSA App key and client CA
  for the actual Reviewer credential/start gates. Run the same fixture with
  public `--phase activate --authorize-reviewer-activation` after the initial
  expert backend materialization; this executes the compiled Rust Reviewer under its
  non-root service identity. The external pool fixture defers registration until
  that real readiness gate passes. An initial materialization/refusal is not an
  overall successful Apply; repeat the public Apply after activation.

For a subsequent actual upgrade, `--seed-predispatch-marker` inserts a bounded
synthetic no-worker record under the real Writer mutex. It requires an installed
consumer, never replaces existing history, and checks byte preservation after a
successful public operation. This supplements the exact old-reader and rollback
tests; it does not replace original-run recovery qualification.

The host needs actual Node 22, Python/Ansible, GCC/binutils, libc development link
inputs, `ss`, `bubblewrap`, and the pinned real Rust toolchain/offline crate cache.
Missing manifests, development link stubs or archiver tools are fixture setup
failures. Preserve their logs; repair the isolated prerequisite and repeat the
same bounded TEST operation, or use a fresh TEST namespace. Do not weaken a
production guard to make an incomplete fixture pass.

`task230_github_https.py --isolated-disposable-container --prepare` provisions
the isolated container's mock transport once. Run the same command without
`--prepare` as a background fixture process. It serves synthetic GitHub responses
through real HTTPS on `127.0.0.1:443`; the container has no external interface.
The backend fixture supplies its small synthetic Runner archive and Codex installer
at their exact pinned URLs inside the mock; the Runner hash is an extra variable
only in this disposable container. Production URL assertions and public
entrypoints remain active.
Only this disposable container receives the DNS aliases and TEST trust anchor.
The `/usr/bin/node` launcher invokes the actual Node 22 binary with
`--use-system-ca`; actual production JavaScript, JWT signing, secret scrubbing,
Python urllib, Node fetch and native authority validation remain in use. The
request log records only methods and URL paths. Dynamic original-run/owner
authorization observations are JSON fixtures in
`/qualification/github-mock/active.json`. No live GitHub permission is proven.

The two public OpenAI client CA files must be supplied as offline prerequisite
bytes beneath `/qualification/github-mock`, using the canonical filenames. The
fixture can serve them at their original HTTPS URLs so the unchanged owning TLS
helper verifies their exact source-pinned SHA-256 certificate fingerprints and
chain. They are public CA certificates, not credential or private-key inputs.

A successful baseline Apply is separate from original-attempt bridge,
interruption/forward-recovery and rollback qualification. Record those actual
results and the exact source SHA independently. These fixtures do not establish
PROD recovery, independent acceptance, GitHub App permission qualification, or
real Codex/Actions execution.

## Coupled Actions rerun and installed Apply fixture

After a successful isolated baseline installation, run the exact candidate's
shared admission/routing scenario against its real installed publication and
execution stores and protected admission gate:

```sh
RELAY_CONSUMER_CONFIG="/etc/$namespace/consumer.json" RELAY_EXECUTION_SLOT=primary \
  node deploy/tests/fixtures/qualify_task230_rerun.mjs \
  --isolated-disposable-container --expected-revision "$candidate_sha"
```

The script requires the offline root container, the exact clean Git candidate,
and unused synthetic run IDs 99 and 100. It never replaces existing history.
Its child holds the actual Writer publication mutex throughout the scenario.
GitHub observations and the contained worker result are synthetic; the production
broker, routing entrypoint, `runAttempt`, disk stores and installed gate run
unchanged. Its in-process Writer transport models the fixed privileged helper's
credential-free `complete-execution` interception through the admission
capability; this interception does not go through broker request parsing in the
production helper. It does not prove the helper's external caller/UID boundary.
The scenario models durable successor admission on Actions attempt 1,
interruption before launch, rerun attempt 2, one completed worker and terminal
replay. It checks the finalized predecessor, completed successor and empty
installed active/unknown inventory. This is not evidence of an actual GitHub rerun.

Then run the same public Apply used for the baseline, with the same candidate
revision and fixture configuration. Its real quiesce/drain and installer must
succeed. Finally repeat the command above with `--verify-preserved` to verify
the exact bytes of both publication records and the successor execution journal.
`/qualification/task230-rerun-evidence.json` records the candidate revision,
hashes, one-worker count, inventory and synthetic boundaries. Preserve the public
Apply logs separately. Successful seeding or inventory alone is not an Apply
result. A Podman transport may supply the fixture's `/.dockerenv` sentinel only
after independently establishing root, real systemd, a private cgroup namespace,
and a private network namespace containing only `lo`; report that substitution.

## Preserved exploratory evidence

The intermediate synthetic source commit
`92a86b53441889529c4d68fcb174791948a7789d` is a fixture snapshot, not an
accepted candidate or final-head claim. Its actual expert backend run completed
`ok=1060 changed=389 failed=0`, built the locked Rust Reviewer and installed its
binary. Native activation subsequently launched that actual Reviewer as its
non-root user. The synthetic Runner registration process and real pool
`State`/`Host`/`reconcile` launched its actual non-root systemd service.

Earlier exploratory failures are retained in the container logs: incomplete
copied Reviewer build manifests, missing offline libc link stubs/binutils, absent
client CA, and an initial Runner start before Reviewer readiness. They were TEST
setup gaps. The helper now defers synthetic registration until actual readiness.
The partial pool start was diagnosed through real state/PID observations and
completed using actual `Host.start`, followed by the fixture's explicit
`--reconcile-pool-only` mode. It never deletes registration/history to simulate
successful recovery.

An expert `--phase upgrade` against that retained marker refused with
`PREDISPATCH_TARGET_INCOMPATIBLE` before quiesce; this is separate negative
evidence and does not establish ordinary `--phase install` qualification.
The first ordinary install repeat also exposed a Docker capability constraint:
unprivileged Docker exec root could see the non-root Reviewer's socket but could
not inspect its `/proc/<pid>/fd` links. A privileged **exec process** in the same
offline container obtains the real `ss` PID ownership evidence. This transport
change neither replaces `ss` nor changes production guards. Report it with the
final commands; the container still has only `lo` and no external network.
