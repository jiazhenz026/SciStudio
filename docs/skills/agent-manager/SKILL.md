# agent-manager

Manager workflow skill for running isolated multi-agent cascades in SciEasy.

## Purpose
- Enforce branch/checklist discipline and artifact traceability.
- Dispatch isolated agents by phase.
- Require checklist evidence updates for every completed row.

## Core rules
1. Use tracking branches and never push to `main` directly.
2. Treat the checklist file as the phase source of truth.
3. Every checked item must append an artifact pointer.
4. Keep agent contexts isolated unless a phase explicitly requires aggregation.
5. Record drift in append-only drift log.

## Structure
- `templates/00-common-boilerplate.md`
- `templates/skeleton-agent.md`
- `templates/implement-agent.md`
- `templates/audit-agent.md`
- `templates/fix-agent.md`
- `scripts/remind-checklist-discipline.sh`
- `scripts/check-agent-template.sh`

## Usage notes
- This exported copy is repository-local for collaboration and review.
- If this differs from user-local skill copies, this repo copy is the version used for team audits.
