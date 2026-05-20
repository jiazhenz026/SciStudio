# Root Policy

## 1. Decision Summary

SciEasy is an AI-native workflow runtime for multimodal scientific data. AI
developers must preserve the repository architecture and traceability rules
while making scoped, reviewable changes.

Core principles:

- The workflow graph, runtime state, lineage, block contracts, and execution
  semantics belong to the backend/runtime layer.
- Data should flow as typed references, lazy handles, or persisted artifacts
  rather than large in-memory payloads.
- Core contracts stay small and stable.
- External tools, GUI steps, code blocks, plugins, and manual review are
  first-class workflow participants.
- AI may propose, but formal schemas, runtime validation, lineage, and
  execution policy decide what runs.

Coding boundaries:

- Prefer typed contracts, explicit schemas, clear interfaces, and deterministic
  behavior.
- Keep module ownership narrow.
- Do not move plugin logic into core for convenience.
- Do not put runtime truth in frontend state.
- Do not bypass schemas, tests, lineage, or execution policy to make a demo
  work.
- Do not introduce temporary shortcuts unless they are documented with a
  tracked issue.

Out-of-scope work must be recorded in the repo with a tracked `TODO(#NNN)`
comment before it is deferred.

Canonical entry points:

- Root policy: `AGENTS.md`.
- Rule modules: `ai_developers/rules/`.
- Canonical skills: `ai_developers/skills/`.
