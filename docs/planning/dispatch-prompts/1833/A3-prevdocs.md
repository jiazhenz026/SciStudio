[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Land the ADR-052 public API contract; you implement the **previewer-author surface**, the **generated-reference doc build** (mkdocstrings/griffe, ADR-052 §7), and the **§14 doc deletion**.
- Task kind: feature
- Persona: implementer
- Issue: #1833 (umbrella tracking #1817)
- Protected branch: main
- Agent branch: feat/1833-adr-052-prevdocs
- Agent worktree: /Users/jiazhenz/scistudio-wt-1833-prevdocs
- Gate record: manager-owned; do NOT touch.

## Required Rules

Read and follow, FROM YOUR WORKTREE:
- `docs/adr/ADR-052.md` (esp. **§7 generated docs + versioning**)
- `docs/specs/adr-052-public-api-surface.md` — AUTHORITATIVE. Sections you implement: **§8 (all of §8.1–§8.5), §7 doc-build references, §14 (the doc-delete + reference-build rows), §16 step 2.**
- `AGENTS.md`, `docs/ai-developer/rules.md`, `docs/ai-developer/personas/implementer.md`

Transcribe the spec literally; the spec wins over intuition.

## Scope

You own ONLY:
- `src/scistudio/previewers/**`
- `mkdocs.yml` (create), `pyproject.toml` (docs deps only), `scripts/docs/**` (doc-gen scripts), `docs/user/reference/**` (generated target)
- `docs/block-development/**` (DELETE the hand-written set)

You must NOT touch:
- `tests/**` (single separate test agent owns ALL tests)
- `src/scistudio/core/**`, `src/scistudio/blocks/**`
- `docs/specs/**`, `docs/adr/**`, `docs/ai-developer/**`, `docs/architecture/**`, `docs/audit/**`, `docs/planning/**`
- `scistudio.ai.agent.mcp.tools_plot/**`

If you need an out-of-scope path, STOP and report.

## Coordination

- core/, blocks/, and tests are edited IN PARALLEL by other agents. Stay in your scope.
- Work only in worktree `/Users/jiazhenz/scistudio-wt-1833-prevdocs` on `feat/1833-adr-052-prevdocs`.
- MUST NOT `pip install -e .`. Use `PYTHONPATH=$PWD/src`. (For docs deps you MAY `pip install` mkdocs/mkdocstrings into the ambient env to test the build, but record them in `pyproject.toml`; never `pip install -e .`.)
- **DO NOT commit/push/PR.** The manager integrates your worktree.
- `scistudio.stability` (`get_stability`, `StabilityInfo`) is already on main — the doc build reads tier/`Since` through it.

## SHARED FREEZE CONTRACT (manager-defined; identical across all agents)

- Canonical public roots (public surface = each root's `__all__`):
  1. `scistudio.core.types`  2. `scistudio.core.meta`  3. `scistudio.blocks.base`
  4. `scistudio.blocks.process`  5. `scistudio.blocks.io`  6. `scistudio.blocks.app`
  7. `scistudio.blocks.code`  8. `scistudio.previewers.models`  9. `scistudio.previewers.data_access`
  (You own the declarations for roots #8 and #9, plus the doc build that renders ALL 9.)
- Decoration rule: EVERY name in a root's `__all__` carries exactly one `@stable(since=...)`/`@provisional(since=...)` matching the spec Tier column. `@internal` is NEVER in `__all__`. Baseline `since="0.3.1"`.
- The doc-build filters to exactly these roots' `__all__` and reads tier/`Since` from `scistudio.stability.get_stability`.

## Work To Do

### previewers source (§8) — whole subsystem PROVISIONAL
1. `previewers/models.py __all__` (§8.1): the 29 symbols today; **DROP the 7 Internal rows** — `PreviewSession`, `RoutingAmbiguityError`, `UnknownPreviewerError`, `UnknownTargetError`, `MissingBundleError`, `InvalidSpecError`, `DuplicatePreviewerIdError`. KEEP the rest (author types + provider protocols + `PreviewError`/`ProviderError`). All kept = **@provisional(since="0.3.1")**.
2. `previewers/data_access.py __all__` (§8.2): KEEP `PreviewDataAccess` (+ its 10 bounded-read methods) and the 10 result dataclasses (`DataFramePage, ArrayPlane, SliceAxis, ArrayTile, SeriesPoints, TableXYPoints, TextChunk, ArtifactInfo, CompositeSlots, CollectionSample`), all **@provisional**. **DROP** `png_data_uri` (Internal) and the `DEFAULT_MAX_*` constants (Internal).
3. `sanitize_svg` (§8.3): already relocated to `previewers/helpers.py` (#1823). Decorate it **@provisional**; ensure it is the public helper home (check `helpers.py __all__`). The core fallback viewers in `fallbacks.py` stay Internal.
4. `previewers/__init__.py` (§8.4): the operational layer (`PreviewerRegistry, PreviewRouter, PreviewSessionManager, PreviewService, build_preview_service, get_preview_service, load_project_previewers`, asset/project constants) is **Internal** — it stays importable (api-runtime imports it) but carries NO stability promise. Reconcile `previewers/__init__.__all__` so it does not advertise these as public author surface; do NOT break existing `from scistudio.previewers import build_preview_service`-style internal imports. The canonical AUTHOR roots are `models` + `data_access` (+ `helpers.sanitize_svg`), NOT the package top level.
5. **Remove/replace `_guess_mime` in previewers** (§7.2/§12, owner option c — non-load-bearing extension→MIME): `data_access.py` `_guess_mime` (used at `resolved_mime = mime_type or self._guess_mime(path)`) and `fallbacks.py` `_PLOT_MIME`. Replace with an authoritative source or `None`. (The blocks copies are another agent's; do not touch blocks.)
6. Docstrings: write/clean a docstring on every public previewer symbol (the reference build reads these).

### Doc build (ADR-052 §7, spec §16 step 2)
7. Wire a **generated API reference from docstrings + stability decorators** using **mkdocstrings + griffe** (ADR-052 §7 names these; `griffe>=1.7` is already a dep — see `src/scistudio/qa/audit/griffe_facts.py` for how the repo already reads the API via griffe). Requirements:
   - Add `mkdocs`, `mkdocstrings[python]` (and griffe if needed) to a **docs** optional-dependency group in `pyproject.toml` (never `pip install -e .`).
   - Create `mkdocs.yml` with the reference nav.
   - Emit **only the public surface** = symbols in the 9 canonical roots' `__all__` (filter out everything else; `internal`/undecorated excluded).
   - Render a **tier badge + `Since`** next to each entry, read from `scistudio.stability.get_stability` via griffe metadata (a small griffe extension or an mkdocstrings option). No hand-maintained table.
   - **Version-stamp single-version** for alpha (stamp the core version; `mike` multi-version is deferred — leave the `TODO(#1817)` already in ADR-052 §7).
   - Target output under `docs/user/reference/**` (generated; not hand-edited — ADR-042 generated-doc rule).
   - Provide a reproducible build the manager/audit can run, e.g. `mkdocs build --strict` and/or a `scripts/docs/build_reference.py`. It MUST succeed cleanly (the audit checks "docs successfully build").
   - NOTE: the core/blocks decorators land in OTHER worktrees; in YOUR worktree only previewers + stability are decorated. So verify the TOOLCHAIN + filter + badge logic run cleanly (build succeeds, badges render for the decorated previewer/stability symbols). The full badged output is validated by the manager at integration once all decorators are merged. State clearly in your report that full-surface badge validation is an integration step.
   - If mkdocstrings integration cannot be made to build green within reason, you MAY fall back to a **griffe-based generation script** that emits the same filtered, badged markdown reference and wire it into the docs build — but document the deviation from ADR-052 §7's mkdocstrings choice for the manager.

### §14 doc deletion
8. **Delete the entire `docs/block-development/**`** hand-written set (guides + examples). The generated reference (step 7) + the spec become the authoritative contract; the rewrite is owner-paced (#1825) — only DELETE here. Update `mkdocs.yml` nav and any docs index/links to drop `block-development` references and point to the generated reference, so the doc build has **no dangling links** and still builds `--strict`. Grep `docs/**` and `mkdocs.yml` for `block-development` references and fix/remove them (within your scope). If a non-`docs/` file (e.g. code, README at repo root) links to `block-development`, report it — do not edit out-of-scope.

## Validation (run in your worktree)

- Import `scistudio.previewers.models`, `scistudio.previewers.data_access`; print `__all__`; assert each has `get_stability` non-None.
- Run the doc build (`mkdocs build --strict` or the script) → it MUST succeed. Capture the output.
- Confirm `docs/block-development/**` is gone and the build has no dangling links.
- `PYTHONPATH=$PWD/src python -m pytest tests/previewers -x -q` (read-only). Tests referencing dropped symbols (`png_data_uri`, the 7 model internals, `DEFAULT_MAX_*`, `_guess_mime`) will fail — EXPECTED; the test agent updates them. **Report those test files; do NOT edit tests.**

## TODO And Deferral Rule

`TODO(#NNN): <reason>`:
- `TODO(#1817)`: `mike` multi-version published docs once >1 core line is supported (ADR-052 §7 already carries this TODO — preserve it).
- `docs/block-development` rewrite is owner-paced `#1825` (delete-only here).

## Output Required

1. **Public surface map** for roots #8 and #9 (+ `sanitize_svg`): `import_path.symbol → kind → tier → since`.
2. Changed/created/deleted file paths (incl. `mkdocs.yml`, `pyproject.toml` docs group, `docs/user/reference/**`, deleted `docs/block-development/**`).
3. The exact doc-build command + its success output (proof the reference builds).
4. Whether you used mkdocstrings (ADR-conformant) or the griffe-script fallback (note deviation).
5. List of EXISTING test files referencing dropped previewer symbols (for the test agent).
6. Any out-of-scope `block-development` link you found (to route).
7. Any blocker.

## Stop Conditions

Stop and report if: you need an out-of-scope file; the doc build cannot be made green; deleting `block-development` would leave the spec/contract with no contract docs (it should not — the generated reference replaces it); a previewer change breaks a contract the spec did not anticipate.
