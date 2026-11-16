# Workflow-aware GitHub repository governance

<a id="GH-001"></a>
**GH-001 — Explicit workflow adoption.**

Apply this protocol when selecting, adopting or changing GitHub repository
workflow and protection guidance, only if the owning project explicitly adopts
this topic in human-owned AGENTS or equivalent accepted policy. Installation,
updating the package and reading this file neither adopt it nor apply settings.
Existing project policy remains authoritative until its own reviewed adoption
reconciles duplicates and exceptions. This passive guidance grants no settings,
credential, execution, merge, publication, migration or closure permission.

## Start from the working model

<a id="GH-002"></a>
**GH-002 — Discover actual working paths.**

Read the project's accepted instructions, relevant owner decisions and actual
source/publication workflow. Identify important branches and published refs,
authorized human/automation writers, review and validation already in use, and
legitimate exceptions. Use existing project records; no new repository-type
field, registry, provisioning service, daemon or Relay dependency is needed.

<a id="GH-003"></a>
**GH-003 — Select by change and ref.**

These paths can coexist in one repository; choose by the change and ref:

| Working path | Guidance to select |
| --- | --- |
| Governed source development, manually operated or Relay-managed | Trace an admitted change to its canonical task/decision, reviewable PR and exact result. Use substantive independent acceptance and meaningful applicable checks under project authority. Manual operation preserves this baseline without importing Relay's typed schemas, launch, identity or routing contracts. |
| Living reference/evidence maintenance | Preserve explicit owner-authorized routine direct-to-main updates. Keep sources, dates, uncertainty and a useful commit explanation; validate the changed evidence. No Task Request or PR is required merely for a factual refresh. |
| Published/generated distribution | Follow the owner's release path from accepted source to identifiable artifact/version. Protect published identity separately from source-development merge choices. Generated publication can legitimately push directly. |
| Mixed workflow | State which changes use each path in existing instructions. Assess both ordinary human updates and supported automation; a repository-wide PR rule cannot distinguish materiality or file ownership by itself. |

<a id="GH-004"></a>
**GH-004 — Routine evidence versus material changes.**

A corrected date, source link or measurement under an unchanged interpretation
can be routine evidence maintenance. A changed general recommendation, supported
contract, security assumption or consumer obligation is material even in a
one-line edit. For material reference changes, recommend independent assessment
of evidence and effects before adoption through the project's authority. A PR
is a useful route, but another durable review/decision path may suffice. Do not
invent a universal threshold, require PRs for every refresh, or silently change
downstream consumer decisions when shared evidence changes.

## Select proportionate protections

<a id="GH-005"></a>
**GH-005 — Proportionate protection choices.**

Before making a control mandatory, apply [proportional-controls](proportional-controls.md):
identify the concrete harm, current protection, operator/maintenance cost and
least-friction sufficient alternative, including accepting risk. Preserve
stronger accepted protections. A recommended profile is a starting proposal for
owner adoption, not an already authorized configuration or universal gate.

| Concern | Recommended starting choice and exceptions |
| --- | --- |
| Lost important history or branch deletion | Where enforceable at reasonable cost, block force pushes and deletion on main/default and important retained branches. Ordinary non-force direct pushes remain possible without a PR requirement. Check administrator/bypass coverage. Intentional rewrite, deletion or recovery needs specific project authority; availability of bypass is not permission. If enforcement is unavailable, record the gap and use accepted non-force practice and existing recovery evidence, or escalate an unacceptable risk. |
| Accidental source integration without assessment | For governed PR development, prefer an enforced PR route if compatible with the accepted human/bot paths. Retain task traceability, exact-result independent acceptance and applicable validation whether enforcement is available or not. Do not mandate Relay, new CI, a fixed native approval count or a second review ritual. |
| Accidental merge style or stale task branches | For PR-centric work with disposable task branches, recommend squash-only and automatic deletion of merged head branches. Preserve merge/rebase when commit topology, individual commits or supported tooling matter. Retained release/integration branches need compatible deletion protection or auto-delete kept off. On a direct-main or generated repository these options have little ordinary-path effect; configuring them is optional unless its PR path justifies the work. |
| Ineffective checks or review identity | Require only checks that defend an accepted risk and reliably run for the permitted path; reuse existing meaningful validation. Select native review requirements only when qualified reviewers/identities are available and the project accepts the cost. An independent assessment through one owner's account does not supply a distinct native approving identity or satisfy GitHub's stronger requirements. An unavailable required reviewer/check is a gap to reconcile, not a reason to self-approve or bypass. |
| Changed head after review or integration conflict | Requalify affected checks and independent assessment for the changed result. Native stale-review dismissal or latest-push review may help where identity/workflow supports it. Strict up-to-date checks, merge queues, signed commits, deployments and extra reviews require their own risk/cost justification; they are not this protocol's baseline. |
| Frozen publication ref overwritten or removed | Preserve existing version/commit/tag identity using the accepted release boundary and authorized writers. Where appropriate, tag rulesets can restrict updates/deletion while permitting new release refs. Do not block the supported publisher's new-tag/default-branch transaction or broadly exempt it from immutability without examining the existing no-overwrite mechanism. |

<a id="GH-006"></a>
**GH-006 — Authority and supported writer exceptions.**

Merge settings do not enforce independent acceptance. Successful checks do not
grant merge authority. A PR-only rule can obstruct authorized direct writers;
prefer separate branches or an existing narrowly authorized publisher path when
that preserves both contracts. A broad PR bypass can also bypass other rules;
inspect the affected rules and identity rather than treating the exception as
harmless. Do not install a new bot or obtain broader credentials to satisfy a
suggested profile. Product-specific provisioning and enforcement remain local.

<a id="GH-007"></a>
**GH-007 — Separately owned release policy.**

For publication lifecycle, use [package-versioning](package-versioning.md) only
if separately adopted, otherwise the project's accepted release policy. Keep
accepted source, source integration, artifact publication and consumer adoption
distinct. Never rewrite a frozen release as repository cleanup; a repair uses
a new admitted version. A distribution default branch may represent the last
published payload rather than the highest SemVer. This protocol defines no new
release cadence, publisher, registry or maintenance-line arrangement.

## Verify what GitHub actually enforces

<a id="GH-008"></a>
**GH-008 — Verify actual host capability.**

Use the repository's current GitHub host/version, visibility, plan and existing
authorized access. Branch protection and branch/tag rulesets are available on
GitHub.com public Free repositories and on qualifying paid private repositories;
individual features, organization rules and Enterprise Server versions differ.
Read current feature documentation before depending on a capability. Rule
editing needs repository admin or an applicable custom permission; merge-option
and auto-delete editing also need appropriate settings access. Capability is
not owner authorization. No upgrade or privilege acquisition is required here.

<a id="GH-009"></a>
**GH-009 — Inspect effective layered protection.**

Inspect Settings / General for merge options and auto-delete; Settings / Branches
and Rules / Rulesets (including inherited rules) for protected refs. Check ref
targets/exclusions, enforcement state, checks/reviews and bypass actors/modes.
Classic protection and rulesets can coexist; applicable rulesets layer, whereas
only one classic branch-protection rule applies. Disabled/evaluate-only rules
are not enforcing controls. A protected flag or one visible rule is insufficient
to establish the effective profile. See [GitHub protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
and [rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).

The following optional GitHub CLI examples are read-only. Substitute the actual
repository and URL-encoded branch; main is illustrative, not a mandated name.
Use existing authorized access without printing credentials:

```sh
gh api repos/OWNER/REPO --jq '{default_branch,allow_squash_merge,allow_merge_commit,allow_rebase_merge,delete_branch_on_merge}'
gh api repos/OWNER/REPO/branches/main/protection
gh api --paginate 'repos/OWNER/REPO/rulesets?includes_parents=true&per_page=100'
gh api --paginate 'repos/OWNER/REPO/rules/branches/main?per_page=100'
```

<a id="GH-010"></a>
**GH-010 — Evidence and access limits.**

The branch-rules endpoint reports active ruleset rules, including inherited
ones, not the complete classic-protection configuration. Inspect each applicable
ruleset's details through its returned API/UI link, including tag targeting and
bypass; read the classic protection separately. Rule details may conceal bypass
actors from callers without write access. Missing fields, permission/plan errors,
an inaccessible API or an ambiguous 404 mean unverified evidence, not proof of
absence. An empty branch-rules response says nothing about tag protections.
Use the authorized UI or existing owner evidence if available; otherwise state
the gap and whether the concrete risk blocks adoption. Do not change identity,
scopes, plan or settings as a verification workaround. See the [rules API](https://docs.github.com/en/rest/repos/rules)
and [branch-protection API](https://docs.github.com/en/rest/branches/branch-protection).

<a id="GH-011"></a>
**GH-011 — Ordinary path and check compatibility.**

Check that the chosen merge method and linear-history setting are compatible,
that retained branches survive auto-delete, and that required check names,
triggers and reporting identity support ordinary changes. Inspect existing run
evidence rather than manufacturing a destructive push/deletion test. A configured
required check does not prove that meaningful validation ran. See [merge methods](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github)
and [automatic branch deletion](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-the-automatic-deletion-of-branches).

## Verification timing

<a id="GH-012"></a>
**GH-012 — Event-directed verification timing.**

| Occasion | Sufficient work |
| --- | --- |
| New repository onboarding or first topic adoption | Identify working paths and authority; select the proportionate profile; inspect relevant effective settings, plan/identity limits and supported writer/check/review/publication paths once. Reuse current evidence. Any application of settings needs separately admitted authority and readback. |
| Relevant policy/settings/visibility/plan change, writer/check identity or trigger change, suspected drift or a denied supported operation | Recheck the affected rules and paths; resolve mismatches and exceptions through current project authority. A package update alone does not adopt a new profile. |
| Each meaningful code/PR change | Run relevant source/tests and check exact-result authority/assessment at integration. Follow already required checks; requalify changed behavior. Repository-wide settings inspection is unnecessary absent a relevant change or drift signal. |
| Routine reference refresh | Verify changed facts, provenance and proportionate format/link consistency. Use the accepted direct-main path; no recurring settings audit, task machinery or unrelated full suite. |
| Publication | Perform existing release-boundary identity/immutability checks for the selected accepted source/version. Reuse qualified transport tooling; do not rerun onboarding or package-manager integration for every release. |

This creates no mandatory periodic audit, per-session settings query, duplicated
status record or synchronizer. Keep stable path rules/exceptions in accepted
project instructions; mutable configuration observations and decisions belong
in the existing onboarding/task/PR/release records with date and evidence scope.

## Short new/existing-repository checklist

<a id="GH-013"></a>
**GH-013 — Bounded onboarding sequence.**

1. Read current project authority. Identify normal update/publication paths,
   important refs, supported writers and material-change exceptions.
2. Select the profile above against concrete risk and current protections.
   Existing repositories preserve supported paths and stricter accepted rules;
   reconcile shared/local duplicates in their separately reviewed adoption.
3. Inspect effective GitHub settings and feature/identity limits with current
   access. Specify enforcement gaps and the cheapest sufficient alternative.
4. If specifically authorized, the responsible owner/operator applies only the
   selected settings and reads them back; otherwise hand off the recommendation.
5. Walk an ordinary update and applicable publication/exception path using
   available evidence. Keep the concise path/exception and event-recheck rule in
   existing guidance; report unqualified paths without claiming enforcement.

## Practical walkthroughs

- **Manual PR source change:** A library uses an Issue and one task PR, existing
  compilation/tests and independent exact-head assessment. Its owner selects
  squash and disposable-branch deletion, with history protection and a supported
  PR route. No Relay schema or new CI is needed. After a head correction, assess
  affected checks and that head again; repository-settings onboarding is reused.
- **Direct-main evidence refresh:** An owner-authorized reference maintainer
  corrects a dated benchmark measurement, checks its primary source and format,
  then makes a non-force commit to main. History/deletion protection can coexist
  with this path. A new general recommendation instead receives evidence/effect
  assessment and the owner's adoption decision using its accepted review path;
  it does not alter already admitted downstream tasks.
- **Generated distribution:** A qualified publisher takes an accepted source,
  checks the new version is unpublished and advances distribution main plus the
  new tag through its accepted no-overwrite path. Old version tags remain intact.
  Human source merge preferences do not require a PR around generated publication.
  A publication failure is reported and recovered under existing release policy.
- **Hybrid/exception:** Source changes use PRs; routine data or generated output
  has an explicitly accepted direct path. Before a repository-wide PR requirement,
  examine its effect on both. Separate refs or narrowly scoped existing authority
  may suffice; neither a blanket bot bypass nor PRs for all data are automatic
  defaults. A retained integration branch can justify keeping auto-delete off.
  If plan/access prevents an essential protection, record the unmet invariant
  and obtain the owning project's disposition; do not silently weaken it.
