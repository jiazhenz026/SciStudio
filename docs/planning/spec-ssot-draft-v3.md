# SciEasy Interface SSOT — Draft v3 (Cross-cascade reconciliation)

> **Phase 5.5 deliverable**: my draft v2 + Codex draft v2 → convergent draft v3.
>
> **Inputs**:
> - My draft v2: `docs/planning/spec-ssot-draft-v2.md` (Phase 5, ~195 entries at fine granularity)
> - Codex draft v2: `docs/audit/codex/phase-5/2026-05-17-prefinal-draft.md` + `docs/audit/codex/phase-3/2026-05-17-manager-draft.md` (21 entries at principle granularity)
> - Codex source: PR #1094 branch `codex/review-architecture-and-planning-documents-27pf8w`

---

## Granularity analysis

The two cascades operated at fundamentally different levels:

| Aspect | Claude Code (me) | Codex |
|---|---|---|
| **N (modules)** | 13 | 9 |
| **Total entries** | ~195 | 21 |
| **Granularity** | Per-interface (class/method/route/MCP-tool) | Per-principle (per-contract-cluster) |
| **a-class** | ~82 | 10 |
| **b-class** | ~33 | 8 |
| **c-class** | ~16 | 3 |
| **d-class** | ~64 | **0** |
| **Authority approach** | Strict signature/field comparison | Principle alignment |

**Both cascades agree: D=0 for blocking-level contradictions.** Codex's "no D" matches my finding that all 64 d-class entries are d-document/d-private/d-remove — i.e., none break production.

**Granularity is complementary, not contradictory**:
- Codex's 21 principles = excellent for **section preambles** (architectural framing)
- My 195 entries = excellent for **detailed interface inventory** (grep-checkable, contract-stable)

**Phase 6 SSOT integration plan**: lift Codex's principle text as the opening paragraph of each `## <module>` section in `INTERFACE_SPEC.md`, then continue with my per-interface enumeration.

---

## 10-point reconciliation checklist (from draft v2)

| # | Question | Claude | Codex | Convergent? |
|---|---|---|---|---|
| 1 | Module count match? | N=13 | N=9 | DIFFERENT (granularity); fold both views |
| 2 | Aggregate label breakdown match? | a~45% b~17% c~8% d~33% | a=48% b=38% c=14% d=0% | DIFFERENT distributions (granularity-driven); convergent on D=0 |
| 3 | Same biggest finding? (ADR-028 §D8) | YES (full cluster #1073-#1078) | PARTIAL (1 of 5 entries only: `supported_extensions`) | CONVERGENT |
| 4 | Same PROJECT_TREE.md ⚠️ finding? | YES (Image/Spectrum/PeakTable in core entry-points) | NOT in Codex output | MY-SIDE ONLY (Codex missed) |
| 5 | WS inbound message names correct? | YES (caught draft v1 bug, fixed in v2) | YES (b/c at stringly-typed risk) | CONVERGENT on direction |
| 6 | `finish_ai_block` classification? | b-docs-wins (ARCH §7.2 stale) | not at the per-tool level | CONVERGENT (both treat MCP/AIBlock as needing doc-fix) |
| 7 | versioning-git entirely d-class? | YES (22 GitEngine methods undocumented) | NOT separated as standalone module | MY-SIDE FINER (Codex folded into M03/M05/M08) |
| 8 | NEW issues each side wants? | 14 #TBD-* placeholders | 2 follow-up doc-hygiene notes | MY-SIDE has more concrete issue tracking |
| 9 | Sub-label distributions (b-code-wins vs b-docs-wins)? | b-code-wins dominant (code is truth) | docs-fix dominant (centralize text) | DIFFERENT philosophy; both valid |
| 10 | `core.materialisation` placement? | tentative under collection-transport, flagged for Phase 6 | not at that granularity | MY-SIDE has it (Codex's coarse view subsumed) |

**Outcome**: 7 convergent / 3 divergent (Codex coarser). No contradictions; complementary perspectives.

---

## NEW entries from Codex that draft v3 adds to my v2

### Cross-cutting NEW entry 1: `rest-api.cross-layer-coupling` (C-class, code-change)

**Codex R2 finding (high-confidence, MED dispute level)**:
> API 路由中出现 runtime 级动作（例如分支切换后 refresh block registry），从分层角度看属于"API 编排 runtime 状态刷新"的跨层连接点

**Description**: REST endpoints in `src/scieasy/api/routes/git.py` trigger runtime-level effects (e.g. `refresh_block_registry()` after branch switch). This is a **cross-layer coupling** — API surface (Layer 5) directly invoking runtime state mutation (Layer 3). Architectural anti-pattern per ARCH §3 (clean layer boundaries).

**My draft v2 implicit coverage**: I had `ApiRuntime.refresh_block_registry` as d-document (load-bearing internal class); but I didn't flag the cross-layer coupling itself as a CONTRACT issue.

**Decision for SSOT**:
- **Class**: c-impl (the architectural contract "API does not mutate runtime" is documented but code violates it)
- **Sub-label**: c-impl (recommend layer-boundary cleanup) OR c-defer (acknowledge as known coupling, document it)
- **Module assignment**: rest-api (since the violation site is in api/routes/)
- **Phase 9 issue**: `#TBD-rest-api-cross-layer-coupling`

### Cross-cutting NEW entry 2: `workflow-yaml.validator-strictness-variability` (C-class, code-change)

**Codex R2 finding (CONFIRMED, MED dispute)**:
> validator 在 registry 可用与不可用场景下行为不同（严格端口/类型校验 vs warning/fallback），导致"事实源严格性"受运行上下文影响。同一图定义在不同执行环境下可得到不同级别诊断结果

**Description**: `validate_workflow` (MCP tool + REST endpoint at `src/scieasy/workflow/validator.py`) has DIFFERENT validation depth depending on whether the BlockRegistry is fully populated. With registry: strict port/type checking. Without registry: degraded warning-only mode with fallback. Same YAML produces different diagnostic depth.

**My draft v2 implicit coverage**: I had `validate_workflow` MCP tool as a-class (signature/behavior match docs). But I didn't flag the CONTEXT-DEPENDENT STRENGTH itself as a contract issue.

**Decision for SSOT**:
- **Class**: c-impl (contract should be deterministic; current behavior is implementation leak)
- **Sub-label**: c-impl (recommend documenting two-mode behavior explicitly OR forcing strict-only)
- **Module assignment**: workflow-yaml (cross-references mcp-tools + rest-api)
- **Phase 9 issue**: `#TBD-validator-strictness-context-dependent`

### Module preambles to lift from Codex (Phase 6 SSOT)

Each `## <module>` section in `INTERFACE_SPEC.md` opens with Codex's principle-level statement, then continues with my per-interface enumeration. Specific Codex-derived preambles:

| My module | Codex source | Preamble theme |
|---|---|---|
| block-abc | M02 | Block base contract is stable + typed; dynamic_ports + variadic are first-class; registry strictness has documented fallback path |
| port-system | M02 (sub) | Port type + constraint contract + two-phase validation are stable |
| data-types | M01 | DataObject typed contract + 3-slot metadata stratification is the root abstraction |
| storage-backends | M01 (sub) | Reference-flow + persistence backends with type→backend routing |
| collection-transport | M01 (sub) | Transport-only wrapper; cross-process serialization stable |
| block-registry | M02 (sub) | Registry/validator strictness vs fallback B-class (docs-fix) |
| execution-engine | M03 | DAG lifecycle stable; scheduler responsibility breadth B; checkpoint wire schema B |
| lineage-db | M01 (history-layer) | Dual-history (`workflow_git_commit` join) is stable A |
| rest-api | M05 + M06 + M08 | REST schema A; **cross-layer coupling C**; CLI install A; scaffold conformance B |
| ws-sse-protocol | M05 (realtime) | **WS/SSE stringly-typed B/C** (code-change recommended); reverse-coupling to frontend C |
| mcp-tools | M04 | AI propose / runtime validate boundary A; **dual-channel audit complexity B** |
| versioning-git | (not separated by Codex) | (my-side only finding — entire d-class module) |
| agent-provisioning | M08 (sub) | CLI install + scaffold conformance B/A |

---

## What draft v3 OVERRULES from my draft v2

(none — Codex's findings are ADDITIONS, not corrections to my v2's findings)

## What draft v3 OVERRULES from Codex draft v2

(none — Codex's 21 entries all subsume into my finer 195-entry view; no Codex entry contradicts mine)

---

## Aggregate count update (draft v3)

| Phase | Total | a | b | c | d |
|---|---|---|---|---|---|
| Draft v1 (my Phase 3) | ~180 | ~80 | ~28 | ~12 | ~60 |
| Draft v2 (my Phase 5) | ~195 | ~82 | ~33 | ~16 | ~64 |
| **Draft v3 (Phase 5.5 cross-cascade)** | **~197** | **~82** | **~33** | **~18** | **~64** |

Delta from v2 → v3:
- +1 c-class: rest-api.cross-layer-coupling (M05 from Codex)
- +1 c-class: workflow-yaml.validator-strictness-variability (M06 from Codex)
- Module preambles added (presentation-only)

---

## Approval for Phase 6 SSOT-writing

Manager judgment: draft v3 is ready for Phase 6 SSOT-writing.

**Convergence quality**: high. No contradictions; complementary perspectives strengthen the SSOT.

**Phase 6 SSOT structure** (per draft v3 reconciliation):
1. Title + status banner + grammar reference (per draft v1 plan)
2. Per-module sections (13 modules):
   - **Opening preamble**: Codex principle-level statement (1-2 paragraphs framing the module's contract intent)
   - **Per-interface entries**: my 195+ entries (full signature + Status + Source + Primary-doc-source + Issue)
3. Cross-cutting section: the 2 NEW Codex c-class entries
4. Append: cross-cascade reconciliation log + open issue list

---

## Next: Phase 6 manager writes INTERFACE_SPEC.md

Output target: `docs/specs/INTERFACE_SPEC.md`. Grammar consumed by `scripts/spec_audit/extract_spec.py`.

Given budget constraints (full 195-entry verbatim is ~150KB+), Phase 6 SSOT will be produced in a **lightly compressed form**:
- Full Status/Source/Primary-doc-source fields per entry (required by extract_spec)
- Signature blocks for a + b entries (verbatim from M-reports / C-reports)
- d-document entries get minimal signatures (1-line summary + reference to source file/section)
- d-private/d-remove entries are listed but not signature-detailed (they're being removed from public spec)

This keeps the SSOT machine-checkable while remaining manageable. Phase 7 audit + Phase 8 final fix can iterate on detail level if needed.
