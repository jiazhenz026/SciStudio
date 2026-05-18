---
name: codemod-with-adr
description: Run libCST codemods only when paired with an ADR reference.
allowed-tools: [Bash, Read]
kind: tool-wrapping
priority: P2
pointer: scieasy.qa.codemods
adr: 42
---

# codemod-with-adr skill

For canonical behaviour, read the module docstring of `scieasy.qa.codemods`.

After reading, execute in order:
1. Confirm the change is motivated by a contract-changing ADR (e.g. signature rename).
2. Add the codemod under `tools/codemods/<name>.py`.
3. Run `python -m scieasy.qa.codemods run <name> --adr 42` (the runner refuses without `--adr`).
4. Commit with both `ADR: 42` and `Codemod-Source: <commit-sha>` trailers.

When uncertain, prefer no edit with explanation.
