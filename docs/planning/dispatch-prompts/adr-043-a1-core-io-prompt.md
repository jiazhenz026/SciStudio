[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciEasy
- Owner request: Migrate in-tree `LoadData` / `SaveData` core IO blocks to ADR-043 explicit `FormatCapability` declarations; delete legacy `supported_extensions` ClassVar.
- Task kind: refactor
- Persona: implementer
- Parent tracking issue: #1204
- Umbrella sub-issue: #1296
- Umbrella PR: #1297 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-043/core-blocks-and-imaging
- Agent branch: feat/issue-1296/adr043-a1-core-io
- Agent worktree: `.claude/worktrees/adr-043-a1-core-io/` (provided by manager)
- Manager checklist: `docs/planning/adr-043-package-migration-checklist.md` (edit ONLY row in §6 Dispatch Matrix marked "A1" and §7 Track A1 rows)
- Spec: `docs/specs/adr-043-package-migration.md` (your work is Phase A1 / FR-001..FR-003, FR-015, FR-016)

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md (refactor variant — similar gate flow)
- docs/ai-developer/personas/implementer.md
- The spec at `docs/specs/adr-043-package-migration.md` — your authoritative scope is Phase A1 in §4.3 and FR-001..FR-003 in §3.

## Scope

You own only:

- `src/scieasy/blocks/io/loaders/load_data.py`
- `src/scieasy/blocks/io/savers/save_data.py`
- `tests/blocks/io/test_load_data_capabilities.py` (create)
- `tests/blocks/io/test_save_data_capabilities.py` (create)
- `CHANGELOG.md` (Unreleased entry only)
- Your own gate record at `.workflow/records/<issue-or-derived-id>-a1-core-io.json`
- Your own checklist rows in `docs/planning/adr-043-package-migration-checklist.md` (only the rows marked A1 in §6 + the rows in §7 — DO NOT edit other tracks' rows).

You must not touch:

- `src/scieasy/blocks/io/io_block.py` — base class; `supported_extensions` ClassVar stays for unmigrated third-party packages (FR-003 explicitly scopes the delete to LoadData/SaveData only).
- `src/scieasy/blocks/io/capabilities.py`, `simple_io.py`, `materialisation.py` — already migrated infrastructure.
- `src/scieasy/blocks/registry.py` — already capability-aware.
- `src/scieasy/engine/**`, `src/scieasy/workflow/validator.py` — out of scope.
- `packages/scieasy-blocks-imaging/**`, `packages/scieasy-blocks-srs/**`, `packages/scieasy-blocks-lcms/**` — other agents.
- `frontend/src/**` — A3 agent.
- The spec doc, the manager checklist (except your own rows), other agents' branches/worktrees.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone. A2 (imaging) and A3 (frontend) are running in parallel — independent worktrees, independent file sets.
- MUST work only on your assigned branch `feat/issue-1296/adr043-a1-core-io`.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope (no preemptive imaging fixes, no engine touch).
- Open your PR targeting `track/adr-043/core-blocks-and-imaging` (the umbrella), NOT `main`.
- MUST NOT merge any PR.
- Edit ONLY your checklist rows.
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo:
```
# TODO(#NNN): <reason>. Out of scope per <ADR/spec/PR/owner decision>. Followup: <issue or tracking ref>.
```
Do not leave hidden V1 / MVP / "later" work. Use parent tracker #1204 or sub-issue #1296 if the deferred follow-up is the umbrella's responsibility; otherwise open a new tracked issue.

Known deferred items:

- N/A for Phase A1 scope.

## Work To Do (matches spec §4.3 Phase A1, T-001..T-006)

1. **T-001:** Declare `LoadData.format_capabilities: ClassVar[tuple[FormatCapability, ...]]` covering all six core DataObject types × supported extensions per `LoadData.supported_extensions`. Capability ID convention: `core.{lower(type)}.{format_id}.load` (e.g. `core.dataframe.csv.load`). Every record `is_synthesized=False`, `metadata_fidelity=MetadataFidelity(level="pixel_only")`, `is_default=True` for the single-handler case. Pickle (.pkl/.pickle) carries `notes="requires allow_pickle=True"`.

2. **T-002:** Declare `SaveData.format_capabilities` mirror with `direction="save"`. Capability ID convention: `core.{lower(type)}.{format_id}.save`. Pair each load+save with `roundtrip_group=core.{type}.{format}`.

3. **T-003:** Delete the `supported_extensions: ClassVar[dict[str, str]]` from both `LoadData` and `SaveData` class bodies. Rewire `_resolve_format(path, block)` in `load_data.py` and `_resolve_save_format(path)` in `save_data.py` to derive the legacy extension→format_id mapping from `cls.format_capabilities` (or via `registry.list_format_capabilities(...)`). Update internal `_load_*` / `_save_*` callers accordingly.

4. **T-004:** Update user-facing error messages that previously enumerated `sorted(LoadData.supported_extensions.keys())` / `sorted(SaveData.supported_extensions.keys())` to derive the supported set from `format_capabilities`.

5. **T-005:** Create `tests/blocks/io/test_load_data_capabilities.py` and `tests/blocks/io/test_save_data_capabilities.py`. Cover:
   - capability count (one per `(type, format_id)` pair).
   - capability IDs match the convention.
   - `is_synthesized=False` on every record.
   - `is_default=True` set correctly.
   - `BlockRegistry.find_loader_capability` / `find_saver_capability` returns the explicit record (not synthesized) for each declared extension.
   - Ambiguity error if a hypothetical extension matches multiple records (you may parametrize a registry-level test that mocks two LoadData-like blocks with the same `(type, ext)`).
   - Pickle gating still works at runtime (`allow_pickle=True` required for `.pkl`).
   - Backward-compat: existing single-path load + save still works for at least DataFrame+CSV, Array+npy, Text+md round-trip.

6. **T-006:** Add a `[#1296]`-prefixed CHANGELOG entry under `## [Unreleased]` → `### Added` describing this slice.

## Required Tests And Checks

- `pytest tests/blocks/io/test_load_data_capabilities.py tests/blocks/io/test_save_data_capabilities.py --timeout=60` — must pass.
- `pytest tests/blocks/io/` targeted for any tests that touch LoadData/SaveData — verify no pre-existing regression.
- `ruff check src/scieasy/blocks/io/loaders/ src/scieasy/blocks/io/savers/ tests/blocks/io/`
- `ruff format --check src/scieasy/blocks/io/loaders/ src/scieasy/blocks/io/savers/ tests/blocks/io/`
- `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` — record evidence path in your gate record. Pre-existing repo-wide findings are owner-acknowledged debt; if your changes add NEW findings, fix them.
- Sentrux: if Sentrux MCP/CLI is unavailable in your worktree, record `--status skipped` with rationale "Sentrux CLI unavailable; tests + ruff + full_audit cover the change surface and changes are scoped to canonical IO block declarations".

## Gate Record Stages You Must Execute

Use `python -m scieasy.qa.governance.gate_record` with your own record path.

1. `start --task-kind refactor --issue 1296 --slug a1-core-io --branch feat/issue-1296/adr043-a1-core-io --owner-directive "Phase A1: migrate LoadData/SaveData to explicit ADR-043 FormatCapability per spec FR-001..FR-003" --include <each file> --record-path .workflow/records/1296-a1-core-io.json`
2. `plan --planned-file <each> --required-check ruff --required-check format --required-check pytest --required-check full_audit --docs "CHANGELOG.md"`
3. `docs --updated CHANGELOG.md --na "docs:no docs-doc changes; spec already covers contract"`
4. `check` once per check after running.
5. `sentrux --status skipped --evidence "<rationale>"` (or pass if available).
6. After commit: `finalize --commit-sha <sha> --pr-url <url> --pr-number <n> --body-closes-issue "#1296"`.

## Output Required

Before reporting done, provide:

- Changed file paths (absolute or repo-relative).
- Tests/checks run and results (commands + pass/fail).
- Checklist rows updated (link to the diff in the manager checklist).
- PR number + URL (targeting `track/adr-043/core-blocks-and-imaging`).
- Gate record path with all six stages `done`.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR-043, spec, or gate record.
- CI or local checks fail for reasons you cannot diagnose within reasonable effort.
- Another agent's work conflicts with yours on a shared file (should not happen given the file partitioning, but report immediately if it does).
- You cannot add or update the required tests.

## Codex Auto-Review Reconciliation

After your PR opens and CI runs, Codex auto-review will fire. Read every Codex auto-review comment and explicitly accept, defer (with tracked issue), or reject each one on the record before reporting done. Cap reconciliation at one round per ADR-042 norms.
