# ADR-042 Tool Configuration Checklist

## 1. Change Summary

This checklist tracks repository configuration for ADR-042 tools. It separates
implemented tools, partially implemented tools, future custom tools, and manual
or scheduled tools so CI/pre-commit wiring can be completed without treating
new failures as bugs to hide.

## 2. Common Automated Tools

| Tool | Configuration target | CI placement | Pre-commit placement | Status |
|---|---|---|---|---|
| `ruff check` | `pyproject.toml` | `lint` | yes | configured |
| `ruff format` | `pyproject.toml` | `lint` | yes | configured |
| `mypy` | `pyproject.toml` | `typecheck` | yes | configured |
| `pyright` | `pyrightconfig.json` | `typecheck` | no | configured |
| `pytest` | `pyproject.toml` | `test` | no | configured |
| `pytest-xdist` | `pyproject.toml` | `test` | no | configured |
| `pytest-timeout` | `pyproject.toml` | `test` | no | configured |
| `pytest-randomly` | `pyproject.toml` | `test` | no | configured |
| `pytest-cov` / `coverage` | `pyproject.toml` | `test` | no | configured |
| `import-linter` | `pyproject.toml` | `import-boundaries` | no | configured |
| `griffe` / `griffe-pydantic` | `pyproject.toml` | `audit` | no | configured |
| `interrogate` | `pyproject.toml` | `audit` | no | configured |
| `pydoclint` | `pyproject.toml` | `audit` | no | configured |
| `vulture` | `pyproject.toml` | `audit` | no | configured |
| `xenon` | CI args | `audit` | no | configured |
| `mutmut` | `pyproject.toml` | scheduled/manual | no | configured |
| `libcst` | `pyproject.toml` | future codemod audit | no | dependency configured |
| `pydantic-settings` | `pyproject.toml` | future settings schema tests | no | dependency configured |
| `pip-audit` | `pyproject.toml` | `security` | no | configured |
| `bandit` | `pyproject.toml` | `security` | no | configured |
| `codespell` | `.codespellrc` | `lint` | yes | configured |
| `yamllint` | `.yamllint` | `lint` | yes | configured |
| `pyproject-fmt` | `pyproject.toml` | `lint` | yes | configured |
| `actionlint` | pre-commit/CI install | `workflow-lint` | yes | configured |
| `zizmor` | pre-commit/CI install | `workflow-lint` | yes | configured |
| `eslint` | `frontend/package.json` | `frontend` | yes | configured |
| `prettier` | `frontend/package.json` | `frontend` | yes | configured |
| `tsc --noEmit` | `frontend/package.json` | `frontend` | no | configured |
| `vitest` | `frontend/package.json` | `frontend` | no | configured |
| `vite build` | `frontend/package.json` | `frontend` | no | configured |
| `typedoc` | `frontend/package.json` | `docs-build` | no | configured |

## 3. Documentation Build Tools

| Tool | Configuration target | CI placement | Status |
|---|---|---|---|
| `markdownlint-cli2` | `.markdownlint.yaml` | `docs-build` | configured |
| `sphinx-lint` | `docs/sphinx/conf.py` | `docs-build` | configured |
| `sphinx-build -W --keep-going --nitpicky` | `docs/sphinx/conf.py` | `docs-build` | configured |
| Sphinx `linkcheck` | `docs/sphinx/conf.py` | `docs-build` | configured |
| `pytest-examples` | `pyproject.toml` | docs dependency | configured |
| `sphinx-gallery` | `docs/sphinx/conf.py` | `docs-build` | configured |
| `sphinx-autoapi` / `autosummary` / `numpydoc` | `docs/sphinx/conf.py` | `docs-build` | configured |
| `autodoc-pydantic` | `docs/sphinx/conf.py` | `docs-build` | configured |
| `sphinx-click` | `docs/sphinx/conf.py` | `docs-build` | configured |
| `sphinxcontrib-openapi` | `docs/sphinx/conf.py` | `docs-build` | configured |
| `pydata-sphinx-theme` / UX extensions | `docs/sphinx/conf.py` | `docs-build` | configured |
| `typedoc` | `frontend/package.json` | `docs-build` | configured |

## 4. Implemented Or Partial Custom Tools

| Tool | Implemented state | Required configuration | Status |
|---|---|---|---|
| `code_score --changed --fast` | partial | pre-commit hard-fail on F | configured |
| `code_score --changed --full` | partial | PR CI hard-fail on F | configured |
| `code_score --module-health` | partial | scheduled/manual audit | configured |
| `test_quality.ast_lint` | partial | audit CI/manual check | configured |
| `test_quality.test_first_check` | partial | audit CI/manual check | configured |
| `test_quality.mutation_runner` | partial | manual/scheduled or targeted CI | configured |
| `frontmatter_lint` | partial | pre-commit and docs/audit CI | configured |
| `doc_length_lint` | partial | pre-commit and docs/audit CI | configured |
| `auto_generated_lint` | partial | pre-commit and docs/audit CI | configured |
| `skill_pointer_sync` | partial | pre-commit and docs/audit CI | configured |
| docs generators | partial | docs-build generation/freshness step | configured |

## 5. Unimplemented Custom Tools To Wire When Added

| Tool | Expected module or script | CI/pre-commit target | Status |
|---|---|---|---|
| shared schemas | `scieasy.qa.schemas.*` | audit/schema tests | missing implementation |
| `generate_facts` | `scripts/audit/generate_facts.py` | `audit`, `docs-build` | missing implementation |
| `doc_drift` | `scieasy.qa.audit.doc_drift` | `audit` | missing implementation |
| `fact_drift` | `scieasy.qa.audit.fact_drift` | `audit` | missing implementation |
| `closure` | `scieasy.qa.audit.closure` | `audit` | missing implementation |
| `signature_drift` | `scieasy.qa.audit.signature_drift` | `audit` | missing implementation |
| `full_audit` | `scieasy.qa.audit.full_audit` | `audit` | missing implementation |
| `local_gate` | `scieasy.qa.governance.local_gate` | pre-commit/commit-msg | missing implementation |
| `issue_link` | `scieasy.qa.governance.issue_link` | workflow gate / AI local gate | missing implementation |
| `docs_landing` | `scieasy.qa.governance.docs_landing` | pre-commit | missing implementation |
| `persona_policy` | `scieasy.qa.governance.persona_policy` | pre-commit / workflow gate | missing implementation |
| `human_bypass_guard` | `scieasy.qa.governance.human_bypass_guard` | workflow gate | missing implementation |
| `pr_merge_guard` | `scieasy.qa.governance.pr_merge_guard` | workflow gate/manual guard | missing implementation |
| `core_change_guard` | `scieasy.qa.governance.core_change_guard` | workflow gate | missing implementation |
| `governance_mod_guard` | `scieasy.qa.governance.mod_guard` | workflow gate | missing implementation |
| `weakened_ci_check` | `scieasy.qa.governance.weakened_ci_check` | workflow-lint | missing implementation |
| `complete_artifacts` | `scieasy.qa.audit.complete_artifacts` | workflow gate / audit | missing implementation |
| `codemod_lint` | `scieasy.qa.audit.codemod_lint` | audit | missing implementation |
| `trailer_lint` | `scieasy.qa.audit.trailer_lint` | commit-msg / workflow gate | missing implementation |
| `committer_enforce` | `scieasy.qa.audit.committer_enforce` | deferred workflow gate | missing implementation |
| `instructions_loaded_audit` | `scripts/audit/instructions_loaded_audit.py` | report-only audit | missing implementation |

## 6. Manual And Scheduled Tools

| Tool | Manual/scheduled placement | Status |
|---|---|---|
| `code_score --module-health` | weekly scheduled workflow | configured |
| `test_quality.mutation_runner` / `mutmut` | manual or scheduled targeted mutation | configured |
| AI advisory score | optional pre-commit/CI when CLI is available | configured |
| `instructions_loaded_audit` | report-only manual/CI diagnostic | missing implementation |
| Sphinx `linkcheck` | scheduled/manual or docs-build once baseline exists | configured |
