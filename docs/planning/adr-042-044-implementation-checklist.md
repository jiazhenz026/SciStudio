# ADR-042/043/044 Implementation Checklist

> Mandatory local tracking document for the ADR-042/043/044 rewrite.
> Active implementation rounds list only what is needed for coordination.
> Completed rounds are collapsed into the section tracker to keep this file short.

## Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Agents work in self-owned worktrees.
- Agent branches are created from local `umbrella/adr-042-044-implementation`.
- No agent pushes remote branches or opens PRs during local implementation.
- Manager merges an agent branch back into the local umbrella branch only after owner approval.
- Out-of-scope or deferred behavior must be tagged in repo with `TODO(#1113)` and an ADR section reference.

## Global State

| Item | Status | Notes |
|---|---:|---|
| Umbrella branch | [~] | `umbrella/adr-042-044-implementation` |
| Remote push / PR | [ ] | Deferred until owner explicitly requests it |
| Owner audit | [ ] | Owner will personally audit implementation rounds |
| Feature freeze | [~] | Only ADR-042/043/044 cascade implementation work allowed |

## Section Implementation Tracking

| ADR section | Status | Current owner | Branch / worktree | Merge status | Notes |
|---|---:|---|---|---|---|
| ADR-043 §2 Implementation Monitoring | [x] | Agent Bacon | merged from `local/adr043-s2-implementation-v2` | Merged locally | Agent commit `35831b5b925fce63b25fc9158e17359930befcd9`; merge commit `f4e73fa0`; no phase-gate files restored |
| ADR-043 §5 CLAUDE.md / AGENTS.md Layered Design | [x] | Agent Beauvoir | merged from `local/adr043-s5-layered-scaffold` | Merged locally | Agent commit `67d5f76aa0828e067d3cb93adb1d26f66aab4788`; merge commit `4bc471c2` |
| ADR-042 §5 Frontmatter Schema | [~] | TBD §5 agent | `local/adr042-s5-frontmatter` / `SciEasy-adr042-s5-frontmatter` | In progress | Owns `frontmatter.py` and focused frontmatter tests |
| ADR-042 §6 MAINTAINERS Schema | [~] | TBD §6 agent | `local/adr042-s6-maintainers` / `SciEasy-adr042-s6-maintainers` | In progress | Owns `maintainers.py` and focused maintainers tests |
| ADR-042 §7 Audit Report + Facts Registry Schema | [~] | TBD §7 agent | `local/adr042-s7-report-facts` / `SciEasy-adr042-s7-report-facts` | In progress | Owns `report.py`, `facts.py`, and focused report/facts tests |
| ADR-042 §8 Truth Model & Conflict Arbitration Schema | [~] | TBD §8 agent | `local/adr042-s8-truth` / `SciEasy-adr042-s8-truth` | In progress | Owns `truth.py` and focused arbitration tests |

## Active Round: ADR-042 §5-§8 Schema Modules

| Section | Implementation plan | Agent branch | Scope guard |
|---|---|---|---|
| ADR-042 §5 | Complete `ADRFrontmatter` / `SpecFrontmatter` pydantic v2 models, lifecycle enums, governance/translation/amendment models, and validators for status dates, code implementation coverage, self-supersession, and `agent_editable=allowlist`. | `local/adr042-s5-frontmatter` | Do not implement frontmatter lint CLI or supersession bot. |
| ADR-042 §6 | Complete `MaintainersEntry` / `Maintainers`, `AgentRuntime`, glob/exclude matching helpers, and deterministic most-specific resolution semantics. | `local/adr042-s6-maintainers` | Do not generate full repo `MAINTAINERS` coverage or CI closure checks. |
| ADR-042 §7 | Keep the shared `AuditReport` envelope compatible with existing §2 tools, add `FactsRegistry` and namespace fact models, and validate denormalized report counts. | `local/adr042-s7-report-facts` | Do not implement facts generation scripts or report retention/archive jobs. |
| ADR-042 §8 | Add a small truth/arbitration schema module for transitional vs permanent conflict rules, status-driven resolution, b-class conflict inputs, and multi-ADR conflict representation. | `local/adr042-s8-truth` | Do not implement the full drift classifier from ADR-042 §9. |

## Deferred File Tracking

| File / path | Status | Deferred reason | Implement when | Owner |
|---|---:|---|---|---|
| `src/scieasy/qa/schemas/classification.py` | [!] | Belongs to ADR-043 §6.1-6.3 data classification / rubric / path boundary schema, not §5 scaffold alone. | When ADR-043 §6 implementation starts. | §6 agent |
| `src/scieasy/qa/classification/lint.py` | [!] | Depends on ADR-043 §6 semantics and §2 report primitives. | When ADR-043 §6 implementation starts after §2 schema foundation lands. | §6 agent |
| `scripts/audit/classification_lint.py` | [!] | Full implementation needs ADR-043 §6.1-6.3 semantics and §2 report primitives. | When ADR-043 §6 implementation starts after §2 skeleton merge. | §6 agent |
| `CLAUDE.md` symlink / full pointer replacement | [!] | High governance blast radius; current file carries active policy and should not be replaced without owner audit of the new root `AGENTS.md`. | After §5 scaffold is audited and owner explicitly approves the migration step. | Manager / owner-approved §5 followup |
| `docs/contributing/**` workflow docs | [!] | ADR-044 owns the four-category doc set; skill-as-pointer closure needs real target docs that do not exist yet. | During ADR-044 documentation-set implementation. | ADR-044 docs agent |
| Full skill-pointer closure enforcement | [!] | Depends on ADR-044 `docs/contributing/` targets and `skill_pointer_sync.py`. | After ADR-044 doc skeleton and §2 report primitives land. | ADR-044 / QA audit agent |
| `src/scieasy/qa/tracker/phase_gate.py` | [!] | Removed. This was a temporary ADR-042/043/044 cascade phase-readiness gate, not the repository `.workflow/gate.py`; owner now controls cascade phase readiness manually. | Only if owner later asks to reinstate a redesigned cascade phase-gate tool. | Owner / future §2 followup |
| `scripts/audit/phase_gate.py` | [!] | Removed with the temporary cascade phase-gate implementation; do not recreate as part of ADR-043 §2 unless owner requests it. | Only if owner later asks to reinstate a redesigned cascade phase-gate tool. | Owner / future §2 followup |
| `tests/qa/test_phase_gate.py` | [!] | Removed with the temporary cascade phase-gate implementation. | Only if owner later asks to reinstate a redesigned cascade phase-gate tool. | Owner / future §2 followup |

## Tool Stack Tracking

Source: ADR-042 §21.1 and §21.2. Status starts as `[ ]` until the tool is
installed/configured, wired into pre-commit or CI where applicable, and covered
by a focused verification command. ADR-044 may amend docs-build rows; record
those updates in the Notes column when implemented.

### Python / QA / Docs Tool Stack

| Category | Tool | Purpose | Config location | Status | Owner / Notes |
|---|---|---|---|---:|---|
| Lint (Python) | `ruff` (E, W, F, I, N, UP, B, SIM, RUF, D, S, ANN, PTH, RET, PT, DOC) | All-in-one linter; includes pydocstyle and bandit subsets | `pyproject.toml [tool.ruff]` | [ ] | Existing config partial; ADR target unverified |
| Format | `ruff format` | Code formatting | `pyproject.toml` | [ ] | Existing config partial; ADR target unverified |
| Type | `mypy --strict` without `ignore_missing_imports` | Primary type checker | `pyproject.toml [tool.mypy]` | [ ] | Existing config is not ADR target |
| Type | `pyright` | Secondary type checker | `pyrightconfig.json` | [ ] | Pending |
| Docstring coverage | `interrogate` | Public docstring coverage target | `pyproject.toml [tool.interrogate]` | [ ] | Pending |
| Docstring-signature | `pydoclint` | Docstring/signature consistency | `pyproject.toml [tool.pydoclint]` | [ ] | Pending |
| API surface | `griffe` + `griffe-pydantic` | Public API change detection | `pyproject.toml [tool.griffe]` | [ ] | Pending |
| Dead code | `vulture` | Unreachable/unused code | `pyproject.toml [tool.vulture]` | [ ] | Pending |
| Complexity | `xenon` | McCabe complexity enforcement | `pyproject.toml [tool.xenon]` | [ ] | Pending |
| Security | `pip-audit` | Dependency vulnerability audit | CLI only | [ ] | Pending |
| Docs build | `sphinx` + `sphinx-autoapi` + `myst-parser` + `sphinx-needs` + `furo` + `sphinx-substitution-extensions` | API ref, cross-ref, theme, facts substitution | `docs/sphinx/conf.py` | [ ] | ADR-044 replaces `furo` with `pydata-sphinx-theme` |
| Doc lint | `markdownlint-cli2` | Markdown style | `.markdownlint.yaml` | [ ] | Pending |
| Doc lint | `sphinx-lint` | Sphinx-specific lint | CLI only | [ ] | Pending |
| Link check | Sphinx `linkcheck` builder | External URL validation | `docs/sphinx/conf.py` | [ ] | Pending |
| Doc examples | `pytest-examples` | Execute fenced code blocks in docs | `pyproject.toml` | [ ] | Pending |
| Workflow lint | `actionlint` | GitHub Actions YAML lint | CLI only | [ ] | Pending |
| Workflow security | `zizmor` | GitHub Actions security audit | CLI only | [ ] | Pending |
| Spell check | `codespell` | Typo detection | `.codespellrc` | [ ] | Pending |
| YAML | `yamllint` | YAML format | `.yamllint` | [ ] | Pending |
| Config format | `pyproject-fmt` | `pyproject.toml` format | CLI only | [ ] | Pending |
| Import boundaries | `import-linter` | Layer dependency contracts | `pyproject.toml [tool.importlinter]` | [ ] | Existing config partial; ADR target unverified |
| Pre-commit | `pre-commit` | Hook framework | `.pre-commit-config.yaml` | [ ] | Pending |
| Commit lint | `commitizen` | Conventional commit format | `pyproject.toml [tool.commitizen]` | [ ] | Pending |
| Test | `pytest` + `pytest-xdist` + `pytest-timeout` + `pytest-randomly` + `pytest-examples` | Parallel, timeout, randomized order, doc examples | `pyproject.toml [tool.pytest.ini_options]` | [ ] | Existing config partial; ADR target unverified |
| Coverage | `pytest-cov` + `coverage` | Coverage measurement | `pyproject.toml [tool.coverage.*]` | [ ] | Existing coverage config partial; ADR target unverified |
| Codemod | `libcst` | Concrete-syntax-tree refactoring | Library | [ ] | Pending |
| Schema | `pydantic v2` + `pydantic-settings` | Schema validation and env var contracts | Library | [ ] | `pydantic` exists; `pydantic-settings` unverified |

### Frontend Tool Stack

| Category | Tool | Purpose | Config location | Status | Owner / Notes |
|---|---|---|---|---:|---|
| Lint | `eslint` strict config + `eslint-plugin-tsdoc` + `eslint-plugin-jsdoc` | TypeScript lint and docs lint | `frontend/` config | [ ] | Pending |
| Format | `prettier` | Frontend formatting | `frontend/` config | [ ] | Pending |
| Type | `tsc --noEmit` | TypeScript type checking | `frontend/` config | [ ] | Pending |
| Test | `vitest` | Frontend tests | `frontend/` config | [ ] | Pending |
| Doc | `typedoc` | Frontend API docs with Python cross-links | `frontend/` config | [ ] | Pending |

## CI Wiring Task List

All ADR-042/043/044 QA checks are report-only until the owner explicitly flips
them to hard-fail. This section tracks wiring tasks separately from tool
implementation so final CI hookup can be done in one owner-reviewed pass.

| Wiring task | Status | Current behavior | Future hard-fail trigger | Notes |
|---|---:|---|---|---|
| ADR-043 §2 report-only aggregate runner | [x] | Local report-only script `scripts/audit/adr043_section2_report_only.py`; writes `docs/audit/report-only/adr043-section2-report-only.json`; exits 0 for underlying findings | Owner final CI pass | Verified with `pytest tests/qa/test_adr043_section2_report_only.py --timeout=60 --no-cov`, `ruff check scripts/audit/adr043_section2_report_only.py tests/qa/test_adr043_section2_report_only.py`, and one aggregate run |
| `adr_implementation_check` CI/pre-commit wiring | [ ] | Manual only | After tracker rows stop using transitional `in_progress` scaffolding | Should fail on schema/import/artifact errors; warning policy owner-defined |
| `tool_self_test_runner all` CI wiring | [ ] | Manual only | After required `docs/audit/tool-self-test/*-on-adr-042.json` artifacts exist | Currently expected to report missing artifacts |
| `governance_drift` CI wiring | [ ] | Manual only | After known ADR/config mismatches are resolved or explicitly baselined | Currently reports coverage 90-vs-70 drift |
| `addendum_propagate` pre-commit/CI wiring | [ ] | Manual only | After tracker update workflow is owner-approved | Should start as report-only on ADR addendum diffs |
| Hard-fail conversion plan | [ ] | Deferred; report artifact records `TODO(#1113)` hard-fail-later notes | Owner final CI pass | Convert selected report-only tasks to required CI checks in one batch |

## Drift Log

- 2026-05-18: Initial skeleton agent `019e3c62-7ed1-7c30-9c0a-0bd7fd5e1dc4` was interrupted/shutdown before producing worktree changes. Re-dispatched as `019e3c69-8976-77d2-b468-572a0be48766`.
