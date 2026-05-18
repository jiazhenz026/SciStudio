---
name: session-logs
description: Search local agent session JSONL for drift root-cause.
allowed-tools: [Read, Bash, Grep]
kind: tool-wrapping
priority: P1
pointer: docs/contributing/reference/session-logs.md
adr: 42
---

# session-logs skill

For canonical behaviour, read: `docs/contributing/reference/session-logs.md`

After reading, execute in order:
1. Locate the session JSONL under `~/.claude/projects/.../memory/` (or runtime-specific path).
2. Grep the session for the symbol or commit SHA implicated by the audit finding.
3. Inspect the surrounding context to identify when the drift was introduced.
4. Cite the session ID in the fix commit message body.

When uncertain, prefer no edit with explanation.
