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

## 4. Custom Tools Implementation Status

| Tool | ADR/spec gap found before this round | Required configuration | Status |
|---|---|---|---|
| shared schemas | Missing `scieasy.qa.schemas.*`; existing tools used local shims | schema tests and validators | implemented |
| `code_score --changed --fast` | Used local report shim instead of shared schema | pre-commit hard-fail on F | implemented and configured |
| `code_score --changed --full` | Used local report shim instead of shared schema | PR CI hard-fail on F | implemented and configured |
| `code_score --module-health` | Needed scheduled/manual placement | scheduled/manual audit | implemented and configured |
| `test_quality.ast_lint` | Needed shared report alignment | audit CI/manual check | implemented and configured |
| `test_quality.test_first_check` | Needed shared report alignment | audit CI/manual check | implemented and configured |
| `test_quality.mutation_runner` | Needed normalized report and scheduled/manual placement | manual/scheduled or targeted CI | implemented and configured |
| `frontmatter_lint` | Did not validate with ADR/Spec Pydantic schemas | pre-commit and docs/audit CI | implemented and configured |
| `doc_length_lint` | Already implemented; needed shared report compatibility | pre-commit and docs/audit CI | implemented and configured |
| `auto_generated_lint` | Already implemented; needed generated manifest consistency in CI | pre-commit and docs/audit CI | implemented and configured |
| `skill_pointer_sync` | Already implemented; needed CI/pre-commit placement | pre-commit and docs/audit CI | implemented and configured |
| docs generators | Needed generated-doc freshness and Sphinx integration | docs-build generation/freshness step | implemented and configured |
| `generate_facts` | Missing fact registry generator | `audit`, `docs-build`, pre-commit freshness | implemented and configured |
| `doc_drift` | Missing explicit reference classifier | `audit` | implemented and configured |
| `fact_drift` | Missing fact substitution checker | `audit` | implemented and configured |
| `closure` | Missing bidirectional ownership/phantom check | `audit` | implemented and configured |
| `signature_drift` | Missing signature-level spec checker | `audit` | implemented and configured |
| `full_audit` | Missing consistency aggregate runner | `audit` | implemented and configured |
| `local_gate` | Missing local AI gate state and commit trailer checks | pre-commit/commit-msg | implemented and configured |
| `issue_link` | Missing issue resolution abstraction | workflow gate / AI local gate | implemented |
| `docs_landing` | Missing docs/changelog/checklist landing validator | local gate / workflow gate | implemented |
| `persona_policy` | Missing persona/runtime/constitution validator | local gate / workflow gate | implemented |
| `human_bypass_guard` | Missing human-authored label provenance check and required `--pr` CLI | workflow-lint PR CI | implemented and configured |
| `pr_merge_guard` | Missing AI merge guard | workflow gate/manual guard | implemented |
| `core_change_guard` | Missing protected-core authorization check | workflow gate | implemented and configured |
| `governance_mod_guard` | Missing governance modification guard | workflow gate | implemented and configured |
| `weakened_ci_check` | Missing CI/test/lint weakening detector | workflow-lint | implemented and configured |
| `complete_artifacts` | Missing governed-change artifact check | workflow gate / audit | implemented |
| `codemod_lint` | Missing contract-migration metadata check | audit | implemented |
| `trailer_lint` | Missing commit trailer range check | commit-msg / workflow gate | implemented and configured |
| `committer_enforce` | Missing deferred committer check | deferred workflow gate | implemented as deferred/skipped unless configured |
| `instructions_loaded_audit` | Missing report-only diagnostic | report-only audit | implemented |

## 5. Remaining Limitations To Review

| Area | Status | Reason |
|---|---|---|
| Historical repository compliance | not fixed here | This task implements tools; existing ADR/docs/code drift should fail and be cleaned separately |
| `committer_enforce` hard-fail | deferred by ADR | ADR-042 keeps it deferred until the owner defines approved AI commit paths |
| GitHub live metadata fetching | implemented for human bypass only | Other guards still accept explicit PR metadata or local diff evidence; no hidden branch-name/prose inference is used |

## 6. Manual And Scheduled Tools

| Tool | Manual/scheduled placement | Status |
|---|---|---|
| `code_score --module-health` | weekly scheduled workflow | configured |
| `test_quality.mutation_runner` / `mutmut` | manual or scheduled targeted mutation | configured |
| AI advisory score | optional pre-commit/CI when CLI is available | configured |
| `instructions_loaded_audit` | report-only manual/CI diagnostic | implemented |
| Sphinx `linkcheck` | scheduled/manual or docs-build once baseline exists | configured |
