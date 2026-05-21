# ADR-042 Documentation Generation Tooling Checklist

Tracking issue: #1314

This checklist records the current rollout state for ADR-042 documentation
generation and adjacent QA tooling. It is evidence-only tracking; the governing
contracts remain `docs/adr/ADR-042.md`,
`docs/specs/adr-042-documentation-tools.md`, and the related ADR-042 specs.

## Conventions

- `[x]` implemented and wired to at least one runnable workflow.
- `[~]` implemented but not fully wired to the ADR-042 target pipeline.
- `[ ]` specified by ADR-042/specs but not implemented in the repository.
- Evidence paths name current implementation or the absence observed during the
  2026-05-21 audit for #1314.

## ADR-042 Generated Documentation Targets

| Status | Target | ADR-042 source | Current evidence | Follow-up |
|---|---|---|---|---|
| [ ] | Python API reference at `docs/user/reference/api/` | `docs/adr/ADR-042.md` Section 6.3 | No `docs/user/` tree; no Sphinx config found. | Implement Sphinx/griffe-backed API reference generator. |
| [ ] | Schema reference at `docs/user/reference/schemas/` | `docs/adr/ADR-042.md` Section 6.3 | No `src/scistudio/qa/docs/schema_reference.py`; no generated target. | Implement Pydantic schema reference generator. |
| [ ] | CLI reference at `docs/user/reference/cli.md` | `docs/adr/ADR-042.md` Section 6.3 | No `src/scistudio/qa/docs/cli_reference.py`; no generated target. | Implement Typer command-tree reference generator. |
| [ ] | Server API reference at `docs/user/reference/server-api.md` | `docs/adr/ADR-042.md` Section 6.3 | No `src/scistudio/qa/docs/openapi_reference.py`; no generated target. | Implement FastAPI OpenAPI reference generator. |
| [ ] | Entry-point catalog at `docs/user/reference/entry-points.md` | `docs/adr/ADR-042.md` Section 6.3 | No `src/scistudio/qa/docs/entry_point_catalog.py`; no generated target. | Implement `importlib.metadata.entry_points()` catalog generator. |
| [ ] | Block catalog at `docs/user/reference/blocks/` | `docs/adr/ADR-042.md` Section 6.3 | No `src/scistudio/qa/docs/block_catalog.py`; no generated target. | Implement block-registry catalog generator. |
| [ ] | Runner catalog at `docs/user/reference/runners/` | `docs/adr/ADR-042.md` Section 6.3 | No `src/scistudio/qa/docs/runner_catalog.py`; no generated target. | Implement runner-registry catalog generator. |
| [ ] | Tutorial gallery under `docs/user/tutorials/` and `docs/user/examples-gallery/` | `docs/adr/ADR-042.md` Section 6.3 | No `sphinx-gallery` wiring or generated gallery target found. | Decide rollout timing after Sphinx docs root exists. |
| [ ] | LLM context file at `docs/user/llms.txt` | `docs/adr/ADR-042.md` Section 6.3 | No `src/scistudio/qa/docs/llms_txt.py`; no `docs/user/llms.txt`. | Implement deterministic `llms.txt` generator. |
| [~] | Facts registry at `docs/facts/generated.yaml` | `docs/adr/ADR-042.md` Section 6.3 | `scripts/audit/generate_facts.py` and `scistudio.qa.audit.facts` exist; `docs/facts/generated.yaml` is absent in this checkout. | Decide whether generated facts should be committed or produced only as gate evidence. |

## ADR-042 Documentation Tooling

| Status | Tool | ADR/spec source | Current evidence | Follow-up |
|---|---|---|---|---|
| [x] | `frontmatter_lint` | `docs/specs/adr-042-documentation-tools.md` FR-001..FR-005 | `src/scistudio/qa/audit/frontmatter_lint.py`; `tests/qa/test_audit_frontmatter_lint.py`; included by `full_audit`. | None for current slice. |
| [ ] | `doc_length_lint` | `docs/specs/adr-042-documentation-tools.md` FR-006..FR-007 | No `src/scistudio/qa/audit/doc_length_lint.py`; no `tests/qa/test_doc_length_lint.py`. | Implement report-only first, then hard-fail per ADR-042 rollout. |
| [ ] | `auto_generated_lint` | `docs/specs/adr-042-documentation-tools.md` FR-008..FR-009 | No `src/scistudio/qa/audit/auto_generated_lint.py`; no generated-doc manifest. | Implement after at least one deterministic generated-doc target exists. |
| [ ] | `skill_pointer_sync` | `docs/specs/adr-042-documentation-tools.md` FR-012 | No `src/scistudio/qa/audit/skill_pointer_sync.py`; no `tests/qa/test_skill_pointer_sync.py`. | Implement pointer parity checks for `.agents/`, `.claude/`, and `.codex/`. |
| [ ] | Generated-doc manifest | `docs/specs/adr-042-documentation-tools.md` Section 4.5 | No `docs/user/reference/generated-docs.yaml`. | Add manifest schema with generator id, target path, inputs, and source hash. |
| [ ] | Sphinx build with warnings as errors | `docs/adr/ADR-042.md` Sections 6.4..6.7 | No `docs/sphinx/conf.py`; no Sphinx dependencies in `pyproject.toml`; no docs-build CI job. | Add docs build only after generated references are deterministic. |
| [ ] | ADR-042 generation pipeline order | `docs/adr/ADR-042.md` Section 6.5 | No pipeline currently runs facts -> references -> `llms.txt` -> Sphinx -> generated-doc lint -> drift checks. | Add a single documented command and CI job once missing generators land. |

## Implemented Consistency Tools Relevant To Documentation

| Status | Tool | Current evidence | Wiring state |
|---|---|---|---|
| [x] | `griffe_facts` | `src/scistudio/qa/audit/griffe_facts.py`; `tests/qa/test_griffe_facts.py`. | Used by `generate_facts`. |
| [~] | `generate_facts` | `src/scistudio/qa/audit/facts.py`; `scripts/audit/generate_facts.py`; `tests/qa/test_generate_facts_cli.py`. | Runnable and used by `full_audit`; generated target is absent from the tree. |
| [x] | `fact_drift` | `src/scistudio/qa/audit/fact_drift.py`; `tests/qa/test_audit_fact_drift.py`. | Included by `full_audit`. |
| [x] | `doc_drift` | `src/scistudio/qa/audit/doc_drift.py`; `tests/qa/test_audit_doc_drift.py`. | Included by `full_audit`. |
| [x] | `closure` | `src/scistudio/qa/audit/closure.py`; `tests/qa/test_audit_closure.py`. | Included by `full_audit`. |
| [x] | `signature_drift` | `src/scistudio/qa/audit/signature_drift.py`; `tests/qa/test_audit_signature_drift.py`. | Included by `full_audit`. |
| [x] | `architecture_drift` | `src/scistudio/qa/audit/architecture_drift.py`; `tests/qa/test_architecture_drift.py`. | Included by `full_audit` via ADR-042 Addendum 1 work. |
| [x] | `full_audit` | `src/scistudio/qa/audit/full_audit.py`; `tests/qa/test_audit_full_audit.py`. | Runnable CLI; gate workflow validates recorded full-audit evidence. |
| [x] | `vulture_audit` | `src/scistudio/qa/audit/vulture_audit.py`; `tests/qa/test_audit_vulture.py`; `vulture_allowlist.py`; `[tool.vulture]` config in `pyproject.toml`. | Included by `full_audit` as informational child report (#1340). Reports WARNING-severity findings; never sets `blocks_merge` in v1. |

## Adjacent ADR-042 Tooling Not Yet In Documentation Pipeline

| Status | Tool family | Current evidence | Note |
|---|---|---|---|
| [x] | Gate records and PR workflow guards | `src/scistudio/qa/governance/gate_record.py`; `.github/workflows/workflow-gate.yml`; `.pre-commit-config.yaml`; `tests/qa/test_gate_record*.py`. | Implemented by ADR-042 Addendum 1, not a docs generator. |
| [x] | Docs landing guard | `src/scistudio/qa/governance/docs_landing.py`; `tests/qa/test_docs_landing.py`; workflow-gate orchestration. | Enforces docs evidence in gate records. |
| [ ] | `complete_artifacts`, `codemod_lint`, `trailer_lint`, `committer_enforce` | Listed in `docs/specs/adr-042-ai-governance-tools.md`; no corresponding modules found. | Track separately from documentation generation. |
| [~] | `code_score` and `test_quality` | Listed in `docs/specs/adr-042-code-quality-tools.md`; `code_score` and `test_quality` modules still absent. `vulture` (also listed as standard tool in same spec, lines 22 + 64) is now wired through `vulture_audit` (#1340). | Track `code_score` and `test_quality` separately. |

## Open Follow-Ups

- [ ] Create an implementation issue for `doc_length_lint`,
      `auto_generated_lint`, and generated-doc manifest rollout.
- [ ] Create an implementation issue for `src/scistudio/qa/docs/**`
      generators: `llms_txt`, `entry_point_catalog`, `cli_reference`,
      `openapi_reference`, `schema_reference`, `block_catalog`, and
      `runner_catalog`.
- [ ] Create an implementation issue for Sphinx docs root and docs-build CI
      once at least one generated reference target is deterministic.
- [ ] Decide whether `docs/facts/generated.yaml` should be committed as
      canonical generated evidence or kept out of tree and produced in gate/CI.
