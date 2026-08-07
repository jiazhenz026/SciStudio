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
| `admin-approved:core-change` for `src/scistudio/core/types/base.py` (FR-053) | **Authorized** for PR B | B2 (#2023) |
| `#2009` previewer registry refresh | **Included in PR A** alongside `#2021` | A2 |
| `admin-approved:core-change` for **PR A** as well | **Authorized.** Raised after manager review found `PROTECTED_CORE_PATTERNS` covers `src/scistudio/{core,engine,blocks,workflow,utils}/**`, so PR A needs the label too — broader than spec §12.1, which flagged only `base.py` | A1, A3, manager |
| Track B backend sequencing | Owner: dispatch B1/B2 **after** the Track A audit, not in parallel | manager |
| Standing authorization | Owner delegated all remaining decisions to the manager and went offline. Manager proceeds autonomously; every decision taken under this delegation is recorded in §9 | manager |

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

- Authorized bypass label: `admin-approved:core-change` (**PR A and PR B**, narrow protected-core authorization — not a gate bypass)
- Owner authorization source: `owner chat, 2026-08-07 — "Authorized — I will apply it"`
- Reason: `PROTECTED_CORE_PATTERNS (src/scistudio/qa/governance/gate_record/surfaces.py:73) covers src/scistudio/{core,engine,blocks,workflow,utils}/**. PR A lands the shared provisioning helper and the drop-in scan fix there; PR B additionally adds two optional colour class attributes to DataObject (FR-053). The label authorizes the protected paths only; it does not bypass scope, docs, issue linkage, or check obligations.`
- Manager note: `The manager cannot self-authorize. CI verifies label actor provenance. The owner authorized both PRs in chat on 2026-08-07 and delegated application of the label to the manager along with all remaining decisions.`

No broad bypass label (`admin-approved:bypass`, `human-authored`) is authorized for
this dispatch. Standard gate validation applies to every agent and to both final PRs.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `gate_record check --mode pre-commit` | `N/A` | `[ ]` | `<ledger event>` |
| Commit message | `gate_record check --mode commit-msg` | `N/A` | `[ ]` | `<ledger event>` |
| Pre-PR reconcile (PR A) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | `<ledger reconcile event>` |
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

- [x] `A1` shared provisioning helper + four consumers (FR-057 – FR-060) -> `src/scistudio/core/dropins.py`, commit `24a1426a`
- [~] `A1` scan-order kept separate, rationale recorded on the **type** side only (FR-061) -> `core/types/registry.py` module docstring, commit `24a1426a`. **Block-side back-pointer missing**; reassigned to A3 (prompt item 7a), since A3 owns `blocks/registry/**`.
- [x] `A1` provisioning parity test, 12 tests -> `tests/api/test_registry_provisioning_parity.py`
- [x] `A2` package install/uninstall refreshes type registry (FR-063) -> `_after_package_change`, commit `329f8737`
- [x] `A2` branch switch refreshes type registry (FR-064) -> `routes/git.py`, commit `329f8737`
- [x] `A2` previewer registry refreshed at the same sites (#2009) -> `refresh_all_registries`, commit `329f8737`. `src/scistudio/previewers/**` needed no change: `refresh_preview_service` already existed and #2009 was purely a call-site defect.
- [x] `A2` FR-062 audit found **seven** invalidation sites, not the five the issue listed — `open_project` and `_configure_static_registries` were unlisted. The latter is deliberately left alone: the preview service is built lazily, so unifying it there would eagerly build it at construction.
- [x] `A2` reload symmetry test, 8 tests, all 8 fail on base -> `tests/api/test_registry_reload_symmetry.py`
- [!] `A2` FR-065 cross-process refresh **partially** delivered. In-process is covered (`_RuntimeAdapter` reads registries through by property). The standalone `scistudio mcp-bridge` builds registries once in `make_mcp_runtime` with no invalidation channel; adding one needs IPC in `ai/agent/mcp/**` and has no trigger until the #1996 write endpoint exists. **Sequenced into B1**, recorded in §9 and in B1's prompt — not deferred.
- [ ] `A3` types dirs on `sys.path` for drop-in execution (FR-012) -> `<commit>`
- [ ] `A3` worker parity via `runtime_import_roots` (FR-013) -> `<commit>`
- [ ] `A3` project types shadow user types (FR-014) -> `<commit>`
- [ ] `A3` import failure surfaced to the user (FR-015) -> `<commit>`
- [ ] `A3` colliding type filename rejected with an error (FR-016, OQ-1) -> `<commit>`
- [ ] `A3` §2.5 reproduction now registers `uses_spectrum` -> `tests/blocks/test_dropin_type_import.py`
- [ ] Docs: spec §13 OQ-1 resolution + CHANGELOG -> `<commit>`

### 7.4 Audit

- [x] `AUDIT-A` assigned (`with-context`) -> commit `8205d828`
- [x] Audit report file path assigned: `docs/audit/2026-08-07-adr-053-spec1-track-a.md`
- [x] Audit report committed -> `8205d828`
- [x] Audit report merged into PR A evidence path -> merge `afab0e8a`
- [x] Findings recorded. **Recommendation: pass-with-fixes.** 2 P1, 3 P2, 4 P3.
- [x] P1 findings fixed before integration -> `A-FIX` commit `392bba5b`, integrated at `6a9eae24`
- [x] P2/P3 findings fixed -> same commit; all three P2s and all four P3s closed, none deferred

#### A-FIX outcome (all AUDIT-A findings closed)

One shared guard replaces the single-site rule:

```python
guard_dropin_type_roots(import_roots, *, bind=True) -> tuple[DropinTypeCollision, ...]
```

called from **four** sites — `_scan_tier1`, `BlockRegistry.instantiate`,
`engine/runners/worker.py::_prepend_runtime_import_roots`, and
`TypeRegistry._scan_filesystem_dirs` (with `bind=False`, because that pass loads by file
path and needs the verdict rather than the mitigation). The old `_shadowed_top_level_module`
and its scan loop are deleted, so nothing restates the rule.

Manager-verified reproduction, run against the base tree and the fix:

| | base `e3e95a75` | after `392bba5b` |
|---|---|---|
| worker resolves the shadowed name | `SHADOWED-BY-TYPE-FILE` (the `types/` file) | the **installed** module |
| colliding type in a real `TypeRegistry` | registered | **absent** |
| collision reported on the FR-015 surface | yes | yes (unchanged) |

7 of the new tests fail on the base tree and pass on the fix, so they are genuine
regression tests rather than assertions written to match the implementation.

**Manager prompt error, corrected by the agent.** My fix prompt located the worker's
`sys.path` injection at `blocks/registry/__init__.py:521`. The worker never calls
`BlockRegistry.instantiate` — it calls its own `_prepend_runtime_import_roots`
(`engine/runners/worker.py:96`). A-FIX went to the real file, added it as a declared scope
addition, and flagged it rather than halting for a four-line call. That was the right call:
stopping would have left both P1s open.

**MCP `reload_blocks`** got `hot_reload()` plus a new `TypeRegistry.rescan()` (clear, then
`scan_all`) because a bare `scan_all` is additive — later passes skip names already present,
so an edited type would keep its first definition forever. The MCP context exposes registries
as read-only properties over the live runtime, so in-place refresh is the only reach it has;
previewers stay outside it and the docstring says so rather than implying coverage.

Ratchet: **6981 LOC / 119 clusters, byte-identical to base.** Import-linter 13/13 kept.
mypy clean over 343 files.

#### AUDIT-A findings

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| P1-1 | P1 | **The shadowing guard does not cover the worker.** `_reject_shadowing_type_files` pre-binds the installed module only inside `BlockRegistry._scan_tier1`. The worker reconstructs through `registry/__init__.py:521` — `prepended_sys_paths(spec.runtime_import_roots)` with no pre-binding — so `{project}/types/sample_dep.py` shadows the installed `sample_dep` there. Demonstrated with a real `python -m scistudio.engine.runners.worker` run. **A new hazard introduced by Track A**: before #2022 the type dirs were never on `sys.path`. This is the exact scan-time-vs-run-time divergence FR-013/FR-057 exist to prevent. | `A-FIX`: move detection + pre-binding into one shared function in `core/dropins.py`, called from every site that puts type roots on `sys.path` |
| P1-2 | P1 | **"Rejected" is announced but registration is not refused.** `{project}/types/json.py` reports `DropinTypeNameCollision`, stdlib `json` still wins in the API process, **and the type still registers, resolvable and loadable**. The user is told to rename the file while the type keeps working. Owner's recorded decision was "registration is refused". Root cause of the miss: **not one of A3's 18 tests constructs a `TypeRegistry`.** | `A-FIX`: `TypeRegistry`'s drop-in pass skips colliding files using the same shared detection; test via a real `TypeRegistry` |
| P2-1 | P2 | **FR-062's audit stopped at one method name.** FR-062 is written in terms of invalidating *events*, but A2 enumerated only `refresh_block_registry` sites. Three more invalidate via `hot_reload()`: `POST /api/blocks/reload`, the file-save hook (`routes/projects.py:491`), and MCP `reload_blocks`. **Saving a file under `{project}/types/` refreshes nothing at all.** | `A-FIX` |
| P2-2 | P2 | A2's reload-symmetry test greps `api/routes/*.py` for three literal method names, so it structurally cannot see `hot_reload()`; its docstring overclaims what it proves. | `A-FIX`: replace with a behavioural test |
| P2-3 | P2 | A3's FR-016 spec rewrite dropped the owner's "registration is refused" wording; the §11 acceptance row now certifies a build that fails both P1s; §14 claims the hazard is closed "by binding the real module before any drop-in runs", untrue in the worker. | `A-FIX` |
| P3-1..4 | P3 | Directory-package collisions undetected (`*.py` glob only); the rejection eagerly imports the shadowed module on every scan; the sibling-`types/` inference is load-bearing but only documented, not pinned by a test; checklist §9 missed two accepted scope additions. | First three to `A-FIX`; the fourth fixed by the manager in this commit |

#### Manager judgments AUDIT-A re-verified independently

| Judgment I had accepted from an agent report | Verdict |
|---|---|
| A2 left `_configure_static_registries` out of the unified refresh (lazy preview service) | **Sound** — and no stale window: the lazy build sees the same `active_project is None`, and `open_project` rebuilds |
| `previewers/**` needed no change; #2009 was purely a call-site defect | **Sound** — `refresh_preview_service` pre-existed at `_data.py:248`; diffstat over `src/scistudio/previewers/` is empty, and #2009 did not grow into #2017 |
| A2's seven-site enumeration | **Count correct**, extras exactly as reported — but incomplete as a *method-name* audit, hence P2-1 |
| A3's `dropin_type_roots_for_block_dirs` derivation, and its claim the API server never sets `SCISTUDIO_PROJECT_DIR` | **Sound** — every `SCISTUDIO_PROJECT_DIR` write in `src/` targets a child-process env dict; FR-014 ordering holds across all reachable tier combinations; `add_scan_dir` has exactly one caller in `src/` so no bypass exists |
| A3's FR-061 back-pointer | **Delivered correctly** at `blocks/registry/__init__.py:403`, pointing at the type-registry record rather than duplicating it |

Spec §2.5 was reproduced independently by the audit: `False` before at `b485e293`, `True` after at `e3e95a75`, on the worker path too.

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

- [x] `B1` shared origin resolver + block origin split + fallback (FR-001 – FR-004) -> commit `19e31a10`. One `resolve_origin(surface, ...)` with `BLOCK_SURFACE` / `TYPE_SURFACE`; containment uses `os.path.realpath` + `Path.is_relative_to`, never string prefixes.
- [x] `B1` user library write endpoint, inverse path constraint, no silent overwrite (FR-006 – FR-009) -> `PUT /api/user-library/file?target=blocks|types&filename=…`; 409 on collision, `overwrite:true` the only replace path; 400/403/413/415/422 rejection matrix.
- [x] `B1` existence probe (FR-031) -> `GET /api/user-library/file` with the same 200/404 shape as the project endpoint, so B5's probe is a one-line analogue.
- [x] `B1` registry refresh after write (FR-010) -> `refresh_all_registries()`
- [x] `B1` MCP promotion tool (FR-011) -> `promote_to_user_library`; catalogue 35 → 36 tools
- [x] `B1` **FR-065 cross-process refresh, which A2 could not reach** -> `StandaloneMCPRuntime` exposes its registries as properties that first call `sync_dropins()`, comparing a `dropin_revision()` signature (path, size, `st_mtime_ns` per `.py` across both tiers). The shared directory *is* the channel, so it works both ways with no IPC.
- [x] `B2` `DataObject` colour attributes (FR-049) -> commit `3a65d12f` **[protected core]**. Manager verified the diff is **purely additive**: two optional `ClassVar[str | None] = None` and their docstrings, zero deletions, no behavioural code touched.
- [x] `B2` registry colour collection + invalid-colour fallthrough (FR-050, FR-052) -> validated at collection time, not render time; short forms expand, output lowercased; anything unparseable is dropped with a warning naming class, attribute and value, and arrives at the frontend as `null` rather than a bad string.
- [x] `B2` per-type load/save extensions from `FormatCapability` (FR-054 – FR-056) -> reported separately; `Series` really does save `.json` without loading it, which is the FR-055 asymmetry the spec wanted visible.
- [x] `B2` types listing + type template endpoints (FR-026 – FR-028, FR-005) -> `GET /api/types/` and `GET /api/types/template`; template shape byte-identical to the block template so FR-033 can share steps.
- [x] `B2` **FR-066 guard** -> `TypeHierarchyEntry.ui_ring_color` left dead, with a test asserting it stays unpopulated so the rejected second colour supply point cannot be reintroduced by someone who finds the field and assumes it was an oversight.
- [x] `B2` consumed B1's shared resolver rather than writing a second path comparison (FR-003), pinned by `test_the_origin_adapter_delegates_the_whole_vocabulary`.
- [x] `B3` origin-first grouping in `buildPaletteSections` (FR-038) -> commit `9d50bf00`. `derivePackage`'s `CUSTOM_PACKAGE` branch removed so no dead `Custom` section can reappear.
- [x] `B3` Blocks tab, My Library / This Project sections, empty states (FR-034 – FR-037) -> commit `9d50bf00`. FR-034 note: the **tab** already read `Blocks` on `origin/main`; what disagreed was the panel heading `Palette`, renamed so panel and tab agree and `Data types` reads as a peer.
- [x] `B3` shared palette helpers extracted (§10.1, FR-047) -> `frontend/src/components/palette/{sections,hoverPopover}.ts`, `{PaletteTile,FilterChips,DetailPopover}.tsx`. Manager verified `buildSections<T>` carries no block knowledge, so FR-047 holds. §10.2 respected: `derivePackage`, the io predicates, `CATEGORY_KEYS`, `portSignature` stayed block-side.
- [x] `B3` interactive popover, drag unaffected (FR-044 – FR-046) -> commit `9d50bf00`. `onDragStart` fires after `onLeave`. Mouse events used rather than pointer events because jsdom has no `PointerEvent`.
- [x] `B3` tests: paletteModel 11 → 31, plus 21 shared-helper and 12 component tests; **6 of 11 pre-existing palette-model tests rewritten** for the grouping-dimension change, as spec §14 predicted.
- [x] `B3` docs: `docs/specs/frontend-block-palette.md` amended for §4 sections/ordering, the grouping change, and the popover.
- [x] `B4` Data types tab, tiles, filter chips, empty states (FR-039 – FR-041) -> commit `25ce0c18`. B3's `TODO(#2025)` removed; manager verified none remains in `frontend/src/`.
- [x] `B4` type popover contents incl. parent chain and extensions (FR-042, FR-043) -> commit `25ce0c18`
- [x] `B4` canvas colour source switch + loading fallback (FR-066, FR-067, FR-051) -> commit `25ce0c18`. **FR-067 is solved by having no loading state**: `declaredTypeColors` is `undefined` until a complete listing lands, and the resolvers read `undefined` exactly as "declares nothing" — the pre-ADR-053 answer — so no placeholder colour exists in the path. The test is non-vacuous: it asserts the undeclared port's colour string and every port's `{top,left,right}` are unchanged **and** that the declaring port did change.
- [x] `B4` consumed every B3 helper with no per-surface special-casing, so FR-047 held in practice, not just in principle.
- [x] `B6` **type package attribution, closing the one partial requirement in this track** -> commit `52d47616`. FR-040's per-package A→Z split now works. `TypeSpec.package_root` records which distribution's discovery hook delivered the class; the route looks that root up in the map the block registry already maintains. Agreement with `BlockSummary.package_name` is **structural** — one string read once, not two derivations kept in step. Pinned by an end-to-end parity test that builds a real source package shipping one block and one type and scans both through real discovery machinery.

**B6's honest residual, recorded rather than smoothed over.** No discovery tier can make the two tabs *contradict* each other; what remains is *incompleteness*. A package whose `PackageInfo.name` is a display string (`"SRS Imaging"`) is blanked by the existing `routes/blocks.py` filter, so its types report `null` and stay lumped while the Blocks tab titles its section from a frontend display heuristic types have no equivalent of. Reproducing that heuristic backend-side would be inventing a name — the thing B4 and the manager both refused. A distribution shipping types but no blocks likewise reports `null`, with no Blocks section to disagree with. In every case the lumped `Packages` section still renders and no type is dropped.
- [x] `B5` promotion action shared across E1/E2/E5, copy-not-move, collision prompt, hidden rules (FR-017 – FR-020, FR-025) -> commit `11871bef`. Manager grepped it; AUDIT-B proved it more strongly: four render sites -> one `PromoteToLibraryAction` -> one `runPromotion` -> one `promoteToUserLibrary`, pinned by a test that mocks `runPromotion` and shows all three surfaces hit the same mock.
- [x] `B5` **FR-019 subtlety neither the spec nor the manager anticipated** -> the popovers pass `actions` only when the item is promotable. `DetailPopover` renders its hairline on truthiness and a JSX element is always truthy, so a component returning `null` would have left an empty ruled strip under every built-in tile, which is not "hidden". Covered by `it.each` over built-in / packaged / already-in-library asserting `palette-popover-actions` is absent.
- [x] `B5` cascade promotion with AST dependency detection (FR-021 – FR-024) -> commit `11871bef`. Parses statically from source the app already holds; classification is **not** re-derived client-side but read from `TypeSummary.origin`, which the backend filled with the FR-003 resolver, so no backend endpoint was needed. Second-level dependencies are reported and the one-level stop is proven by test.
- [x] `B5` New data type + new-file destination choice E4 (FR-029 – FR-033) -> commit `11871bef`. One `createDropinFile` flow; tests assert identical call sequences and the **same validator function object**.
- [x] Docs: `docs/specs/frontend-block-palette.md` + CHANGELOG -> across B3, B4, B5, B6
- [x] **Integration conflict only integration could catch** -> B6 made `TypeSummary.package_name` required while B5's promotion fixture was written against the pre-B6 shape. Both branches were green alone; the merge failed typecheck. Fixed by the manager at `327ae238`.

### 8.4 Audit

- [x] `AUDIT-B` assigned (`with-context`) -> commit `c2b41907`. **Recommendation: pass-with-fixes, 0 P1, 2 P2, 6 P3.**
- [x] `AUDIT-SEC` assigned (`no-context`) for the write path and `sys.path` widening.
- [x] Audit report paths assigned and committed.
- [~] Audit reports merged into PR B evidence path.
- [x] Findings recorded below.
- [x] No P1 findings in AUDIT-B.
- [~] P2/P3 findings -> dispatched to `B-FIX` on `fix/1996-track-b-audit-findings`

#### AUDIT-B findings

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| P2-1 | P2 | **The FR-066 dead-field guard cannot fail.** `test_type_hierarchy_still_carries_its_dead_colour_field` uses a fixture whose only registered types are the six core bases, none declaring a colour, so a reintroduced `ui_ring_color=entry.ui_ring_color` would leave the field `None` and the test would still pass. Its docstring, `CHANGELOG.md` and this checklist all claimed otherwise. | `B-FIX`: register a type that declares a colour, and verify the new test fails when the field is populated |
| P2-2 | P2 | **The MCP promotion tool applies a second, narrower origin rule, which is the exact FR-003 divergence the requirement exists to prevent, already realised rather than merely risked.** E1/E2/E5 hide promotion unless the resolved origin is `project`; E3 (`tools_library.py:167`) tests `source.parent == library_root`, so a `custom`-origin block is hidden by the three frontend entry points and **accepted by the agent**. Refusal-for-refusal parity is claimed in a docstring, in CHANGELOG and in this checklist, and is false as written. Root cause is layering: `resolve_origin` lives in `scistudio.api._block_source` and the import-linter contract "AI must not depend on api" forbids the AI layer from importing it. | `B-FIX`: move the resolver to a layer both `api` and `ai` can import, the same lesson as `core/dropins.py`, and add a parity test covering the whole vocabulary including `custom` |
| P3 x6 | P3 | Assorted. | `B-FIX` |

#### The six claims AUDIT-B re-verified independently

All upheld: FR-025 single implementation, proved more strongly than the manager's grep;
FR-019 on the resolved origin with the user-library trap explicitly pinned; FR-067 with a
**non-vacuous** no-re-layout test that also asserts the declaring port changed; FR-051
undeclared-type resolution byte-identical, the only deletion being the provably never
populated `ui_ring_color` branch; FR-066 nothing populates the field, though the guard is
weak (P2-1); and B6's package parity as structurally one string, its residual confirmed to be
incompleteness rather than contradiction.

Both manager-accepted scope additions were judged **accept**, and AUDIT-B supplied a reason
the manager had not: passing `NodeActionToolbar` a *node* rather than an `onPromote` callback
is correct precisely because a callback would have put a second copy of the FR-019 decision
in `BlockNode`.

Also confirmed: cascade genuinely writes dependencies rather than warning; no tips strip;
**zero** new `TODO(` in the range and B3's `TODO(#2025)` gone; every source change carries
test changes; seven ledgers clean of absolute paths, usernames and transcripts.

Not done, stated rather than glossed: no browser smoke check (no browser on this host),
Sentrux unavailable, and two symlink tests skip because this host forbids symlink creation.
The directory-junction escape case does run, and passes.

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
| `2026-08-07` | `manager` | `PROTECTED_CORE_PATTERNS covers src/scistudio/{core,engine,blocks,workflow,utils}/**, so PR A needs admin-approved:core-change too. Spec §12.1 flagged only base.py (FR-053).` | `Verified independently by running gate_record check --mode pre-commit on the integration branch. Owner authorized the label for PR A (§1.2).` | `N/A` |
| `2026-08-07` | `A1` | `FR-061 requires the divergent-scan-order rationale at BOTH call sites. A1 recorded it thoroughly on the type side; BlockRegistry.scan() got no back-pointer.` | `Not reopened with A1. Reassigned to A3, which owns blocks/registry/**, as prompt item 7a.` | `Verified by AUDIT-A` |
| `2026-08-07` | `A2` | `Edited tests/api/test_packages.py, outside its declared write set. The route tests' _Runtime double only stubbed refresh_block_registry, so the unified entry point broke every package-route test.` | `Accepted. Unavoidable and correctly amended into A2's ledger before the edit. Touching the file also surfaced 8 pre-existing mypy errors (CI only runs mypy over src/), fixed as mechanical annotations.` | `N/A` |
| `2026-08-07` | `A2` | `FR-065 cross-process refresh cannot land in Track A: the standalone mcp-bridge builds registries once and has no invalidation channel, and there is no trigger until the #1996 write endpoint exists.` | `Sequenced into B1 rather than deferred. Recorded in B1's dispatch prompt and in §7.3.` | `B1 (#1996)` |
| `2026-08-07` | `owner` | `Owner delegated all remaining decisions to the manager and went offline mid-dispatch.` | `Manager proceeds autonomously. Every subsequent decision is recorded in this log with its rationale so the owner can audit them on return.` | `N/A` |
| `2026-08-07` | `B3` | `Block-listing types live in frontend/src/types/api.ts, not frontend/src/lib/api/ as the prompt's write set said.` | `Accepted. B3 added BlockOrigin and BlockSummary.origin? there and nowhere else, and declared it in its ledger --include. lib/api/blocks.ts untouched.` | `N/A` |
| `2026-08-07` | `B3` | `Product judgment: FR-037 empty states are suppressed while a search term or chip filter is active.` | `Accepted by the manager. Under a filter, "No blocks of your own yet" asserts something false about a section whose contents were merely filtered away, and #1995's AC requires filtering to behave for the new sections exactly as for existing ones. Unfiltered, both always render. Documented in spec §4.2 and tested both ways.` | `Confirm with AUDIT-B` |
| `2026-08-07` | `B3` | `Product judgment: the custom fallback origin groups into This Project rather than My Library or its own section.` | `Accepted by the manager. An unresolvable file_path is not evidence of cross-project reuse, so filing it under My Library would make a claim the backend never made; This Project renders unconditionally so a custom block can never vanish; and it is where every tier-1 block lands on a backend that has not yet split the tiers, so the palette degrades rather than breaks while B1 is in flight.` | `Confirm with AUDIT-B` |
| `2026-08-07` | `B3` | `Left TODO(#2025) on the ProjectWorkspace types branch, which renders null.` | `Accepted. The TODO cites a tracked open issue and B4 fills it in the same PR, so it is not an untracked deferral. AUDIT-B must confirm it is gone by the time PR B is opened.` | `B4 (#2025)` |
| `2026-08-07` | `manager` | `gate_record python_tests cannot reach green on this Windows host: 9 environmental failures, all reproducing on the unmodified base (POSIX unix sockets, POSIX shell rc, Windows path semantics, TOML backslash escaping, and the #2011 /bin/sh hook family).` | `Accepted for every agent slice. Each agent verified the failures reproduce on its own base commit before proceeding. The evaluator deliberately ignores a --check-na for python_tests because CI owns that job, so the Linux runner on the two delivery PRs is the authoritative evidence. Manager will not treat a local python_tests red as a slice defect without first reproducing it on the base.` | `CI on PR A / PR B` |
| `2026-08-07` | `A-FIX` | `Accepted scope addition: src/scistudio/engine/runners/worker.py — the manager's fix prompt named the wrong file for the worker sys.path injection.` | `Accepted. The worker never calls BlockRegistry.instantiate; without the real call site the P1-1 reproduction still fails. Agent declared it in its ledger and flagged it rather than halting. engine/** is protected core and covered by the owner-authorized label.` | `N/A` |
| `2026-08-07` | `A-FIX` | `Accepted scope addition: tests/api/test_blocks.py, tests/api/test_reload_on_save.py, tests/ai/test_mcp_tools_authoring.py — consequences of the P2-1 route change, since refresh_all_registries builds a fresh BlockRegistry rather than re-scanning the existing object.` | `Accepted. Also fixed 5 pre-existing latent mypy errors the pre-commit hook surfaced once those files entered the changed set.` | `N/A` |
| `2026-08-07` | `A2` | `Accepted scope addition: tests/api/test_packages.py (test double needed the unified entry point).` | `Recorded here to close AUDIT-A P3-4, which noted §9 was missing two accepted scope additions.` | `N/A` |
| `2026-08-07` | `A3` | `Accepted scope addition: tests/blocks/test_registry_package_layout.py (ADR-047 §C9 class inventory plus a pre-existing mypy error the diff exposed).` | `Recorded here to close AUDIT-A P3-4.` | `N/A` |
| `2026-08-07` | `manager` | `AUDIT-A returned two P1s. Track B backend (B1/B2) was unblocked by the owner's condition once the audit returned, but A-FIX and B1 both edit api/routes/blocks.py and ai/agent/mcp/**.` | `Held B1/B2 until A-FIX lands, rather than creating the two-agents-one-file hard fail the dispatch rules forbid.` | `N/A` |
| `2026-08-07` | `manager` | `B3 was dispatched before the owner's "wait for the Track A audit" answer arrived. B3 is frontend-only, cut from origin/main, and shares no file with Track A.` | `Left running. The owner's constraint targeted the backend agents B1/B2, which depend on A1's helper; B3 does not.` | `N/A` |

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
