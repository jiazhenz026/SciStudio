---
title: "ADR-053 Spec 1 Personal Tool Library Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 53
language_source: en
---

# ADR-053 Spec 1 Personal Tool Library Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Deliver ADR-053 Spec 1 (personal tool library) in full — the new feature and the pre-existing runtime defects — as two reviewable PRs, with no deferred scope.`
- Task kind: `manager` (manager-owned); dispatched slices are `refactor`, `bugfix`, and `feature`
- Manager persona: `manager`
- Spec: `docs/specs/adr-053-personal-tool-library.md`
- ADR: `docs/adr/ADR-053.md` §3
- Issues: `#2020`, `#2021`, `#2009`, `#2022` (PR A) · `#1995`, `#1996`, `#2023`, `#2024`, `#2025`, `#2026` (PR B)
- Manager gate record: `.workflow/records/1995-adr-053-spec1-personal-tool-library.json`
- Protected branch: `main`
- Umbrella branch: `track/adr-053-spec1-personal-tool-library`
- Umbrella PR: `#2029`
- Umbrella PR title: `[DO NOT MERGE] ADR-053 Spec 1: personal tool library (manager track)`
- Manager worktree: `SciStudio-wt-2053-mgr`
- Final PR target:
  - PR A -> `main`
  - PR B -> `fix/2020-adr-053-registry-runtime-defects` (stacked; GitHub retargets to `main` when PR A merges)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
- Dispatch prompts committed under `docs/planning/adr-053-spec1-dispatch-prompts/`

### 1.1 Delivery Branches

| Branch | Base | Final PR | Closes |
|---|---|---|---|
| `fix/2020-adr-053-registry-runtime-defects` | `origin/main` | PR A | `#2020`, `#2021`, `#2009`, `#2022` |
| `feat/1995-adr-053-personal-tool-library` | Track A branch | PR B | `#1995`, `#1996`, `#2023`, `#2024`, `#2025`, `#2026` |

PR B is stacked on PR A because spec §12.2 step 1 (the shared provisioning
helper) is the foundation every feature slice sits on. Each PR therefore shows
only its own diff.

### 1.2 Owner Decisions Recorded Before Dispatch

| Decision | Answer | Where it binds |
|---|---|---|
| Spec §13 OQ-1 (FR-016): type filename shadowing an importable top-level module | **Reject the file and report an error** — registration is refused, not merely warned | A3 (#2022) |
| PR structure | Stacked: PR B based on PR A | manager |
| `admin-approved:core-change` for `src/scistudio/core/types/base.py` (FR-053) | **Authorized**; owner applies the label to PR B | B2 (#2023) |
| `#2009` previewer registry refresh | **Included in PR A** alongside `#2021` | A2 |

## 2. Scope

- In scope:
  - `src/scistudio/core/dropins.py` (new shared drop-in provisioning helper)
  - `src/scistudio/core/types/{base,registry,serialization}.py`
  - `src/scistudio/blocks/registry/_scan.py`, `src/scistudio/blocks/io/_unified_dispatch.py`
  - `src/scistudio/api/runtime/_projects.py`, `src/scistudio/api/_block_source.py`
  - `src/scistudio/api/routes/{blocks,git,packages,types,user_library}.py`, `src/scistudio/api/schemas.py`
  - `src/scistudio/ai/agent/mcp/**` (type scan dirs + promotion tool)
  - `frontend/src/components/BlockPalette*`, `TypePalette.tsx`, `BlockDetailPopover.tsx`,
    `frontend/src/config/typeColorMap.ts`, `frontend/src/components/nodes/BlockNode.parts/PortHandles.tsx`,
    `frontend/src/components/WorkflowCanvas.tsx`, `frontend/src/App.tsx`,
    `frontend/src/App.parts/{ProjectWorkspace,useProjectActions}.tsx|ts`,
    `frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx`, `frontend/src/lib/api/**`
  - `docs/specs/frontend-block-palette.md`, `docs/planning/adr-053-spec1-*`
  - Tests named in spec §11
- Out of scope:
  - A user tier for previewers and any `OwnerKind` change (#2017) — spec §scope.out
  - The palette tips strip (#1997) — belongs to the Learning Center spec
  - Learning Center entries, tutorial registry, progress, first-run landing (#1998, #1999)
  - Codebase import / agent transcription (#2000, #2001, #2002) — **owned by the parallel
    spec 2 manager on `track/adr-053-work-import`**
  - Block discovery tier semantics, the registry data model, type serialization format
  - Sandboxing drop-in execution (#1531)
  - `docs/ai-developer/**` (governance surface; no `governance_touch` declared)
- Protected paths:
  - `src/scistudio/core/types/base.py` — requires `admin-approved:core-change` on PR B
    (FR-053); owner authorized, owner applies the label.
  - All other `src/scistudio/core/**` edits stay inside the declared files above.
- Deferred work:
  - `none` — owner directive is complete delivery. Any deferral discovered mid-flight is a
    blocker to raise, not a TODO to write, unless the owner authorizes it and it is
    recorded in §9 with a tracked issue.

### 2.1 Parallel Manager Coordination

A second manager is implementing spec 2 (`docs/specs/adr-053-work-import.md`) on
`track/adr-053-work-import`, worktree `SciStudio-wt-work-import`. Expected contact
surfaces, and how they are handled:

| Surface | Risk | Handling |
|---|---|---|
| `src/scistudio/ai/agent/mcp/runtime.py` | Both tracks touch agent runtime | This track owns the type scan-dir registration (FR-059). Spec 2 owns session spawn. Conflict resolved at integration by the manager, not by an agent. |
| `frontend/src/components/Toolbar*` | Spec 2 adds a "Bring in my work" entry; B5 adds "New data type" | Different files under `Toolbar.parts/`; B5 owns `FileOperationsGroup.tsx` only. |
| `src/scistudio/api/schemas.py` | Both may add response models | This track's additions are block-origin and type-listing models only. |
| Drop-in type import (#2022) | Spec 2 **depends** on this fix | Spec 2 consumes it after PR A merges; this track must not weaken it. |

Agents MUST NOT edit files owned by the spec 2 track and MUST NOT rebase onto
`track/adr-053-work-import`.

## 3. Conventions

- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created
      (`track/adr-053-spec1-personal-tool-library`, `SciStudio-wt-2053-mgr`, off `origin/main` at `b485e293`).
- [x] Existing issues linked; no new issue created (`#1995`, `#1996`, `#2009`, `#2020`–`#2026` all already open).
- [x] Gate record started (`.workflow/records/1995-adr-053-spec1-personal-tool-library.json`).
- [x] Scope include/exclude recorded in the gate record.
- [x] Owner decisions on OQ-1, PR structure, core-change label, and #2009 recorded (§1.2).
- [x] Umbrella branch created.
- [x] Umbrella PR opened (`#2029`).
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found (`PYTHONPATH=./src` used in every worktree).
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and committed under
      `docs/planning/adr-053-spec1-dispatch-prompts/`.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change` (PR B only, narrow protected-core authorization — not a gate bypass)
- Owner authorization source: `owner chat, 2026-08-07 — "Authorized — I will apply it"`
- Reason: `FR-053 — src/scistudio/core/types/base.py gains two optional colour class attributes on DataObject. The label authorizes the protected path only; it does not bypass scope, docs, issue linkage, or check obligations.`

No broad bypass label (`admin-approved:bypass`, `human-authored`) is authorized for
this dispatch. Standard gate validation applies to every agent and to both final PRs.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `gate_record check --mode pre-commit` | `N/A` | `[ ]` | `<ledger event>` |
| Commit message | `gate_record check --mode commit-msg` | `N/A` | `[ ]` | `<ledger event>` |
| Pre-PR reconcile (PR A) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | `<ledger reconcile event>` |
| Pre-PR reconcile (PR B) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | `<ledger reconcile event>` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/CI/runtime behavior changed: `no` — this dispatch changes
  product runtime and UI, not the gate CLI, PR wrapper, hooks, or CI workflow graph.
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — no AI-developer governance surface changes. Product docs updated instead: docs/specs/frontend-block-palette.md (B3, B4) and docs/specs/adr-053-personal-tool-library.md §13 OQ-1 resolution (A3).`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `dispatch-prompts/a1-provisioning-helper.md` | Shared drop-in provisioning helper; four consumers; scan-order reconciliation | `fix/2020-dropin-provisioning-helper` | `SciStudio-wt-a1` | `src/scistudio/core/dropins.py`, `src/scistudio/core/types/serialization.py`, `src/scistudio/core/types/registry.py`, `src/scistudio/api/runtime/_projects.py`, `src/scistudio/ai/agent/mcp/runtime.py`, `src/scistudio/blocks/io/_unified_dispatch.py`, `tests/api/test_registry_provisioning_parity.py` | frontend, routes, `_scan.py` | `#2020` | `[ ]` |
| `A2` | `implementer` | `N/A` | `dispatch-prompts/a2-reload-symmetry.md` | Type + previewer registry refresh on package install/uninstall and branch switch | `fix/2021-registry-reload-symmetry` | `SciStudio-wt-a2` | `src/scistudio/api/routes/git.py`, `src/scistudio/api/routes/packages.py`, `src/scistudio/api/runtime/_projects.py`, `src/scistudio/previewers/**` (refresh entry only), `tests/api/test_registry_reload_symmetry.py` | `core/dropins.py`, `_scan.py`, frontend | `#2021`, `#2009` | `[ ]` |
| `A3` | `implementer` | `N/A` | `dispatch-prompts/a3-dropin-type-import.md` | Drop-in block imports drop-in type; worker parity; shadowing rejection; failure surfacing | `fix/2022-dropin-type-import` | `SciStudio-wt-a3` | `src/scistudio/blocks/registry/_scan.py`, `src/scistudio/blocks/registry/__init__.py`, `src/scistudio/core/dropins.py` (import-roots only), `src/scistudio/api/routes/blocks.py` (failure surfacing), `docs/specs/adr-053-personal-tool-library.md` (§13 OQ-1), `tests/blocks/test_dropin_type_import.py` | `_projects.py`, `packages.py`, `git.py`, frontend palette | `#2022` | `[ ]` |
| `AUDIT-A` | `audit_reviewer` | `with-context` | `dispatch-prompts/audit-a-track-a.md` | Audit integrated Track A against spec §5, §10.3, §10.4 | `audit/adr-053-spec1-track-a` | `SciStudio-wt-audit-a` | `docs/audit/2026-08-07-adr-053-spec1-track-a.md` | implementation code | `#2020` | `[ ]` |
| `B1` | `implementer` | `N/A` | `dispatch-prompts/b1-origin-and-write-path.md` | Shared origin resolver; block origin split; user library write endpoint; MCP promote tool | `feat/1995-origin-tiers-and-user-library-write` | `SciStudio-wt-b1` | `src/scistudio/api/_block_source.py`, `src/scistudio/api/routes/blocks.py`, `src/scistudio/api/routes/user_library.py`, `src/scistudio/api/schemas.py`, `src/scistudio/api/__init__.py`, `src/scistudio/ai/agent/mcp/**`, `tests/api/test_block_origin_tiers.py`, `tests/api/test_user_library_write.py` | frontend, `core/types/**`, `routes/types.py` | `#1995`, `#1996` | `[ ]` |
| `B2` | `implementer` | `N/A` | `dispatch-prompts/b2-type-colour-and-types-api.md` | DataObject colour attrs; registry colour collection; per-type extensions; types listing + template endpoints | `feat/2023-type-colour-and-types-api` | `SciStudio-wt-b2` | `src/scistudio/core/types/base.py`, `src/scistudio/core/types/registry.py`, `src/scistudio/api/routes/types.py`, `src/scistudio/api/schemas.py`, `src/scistudio/api/__init__.py`, `src/scistudio/blocks/io/_config_enrichment.py`, `tests/api/test_types_routes.py`, `tests/core/test_type_colour.py` | frontend, `_block_source.py`, `user_library.py` | `#2023`, `#2024` | `[ ]` |
| `B3` | `implementer` | `N/A` | `dispatch-prompts/b3-palette-tiers-and-popover.md` | Origin-first grouping; shared palette helpers; Blocks tab rename; tier sections + empty states; interactive popover | `feat/1995-palette-tiers-and-popover` | `SciStudio-wt-b3` | `frontend/src/components/BlockPalette.tsx`, `frontend/src/components/BlockPalette.parts/**`, `frontend/src/components/BlockDetailPopover.tsx`, `frontend/src/components/palette/**` (new shared), `frontend/src/App.tsx`, `frontend/src/App.parts/ProjectWorkspace.tsx`, `frontend/src/lib/api/blocks*`, `docs/specs/frontend-block-palette.md` (§4, popover) | `TypePalette.tsx`, `typeColorMap.ts`, `useProjectActions.ts`, backend | `#1995`, `#2025` (popover only) | `[ ]` |
| `B4` | `implementer` | `N/A` | `dispatch-prompts/b4-types-tab-and-canvas-colour.md` | Data types tab; type tiles + popover contents; canvas colour source switch with loading fallback | `feat/2025-data-types-tab-and-canvas-colour` | `SciStudio-wt-b4` | `frontend/src/components/TypePalette.tsx`, `frontend/src/config/typeColorMap.ts`, `frontend/src/components/nodes/BlockNode.parts/PortHandles.tsx`, `frontend/src/components/WorkflowCanvas.tsx`, `frontend/src/lib/api/code.ts`, `frontend/src/store/**` (types slice), `frontend/src/App.tsx`, `frontend/src/App.parts/ProjectWorkspace.tsx`, `docs/specs/frontend-block-palette.md` (tab section) | `BlockPalette.parts/**`, `useProjectActions.ts`, backend | `#2025`, `#2024` (frontend) | `[ ]` |
| `B5` | `implementer` | `N/A` | `dispatch-prompts/b5-promotion-and-new-file.md` | Promotion action E1/E2/E4/E5 + cascade; New data type; new-file destination choice | `feat/1996-promotion-and-new-file-flows` | `SciStudio-wt-b5` | `frontend/src/App.parts/useProjectActions.ts`, `frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx`, `frontend/src/lib/api/userLibrary.ts` (new), `frontend/src/components/promotion/**` (new), source-editor toolbar + canvas node menu components, `frontend/src/components/BlockDetailPopover.tsx` (action row only), `frontend/src/components/TypePalette.tsx` (action row only) | `paletteModel.ts`, `typeColorMap.ts`, backend | `#1996`, `#2026` | `[ ]` |
| `AUDIT-B` | `audit_reviewer` | `with-context` | `dispatch-prompts/audit-b-track-b.md` | Audit integrated Track B against spec §3, §4, §6–§9 | `audit/adr-053-spec1-track-b` | `SciStudio-wt-audit-b` | `docs/audit/2026-08-07-adr-053-spec1-track-b.md` | implementation code | `#1995` | `[ ]` |
| `AUDIT-SEC` | `audit_reviewer` | `no-context` | `dispatch-prompts/audit-sec-no-context.md` | Independent review of the second write door and the `sys.path` widening | `audit/adr-053-spec1-write-path` | `SciStudio-wt-audit-sec` | `docs/audit/2026-08-07-adr-053-spec1-write-path.md` | implementation code | `#1996` | `[ ]` |

### 6.1 Wave Order

Sequencing follows spec §12.2. Agents in the same wave run in parallel and own
disjoint files.

| Wave | Agents | Gate to next wave |
|---|---|---|
| A-1 | `A1` | Helper API stable; parity test green |
| A-2 | `A2`, `A3` | Both merged into Track A branch |
| A-3 | `AUDIT-A` | P1 findings fixed |
| B-1 | `B1`, `B3` | Origin contract landed backend + frontend |
| B-2 | `B2` | Types endpoint available |
| B-3 | `B4` | Types tab + canvas colour landed |
| B-4 | `B5` | Promotion + new-file landed |
| B-5 | `AUDIT-B`, `AUDIT-SEC` | P1 findings fixed |

### 6.2 Frozen Contracts

These are fixed before dispatch so parallel agents cannot disagree.

**Block origin vocabulary** (FR-001, FR-002, FR-004) — `builtin` | `user` | `project` |
`package` | `custom`. `custom` is the unresolvable-path fallback only. `builtin` is
unchanged from today so existing consumers keep working.

**Type origin vocabulary** (FR-005) — `core` | `user` | `project` | `package` | `custom`.

**Shared origin resolver** (FR-003) — one function, consumed by both the block and the
type surface. B1 creates it; B2 consumes it and MUST NOT write a second path comparison.

**Shared drop-in provisioning helper** (FR-057, FR-058) — `src/scistudio/core/dropins.py`.
It must live in `scistudio.core` or lower: `scistudio.core` is forbidden from importing
`scistudio.blocks` by the import-linter contract "Core must not depend on blocks, engine,
api, ai, or workflow", and `scistudio.core.types.serialization` is one of the four
consumers. Required surface:

- drop-in scan directories for a given tier and project context (blocks and types),
- import roots for drop-in execution (project types dir, user types dir, user site dir),
- user-tier resolution that never depends on an active project (FR-060).

**User library roots** — `~/.scistudio/blocks/` and `~/.scistudio/types/`, resolved
through the same helper so there is exactly one answer to "where does the user tier live".

## 7. Track A: Registry Runtime Defects (PR A)

### 7.1 Track Scope

- Owner: `manager`
- Branch: `fix/2020-adr-053-registry-runtime-defects`
- In scope:
  - FR-057 – FR-061: one shared provisioning helper consumed by all four registration points
  - FR-062 – FR-065: reload symmetry for the type registry, extended to the previewer registry (#2009)
  - FR-012 – FR-016: drop-in block imports a drop-in type; worker parity; failure surfacing; shadowing rejection
- Out of scope:
  - Origin tier split, write path, palette, types API — all Track B
- Required docs:
  - `docs/specs/adr-053-personal-tool-library.md` §13 OQ-1 marked resolved (A3)
  - `CHANGELOG.md` entry for the user-visible defect fixes
- Required tests:
  - `tests/api/test_registry_provisioning_parity.py` (A1)
  - `tests/api/test_registry_reload_symmetry.py` (A2)
  - `tests/blocks/test_dropin_type_import.py` (A3)

### 7.2 Dispatch

- [ ] `A1` prompt created from the work template and committed.
- [ ] `A2` prompt created from the work template and committed.
- [ ] `A3` prompt created from the work template and committed.
- [ ] Agent branches/worktrees assigned.
- [ ] Write sets and out-of-scope paths included in every prompt.
- [ ] TODO rule included in every prompt.
- [ ] Required checks included in every prompt.

### 7.3 Implementation

- [ ] `A1` shared provisioning helper + four consumers (FR-057 – FR-060) -> `<commit>`
- [ ] `A1` scan-order reconciled or documented at both call sites (FR-061) -> `<commit>`
- [ ] `A1` provisioning parity test -> `tests/api/test_registry_provisioning_parity.py`
- [ ] `A2` package install/uninstall refreshes type registry (FR-063) -> `<commit>`
- [ ] `A2` branch switch refreshes type registry (FR-064) -> `<commit>`
- [ ] `A2` previewer registry refreshed at the same sites (#2009) -> `<commit>`
- [ ] `A2` reload symmetry test -> `tests/api/test_registry_reload_symmetry.py`
- [ ] `A3` types dirs on `sys.path` for drop-in execution (FR-012) -> `<commit>`
- [ ] `A3` worker parity via `runtime_import_roots` (FR-013) -> `<commit>`
- [ ] `A3` project types shadow user types (FR-014) -> `<commit>`
- [ ] `A3` import failure surfaced to the user (FR-015) -> `<commit>`
- [ ] `A3` colliding type filename rejected with an error (FR-016, OQ-1) -> `<commit>`
- [ ] `A3` §2.5 reproduction now registers `uses_spectrum` -> `tests/blocks/test_dropin_type_import.py`
- [ ] Docs: spec §13 OQ-1 resolution + CHANGELOG -> `<commit>`

### 7.4 Audit

- [ ] `AUDIT-A` assigned (`with-context`).
- [ ] Audit report file path assigned: `docs/audit/2026-08-07-adr-053-spec1-track-a.md`
- [ ] Audit report committed.
- [ ] Audit report merged into PR A evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager (every changed file, not summaries).
- [ ] Scope compliance verified per agent.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged into `fix/2020-adr-053-registry-runtime-defects`.
- [ ] `gate_record check --mode pre-pr` green.
- [ ] PR A opened via `python scripts/scistudio_pr_create.py`.
- [ ] PR A CI green.

## 8. Track B: Personal Tool Library Feature (PR B)

### 8.1 Track Scope

- Owner: `manager`
- Branch: `feat/1995-adr-053-personal-tool-library` (based on Track A branch)
- In scope:
  - FR-001 – FR-005 origin tiers; FR-006 – FR-011 user library write path and MCP tool
  - FR-017 – FR-025 promotion and cascade; FR-026 – FR-028 types API
  - FR-029 – FR-033 new-file flows; FR-034 – FR-046 palette and Data types tab
  - FR-049 – FR-056 declared type colour and per-type extensions; FR-066 – FR-067 canvas colour source
- Out of scope:
  - Everything in Track A (already landed on the base branch)
  - Previewer user tier (#2017), tips strip (#1997), Learning Center, work import
- Required docs:
  - `docs/specs/frontend-block-palette.md` amended (B3 for §4 sections/ordering/grouping and the popover; B4 for the Data types tab)
  - `CHANGELOG.md` entry for the feature
- Required tests: spec §11 rows for §3, §4, §6–§9

### 8.2 Dispatch

- [ ] `B1`–`B5` prompts created from the work template and committed.
- [ ] Agent branches/worktrees assigned.
- [ ] Write sets and out-of-scope paths included in every prompt.
- [ ] Frozen contracts (§6.2) restated in every prompt.
- [ ] TODO rule included in every prompt.
- [ ] Required checks included in every prompt.

### 8.3 Implementation

- [ ] `B1` shared origin resolver + block origin split + fallback (FR-001 – FR-004) -> `<commit>`
- [ ] `B1` user library write endpoint, inverse path constraint, no silent overwrite (FR-006 – FR-009) -> `<commit>`
- [ ] `B1` registry refresh after write (FR-010) -> `<commit>`
- [ ] `B1` MCP promotion tool (FR-011) -> `<commit>`
- [ ] `B2` `DataObject` colour attributes (FR-049) -> `<commit>` **[protected core]**
- [ ] `B2` registry colour collection + invalid-colour fallthrough (FR-050, FR-052) -> `<commit>`
- [ ] `B2` per-type load/save extensions from `FormatCapability` (FR-054 – FR-056) -> `<commit>`
- [ ] `B2` types listing + type template endpoints (FR-026 – FR-028, FR-005) -> `<commit>`
- [ ] `B3` origin-first grouping in `buildPaletteSections` (FR-038) -> `<commit>`
- [ ] `B3` Blocks tab rename, My Library / This Project sections, empty states (FR-034 – FR-037) -> `<commit>`
- [ ] `B3` shared palette helpers extracted (§10.1, FR-047) -> `<commit>`
- [ ] `B3` interactive popover, drag unaffected (FR-044 – FR-046) -> `<commit>`
- [ ] `B4` Data types tab, tiles, filter chips, empty states (FR-039 – FR-041) -> `<commit>`
- [ ] `B4` type popover contents incl. parent chain and extensions (FR-042, FR-043) -> `<commit>`
- [ ] `B4` canvas colour source switch + loading fallback (FR-066, FR-067, FR-051) -> `<commit>`
- [ ] `B5` promotion action shared across E1/E2/E5, copy-not-move, collision prompt, hidden rules (FR-017 – FR-020, FR-025) -> `<commit>`
- [ ] `B5` cascade promotion with AST dependency detection (FR-021 – FR-024) -> `<commit>`
- [ ] `B5` New data type + new-file destination choice E4 (FR-029 – FR-033) -> `<commit>`
- [ ] Docs: `docs/specs/frontend-block-palette.md` + CHANGELOG -> `<commit>`

### 8.4 Audit

- [ ] `AUDIT-B` assigned (`with-context`).
- [ ] `AUDIT-SEC` assigned (`no-context`) for the write path and `sys.path` widening.
- [ ] Audit report paths assigned:
      `docs/audit/2026-08-07-adr-053-spec1-track-b.md`,
      `docs/audit/2026-08-07-adr-053-spec1-write-path.md`
- [ ] Audit reports committed.
- [ ] Audit reports merged into PR B evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 8.5 Integration

- [ ] Agent output reviewed by manager (every changed file, not summaries).
- [ ] Scope compliance verified per agent.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged into `feat/1995-adr-053-personal-tool-library`.
- [ ] `gate_record check --mode pre-pr` green.
- [ ] PR B opened via `python scripts/scistudio_pr_create.py`, targeting the Track A branch.
- [ ] `admin-approved:core-change` applied by owner.
- [ ] PR B CI green.

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-08-07` | `manager` | `Spec §12.1 lists no home for the shared provisioning helper; core cannot import blocks.` | `Frozen contract §6.2 places it at src/scistudio/core/dropins.py and requires import-linter to pass.` | `N/A` |
| `2026-08-07` | `manager` | `#2009 (previewer reload) is outside the spec's declared scope.` | `Owner authorized inclusion in PR A (§1.2).` | `N/A` |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate records include issue, scope, plan, docs, tests, checks, Sentrux evidence when
      needed, commit, and PR evidence for both tracks.
- [ ] PR A closes `#2020`, `#2021`, `#2009`, `#2022`.
- [ ] PR B closes `#1995`, `#1996`, `#2023`, `#2024`, `#2025`, `#2026`.
- [ ] `admin-approved:core-change` present on PR B.
- [ ] CI passed on both PRs.
- [ ] Checklist final state matches both PRs and both gate records.
- [ ] Umbrella PR `#2029` closed without merging.
