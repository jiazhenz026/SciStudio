---
scope: src/scieasy/**
parent_agents_md: AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43, 44]
---

# src/scieasy/AGENTS.md — Python source tree

## Scope

Python source code for the SciEasy runtime, blocks, engine, API, workflow, and orchestration. Excludes `core/` (see `src/scieasy/core/AGENTS.md`), `qa/` (`src/scieasy/qa/AGENTS.md`), and `blocks/` (`src/scieasy/blocks/AGENTS.md`), which have stricter rules.

## Policy

- All new Python modules MUST follow `from __future__ import annotations` at top.
- All public callables MUST have type hints (PEP 695 or 3.12+ generics where natural).
- All public callables MUST have docstrings (Google style); enforced by `interrogate` ≥ 90% per package.
- pydantic models use `model_config = ConfigDict(extra="forbid")` unless an ADR documents the carve-out.
- Mutable default args are a lint failure. Use `field(default_factory=...)`.
- No `import *`. No bare `except:`. No `eval`/`exec` on untrusted input.
- Subprocess / threading boundaries follow ADR-017–022 (subprocess isolation, cancellation, Collection transport, psutil memory monitor).

## Routing

| Need | Where |
|---|---|
| Frozen core contracts | `src/scieasy/core/AGENTS.md` |
| Block-development conventions | `src/scieasy/blocks/AGENTS.md` |
| QA tooling edits | `src/scieasy/qa/AGENTS.md` (read-only outside ADR-042/043/044 implementation phase) |
| AI orchestration constraints (ADR-035) | `src/scieasy/blocks/ai/` rules; see root `## Routing` for `adr-router` |
| Schema validation patterns | Root AGENTS.md `## Policy` and pydantic conventions |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/scieasy/**/*.py` (source) | public | Free edit per §Paths below |
| `src/scieasy/_skills/**` | internal | Templates / pointer files; layout fixed by ADR-042 §17 |
| `src/scieasy/agent_provisioning/templates/**` | internal | Cross-runtime install templates |
| `src/scieasy/**/test_fixtures/**` (if any) | test-fixtures | Never large binaries |

## Assessment rubric

In addition to root R1–R11:

| ID | Criterion | Verify with |
|---|---|---|
| R1-py | `ruff check src/scieasy/` clean | `ruff check src/scieasy/` |
| R2-py | `ruff format --check src/scieasy/` clean | `ruff format --check src/scieasy/` |
| R3-py | `mypy --strict src/scieasy/<changed>` clean for new modules | `mypy --strict src/scieasy/<changed>` |
| R4-py | New public API documented in relevant `docs/specs/*.md` | Visual review |
| R5-py | pytest for the changed package runs in ≤60s with `--timeout=60` | `pytest tests/<pkg>/ --timeout=60` |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `src/scieasy/blocks/**` (excl. `blocks/ai/`, `blocks/core/` if present) | Free edit; block contract tests required |
| ✅ | `src/scieasy/engine/**` | Free edit; ADR-018/019 invariants enforced by tests |
| ✅ | `src/scieasy/api/**` | Free edit; OpenAPI schema regen via `make api-spec` |
| ✅ | `src/scieasy/workflow/**` | Free edit |
| ✅ | `src/scieasy/orchestration/**` | Free edit |
| ⚠️ | `src/scieasy/blocks/ai/**` | ADR-035 governs; provider-neutrality required |
| ⚠️ | `src/scieasy/agent_provisioning/**` | ADR-040 governs; cross-runtime parity rules |
| ⚠️ | `src/scieasy/_skills/**` | Layout dictated by ADR-042 §17; do not add/remove without ADR ref |
| 🚫 | `src/scieasy/core/**` | Frozen contracts (see subtree AGENTS.md) |
| 🚫 | `src/scieasy/qa/**` outside implementation phase | QA infra owned exclusively |

## Out-of-scope

Per root AGENTS.md `## Out-of-scope format`. No new conventions added at this subtree.
