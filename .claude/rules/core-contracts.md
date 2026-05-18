---
description: Core contract boundaries
paths:
  - src/scieasy/core/**
---

# Core Contracts

- Core defines stable primitive contracts, not domain-specific workflows.
- Contract, schema, storage, or execution-semantics changes need an accepted ADR
  or spec reference before implementation.
- Prefer explicit typed models and validation over implicit side effects.
- Preserve reference/persisted-artifact data flow; do not introduce eager
  whole-payload transfer assumptions.

TODO(#1113): Replace this scaffold with a generated pointer to the mature core
contract handbook once ADR-044 handbooks are introduced. Out of scope per
ADR-043 §5 / ADR-044 §11. Followup: #1113.
