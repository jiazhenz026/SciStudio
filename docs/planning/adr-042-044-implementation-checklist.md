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
- Agents must not run `pip install -e .`, `python -m pip install -e .`, or equivalent editable installs. Use per-command `PYTHONPATH` pointing at the agent worktree's `src` instead.
- Dispatch prompts must restate the editable-install ban; a violation blocks automatic merge until the owner reviews the branch.

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

This section tracks every known CI/pre-commit wiring target for the
ADR-042/043/044 cascade. Status is about wiring, not implementation quality:
`[x]` means the check currently runs in CI/pre-commit; `[~]` means local/manual
tooling exists but CI wiring is incomplete; `[ ]` means not wired.

### Current GitHub Actions Wiring

| Workflow / job | Status | Tooling covered | Hard-fail behavior | Notes |
|---|---:|---|---|---|
| `.github/workflows/ci.yml` / `Lint & Format` | [x] | `ruff check .`, `ruff format --check .` | Hard-fail | Existing generic CI; ADR-042 target rule set still broader than current config |
| `.github/workflows/ci.yml` / `Type Check` | [x] | `mypy src/scieasy/ --ignore-missing-imports` | Hard-fail | Existing generic CI; ADR-042 target is stricter than current config |
| `.github/workflows/ci.yml` / `Architecture Tests` | [x] | `pytest tests/architecture/ -v --no-cov` | Hard-fail | Existing architecture placement/boundary tests |
| `.github/workflows/ci.yml` / `ADR Implementation Tracker` | [x] | `python scripts/audit/adr_implementation_check.py --json` with `PYTHONPATH=src` | Hard-fail on tracker errors | No editable install; currently intentionally fails while tracker rows remain unmet |
| `.github/workflows/ci.yml` / `Test` | [x] | `pytest -n auto`, `pytest-timeout`, `pytest-cov` on Python 3.13, `--no-cov` on Python 3.11 | Hard-fail | Existing generic test matrix |
| `.github/workflows/ci.yml` / `Import Contracts` | [x] | `lint-imports` / `import-linter` | Hard-fail | Existing import-boundary CI |
| `.github/workflows/ci.yml` / `Frontend` | [x] | `npm test` (`vitest`), `npm run build` (`tsc -b` + `vite build`), frontend/dist freshness | Hard-fail | Existing frontend CI; no standalone ESLint/Prettier/Typedoc job yet |
| `.github/workflows/ci.yml` / `Build Frontend for Release` | [x] | release-tag frontend static packaging | Hard-fail on tag builds | Existing tag-only release job |
| `.github/workflows/workflow-gate.yml` | [x] | issue link, workflow state warning, changelog/docs/tests checks | Hard-fail for selected policy checks | Existing workflow-gate CI |
| `.github/workflows/ai-review.yml` | [x] | Codex PR review | Non-blocking | `continue-on-error: true` |
| GitHub CodeQL | [x] | Code scanning | Hard-fail per GitHub settings | GitHub-managed workflow/status |

### Generic ADR-042 Tool Stack Wiring

| Tool / group | Status | Current behavior | Target wiring | Notes |
|---|---:|---|---|---|
| `ruff` lint/format | [x] | Direct CI hard-fail | Keep direct CI; expand rules/config to ADR target later | Existing config partial |
| `mypy` | [x] | Direct CI hard-fail with `ignore_missing_imports` | Tighten toward ADR target later | Current config intentionally weaker |
| `pytest` / `pytest-xdist` / `pytest-timeout` / `pytest-cov` | [x] | Direct CI hard-fail | Keep matrix; align coverage target later | Coverage currently 70, ADR target notes 90 drift |
| `import-linter` | [x] | Direct CI hard-fail | Keep direct CI | Existing contracts partial |
| `vitest` | [x] | Direct CI via `npm test` | Keep direct CI | Frontend package script |
| `tsc` | [x] | Direct CI via `npm run build` (`tsc -b`) | Keep direct CI | Not a standalone type job |
| `vite build` | [x] | Direct CI via `npm run build` | Keep direct CI | Frontend build |
| `pre-commit` | [ ] | Installed in dev extras only | Add pre-commit CI job after hooks stabilize | Do not use as hidden aggregate until hooks are owner-approved |
| `commitizen` | [ ] | Config exists | Add commit/PR-title lint if owner wants enforced convention | Current workflow gate checks PR body, not commit format |
| `pyright` | [ ] | Not configured/wired | Add dedicated CI job | ADR-042 secondary type checker |
| `interrogate` | [ ] | Not configured/wired | Add docs/docstring CI job | ADR-042 docstring coverage |
| `pydoclint` | [ ] | Not configured/wired | Add docs/docstring CI job | ADR-042 docstring signature lint |
| `griffe` / `griffe-pydantic` | [ ] | Not configured/wired | Add API surface CI job | ADR-042 API change detection |
| `vulture` | [ ] | Not configured/wired | Add dead-code CI job | Needs baseline/allowlist |
| `xenon` | [ ] | Not configured/wired | Add complexity CI job | Needs threshold config |
| `pip-audit` | [ ] | Not wired | Add dependency audit job | Coordinate with existing Dependabot/security posture |
| Sphinx docs build stack | [ ] | Not configured/wired | Add docs build CI | ADR-044 amends theme/tool list |
| `markdownlint-cli2` | [ ] | Not configured/wired | Add docs lint CI | Needs `.markdownlint.yaml` |
| `sphinx-lint` | [ ] | Not wired | Add docs lint CI | After Sphinx tree exists |
| Sphinx `linkcheck` | [ ] | Not wired | Add scheduled/manual or PR docs CI | External URLs may need non-blocking baseline first |
| `pytest-examples` | [ ] | Not wired | Add docs examples CI | After docs examples are stable |
| `actionlint` | [ ] | Not installed/wired | Add workflow lint CI | Local fallback currently YAML parse only |
| `zizmor` | [ ] | Not wired | Add workflow security CI | Needs baseline/allowed findings |
| `codespell` | [ ] | Not configured/wired | Add spelling CI | Needs `.codespellrc` |
| `yamllint` | [ ] | Not configured/wired | Add YAML lint CI | Needs `.yamllint` |
| `pyproject-fmt` | [ ] | Not wired | Add config format CI | Should be isolated from semantic pyproject edits |
| `libcst` codemod checks | [ ] | Library target only | Wire only when codemod tools exist | ADR-042 codemod support |
| `pydantic-settings` schema/env contracts | [ ] | Not verified | Wire after settings schemas exist | `pydantic` itself is installed/used |
| `eslint` / `eslint-plugin-tsdoc` / `eslint-plugin-jsdoc` | [ ] | Not configured/wired | Add frontend lint CI | Current frontend only has Vitest/build |
| `prettier` | [ ] | Not configured/wired | Add frontend format CI | Current frontend has no Prettier job |
| `typedoc` | [ ] | Not configured/wired | Add frontend docs CI | ADR-042/044 frontend API docs target |

### SciEasy QA / Audit Tool Wiring

| Tool / artifact | Status | Current behavior | Target wiring | Notes |
|---|---:|---|---|---|
| `adr_implementation_check` | [x] | CI hard-fail via `ADR Implementation Tracker` | Add PR-aware diff mode later | Current tracker errors intentionally fail CI |
| `adr043_section2_report_only.py` | [x] | Local aggregate runner, not CI | Keep manual/report artifact unless owner wants a non-blocking summary job | Report-only helper, not a gate |
| `tool_self_test_runner all` | [ ] | Manual only | CI hard-fail after `docs/audit/tool-self-test/*-on-adr-042.json` exists | Currently expected to fail missing artifacts |
| `governance_drift.py` | [ ] | Manual only | CI hard-fail after known ADR/config drift is resolved or baselined | Current coverage 90-vs-70 drift is known |
| `addendum_propagate.py` | [ ] | Manual mutating tool | Pre-commit/CI only after dry-run or owner-approved workflow exists | Do not run blindly in aggregate CI |
| `generate_facts.py` + facts extractors | [ ] | Required by tracker; implementation in progress | CI regeneration + committed diff check | Owned by ADR-042 §7 followup agent |
| `doc_drift` / `frontmatter_lint` / `fact_drift` / `closure` / `full_audit` | [ ] | Future ADR-042 audit tools | Add CI once implemented and baselined | These should likely feed `AuditReport` |
| `trailer_lint` / `committer_enforce` | [ ] | Future ADR-042 commit/provenance tools | Add workflow/pre-commit after owner policy is final | Must respect human/agent trailer rules |
| `complete_artifacts.check` | [ ] | Future ADR-042 audit tool | Add CI after tracker and facts are stable | Mentioned in ADR-042 frontmatter/contracts |
| `contradiction_audit.run` | [ ] | Future ADR-042 self-audit tool | Add scheduled/manual CI first, then PR gate | Needs baseline and report artifact |
| `classification_lint` | [ ] | Deferred | Add after ADR-043 §6 schema/lint implementation | Tracked in Deferred File Tracking |
| Governance modification hard-block tools | [ ] | Hook scaffolds exist, not active CI gate | Add after ADR-043 §3 implementation | Includes governance paths, weakening/honeypot checks |
| Test quality / mutation tooling | [ ] | Not wired | Add after ADR-043 §4 implementation and baseline | Mutation score likely staged rollout |
| ADR-044 docs tools (`workflow_sync`, `auto_generated_lint`, `doc_length_lint`, `skill_pointer_sync`) | [ ] | Not wired | Add after ADR-044 doc skeleton/tool implementation | Depends on docs/contributing/user/prod-agent/doc-guide |

## Drift Log

- 2026-05-18: Initial skeleton agent `019e3c62-7ed1-7c30-9c0a-0bd7fd5e1dc4` was interrupted/shutdown before producing worktree changes. Re-dispatched as `019e3c69-8976-77d2-b468-572a0be48766`.
- 2026-05-18: Agent Goodall (`019e3ca5-7c50-7fb2-b147-28ec305e1cdb`) ran `python -m pip install -e .` in `SciEasy-adr042-s6-maintainers`, which contaminated global `scieasy` imports. Environment was fixed by uninstalling the editable `scieasy` package; future agents must use per-command `PYTHONPATH`.
