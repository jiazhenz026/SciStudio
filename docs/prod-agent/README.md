---
doc_id: prod-agent-readme
title: "Production-environment embedded agent — overview"
category: prod-agent
audience: [maintainer, operator, end-user]
governs_adr: 40
generation: hand
related_addenda: [A1, A2, A3, A4]
related_user_docs: [prod-env-artifacts]
related_known_gaps: [OQ-1, OQ-2, OQ-3]
maintenance_owner: "@jiazhenz026"
last_reviewed: 2026-05-18
---

# Production-environment embedded agent

## What this is

<!-- TODO(Phase 3): 2 sentences pointing to ADR-040 -->
SciEasy's production-environment embedded agent is a four-layer reliability
stack (per [ADR-040](../adr/ADR-040.md)) that provisions agent config, skills,
and MCP tools into user project directories at install/upgrade time.

## What it produces in user projects

<!-- TODO(Phase 3): table of artifacts, ≤8 rows, point to user-visible doc -->

| Artifact | Location | Purpose |
|---|---|---|
| `CLAUDE.md` | `<project>/CLAUDE.md` | Agent policy routing |
| `AGENTS.md` | `<project>/AGENTS.md` | Agent conventions |
| `.claude/` | `<project>/.claude/` | Claude Code config |
| `.codex/` | `<project>/.codex/` | Codex config |

See [prod-env-artifacts](../user/prod-env-artifacts.md) for end-user perspective.

## Known issues / gaps

<!-- TODO(Phase 3): write Codex 0.130 Windows gap; OQ-1/OQ-2/OQ-3; ADR-040 §10 deferred items -->
- Codex 0.130 Windows gap: see ADR-040 §10.
- OQ-1, OQ-2, OQ-3: open questions per ADR-040 Appendix A.

## Upgrade flow

<!-- TODO(Phase 3): write -->
See [ADR-040 §6](../adr/ADR-040.md) phased implementation and Addendum 1 flatten paths.

## How to extend

<!-- TODO(Phase 3): write -->
- Add a hook: edit `src/scieasy/agent_provisioning/templates/`.
- Add a skill: edit `src/scieasy/_skills/scieasy/<name>/`.
- Add an MCP tool: edit `src/scieasy/ai/agent/mcp/tools_<group>.py`.
