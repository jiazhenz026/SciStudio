---
scope: src/scieasy/blocks/**
parent_agents_md: src/scieasy/AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [28, 29, 30, 31, 33, 35, 42]
---

# src/scieasy/blocks/AGENTS.md — Block development

## Scope

All block implementations: code blocks, AppBlocks (Fiji/Napari/QuPath), LCMS/SRS/imaging/AI blocks, manual-review blocks (via AppBlock pattern). Block contract is defined in `docs/block-development/block-contract.md`.

## Policy

- Every block MUST declare `category` and `subcategory` per ADR-029.
- Every block MUST declare `config_schema` (pydantic `ConfigDict(extra="forbid")`) and `input/output` slot contracts.
- Every block MUST be registered through `BlockRegistry` (not via class-level decorators that bypass the registry).
- AppBlocks MUST use the file-exchange protocol; never hold large in-memory data structures across the GUI boundary.
- AI blocks (`src/scieasy/blocks/ai/**`) MUST stay provider-neutral per ADR-035; no hard-coded vendor SDK imports outside the adapter layer.
- Tests required for every new block: positive path, slot-type mismatch, missing-input, config-validation.

## Routing

| Need | Where |
|---|---|
| Block contract reference | `docs/block-development/block-contract.md` |
| Category / subcategory taxonomy | ADR-029 + `docs/specs/block-taxonomy.md` |
| AI block constraints | `src/scieasy/blocks/ai/` (ADR-035 governs) |
| AppBlock file-exchange | ADR-031 + `docs/block-development/app-block.md` |
| Workflow integration | `src/scieasy/workflow/**` |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/scieasy/blocks/**/*.py` | public | Free edit per §Paths |
| `src/scieasy/blocks/**/_app_bundles/**` (if present) | generated-code | Regenerate via build; no hand edit |

## Assessment rubric

In addition to root R1–R11 and `src/scieasy/AGENTS.md` rubric:

| ID | Criterion | Verify with |
|---|---|---|
| R1-blk | Block registered through `BlockRegistry` | `pytest tests/blocks/test_registry.py` |
| R2-blk | `category` + `subcategory` declared per ADR-029 | `python -m scieasy.qa.audit.block_taxonomy` (when shipped) |
| R3-blk | Slot contract tests cover positive + negative paths | Visual review |
| R4-blk | If block runs an external app, file-exchange protocol used (no in-proc IPC) | Visual review |
| R5-blk | Chrome smoke test recorded if block has frontend surface | Linked Chrome MCP transcript |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `src/scieasy/blocks/<category>/<block>.py` | Free edit for the owned block |
| ✅ | `tests/blocks/**` | Free edit |
| ⚠️ | `src/scieasy/blocks/__init__.py` registry imports | Add/remove only when registering a new block |
| ⚠️ | `src/scieasy/blocks/ai/**` | ADR-035 governs; provider-neutrality required |
| 🚫 | `src/scieasy/blocks/_contract.py` / signatures defined in core | Use core AGENTS.md flow |

## Out-of-scope

Per root AGENTS.md `## Out-of-scope format`. Any block deferred to "Phase N" MUST have a tracking issue and a `# TODO(#NNN):` marker in the registry stub.
