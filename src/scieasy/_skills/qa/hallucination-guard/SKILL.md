---
name: hallucination-guard
description: Verify imported symbols and URLs cited in code/docs exist.
allowed-tools: [Read, Bash]
kind: tool-wrapping
priority: P2
pointer: scieasy.qa.audit.hallucination_guard
adr: 42
---

# hallucination-guard skill

For canonical behaviour, read the module docstring of `scieasy.qa.audit.hallucination_guard`.

After reading, execute in order:
1. Run `python -m scieasy.qa.audit.hallucination_guard --target <path>`.
2. For each flagged symbol/URL, verify it actually exists (import probe or HTTP HEAD).
3. If the symbol is genuinely missing, treat the doc citation as a c2-class finding (§9.1).
4. Fix by either correcting the citation or adding the missing symbol with an ADR.

When uncertain, prefer no edit with explanation.
