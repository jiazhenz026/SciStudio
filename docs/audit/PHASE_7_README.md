# Phase 7 — INTERFACE_SPEC.md Post-Write Audit

> **Branch**: `track/spec-ssot-phase7` (this branch)
> **Base**: `track/spec-ssot` at commit `fdb7765` (Phase 6 SSOT commit)
> **Umbrella PR**: opened against `track/spec-ssot` (DO NOT MERGE — visibility only)
> **Umbrella issue**: #1090

## Purpose

Post-write audit of `docs/specs/INTERFACE_SPEC.md` (6588 lines / ~197 entries). The SSOT is the project's authoritative interface contract — this audit gates Phase 8 (CI live + CLAUDE.md amendment + ACCEPTED banner).

## Maximum-rigor anti-hallucination policy

The 11 auditors operate under STRICT anti-hallucination rules:

1. **Each auditor owns exactly their assigned modules.** Never audit outside scope (avoid laziness from cross-checking everything superficially).
2. **For EVERY interface in the SSOT for owned modules, open the actual code file at the cited `Source:` line range and read the actual signature.** Cite verbatim quotes.
3. **NEVER trust the SSOT content as ground truth** — verify against code.
4. **NEVER trust intermediate audit reports** (Phase 1.5 / 2 / 2.5 / 4) as ground truth — those may have hallucinated.
5. Report findings as P1 (must fix before SSOT acceptance) / P2 (should fix) / P3 (nit).
6. Each auditor writes ONE report file to `docs/audit/2026-05-17-spec-ssot-p7-Z<n>.md`.

## Agent dispatch + module assignment

### Claude Code side (Z1..Z7, this session — 7 agents per N halving rule)

Same module pairing as Phase 4 for continuity:

| Agent | Owned modules | SSOT entry count | Notes |
|---|---|---|---|
| Z1 | block-abc + port-system | 30 + 13 = 43 | largest non-solo |
| Z2 | data-types + storage-backends | 19 + 9 = 28 | |
| Z3 | collection-transport + block-registry | 7 + 9 = 16 | |
| Z4 | execution-engine (solo) | 27 | solo because largest single module |
| Z5 | lineage-db + versioning-git | 11 + 12 = 23 | versioning-git is mostly d-class |
| Z6 | rest-api + ws-sse-protocol | 23 + 8 = 31 | most FE-BE drift |
| Z7 | mcp-tools + agent-provisioning | 15 + 12 = 27 | post-ADR-040 surfaces |

Plus the 2 cross-cutting C-class entries at the end of the SSOT — assigned to whichever Z-agent owns the host module (M05 → Z6; M06 → split between Z6 and the workflow-yaml owner; manager curates).

### Codex side (Z8..Z11, external — 4 synthesis audit agents)

Dispatched externally by user. Will push reports to this same branch. Synthesis scope TBD per Codex side's plan.

## Report file convention

- Filename: `docs/audit/2026-05-17-spec-ssot-p7-Z<n>.md`
- Branch: each auditor commits + pushes to `track/spec-ssot-phase7`
- Format: per Z-agent dispatch prompt (P1/P2/P3 severity per finding, verbatim code citations)

## Acceptance for SSOT (Phase 8 gate)

- 11 audit reports landed (7 Claude + 4 Codex)
- Manager reconciles all P1 findings, edits SSOT
- `python -m scripts.spec_audit.extract_spec` parses cleanly (172/208 → target 208/208 after multi-id heading renames per Phase 7 task)
- Then proceed to Phase 8 (flip CI live, amend CLAUDE.md with SSOT-authority section, bump banner to ACCEPTED)
