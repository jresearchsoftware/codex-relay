# Task 109 Step 4: terminal prepublication qualification frontier

Authority: [Task 109](https://github.com/jresearchsoftware/codex-relay/issues/109),
[current Request 6106333263](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6106333263)
and [Decision 6106329052](https://github.com/jresearchsoftware/codex-relay/issues/109#issuecomment-6106329052).
This is qualification evidence and a review handoff, not executable authority.

## Source and installation boundary

The accepted source is `cf4c06b1061797e90df645ec45980a068e138ff5`, the
squash merge of [PR 110](https://github.com/jresearchsoftware/codex-relay/pull/110)
at independently approved head `d7f71133bd415eb550dae40449d4bb8d094ae1cd`.
Local normalization preserved the clean previous checkout and created the
Request's `codex/task-109-step-4` branch at that accepted source. No reset or
force publication was used.

The current consumer projection predates the new recovery template. Its
recovery workflow supports only `inspect` and `recover`; the accepted template
also requires explicit `inspect-prepublication`, `recover-prepublication` and
`candidate_head` inputs. This is the expected consumer-adoption gate exposed by
the accepted product change, not a claim that a runtime regression occurred.

The public `deploy/relay-deploy.py --phase workflow-project
--authorize-workflow-projection` interface generated the candidate from the
clean accepted source and the existing durable owner configuration. Only the
recovery projection and its manifest digest changed. The routing and owner
lifecycle projection bytes remain identical. No template was edited to produce
this consumer proposal.

**STOP: independent review and ordinary acceptance of this consumer projection
are required before installation.** The protected lifecycle was not invoked.
The AGENTS routing clarification authorized by the selected Decision is included
in this same handoff. No new Task or Step was allocated.

## Disposable Debian qualification

Qualification used a native Debian WSL filesystem with Node 22.20.0, Python
3.11.2 and Git 2.39.5. All mutated attempts, objects, remotes, configurations and
identities were synthetic. No original Task 97 evidence or host credentials
were used as fixtures.

The accepted source's focused suites passed **47/47 with zero skips**, run as
native root:

```sh
node --import ./consumer/test-support/consumer-env.mjs --test \
  controller/test/prepublication-recovery.test.mjs \
  controller/test/worktree-observation.test.mjs
```

Coverage includes real UID 983/985 separation with GID 979: 0640 group-readable
bytes are observed; 0600 fails for the collector; root observation succeeds
without changing source UID/GID, mode or ctime. It also covers ancestor/ref/object
symlink rejection, hardlinked object/worktree rejection, isolated Git metadata,
incomplete observation, transient-secret/identity/mode rejection, changed
authority/candidate/remote, fresh native owner authorization, preserved historic
evidence, one publication reservation and no repeat push after ambiguous failure.
The committed [focused TAP log](task-109-step-4-focused.tap) records these checks.

The existing namespace proof also passed:

```sh
sudo python3 deploy/ansible/tests/installed_runtime_proof.py --consumer-only
```

Its private mount/PID/network namespace exercised actual rendered templates,
root-owned configuration parents, real Writer sudo admission, rejected writable
or symlinked parents, preserved child access and credential isolation. It also
passed the owner lifecycle Python closure and final parent-drift gates. Its
synthetic installed identities differ from the 983/985/979 collector test; these
are complementary proofs, not one integrated original-attempt recovery proof.

Two setup failures preceded the focused PASS. Git archive extraction preserved
group-writable fixture mode 0664, correctly rejected by consumer loading. The
first distinct-UID spawn could not traverse the operator's private home to reach
Node. Only the disposable source modes and a disposable copy of the same Node
binary were corrected. Neither failure caused an original-attempt permission
repair or a source-code correction.

Dedicated concurrent race qualification and live installed procfs/root-helper
recovery with the original candidate have not been completed. Passing the
symlink/hardlink tests and source timestamp checks does not substitute for those
proofs. No claim of complete incident-use qualification is made.

## Read-only protected host observation

Existing owner SSH access was used with verified operator-key and host-key
fingerprints. Public evidence contains only bounded summaries and digests.

- Installed revision: `dbfea1889da994791a5b6c05d97a71405d21eac5`.
- Admission: `open`, no operation, no active or unknown attempts.
- Worker UID 983 and general-runner/collector UID 985 exist; the collector's
  supplementary groups include GID 979.
- The fixed Writer helper and owner lifecycle helper are root-owned 0750; the
  publication lock is root-owned 0600.
- Protected installed consumer configuration matches the durable deployment
  snapshot. The installed source does not yet contain prepublication recovery.
- The host's fixed Node executable reports **18.20.4**, below the documented
  minimum 22. This is a pre-existing environment observation; its origin was
  not diagnosed. It must be dispositioned before claiming supported live
  qualification. No Node upgrade or alternate executable was substituted.

The preserved original attempt is still `run-38088852703`; its journal binds
Request 6102494929 with digest
`72b203fe1dc64a8557fd93c2a311cbd7199d37303b445fb22e29a83a14bf04a9`.
Native authority selection confirms that this remains the current Task 97 Step 3
Request. The stored execution reports successful returned work, `child=started`
and `containment=reaped`. Writer still binds historic BLOCKED Outcome 6102635866,
with no collection or publication intent and no prepublication reservation.

Bounded direct ref inspection confirms retained candidate
`0e796cd8deeab3871478b3721ea4f556d8e4094a` on `codex/task-97-step-3`.
No trusted Git command was run against worker metadata. Complete reachable
object/worktree validation and current remote eligibility remain deferred to the
qualified installed recovery path; ref presence is not candidate acceptance.

Observed immutable-file digests for later comparison:

| Evidence | SHA-256 |
| --- | --- |
| Original journal | `07d09f0a2510d0156b5df4a11e64ef1841333fa328896a7ba72dfb65e75d01a4` |
| Original Writer record | `9e9f83ef380f6fffddc1422d670a8b4901baf516408004541a548058758e869f` |

No host installation, lifecycle transition, service/configuration/credential
change, permission repair, evidence cleanup, original Task 97 authority edit,
recovery inspection, recovery publication or model replay occurred. The exact
Task 97 native owner authorization body has not been generated or posted.

## Validation and warnings

The complete candidate set ran on a native Debian filesystem: `git diff --check`,
`npm test`, deployment pytest, locked Cargo tests, Cargo formatting,
`scripts/qualify.py` and `scripts/check-candidate.py` passed. Node reported
669 passed, zero failed and one root-only skip (separately passed above).
Deployment pytest reported 865 passed, 299 skipped and 19 warnings. Skipped
privileged/environment-dependent cases are not host qualification. The warnings
were one Python `crypt` deprecation and 18 Jinja invalid-escape deprecations;
these are environment/dependency observations, not evidence of a regression
introduced by the projection or documentation change.

Required native CI remains in the PR's own check records. The disposable root
qualification above remains separate from ordinary unprivileged checks and from
live-host proof.

The primary Step 4 [routing run](https://github.com/jresearchsoftware/codex-relay/actions/runs/38118917658)
and its route check annotation report closure normalization to `keep-open`.
Native authority selection also returns `ISSUE_CLOSURE_POLICY_INVALID`: the
charter's backtick-wrapped closure value is noncanonical. Both current Requests
bind keep-open, and no Issue closure was attempted. The charter was not edited
because that would invalidate its digest-bound authority.

The native task-title update succeeded, but the available read-back displays a
truncated title. Exact persistence is unverified and nonblocking. Requested
profile: gpt-6.1-sol/xhigh, Subagents On; actual model/effort UNAVAILABLE, no
subagents used.

After independent acceptance and appropriately refreshed exact authority, this
same Step can resume at the projection/host qualification boundary. Installation
must still use the supported pinned lifecycle. Only after verified installation
and complete original-attempt inspection may the owner post the exact native
Task 97 authorization and permit one supported recovery. Task 97 still needs
independent exact-head review after any recovered PR. Both Issues remain open.
