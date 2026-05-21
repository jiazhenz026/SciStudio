[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciEasy
- Owner request: Add frontend UI for ADR-043 capability selection (dropdown on port editor), OME metadata browser panel on output preview, and lossy-save warning chip on SaveImage nodes.
- Task kind: feature
- Persona: implementer
- Parent tracking issue: #1204
- Umbrella sub-issue: #1296
- Umbrella PR: #1297 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-043/core-blocks-and-imaging
- Agent branch: feat/issue-1296/adr043-a3-frontend
- Agent worktree: `.claude/worktrees/adr-043-a3-frontend/` (provided by manager)
- Manager checklist: `docs/planning/adr-043-package-migration-checklist.md` (edit ONLY rows in §6 marked "A3" and §9 Track A3)
- Spec: `docs/specs/adr-043-package-migration.md` (your work is Phase A3 / FR-012..FR-014)

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- The spec at `docs/specs/adr-043-package-migration.md` — your authoritative scope is Phase A3 in §4.3 and FR-012..FR-014 in §3.
- Existing frontend conventions (see other components under `frontend/src/components/`). Match the existing React + state management + styling patterns; do not introduce a new framework or styling system.

## Scope

You own only:

- `frontend/src/components/PortEditor/CapabilityDropdown.tsx` (create)
- `frontend/src/components/OutputPreview/OMEMetadataPanel.tsx` (create)
- `frontend/src/components/WorkflowEditor/LossySaveWarning.tsx` (create)
- `frontend/src/api/capabilities.ts` (modify — extend existing capability listing client; if file doesn't exist, create it minimally and register in the API export barrel)
- `frontend/src/__tests__/CapabilityDropdown.test.tsx` (create)
- `frontend/src/__tests__/OMEMetadataPanel.test.tsx` (create)
- `frontend/src/__tests__/LossySaveWarning.test.tsx` (create)
- Integration points: PortEditor, OutputPreview, WorkflowEditor (modify ONLY to wire in your new components; do not refactor unrelated logic)
- `CHANGELOG.md` (Unreleased entry only)
- Your own gate record at `.workflow/records/1296-a3-frontend.json`
- Your own checklist rows.

You must not touch:

- Any backend code (`src/scieasy/**`, `packages/**`).
- Other frontend components beyond the integration points listed above.
- Other agents' branches/worktrees.
- The spec doc.

If you need an out-of-scope path, stop and report back.

## Coordination

- A1 (core IO) and A2 (imaging) run in parallel. Your capability dropdown reads from the backend capability API — the schema is already in place (ADR-043 §11.4 BlockRegistry.list_format_capabilities is committed). DO NOT wait for A2 to merge — the API contract is stable.
- The A2 agent's work adds new imaging capabilities; your dropdown will pick them up automatically via the API.
- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .` (frontend doesn't use it; just don't pollute Python env).
- Open your PR targeting `track/adr-043/core-blocks-and-imaging`.

## TODO And Deferral Rule

Same as other phases. Use `TODO(#NNN): ...` with tracked reference.

Known deferred items:

- N/A.

## Work To Do (matches spec §4.3 Phase A3, T-020..T-024)

1. **T-020:** Extend `frontend/src/api/capabilities.ts`:
   - `listCapabilities(direction, type, extension?)` returning `FormatCapability[]`.
   - `getOMEMetadata(objectId)` returning the OME object for a workflow output.
   - Wire in the existing API base URL + auth. Mirror existing client patterns.

2. **T-021:** Create `CapabilityDropdown.tsx` per spec FR-012:
   - Props: `direction: "load"|"save"`, `dataType: string`, `extension: string`, `value: string|null` (capability_id), `onChange: (capability_id: string) => void`.
   - On mount, fetch capabilities matching `(direction, dataType, extension)`.
   - Render options with `label`, `format_id`, and a metadata-fidelity badge ("pixel_only" | "typed_meta" | "format_specific" | "lossless").
   - If exactly one match, auto-select; otherwise require user pick.
   - Integrate into the existing PortEditor (find where port type+extension are configured; add the dropdown below extension).

3. **T-022:** Create `OMEMetadataPanel.tsx` per spec FR-013:
   - Props: `ome: OME | null`.
   - Render OME as a navigable tree: images → pixels (physical_size_x/y/z, size_x/y/z), channels (name, color, emission_wavelength), annotations (StructuredAnnotations).
   - Copy-to-clipboard button next to each leaf field.
   - "OME metadata" button on the output preview that opens this panel.

4. **T-023:** Create `LossySaveWarning.tsx` per spec FR-014:
   - Props: `sourceOmeFields: string[]`, `targetCapabilityFidelity: MetadataFidelity`.
   - Compute the set of fields in `sourceOmeFields` not declared in `targetCapabilityFidelity.format_metadata_writes` or `typed_meta_writes`.
   - Render as a warning chip on the SaveImage node listing the dropped fields, with tooltip explaining "These OME fields will be dropped when saving in this format".

5. **T-024:** Mandatory Chrome smoke test (per the user-level discipline rule for any UI dispatch):
   - Use Chrome MCP or Playwright (whichever this repo uses — check existing UI smoke tests under `frontend/src/__tests__/` or `frontend/e2e/`).
   - Navigate to a workflow with a port that has multiple matching capabilities; verify the dropdown shows ≥2 options.
   - Click the OME metadata button on a sample output; verify the panel opens and renders at least one field.
   - Verify lossy-save warning appears on a SaveImage node when source OME has fields the target capability cannot persist.
   - Commit the smoke test script + evidence (screenshot or log file path).

6. **T-024.5:** CHANGELOG entry `[#1296]` under `## [Unreleased]` → `### Added`.

## Required Tests And Checks

- Unit tests via `npm test` / `vitest run` (whichever this repo uses — match existing test script).
- Type check: `npm run typecheck` or `tsc --noEmit`.
- Lint: `npm run lint` or equivalent eslint config.
- Mandatory Chrome smoke (see T-024).
- DO NOT use `npm run dev` for verification (per saved hygiene rule — stale dev server hygiene); use `vitest run` and the Chrome smoke harness.
- `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` — record. Pre-existing debt is owner-acknowledged.
- Sentrux: skipped with rationale if CLI unavailable.

## Gate Record Stages You Must Execute

Same pattern. Your slug is `a3-frontend`. Your record path is `.workflow/records/1296-a3-frontend.json`.

## Output Required

Changed paths, tests/checks results (especially Chrome smoke evidence path), checklist rows, PR URL, gate record path, Codex auto-review reconciliation.

## Stop Conditions

Same as other A-phase agents. Additional:

- If the existing frontend codebase has no obvious component for PortEditor / OutputPreview / WorkflowEditor wiring, stop and report — DO NOT invent new integration points. Manager will help locate.
- Chrome smoke test failure is a hard stop; report at the smoke-test step.

## Codex Auto-Review Reconciliation

Same as other phases. After PR opens and CI runs, reconcile each Codex auto-review finding on the record.
