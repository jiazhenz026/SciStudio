---
title: "No-Context Audit — Documentation / Contract Drift"
issue: 1589
branch: audit/2026-06-11-codebase-no-context
author: audit_reviewer agent (AUD-1, no-context) + manager verification
date: 2026-06-11
status: committed
lens: documentation / contract drift
overall_recommendation: pass-with-fixes
---

# No-Context Audit — Documentation / Contract Drift (2026-06-11)

## 1. Scope and method

This is one lens of a three-lens **no-context** repository audit (issue #1589).
The audit agent was dispatched with **no current-task context**: it could read
only ADRs, specs, repository docs, code, and tests — never issues, gate records,
PR descriptions, commit messages, or any manager summary. It independently
compared the repository's declared contracts (ADR/spec `governs:` frontmatter,
documented behavior, public signatures/schemas, generated facts) against the
actual implementation at `main` HEAD `cd370810`.

Method: enumerate `governs:` frontmatter across `docs/adr/**` and `docs/specs/**`;
confirm each governed module/file/contract exists and matches the documented
shape; run the live audit pipeline (`full_audit.run`, `doc_drift`,
`signature_drift`, `closure`) and compare to committed snapshots.

The manager independently re-verified the highest-impact claims against the cited
code (see the **Manager verification** note on each finding).

> Note: the live contract-drift suite (`doc_drift`, `signature_drift`, `closure`
> with the MAINTAINERS rule, `fact_drift`, `frontmatter_lint`) **passes** against
> current HEAD. The findings below are about the *edges* of the audit surface
> (stale snapshots, mislabeled status, phantom governed paths, a guard blind
> spot), not about the validated contracts. Recommendation: **pass-with-fixes**.

## 2. Findings (severity-ordered)

### DRIFT-01 — Stale committed audit snapshot contradicts the live audit (P2)

- **Category:** doc_drift · **Confidence:** high
- **Locations:** `docs/audit/latest/facts-summary.json:1-30`,
  `src/scistudio/qa/audit/facts.py:41`, `src/scistudio/qa/audit/full_audit.py:147`
- **Evidence:** The committed `latest` snapshot records `"status": "fail"`,
  `"source_sha": "ec08b610…"`, `"generated_at": "1970-01-01T00:00:00Z"`, with
  child reports `doc_drift fail findings=30` and `closure fail findings=1373`.
  Running the real pipeline against HEAD produces the opposite:
  `_source_tree_sha(root,'scistudio')` = `ccb9bdeb…` (≠ committed `ec08b610`),
  and `full_audit.run(root)` returns **status=pass** with `doc_drift findings=0`,
  `closure findings=0` (21 symbols covered via the MAINTAINERS rule),
  `signature_drift findings=0`. The artifact was last modified in a
  SciEasy→SciStudio rename commit (`74c6843c`), not by a fresh audit run.
- **Impact:** Anyone reading `docs/audit/latest/` as the canonical snapshot is
  told the repo is FAILING with ~1400 findings while HEAD actually passes
  cleanly. Violates "generated docs must stay generated" (AGENTS.md §3.4); can
  trigger phantom remediation, mask a real future regression, and erode trust in
  the audit surface. The file is 723 KB and git-tracked.
- **Recommendation:** Regenerate the snapshot from HEAD (so `source_sha` and
  child statuses match reality), or stop tracking it and treat it as a build
  artifact; if it is meant as a point-in-time record, date it like the other
  `docs/audit/*` snapshots instead of calling it `latest`.

### DRIFT-02 — Three shipped specs still labeled `status: Planned` (P3)

- **Category:** doc_drift · **Confidence:** high
- **Locations:** `docs/specs/adr-045-workflow-state-version.md:4`,
  `docs/specs/adr-042-gate-ledger-runtime.md:4`,
  `docs/specs/adr-042-test-engineer-persona.md:4`
- **Evidence:** `adr-045-workflow-state-version` is `Planned`, yet every governed
  path/test exists on main (`workflow_watcher.py`, `test_workflow_version_vector`,
  `test_file_version_vector`, `useWebSocket.versionVector.test.ts`) and the
  feature landed in merged `feat(#1401)` commits. `adr-042-gate-ledger-runtime`
  is `Planned` but the gate_record package already contains `ledger.py`
  (`schema_version=2` with `check_events`/`reconcile_events`), `checks.py`
  (`CHECK_CATALOG` + `select_checks(...tier)`), `evaluator.py`, `io.py`,
  `surfaces.py`. `adr-042-test-engineer-persona` is `Planned` but the persona doc
  exists and AGENTS.md lists `test_engineer` as supported.
- **Impact:** Specs labeled Planned for shipped behavior misrepresent project
  state. `doc_drift._active_governance` treats Planned and Implemented alike, so
  the existence checks still run and the mislabel is **not** auto-caught; it
  persists silently. A reader trusting `status` cannot tell which designs are
  real.
- **Recommendation:** Advance these specs to `status: Implemented`; sweep the
  other `Planned/Draft` adr-042/adr-04x specs for the same drift in one focused
  docs PR.

### DRIFT-03 — ADR-044 spec governs a phantom file and a non-existent contract (P3)

- **Category:** doc_drift · **Confidence:** high
- **Locations:** `docs/specs/adr-044-subworkflow-block.md:55,45,396`,
  `src/scistudio/api/runtime/` (package, not `runtime.py`),
  `src/scistudio/workflow/definition.py:37`, `src/scistudio/qa/audit/doc_drift.py:32`
- **Evidence:** The spec governs `src/scistudio/api/runtime.py` and a contract
  `WorkflowDefinition.flatten_subworkflows` plus a test
  `tests/workflow/test_flatten_subworkflows.py`. But `api/runtime.py` no longer
  exists (the god-file refactor #1430 decomposed it into the `api/runtime/`
  package; `_runs.py` holds `start_workflow`); `grep -rn flatten_subworkflows
  src/` returns nothing; `WorkflowDefinition` has no such method; the test file
  is absent. `doc_drift` skips all of this because the spec is `status: Draft`
  and `_active_governance` returns False for non-Planned/Implemented specs.
- **Impact:** A maintainer following the spec to locate code is misdirected to a
  deleted monolith, and the audit cannot catch it (Draft specs are inactive), so
  the phantom references can rot indefinitely. (ADR-044 itself is honest — it
  discloses the runtime change as not-yet-landed, and ARCHITECTURE.md §5.4.7
  correctly marks the flatten approach as Planned.)
- **Recommendation:** Update `governs.files` to `src/scistudio/api/runtime/**`
  (post-refactor package) or remove the `runtime.py` reference until the runtime
  change is scoped; ensure `flatten_subworkflows` + its test exist (or the
  `governs` entries are corrected) before the spec is promoted out of Draft.

### DRIFT-04 — `doc_drift` never existence-checks `governs.entry_points` (P3)

- **Category:** doc_drift · **Confidence:** high
- **Locations:** `src/scistudio/qa/audit/doc_drift.py:206-248`,
  `docs/adr/ADR-048.md:27-28`, `docs/specs/adr-048-preview-system.md:38-39`
- **Evidence:** `classify_repo` iterates only `governs.modules` (line 211),
  `governs.contracts` (224), and `governs.files` (237); there is no loop over
  `governs.entry_points`. The `entry_points` surface is used only inside
  `_check_adr_spec_alignment` for ADR↔spec cross-coverage, never against real
  symbols. ADR-048 and adr-048-preview-system declare
  `entry_points: scistudio.previewers`; `src/scistudio/previewers` does not exist
  and no such entry point is registered in any `pyproject.toml`, yet
  `full_audit.run` reports `doc_drift` **pass**.
- **Impact:** A declared entry-point surface can name a group that ships nothing
  and the drift detector stays green. Currently benign for ADR-048 (Proposed,
  previewers are intentional future work), but the same blind spot would hide a
  real broken entry point for an Accepted/Implemented doc. A latent gap in the
  drift guard itself.
- **Recommendation:** Extend `classify_repo` with an `entry_points` existence
  check for active documents (mirror the module check), or document explicitly
  why entry points are intentionally not existence-validated.

## 3. Manager verification

- DRIFT-03 phantom path **confirmed**: `src/scistudio/api/runtime.py` is absent;
  `src/scistudio/api/runtime/` is a package; `grep -rn flatten_subworkflows src/`
  returns nothing.
- DRIFT-04 phantom entry point **confirmed**: `src/scistudio/previewers` does not
  exist.
- DRIFT-01/02 are high-confidence with reproducible verification steps recorded
  by the agent (live `full_audit.run`, source-SHA comparison, `git log` of the
  snapshot). Not independently re-run by the manager but accepted as high.

## 4. Recommendation

**pass-with-fixes.** No documented runtime guarantee is broken. Regenerate or
de-track the stale `latest` snapshot (DRIFT-01, P2), and fold the three status
corrections + the two phantom-path/guard items into a focused docs reconciliation
(DRIFT-02/03/04, P3). See the consolidated index for the follow-up issue plan.
