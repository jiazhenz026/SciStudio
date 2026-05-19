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
- [ ] Umbrella PR opened as `[DO NOT MERGE]`.
- [ ] Tracking branch pushed.

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

- [ ] Define CodeBlock v2 config models for script path, inline code migration diagnostics, declared inputs, declared outputs, working directory, interpreter selection, environment variables, timeout, and exchange-directory policy.
- [ ] Validate path-like fields without assuming the project fits in memory or that paths are local-only forever.
- [ ] Implement Python interpreter resolution for `auto`, explicit executable path, and active environment fallback.
- [ ] Implement provenance helpers that capture script path, content hash when available, interpreter identity, command argv, environment delta, and execution timestamps.
- [ ] Add tests for valid config, invalid mixed inline/script config, missing script, interpreter resolution success/failure, and provenance payload stability.
- [ ] Avoid `src/scieasy/blocks/code/code_block.py` in this track.

Exit Criteria:

- [ ] Track A PR targets `track/adr-041/codeblock-v2`.
- [ ] Track A CI is green.
- [ ] Checklist rows updated with PR/test evidence.

### Track B - Exchange Manifest Helpers (Owner: I41b / #1224)

Scope:

- `src/scieasy/blocks/code/exchange.py`
- `tests/blocks/code/test_codeblock_exchange.py`

Tasks:

- [ ] Create exchange-directory layout helpers for per-run input, output, manifest, log, and temp paths.
- [ ] Implement deterministic input filename planning from port names, declared formats, and collision-safe suffixing.
- [ ] Implement an exchange manifest shape that records port name, object type, exchange path, format hint, materialisation status, and warnings.
- [ ] Implement declared-output discovery with missing-output and extra-output diagnostics.
- [ ] Use injectable adapter callables for materialise/reconstruct seams so ADR-043 capability registry work can wire in later without editing `engine/materialisation.py` in this track.
- [ ] Add tests for collision handling, manifest contents, declared output discovery, and diagnostics.

Exit Criteria:

- [ ] Track B PR targets `track/adr-041/codeblock-v2`.
- [ ] Track B CI is green.
- [ ] Checklist rows updated with PR/test evidence.

## Phase 2 - CodeBlock Runtime Integration

### Track C - Python MVP Execution (Owner: I41c / #1225)

Dependencies:

- Track A merged to tracking branch.
- Track B merged to tracking branch.

Scope:

- `src/scieasy/blocks/code/code_block.py`
- `src/scieasy/blocks/code/__init__.py` if needed
- CodeBlock execution tests under `tests/blocks/code/`

Tasks:

- [ ] Integrate v2 config parsing into `CodeBlock` without silently accepting ambiguous legacy config.
- [ ] Use Track A interpreter/provenance helpers and Track B exchange helpers to run Python scripts through the file-exchange contract.
- [ ] Preserve backend ownership of graph/runtime truth; frontend remains editor/viewer only.
- [ ] Return declared outputs as typed runtime objects or structured diagnostics according to the planning spec.
- [ ] Add tests for successful Python script execution, missing output failure, script non-zero exit failure, timeout, and provenance recording.
- [ ] Add migration diagnostics for unsupported legacy inline/function mode.

Exit Criteria:

- [ ] Track C PR targets `track/adr-041/codeblock-v2`.
- [ ] Track C CI is green.
- [ ] Checklist rows updated with PR/test evidence.

## Phase 3 - Validation and Migration Diagnostics

### Track D - Workflow Validation (Owner: I41d / #1226)

Dependencies:

- Track A merged.
- Track C contract stable enough for validator integration.

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

- Track C merged.
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

- [ ] I41a dispatched for #1223.
- [ ] I41b dispatched for #1224.
- [ ] I41c dispatched for #1225.
- [ ] I41d dispatched for #1226.
- [ ] I41e dispatched for #1227.
- [ ] A41/F41 dispatched for #1228.
