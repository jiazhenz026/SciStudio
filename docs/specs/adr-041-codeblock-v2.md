---
spec_id: adr-041-codeblock-v2
title: "ADR-041 CodeBlock v2 Implementation Specification"
status: Draft
feature_branch: docs/issue-1208/adr-041-codeblock-v2-spec
created: 2026-05-19
input: "Owner request to write an ADR-042-compliant, implementation-ready planning spec for ADR-041."
owners:
  - "@jiazhenz026"
related_adrs:
  - 41
  - 42
  - 43
related_specs:
  - adr-043-io-format-capability-registry
scope:
  in:
    - CodeBlock v2 as an AppBlock-shaped script integration block.
    - Project-local script selection and provenance capture.
    - File-only exchange directory delivery for typed inputs and outputs.
    - ADR-043 capability-aware input materialisation and output reconstruction.
    - Interpreter resolution and environment snapshot capture.
    - Executed notebook and rendered artifact capture.
    - Frontend configuration for script path, interpreter mode, ports, exchange paths, and capability selection.
    - Migration from current inline/function CodeBlock behavior to v2 script mode.
  out:
    - DataObject-owned external format semantics.
    - Parameters-mode injection into scripts, notebooks, frontmatter, shell variables, or MATLAB workspaces.
    - Registering every script file as a separate palette block.
    - Workflow-language execution semantics for Snakemake, Nextflow, CWL, or WDL.
    - Container orchestration for Docker, Apptainer, or Singularity.
    - Full package migration to ADR-043 capabilities; that remains governed by ADR-043.
governs:
  modules:
    - scistudio.blocks.code
    - scistudio.blocks.app
    - scistudio.engine.materialisation
    - scistudio.workflow
  contracts:
    - scistudio.blocks.code.code_block.CodeBlock
    - scistudio.blocks.code.interpreters.resolve_script_interpreter
    - scistudio.blocks.code.exchange.prepare_codeblock_exchange
    - scistudio.blocks.code.exchange.collect_codeblock_outputs
    - scistudio.blocks.code.validation.validate_codeblock_config
    - scistudio.blocks.code.provenance.capture_script_provenance
    - scistudio.blocks.app.bridge
    - scistudio.engine.materialisation.materialise_to_file
    - scistudio.engine.materialisation.reconstruct_from_file
  entry_points:
    - scistudio.blocks
  files:
    - docs/specs/adr-041-codeblock-v2.md
    - docs/adr/ADR-041.md
    - docs/adr/ADR-043.md
    - src/scistudio/blocks/code/**
    - src/scistudio/blocks/app/**
    - src/scistudio/engine/materialisation.py
    - src/scistudio/workflow/validator.py
    - frontend/src/**
    - docs/block-development/**
tests:
  - tests/blocks/code/test_codeblock_v2_config.py
  - tests/blocks/code/test_codeblock_exchange.py
  - tests/blocks/code/test_codeblock_interpreters.py
  - tests/blocks/code/test_codeblock_execution.py
  - tests/blocks/code/test_codeblock_notebooks.py
  - tests/blocks/app/test_app_block_capabilities.py
  - tests/engine/test_materialisation_capabilities.py
  - tests/workflow/test_io_boundary_validation.py
  - frontend/src/**/__tests__/**
acceptance_source: adr
language_source: en
---

# ADR-041 CodeBlock v2 Implementation Specification

## 1. Change Summary

This spec translates ADR-041 into an implementable plan for CodeBlock v2.
CodeBlock v2 is a script integration block shaped like AppBlock: it materialises
typed workflow inputs into files, launches a project-local script through a
resolved interpreter, waits for completion, collects declared output files, and
reconstructs typed SciStudio objects through ADR-043 IO format capabilities.

The implementation must preserve ADR-041's architectural boundaries:

- the workflow graph and runtime remain the source of truth;
- CodeBlock owns script execution coordination, not file format semantics;
- typed boundary IO is resolved through ADR-043 capabilities;
- delivery is file-only in v1;
- inline code and SciStudio entry-function mode are removed from CodeBlock v2;
- script provenance, interpreter resolution, and environment snapshots are
  captured for lineage.

The first deliverable should be a Python-script MVP that shares the AppBlock
boundary lifecycle. Later phases add notebook artifacts, additional interpreter
families, richer frontend guidance, and migration paths for legacy CodeBlock
workflows.

## 2. User Scenarios & Testing

### User Story 1 - Run an existing Python script with typed file inputs (Priority: P1)

As a scientist, I need to select a project-local `.py` script and connect
typed workflow inputs to script-readable files without rewriting the script as
a SciStudio `run()` function.

Why this priority: ADR-041 exists because the current CodeBlock requires
framework-shaped code and excludes existing file-oriented scripts.

Independent Test: Configure a CodeBlock with one `Image` input and one
`DataFrame` output, run a fixture Python script that reads from
`inputs/image/` and writes to `outputs/table/`, and verify the output is a
typed `DataFrame` reconstructed through ADR-043 capabilities.

Acceptance Scenarios:

1. Given a project-local Python script and a valid input saver capability, when
   the block runs, then the input is materialised into the declared input port
   folder before the interpreter starts.
2. Given the script writes a supported output extension into the declared
   output port folder, when collection runs, then the runtime reconstructs the
   declared output type through the selected loader capability.
3. Given a missing or ambiguous input saver capability, when workflow
   validation runs, then the block fails before the script starts.

### User Story 2 - The script boundary is visible and hard to misuse (Priority: P1)

As a workflow author, I need the config panel to show exactly which folders my
script should read from and write to.

Why this priority: ADR-041 accepts that users may need to adapt path strings
inside scripts, so the UI must make the exchange contract obvious.

Independent Test: Render the CodeBlock config panel for multiple input and
output ports and verify it displays direction, declared type, selected
extension, capability label, and copyable exchange-relative folder paths.

Acceptance Scenarios:

1. Given a configured input port named `image`, when the config panel renders,
   then it shows `inputs/image/` as the stable read folder.
2. Given a configured output port named `mask`, when the config panel renders,
   then it shows `outputs/mask/` as the stable write folder.
3. Given likely absolute path literals are detected in a script, when the user
   edits the block, then the UI shows warnings without changing the script
   automatically.

### User Story 3 - Invalid output contracts fail before execution (Priority: P1)

As a user, I need a declared output such as `Label + .tif` to fail early if no
loader capability can reconstruct that type.

Why this priority: ADR-041 consumes ADR-043 so AppBlock and CodeBlock boundary
IO share the same deterministic validation behavior.

Independent Test: Validate CodeBlock fixture ports for missing, unique,
ambiguous, and explicit loader/saver capability selections.

Acceptance Scenarios:

1. Given an output port with no matching loader capability, when validation
   runs, then it returns a typed capability error and the process is not
   launched.
2. Given two matching loader capabilities and no explicit `capability_id`, when
   validation runs, then it reports ambiguity.
3. Given the same two capabilities and an explicit valid `capability_id`, when
   validation runs, then the workflow is accepted.

### User Story 4 - Script provenance survives review and rerun (Priority: P2)

As a reviewer, I need lineage to say which script, interpreter, environment,
capabilities, and exchange files produced a run.

Why this priority: script integrations are not reproducible unless their
source and execution context are captured.

Independent Test: Run a CodeBlock fixture and inspect the lineage record for
script relative path, content hash or git evidence, interpreter command,
environment mode, selected capabilities, exchange manifest, and produced files.

Acceptance Scenarios:

1. Given a script tracked by project git, when CodeBlock runs, then lineage
   records the script path and git commit evidence.
2. Given a project-local but untracked script, when CodeBlock runs, then
   lineage records a content hash and flags the untracked status.
3. Given environment mode `existing`, when CodeBlock runs, then lineage records
   the resolved interpreter path and an environment snapshot.

### User Story 5 - Notebook-like scripts produce evidence artifacts (Priority: P2)

As a scientist using notebooks or rendered documents, I need the executed
notebook or rendered artifact captured even when my typed data outputs are
separate.

Why this priority: ADR-041 treats executed notebooks as reproducibility
evidence, not just transient process side effects.

Independent Test: Execute an `.ipynb` fixture through CodeBlock and verify the
runtime captures an `_executed_notebook` `Artifact` output and records it in
lineage.

Acceptance Scenarios:

1. Given an `.ipynb` script, when execution succeeds, then the executed notebook
   file is captured as an `Artifact`.
2. Given the notebook also writes typed output files, when output collection
   runs, then typed outputs and the executed artifact are both returned.
3. Given notebook execution fails, when the run ends, then the partial executed
   artifact is retained if the interpreter produced one and lineage marks the
   block failed.

### User Story 6 - Legacy CodeBlock workflows get an explicit migration path (Priority: P3)

As a maintainer, I need existing inline/function-mode CodeBlock workflows to
fail or migrate clearly rather than silently changing semantics.

Why this priority: ADR-041 removes current CodeBlock modes. Silent migration
would risk changing runtime behavior without user consent.

Independent Test: Load representative legacy CodeBlock configs and verify the
workflow validator emits migration diagnostics with suggested replacement
paths.

Acceptance Scenarios:

1. Given a legacy inline CodeBlock config, when validation runs, then it emits a
   migration diagnostic pointing to ProcessBlock or custom block authoring.
2. Given a legacy script-mode config with a project-local script, when migration
   is available, then the tool proposes a CodeBlock v2 config without changing
   it silently.
3. Given a legacy config that cannot be migrated safely, when loading the
   workflow, then the UI shows a blocking migration error.

### Edge Cases

- Script path traversal such as `../outside.py`.
- Symlinked script paths that resolve outside the project.
- Case-insensitive extension matching on Windows.
- Input port folder name collisions.
- Multiple output ports using the same extension.
- Output folder contains both matching and non-matching extensions.
- Required output port folder is empty.
- Optional output port folder is empty.
- Collection input item names collide after basename normalization.
- Script exits successfully but produces no declared outputs.
- Script exits nonzero after producing partial outputs.
- Interpreter discovery finds multiple candidates.
- Environment snapshot command is unavailable or times out.
- User deletes the exchange directory while the process is running.
- Workflow is cancelled while a child process is active.

## 3. Requirements

### Functional Requirements

- FR-001: CodeBlock v2 MUST expose one user-facing `Code Block` palette item.
- FR-002: CodeBlock v2 MUST remove inline code execution from block config.
- FR-003: CodeBlock v2 MUST remove SciStudio entry-function mode from block
  config.
- FR-004: CodeBlock v2 MUST require the configured script path to resolve
  inside the project directory.
- FR-005: Script path validation MUST resolve symlinks before accepting the
  path.
- FR-006: CodeBlock v2 MUST use file delivery mode only.
- FR-007: Every run MUST allocate a block-scoped exchange directory under the
  configured exchange root.
- FR-008: Every input and output port MUST have a dedicated folder under
  `inputs/` or `outputs/`.
- FR-009: Input materialisation MUST complete before the interpreter process is
  launched.
- FR-010: Output port folders MUST be created before process launch.
- FR-011: Input ports MUST resolve ADR-043 saver capabilities before execution.
- FR-012: Output ports MUST resolve ADR-043 loader capabilities before
  execution.
- FR-013: Ambiguous capability selection MUST fail unless `capability_id` is
  supplied.
- FR-014: Workflow config MAY omit `capability_id` only when capability lookup
  has exactly one deterministic match.
- FR-015: Collection inputs MUST materialise each item as one file under the
  port folder.
- FR-016: Single-object inputs MUST still use the same port folder contract.
- FR-017: Output collection MUST inspect only declared output port folders.
- FR-018: Files directly under the output root or unknown folders MUST be
  ignored with warnings.
- FR-019: Files in a declared output folder with the wrong extension MUST be
  ignored with warnings.
- FR-020: Required output ports MUST fail if no matching files are produced.
- FR-021: Optional output ports MAY return an empty collection when no matching
  files are produced.
- FR-022: Multiple output ports MAY use the same extension because folder
  placement determines the port.
- FR-023: Interpreter resolution MUST support `auto` and `existing` modes.
- FR-024: `auto` mode MUST be deterministic for a fixed project state.
- FR-025: `existing` mode MUST record the selected executable or environment
  path.
- FR-026: The MVP MUST support plain `.py` scripts.
- FR-027: Notebook support MUST capture executed artifacts as `Artifact`
  outputs.
- FR-028: CodeBlock runs MUST record script provenance, interpreter resolution,
  environment snapshot, capability selections, and exchange manifest in
  lineage-owned runtime metadata.
- FR-029: CodeBlock MUST NOT add format-specific type logic, extension alias
  guessing, or semantic conversion rules.
- FR-030: The frontend MUST display exchange-relative read/write folders for
  each declared port.
- FR-031: The frontend MUST persist selected `capability_id` values when user
  selection is needed.
- FR-032: Legacy inline/function CodeBlock configs MUST receive explicit
  migration diagnostics.
- FR-033: Process cancellation MUST terminate or signal the interpreter using
  the existing external-process lifecycle where possible.
- FR-034: CodeBlock v2 MUST preserve AppBlock's file-exchange security
  posture, including project-root path validation and controlled process
  command construction.

### Non-Functional Requirements

- NFR-001: The Python-script MVP should add no format dispatch behavior beyond
  ADR-043 capability calls.
- NFR-002: Exchange folder names and generated filenames MUST be deterministic
  for the same workflow run inputs.
- NFR-003: Capability and validation errors MUST name the port, direction,
  declared type, extension, and capability candidates where available.
- NFR-004: Interpreter resolution errors MUST distinguish missing executable,
  unsupported extension, unsafe path, and environment snapshot failure.
- NFR-005: Output collection MUST be sorted deterministically by port and path.
- NFR-006: Large input materialisation should stream or delegate to existing
  materialisation helpers instead of eagerly loading payloads into memory.
- NFR-007: UI guidance may inspect script text, but it MUST NOT rewrite scripts
  without explicit user action.
- NFR-008: The implementation must remain testable without requiring R, Quarto,
  MATLAB, or system notebooks in the base CI job; optional interpreters use
  skipped or separately marked integration tests until CI images include them.

### Key Entities

| Entity | Description | Required attributes | Relationships |
|---|---|---|---|
| `CodeBlockConfig` | Persisted block configuration | script path, interpreter mode, environment config, port file configs | Owned by workflow config |
| `PortFileConfig` | File exchange contract for one port | port name, direction, data type, extension, capability id, required flag, folder | Used by validation and exchange prep |
| `CodeBlockExchangeManifest` | Runtime record of concrete exchange paths | run id, block id, exchange root, port folders, materialised files, collected files, warnings | Recorded in lineage/runtime metadata |
| `ResolvedInterpreter` | Safe interpreter command | family, executable, argv prefix, working directory, environment variables, version evidence | Produced before process launch |
| `EnvironmentSnapshot` | Reproducibility context | mode, interpreter path, version, package listing, lockfile evidence, warnings | Stored in lineage-owned metadata |
| `ScriptProvenance` | Source identity for the selected script | project-relative path, resolved path, git tracked state, commit evidence, content hash | Stored with each run |
| `OutputCollectionPlan` | Port-specific reconstruction plan | port folder, extension, target type, loader capability, required flag | Consumed after process exit |
| `MigrationDiagnostic` | Legacy CodeBlock migration result | legacy mode, severity, message, suggested target | Displayed by validator/UI |

## 4. Implementation Plan

### 4.1 Technical Approach

Implement CodeBlock v2 by extracting script-specific behavior into narrow
helpers while reusing AppBlock's external process and file-exchange lifecycle.
The CodeBlock class should coordinate:

1. config validation;
2. project-local script provenance capture;
3. interpreter resolution;
4. exchange directory preparation;
5. process launch and cancellation;
6. output collection;
7. lineage metadata emission.

Format work stays outside CodeBlock. Input materialisation calls
`materialise_to_file(..., capability_id=...)`; output reconstruction calls
`reconstruct_from_file(..., capability_id=...)`. Capability lookup, ambiguity,
and metadata fidelity warnings come from ADR-043 surfaces.

The implementation should prefer composition over inheriting every AppBlock
detail if literal subclassing creates awkward config coupling. A shared
external-boundary helper is acceptable as long as AppBlock and CodeBlock use
the same validation, exchange, and materialisation semantics.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/blocks/code/code_block.py` | rewrite or replace | Move CodeBlock to v2 script-as-external-boundary behavior |
| `src/scistudio/blocks/code/config.py` | create | Typed CodeBlock v2 config, port file config, migration diagnostics |
| `src/scistudio/blocks/code/exchange.py` | create | Prepare exchange folders and collect output files |
| `src/scistudio/blocks/code/interpreters.py` | create | Resolve script interpreter and environment mode |
| `src/scistudio/blocks/code/provenance.py` | create | Capture script source hash, git evidence, and environment snapshot |
| `src/scistudio/blocks/code/validation.py` | create | Validate script path, ports, capabilities, and migration state |
| `src/scistudio/blocks/code/runners/**` | modify | Retire or adapt entry-function runners behind interpreter execution |
| `src/scistudio/blocks/app/bridge.py` | modify if needed | Share AppBlock boundary helpers with CodeBlock |
| `src/scistudio/blocks/app/app_block.py` | modify if needed | Keep AppBlock and CodeBlock capability validation aligned |
| `src/scistudio/engine/materialisation.py` | modify if needed | Ensure capability-aware file read/write supports CodeBlock exchange |
| `src/scistudio/workflow/validator.py` | modify | Add early CodeBlock v2 boundary validation and legacy diagnostics |
| `src/scistudio/api/routes/blocks.py` | modify if needed | Expose CodeBlock config schema and capability choices |
| `frontend/src/components/**` | modify | Config panel, port exchange guidance, script path warnings |
| `frontend/src/store/**` | modify if needed | Persist CodeBlock capability and exchange config state |
| `docs/block-development/**` | modify | Document script-as-block usage and migration guidance |
| `docs/architecture/ARCHITECTURE.md` | modify if behavior text changes | Keep architecture docs aligned with implemented CodeBlock v2 |

### 4.3 Implementation Sequence

1. Define config and validation models:
   - `CodeBlockConfig`;
   - `PortFileConfig`;
   - interpreter/environment config;
   - `MigrationDiagnostic`;
   - script path validation.
2. Add exchange manifest helpers:
   - create block-scoped exchange root;
   - create per-port folders;
   - resolve folder collisions;
   - materialise input objects with ADR-043 saver capabilities;
   - collect matching output files per port.
3. Add Python-script MVP:
   - resolve `.py` interpreter in `auto` and `existing` modes;
   - launch process in the block exchange directory;
   - propagate process stdout/stderr and exit status through existing runner
     result surfaces;
   - reconstruct typed outputs.
4. Add workflow validation:
   - validate CodeBlock ports before execution;
   - fail missing/ambiguous capabilities;
   - emit legacy inline/function migration diagnostics.
5. Add provenance and lineage capture:
   - script relative path;
   - content hash or git evidence;
   - interpreter command and version;
   - environment snapshot;
   - exchange manifest and selected capabilities.
6. Add frontend MVP:
   - script picker restricted to project-local paths;
   - interpreter mode controls;
   - port table with type, extension, capability, required flag;
   - copyable exchange path guidance;
   - absolute path warnings.
7. Add notebook support:
   - `.ipynb` execution through nbconvert or a local Jupyter runner;
   - executed notebook artifact capture;
   - partial artifact retention on failure when available.
8. Add additional interpreter families in separate issues:
   - `.R` and `.Rmd`;
   - `.qmd`;
   - `.sh`;
   - `.m` and `.mlx`.
9. Update documentation:
   - block-development guide;
   - migration notes from legacy CodeBlock modes;
   - architecture text if implementation chooses composition over subclassing.

### 4.4 Phase Breakdown

| Phase | Deliverable | Minimum tests | Exit criteria |
|---|---|---|---|
| 1 | Config, validation, and exchange skeleton | config schema, unsafe paths, folder layout | Can validate a CodeBlock v2 config without launching a process |
| 2 | Python-script MVP | materialise input, run fixture script, collect typed output | `.py` scripts work through file exchange in local tests |
| 3 | ADR-043 boundary validation | missing, ambiguous, explicit capability cases | Invalid ports fail before process launch |
| 4 | Provenance and lineage | script hash, git state, interpreter snapshot | Run records include reproducibility metadata |
| 5 | Frontend MVP | config rendering, persisted capability id, warnings | User can configure a script block without editing YAML |
| 6 | Notebook artifact support | executed notebook output, failure retention | `.ipynb` produces `_executed_notebook` artifact |
| 7 | Legacy migration diagnostics | inline/function fixtures | Legacy behavior is blocked or migrated explicitly |
| 8 | Additional interpreters | optional integration tests | Each interpreter family lands independently |

### 4.5 Verification Plan

- Run unit tests for config parsing and validation.
- Run path-safety tests for project-local, traversal, symlink, and outside-root
  script paths.
- Run exchange tests for single object, collection, folder collisions, same
  extension on multiple output ports, wrong-extension warnings, and missing
  required outputs.
- Run capability validation tests for unique, missing, ambiguous, and explicit
  selections.
- Run Python execution integration tests with fixture scripts and temporary
  projects.
- Run cancellation tests against a long-running fixture script.
- Run provenance tests for tracked, untracked, and modified scripts.
- Run frontend tests for config panel rendering, capability persistence, and
  path-warning UI.
- Run notebook tests behind an optional dependency marker or CI image that
  includes Jupyter.
- Run existing AppBlock and materialisation tests to ensure shared boundary
  behavior is not regressed.

### 4.6 Signature-Level Contracts

The exact implementation may split helpers differently, but downstream code
and tests should target equivalent public responsibilities.

```python
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, Field

from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


PortDirection = Literal["input", "output"]
InterpreterMode = Literal["auto", "existing"]


class PortFileConfig(BaseModel):
    name: str
    direction: PortDirection
    data_type: str
    extension: str
    capability_id: str | None = None
    required: bool = True
    exchange_folder: str | None = None


class CodeBlockConfig(BaseModel):
    script_path: str
    interpreter_mode: InterpreterMode = "auto"
    interpreter_path: str | None = None
    environment: Mapping[str, Any] = Field(default_factory=dict)
    inputs: list[PortFileConfig] = Field(default_factory=list)
    outputs: list[PortFileConfig] = Field(default_factory=list)
```

```python
class ResolvedInterpreter(BaseModel):
    family: str
    executable: str
    argv: list[str]
    working_directory: str
    environment: Mapping[str, str] = Field(default_factory=dict)
    version: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ScriptProvenance(BaseModel):
    relative_path: str
    content_sha256: str
    git_commit: str | None = None
    git_status: Literal["tracked-clean", "tracked-modified", "untracked"]
    resolved_path: str


class CodeBlockExchangeManifest(BaseModel):
    exchange_root: str
    input_folders: Mapping[str, str]
    output_folders: Mapping[str, str]
    materialised_inputs: Mapping[str, list[str]] = Field(default_factory=dict)
    collected_outputs: Mapping[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
```

```python
def validate_codeblock_config(
    config: CodeBlockConfig,
    *,
    project_dir: Path,
    registry: BlockRegistry,
) -> list[Exception]:
    ...


def resolve_script_interpreter(
    script_path: Path,
    *,
    environment_config: Mapping[str, Any],
    project_dir: Path,
    mode: InterpreterMode = "auto",
    interpreter_path: Path | None = None,
) -> ResolvedInterpreter:
    ...


def capture_script_provenance(
    script_path: Path,
    *,
    project_dir: Path,
) -> ScriptProvenance:
    ...
```

```python
def prepare_codeblock_exchange(
    inputs: Mapping[str, DataObject | Collection],
    port_configs: Sequence[PortFileConfig],
    *,
    exchange_dir: Path,
    registry: BlockRegistry,
) -> CodeBlockExchangeManifest:
    ...


def collect_codeblock_outputs(
    port_configs: Sequence[PortFileConfig],
    *,
    exchange_manifest: CodeBlockExchangeManifest,
    registry: BlockRegistry,
) -> dict[str, Collection]:
    ...
```

### 4.7 Legacy Migration Plan

Legacy CodeBlock configs should not be rewritten silently. The implementation
should provide a validator or migration helper that classifies each legacy
config:

| Legacy shape | Automatic action | User-facing guidance |
|---|---|---|
| Inline code | block loading fails with migration diagnostic | Move logic to a ProcessBlock/custom block or save it as a project script |
| Entry-function script | migration suggestion only | Keep as ProcessBlock/custom block or adapt to file exchange |
| Existing script path inside project | optional suggested v2 config | Review generated input/output file folders before saving |
| Script path outside project | blocking diagnostic | Copy or symlink into the project first |

The UI may offer a migration wizard, but the runtime validator remains the
authority. Migration diagnostics should include issue/spec references so
reviewers can distinguish intentional removals from accidental regressions.

## 5. Acceptance Criteria

- AC-001: CodeBlock v2 exposes one palette item and no inline/function mode
  controls.
- AC-002: Project-local script validation rejects traversal and symlink escape
  paths.
- AC-003: A `.py` fixture script runs through AppBlock-style file exchange and
  returns typed outputs reconstructed through ADR-043 capabilities.
- AC-004: Missing or ambiguous input saver capabilities fail before process
  launch.
- AC-005: Missing or ambiguous output loader capabilities fail before process
  launch.
- AC-006: Multiple output ports with the same extension are routed by folder,
  not by extension alone.
- AC-007: Required empty output folders fail; optional empty output folders do
  not fail.
- AC-008: Lineage records script provenance, interpreter resolution,
  environment snapshot, selected capabilities, and exchange manifest.
- AC-009: The frontend shows copyable `inputs/<port>/` and `outputs/<port>/`
  guidance for every configured port.
- AC-010: The frontend persists `capability_id` when the user selects among
  multiple matching capabilities.
- AC-011: `.ipynb` execution captures an executed notebook `Artifact` when
  notebook support is enabled.
- AC-012: Legacy inline/function configs produce explicit migration diagnostics
  rather than silently running under new semantics.
- AC-013: Block-development documentation includes CodeBlock v2 script usage,
  path adaptation examples, and migration guidance.
- AC-014: Existing AppBlock capability and materialisation tests remain green.

## 6. Risks And Rollback

The main architecture risk is duplicating AppBlock's boundary behavior inside
CodeBlock. Mitigate this by sharing exchange, materialisation, reconstruction,
and process lifecycle helpers wherever the AppBlock contracts already fit.

The second risk is reintroducing implicit format guessing. CodeBlock must call
ADR-043 capability APIs and fail on missing or ambiguous choices instead of
guessing extension aliases or accepting parent-type conversions silently.

The third risk is breaking existing CodeBlock users. Mitigate this with
explicit migration diagnostics, documentation, and a staged release note. Do
not silently reinterpret inline/function configs as script-mode configs.

Rollback should be straightforward for Phase 1 and Phase 2: keep legacy
CodeBlock behind a feature flag or compatibility branch until the v2 MVP and
migration diagnostics are ready. After legacy mode is removed, rollback
requires restoring the previous CodeBlock implementation and disabling v2
schema validation.

## 7. Assumptions

- ADR-043 capability APIs are available before CodeBlock v2 hard validation
  ships.
- Python-script support is the first executable MVP because it is available in
  the project runtime and can run in base CI.
- R, Quarto, Bash, MATLAB, and Octave support land as separate follow-up issues
  after the Python MVP proves the shared boundary contract.
- Environment snapshots may initially use interpreter-specific best-effort
  commands; missing optional snapshot evidence is a warning unless the selected
  environment mode requires it.
- The exact lineage storage field for environment snapshots may be chosen
  during implementation, but it must remain lineage-owned runtime metadata and
  not typed object `meta`.
