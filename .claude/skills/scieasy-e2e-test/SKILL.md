---
name: scieasy-e2e-test
description: Use when running a live end-to-end SciEasy session — driving the GUI in Chrome via Chrome MCP, verifying a PR before merge, reproducing a hotfix bug live, or any time the user says "跑 e2e", "do an e2e", "verify in Chrome", "run e2e on PR #N", or hands you a path under docs/ai-developer/e2e/. Pairs a user-filled scenario file with a pass/fail verdict written back into the same file.
---

# SciEasy E2E Test Skill

This skill is a hard pointer only. It does not define independent policy.

Before doing e2e work, load and follow:

- @AGENTS.md
- @docs/ai-developer/rules.md
- @docs/ai-developer/skills/scieasy-e2e-test/SKILL.md
- @docs/ai-developer/e2e/template.md (the scenario shape this skill expects)
- @docs/ai-developer/e2e/README.md (workflow + naming for scenario files)
- @docs/ai-developer/personas/manager.md when the e2e is part of a manager coordination
- @docs/ai-developer/specific_rules/hotfix.md when the e2e is a hotfix repro

The Chrome MCP recipes, dev-server lifecycle, screenshot recipes, and
final report template live alongside the canonical SKILL.md under
`docs/ai-developer/skills/scieasy-e2e-test/references/`. Read whichever
reference the current step needs.

Do not continue as the e2e tester until the canonical SKILL.md and the
scenario template are loaded.
