# AGENTS.md

This is the root policy entry point for AI assistants and human contributors in
the SciEasy repository. Keep this file short. Load detailed rules from
`ai_developers/rules/` only when the task needs them.

## What This Project Is

SciEasy is an AI-native, inclusive workflow runtime for multimodal scientific
data. It is built around a typed workflow graph that can connect Python, R, CLI
tools, GUI applications, manual review, plugins, batch execution, and
AI-assisted workflow construction.

SciEasy is not a bag of scripts, a no-code toy, or a monolithic UI without
runtime semantics. The backend/runtime owns graph truth, block contracts,
lineage, execution state, storage behavior, and validation.

## How To Work Here

1. Work from an issue and a scoped change plan.
2. Use the active `.workflow/gate.py` workflow before implementation, docs,
   changelog, and PR submission.
3. Create a task branch. Do not work directly on `main`.
4. Modify only files listed in the change plan. Update the plan before adding
   files.
5. Keep commits focused and attributable to the issue.
6. Add tests or explain why tests are not applicable.
7. Update docs and changelog when behavior, workflow, governance, or public
   contracts change.
8. Open a PR and verify CI. AI agents must not merge PRs.

For exact commands, read `ai_developers/rules/gate-workflow.md`.

## Rule Index

- Project principles and architecture boundaries:
  `ai_developers/rules/root-policy.md`
- Active gate workflow and command examples:
  `ai_developers/rules/gate-workflow.md`
- Branch, commit, PR, and CI discipline:
  `ai_developers/rules/branch-pr-ci.md`
- ADR, spec, SpecKit, and bugfix decision rules:
  `ai_developers/rules/spec-and-adr.md`
- Documentation, changelog, and skill-pointer rules:
  `ai_developers/rules/docs-governance.md`
- Current quality checks:
  `ai_developers/rules/code-quality.md`
- Protected governance, workflow, and core paths:
  `ai_developers/rules/protected-changes.md`
- Hotfix live-debugging exception:
  `ai_developers/rules/hotfix.md`
- AI personas:
  `ai_developers/rules/personas.md`
- Runtime skill parity:
  `ai_developers/rules/runtime-parity.md`

Canonical repository-development skills live in `ai_developers/skills/`.
Runtime skill directories are mirrors only:

- `.claude/skills/`
- `.codex/skills/`
- `.agents/skills/`

## Main Boundaries

- Workflow graph, runtime state, lineage, and block contracts are backend truth.
  The frontend edits and views; it is not the source of truth.
- Data should flow as references, handles, or persisted artifacts. Do not assume
  large scientific data fits in memory.
- Core stays small and stable. Domain behavior belongs in wrappers, adapters,
  plugins, or higher layers.
- Manual review and GUI intervention are first-class workflow steps, usually
  modeled through `AppBlock` file exchange.
- AI may propose graphs, blocks, parameters, and code, but runtime validation
  and formal schemas decide what is accepted and executed.
- Do not move plugin logic into core, put runtime truth in frontend state,
  bypass schemas, weaken tests, or hide architecture changes in convenience
  patches.
- Any intentional deferral in code or tests needs a tracked `TODO(#NNN)`.

## Current Governance Status

The active gate is still `.workflow/gate.py`. ADR-042 local gate sessions and
other not-yet-implemented checks are not active until their tools and CI checks
exist. Do not require rules that have no implementation yet.
