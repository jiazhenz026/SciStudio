---
description: Governance path guardrails
paths:
  - .governance-paths.yaml
  - MAINTAINERS
  - .github/CODEOWNERS
  - docs/identity/humans.yml
  - docs/audit/overrides.log
  - docs/audit/governance-changes.log
  - docs/audit/commit-log.jsonl
---

# Governance Edits

- Treat governance and identity paths as Tier-2 or owner-directed surfaces.
- Do not edit CODEOWNERS, MAINTAINERS, identity files, or append-only audit logs
  unless the dispatch explicitly names that file and authority.
- Do not hand-edit generated governance/fact outputs.
- Preserve append-only semantics for governance logs.

TODO(#1113): Wire deterministic governance-mod guard behavior after ADR-043 §3
runtime hooks are implemented. Out of scope per ADR-043 §5 / ADR-044 §11.
Followup: #1113.
