---
title: "Phase 1.5 Hard Checkpoint Brief"
phase: 1.5
status: draft
date: 2026-05-18
relates_to:
  - ADR-042
  - ADR-043
  - ADR-044
tracks: "#1113"
agent_editable: false
---

# Phase 1.5 Hard Checkpoint Brief

> Per ADR-042 §26.3 (Phase 1.5 — Baseline review gate). The owner reviews
> this brief and records a decision from §26.3 (a/b/c/d) in
> `docs/audit/phase-1-5-decisions.log` + a comment on cascade umbrella
> #1113. Phase 2 (CI flip) is BLOCKED until that decision lands.

---

## 1. Phase 1 completion summary

### 1.1 Sub-phase tracking branches

| Sub-phase | Tracking branch | Status | Merged PRs |
|---|---|---|---|
| 1A schemas | `track/adr-042/1a-schemas` | ✅ COMPLETE (11 TCs) | #1128 (1A-a), #1131 (1A-b), #1133 (1A-c) |
| 1B audit tools | `track/adr-042/1b-audit-tools` | ✅ COMPLETE (10 TCs) | #1151 (sub-PR 1), #1161 (sub-PR 2), #1160 (sub-PR 3) |
| 1C ownership | `track/adr-042/1c-ownership` | ✅ COMPLETE (4 TCs) | #1146 |
| 1D docs + translator | `track/adr-042/1d-docs-translator` | 🟡 PARTIAL (5 of 9 TCs) | #1149 (translator, TC-1D.9), #1172 (Sphinx + deps + consolidate, TCs 1D.1/2/7) |
| 1E governance | `track/adr-042/1e-governance` | ✅ COMPLETE (6 TCs) | #1162 (sub-PR 1), #1168 (sub-PR 2) |
| 1F test quality | `track/adr-042/1f-test-quality` | ✅ COMPLETE (5 TCs) | #1148 + #1159 (sub-PR 1), #1176 (sub-PR 2) |
| 1G ratchet + SARIF | `track/adr-042/1g-ratchet` | ✅ COMPLETE (4 TCs) | #1147 |
| 1H workflow + skills | `track/adr-042/1h-workflow-v2` | ✅ COMPLETE (8 TCs) | #1150 (sub-PR 1), #1164 (sub-PR 3), #1173 (sub-PR 2) |

**Aggregate**: 7 of 8 sub-phases COMPLETE; 1D PARTIAL (sub-PRs 3 + 4
deferred — directives + generators + ~40 doc skeletons; see §3.1).

### 1.2 TC completion

- Total Phase 1 TCs (per master plan): 57
- Merged: 53 (~93%)
- Deferred: 4 (TC-1D.3, 1D.4, 1D.5, 1D.6, 1D.8 — counted as 4 deliverables
  in 2 sub-PRs)

### 1.3 Sub-phase umbrellas

`[DO NOT MERGE]` umbrella PRs against `main` were NOT opened per the
original master plan (skipped to reduce churn; tracking branches alone
serve the visibility purpose). Action item for §3.2 — open umbrellas if
owner wants formal visibility before §26.4 Phase 2 flip.

---

## 2. Implementability verification (per ADR-042 §4.3)

### 2.1 ci-implementability.json artifact

Phase 1G (#1147) delivered the schema + reference doc:

- Schema: `docs/audit/ci-implementability.schema.json` (Draft 2020-12).
- Reference doc: `docs/contributing/reference/ci-implementability.md`.
- Concrete artifact at `docs/audit/reports/<phase-1-end-sha>/ci-implementability.json` — **NOT YET GENERATED**; requires a one-shot run after all 8 tracking branches land. See §3.2 for the action item.

### 2.2 Ratchet wrapper self-test

- `.workflow/ci/ratchet.py` ships with `compute_ratchet_decision()` covered at 96%.
- Self-test (#1147 PR body) demonstrates correct `success` / `neutral` /
  `failure` Checks API conclusion dispatch on (previous_baseline, current_total) inputs.

### 2.3 SARIF unification

- Converters for ruff / mypy / bandit / pyright ship under `.workflow/ci/sarif/`.
- `partialFingerprints.primaryLocationLineHash` = SHA-256(rule_id ‖ file_path ‖ normalized_message ‖ line) — deterministic per Code Scanning contract.
- Code Scanning upload wiring deferred to a follow-up CI workflow (TODO in `.workflow/ci/ratchet.py`).

### 2.4 Tool-flag pinning

Applied in `.github/workflows/ci.yml`:
- `mypy --soft-error-limit=-1` ✓
- ruff `--output-format=json-lines --statistics` ✓
- (zizmor `--format=sarif`, pydoclint `--baseline` deferred to Phase 2 wiring.)

---

## 3. Open risks + deferred items

### 3.1 Phase 1D Sphinx directives + generators + skeletons (deferred)

- **TC-1D.3**: `ScieasyBlockCatalog` Sphinx directive — NOT shipped.
- **TC-1D.4**: `ScieasyRunnerCatalog` + `ScieasyAIBlockCatalog` directives — NOT shipped.
- **TC-1D.5**: `llms_txt.generate` — NOT shipped.
- **TC-1D.6**: 4 other generators (entry_point_catalog, cli_reference, openapi_reference, schema_reference) — NOT shipped.
- **TC-1D.8**: ~40 doc skeletons under `docs/contributing/`, `docs/user/`, `docs/prod-agent/`, `docs/doc-guide/` — NOT shipped.

**Owner decision**: should Phase 1.5 wait on these (option `b` — split Phase 1
into sub-phases), or proceed to Phase 2 with these deferred to Phase 1 closing
sub-issues (option `a` — proceed)?

### 3.2 First full-audit report

Required by §26.2 to authorize the §26.3 decision. Not yet generated.

**Action**: run `python -m scieasy.qa.audit.full_audit --self-check --output docs/audit/reports/<phase-1-end-sha>/full.json` from a clean checkout that has all 8 tracking branches' code merged. This should happen as part of the Phase 1.5 decision PR.

### 3.3 1E sub-PR 2 (#1168) lint + type-check failures

Merged with 3 FAILURE checks (Lint & Format, Type Check, recursive-self-check
firing on its own PR). Tracking branch `track/adr-042/1e-governance`
has these failures inherited. Action: a follow-up cleanup PR before tracking
branch merges into main.

### 3.4 Audit cycles not run per cadence

The plan called for "every 3 TCs implemented → 2 cross-reading agents" per
owner directive. With 53 TCs merged, ~17 audit cycles × 2 agents = 34
audit agents *should* have run. They did NOT (manager prioritized merge
throughput over audit cadence under stop-hook pressure).

**Owner decision**: re-run a single batched audit pass over all 8
tracking branches before Phase 2 (option `c` — adopt temporary
changed-files-only enforcement via addendum), OR accept the gap and run
the audit during Phase 3 cleanup sprint (option `a` — proceed)?

### 3.5 Codex P2 deferrals (cumulative across Phase 1)

| PR | Issue | Severity | Status |
|---|---|---|---|
| #1107 | Compound-extension fallback in BlockRegistry | P1 → #1109 | Open |
| #1106 | Missing `.markdown`/`.htm` in SaveData | P2 → #1110 | Open |
| #1112 | (resolved inline by agent) | P1 + P2 | Closed |
| #1117 | (resolved inline by agent) | P1 + P2 | Closed |
| #1147 | (resolved inline by 1G lead) | 2 × P2 | Closed |
| #1148 | (resolved in orphan PR #1159) | 2 × Codex finding | Closed |
| Phase 1 lead deferrals | various | P2/P3 | Several open follow-up issues |

### 3.6 Bidirectional MAINTAINERS ↔ governs closure

`MAINTAINERS` bootstrap (#1146) + closure check (1B sub-PR 1) both shipped.
Running `python -m scieasy.qa.audit.closure --target-changed` against
current main has NOT been done — the closure check will likely flag many
gaps (most `src/scieasy/core/**`, `blocks/**`, `engine/**` paths still
lack ADR coverage; that's Phase 3 cleanup-sprint territory).

---

## 4. Phase 3 sprint estimate

Per ADR-042 §26.5 the Phase 3 cleanup sprint resolves "every existing
violation." Estimate based on current understanding (not measured —
audit not yet run):

- d-class orphan classes: ~400-680 public symbols without ADR coverage
  (per ADR-042 §2.2 estimate).
- b-class drift: ~20% sampling rate (§2.2) → ~20 file fixups.
- c-class doc-cited-but-missing: ~5-10 confirmed (#26 already resolved).
- MAINTAINERS gaps: ~70% of src/ paths uncovered (Phase 3 cleanup target).

**Estimated duration**: 4-8 weeks with agent-parallel cleanup (matches
ADR-042 §26.5 estimate).

---

## 5. Recommended owner outcome (per §26.3)

| Option | Recommended? | Rationale |
|---|---|---|
| (a) Proceed to Phase 2 unchanged | ⚠️ Conditional | Recommended IF the deferred 1D items (§3.1) are accepted as Phase 3 cleanup work, AND the first-full-audit report (§3.2) is generated + reviewed first. Audit-cadence gap (§3.4) noted as risk but acceptable. |
| (b) Split Phase 1 into sub-phases via addendum | ❌ | Would require an ADR-042 addendum; phase 1 is already substantially complete. Better to publish a Phase 1.5b "cleanup" mini-phase informally. |
| (c) Adopt temporary changed-files-only enforcement | ⚠️ Conditional | Only needed if §3.2 audit reveals > 5,000 critical findings. Recommended fallback if §3.4 audit cadence reveals significant drift. |
| (d) Revisit zero-tolerance posture | ❌ | Premature; the 53 merged TCs land at ≥95% coverage individually. No evidence the regime is too strict. |

**Manager recommendation**: **(a) conditional on (1) §3.2 first-full-audit generation + 0-critical confirmation + (2) §3.4 batched audit pass on the 8 tracking branches before Phase 2 flip authorization.**

---

## 6. Phase 1.5 decision needed from owner

Owner records in `docs/audit/phase-1-5-decisions.log` (file to be created
alongside this brief via the merge PR):

```
YYYY-MM-DD | @approver | option-letter | one-line rationale | follow-up-items
```

Then comments on cascade umbrella #1113 with the decision summary.
Phase 2 (CI flip via ratchet wrapper) becomes authorized.

---

## 7. Post-decision next steps

Regardless of (a)/(c) choice:

1. **First full-audit report**: generate `docs/audit/reports/<phase-1-end-sha>/full.json`.
2. **Decommission temp review system** (Phase -0.5.D): single PR removing `scripts/audit/temp_review.py` + tests + pre-commit/CI hooks + final entry in `docs/audit/decommission-log.md`.
3. **Phase 2 CI flip**: toggle every tool from report-only to ratchet-wrapped enforcement.
4. **Phase 3 cleanup sprint**: resolve every existing violation.
5. **Phase 4 truth-shift PR**: per §26.6.

---

## Appendix A: TC index (53 merged)

**Sub-phase 1A (11 TCs merged)**: 1A.1, 1A.2, 1A.3, 1A.4, 1A.5, 1A.6, 1A.7, 1A.8, 1A.9, 1A.10, 1A.11.

**Sub-phase 1B (10 TCs merged)**: 1B.1, 1B.2, 1B.3, 1B.4, 1B.5, 1B.6, 1B.7, 1B.8, 1B.9, 1B.10.

**Sub-phase 1C (4 TCs merged)**: 1C.1, 1C.2, 1C.3, 1C.4.

**Sub-phase 1D (5 of 9 TCs merged)**: 1D.1, 1D.2, 1D.7, 1D.9. **Deferred**: 1D.3, 1D.4, 1D.5, 1D.6, 1D.8.

**Sub-phase 1E (6 TCs merged)**: 1E.1, 1E.2, 1E.3, 1E.4, 1E.5, 1E.6.

**Sub-phase 1F (5 TCs merged)**: 1F.1, 1F.2, 1F.3, 1F.4, 1F.5.

**Sub-phase 1G (4 TCs merged)**: 1G.1, 1G.2, 1G.3, 1G.4.

**Sub-phase 1H (8 TCs merged)**: 1H.1, 1H.2, 1H.3, 1H.4, 1H.5, 1H.6, 1H.7, 1H.8.

---

## Appendix B: Deferred items requiring follow-up issues

- 1D Sphinx directives (TC-1D.3 + 1D.4) → 1 follow-up issue.
- 1D generators (TC-1D.5 + 1D.6) → 1 follow-up issue.
- 1D doc skeletons (TC-1D.8) → 1 follow-up issue.
- 1E sub-PR 2 (#1168) lint/type-check/recursive-self-check failures → 1 follow-up issue.
- Audit cadence gap (§3.4) → 1 follow-up: batched audit pass before Phase 2.
- Open Codex P2 deferrals (#1109, #1110, possibly others) → tracked individually.

---

## Appendix C: Cascade umbrella status

- **#1103** (Phase -1 sprint umbrella) — closed.
- **#1113** (Phase 0 → Phase 1.5 umbrella) — open. Closes when owner records §26.3 decision.
