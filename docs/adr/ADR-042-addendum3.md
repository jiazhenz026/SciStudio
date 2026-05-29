---
adr: 42
addendum: 3
title: "Sentrux Downgraded To Advisory Gate"
status: Accepted
date_created: 2026-05-21
date_accepted: 2026-05-21
date_superseded: null

supersedes: []
superseded_by: null
related: [42]
closes_issues: [1408]
tracking_issue: 1408

is_code_implementation: true
governs:
  modules:
    - scistudio.qa.governance.gate_record
    - scistudio.qa.governance.gate_record.guards.sentrux_gate
  contracts:
    # ``gate_record`` is a sub-package as of #1433 (umbrella #1427) and was
    # restructured by ADR-042 Addendum 6: the standalone ``validation`` module
    # collapsed into the shared ``evaluator.reconcile`` entry point and the
    # ``sentrux_gate`` guard moved under ``gate_record.guards``. Contract paths
    # below point to the canonical definition sites in that layout so
    # doc_drift / closure can resolve them against generated facts.
    - scistudio.qa.governance.gate_record.evaluator.reconcile
    - scistudio.qa.governance.gate_record.guards.sentrux_gate.check
  entry_points: []
  files:
    - docs/adr/ADR-042-addendum3.md
    - .github/workflows/workflow-gate.yml
    - src/scistudio/qa/governance/gate_record
  excludes: []

tests:
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_record_ci.py

agent_editable: false
assisted_by:
  - "Claude:opus-4-7"

phase: implementation
tags: [qa, ci, ai-governance, workflow-gate, sentrux]
owner: "@jiazhenz026"
co_authors: []
language_source: en
translations: []
---

# ADR-042 Addendum 3: Sentrux Downgraded To Advisory Gate

## 1. Decision Summary

This addendum downgrades Sentrux free-tier evidence from a hard gate
requirement to an advisory signal. It narrowly supersedes ADR-042
Addendum 1 §D1 (Sentrux free-tier architecture evidence) and §D5
(free-tier honesty rule) only with respect to their **blocking
semantics**; all other Addendum 1 decisions (D2 committed gate records,
D3 six-stage gate, D7 implementation tests, D8 legacy gate removal,
D9 generated artifacts, D10 AI gate CLI, D11/D12 architecture
frontmatter/drift) are unaffected.

> **Note (ADR-042 Addendum 6):** The implementation symbols this addendum
> governs were restructured by Addendum 6. The `validate_gate_record`
> validator collapsed into the shared `evaluator.reconcile` entry point and
> the `sentrux_gate` guard moved under `gate_record.guards`; its advisory
> behavior is now expressed by `gate_record.guards.sentrux_gate.check`. The
> `governs` block has been repointed accordingly.

| Decision | Change | Enforcement target | Detailed section |
|---|---|---|---|
| D1. Drop sentrux missing-evidence as a hard gate | `validate_gate_record` no longer fails on missing/skipped/unknown sentrux evidence | Local pre-push / pr-ready / ci CLI | Section 3 |
| D2. Keep sentrux recorded-failure as a hard gate (local only) | `validate_gate_record` still fails when sentrux evidence is explicitly `status="fail"` — the developer ran sentrux, saw a failure, and is pushing anyway | Local pre-push / pr-ready / ci CLI | Section 3 |
| D3. CI sentrux step becomes advisory annotations | `workflow-gate.yml` calls `verify_free_tier_claims` and converts findings to `::warning::` annotations; does not contribute to the blocking reports list | GitHub Actions workflow-gate CI step | Section 4 |
| D4. Override mechanism is unchanged | `admin-approved:ai-override` continues to bypass the recorded-fail local block when warranted | Existing ADR-042 override-label workflow | Section 5 |

### 1.1 Problems Addressed

| Problem | Risk | Decision | Detailed section |
|---|---|---|---|
| Sentrux binary is not installable in many contributor and AI-agent execution environments. The official distribution is a Rust source tree under the Claude marketplace; no prebuilt binary is shipped for the typical agent host. | Every PR that touches source / workflow / architecture / governance / sentrux rule files fails the local pre-push hook with `gate-record.sentrux.missing` until the author adds an `admin-approved:ai-override` label. The override is a documented escape but it shifts diagnostic work onto every reviewer for every such PR. Working example: PR #1406, which had to ship with the override label purely for tooling reasons. | Drop the missing-evidence requirement entirely. Sentrux evidence is now opt-in. | Section 3 |
| CI sentrux step blocks merge on findings that are often advisory at merge time (architectural debt is information, not necessarily a release blocker). | Reviewers cannot weigh "this PR regressed structure" against "this is pre-existing debt the team has scoped to fix later" without a hard escape label. | Convert CI sentrux step to surface findings as `::warning::` annotations only; never contribute to the blocking decision. Reviewers read the warnings and decide. | Section 4 |
| Recorded-failure evidence is a different signal from missing/skipped/unknown evidence. A developer who ran sentrux, observed a real failure, and chose to push anyway is the case the gate was actually designed to catch. | Removing all sentrux enforcement would also remove that targeted signal. | Keep recorded-failure as a local block; let the override label handle justified exceptions. | Section 3 |
| Other Addendum 1 decisions are independent of sentrux's blocking semantics. | Conflating "sentrux is advisory" with "the rest of Addendum 1 is up for revision" creates uncertainty about gate workflow, architecture frontmatter, and override-label semantics. | Limit the supersession to §D1 (missing-evidence) and §D5 (blocking honesty rule); explicitly call out which decisions are NOT changed. | Section 6 |

## 2. Scope

The supersession is narrow:

- **In scope (changed):** Sentrux evidence becomes opt-in at the gate.
  CI never blocks on sentrux. Missing, skipped, or unknown sentrux
  evidence is allowed. Recorded `status="fail"` still blocks locally.
- **Out of scope (unchanged):** Committed gate records (Addendum 1 §D2),
  six-stage gate (§D3), implementation tests requirement (§D7), legacy
  gate removal (§D8), generated artifacts handling (§D9), AI gate CLI
  (§D10), architecture frontmatter audit (§D11), architecture
  truthfulness audit (§D12), override-label workflow (§D6 reused as is),
  `.sentrux/rules.toml` as the executable architecture-rule source
  (Addendum 1 §2 retained as advisory documentation).

The Sentrux tool, the `SentruxEvidence` data model, the
`gate_record sentrux` CLI subcommand, and the `verify_free_tier_claims`
function all continue to exist. They are simply not blocking by default.

## 3. Gate Record Validation Change

`scistudio.qa.governance.gate_record.validate_gate_record` previously
emitted two findings:

| Finding | When | Severity |
|---|---|---|
| `gate-record.sentrux.missing` | Sentrux applies and evidence is None | Blocking |
| `gate-record.sentrux.not-passing` | Sentrux evidence is recorded and status != "pass" | Blocking |

After this addendum:

| Finding | When | Severity |
|---|---|---|
| `gate-record.sentrux.not-passing` | Sentrux applies and evidence is recorded with `status == "fail"` | Blocking |

Concretely:

- Evidence absent (`sentrux is None`): no finding.
- Evidence recorded with `status="pass"`: no finding.
- Evidence recorded with `status="skipped"` or `status="unknown"`: no finding.
- Evidence recorded with `status="fail"`: blocking finding.

The override-label workflow (`admin-approved:ai-override` and the
human-authored bypass set established in Addendum 1) continues to skip
all gate-record validation findings including this one.

## 4. CI Workflow Change

`.github/workflows/workflow-gate.yml` previously included
`sentrux_gate.verify_free_tier_claims(...)` in the `reports` list whose
contents drive the workflow-gate job's pass/fail decision. Any sentrux
finding caused the job to fail.

After this addendum, the workflow:

1. Still calls `verify_free_tier_claims(record.get("sentrux"), changed_files=changed, ...)`.
2. Iterates over the returned findings and prints each as a GitHub
   Actions `::warning::` annotation (`::warning title=Sentrux
   advisory::<rule_id>: <message>`).
3. Does NOT add the sentrux report to the `reports` list.
4. Emits a notice line clarifying that sentrux findings are advisory
   per this addendum.

The workflow-gate job therefore never fails on sentrux alone. All other
checks (`issue_link`, `docs_landing`, `core_change_guard`,
`mod_guard`, `pr_merge_guard`, `weakened_ci_check`, etc.) continue to
block as before.

## 5. Override Mechanism

The `admin-approved:ai-override` label continues to work as defined in
Addendum 1 §D6. It now applies primarily to the rare case where a
developer ran sentrux, recorded `status="fail"`, and has a written
rationale for proceeding (e.g. the failure is pre-existing debt
tracked elsewhere). The label remains optional — most PRs no longer
need it because the gate no longer fails on missing evidence.

The `--bypass-label` flag on the gate-record CLI and the
`SCISTUDIO_GATE_BYPASS_LABELS` environment variable retain their
behavior. Their primary purpose now is the recorded-fail case rather
than the missing-evidence case.

## 6. Decisions Explicitly Retained From Addendum 1

To prevent scope creep this addendum reaffirms the following Addendum 1
decisions as fully in force:

- §D2 Committed gate records as CI evidence.
- §D3 Six-stage gate (Scope+Issue → Plan → Implement → Update Docs →
  Test+Checks → Commit+Submit PR).
- §D4 QA full audit evidence requirement.
- §D6 Override-label set (`human-authored`, `admin-approved:ai-override`,
  `admin-approved:core-change`, `admin-approved:merge`).
- §D7 Implementation tests required for implementation-category tasks.
- §D8 Legacy gate removal (`.workflow/gate.py` deleted, single CI
  gate authority).
- §D9 Generated artifact handling.
- §D10 AI gate CLI requirement.
- §D11 Architecture frontmatter audit.
- §D12 Architecture truthfulness / drift audit.

Architecture drift, frontmatter lint, and other ADR-042 full-audit
children are independent of sentrux and continue to block CI as before.

## 7. Verification

This addendum is verified by:

- `tests/qa/test_gate_record_ci.py` — invert
  `test_sentrux_required_for_applicable_changes` so it asserts that
  missing evidence is now allowed; add new assertion that recorded
  `status="fail"` still produces `gate-record.sentrux.not-passing`.
- `tests/qa/test_gate_record.py` — keep the existing
  `test_sentrux_evidence_rejects_*` tests since the `SentruxEvidence`
  validation model is unchanged. Add a new test that confirms
  recorded `status="skipped"` no longer triggers
  `gate-record.sentrux.missing` for applicable changes.
- Manual: CI run on a PR with no sentrux evidence and source-touching
  diff completes without blocking on sentrux; the workflow-gate job
  output contains sentrux advisory `::warning::` annotations where
  applicable.

## 8. Out Of Scope

This addendum does not:

- Remove `sentrux_gate.py`, `SentruxEvidence`, or the `gate_record sentrux` CLI subcommand.
- Change `.sentrux/rules.toml` semantics or the `sentrux check` CLI.
- Modify any other Addendum 1 decision.
- Introduce a new advisory tool to replace sentrux's role. The
  semantic-duplication scan introduced by Addendum 2 is a separate gate.
- Auto-promote sentrux warnings back to errors based on label or
  repository state. If a future hardening path is desired, it is a
  future addendum.
