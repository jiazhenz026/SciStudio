# AI Developers

This directory is the canonical repository source for AI developer rules and
repository-development skills.

Runtime-specific directories such as `.claude/skills/`, `.codex/skills/`, and
`.agents/skills/` are mirrors. Do not edit mirrored skill files by hand; update
`ai_developers/skills/` first, then synchronize the mirrors.

Current governance status:

- The active task workflow is the existing `.workflow/gate.py` six-stage gate.
- ADR-042 local gate sessions under `.git/scieasy/gates/` are not implemented
  yet and are not required by these rules.
Use:

- `rules/` for canonical AI developer rules.
- `skills/` for canonical persona and governed-change skills.
