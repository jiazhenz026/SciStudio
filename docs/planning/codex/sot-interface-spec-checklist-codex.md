# Codex SSOT Interface Program Checklist (Manager Track)

> **Mandatory tracking doc.** Codex manager and Codex-dispatched agents update only rows they own.
> Drift = protocol violation.

## Conventions
- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- Every row must include: **Owner**, **Authority**, **Artifact evidence**
- When checking a row, append one-line proof: `→ <report path / commit / PR / test command>`
- Primary authority for technical conflicts: `docs/architecture/ARCHITECTURE.md`

## Program metadata
- Manager track: `codex`
- Branch rule: execution branch name MUST contain `codex`
- Artifact root: `docs/audit/codex/`
- Hard stop: pause before Phase 6 final-spec write

---

## Phase 0 — Preflight + hook gate design

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P0.1 Preflight scope note recorded (in/out scope, assumptions, exclusions) | Manager-codex | ARCHITECTURE + AGENTS.md | `docs/audit/codex/phase-0/2026-05-17-preflight-codex.md` → created |
| [x] | P0.2 Rule catalog finalized and linked from plan/checklist | Manager-codex | manager-rule-catalog-codex.md | → finalized and linked in codex planning docs |
| [x] | P0.3 Hook architecture draft recorded (extract_code/extract_docs/compare/policy/report) | Manager-codex | plan §Phase 0 | `docs/audit/codex/phase-0/2026-05-17-hook-design-codex.md` → created |
| [x] | P0.4 Hook fail-policy locked (B without decision fails; C/D without issue link fails; missing evidence fails) | Manager-codex | manager-rule-catalog §7 | `docs/audit/codex/phase-0/2026-05-17-hook-policy-codex.md` → created |
| [x] | P0.5 Audit phase folder skeleton present and verified | Manager-codex | isolation rules | `docs/audit/codex/phase-*/.gitkeep` → verified |
| [!] | P0.6 `agent-manager` skill installed and load-verified (or blocked with evidence + fallback protocol documented) | Manager-codex | user instruction | blocked: path unavailable + installer 403; see `manager-scratchpad-codex.md` |

## Phase 1 — Interface-scope audit (module discovery only)

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P1.1 Dispatch isolated scope-audit agent (architecture + core code; no package repos) | Manager-codex | plan §Phase 1 | → subagent `A1-scope` dispatched (run log in session) |
| [x] | P1.2 Accept module inventory `M={m1..mn}` only (no interface details allowed) | A1-scope | plan §Phase 1 | → `docs/audit/codex/phase-1/2026-05-17-A1-module-scope.md` |
| [x] | P1.3 Manager validates module list completeness and freezes `n` for Phase 1.5 | Manager-codex | checklist discipline | → n fixed at 9 in scratchpad decision log |

## Phase 1.5 — Concurrent deep audits (strict isolation)

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P1.5.1 Spawn reduced set of code-only agents (2 modules/agent, no docs) concurrently | Manager-codex | user override (cost control) + plan §Phase 1.5 | → dispatched `A-code-1..4` for M01..M08 |
| [x] | P1.5.2 Spawn 1 docs-only agent (all modules, no code) | Manager-codex | plan §Phase 1.5 | → `docs/audit/codex/phase-1.5/2026-05-17-A-docs-all-M01-M09.md` |
| [x] | P1.5.3 Spawn 1 docs+code diff agent (no peer reports) | Manager-codex | plan §Phase 1.5 | → `docs/audit/codex/phase-1.5/2026-05-17-A-diff-all-M01-M09.md` |
| [x] | P1.5.4 Collect all reports under phase-1.5 and verify isolation constraints | Manager-codex | rule catalog §3 | → collected 6 reports: A-code-1..4, A-docs, A-diff |
| [x] | P1.5.5 Update manager master index from reports (append-only) | Manager-codex | user requirement | → scratchpad updated with Phase 1.5 execution summary |

## Phase 2 — Triple independent A/B/C/D classification

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P2.1 Spawn classifier C1 with full Phase 1.5 inputs | Manager-codex | plan §Phase 2 | → `docs/audit/codex/phase-2/2026-05-17-C1-abcd.md` |
| [x] | P2.2 Spawn classifier C2 with full Phase 1.5 inputs | Manager-codex | plan §Phase 2 | → `docs/audit/codex/phase-2/2026-05-17-C2-abcd.md` |
| [x] | P2.3 Spawn classifier C3 with full Phase 1.5 inputs | Manager-codex | plan §Phase 2 | → `docs/audit/codex/phase-2/2026-05-17-C3-abcd.md` |
| [x] | P2.4 Verify classifiers were mutually isolated and independently reasoned | Manager-codex | rule catalog §3 | → three independent reports produced via isolated dispatch |

## Phase 2.5 — Dual reconciliation

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P2.5.1 Spawn reconciler R1 over C1/C2/C3 reports | Manager-codex | plan §Phase 2.5 | → `docs/audit/codex/phase-2.5/2026-05-17-R1-reconcile.md` |
| [x] | P2.5.2 Spawn reconciler R2 over C1/C2/C3 reports | Manager-codex | plan §Phase 2.5 | → `docs/audit/codex/phase-2.5/2026-05-17-R2-reconcile.md` |
| [x] | P2.5.3 Resolve R1/R2 disagreements with explicit evidence links | Manager-codex | evidence rules | → resolved in manager merge method, phase-3 draft rationale column |
| [x] | P2.5.4 Produce unified candidate interface/schema/convention list | Manager-codex | user phase design | → `docs/audit/codex/phase-3/2026-05-17-manager-draft.md` |

## Phase 3 — Manager merge draft

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P3.1 Manager merges R1/R2 into master draft list | Manager-codex | plan §Phase 3 | → `docs/audit/codex/phase-3/2026-05-17-manager-draft.md` |
| [x] | P3.2 Every entry has A/B/C/D + rationale + evidence refs | Manager-codex | ABCD rules | → completed in phase-3 master table |
| [x] | P3.3 B/C/D entry action typed as `code-change` vs `docs-fix` | Manager-codex | issue policy mapping | → action_type column populated in phase-3 draft |

## Phase 4 — Draft audit

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P4.1 Spawn module auditors (cost-optimized grouping) and verify A/B/C/D | Manager-codex | user phase design | → `docs/audit/codex/phase-4/2026-05-17-A4-1..A4-5-*.md` |
| [x] | P4.2 Spawn +1 architecture/ADR auditor (draft vs architecture, ADR as supplemental) | Manager-codex | user priority rule | → `docs/audit/codex/phase-4/2026-05-17-A4-arch-consistency.md` |
| [x] | P4.3 Consolidate audit deltas and severity ranking | Manager-codex | audit discipline | → `docs/audit/codex/phase-4/2026-05-17-phase4-summary.md` |

## Phase 5 — Manager fix

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [x] | P5.1 Apply corrections to manager draft per Phase 4 findings | Manager-codex | plan §Phase 5 | → `docs/audit/codex/phase-5/2026-05-17-prefinal-draft.md` |
| [x] | P5.2 Re-check A/B/C/D tags for corrected entries | Manager-codex | ABCD rules | → tags revalidated; no relabel changes required |
| [x] | P5.3 Confirm unresolved contradictions are explicitly logged | Manager-codex | traceability rules | → unresolved section in phase-5 prefinal draft |

## Phase 6 — pause gate (do not proceed)

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [ ] | P6.1 Freeze Codex handoff bundle for cross-manager review | Manager-codex | user instruction | handoff manifest |
| [ ] | P6.2 STOP before final spec writing | Manager-codex | user instruction | manager sign-off note |

## Issue generation readiness (for post-acceptance execution)

| Status | Item | Owner | Authority | Artifact evidence |
|---|---|---|---|---|
| [ ] | I1 Every B/C/D entry mapped to issue type (`code-change` or `docs-fix`) | Manager-codex | issue policy | issue mapping sheet |
| [ ] | I2 Parent tracking issue draft created | Manager-codex | user phase 9 | issue template draft |
| [ ] | I3 Child issue template ready (one interface entry per issue) | Manager-codex | user phase 9 | child template draft |

---

## Drift log (append-only)
When any row is ticked without valid evidence, or any out-of-scope file is touched, append:

`YYYY-MM-DD HH:MM — actor <name> ticked <row> without evidence / touched out-of-scope file <path>. Action: <revert/escalate/fix PR>.`

(Empty until first violation)
