---
name: maintainers-reverse
description: Reverse-lookup MAINTAINERS for ownership before editing a path.
allowed-tools: [Read, Bash]
kind: tool-wrapping
priority: P2
pointer: scieasy.qa.audit.maintainers_reverse
adr: 42
---

# maintainers-reverse skill

For canonical behaviour, read the module docstring of `scieasy.qa.audit.maintainers_reverse`.

After reading, execute in order:
1. Run `python -m scieasy.qa.audit.maintainers_reverse <path>` to fetch the owning MAINTAINERS entry.
2. Confirm your identity (per ADR-042 §25.2) is listed in the entry's `owners`.
3. If you are not an owner, request review from one of the listed owners before merging.
4. If MAINTAINERS lists no owner for the path, open an issue to add coverage (§11.3).

When uncertain, prefer no edit with explanation.
