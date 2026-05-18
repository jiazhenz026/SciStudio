# Issue #1171 — Phase 1H sub-PR 2: AGENTS.md hierarchy migration

**Cascade**: ADR-042/043/044 QA Infrastructure Overhaul · umbrella #1113
**Parent**: #1139 (Phase 1H umbrella)
**Tracking branch**: `track/adr-042/1h-workflow-v2`
**Sibling sub-PRs**: #1150 (sub-PR 1 Workflow v2 shadow), #1164 (sub-PR 3 skills + committer + extractors)
**Date**: 2026-05-18
**Author**: @claude (Opus 4.7 1M)
**Workflow gate task**: `20260518-075646-phase-1h-sub-pr-2-agents-md-hierarchy-mi`

## Scope

Two TCs from the Phase 1H slice:

- **TC-1H.3** — root `AGENTS.md` (canonical, ≤200 lines) per ADR-042 §12.1 + ADR-043 §5.3.
- **TC-1H.4** — 8 per-subtree `AGENTS.md` files per ADR-042 §12.2 + ADR-043 §5.6.

## What shipped

### Root AGENTS.md

158 lines (target ≤200 per ADR-043 §5.3; soft ceiling 230 in the test for the Hotfix Mode carve-out). Replaces the prior 1106-line CLAUDE.md clone that the Phase 0 promotion commit (f0672f3) renamed but did not actually migrate.

Sections present (verbatim section headers):

- `## Identity` — what SciEasy is / isn't (one-paragraph distillation of CLAUDE.md §1).
- `## Policy (non-negotiable, always applies)` — 13 one-liners derived from CLAUDE.md §2 + §6 + §7.6 + §11 + §12.
- `## Routing` — skill table (14 rows) pointing to `.workflow/gate.py`, `.claude/skills/speckit-*`, the 11 `src/scieasy/_skills/qa/` skills, and `~/.claude/skills/agent-manager/`.
- `## Data classification` — per ADR-043 §6.1, 8 path-glob entries.
- `## Assessment rubric` — per ADR-043 §6.2, R1–R11 (R1–R10 from ADR-043 §6.2 example + R11 = "no LOCK on advancement").
- `## Paths` — per ADR-043 §6.3, three-tier ✅/⚠️/🚫 with 15 rows.
- `## Out-of-scope format` — verbatim TODO format from CLAUDE.md §7.6.
- `## Hotfix mode (live-debugging exception)` — verbatim §11.5 preserved per ADR-042 §27.3.
- `## Per-subtree AGENTS.md` — index of the 8 sub-files.

### Pointer files

Per ADR-042 §12.1 Windows fallback. Symlinks would require admin on Windows; the `@include` pattern works identically across hosts.

| File | Content |
|---|---|
| `CLAUDE.md` | `@include AGENTS.md` |
| `CURSOR.md` | `@include AGENTS.md` |
| `GEMINI.md` | `@include AGENTS.md` |
| `.aiderrc` | `system: AGENTS.md` |

### 8 per-subtree AGENTS.md

Each carries ADR-042 §12.2 frontmatter (`scope`, `parent_agents_md`, `applies_to_agents`, `governing_adrs`) and the 7 required sub-file sections from ADR-043 §5.6 (Scope, Policy, Routing, Data classification, Assessment rubric, Paths, Out-of-scope).

| Path | Governing ADRs declared | Notable additions |
|---|---|---|
| `src/scieasy/AGENTS.md` | 42, 43, 44 | `ruff`/`ruff format`/`mypy --strict` rubric criteria |
| `src/scieasy/core/AGENTS.md` | 17–22, 42 | Mutation ≥ 0.85 for core; ADR-link required in every commit body |
| `src/scieasy/blocks/AGENTS.md` | 28–31, 33, 35, 42 | `category`/`subcategory` discipline (ADR-029); AppBlock file-exchange |
| `src/scieasy/qa/AGENTS.md` | 42, 43, 44 | Mutation ≥ 0.90 per ADR-042 §4.5; 🚫 outside active implementation phase |
| `frontend/AGENTS.md` | 33, 36, 38, 42 | Chrome smoke test mandatory; `npm run dev` forbidden in sub-agent context |
| `docs/AGENTS.md` | 42, 43, 44 | ADR/spec Tier-2 approval; append-only audit logs |
| `.github/AGENTS.md` | 42, 43, 44 | `weakened_ci_check.py` enforcement; pin actions to SHA |
| `.workflow/AGENTS.md` | 42 | Gate stdlib-only constraint; v2 monotonic-strengthening rule |

### Test coverage

`tests/qa/test_agents_md_hierarchy.py` — 50 tests, all pass. Covers:

- Root: file exists, 7 required sections, ≤230-line ceiling, subtree references, Hotfix Mode preservation (verbatim trigger phrases).
- Pointer files: each exists, each contains the expected pointer substring, each is 1 non-blank line.
- Sub-files: each exists, each has frontmatter with required keys, each has 7 required sections, each `## Paths` section uses at least one tier marker, no sub-file duplicates a ≥10-line root paragraph (proxy for ADR-042 §12.4 non-duplication rule).

```text
============================= 50 passed in 1.66s =============================
```

`ruff check tests/qa/test_agents_md_hierarchy.py` clean. `ruff format --check` clean.

## Design decisions

### Hotfix Mode preservation

ADR-042 §27.3 explicitly preserves CLAUDE.md §11.5. ADR-043 §5.4 maps §11.5 to a future `hotfix-mode` skill (with `disable-model-invocation: true`). Owner directive in the dispatch prompt prioritized **no disruption** over skill-extraction.

Resolution: keep §11.5 verbatim in root AGENTS.md under `## Hotfix mode`. This pushes the root from a "tightest possible" ~140 lines to 158 lines — still under the ≤200 ADR-043 §5.3 target. Future Phase work may extract this to a skill once the runtime supports `disable-model-invocation` cleanly; tracked implicitly by ADR-043 §5.4 Phase 1H follow-up.

### Pointer pattern over symlinks

ADR-042 §12.1 names symlinks as the canonical form and `@include AGENTS.md` as the Windows fallback. We use the fallback uniformly because:

1. The repo is developed on Windows-primary by the owner.
2. `git` on Windows requires `core.symlinks=true` AND elevated privileges to create symlinks at clone time; this would silently break the repo for any user without those flags.
3. The fallback pattern is supported by every listed runtime per ADR-042 §17.2.

The content-equivalence check (ADR-042 §12.1 pre-commit hook) is Phase 1F work — TODO-tagged in the impl record but not in code (the pointer files have no code-side surface).

### Sub-AGENTS.md selection

The 8 paths come directly from ADR-042 §12.2 and ADR-043 §5.3. ADR-043 §5.3 also lists `src/scieasy/blocks/ai/AGENTS.md` as ~30 lines for "ADR-035-specific constraints" — we did not create this sub-file in this PR. Rationale: ADR-035 routing already appears in `src/scieasy/blocks/AGENTS.md` (`## Routing` row "AI orchestration constraints (ADR-035)"), and adding a deeper nested file would create a 3-tier hierarchy that the Phase 1F `agents-md-lint` (not yet shipped) has not been designed to walk. Tracked as out-of-scope below.

## Out-of-scope (TODO-tagged where surfaces exist)

Per CLAUDE.md §7.6 and the dispatch prompt:

1. **`agents-md-lint` pre-commit hook** (ADR-042 §12.4). Validates: root exists, pointer files resolve, every governed subtree has an AGENTS.md when `agents_required: true`, sub-files do not duplicate root content. Phase 1F. The test file `tests/qa/test_agents_md_hierarchy.py` enforces these invariants at the source-of-truth level; the pre-commit hook is the runtime guard.

2. **`classification_lint.py` CI gate** (ADR-043 §6). Validates the `## Data classification` section across all AGENTS.md files; cross-file consistency. Phase 1G.

3. **Content-equivalence pre-commit check** for pointer files (ADR-042 §12.1). Phase 1F.

4. **`src/scieasy/blocks/ai/AGENTS.md`** (ADR-035-specific). Not created — see "Sub-AGENTS.md selection" above. Open a follow-up issue when the Phase 1F lint hook ships if deeper nesting is required.

5. **`tests/AGENTS.md`**. Root `## Paths` already specifies `pytest timeout=60` for tests; deferred to Phase 1F-or-later when `agents-md-lint` can enforce sub-presence requirements.

6. **Hotfix Mode skill extraction** (ADR-043 §5.4 maps to `.claude/skills/hotfix-mode/SKILL.md` with `disable-model-invocation: true`). Owner directive in dispatch prompt declines this for now; verbatim §11.5 in root AGENTS.md is the chosen form.

No in-code TODO markers were needed because nothing in `src/` was edited by this PR. All deferrals are documentation/CI surface and are tracked in this impl record + the cascade umbrella #1113.

## Verification

| Check | Result |
|---|---|
| `pytest tests/qa/test_agents_md_hierarchy.py -v --timeout=60` | 50 passed |
| `ruff check tests/qa/test_agents_md_hierarchy.py` | clean |
| `ruff format --check tests/qa/test_agents_md_hierarchy.py` | clean |
| Root AGENTS.md line count | 158 (≤200 target, ≤230 ceiling) |
| 8 per-subtree files exist | ✅ |
| 4 pointer files exist with expected content | ✅ |
| Hotfix Mode preserved verbatim | ✅ (test_root_agents_md_preserves_hotfix_mode passes) |
| No sub-file duplicates ≥10-line root paragraph | ✅ (test_subtree_agents_md_does_not_duplicate_root passes for all 8) |
