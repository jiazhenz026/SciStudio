---
name: provenance-tagger
description: Enforce Assisted-by / Fixes / ADR trailers via scripts/committer.py.
allowed-tools: [Bash]
kind: tool-wrapping
priority: P0
pointer: scripts/committer.py
adr: 42
---

# provenance-tagger skill

For canonical behaviour, read `scripts/committer.py`'s module docstring.

After reading, execute in order:
1. `export SCIEASY_AGENT_RUNTIME=Claude` (or your runtime) and `SCIEASY_AGENT_MODEL=<model-id>`.
2. Stage files via `python scripts/committer.py add <file> [<file>...]`. Forbidden tokens: `-A`, `-a`, `.`, `*`.
3. Commit via `python scripts/committer.py commit -m "<type>(<scope>): <subject>"`.
4. The wrapper appends `Assisted-by: <runtime>/<model>` and writes `docs/audit/commit-log.jsonl`.

When uncertain, prefer no edit with explanation.
