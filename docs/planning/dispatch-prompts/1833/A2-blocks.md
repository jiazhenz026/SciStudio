[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Land the ADR-052 public API contract; you implement the **block-authoring surface** (base/process/io/app/code) exactly as the owner-signed per-symbol spec records it, plus fix the custom-block starter template's API.
- Task kind: feature
- Persona: implementer
- Issue: #1833 (umbrella tracking #1817)
- Protected branch: main
- Agent branch: feat/1833-adr-052-blocks
- Agent worktree: /Users/jiazhenz/scistudio-wt-1833-blocks
- Gate record: manager-owned; do NOT touch.

## Required Rules

Read and follow, FROM YOUR WORKTREE:
- `docs/adr/ADR-052.md`
- `docs/specs/adr-052-public-api-surface.md` — THE AUTHORITATIVE per-symbol contract (your checklist). Sections you implement: **§4 (all of §4.1–§4.8), §5, §6 (all of §6.1–§6.5), §7 (all of §7.1–§7.4), §7A, the `Block.persist_*` rows of §11, and §16 step 1.**
- `AGENTS.md`, `docs/ai-developer/rules.md`, `docs/ai-developer/personas/implementer.md`

The spec is signed and authoritative. Transcribe it literally; where intuition disagrees, the spec wins.

## Scope

You own ONLY:
- `src/scistudio/blocks/**` (base, process, io, app, code, and `_templates/`)

You must NOT touch:
- `tests/**` (a single separate test agent owns ALL tests — owner's hard rule)
- `src/scistudio/core/**`, `src/scistudio/previewers/**`
- `mkdocs.yml`, `pyproject.toml`, `docs/**`
- `scistudio.ai.agent.mcp.tools_plot/**`

If you need an out-of-scope path, STOP and report back.

## Coordination

- Other agents edit core/, previewers/, doc build, and tests IN PARALLEL. Stay strictly in `src/scistudio/blocks/**`.
- Work only in worktree `/Users/jiazhenz/scistudio-wt-1833-blocks` on `feat/1833-adr-052-blocks`.
- MUST NOT `pip install -e .`. Run python with `PYTHONPATH=$PWD/src`.
- **DO NOT commit/push/PR.** The manager integrates your worktree. Edit files and report.
- `scistudio.stability` is already on main — import and use it.

## SHARED FREEZE CONTRACT (manager-defined; identical across all agents)

- Canonical public roots (public surface = each root's `__all__`):
  1. `scistudio.core.types`  2. `scistudio.core.meta`  3. `scistudio.blocks.base`
  4. `scistudio.blocks.process`  5. `scistudio.blocks.io`  6. `scistudio.blocks.app`
  7. `scistudio.blocks.code`  8. `scistudio.previewers.models`  9. `scistudio.previewers.data_access`
  (You own the declarations for roots #3–#7.)
- Decoration rule: EVERY name in a root's `__all__` carries exactly one `@stable(since=...)` or `@provisional(since=...)` matching the spec Tier column. `@internal` is NEVER in `__all__`. Baseline `since="0.3.1"`.
- Method-level decoration: public methods/classmethods/staticmethods named "Public" in the spec tables carry the same decorators at their spec tier. `@classmethod`/`@staticmethod` OUTERMOST, then `@stable/...`.

## Work To Do (transcribe the spec; the §4.8/§6.5/§7/§7A "Net __all__ change" notes are explicit)

### blocks.base (§4)
1. `blocks.base.__all__` net change (§4.8): KEEP `Block, BlockConfig, InputPort, OutputPort, ExecutionMode, PackageInfo`. DROP `Port, BlockState, BlockResult` and the 4 port helpers (`port_accepts_type, port_accepts_signature, validate_connection, validate_port_constraint`). ADD `PackageOtaSource` (provisional) + the re-exported interactive surface + re-export `BlockCancelledByAppError`.
2. `interactive.py __all__` net change (§4.8): KEEP `InteractiveMixin, InteractivePrompt, PanelManifest, load_intermediate, PANEL_API_VERSION, INTERACTIVE_RESPONSE_KEY`; DROP `SupportsInteraction, coerce_prompt, serialise_storage_ref, deserialise_storage_ref, INTERACTIVE_INTERMEDIATE_KEY` and the other internal rows in §4.8. **Re-export the kept interactive symbols from the `blocks.base` root.** Whole interactive surface = **provisional**.
3. Decorate per §4.1–§4.7: `Block` stable; all its authoring ClassVars stable EXCEPT `dynamic_ports` → **provisional**; lifecycle/hooks/helpers stable (`validate, run, postprocess, process_item, get_effective_input_ports, get_effective_output_ports, pack/unpack/unpack_single/map_items/parallel_map, persist_array, persist_table` §11); `get_panel_manifest` → **provisional**. `BlockConfig` stable (`params`, `get`). `InputPort`/`OutputPort` stable (fields per §4.3). `ExecutionMode` stable. `PackageInfo` stable; `PackageInfo.ota` provisional; `PackageOtaSource` provisional. `BlockCancelledByAppError` provisional (defined in `exceptions.py`; re-export from `blocks.app` too — see app step). Demote `Port`, `BlockState`, `BlockResult`, the 4 port helpers, `ports_from_config_dicts` to Internal (no decorator, not in `__all__`).

### blocks.process (§5)
4. `process.__all__ = ["ProcessBlock"]`. `ProcessBlock` stable + members (`algorithm, process_item(3-arg), setup, teardown, run`) stable. `to_arrow`, `_process_item_takes_state` internal.

### blocks.io (§6)
5. `io.__all__` net change (§6.5): KEEP `IOBlock, SimpleLoader, SimpleSaver, FormatCapability, MetadataFidelity, CapabilityDirection, MetadataFidelityLevel` + the 5 capability errors (`CapabilityValidationError, InvalidExtensionError, InvalidMetadataFidelityError, InvalidFormatCapabilityError, SimpleIODeclarationError`). DROP `normalize_extension, normalize_extensions, LoadData, SaveData`. All kept = **stable**. Mark `IOBlock.supported_extensions` **deprecated** (⚠️ — keep importable, decorate to reflect deprecated; use the deprecation mechanism the stability module / repo convention provides; it is still a public ClassVar but slated for removal). Decorate per §6.1–§6.3 tables. `materialise_to_file`/`reconstruct_from_file` internal. `LoadData`/`SaveData` stay importable via deep path; just drop from `io.__all__`.

### blocks.app (§7) — whole surface PROVISIONAL
6. `app.__all__` net change (§7): KEEP `AppBlock`; ADD `FileExchangeBridge, FileWatcher, ProcessExitedWithoutOutputError, validate_app_command, ExternalAppBridge`; re-export `BlockCancelledByAppError`. All **provisional**. Decorate per §7.1–§7.4.
7. **Resolve `_PopenProcessAdapter` (§7.1, owner option b):** teach `FileWatcher` (watcher.py) to accept a plain `subprocess.Popen` as its `process_handle` (treat `.poll() is None` as "alive"); `_PopenProcessAdapter` stays Internal (no longer needed on the surface). Do NOT delete the adapter if internal callers still need it, but the public path is the plain `Popen`.
8. **Remove/replace `_guess_mime` in `blocks/app/bridge.py` (§7.2, owner option c):** extension→MIME is non-load-bearing (`Artifact.mime_type` only feeds a provenance sidecar; nothing branches on it). Replace the `_guess_mime(fp)` call at the `Artifact(...)` construction with an authoritative source or `None` (the typed path already sets `mime_type=None`). Remove the now-dead `_guess_mime` def. **Also remove the `blocks/io/loaders` MIME-guess copies** (`_MIME_GUESS` in `_helpers.py`, its use in `load_data.py` and reference in `_capability.py`) the same way — replace with the declared type / `FormatCapability.format_id` / `None`. (The previewers copies are another agent's; do not touch previewers.)

### blocks.code (§7A) — whole surface PROVISIONAL
9. Publish the entire `blocks/code` non-underscore surface as **provisional**, re-exported from `blocks.code.__all__` (the §7A tables enumerate it: `CodeBlock`, config models incl. `CodeBlockConfig`/`PortFileConfig`/**add `CodeBlockConfigError`**, backend-registration surface, exchange/interpreters/introspect/provenance/validation/backends symbols). Leading-underscore names stay internal. `MigrationDiagnostic`, `resolve_project_path`, `legacy_migration_diagnostics` → internal.
10. **DELETE the dead legacy runner layer** (§7A decision log "Owner: delete"): remove `src/scistudio/blocks/code/runner_registry.py` and the `runners/*` package (production code only — 0 production importers; `code_block.py` uses `backends/`). Do NOT touch their tests (the test agent removes `tests/blocks/test_runner_registry.py`, `test_runners_subprocess.py`, and the `test_code_block.py` runner import).

### Template
11. **Custom-block GUI starter template** `src/scistudio/blocks/_templates/block_base_template.py`: update its example/scaffold code to the contract API ONLY — canonical-root imports (`from scistudio.blocks.process import ProcessBlock`, `from scistudio.core.types import ...`), public symbols, the ergonomic accessors / public idioms where it illustrates reads. **Do NOT change the teaching narrative, comments' intent, or structure — only the API surface used.** If a string/skeleton test asserts the old API text, do not edit the test; report it.

## Validation (run in your worktree; RUN tests but do NOT edit them)

- Import every root you own and print `__all__`; assert each `__all__` symbol has `get_stability(...)` non-None.
- `PYTHONPATH=$PWD/src python -m pytest tests/blocks -x -q` (read-only). Tests referencing removed/renamed symbols (`LoadData`/`SaveData` in `io.__all__`, `normalize_extension`, the port helpers, `_guess_mime`, the runner layer, `_PopenProcessAdapter` as adapter, interactive `__all__` drops) will fail — EXPECTED; the test agent updates them from the same spec. **Report those test files; do NOT edit tests.**
- Smoke: construct an `AppBlock` watcher path mentally / confirm `FileWatcher(process_handle=Popen(...))` type-checks; confirm `CodeBlock` still imports after the runner-layer deletion.

## TODO And Deferral Rule

`TODO(#NNN): <reason>`. Known deferrals:
- `TODO(#1817)`: `port_accepts_signature` is dead code (0 call sites) — keep-or-delete tracked under #1817 (leave it, just drop from `__all__`).
- imaging passing a raw `Popen` / dropping `_guess_mime` import is a cross-repo migration (not in this repo).

## Output Required

1. **Public surface map** for roots #3–#7: `import_path.symbol → kind → tier → since` for every public symbol + decorated member, as implemented (manager reconciliation key).
2. Changed + deleted file paths.
3. List of EXISTING test files referencing removed/renamed symbols (for the test agent).
4. Confirmation the runner-layer deletion leaves `CodeBlock` importable.
5. Any blocker or scope issue.

## Stop Conditions

Stop and report if: you need an out-of-scope file; the FileWatcher-plain-Popen change or `_guess_mime` removal breaks a contract the spec did not anticipate; the runner-layer deletion has a hidden production importer; you cannot make a surface match the spec.
