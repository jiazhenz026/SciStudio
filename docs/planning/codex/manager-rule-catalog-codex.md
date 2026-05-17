# Codex Manager Rule Catalog — SSOT Interface Program

## 0. Purpose
This catalog is the **operational rulebook** for the Codex manager track while delivering the SSOT interface specification program.
It is intentionally concise, enforceable, and cross-referenced by plan/checklist artifacts.

## 1. Authority hierarchy
1. Direct user instruction in the active thread
2. Repository AGENTS.md process and boundary rules
3. `docs/architecture/ARCHITECTURE.md` for technical contract authority
4. ADRs as secondary evidence (used only when architecture is silent)

If architecture and ADR conflict: **architecture wins**.

## 2. Isolation and branch discipline
- Codex branch names MUST contain `codex`.
- All Codex audit artifacts MUST be under `docs/audit/codex/`.
- Codex manager/agents MUST NOT read or modify ClaudeCode artifacts.
- One phase output file set per subdirectory:
  - `docs/audit/codex/phase-0/`
  - `docs/audit/codex/phase-1/`
  - `docs/audit/codex/phase-1.5/`
  - `docs/audit/codex/phase-2/`
  - `docs/audit/codex/phase-2.5/`
  - `docs/audit/codex/phase-3/`
  - `docs/audit/codex/phase-4/`
  - `docs/audit/codex/phase-5/`

## 3. Agent context isolation policy
- By default: `fork_context=false` for independent audits.
- Agents in Phase 1.5 MUST NOT receive other agents' reports.
- Phase 2 classifiers MAY read Phase 1.5 reports, but MUST NOT read each other's outputs.
- Phase 2.5 reconcilers MAY read Phase 2 reports, but MUST NOT read each other's draft reconciliations.
- Manager is the only role allowed to merge cross-agent outputs (Phase 3/5).

## 4. Scope boundaries (this program)
In scope:
- Interface contracts (API, events, schemas, block contracts, runtime contracts)
- Convention contracts (naming, backward compatibility, ownership boundaries)
- Gap classification (A/B/C/D) and issue mapping

Out of scope:
- Feature implementation
- Runtime behavior changes
- Package repo contract authoring outside this repository

## 5. ABCD labels (canonical)
- A = code+docs aligned
- B = code+docs divergent; choose canonical side and record rationale
- C = doc-only (missing in code)
- D = code-only (missing in docs)

Every B/C/D entry MUST include issue linkage before acceptance.

## 6. Evidence and traceability rules
- Every assertion in audit reports must cite concrete code/doc path.
- Every decision in manager merge must reference source report IDs.
- Scratchpad is append-only; no destructive edits.
- Phase checkpoint updates must be reflected in checklist state.

## 7. Hook enforcement baseline (Phase 0)
The automation hook must provide:
- deterministic extraction (code/docs to normalized artifacts)
- deterministic compare/classification (A/B/C/D)
- policy gate outcomes (pass/fail/warn)
- machine-readable output (`.json`) + human report (`.md`)

Minimum fail conditions:
- any B without explicit canonical decision
- any C or D without linked issue ID
- missing evidence link for accepted interface entry

## 8. Stop gate
Per program requirement, Codex track stops before final spec writing in Phase 6.
A handoff package is mandatory for cross-manager review before continuation.
