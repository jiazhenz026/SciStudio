[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issues: #1995, #1996, #2023, #2024, #2025, #2026
- Issue URLs: https://github.com/jiazhenz026/SciStudio/issues/1995 (and 1996, 2023, 2024, 2025, 2026)
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs, with no deferred scope; this is PR B, the personal tool library feature.
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Audited branch: feat/1995-adr-053-personal-tool-library (integrated B1 – B5, stacked on the Track A branch)
- Audit branch: audit/adr-053-spec1-track-b
- Audit worktree: C:/Users/jiazh/workspace/SciStudio-wt-audit-b
- Gate record: create with `gate_record init --slug adr-053-spec1-track-b-audit`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md
- Commits to audit: every commit on `feat/1995-adr-053-personal-tool-library` since `fix/2020-adr-053-registry-runtime-defects`. Track A is audited separately by AUDIT-A; do not re-audit it.
- Audit report path: docs/audit/2026-08-07-adr-053-spec1-track-b.md

## Required Reading

- The six GitHub issues above and all owner instructions in them.
- The manager checklist, especially §1.2 owner decisions, §6.2 frozen contracts, and §8.
- The five dispatch prompts under `docs/planning/adr-053-spec1-dispatch-prompts/` (b1–b5).
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/specs/adr-053-personal-tool-library.md — §3, §4, §6, §7, §8, §9, §10.1, §10.2, §11, §14
- docs/specs/frontend-block-palette.md
- docs/adr/ADR-053.md §3

## Audit Goal

Verify the claimed work against the issues, the checklist, the governing spec, the code,
the tests, gate evidence, and CI.

Report findings first, ordered by severity:

- **P1**: blocks merge or breaks contract.
- **P2**: should fix before completion.
- **P3**: improvement or follow-up.

Spec §11 is a test plan with one row per obligation. **Walk every row** and record for each
whether a test exists, what it asserts, and whether it actually proves the FR. A test that
exists but asserts nothing meaningful is a P2 finding, not a pass.

## Scope

Audit these claims:

**Origin tiers and the anti-drift contract**
- FR-001/FR-002 — a `tier1` block resolves to `user` or `project` by path; unresolvable paths
  fall back to `custom` and existing `custom` consumers still work. Verify the Windows
  differing-drive case, not only POSIX symlinks.
- **FR-003 — one shared resolver.** This is the highest-value anti-drift check in the track.
  Grep for a second path comparison on the type side. Two resolvers is a P1.
- FR-004/FR-005 — both listing responses carry the resolved origin, with the frozen
  vocabularies (`builtin|user|project|package|custom` for blocks, `core|user|project|package|custom`
  for types).

**The write path — spec §14 calls this the highest-risk surface in the spec**
- FR-006 — one endpoint serves both targets, selected **explicitly by the caller, never
  inferred from file content**.
- FR-007 — the constraint is the **inverse** of the project endpoint's, not a relaxation.
  Traversal and symlink escapes 403 with a matching error shape. Verify resolved real paths
  are compared, not string prefixes.
- FR-008 — no silent overwrite; collision reported; overwrite requires explicit opt-in.
- **FR-009 — `PUT /api/projects/{project_id}/file` still rejects paths outside the project
  root.** A second door was added; the first must not have widened. Test this directly.
- FR-010/FR-065 — registry refresh after write, reaching every process holding a registry.
- FR-011 — the MCP promotion tool exists and its semantics match the frontend action.

**Promotion**
- FR-017 — copy, never move; the originating project still works.
- FR-018 — collision prompts with overwrite and rename.
- **FR-019 — the condition is the resolved origin `project`, not the tier-1 classification.**
  A user-library block is also tier-1 with a resolvable `file_path`; if the broader test was
  used, promotion is offered for an already-promoted item. Verify the action is **hidden,
  not disabled**, for built-in, packaged, and already-in-library items.
- FR-020 — success confirms inline and reveals the item in `My Library`.
- FR-021 – FR-024 — cascade uses static AST parsing resolved against the type registry;
  declining still promotes the block **with a warning**; second-level dependencies are
  **reported**, not silently missed.
- FR-025 — E1, E2, E3, E5 share one implementation. Four copies is the drift the spec exists
  to prevent; grep for duplicates.

**Types API and declared colour**
- FR-026/FR-027 — the types endpoint exists under `routes/types.py` and is **independent of
  the block list response**; the Data types tab does not need a blocks request.
- FR-028 — the type template mirrors the block template's shape and includes the colour
  attributes as commented-out lines.
- FR-049/FR-050 — `DataObject` colour attributes exist and the registry collects them.
  **Verify the core change is minimal and additive** — two optional attributes defaulting to
  `None`. Anything more on a protected core path is a P1.
- FR-051 — precedence declared > `typeColorMap` > `hashTypeName`, identical for palette tiles
  and canvas ports. **Verify an undeclared type's colour is unchanged from before this PR**;
  that is the spec's own stated blast-radius bound.
- FR-052 — a malformed hex warns and falls through without breaking palette or canvas.
- FR-054 – FR-056 — load and save extensions reported **separately**; a type with no
  capability reports **empty lists**, rendered as an explicit "no file formats registered".
- **FR-066 — `TypeHierarchyEntry.ui_ring_color` must be left dead, not revived.** Spec §7.1
  rejects reviving it. If someone populated it, that is a P1 contract violation.
- FR-067 — ports render with the fallback before type data arrives and **do not flash or
  re-layout** when it lands. Spec §14 names a wrong fallback as more visible than the drift
  it prevents.

**Palette and Data types tab**
- FR-034 – FR-037 — tab renamed `Blocks`; `My Library` and `This Project` sections; order is
  `Data I/O` (pinned) → `Built-in` → `My Library` → `This Project` → packages A→Z; **both
  tier sections render when empty** with a one-line teaching statement. The empty states are
  load-bearing per ADR-053 §3 and spec §9.1 — a missing empty state is P1, not cosmetic.
- FR-038 — grouping is by **origin tier first, package second**. Verify the grouping
  dimension actually changed rather than sections being bolted onto package grouping.
- FR-039 – FR-043 — `Data types` tab between `Blocks` and `Project`; mirrors the Blocks
  structure; tiles carry solid fill plus ring through the FR-051 precedence; the popover
  carries name, parent (with the core base when it differs), description, separately-reported
  extensions, origin, and the promotion action.
- FR-044 – FR-046 — popover interactive, survives the tile→popover gap, **does not break
  dragging** (spec §11 requires a test), and **one popover implementation serves both
  surfaces**.
- FR-047 / §10.1 / §10.2 — the listed helpers are genuinely shared and `buildSections<T>`
  serves both surfaces without per-surface special-casing; the block-only concepts
  (`derivePackage`, `isIoSource`/`isIoSink`/`isDataIoBlock`, `CATEGORY_KEYS`, `portSignature`)
  were **not** generalised.

**New-file flows**
- FR-029 – FR-033 — the destination choice exists; each destination routes to the right
  endpoint and probes the right place; New data type mirrors New custom block; and the two
  flows **share** prompt, validation, probe, write-dispatch, and open-file steps.

**Governance**
- `admin-approved:core-change` is required on PR B (FR-053) and CI verifies actor provenance.
  Verify the ledger records the label and that the protected-core diff is confined to
  `src/scistudio/core/types/base.py`.
- **Scope drift** — each agent stayed inside its declared write set; the gate ledger was
  amended where it did not.
- **Deferral drift** — the owner directive is complete delivery. Any `TODO(#NNN)` from this
  track is a finding unless owner authorization is recorded in checklist §9. Check
  specifically that cascade was not silently reduced to warn-only (spec §15 records it as a
  required owner assumption) and that the tips strip (#1997) was not built.
- **Test-change requirement** — implementation work added or modified test files.
- **Ledger sanitization** — no absolute local paths, usernames, temp dirs, virtualenv paths,
  or raw transcripts in committed ledger events.

Audit these files or surfaces: the full diff of the audited branch against the Track A
branch, plus `docs/specs/frontend-block-palette.md` and the five agents' gate ledgers under
`.workflow/records/`.

Do not write feature code. MUST write the audit report to the repository file named above.
Only write the audit report and your assigned checklist audit rows (§8.4).

## Coordination

- MUST work only on your assigned audit branch, in your assigned audit worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- MUST NOT merge any PR.
- MUST NOT fix implementation code unless the manager explicitly changes your role to fix agent.
- Edit only the §8.4 checklist audit rows.
- Windows note: a post-commit hook fails with `ExecutableNotFoundError: Executable /bin/sh not found` (known issue #2011). The commit still lands; verify with `git log`.

## Checks

Run or verify:

- `PYTHONPATH=./src python -m pytest tests -q`
- `cd frontend && npm run test`, `npx tsc --noEmit`, `npm run lint`, `npm run build`
- A frontend smoke check of the palette: the two tier sections render when empty, the Data
  types tab is present, the popover is clickable, and dragging still works. If you cannot run
  a browser, say so explicitly rather than claiming a smoke check you did not perform.
- The repository's import-linter command.
- Sentrux MCP if available; otherwise `sentrux scan .` / `sentrux check .`, or record unavailability explicitly.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base fix/2020-adr-053-registry-runtime-defects --head HEAD --pr-body-file .workflow/local/pr-body.md --admin-label admin-approved:core-change`

## Output Required

- Audit report path.
- Commit that contains the audit report file.
- A row-by-row walk of spec §11's test plan, with a verdict per row.
- Findings ordered by severity, each with evidence from code, tests, or tool output.
- Checklist drift, scope drift, and missing tests/docs/gate evidence, if any.
- Whether the frontend smoke check was actually performed.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- You need to change implementation code.
- Required evidence is unavailable.
- The audit scope conflicts with AGENTS.md, ADR-053, the spec, or a gate record.
