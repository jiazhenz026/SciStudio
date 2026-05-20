[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciEasy
- Persona: audit_reviewer
- Audit mode: **no-context**
- Audit branch: `feat/issue-1296/adr043-c1-audit`
- Audit worktree: `/c/Users/jiazh/Desktop/workspace/SciEasy/.claude/worktrees/adr-043-c1-audit`
- Allowed audit surfaces:
  - `docs/adr/ADR-043.md`
  - `docs/adr/ADR-041.md`
  - `docs/specs/adr-043-package-migration.md`
  - `docs/ai-developer/specific_rules/document-standards.md` (for SpecKit/ADR-042 §3.4 structural checks on the spec)
  - `src/scieasy/blocks/io/loaders/load_data.py`
  - `src/scieasy/blocks/io/savers/save_data.py`
  - `src/scieasy/blocks/io/io_block.py`
  - `src/scieasy/blocks/io/capabilities.py`
  - `src/scieasy/blocks/io/simple_io.py`
  - `src/scieasy/blocks/registry.py`
  - `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/types.py`
  - `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/**`
  - `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/{math,morphology,preprocess,projection,registration,segmentation,measurement}/**`
  - `packages/scieasy-blocks-imaging/pyproject.toml`
  - `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/**`
  - `frontend/src/components/PortEditor/CapabilityDropdown.tsx`
  - `frontend/src/components/OutputPreview/OMEMetadataPanel.tsx`
  - `frontend/src/components/WorkflowEditor/LossySaveWarning.tsx`
  - `frontend/src/api/capabilities.ts`
  - `tests/blocks/io/test_load_data_capabilities.py`
  - `tests/blocks/io/test_save_data_capabilities.py`
  - `packages/scieasy-blocks-imaging/tests/test_format_capabilities.py`
  - `packages/scieasy-blocks-imaging/tests/test_image_meta_ome.py`
  - `packages/scieasy-blocks-imaging/tests/test_bioformats_handler.py`
  - `packages/scieasy-blocks-imaging/tests/test_processblock_meta_propagation.py`
  - `packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py`
  - `frontend/src/__tests__/CapabilityDropdown.test.tsx`
  - `frontend/src/__tests__/OMEMetadataPanel.test.tsx`
  - `frontend/src/__tests__/LossySaveWarning.test.tsx`
  - `docs/audit/adr-043-imaging-propagation-audit.md`
  - `docs/audit/adr-043-srs-propagation-audit.md`
- Audit report path: `docs/audit/2026-05-20-adr-043-package-migration-no-context.md`

## Context Limits

You must NOT read or use:

- The current GitHub issue (do not call `gh issue view`).
- The current PR descriptions or PR comments (do not call `gh pr view <umbrella or sub-PRs>`).
- Manager checklist files: `docs/planning/adr-043-package-migration-checklist.md` is OFF LIMITS.
- Other dispatch prompts in `docs/planning/dispatch-prompts/adr-043-a*-*.md`, `adr-043-b*-*.md`, `adr-043-d*-*.md` — OFF LIMITS.
- Commit messages of recent merges (do not `git log -p` the umbrella branch).
- Chat summaries or any prior agent's report content.

You may read:

- The allowed audit surfaces listed above.
- Anything else under `docs/adr/`, `docs/architecture/`, `docs/block-development/` reachable via cross-references from the spec or governing ADRs.
- Generated facts at `docs/facts/generated.yaml` if present (committed generated artifacts only).
- Tool output from commands you run yourself.

## Required Reading

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs (ADR-041, ADR-043) and the spec at `docs/specs/adr-043-package-migration.md`.

## Audit Goal

Independently verify the integrated ADR-043 package-migration work landed on this branch against the spec + governing ADRs. Do NOT assume what implementation agents intended; check what the code, tests, and committed audits actually say.

The audit verifies **all 17 functional requirements (FR-001..FR-017) and all 6 measurable outcomes (SC-001..SC-006)** declared in `docs/specs/adr-043-package-migration.md` §3 + §5. For each:

- Cite the spec line(s) describing the requirement.
- Cite the code/test/doc evidence that satisfies it, OR cite the gap.
- Classify severity (P0 hard fail / P1 must-fix / P2 should-fix / P3 nit).

Additionally check ADR-043 §9 package validity rules:

- Capability IDs are package-qualified and globally stable.
- Extensions are normalized lowercase with leading dots.
- Defaults do not conflict within `(direction, type, extension)` groups.
- Round-trip groups marked round-trip have BOTH load and save.
- Metadata fidelity declarations reference fields that exist on the declared type's `Meta` model when `level=typed_meta` or stronger.
- `is_synthesized=False` on every explicit FormatCapability record declared on LoadData/SaveData/LoadImage/SaveImage.

And ADR-043 §6 ambiguity resolution:

- No `(direction, type, extension)` triple matches multiple `is_default=True` capabilities across packages.

And ADR-041 + spec FR-009 propagation contract:

- Mode A: same-type shape-preserving blocks set `meta=source.meta` (transparent propagation).
- Mode B: shape-changing transform helpers consume and transform `ome` field (resize / projection / split helpers update `ome.images[0].pixels.*` accordingly).
- Mode C: cross-type cuts must propagate `ome` when output shape is spatially aligned with input (e.g. Image→Label segmentation); legitimate-drop allowed for dimensionality-reduced outputs (PCA score, abundance maps to DataFrame) but MUST be documented in a committed audit report.

## Coordination

- MUST work only on your assigned audit branch and worktree.
- MUST NOT use `pip install -e .`.
- MUST NOT merge any PR.
- MUST NOT edit implementation files (this audit is read-only against the code; you can ONLY edit your own audit report and your own gate record).
- MUST NOT edit the manager checklist.
- MUST write the audit report to `docs/audit/2026-05-20-adr-043-package-migration-no-context.md`.
- The audit report file must be committed in your audit PR targeting `track/adr-043/core-blocks-and-imaging`.

## Checks

Run or verify these commands and record evidence in the audit report:

- `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` — record path; classify findings into "this-PR's-files" vs "pre-existing-repo-debt".
- `ruff check src/scieasy/blocks/io/ packages/scieasy-blocks-imaging/ packages/scieasy-blocks-srs/`
- `ruff format --check src/scieasy/blocks/io/ packages/scieasy-blocks-imaging/ packages/scieasy-blocks-srs/`
- `pytest tests/blocks/io/test_load_data_capabilities.py tests/blocks/io/test_save_data_capabilities.py packages/scieasy-blocks-imaging/tests/test_format_capabilities.py packages/scieasy-blocks-imaging/tests/test_image_meta_ome.py packages/scieasy-blocks-imaging/tests/test_processblock_meta_propagation.py packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py --timeout=60`
- ADR-043 §9 package validity scan: implement as a manual code+test cross-reference per the rules listed under "Audit Goal" above.
- Sentrux: skipped with rationale if CLI/MCP unavailable (consistent with other phases).

## Gate Record Stages You Must Execute

Use `python -m scieasy.qa.governance.gate_record` with your own record path at `.workflow/records/1296-c1-audit.json`. Run the full sequence:

1. `start --task-kind maintenance --issue 1296 --slug c1-audit --branch feat/issue-1296/adr043-c1-audit --owner-directive "Phase C1 no-context audit of ADR-043 package migration against spec FR-001..FR-017 and SC-001..SC-006" --include docs/audit/2026-05-20-adr-043-package-migration-no-context.md --include .workflow/records/1296-c1-audit.json --record-path .workflow/records/1296-c1-audit.json`
2. `plan` — declare planned files (just the audit report and gate record).
3. `docs` — record audit report as the doc landing.
4. `check` for each command above.
5. `sentrux --status skipped` with rationale.
6. After commit + PR open: `finalize` with commit SHA + PR URL + closes `#1296`.

## Output Required

- Audit report path: `docs/audit/2026-05-20-adr-043-package-migration-no-context.md` (committed).
- Audit PR URL (targeting umbrella `track/adr-043/core-blocks-and-imaging`).
- Findings ordered by severity (P0 / P1 / P2 / P3).
- Evidence per finding (file:line, test name, tool output).
- Recommendation: **pass** / **pass-with-fixes** / **block**.
- Codex auto-review reconciliation summary (cap 5 min wait after CI green; if no review fires, record that).

## Stop Conditions

Stop and report back if:

- You are forced to read manager context (issue, checklist, PR descriptions) to verify a requirement — the requirement is then under-specified in code/docs.
- The audit requires editing implementation code.
- A spec requirement (FR-001..FR-017 or SC-001..SC-006) cannot be checked against any committed artifact (code / tests / committed audit).
