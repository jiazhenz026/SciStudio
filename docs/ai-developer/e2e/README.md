---
title: "E2E Session Files"
status: Approved
owners:
  - "@jiazhenz026"
language_source: en
---

# E2E Session Files

This directory holds **filled e2e session files** — one Markdown file per
end-to-end test session. Each file pairs with one invocation of the
`scistudio-e2e-test` skill (see
`docs/ai-developer/skills/scistudio-e2e-test/SKILL.md`).

## How To Run An E2E Session

1. Copy `template.md` to a new file in this directory. Name it
   `YYYY-MM-DD-<short-kebab-name>.md` so files sort chronologically.

2. Fill Sections 1–6 of the new file. Leave Section 7 (Results) empty.

3. Open a Claude Code session in the repo root and ask Claude to run
   that e2e file:

   ```
   跑 e2e: docs/ai-developer/e2e/2026-05-20-pr-1300-readiness.md
   ```

   The `scistudio-e2e-test` skill triggers, executes the steps in order,
   and writes back into Section 7.

4. Review the verdict + artifacts. If the session passes, the file is
   evidence — commit it under the same PR / issue it tested. If it
   fails, fix or defer, then re-run (skill rewrites Section 7 in
   place).

## File Naming

- **Format**: `YYYY-MM-DD-<short-kebab-name>.md`

- **Examples**:
  - `2026-05-20-pr-1300-readiness.md`
  - `2026-05-20-hotfix-869-stuck-loading-tab.md`
  - `2026-05-20-adr-035-aichat-slash-commands.md`

- **One file per session**. Do not edit a passed session file to run
  the same scenario again — copy it to a new dated filename and re-run.
  The history of e2e files is part of the project record.

## What Belongs Here vs. Elsewhere

- **Here**: scenario plans + their result reports. Both human-authored
  intent (Sections 1–6) and skill-written results (Section 7) live in
  the same file.

- **Not here**: unit tests (`tests/`), integration tests (`tests/integration/`),
  audit reports (`docs/audit/`), or general manager checklists
  (`docs/planning/`). E2E sessions are *live, end-to-end* verification —
  the user is in front of the browser or the skill is driving Chrome MCP.

## Related Documents

- **Skill**: `docs/ai-developer/skills/scistudio-e2e-test/SKILL.md`
- **Template**: `docs/ai-developer/e2e/template.md`
- **Manager persona** (owns coordinated e2e):
  `docs/ai-developer/personas/manager.md`
- **Hotfix rules** (hotfix sessions usually end with an e2e):
  `docs/ai-developer/specific_rules/hotfix.md`
- **Frontend smoke rule** (governs UI verification cadence):
  `.claude/rules/frontend-smoke-test.md`
