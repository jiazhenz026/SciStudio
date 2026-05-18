---
scope: .github/**
parent_agents_md: ../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43]
---

# GitHub Automation Instructions

## Identity

`.github/**` owns repository workflows, issue/PR templates, dependency config,
and ownership metadata used by GitHub.

## Policy

- Root `AGENTS.md` applies first.
- Do not weaken CI, branch protection, or governance checks for convenience.
- CODEOWNERS and identity ownership files are not agent-editable by default.
- Workflow changes need local lint/review when the relevant tools exist.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| Workflow edit | CI/governance review | ADR-042 §17, §21 |
| PR/issue template edit | Docs/governance review | Root policy |
| CODEOWNERS change | Refuse unless explicit owner-directed slice | ADR-043 governance rules |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `.github/workflows/**` | internal | CI governance; review carefully |
| `.github/ISSUE_TEMPLATE/**`, `.github/pull_request_template.md` | public | Contributor-facing text |
| `.github/CODEOWNERS`, `.github/secrets/**` | user-data/secrets | Do not auto-edit or read secrets |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| GH1 | CI/governance checks are not weakened | Diff review |
| GH2 | Workflow syntax is checked when tooling exists | `actionlint` or documented fallback |
| GH3 | Ownership files remain untouched unless explicitly scoped | `git diff -- .github/CODEOWNERS` |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `.github/AGENTS.md` | Layered instruction scaffold for this subtree |
| ⚠️ | `.github/workflows/**`, `.github/ISSUE_TEMPLATE/**` | CI and contributor workflow |
| ⚠️ | `.github/dependabot.yml`, `.github/pull_request_template.md` | Automation and review surface |
| 🚫 | `.github/CODEOWNERS`, `.github/secrets/**` | Ownership/secret surfaces |
