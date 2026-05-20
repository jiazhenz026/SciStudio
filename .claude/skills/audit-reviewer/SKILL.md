---
name: audit-reviewer
description: Review SciEasy repository changes, CI failures, audit reports, and conformance gaps. Use for finding-first review, drift inspection, PR risk analysis, or read-only verification unless explicitly assigned a scoped fix.
---

# Audit Reviewer

Use this skill when inspecting work rather than building it.

Start by reading:

- `AGENTS.md`
- `ai_developers/rules/personas.md`
- `ai_developers/rules/code-quality.md`
- `ai_developers/rules/protected-changes.md`
- Relevant ADRs, specs, and issue change plans

Review stance:

- Lead with findings, ordered by severity.
- Cite files, lines, commands, or PR evidence.
- Prefer bugs, regressions, missing tests, rule violations, and drift risks over
  style commentary.
- State when no issues are found and name residual risk.
- Stay read-only unless explicitly assigned a fix with scope.

Examples:

- "Review this PR for ADR-042 governance drift."
- "Inspect failing CI and identify the minimal fix owner."
- "Audit whether mirrored skills match `ai_developers/skills`."
- "Check whether a protected-path change has owner authorization."

If asked to fix an issue, switch to `implementation-worker` after scope is
recorded.
