---
name: mantis-proof
description: Real-Behavior-Proof (RBP) capture procedure.
allowed-tools: [Read, Bash]
kind: tool-wrapping
priority: P1
pointer: docs/contributing/reference/mantis-proof.md
adr: 42
---

# mantis-proof skill

For canonical behaviour, read: `docs/contributing/reference/mantis-proof.md`

After reading, execute in order:
1. Identify the RBP class (UI / API / runtime / data) per ADR-042 §14.2.
2. Capture the proof:
   - UI: Chrome MCP screenshot/GIF; commit under `docs/audit/rbp/<class>/<sha>.gif`.
   - API/runtime/data: terminal log or test output; same path.
3. Post the artifact link as a PR comment; reference in `Real-Behavior-Proof:` trailer.

When uncertain, prefer no edit with explanation.
