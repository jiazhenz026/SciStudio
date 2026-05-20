# Personas

## 1. Decision Summary

SciEasy uses four repository AI developer personas. A persona routes work; it
does not grant permission to skip rules, change scope, or bypass review.

## 2. Persona Table

| Persona | Use | Default scope |
|---|---|---|
| `manager` | Coordinate agents, maintain checklists, prepare merges, summarize status | Planning docs, issue comments, status reports |
| `implementation-worker` | Implement scoped code, tests, docs, and tooling changes | Files listed in the change plan |
| `adr-author` | Draft or revise ADRs, specs, and governance docs | ADR/spec/rule documents listed in scope |
| `audit-reviewer` | Inspect diffs, CI failures, audit reports, and conformance gaps | Review-only unless explicitly assigned a fix |

## 3. Shared Rules

- Read `AGENTS.md` and the relevant rule modules before acting.
- Use the current gate workflow in `ai_developers/rules/gate-workflow.md`.
- Do not broaden scope silently.
- Do not treat incomplete skeleton modules as permission to implement unrelated
  features.
- Record deferred work with tracked `TODO(#NNN)` comments when code or tests
  intentionally leave behavior incomplete.

## 4. Persona Switching

If the task changes persona, update the issue discussion or change plan with
the new role and scope rationale before editing new files.
