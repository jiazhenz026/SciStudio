# Protected Changes

## 1. Decision Summary

Governance files, CI rules, and protected core paths require focused scope and
owner review. A PR may strengthen rules in scope; it must not weaken them
incidentally.

Protected governance surfaces:

- `AGENTS.md`
- `CLAUDE.md`
- `ai_developers/**`
- `.agents/**`
- `.claude/**`
- `.codex/**`
- `.github/workflows/**`
- `.pre-commit-config.yaml`
- tool sections in `pyproject.toml`
- `MAINTAINERS`
- workflow and governance docs
- `scripts/audit/**`
- `src/scieasy/qa/**`

Protected core paths:

- `src/scieasy/core/**`
- `src/scieasy/engine/**`
- `src/scieasy/blocks/**`
- `src/scieasy/workflow/**`
- `src/scieasy/utils/**`

Rules:

- Declare protected paths in the change plan before editing them.
- Do not remove tests, CI checks, lint thresholds, ownership markers, or gate
  requirements without explicit owner authorization.
- Do not merge PRs as an AI agent.
- If a protected-path change reveals unrelated work, open or link a follow-up
  issue instead of expanding the PR silently.
