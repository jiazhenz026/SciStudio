---
title: "Phase 1 Investigation Summary — Open Ambiguities + Dispatch-Mode Note"
phase: 1
status: investigation-complete
date: 2026-05-18
relates_to:
  - ADR-042
  - ADR-043
  - ADR-044
tracks: "#1113"
agent_editable: true
---

# Phase 1 Investigation Summary

> 6 INV agents (INV-1 through INV-6) covered the 21 Phase 1A + 1B toolchains.
> The full per-TC analyses live in the dispatch-transcript record (manager
> conversation, 2026-05-18). This summary captures the **open ambiguities
> requiring owner decision** before implementation, plus the dispatch-mode
> failure that produced this distillate instead of per-TC files.

---

## 0. Dispatch-mode note (manager-side mistake)

The 6 INV agents were dispatched with `subagent_type: Plan`, which the harness
puts in strict read-only mode (no file creation, no PR, no branch push). Each
agent produced its investigation **content** correctly but could not persist
to disk. The right dispatch was `subagent_type: general-purpose`. Rather than
re-dispatching 6 fresh agents (token-expensive given the analysis is complete),
this single summary captures the high-value distillate: **per-TC open
ambiguities and their proposed defaults**. The IMPL agents (which ARE
`general-purpose`) will re-read the ADRs directly during implementation —
the investigation reports' main residual value is precisely this list of
owner-decision items.

Per-TC reports are recoverable from the dispatch transcript if needed for
audit-cycle traceability; this summary serves as the working artifact.

---

## 1. Sub-phase 1A — Schemas (11 TCs)

### Cross-cutting (applies to all 1A TCs)

| ID | Question | Proposed default |
|---|---|---|
| **X1** | `_common.py` is referenced in ADR-042 §5.2 but not in any ADR's `governs.modules` / `governs.contracts`. Closure check may flag its 9 `Annotated` type aliases as orphan d-class drift. | Add `scieasy.qa.schemas._common` to ADR-042 `governs.modules` via §27.4 errata in the same PR as 1A.1 implementation. |
| **X2** | `Validator` Protocol in `scieasy.qa.workflow.gate` — `@runtime_checkable` or static-only? | `@runtime_checkable` (enables runtime stage-loader validation). |
| **X3** | Verbatim ADR imports include some unused symbols (e.g., `Literal` in §6.2; `Field` in §6 multiple times; 4 of 8 imports in ADR-044 §5.1). | Drop unused imports for ruff F401 cleanliness; record deviation in PR body for cycle audit. |

### TC-1A.1 frontmatter

- Owner action: same as **X1**.
- Non-blocking: `model_rebuild()` at end of `frontmatter.py` to force-resolve `AgentRuntime` forward ref via side-effect import of `maintainers`. Manager default: yes, add it.

### TC-1A.2 maintainers + _common

- Owner action: **X1**.
- Non-blocking: `AssistedByLine` regex verified compatible with current ADR frontmatter.

### TC-1A.3 audit report

- Non-blocking: `AuditReport.total_findings` is denormalised; add a `@model_validator(mode="after")` enforcing `total == sum(len(r.findings) for r in runs)`. Manager default: yes.
- Non-blocking: §7.3 says symlink `docs/audit/latest/` points to most recent. Windows symlinks need elevation; defer mechanism choice to 1B impl.

### TC-1A.4 facts

- Non-blocking: no extra validators in `FactsRegistry` (cross-field invariants enforced in 1B.3 `fact_drift` instead). Manager default: schema is purely structural.

### TC-1A.5 identity

- **Q5.1 (BLOCKING)**: `EmailStr` requires `pydantic[email]` extra (i.e., `email-validator` package). Verify present in `pyproject.toml`. **Owner action**: confirm install includes the extra; if not, IMPL-1A-b adds it.
- Non-blocking: `HumanIdentity` schema has NO model_validator enforcing MAINTAINER → signing_key present. Only the `requires_signing_key` property checks. Enforcement deferred to file-validation layer in 1C.3. Manager default: ship schema-only.

### TC-1A.6 tracker

- **Q6.1 (BLOCKING)**: ADR-043 frontmatter `tests:` doesn't list `tests/qa/test_schemas_tracker.py`; only `tests/qa/test_implementation_tracker.py` (tool-layer). **Owner action**: add `test_schemas_tracker.py` to ADR-043 frontmatter via errata, OR fold schema tests into the tool-layer file.
- Non-blocking: §2.3 monotonic status transitions are enforced by `scripts/audit/adr_implementation_check.py`, NOT by a pydantic validator. Manager default: schema purely structural.

### TC-1A.7 governance

- **Q7.1 (BLOCKING)**: `HoneypotRuleEntry` (nested in `GovernancePaths` per §3.2) is NOT in ADR-043 `governs.contracts`. Closure may flag. **Owner action**: same pattern as X1 — add to `governs.contracts` via errata.
- **Q7.2 (BLOCKING)**: ADR-043 frontmatter `tests:` has no `test_schemas_governance.py`. Same pattern as Q6.1.
- Non-blocking: `LoosenedAxis.axis: str` is unconstrained (14 axes documented in §3.4.1 but not enforced as enum). Manager default: keep `str` per ADR; semantic constraint lives in TC-1E.3 `monotonic_check`.
- Non-blocking: `GovernanceChangeLogEntry.runtime` has no default; ADR text omits default → required field. Manager default: keep as required.

### TC-1A.8 test_quality

- Non-blocking: no `model_validator` enforcing `mutations_total == killed + survived + timeout`. Manager default: schema purely structural.

### TC-1A.9 classification

- Non-blocking: same as X3 (vestigial `Literal`/`Field` imports).
- Non-blocking: `PathBoundary` overlap with `.governance-paths.yaml` + MAINTAINERS — keep independent; consistency-lint in TC-1F.

### TC-1A.10 doc schemas

- **Q10.1 (BLOCKING)**: ADR-044 §5.1 imports `Translation` from `scieasy.qa.schemas.frontmatter` but ADR-042 §5.2 places it in `_common`. **Owner action**: re-export `Translation` from `frontmatter.py` (IMPL-1A-a side), OR change ADR-044 §5.1 import to come from `_common`. Manager default: re-export from `frontmatter.py` (less ADR text churn).

### TC-1A.11 workflow gate

- Owner action: **X2**.
- Non-blocking: `StageContext.declared_data: dict[str, object]` — each stage validator parses its own slice; documented in docstring. Manager default: yes.

---

## 2. Sub-phase 1B — Audit tools (10 TCs)

### TC-1B.1 doc_drift

- **Q1B.1.1 (BLOCKING)**: companion-file location `docs/adr/ADR-042/algorithms/doc_drift_pseudocode.md` — first subdirectory under `docs/adr/`. **Owner action**: ratify the subdirectory convention before commit. Manager default: yes, ship in subdirectory per §28.0.
- Non-blocking: §9.4 `__all__` Phase 1 behavior — missing `__all__` reported as warning during Phase 1, error from Phase 2. Manager default: yes.
- Non-blocking: §9.2 step 8 "Aggregate into AuditReport" — `doc_drift.classify_repo` returns its own `AuditReport`; full cross-tool aggregation is `full_audit.run`'s job (1B.7).

### TC-1B.2 frontmatter_lint

- **Q1B.2.1 (BLOCKING)**: §5.6 names `scripts/audit/frontmatter_lint.py` but §9.6 names `src/scieasy/qa/audit/frontmatter_lint.py`. **Owner action**: ratify `src/scieasy/qa/audit/` as canonical; treat `scripts/audit/` mention as informal. Manager default: yes.
- **Q1B.2.2 (BLOCKING)**: `docs/contributing/` non-workflows files (e.g., `onboarding.md`, `policy/ai-assistance.md`, `reference/gate-cli.md`) have NO schema in ADR-044 §5. **Owner action**: either (a) extend `WorkflowDocFrontmatter` to cover all of `docs/contributing/`, (b) add `ContributingDocFrontmatter` schema (ADR amendment), or (c) fall-through permissive schema. Manager default: (c) for now; tighten later.
- Non-blocking: line numbers from pydantic ValidationError require `ruamel.yaml` SourceMap. Manager default: `line=None` for v1; tighten later.

### TC-1B.3 fact_drift

- **Q1B.3.1 (BLOCKING)**: Report-only mode for first cycle (§10.6 transitional period). **Owner action**: confirm `--severity-floor=warning` CLI flag during Phase 1; hard-error from Phase 2 onwards. Manager default: yes.
- Non-blocking: word-boundary regex for numeric detection (`\b6\b` not `6`). Manager default: yes.

### TC-1B.4 closure

- **Q1B.4.1 (BLOCKING)**: ADR-044 §12.3 closure extensions (workflow↔skill, entry-points↔reference, schemas↔reference, CLI↔reference) — ship in 1B.4 or defer to 1B.4-ext after 1D? Manager default: defer to 1B.4-ext (depends on 1D docs).
- **Q1B.4.2 (BLOCKING)**: §11.3.2 "semantic conflict" attribute source — `agent_editable` or `AutoGenSource.generation`? Manager default: `agent_editable` for now.
- **Q1B.4.3 (BLOCKING)**: `governs.contracts` (symbol-level) closure — owned by `doc_drift` (d-class) or `closure`? Manager default: `doc_drift` owns symbol-level; `closure` owns file/module-level.
- Non-blocking: generated paths (sphinx-autoapi output) exempted via `pyproject.toml [tool.closure] exclude_paths`.

### TC-1B.5 trailer_lint

- **Q1B.5.1 (BLOCKING)**: Phase-3 cutoff storage — `docs/facts/generated.yaml` field `facts.workflow.phase3_cutoff_sha`? Manager default: yes, generated by `extract_workflow_facts.py` (1H.8). Until then, fall back to "no cutoff".
- **Q1B.5.2 (BLOCKING)**: `ADR:` trailer applicability — any commit touching `docs/adr/` vs any commit touching files in an ADR's `governs.files`? Manager default: (b) glob-based via closure resolver.
- Non-blocking: GitHub Reviews API scopes: `pull-requests:read` + `read:org`.
- Non-blocking: trailer-lint ordering after commitizen in pre-commit. Manager default: yes.

### TC-1B.6 committer_enforce

- **Q1B.6.1 (BLOCKING)**: `CommitLogEntry` schema ownership. Manager default: lives in `scieasy.qa.schemas.report` (1A.3) — add to that TC's `governs.contracts`.
- Non-blocking: log tampering response → warning-level Finding.
- Non-blocking: performance budget optimisation (cursor file `.git/scieasy-committer-enforce-cursor`). Manager default: yes.

### TC-1B.7 orchestrators (full_audit + contradiction_audit + complete_artifacts)

- **Q1B.7.1 (BLOCKING)**: `pre_push=True` tool subset definition. Manager default: enable `trailer_lint`, `committer_enforce`, `frontmatter_lint`, `closure`; disable `doc_drift`, `fact_drift`, mutation/sphinx.
- **Q1B.7.2 (BLOCKING)**: `docs/audit/adr-self-audit/` (§28.1 path) vs `docs/audit/reports/` (used by P0.4 audit #1120). Manager default: standardize on §28.1's path; migrate P0.4 location via symlink or redirect doc.
- **Q1B.7.3 (BLOCKING)**: §28.1 "internally contradicting rule clauses" heuristic — heuristic with warning severity, OR omit pre-Phase-1.5? Manager default: heuristic + warning; users can promote to error.
- Non-blocking: `complete_artifacts` pre-1D.9 translation check → warning "skipped; 1D.9 not yet operational".

### TC-1B.8 amendment_lint + consolidate_cascade

- **Q1B.8.1 (BLOCKING)**: Flat-script (`scripts/audit/amendment_lint.py` per §27.5) vs `scieasy.qa.audit.amendment_lint` module shim. Manager default: flat script canonical (per §27.5); add module shim for API consistency.
- **Q1B.8.2 (BLOCKING)**: `kind: replace` + `kind: extend` on same target — does `replace` win? Manager default: yes (use latest `date_created`); record as warning.
- **Q1B.8.3 (BLOCKING)**: Cross-ADR amendment chains (044 → 043 → 042) supported? Manager default: yes; warn if circular.

### TC-1B.9 codemod_lint

- **Q1B.9.1 (BLOCKING)**: `parse()` return type — `dict[str, Any]` per §9.6 stub literal, OR `CodemodMeta` pydantic model? Manager default: `dict` (stub literal) + sibling `parse_model() -> CodemodMeta`.
- **Q1B.9.2 (BLOCKING)**: `scieasy.qa.codemods.base.CodemodBase` not in ADR-042 `governs.modules`. Manager default: add `scieasy.qa.codemods` to `governs.modules` via §27.4 errata.

### TC-1B.10 4 ADR-044 audit tools

- **Q1B.10.1 (BLOCKING)**: `auto_generated_lint` baseline strategy — content-hash via `docs/audit/baselines/auto-gen.json` (manager proposal) vs mtime per §11.5 literal. Manager default: content-hash (mtime unreliable on Windows / cross-checkout).
- **Q1B.10.2 (BLOCKING)**: New `Regenerated-At:` trailer not in ADR-042 §13.2. Manager default: skip the escape hatch in v1; AG file hand-edits always emit ERROR.
- **Q1B.10.3 (BLOCKING)**: `kind:` frontmatter field on existing skills — migrate in 1B.10 PR vs split prep PR. Manager default: migrate in same PR (mechanical change).
- Non-blocking: `workflow_sync.run` and `skill_pointer_sync.check` overlap is intentional; documented.

---

## 3. Cross-cutting (Phase 1 dispatcher must resolve)

### 3.1 Test file naming convention

Multiple TCs need test files not listed in ADR frontmatter `tests:`. Pattern:
schema-only tests under `tests/qa/test_schemas_<area>.py`; tool-layer tests
under `tests/qa/test_<tool>.py`. **Owner action**: ratify via §27.4 errata
amendment to ADR-042/043 frontmatter, OR fold schema tests into tool tests.

### 3.2 Vestigial-imports policy

X3 affects multiple TCs. **Owner action**: ratify "drop unused imports;
record deviation in PR body" as the default policy for the cascade. Manager
default already applied.

### 3.3 Self-exemption window (§27.4) usage

P-1.2 used the self-exemption for the Acceptance PR. 1B PRs will not have
this exemption — they ship under the temp-review system (Phase -0.5) which
enforces a subset. Full audit machinery becomes self-applicable AS each tool
lands. **Owner action**: confirm strategy; no decision blocker.

### 3.4 Investigation-phase decommission

This summary file is the only investigation artifact. After Phase 1
completes and the full audit toolchain is live, this file may be archived
under `docs/audit/decommission-log.md` (created by P-0.5.D) along with the
temp-review system. **Manager default**: yes.

---

## 4. Recommended next steps

1. **Owner triage** (≤ 1 day): review the BLOCKING ambiguities marked
   `(BLOCKING)` above. The proposed defaults are mostly safe; only those
   you disagree with need explicit override.
2. **Manager dispatches IMPL-1A-a** (general-purpose, template-verbatim):
   ship 1A.1 + 1A.2 + 1A.3 + `_common.py`. Apply X1 + X2 + Q5.1 + Q10.1
   defaults unless you override.
3. **IMPL-1A-b**: 1A.4 + 1A.5 + 1A.11.
4. **IMPL-1A-c**: 1A.6 + 1A.7 + 1A.8 + 1A.9 + 1A.10.
5. **IMPL-1B** (after 1A merges, max-6-parallel per master plan): the 10
   audit tools, dispatched in 3 sub-PRs (B1–B4 audit core; B5–B8
   trailer/orchestrators/amendment; B9–B10 lint specialised).
6. **Audit cycles** (every 3 TCs implemented): 2 no-context Plan agents
   per cycle reading the merged code + ADR text.

The investigation phase is **complete**. Implementation phase begins next.
