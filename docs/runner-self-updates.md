# GitHub Actions Runner self-updates

GitHub's native updater owns ongoing Runner software updates. Relay's single
bootstrap package contract is in `deploy/ansible/group_vars/all.yml`: version,
official release source and SHA-256. URL and archive names derive from that
contract. Bootstrap still verifies the checksum, archive layout and executable
version before installation; it never extracts untrusted archives as root.

Ordinary Apply retains a complete, runnable installed Runner, including an older
version waiting for a GitHub offer and a newer native-updated version. Its
numeric version is diagnostic evidence, not proof that GitHub still supports it.
GitHub determines update rollout and version enforcement. Apply does not downgrade
software, repair a registered corrupt installation automatically, re-register it,
or migrate its update setting. Malformed versions, failed probes, missing files
or unsafe paths require diagnosis. Native `bin -> bin.VERSION` links remain
inside the same runner root. Frozen bootstrap bytes are not a drift baseline
for native-updated software.

Apply, managed-pool preflight and staged package checks require both `bin` and
`externals` to resolve to real, usable directories inside the instance. External
`nodeNUMBER/bin/node` runtimes must be real executable files with searchable
parents; no Node release number is pinned by this check. Missing/dangling links,
empty or inaccessible external runtimes and unsafe aliases cannot pass merely
because Listener still reports a version. Registered damage requires bounded
stopped-only repair; ordinary Apply/staging never replaces that software.

New registrations omit `--disableupdate`. Existing registrations retain their
persisted setting: removing the flag from source cannot change them. Registration
reuse reports the actual version and `disable_update` setting without changing
the running listener. Inspect both `.runner` and `.runner_migrated`; upstream
prefers the migrated file when present.
The registration diagnostic reports `disable_update_source` and
`disable_update_mismatch` alongside `disable_update`. With a migrated marker,
the latter value comes from `.runner_migrated`; a mismatch is visible even when
the two files have the same registration identity. Reuse leaves both untouched.
Do not treat a mismatch as a completed migration: inspect and finish the stopped
maintenance procedure before claiming enabled effective settings.

## Existing-registration maintenance

The narrowly scoped `deploy/runner_self_update.py` maintenance interface changes
only `disableUpdate` to `false` in both existing settings files, preserving their
other fields and the registration ID. This is Relay-owned maintenance backed by
upstream's settings and message-polling implementation, **not a documented
GitHub reconfiguration command**. It needs no new registration token, GitHub
registration mutation, changed labels/groups or new credentials. It neither
reads nor replaces credential contents. GitHub receives the effective setting
when the restarted listener polls for messages. That makes sufficiency of the
local migration a code-backed inference; real server negotiation and update/job
acceptance must still be observed on the installation. There is no documented
separate server-side enable-update toggle. Runner-group ACLs stay unchanged.

Run the interface from an exact accepted product checkout through an explicitly
owner-authorized maintenance session. Ordinary product Apply does not invoke it.
Use the actual service, root, user and recorded GitHub runner ID/name; the
following identifiers are synthetic:

```sh
python3 deploy/runner_self_update.py inspect \
  --root /opt/sample-runner --service sample-runner.service --user sample-runner

# Only after the owner has drained and stopped this exact service:
python3 deploy/runner_self_update.py migrate \
  --root /opt/sample-runner --service sample-runner.service --user sample-runner \
  --agent-id 123 --agent-name sample-runner
```

Migration requires a stopped, process-free target and consistent private settings
owned by the runner. It checks the service's configured user and working
directory, refuses active or ambiguous state, preflights all files before the
first change, and atomically replaces each settings file with fsync. An
interruption between the two replacements can leave a mixed true/false pair;
keep the service stopped and repeat the same migration with the same identity.
It converges that pair without re-registration or credential replacement.
Do not start a partially migrated listener. Invalid identities, malformed JSON,
aliases or unknown process state require inspection rather than a force flag.

## Controlled pool transition

Source acceptance and installation do not authorize this operational transition.
Use a separately owner-authorized private Git-managed Apply for the accepted
source, followed by an explicitly authorized bounded maintenance route, or an
owner-approved private maintenance composition. Never restore the retired public
lifecycle workflow.

1. Refresh the exact installed product/configuration, service inventory and
   registration IDs. Verify the unchanged external runner-group repository and
   trusted workflow/ref restrictions. Inspect current jobs and queue state using
   the existing authorized GitHub installation. An inaccessible API is an
   evidence gap; labels and a running service do not prove idle capacity.
2. Finish the controlling Apply before migrating its transport runner. Keep at
   least one independently verified usable General Runner online. Drain one
   other General Runner, stop only its service through the authorized owner
   route, and verify its cgroup/processes are empty. Do not modify a runner
   carrying an active job, including the maintenance job itself. If safe idle
   capacity cannot be proven, use an owner-authorized out-of-band maintenance
   session rather than guessing.
3. Inspect and migrate that exact registration. Start it using the existing
   authorized service boundary. Observe native update logs, actual running
   version, online registration and an accepted-job completion under the same
   restricted workflow refs. Keep its original name, ID, group, labels, work
   root, Unix user and execution history. Repeat sequentially for the remaining
   General Runners; migrate the former transport only after another verified
   runner can carry the private lifecycle.
4. Treat the distinct Production Runner separately after the General pool is
   viable and no production job is running. Preserve its Reviewer activation
   gate and service dependency. Use its own ID/root/user and the same stopped
   migration, then observe health and the permitted production job path.
5. Record evidence for all seven registrations, both settings files, actual
   running versions, service health and accepted public routing/recovery and
   private lifecycle jobs. GitHub's latest public release alone does not prove
   the version offered to this installation or successful job handoff. Keep the
   Task open until its authorized operational completion conditions hold.

The dedicated runner owns its software root, diagnostics, versioned update
directories and work root. Existing systemd writable-path restrictions permit
updates only within those namespaces. No root-owned recursive extraction,
credential widening or new shared writable parent is needed for native updates.
The official `run.sh`/`run-helper.sh` wrapper handles update exit codes and
relaunches the listener after `update.finished`; the unit's `Restart=on-failure`
is not itself proof of successful update recovery.

## Interrupted update and bounded repair

Upstream replaces `bin` and `externals` links sequentially. An interrupted
update can leave a missing link; the wrapper can then exit successfully while
the service is offline. There is no atomic two-link transaction or guaranteed
automatic rollback. Inspect `_diag/SelfUpdate-*.failed`, update logs, both
versioned directories, listener process/version and service status. Preserve
registration, credentials and historical work; do not rerun registration.

With the exact target stopped and process-free under separate owner authority,
repair only the two links to a complete, validated pair from the same official
version already staged by the updater. Alternatively restore the previous
complete pair if it is still supported; an expired version is not an operational
rollback target. Verify containment and package provenance before changing
links. If neither retained pair is trustworthy, obtain the selected official
package and checksum, validate it through the existing archive validator, and
repair software as the runner identity while preserving instance state. A
fresh download or repaired executable is not proof of GitHub job acceptance.
Retain update evidence and retry only after the failure has been diagnosed.

## Upstream evidence and TEST scope

The implementation was checked against Runner `v2.338.2`:

- [ConfigurationStore](https://github.com/actions/runner/blob/v2.338.2/src/Runner.Listener/Configuration/ConfigurationStore.cs)
  selects `.runner_migrated` and persists `disableUpdate`.
- [MessageListener](https://github.com/actions/runner/blob/v2.338.2/src/Runner.Listener/MessageListener.cs)
  and [BrokerMessageListener](https://github.com/actions/runner/blob/v2.338.2/src/Runner.Listener/BrokerMessageListener.cs)
  pass the setting when requesting messages.
- [SelfUpdater](https://github.com/actions/runner/blob/v2.338.2/src/Runner.Listener/SelfUpdater.cs),
  [update shell](https://github.com/actions/runner/blob/v2.338.2/src/Misc/layoutbin/update.sh.template),
  [run wrapper](https://github.com/actions/runner/blob/v2.338.2/src/Misc/layoutroot/run.sh)
  and [helper](https://github.com/actions/runner/blob/v2.338.2/src/Misc/layoutroot/run-helper.sh.template)
  own download/update and restart behavior.
- [Release](https://github.com/actions/runner/releases/tag/v2.338.2) supplies the
  bootstrap linux-x64 checksum. Progressive rollout means latest release and
  installation-specific offered version can differ.

`python3 scripts/qualify-runner-self-update.py` exercises the exact checksum-bound
official update/wrapper shell in an isolated native Linux temporary directory,
with synthetic listener/job transport and no live registration credentials.
It tests old-to-new link layout, wrapper handoff and interrupted/failed update
repair. Migration and Ansible regression tests cover retained registrations and
Apply convergence. These tests do not prove GitHub server negotiation, a real
native binary download, effective external ACLs or healthy installed PROD jobs.
