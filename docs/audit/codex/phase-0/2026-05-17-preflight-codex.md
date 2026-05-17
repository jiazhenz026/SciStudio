# Phase 0 Preflight — Codex SSOT Interface Program
Date: 2026-05-17
Owner: Manager-codex

## Scope
- Deliver the planning and audit orchestration pipeline for project-wide SSOT interface specification.
- Execute up to Phase 5 outputs and stop before Phase 6 final-spec writing gate.

## In scope
- Manager governance docs and checklist enforcement.
- Phase 0 hook design for deterministic code/doc gap detection.
- Audit artifact isolation under `docs/audit/codex/phase-*`.

## Out of scope
- Runtime/API/engine feature implementation.
- External package repositories as spec-authority sources.
- ClaudeCode manager artifact ingestion.

## Assumptions
1. `docs/architecture/ARCHITECTURE.md` is primary technical authority.
2. ADRs are supplemental and may conflict/noise; architecture prevails.
3. Each B/C/D item will be tied to explicit follow-up issue before acceptance.

## Exclusions and risks
- `agent-manager` skill availability is uncertain in this container and must be treated as a gated dependency with explicit fallback protocol.
- Network-restricted environments may block automated skill installer path.

## Entry criteria met
- Codex branch marker is present.
- Rule catalog, plan, checklist, phase directory skeleton created.
