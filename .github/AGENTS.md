---
scope: .github/**
parent_agents_md: AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43, 44]
---

# .github/AGENTS.md — GitHub configuration and CI

## Scope

GitHub Actions workflows (`.github/workflows/**`), issue/PR templates (`.github/ISSUE_TEMPLATE/**`, `.github/PULL_REQUEST_TEMPLATE.md`), CODEOWNERS, dependabot config, repository configuration.

## Policy

- CI workflows are part of the merge-time hard-guarantee layer (ADR-043 §5.1, row 2). Treat them as governance.
- **🚫 Never weaken CI** without explicit Tier-2 approval. The `weakened_ci_check.py` audit blocks PRs that loosen quality gates (ADR-043 §6.4).
- "Weakening" includes: lowering coverage thresholds, removing required checks, switching `block` → `warn`, narrowing path filters, adding `continue-on-error: true`, or skipping any job for newly-added paths.
- CODEOWNERS is **user-data** per root classification — CODEOWNERS-gated, no auto-edit.
- Workflow secrets MUST come from GitHub Actions secrets; never inline in YAML.
- New workflows MUST pin all action versions to a commit SHA (not a tag) for supply-chain safety.

## Routing

| Need | Where |
|---|---|
| Add a CI job | New workflow file in `.github/workflows/` |
| Add a required check | Workflow + branch-protection rule (admin-only) |
| Loosen a CI gate | File ADR errata; Tier-2 approval; log to `docs/audit/governance-changes.log` |
| Add issue template | `.github/ISSUE_TEMPLATE/<name>.md` |
| Update CODEOWNERS | Owner-only; route through Tier-2 |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `.github/workflows/**` | public | Governance-gated edits |
| `.github/ISSUE_TEMPLATE/**` | public | Free edit |
| `.github/PULL_REQUEST_TEMPLATE.md` | public | Free edit; updates from ADR-043 §4.3 |
| `.github/CODEOWNERS` | user-data | CODEOWNERS-gated |
| `.github/secrets/**` (if exists) | secrets | Never read; only via Actions runtime |
| `.github/dependabot.yml` | public | Free edit; justify scope changes |

## Assessment rubric

In addition to root R1–R11:

| ID | Criterion | Verify with |
|---|---|---|
| R1-gh | `weakened_ci_check.py` passes | `python scripts/audit/weakened_ci_check.py` (when shipped) |
| R2-gh | All actions pinned to commit SHA | `grep -rn "uses:" .github/workflows/ \| grep -vE "@[a-f0-9]{40}"` is empty (or whitelisted) |
| R3-gh | No new `continue-on-error: true` without ADR ref | `grep -rn "continue-on-error: true" .github/workflows/` |
| R4-gh | Loosening logged to `docs/audit/governance-changes.log` | Visual review |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `.github/ISSUE_TEMPLATE/**`, `.github/PULL_REQUEST_TEMPLATE.md` | Free edit |
| ⚠️ | `.github/workflows/**` | Governance; weakening blocked |
| ⚠️ | `.github/dependabot.yml` | Justify scope changes |
| 🚫 | `.github/CODEOWNERS` | Identity/ownership — CODEOWNERS-gated |
| 🚫 | `.github/secrets/**` | Never read in code |

## Out-of-scope

Per root AGENTS.md `## Out-of-scope format`. CI gates planned but not yet shipped (e.g., `weakened_ci_check.py`, `classification_lint.py`, `agents-md-lint`) MUST be TODO-tagged with the Phase reference where they ship.
