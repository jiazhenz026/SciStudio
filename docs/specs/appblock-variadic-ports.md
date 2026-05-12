# AppBlock Variadic Ports + Extension-Based Output Binning

**Issue**: [#680](https://github.com/zjzcpj/SciEasy/issues/680)
**Status**: Implemented
**Builds on**: ADR-029 (variadic port editor), ADR-030 (config_schema MRO merge)
**Related (out of scope)**: #679 (per-app `output_dir` injection)

---

## Goal

Let users define input and output ports on every AppBlock instance via
the existing port editor, and route files saved by the external
application into the declared output ports by file extension.

---

## Editor Contract

The port editor (`frontend/src/components/PortEditorTable.tsx`) renders:

- **Input ports** — name + type (existing fields).
- **Output ports** — name + type + **extension** (new).

Per-port `extension` semantics:

- One string per port (no list, no glob).
- Stored without a leading dot, lowercased on input.
  `"TIF"`, `".tif"`, and `"tif"` all canonicalise to `"tif"`.
- Required field; the schema marks it `"required": ["name", "extension"]`.

The frontend writes the resulting list into
`node.config.params.output_ports` as `[{name, types, extension}, ...]`.

---

## Backend Binner

`AppBlock._bin_outputs_by_extension(output_files, config)` runs after
`watcher.wait_for_output()` returns. Its rules are:

| File condition | Behaviour |
|---|---|
| Suffix (case-insensitive) matches a port's `extension` | Wrap as `Artifact(file_path=...)` and append to that port's `Collection`. |
| Required port receives 0 matching files | Raise `ValueError("Port 'X' required, no '.ext' files in output dir")`. |
| Optional port receives 0 matching files | Return an empty `Collection`. |
| File matches no port | Log a `WARNING` (`"Unmatched output file 'name.ext'"`) and continue. |

Effective port resolution priority:

1. `config["output_ports"]` (run-time, from the workflow/scheduler).
2. `self.get_effective_output_ports()` (instance-level
   `self.config["output_ports"]` -> ClassVar fallback).

`Collection.item_type` is set to `port.accepted_types[0]` (or `Artifact`
when the port declares no types). Downstream blocks consume the
`Artifact` collection via standard load blocks if they need to
materialise the data.

---

## Validator: duplicate-extension check

`scieasy.workflow.validator.validate_workflow` adds **Check 8**:

> For every node whose `BlockSpec.variadic_outputs` is `True`, scan
> `node.config["output_ports"]` and reject configurations where two
> ports declare the same extension (case-insensitive). Emit
> `Node 'X': Duplicate extension 'tif' across output ports {a, b}`.

The check runs at workflow save time so users discover the conflict
before they run the graph.

---

## Subclass Migration

Concrete AppBlock subclasses (FijiBlock, NapariBlock, ElMAVENBlock):

- Keep their `output_ports` ClassVar as a **default scaffold** the user
  may override via the editor.
- Drop plugin-private file-->port heuristics
  (`_collect_outputs` / `_guess_output_port` in the imaging plugin
  were deleted; ElMAVEN's `_classify_export` /
  `_collect_elmaven_outputs` are deprecated and no longer called from
  `run()`).
- Their `run()` ends with a one-liner delegating to
  `self._bin_outputs_by_extension(output_files, config)` when
  `config["output_ports"]` is set, falling back to a single-port
  Artifact wrap for backwards compatibility.
- Broaden their watcher patterns at run time to include each declared
  extension, so files of those types are not filtered out before they
  reach the binner.

---

## Non-Goals

- No file content inspection / type inference.
- No multi-extension ports.
- No per-port glob fields.
- No automatic port creation based on saved content.
- No upper-bound count rules.

---

## Test Coverage

| Layer | Test |
|---|---|
| Base class | `tests/blocks/test_app_block.py::TestAppBlockVariadicPorts` |
| Binner | `tests/blocks/test_app_block.py::TestAppBlockExtensionBinner` |
| Workflow validator | `tests/workflow/test_validator.py::TestValidatorAppBlockDuplicateExtensions` |
| Frontend editor | `frontend/src/components/PortEditorTable.test.tsx` |
| End-to-end FijiBlock | `packages/scieasy-blocks-imaging/tests/test_interactive_blocks.py::test_fiji_block_routes_outputs_into_user_declared_ports_by_extension` |
