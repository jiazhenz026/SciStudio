---
title: "Phase 1H Sub-PR 1 implementation record — Workflow v2 + per-stage validators"
phase: 1
sub_phase: "1H"
sub_pr: 1
tcs:
  - "1H.1"
  - "1H.2"
issue: 1145
parent_issue: 1139
umbrella: 1113
branch: feat/issue-1145/1h-workflow-v2-shadow
session: 20260518-062116-adr-042-043-044-phase-1h-sub-pr-1-workfl
adrs:
  - ADR-042
date: 2026-05-18
agent_editable: true
---

# Phase 1H Sub-PR 1 implementation record

## Scope

Ships TC-1H.1 and TC-1H.2 from the ADR-042/043/044 Phase 1H slice.

- **TC-1H.1**: `.workflow/schema-v2.yaml` + `gate.py v2` shadow-mode support.
- **TC-1H.2**: `src/scieasy/qa/workflow/validators/` package (one module
  per ADR-042 §19.2 stage + `_registry`).

## Files modified

| File | Action | LOC | Purpose |
|------|--------|-----|---------|
| `.workflow/schema-v2.yaml` | NEW | 186 | 7-stage v2 schema per ADR-042 §19.2 |
| `.workflow/gate.py` | EDIT (additive) | +143 | `--schema-version` flag + shadow loader + JSONL logger |
| `src/scieasy/qa/workflow/validators/__init__.py` | NEW | 22 | Package marker |
| `src/scieasy/qa/workflow/validators/_registry.py` | NEW | 65 | ID → callable map |
| `src/scieasy/qa/workflow/validators/start_and_route.py` | NEW | 78 | Stage 1 shape check |
| `src/scieasy/qa/workflow/validators/create_issue.py` | NEW | 60 | Stage 2 shape check |
| `src/scieasy/qa/workflow/validators/change_plan.py` | NEW | 62 | Stage 3 shape check |
| `src/scieasy/qa/workflow/validators/branch.py` | NEW | 56 | Stage 4 branch-name pattern |
| `src/scieasy/qa/workflow/validators/implement_validate.py` | NEW | 36 | Stage 5 placeholder (skip) |
| `src/scieasy/qa/workflow/validators/complete_artifacts.py` | NEW | 35 | Stage 6 placeholder (skip) |
| `src/scieasy/qa/workflow/validators/submit_reconcile.py` | NEW | 60 | Stage 7 shape check |
| `tests/qa/test_workflow_v2_validators.py` | NEW | 290 | 37 per-validator tests |
| `tests/qa/test_workflow_v2_registry.py` | NEW | 130 | 13 registry round-trip tests |
| `tests/qa/test_workflow_v2_shadow.py` | NEW | 320 | 17 in-process + subprocess integration tests |

## Implementation rationale

1. **Shadow mode is purely additive.** The defining ADR-042 §19 Phase 1
   invariant: v1 default behaviour is byte-identical before/after this PR.
   The `--schema-version` flag defaults to `v1`; when omitted, no v2 code
   path runs. Verified by
   `TestV1BehaviourUnchanged::test_v1_advance_writes_no_shadow_log`.

2. **Validators are explicit, not auto-discovered.** Per ADR-042 §28.1
   ("no hidden behaviour") the registry is a hand-maintained dict in
   `_registry.py`. No entry-point discovery, no metaclass magic.

3. **Placeholders return `skip`, not `pass`.** Stages 5 and 6 depend on
   audit tools (`full_audit`, `complete_artifacts.check`) that don't
   exist yet (they ship in TC-1B.7). Returning `skip` (vs `pass`) makes
   the gap auditable: telemetry can later show how many runs hit the
   skip path, motivating the 1B.7 dependency.

4. **Shadow runner swallows ALL v2 exceptions.** Any v2 failure
   (import error, validator crash, malformed YAML) is logged to the
   shadow JSONL but NEVER raised to the caller. This protects v1 from
   any v2 development bug.

## Deviations from investigation spec

None substantive. The validator code follows ADR-042 §19.5 verbatim
(reusing the 1A `Validator` Protocol + `StageContext` shapes).

One minor enrichment: the v1→v2 stage map handles BOTH `update_docs`
and `update_changelog` v1 stages by routing them to v2
`complete_artifacts` (which subsumes both per ADR-042 §19.6 mapping
table). This is implied by §19.6 but not literally typed there;
encoded as a comment in `run_v2_validators_shadow`.

## Tests added

- 37 per-validator unit tests (`test_workflow_v2_validators.py`).
- 13 registry round-trip tests (`test_workflow_v2_registry.py`).
- 17 shadow-mode integration tests (`test_workflow_v2_shadow.py`),
  including 3 subprocess invocations of `gate.py` for end-to-end
  verification.

**Coverage**: 100% line coverage on `scieasy.qa.workflow.gate` (1A
foundation re-exercised) and all 8 new validator modules
(`scieasy.qa.workflow.validators/*`). Well above the ADR-042 §21.6
≥95% bar.

## Known TODOs left in code

Each marker follows CLAUDE.md §7.6:

- `start_and_route.py`: real MAINTAINERS / ADR resolution
  (`# TODO(#1145): … depends on TC-1B.4 closure + TC-1C.2 MAINTAINERS`).
- `create_issue.py`: strict v2 issue-template check (§19.2 follow-up).
- `change_plan.py`: per-file ADR governs.files coverage (depends on
  TC-1B.4 closure).
- `branch.py`: "branched from latest origin/main" git-state check
  (depends on TC-1B.7).
- `implement_validate.py`: subprocess `full_audit --pre-push` (depends
  on TC-1B.7).
- `complete_artifacts.py`: subprocess `complete_artifacts --check`
  (depends on TC-1B.7).
- `submit_reconcile.py`: CI-green + Codex-reconcile checks (depends on
  TC-1H.6 pr-maintainer skill).

## Local verification

- `pytest tests/qa/test_workflow_v2_validators.py
  tests/qa/test_workflow_v2_registry.py tests/qa/test_workflow_v2_shadow.py
  --timeout=60` → 70/70 pass.
- `pytest tests/qa/test_schemas_workflow_gate.py --timeout=60` → 23/23
  pass (1A foundation regression check).
- `ruff check src/scieasy/qa/workflow/validators/ .workflow/gate.py
  tests/qa/test_workflow_v2*.py` → clean.
- `ruff format --check` → clean (applied).
- `python scripts/audit/temp_review.py src/scieasy/qa/workflow/validators
  .workflow/schema-v2.yaml` → 0 findings.

## Out of scope for this Sub-PR (handled in Sub-PRs 2 and 3)

Sub-PR 2 (TCs 1H.3 + 1H.4) ships AGENTS.md hierarchy + symlinks.
Sub-PR 3 (TCs 1H.5–1H.8) ships 11 skills + committer.py + fact
extractors.

## Branch + PR

- Branch: `feat/issue-1145/1h-workflow-v2-shadow`.
- Branched from: `track/adr-042/1a-schemas` (1A schemas required as
  foundation; 1H tracking branch is being updated to include 1A in a
  separate sweep).
- PR target: `track/adr-042/1h-workflow-v2` (per dispatch prompt).
