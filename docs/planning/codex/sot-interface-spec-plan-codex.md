# Codex Manager Plan — Single Source of Truth Interface Spec (Stop at Phase 6)

## Scope and objective
Create a project-wide **Single Source of Truth (SSOT)** interface specification document covering:
- API interfaces (frontend/backend contracts)
- Schema contracts (runtime, block, data, event, config)
- Engineering conventions (naming, ownership, compatibility)

This run is explicitly **documentation planning and audit orchestration**, not implementation.

## Priority rules
1. `docs/architecture/ARCHITECTURE.md` is the primary authority for conflict resolution.
2. ADRs are secondary context; if ADR conflicts with architecture, architecture wins.
3. Packages outside core repo scope (external package repos) are excluded as spec authors; they are spec consumers.
4. Codex and ClaudeCode tracks are isolated; Codex outputs live under `docs/audit/codex/`.
5. Stop execution before writing final spec in Phase 6 handoff checkpoint.

## ABCD classification (human-readable canonical definitions)
- **A — Aligned**: code and documentation both exist and are materially consistent.
- **B — Divergent**: code and documentation both exist but conflict; one side must be selected as canonical.
- **C — Doc-only**: documentation defines interface/contract but code implementation is missing.
- **D — Code-only**: code implementation exists but no authoritative documentation exists.

## Parallel isolation protocol
- Execution branch MUST include `codex` marker.
- Audit artifacts MUST be written only under `docs/audit/codex/phase-*/`.
- Manager-owned synthesis artifacts live under `docs/audit/codex/phase-3/` and `phase-5/`.
- Every spawned agent gets only task-local prompt and owned scope.
- No agent should see other agents' outputs unless phase explicitly requires aggregation.
- Store each report as separate file under `docs/audit/codex/phase-<x>/`.
- Naming pattern: `YYYY-MM-DD-<phase>-<agent-id>-<topic>.md`.

---

## Phase plan

### Phase 0 — Preflight + enforceable hook design
**Goal**: treat this as ADR-like process with a strict, machine-checkable gate.

Deliverables:
1. Preflight note: scope, assumptions, exclusions.
2. Hook design spec for automated gap detection between:
   - SSOT draft interfaces
   - repository code surfaces
   - existing docs
3. Hook must emit deterministic findings in ABCD format and fail CI if unresolved blockers exist.

Proposed hook architecture (deterministic + CI-enforceable):
- `tools/spec_audit/manifest.yml`: declarative module inventory and extraction rules.
- `tools/spec_audit/extract_code.py`: collect code symbols/signatures into normalized JSON.
- `tools/spec_audit/extract_docs.py`: collect doc-declared contracts into normalized JSON.
- `tools/spec_audit/compare.py`: classify every contract as A/B/C/D and generate report.
- `tools/spec_audit/policy.py`: fail conditions (unresolved B, C/D without issue link, missing evidence link).
- `tools/spec_audit/report.py`: emit `audit.json` + `audit.md` for both CI and reviewers.

### Phase 1 — Interface-scope audit
**Goal**: discover module boundaries that require interface specs (no detailed signatures yet).

One isolated agent reads architecture + core code (no package repos), outputs only:
- module inventory `M = {m1..mn}` requiring interface/schema/convention coverage.

Output:
- `docs/audit/codex/phase-1/...` report with module list and rationale.

### Phase 1.5 — Parallel deep audits (must run concurrently)
Given `n = |M|`:
- Agents `1..n`: code-only, each one module, no docs access.
- Agent `n+1`: docs-only across all modules, no code access.
- Agent `n+2`: docs+code consistency checker across all modules, no access to other agent outputs.

Each agent outputs full interface inventory for its scope: endpoints/types/fields/constraints/lifecycle/conventions.

### Phase 2 — Triple independent classification
Spawn 3 agents with identical task:
- read all Phase 1.5 reports
- independently classify every interface entry into A/B/C/D
- produce standalone classification reports.

### Phase 2.5 — Dual reconciliation
Spawn 2 reconciliation agents:
- merge 3 Phase 2 reports
- resolve disagreements with evidence
- produce complete candidate interface list including fields/properties/constraints
- for every B/C/D, propose canonical source decision and required tracking issue type.

### Phase 3 — Manager merge draft
Manager personally merges the two Phase 2.5 outputs into a single master draft list.
Includes:
- canonical interface headers
- canonical schema fields
- canonical conventions
- per-item A/B/C/D label
- decision rationale and evidence links.

### Phase 4 — Manager draft audit
Spawn `n+1` agents:
- `n` module auditors: compare manager draft vs code; verify A/B/C/D correctness.
- `+1` architecture/ADR auditor: compare draft vs architecture (primary) and ADRs (secondary), flag conflicts and omissions.

### Phase 5 — Manager correction
Manager applies fixes from Phase 4 reports.
Output is **pre-final SSOT draft**.

### Phase 6 — Pause gate (required by user)
Stop before final document writing/hardening and cross-manager review exchange.
Handoff package prepared for Codex↔ClaudeCode cross-review.

---

## Issue policy mapping
- If canonical decision follows code but docs differ: create **docs-fix issue**.
- If canonical decision differs from code implementation: create **code-change issue**.
- Every B/C/D entry must include issue linkage before final acceptance.

## Manager context safety
Maintain a rolling manager scratchpad to avoid context loss across many reports.
Scratchpad is append-only and links each decision to report evidence.
