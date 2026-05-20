# Hotfix

## 1. Decision Summary

Hotfix mode is only for live debugging when the owner explicitly invokes it.
It is not a shortcut for ordinary bug fixes, features, refactors, or
architecture changes.

Entry rules:

- The owner must explicitly request hotfix mode.
- Create a `hotfix/<short-description>` branch.
- Before editing code, reread the ADRs and architecture docs that govern the
  touched subsystem.
- Also reread `AGENTS.md` non-negotiable principles and coding boundaries.
- Quote or summarize the governing rule you reread in the first edit-mode
  response so the owner can see the work is grounded.

During hotfix:

- Keep changes limited to the live-debugged bug or tightly related bug cluster.
- Test interactively as needed.
- Commit focused progress when useful.
- Do not push to `main`.
- Do not modify frozen or protected contracts without owner authorization.

When the round ends:

- Run the current `.workflow/gate.py` workflow retroactively.
- Create or link issues for every fixed bug.
- Record the change plan, docs landing, changelog entry, and PR.
- Address CI before considering the PR ready.

Hotfix mode does not apply to refactors, new features, or architecture changes.
Those require the normal gate workflow from the start.
