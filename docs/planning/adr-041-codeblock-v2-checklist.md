# ADR-041 CodeBlock v2 Implementation Checklist

> Mandatory tracking doc. Every agent edits the rows it owns and only those rows.
> Drift is a protocol violation. The manager sweeps after every phase.

## References

- ADR: [ADR-041](../adr/ADR-041.md)
- Planning spec: [ADR-041 CodeBlock v2](../specs/adr-041-codeblock-v2.md)
- Documentation/audit standard: [ADR-042](../adr/ADR-042.md)
- Umbrella issue: [#1222](https://github.com/zjzcpj/SciEasy/issues/1222)
- Umbrella branch: `track/adr-041/codeblock-v2`
- Baseline dependency: PR [#1217](https://github.com/zjzcpj/SciEasy/pull/1217)

## Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Owner labels map to GitHub issues and agent roles.
- When a box is ticked, append a one-line note with PR, commit, audit report, or test evidence.
- Worker PRs target `track/adr-041/codeblock-v2`, not `main`.
- The umbrella PR targets `main` and remains `[DO NOT MERGE]` until child PRs land and the ADR-042 audit passes.

## Manager Discipline

1. Every implementation agent uses an independent git worktree.
2. Every worker branch starts from `origin/track/adr-041/codeblock-v2`.
3. Every worker PR includes `Closes #<track-issue>` and targets `track/adr-041/codeblock-v2`.
4. Agents are not alone in the codebase: they must not revert edits made by others and must adjust to changes already present on the tracking branch.
5. Tests use focused commands with timeouts. Do not run long-lived dev servers for backend-only work.
6. ADR-042-governed docs edited by this cascade must preserve required frontmatter and first-section structure.
7. Any code-level deferred work requires an in-repo `TODO(#NNN)` with a concrete tracking issue and ADR/spec reference.
8. CI must be green before an agent reports a track as done.

## Conflict Guardrails

ADR-043 is being implemented concurrently by another manager. ADR-041 agents must avoid these files unless the manager opens a coordination issue and updates this checklist first:

- `src/scieasy/blocks/io/capabilities.py`
- `src/scieasy/blocks/io/simple_io.py`
- `src/scieasy/blocks/io/io_block.py`
- `src/scieasy/blocks/registry.py`
- `src/scieasy/engine/materialisation.py`
- `src/scieasy/blocks/app/app_block.py`
- `src/scieasy/blocks/app/bridge.py`
- `packages/scieasy-blocks-*`
- `docs/adr/ADR-043.md`
- `docs/specs/adr-043-*`

## Phase 0 - Manager Preflight

- [x] Independent manager worktree created at `C:\Users\jiazh\Desktop\workspace\SciEasy-adr041-manager`.
- [x] Tracking branch created: `track/adr-041/codeblock-v2`.
- [x] Umbrella issue opened: [#1222](https://github.com/zjzcpj/SciEasy/issues/1222).
- [x] Gate workflow started: `20260519-181608-adr-041-codeblock-v2-implementation-casc`.
- [x] ADR-043 active worktrees identified and conflict files excluded from first-wave scope.
- [x] Umbrella PR opened as `[DO NOT MERGE]` -> [PR #1229](https://github.com/zjzcpj/SciEasy/pull/1229).
- [x] Tracking branch pushed -> `origin/track/adr-041/codeblock-v2`.
- [x] Shared interpreter family literals widened for C2-C5 runtime backends -> issue [#1242](https://github.com/zjzcpj/SciEasy/issues/1242).

## Phase 1 - First-Wave Backend Support Modules

### Track A - Config, Interpreter, Provenance (Owner: I41a / #1223)

Scope:

- `src/scieasy/blocks/code/config.py`
- `src/scieasy/blocks/code/interpreters.py`
- `src/scieasy/blocks/code/provenance.py`
- `tests/blocks/code/test_codeblock_v2_config.py`
- `tests/blocks/code/test_codeblock_interpreters.py`
- `tests/blocks/code/test_codeblock_provenance.py`

Tasks:

- [x] Define CodeBlock v2 config models for script path, inline code migration diagnostics, declared inputs, declared outputs, working directory, interpreter selection, environment variables, timeout, and exchange-directory policy. Evidence: commit `2f72ae3b`.
- [x] Validate path-like fields without assuming the project fits in memory or that paths are local-only forever. Evidence: commit `2f72ae3b`; focused config tests cover missing and outside-project scripts.
- [x] Implement Python interpreter resolution for `auto`, explicit executable path, and active environment fallback. Evidence: commit `2f72ae3b`; focused interpreter tests cover auto, existing, missing, and unsupported extension paths.
- [x] Implement provenance helpers that capture script path, content hash when available, interpreter identity, command argv, environment delta, and execution timestamps. Evidence: commit `2f72ae3b`; focused provenance tests cover hash/git state and stable payload shape.
- [x] Add tests for valid config, invalid mixed inline/script config, missing script, interpreter resolution success/failure, and provenance payload stability. Evidence: `python -m pytest tests/blocks/code/test_codeblock_v2_config.py tests/blocks/code/test_codeblock_interpreters.py tests/blocks/code/test_codeblock_provenance.py --timeout=30 --no-cov` passed with 15 tests.
- [x] Avoid `src/scieasy/blocks/code/code_block.py` in this track. Evidence: commit `2f72ae3b` touches only Track A support modules and tests.

Exit Criteria:

- [x] Track A PR targets `track/adr-041/codeblock-v2`. Evidence: [PR #1231](https://github.com/zjzcpj/SciEasy/pull/1231).
- [x] Track A CI is green. Evidence: PR #1231 checks passed on 2026-05-19.
- [x] Checklist rows updated with PR/test evidence. Evidence: PR #1231 plus focused pytest/Ruff evidence recorded above.

### Track B - Exchange Manifest Helpers (Owner: I41b / #1224)

Scope:

- `src/scieasy/blocks/code/exchange.py`
- `tests/blocks/code/test_codeblock_exchange.py`

Tasks:

- [x] Create exchange-directory layout helpers for per-run input, output, manifest, log, and temp paths. Evidence: commit `25104662`; `python -m pytest tests/blocks/code/test_codeblock_exchange.py --timeout=30 --no-cov`.
- [x] Implement deterministic input filename planning from port names, declared formats, and collision-safe suffixing. Evidence: commit `25104662`; `python -m pytest tests/blocks/code/test_codeblock_exchange.py --timeout=30 --no-cov`.
- [x] Implement an exchange manifest shape that records port name, object type, exchange path, format hint, materialisation status, and warnings. Evidence: commit `25104662`; `python -m pytest tests/blocks/code/test_codeblock_exchange.py --timeout=30 --no-cov`.
- [x] Implement declared-output discovery with missing-output and extra-output diagnostics. Evidence: commit `25104662`; `python -m pytest tests/blocks/code/test_codeblock_exchange.py --timeout=30 --no-cov`.
- [x] Use injectable adapter callables for materialise/reconstruct seams so ADR-043 capability registry work can wire in later without editing `engine/materialisation.py` in this track. Evidence: commit `25104662`; `python -m ruff check src/scieasy/blocks/code/exchange.py tests/blocks/code/test_codeblock_exchange.py`.
- [x] Add tests for collision handling, manifest contents, declared output discovery, and diagnostics. Evidence: commit `25104662`; `python -m pytest tests/blocks/code/test_codeblock_exchange.py --timeout=30 --no-cov`.

Exit Criteria:

- [x] Track B PR targets `track/adr-041/codeblock-v2`. Evidence: PR [#1233](https://github.com/zjzcpj/SciEasy/pull/1233).
- [x] Track B CI is green. Evidence: PR [#1233](https://github.com/zjzcpj/SciEasy/pull/1233) checks green on 2026-05-19 before this checklist evidence update.
- [x] Checklist rows updated with PR/test evidence. Evidence: PR [#1233](https://github.com/zjzcpj/SciEasy/pull/1233), commit `25104662`, focused pytest and Ruff commands recorded above.

## Phase 2 - Complete CodeBlock Runtime Module

ADR-041 runtime completion requires every user-important script family named by
the ADR. Python is the first backend lane because it proves the shared
file-exchange lifecycle, but it is not the terminal scope.

### Track C1 - Shared Runtime Integration and Python Backend (Owner: I41c / #1225)

Dependencies:

- Track A merged to tracking branch.
- Track B merged to tracking branch.

Scope:

- `src/scieasy/blocks/code/code_block.py`
- `src/scieasy/blocks/code/__init__.py` if needed
- CodeBlock execution tests under `tests/blocks/code/`

Tasks:

- [x] Integrate v2 config parsing into `CodeBlock` without silently accepting ambiguous legacy config. Evidence: commit `08cc5bc3`; focused pytest passed with 47 tests; Ruff passed.
- [x] Define the shared CodeBlock v2 runtime integration surface used by all interpreter backends. Evidence: commit `08cc5bc3`; runtime uses shared config, exchange, process, output, and provenance seams.
- [x] Use Track A interpreter/provenance helpers and Track B exchange helpers to run scripts through the shared file-exchange runtime, with Python `.py` as the first backend. Evidence: commit `08cc5bc3`; `test_codeblock_execution.py` covers exchange execution.
- [x] Preserve backend ownership of graph/runtime truth; frontend remains editor/viewer only. Evidence: commit `08cc5bc3`; runtime state/provenance stay in backend `CodeBlock` surfaces.
- [x] Return declared outputs as typed runtime objects or structured diagnostics according to the planning spec. Evidence: commit `08cc5bc3`; tests cover typed `Collection[Text]` output, missing output diagnostics, nonzero exit, and timeout.
- [x] Add tests for successful Python script execution, missing output failure, script non-zero exit failure, timeout, and provenance recording. Evidence: `PYTHONPATH=C:\Users\jiazh\Desktop\workspace\SciEasy-adr041-I41c\src python -m pytest tests/blocks/code/test_codeblock_v2_config.py tests/blocks/code/test_codeblock_interpreters.py tests/blocks/code/test_codeblock_provenance.py tests/blocks/code/test_codeblock_exchange.py tests/blocks/code/test_codeblock_execution.py tests/blocks/test_code_block.py tests/blocks/code/test_codeblock_python_integration.py tests/blocks/code/test_codeblock_r_integration.py --timeout=30 --no-cov` passed with 47 tests.
- [x] Add migration diagnostics for unsupported legacy inline/function mode. Evidence: commit `08cc5bc3`; legacy CodeBlock tests now assert `CodeBlockMigrationError`.
- [x] Leave stable extension points for notebook, R/Quarto, shell, and MATLAB/Octave tracks without editing ADR-043-owned files. Evidence: PR #1239 adds `CodeBlockBackend`, `CodeBlockRuntimeContext`, register/list/resolve backend helpers, and a `src/scieasy/blocks/code/backends/` module loader so C2-C5 can add one backend module each without editing `CodeBlock` dispatch logic.
- [x] Do not mark ADR-041 runtime complete in Track C1; C2-C5 remain required sibling backend tracks. Evidence: checklist retains C2-C5 rows after rebase onto manager commit `9a8710dc`.

Exit Criteria:

- [x] Track C1 PR targets `track/adr-041/codeblock-v2`. Evidence: [PR #1239](https://github.com/zjzcpj/SciEasy/pull/1239).
- [x] Track C1 CI is green. Evidence: PR #1239 checks passed on 2026-05-19 after commit `fa42011e`.
- [x] Checklist rows updated with PR/test evidence. Evidence: PR #1239, commits `08cc5bc3`, `653ca2c4`, and `fa42011e`, focused local tests, import contracts, ADR-042 facts check, and CI evidence recorded above.

### Track C2 - Notebook Runtime and Executed Artifact Capture (Owner: I41n / #1235)

Dependencies:

- Track C1 shared runtime integration merged or stable enough for backend registration.

Scope:

- CodeBlock notebook interpreter backend files identified in the Track C2 change plan.
- Notebook runtime tests under `tests/blocks/code/`.

Tasks:

- [ ] Add `.ipynb` runtime execution through nbconvert or a local Jupyter runner when available.
- [ ] Capture the executed notebook as a framework-managed `_executed_notebook` `Artifact`.
- [ ] Preserve typed output collection from declared output folders alongside notebook artifact capture.
- [ ] Add tests for success, failure diagnostics, optional dependency skip behavior, and artifact retention where feasible.
- [ ] Keep optional notebook dependencies out of the base runtime unless the existing project packaging already includes them.

Exit Criteria:

- [ ] Track C2 PR targets `track/adr-041/codeblock-v2`.
- [ ] Track C2 CI is green.
- [ ] Checklist rows updated with PR/test evidence.

### Track C3 - R and Quarto Runtime Support (Owner: I41r / #1238)

Dependencies:

- Track C1 shared runtime integration merged or stable enough for backend registration.

Scope:

- CodeBlock R/Quarto interpreter backend files identified in the Track C3 change plan.
- R/Quarto runtime tests under `tests/blocks/code/`.

Tasks:

- [ ] Add `.R` execution through `Rscript` when available.
- [ ] Add `.Rmd` rendered-document support where R Markdown tooling is available.
- [ ] Add `.qmd` execution/rendering support through Quarto where available.
- [ ] Add deterministic command construction and exchange-directory environment passing.
- [ ] Add tests for missing executable diagnostics, command construction, output collection, and optional dependency skip behavior.

Exit Criteria:

- [ ] Track C3 PR targets `track/adr-041/codeblock-v2`.
- [ ] Track C3 CI is green.
- [ ] Checklist rows updated with PR/test evidence.

### Track C4 - Shell Runtime Support (Owner: I41s / #1237)

Dependencies:

- Track C1 shared runtime integration merged or stable enough for backend registration.

Scope:

- CodeBlock shell interpreter backend files identified in the Track C4 change plan.
- Shell runtime tests under `tests/blocks/code/`.

Tasks:

- [ ] Add `.sh` execution through a compatible POSIX shell when available.
- [ ] Pass exchange-directory context deterministically without adding hidden format semantics.
- [ ] Add tests for successful output collection, nonzero exit diagnostics, missing shell diagnostics, and Windows compatibility behavior.

Exit Criteria:

- [ ] Track C4 PR targets `track/adr-041/codeblock-v2`.
- [ ] Track C4 CI is green.
- [ ] Checklist rows updated with PR/test evidence.

### Track C5 - MATLAB and Octave Runtime Support (Owner: I41m / #1236)

Dependencies:

- Track C1 shared runtime integration merged or stable enough for backend registration.

Scope:

- CodeBlock MATLAB/Octave interpreter backend files identified in the Track C5 change plan.
- MATLAB/Octave runtime tests under `tests/blocks/code/`.

Tasks:

- [x] Add `.m` execution through MATLAB or Octave when available. Evidence: commit `ce9ca4c8`; backend selects MATLAB first in auto mode and falls back to Octave for `.m`.
- [x] Add `.mlx` handling through MATLAB where available, with clear unsupported diagnostics when not available. Evidence: commit `ce9ca4c8`; tests cover `.mlx` MATLAB requirement and Octave rejection.
- [x] Add deterministic command construction, exchange-directory environment passing, and output collection. Evidence: commit `ce9ca4c8`; backend reuses shared CodeBlock process execution and tests assert argv/cwd/env/timeout handoff.
- [x] Add tests for executable selection, missing executable diagnostics, command construction, and optional dependency skip behavior. Evidence: `PYTHONPATH=C:\Users\jiazh\Desktop\workspace\SciEasy-adr041-I41m\src python -m pytest tests/blocks/code/test_codeblock_matlab.py --timeout=30 --no-cov` passed with 10 tests and 1 optional Octave skip; Ruff passed for touched Python files.

Exit Criteria:

- [x] Track C5 PR targets `track/adr-041/codeblock-v2`. Evidence: [PR #1247](https://github.com/zjzcpj/SciEasy/pull/1247).
- [x] Track C5 CI is green. Evidence: PR #1247 `Verify Workflow Compliance` passed on 2026-05-19.
- [x] Checklist rows updated with PR/test evidence. Evidence: PR #1247 plus focused pytest/Ruff evidence recorded above.

## Phase 3 - Validation and Migration Diagnostics

### Track D - Workflow Validation (Owner: I41d / #1226)

Dependencies:

- Track A merged.
- Track C1 contract stable enough for validator integration.
- Runtime backend tracks C2-C5 define extension-specific diagnostics.

Scope:

- `src/scieasy/blocks/code/validation.py`
- Workflow validation integration files identified in the track change plan
- Validation tests under `tests/workflow/` or `tests/blocks/code/`

Tasks:

- [ ] Add reusable validation routines for CodeBlock v2 config and declarations.
- [ ] Wire validation into the existing workflow validation path without moving runtime truth to frontend state.
- [ ] Add actionable diagnostics for legacy inline/function-style CodeBlock configs.
- [ ] Add tests for valid v2 config, invalid path/config combinations, unsupported language modes, and legacy migration messages.

Exit Criteria:

- [ ] Track D PR targets `track/adr-041/codeblock-v2`.
- [ ] Track D CI is green.
- [ ] Checklist rows updated with PR/test evidence.

## Phase 4 - Frontend Configuration

### Track E - CodeBlock v2 Editor (Owner: I41e / #1227)

Dependencies:

- Tracks C1-C5 merged or frontend scope explicitly narrowed to available runtime families.
- Track D merged if validator diagnostics are surfaced in UI.

Scope:

- Frontend CodeBlock config components and API adapters identified in the Track E change plan before editing.

Tasks:

- [ ] Locate existing CodeBlock configuration UI and API adaptation points.
- [ ] Update UI controls for script path, interpreter mode, environment variables, declared inputs, declared outputs, timeout, and exchange-directory options.
- [ ] Avoid frontend-only execution semantics; UI writes the backend-owned config contract.
- [ ] Add frontend tests for config editing and validation-message display.
- [ ] Run browser smoke only if a local frontend target is required and stable.

Exit Criteria:

- [ ] Track E PR targets `track/adr-041/codeblock-v2`.
- [ ] Track E CI is green.
- [ ] Checklist rows updated with PR/test evidence.

## Phase 5 - Documentation, Facts, and Audit

### Track F - Final Docs/Audit (Owner: A41/F41 / #1228)

Dependencies:

- Backend implementation tracks merged.
- Frontend track decision recorded.

Scope:

- `docs/specs/adr-041-codeblock-v2.md` only if implementation errata are needed.
- `docs/audit/<YYYY-MM-DD>-adr-041-*.md`
- `docs/facts/generated.yaml` if public code facts changed.
- `CHANGELOG.md`

Tasks:

- [ ] Regenerate or check ADR-042 facts as required by the changed public symbols.
- [ ] Run the ADR-042 audit suite for ADR-041-related docs and implementation facts.
- [ ] Fix all ADR-041-related audit errors.
- [ ] Record final audit report under `docs/audit/`.
- [ ] Update changelog with implementation track summaries.
- [ ] Confirm no ADR-043 conflict files were modified by ADR-041 tracks.

Exit Criteria:

- [ ] Audit passes.
- [ ] Umbrella PR body links child PRs, audit report, tests, and unresolved risks.
- [ ] Umbrella PR is ready for review once child PRs are merged and CI is green.

## Dispatch Log

- [x] I41a dispatched for #1223. Worktree: `C:\Users\jiazh\Desktop\workspace\SciEasy-adr041-I41a`; branch: `feat/issue-1223/adr041-config-interpreter-provenance`.
- [x] I41b dispatched for #1224. Evidence: worktree `C:\Users\jiazh\Desktop\workspace\SciEasy-adr041-I41b`, branch `feat/issue-1224/adr041-exchange-manifest`, gate session `20260519-182539-adr-041-track-b-codeblock-v2-exchange-ma`.
- [x] I41c dispatched for #1225. Evidence: worktree `C:\Users\jiazh\Desktop\workspace\SciEasy-adr041-I41c`, branch `feat/issue-1225/adr041-codeblock-python-execution`, gate session `20260519-185434-adr-041-track-c-codeblock-v2-python-exec`, PR #1239; retargeted on 2026-05-19 from Python-only MVP to shared runtime integration plus Python backend.
- [ ] I41n dispatched for #1235.
- [ ] I41r dispatched for #1238.
- [ ] I41s dispatched for #1237.
- [x] I41m dispatched for #1236. Evidence: worktree `C:\Users\jiazh\Desktop\workspace\SciEasy-adr041-I41m`, branch `feat/issue-1236/adr041-matlab-octave-runtime`, gate session `20260519-195039-adr-041-track-c5-matlab-and-octave-runti`.
- [ ] I41d dispatched for #1226.
- [ ] I41e dispatched for #1227.
- [ ] A41/F41 dispatched for #1228.
