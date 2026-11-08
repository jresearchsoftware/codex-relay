# Shared TEST lock

Before a manual or automatic Task uses or changes the single shared disposable
TEST contour, claim its ownership marker. This implements the existing
[TEST authority](execution-policy.md#test-environment-authority); a successful
claim is sufficient allocation without another owner assignment. It grants no
additional host, credential, PROD or execution authority. Tasks that do not use
this TEST contour need no lock.

The marker is **on the TEST host**, at
`/var/lib/codex-relay-test/test-environment.lock`, shared by all users of the
`codex-relay-test` contour established by
[Task 76](https://github.com/jresearchsoftware/codex-relay/issues/76).
Run [the helper](../scripts/test-environment-lock.py) on that host through the
execution's already authorized TEST transport. A marker in a local checkout,
another host or a separate sandbox does not reserve the shared contour. Existing
host/TEST access remains necessary; this helper creates no privileged transport
for automatic workers (broader capabilities belong to Task 181).

Use the same persistent file for every Task. Keep it out of TEST reset/cleanup
lists, and never delete, rename or replace its inode during ordinary use.
One-time provisioning uses the established TEST administrator to create the
regular marker with read/write access for the existing authorized TEST users
(currently root and the TEST group), without changing unrelated paths.
Run on the host's local Linux filesystem, not through an NFS client.
Linux `flock` serializes marker inspection/update; the recorded claim persists
across commands and process exits. There is no lease, timeout, queue or age takeover.
The bounded Task 217 exercise also staged a standalone candidate copy at
`/var/lib/codex-relay-test/test-environment-lock.py` for existing authorized TEST
users. Invoke it with `python3` through the same transport; it uses the same
default marker. This staging changes no installed Relay source pointer. Prefer
the selected accepted product source once integrated, and keep all copies on the
same marker path.

## Claim and hand back

From the selected product source on the TEST host:

```sh
python3 scripts/test-environment-lock.py status
python3 scripts/test-environment-lock.py claim \
  --task example/project#42 --execution run-123
```

Preserve the returned holder's `token`, Task, execution, host, PID and timestamp
with the execution evidence. The PID identifies the claiming command, not a
persistent worker: its exit alone does not prove the Task stopped using TEST.
`BLOCKED` (exit 2) includes the holder; report that Task and do not access TEST.
Even another execution of the same Task is a competitor.

Keep ownership across the entire TEST use, including related fixes and cleanup.
After completion or a handled failure, restore/verify usable TEST, then:

```sh
python3 scripts/test-environment-lock.py release \
  --task example/project#42 --execution run-123 \
  --token <returned-token> --test-usable
```

The exact Task, execution and token must match. `--test-usable` records the
executor's cleanup confirmation; the marker cannot itself test service health.
Do not unlock if cleanup fails. Report the retained holder and remaining repair.
Tokens prevent accidental cross-execution release; this is cooperative
coordination among authorized users, not an adversarial access boundary.

For bounded work, the helper claims once, runs the command, executes a Task-owned
cleanup/health script on success or handled failure, and releases only if cleanup
returns zero:

```sh
python3 scripts/test-environment-lock.py run \
  --task example/project#42 --execution run-123 \
  --cleanup-script /absolute/path/to/restore-and-check-test -- work-command arg
```

Busy never starts work or cleanup. Work failure retains its exit code after
successful cleanup. A killed/crashed wrapper, interrupted transport, unavailable
cleanup script or failed cleanup can leave ownership held; inspect it below.
The cleanup script must stop/wait for any TEST work left by the command before
returning zero; a parent process exit alone does not establish that condition.

## Interrupted ownership

Read `status`, locate the recorded execution and confirm through its actual
session/process/job and TEST evidence that it no longer uses TEST. Age, an exited
claim PID, lack of a recent Outcome or a newer Task alone is insufficient.
Stop at uncertain/live ownership. Once stopped, restore and verify usable TEST,
then recover **the exact observed token**:

```sh
python3 scripts/test-environment-lock.py recover \
  --token <observed-token> --confirm-holder-stopped --test-usable
```

Recovery serializes with claims and refuses a stale token, preserving any newer
holder. Recheck `status`; the next Task claims normally. Do not blindly retry an
uncertain claim: inspect whether its recorded execution already owns the marker.
A damaged/incomplete marker fails closed. Inspect its bytes and reconcile all
potential users before an established TEST administrator repairs that same inode;
never infer free ownership from malformed data or replace a live marker.
