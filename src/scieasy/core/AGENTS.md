---
scope: src/scieasy/core/**
parent_agents_md: src/scieasy/AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [17, 18, 19, 20, 21, 22, 42]
---

# src/scieasy/core/AGENTS.md — Frozen core contracts

## Scope

Primitive object types, block contracts, runtime semantics, storage backends. Changes here ripple across every block, every plugin, every workflow.

## Policy

- This subtree is **⚠️ ask-first** for every edit. Open an ADR before changing any signature, field, or invariant.
- No new public types or fields without an ADR.
- Backward compatibility preserved unless ADR documents a major-version bump.
- No domain logic; only contracts and primitives (CLAUDE.md root §2.3).
- No deep inheritance; prefer composition (root §Policy item 3).
- All primitive types use pydantic `model_config = ConfigDict(extra="forbid", frozen=True)` where lifecycle allows.
- Subprocess / cancellation / memory invariants per ADR-017 through ADR-022.

## Routing

| Need | Where |
|---|---|
| Add a new primitive type | Open ADR first; route via `adr-router` skill |
| Change a block contract | Open ADR; coordinate with `src/scieasy/blocks/AGENTS.md` |
| Storage backend changes | Coordinate with ADR-019 storage model |
| Runtime semantics | Coordinate with ADR-017/018 (subprocess isolation, cancellation) |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/scieasy/core/**/*.py` | public | Read-mostly; edits gated by ADR |

## Assessment rubric

In addition to root R1–R11 and `src/scieasy/AGENTS.md` rubric:

| ID | Criterion | Verify with |
|---|---|---|
| R1-core | Linked ADR present in commit body | `git log -1 --format=%B \| grep -E "ADR-[0-9]+"` |
| R2-core | Backward-compat tests still green | `pytest tests/core/ --timeout=60` |
| R3-core | No new abstract base class without ADR justification | Reviewer check |
| R4-core | If schema changed, migration note added to relevant spec | Visual review |
| R5-core | Mutation score for `src/scieasy/core/<changed>` ≥ 0.85 | `mutmut run --paths-to-mutate src/scieasy/core/<changed>` |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ⚠️ | `src/scieasy/core/**` | Frozen contracts; every edit needs an ADR |
| 🚫 | `src/scieasy/core/__init__.py` public re-export list | Touch only when ADR explicitly adds/removes a re-export |

## Out-of-scope

Per root AGENTS.md `## Out-of-scope format`. Core changes that touch contracts but defer follow-up migration MUST file the follow-up issue *before* the merge — verbal "later" is rejected.
