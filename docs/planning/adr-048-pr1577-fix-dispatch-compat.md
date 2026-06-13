---
title: "ADR-048 PR1577 No-Compat Dispatch"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
language_source: en
---

# ADR-048 PR1577 No-Compat Dispatch

Persona: `implementer`
Task kind: `bugfix`
Issues: #1644, #1594
Base: PR #1577 head (`track/adr-048-spec1-preview-system`)

## Task

Resolve the final audit's no-compat finding for MCP inspection preview behavior.
Issue #1594 says pre-alpha code must not retain compatibility/adaptor layers.
The audit found `tools_inspection.preview_data` still live with comments saying
it was preserved from pre-FastMCP with no behavior change.

## Write Set

- `src/scistudio/ai/agent/mcp/tools_inspection/**`
- `tests/ai/test_mcp_tools_inspection.py`
- `docs/specs/adr-048-preview-system.md`
- `docs/block-development/**`
- `CHANGELOG.md`

## Out Of Scope

- Plot UI/MCP reachability.
- `pyproject.toml` entry point fix.
- Broad rewrite of all inspection tools.

## Required Result

- Prefer migrating `preview_data` wording/implementation to canonical bounded
  preview data access instead of compatibility-adapter language.
- If deletion/rename is too disruptive for existing AI tools, make the contract
  explicit as canonical and remove stale compatibility claims.
- Add/update tests for the chosen canonical behavior.
- Report changed paths and exact test commands run.
