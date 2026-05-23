# AGENTS.md

This is the root behavior guide for SciStudio repository work.

Runtime files, skills, memory, and tool-specific configs must point here and to
canonical docs instead of creating separate policy.

## 1. Project Identity

SciStudio is an AI-native workflow runtime for multimodal scientific data. It uses
typed workflow graphs, formal block contracts, persisted artifacts,
plugin-based extension, manual review steps, and AI-assisted orchestration.

## 2. How To Work Here

- Start by understanding the owner request, issue, existing docs, and affected
  code before editing.

- Choose the correct task kind and persona before work starts.
  Use the document index below for routing.

- Keep the task small, traceable, and reviewable.
  Do not silently expand scope.

- Prefer existing contracts, helpers, patterns, and docs over new local
  inventions.

- When unsure, preserve architecture, traceability, and small scope first.
  State assumptions instead of hiding them.

- Treat tests, docs, gate evidence, and CI as part of the work, not afterthoughts.

## 3. Required Rules

### 3.1 Development Hard Rules

- Work on a dedicated branch and worktree.
  Do not share a writable worktree across agents.

- Do not use `pip install -e .`.
  It can pollute the shared environment.

- Every PR must close an open issue.
  Do not create a new issue when an open issue already tracks the work.

- AI-authored work must use the committed gate-record workflow.
  Chat messages and local-only notes are not gate evidence.

- Tests are part of implementation work.
  Add or update tests when behavior changes.

- Documentation is part of the change.
  Update docs or record a clear N/A reason.

- Do not bypass schemas, lineage, runtime checks, governance checks, or CI.

- Do not weaken governance, CI, Sentrux, quality thresholds, or protected paths
  unless the owner explicitly approved that scope.

- CI must pass before work is complete.

### 3.2 Traceability

- Meaningful work must follow:
  Idea -> Issue -> Spec/ADR when needed -> Branch -> Commit -> PR -> Review -> CI/Test -> Merge -> Release.

- Use focused branches, focused commits, and focused PRs.
  Do not mix unrelated work.

- Do not push directly to protected branches.
  Do not merge PRs without explicit owner or administrator authorization.

### 3.3 Branch And Worktree Rules

- Use a dedicated branch for each task.

- Use a dedicated worktree for AI-authored work and parallel work.

- Do not share a writable worktree across agents.

- Do not merge local work into `main`.

### 3.4 Specs, ADRs, And Docs

- Update a spec when work changes contracts, schemas, runtime behavior, storage,
  API behavior, plugin contracts, UI semantics, AI orchestration, or external
  app integration.

- Update an ADR when the change is architectural, hard to reverse,
  cross-module, likely to be questioned later, or a long-term tradeoff.

- Documentation is part of the product.
  Update docs when behavior, workflow, public contracts, or architecture change.

- Generated docs must stay generated.

### 3.5 Coding Boundaries

- Prefer explicit contracts over clever shortcuts.

- Favor composition over deep inheritance.

- Keep modules narrow in responsibility.

- Do not move plugin logic into core for convenience.

- Do not place runtime truth in frontend state.

- Do not bypass schemas, lineage, runtime checks, governance checks, or CI.

### 3.6 Deferred Work

- Deferred work must be visible in the repository.

- Any out-of-scope behavior, edge case, cleanup, test, or follow-up must use a
  tracked TODO that cites an issue, ADR, spec, PR, or follow-up ticket.

```python
# TODO(#NNN): <what is deferred and why>
#   Out of scope per <ADR/spec/PR/owner decision>.
#   Followup: <issue URL or tracking reference>.
```

- Untracked "later", "MVP", "V1", or chat-only deferrals are not acceptable.

### 3.7 AI Agent Rules

- AI agents must read `docs/ai-developer/rules.md`.

- AI agents must use the matching task rule in
  `docs/ai-developer/specific_rules/`.

- AI agents must use the matching persona in `docs/ai-developer/personas/`.

- AI-authored work must use
  `docs/ai-developer/specific_rules/gated-workflow.md`.

- Gate records must be created and updated with:
  `python -m scistudio.qa.governance.gate_record`.

- Local candidate receipts must be generated or validated with:
  `python -m scistudio.qa.governance.gate_receipt`.

- The AI-facing gate command set is indexed in
  `docs/ai-developer/rules.md#5-gate-cli-command-set`.

### 3.8 Hotfix Mode

- Hotfix mode is allowed only when the owner explicitly authorizes hotfix mode.

- During the live owner-guided hotfix session, the agent may bypass normal gate
  steps.

- Final commit and PR submission must complete the standard gated workflow.

- Use `docs/ai-developer/specific_rules/hotfix.md`.

### 3.9 Definition Of Done

Work is done only when scope, code/docs, tests, documentation, gate evidence,
tracked deferrals, issue closure, and CI are all complete.

If any item is missing, the task is not complete.

## 4. Document Index

- Use `docs/ai-developer/rules.md` if you are any AI agent working in this
  repository.

- Use `docs/ai-developer/rules.md#5-gate-cli-command-set` for the canonical
  AI-facing gate record and local receipt commands.

- Use `docs/ai-developer/specific_rules/gated-workflow.md` if you are doing
  AI-authored work that needs gate evidence.

- Use `docs/ai-developer/specific_rules/new-feature.md` if you are building a
  new feature.

- Use `docs/ai-developer/specific_rules/bug-fix.md` if you are fixing a bug.

- Use `docs/ai-developer/specific_rules/hotfix.md` if the owner explicitly
  authorizes hotfix mode.

- Use `docs/ai-developer/specific_rules/docs-change.md` if you are changing
  documentation.

- Use `docs/ai-developer/specific_rules/agent-dispatch.md` if you are managing
  or dispatching multiple agents.

- Use `docs/ai-developer/specific_rules/document-standards.md` if you need the
  ADR-042 document structure reference.

- Use `docs/ai-developer/personas/manager.md` if you are coordinating work,
  dispatching agents, running integration/e2e checks, or handling hotfix flow.

- Use `docs/ai-developer/personas/implementer.md` if you are implementing scoped
  code, tests, docs, or tool changes.

- Use `docs/ai-developer/personas/adr-author.md` if you are writing or updating
  ADRs, specs, addenda, or governance docs.

- Use `docs/ai-developer/personas/audit-reviewer.md` if you are auditing code,
  docs, behavior, or claimed work.

- Use `docs/ai-developer/templates/agent-dispatch-checklist-template.md` if you
  are creating a manager checklist.

- Use `docs/ai-developer/templates/agent-dispatch-prompt-template.md` if you are
  dispatching a non-audit agent.

- Use `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  if you are dispatching an audit agent with current task context.

- Use `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
  if you are dispatching an audit agent without current task context.

- Use `docs/ai-developer/skills/scistudio-e2e-test/SKILL.md` if you are running
  a live end-to-end SciStudio session from a scenario file under
  `docs/ai-developer/e2e/` (PR readiness, hotfix repro, regression check).
  Pair it with `docs/ai-developer/e2e/template.md` (the fill-in scenario
  template) and `docs/ai-developer/e2e/README.md` (workflow + naming).

- Use `.agents/rules/rules.md` if the runtime is generic agent tooling.

- Use `.claude/rules/rules.md` if the runtime is Claude.

- Use `.codex/rules/rules.md` if the runtime is Codex.
