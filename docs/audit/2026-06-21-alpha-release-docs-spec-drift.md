---
doc_type: audit
title: "Alpha Release Docs/Spec Drift Audit"
status: complete
owner: "@jiazhenz026"
date: 2026-06-21
persona: audit_reviewer
audit_mode: no-context
recommendation: block
---

# Alpha Release Docs/Spec Drift Audit

## 1. Change Summary

Recommendation: **block**.

This no-context audit checked whether core runtime ADRs, specs, architecture
docs, code, and tests agree across the allowed audit surfaces. I did not use
current issue, PR, checklist, dispatch-prompt, commit-message, chat-summary, or
manager-summary context. I did not run the gate ledger because this audit's
write set was restricted to this report file only, while gate commands write
committed ledger evidence under `.workflow/records/`.

### P1 - Blocker - ADR-044 SubWorkflow contract is not implemented, and tests assert the rejected runtime model

ADR-044 is `Accepted`, code-implementation scoped, and describes
`SubWorkflowBlock` as authoring-only. It says the existing runtime stub,
`_scheduler_factory`, `_cleanup_callback`, `_run_with_scheduler`,
`_sequential_execute`, `input_mapping`, `output_mapping`, and tests asserting
those semantics are deleted or replaced
(`docs/adr/ADR-044.md:87`, `docs/adr/ADR-044.md:97`,
`docs/adr/ADR-044.md:153`, `docs/adr/ADR-044.md:158`,
`docs/adr/ADR-044.md:303`). It also requires
`WorkflowDefinition.flatten_subworkflows()` and exactly one run-start call site
(`docs/adr/ADR-044.md:161`, `docs/adr/ADR-044.md:170`).

The implementation still does the opposite. `SubWorkflowBlock` is documented as
"runs an entire workflow as a single block" and retains the scheduler factory,
cleanup callback, executable `run()`, `_run_with_scheduler`, and
`_sequential_execute` surfaces (`src/scistudio/blocks/subworkflow/subworkflow_block.py:1`,
`:26`, `:48`, `:53`, `:78`, `:142`, `:157`). `WorkflowDefinition` has only the
dataclass fields and no flattening API (`src/scistudio/workflow/definition.py:36`).
`ApiRuntime.start_workflow` loads and validates the authored workflow, with no
subworkflow flattening step before dispatch (`src/scistudio/api/runtime/_runs.py:302`).

The tests reinforce the pre-ADR behavior: `tests/blocks/test_subworkflow.py`
imports `_sequential_execute`, asserts child block execution, asserts scheduler
factory injection, and asserts fallback sequential execution
(`tests/blocks/test_subworkflow.py:1`, `:12`, `:60`, `:82`, `:113`, `:150`).
The targeted command
`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest --no-cov -q -p no:cacheprovider tests/blocks/test_subworkflow.py`
passed all 13 tests, which confirms the active test suite currently protects
the runtime behavior that ADR-044 rejects.

This blocks release readiness because docs/specs tell reviewers, users, and
future agents that SubWorkflow runtime risk was removed, while the code and
tests still carry the nested-execution stub and no flattener exists.

Required fix: either implement ADR-044 end to end, including flattening,
authoring-only `SubWorkflowBlock`, validator/run-start behavior, and replacement
tests, or supersede/update ADR-044 and its spec to match the currently shipped
nested-runtime semantics.

### P2 - Architecture project tree still documents deleted ViewProxy and old nested-subworkflow runtime

ADR-031 says `ViewProxy` is deleted and there is no `DataObject.view()` path
(`docs/adr/ADR-031.md:235`, `docs/adr/ADR-031.md:237`,
`docs/adr/ADR-031.md:249`). The source tree agrees:
`src/scistudio/core/proxy.py` does not exist. However
`docs/architecture/PROJECT_TREE.md` still lists `core/proxy.py` as a
ViewProxy injected into `block.run()` inputs (`docs/architecture/PROJECT_TREE.md:83`)
and still lists `tests/core/test_proxy.py` as current test structure
(`docs/architecture/PROJECT_TREE.md:579`).

The same target tree also describes `tests/blocks/test_subworkflow.py` as
"Nested workflow execution, input/output mapping" and
`test_subworkflow_nesting.py` as recursive SubWorkflowBlock composition
(`docs/architecture/PROJECT_TREE.md:591`, `docs/architecture/PROJECT_TREE.md:637`),
which conflicts with ADR-044's authoring-only model. This is a lower-severity
docs drift than P1 because it is a tree/reference document, but it undermines
architecture auditability for core runtime surfaces.

Required fix: update or clearly mark `PROJECT_TREE.md` as obsolete/target-only
where it names removed ViewProxy and rejected nested-subworkflow behavior.

### P2 - CodeBlock test/docs evidence still mixes ADR-041 v2 with legacy inline/function runner surfaces

ADR-041 says CodeBlock v2 removes inline code execution and function mode
(`docs/adr/ADR-041.md:96`, `docs/adr/ADR-041.md:223`). The runtime does reject
legacy CodeBlock configs through migration diagnostics
(`src/scistudio/blocks/code/code_block.py:375`). Targeted tests for CodeBlock
v2 and legacy rejection passed:
`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest --no-cov -q -p no:cacheprovider tests/blocks/test_code_block.py tests/blocks/code/test_codeblock_v2_config.py tests/workflow/test_validator_codeblock_v2.py`.

However, `tests/blocks/test_code_block.py` is still titled and structured
around inline Python and importlib entry-function script execution
(`tests/blocks/test_code_block.py:1`, `:14`, `:49`). ADR-041 frontmatter also
lists a non-existent path, `tests/blocks/code/test_code_block.py`, while the
legacy aggregate file lives at `tests/blocks/test_code_block.py`. This is not a
direct user-facing runtime failure, but it is release-relevant test drift:
future audits cannot tell whether the old runner helpers are intentional
compatibility internals, temporary soak leftovers, or stale test coverage.

Required fix: either retitle/scope legacy runner helper tests as compatibility
internals with a tracked cleanup reference, or move/update coverage so ADR-041's
test evidence names current CodeBlock v2 files.

### P3 - IO capability roundtrip contract has tracked xfail drift for save-only JSON groups

The ADR-043 spec says lossless round-trip groups must have both loader and saver
capabilities unless a format is one-way and does not claim losslessness
(`docs/specs/adr-043-io-format-capability-registry.md:287`). Core save
capability construction always assigns a `roundtrip_group`
(`src/scistudio/blocks/io/savers/_capability.py:78`). Series JSON and Text JSON
are save-only (`src/scistudio/blocks/io/savers/_capability.py:194`,
`src/scistudio/blocks/io/savers/_capability.py:235`) and the contract test keeps
both as expected failures under issue `#1454`
(`tests/contracts/test_io_capability_contract.py:105`).

The targeted contract suite passed with the two expected xfails:
`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest --no-cov -q -p no:cacheprovider tests/docs/test_block_development_docs.py tests/contracts/test_runtime_import_contract.py tests/contracts/test_io_capability_contract.py tests/workflow/test_validator.py tests/api/test_runtime_workflow_validation_gate.py`.

Good-to-fix: resolve the xfails by either adding matching loaders, removing or
recategorizing the misleading roundtrip groups for one-way formats, or updating
the spec/test contract to distinguish one-way `pixel_only` capability groups
from real round-trip claims.

## 2. Checks Run

- `git status --short --branch`
- `rg --files docs/adr docs/specs docs/architecture docs/block-development src/scistudio/workflow src/scistudio/engine src/scistudio/blocks src/scistudio/core src/scistudio/api src/scistudio/ai tests`
- Targeted `rg` searches for `SubWorkflowBlock`, `flatten_subworkflows`,
  `ViewProxy`, `gate_receipt`, stale runtime paths, stale test paths, and IO
  capability roundtrip groups.
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python ...` active ADR/spec
  frontmatter scan for missing governed files, tests, modules, and contracts:
  result was 1 missing governed file, 23 missing test paths, 0 missing modules,
  0 missing contracts. Core-relevant rows are reflected in findings above.
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python ...` runtime introspection:
  `WorkflowDefinition.flatten_subworkflows False`,
  `SubWorkflowBlock.run_is_defined True`,
  `SubWorkflowBlock.has_scheduler_factory True`,
  `SubWorkflowBlock.has_cleanup_callback True`.
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest --no-cov -q -p no:cacheprovider tests/blocks/test_subworkflow.py`
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest --no-cov -q -p no:cacheprovider tests/docs/test_block_development_docs.py tests/contracts/test_runtime_import_contract.py tests/contracts/test_io_capability_contract.py tests/workflow/test_validator.py tests/api/test_runtime_workflow_validation_gate.py`
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest --no-cov -q -p no:cacheprovider tests/qa/test_audit_doc_drift.py tests/qa/test_audit_signature_contracts.py tests/qa/test_architecture_drift.py`
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 pytest --no-cov -q -p no:cacheprovider tests/blocks/test_code_block.py tests/blocks/code/test_codeblock_v2_config.py tests/workflow/test_validator_codeblock_v2.py`

Note: the same pytest subsets initially failed without `--no-cov` only because
the repository-wide coverage threshold applies to small targeted subsets. The
reruns above disabled coverage for audit-targeted evidence and passed.

## 3. Recommendation

**Block** alpha release readiness until the ADR-044/SubWorkflow mismatch is
resolved. The accepted runtime contract, implementation, and tests currently
describe different products.
