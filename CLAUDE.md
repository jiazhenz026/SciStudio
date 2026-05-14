# CLAUDE.md

This file defines the working rules, architectural boundaries, and engineering standards for AI assistants and human contributors in this repository.

The goal is to keep development standardized, traceable, extensible, and aligned with the project's long-term architecture.

---

# 1. Project Identity

## What this project is

This repository builds an **AI-native, inclusive workflow runtime for multimodal scientific data**.

The system is intended to support:

- multimodal scientific data in one workflow graph
- typed data objects and standardized block I/O
- Python, R, CLI, GUI software, and manual review in the same runtime
- serial, parallel, batch, and interactive execution
- extensibility through plugins
- AI-assisted orchestration, block generation, and workflow construction

## What this project is not

This project is **not**:

- a replacement for every existing scientific tool
- a monolithic end-user application without a formal runtime
- a collection of ad hoc scripts
- a no-code toy UI without execution semantics
- a place for architecture-free experimentation directly on main branches

---

# 2. Non-Negotiable Principles

The following principles are mandatory.

## 2.1 Workflow graph is the source of truth

The graph definition, runtime state, block contracts, lineage, and execution semantics belong to the backend/runtime layer.

The frontend is an editor and viewer, not the source of truth.

## 2.2 Data flows as references, not large in-memory payloads

Objects passed between blocks should usually be typed object references, lazy handles, or persisted artifacts.

Do not design the system assuming all data fits in memory.

## 2.3 Core must stay small and stable

The core should define minimal contracts, not solve every domain-specific problem.

Prefer:
- stable primitive object types
- stable block contracts
- stable execution semantics

Avoid:
- excessive domain logic in core
- deep inheritance trees
- premature specialization

## 2.4 Everything is connectable, not everything is native

We do not require users to migrate their entire existing workflow.

Instead, we support:
- code blocks
- external application blocks
- manual review blocks
- import/export bridges
- plugin-based extensions

## 2.5 Manual steps are first-class

Human review, editing, annotation, approval, or GUI-based intervention are not hacks.

They are part of the formal workflow model.

In practice, manual review is implemented as an `AppBlock` (see
`docs/block-development/block-contract.md`) that opens a GUI tool such as Fiji,
Napari, or QuPath, pauses the workflow until the user produces an output
file, and then resumes. There is no dedicated manual-review block class —
the `AppBlock` pattern with `app_command="fiji"` (or similar) covers the
manual-review use case via the file-exchange protocol.

## 2.6 AI may propose, but runtime validates and executes

AI-generated graphs, blocks, parameters, or suggestions must always be validated against formal schemas and runtime rules.

AI must never bypass contracts, lineage, or execution policies.

---

# 3. Repository Working Model

All meaningful work should be traceable through the following chain:

**Idea -> Issue -> Spec/ADR -> Branch -> Commit -> PR -> Review -> CI/Test -> Merge -> Release**

If this chain is broken, traceability is broken.

---

# 4. Standard Development Workflow

## 4.1 Before coding

Before starting implementation:

1. confirm there is an issue
2. confirm the scope
3. confirm the acceptance criteria
4. determine whether a spec is required
5. determine whether an ADR is required

## 4.2 When a Spec is required

A spec is required when work changes any of the following:

- object model
- block protocol
- runtime execution behavior
- storage behavior
- API contracts
- plugin contracts
- major UI semantics
- AI orchestration behavior
- external app integration model

If in doubt, write the spec.

## 5.3 When an ADR is required

An ADR is required when making a decision that is:

- architectural
- hard to reverse
- likely to affect multiple modules
- likely to be questioned later
- a tradeoff between competing long-term options

Examples:
- choosing workflow graph ownership rules
- choosing storage model
- defining primitive object types
- choosing plugin strategy
- defining external app execution semantics

## 5.4 During coding

During implementation:

- keep changes scoped
- avoid unrelated refactors
- preserve backward compatibility when possible
- update tests with behavior changes
- update docs for user-facing or architecture-affecting changes
- leave the repo in a working state

## 5.5 Before opening a PR

Before opening a PR:

- run tests
- verify lint/formatting
- update or add docs if needed
- link the issue
- link spec/ADR if applicable
- clearly state risks and scope

---

# 6. Required Engineering Discipline

## 6.1 No direct push to main

Main branch must be protected.

All changes go through PR.

## 6.2 MUST create a branch before any changes

Before making any code or documentation changes, MUST create a feature branch first. Never commit directly on main. Branch naming should follow the convention: `feat/issue-N/short-description`, `fix/issue-N/short-description`, or `docs/short-description`.

## 6.3 MUST create a PR to GitHub

Every change MUST be published to GitHub via a pull request. After committing to a feature branch, push the branch and create a PR. Changes are not considered delivered until a PR exists on GitHub.

## 6.4 MUST verify PR CI passes

After creating a PR, MUST check whether all CI checks pass. If any check fails, diagnose and fix the issues, push fixes, and repeat until all checks are green. A PR with failing CI is not ready for review. Do not leave failing checks unaddressed.

## 6.5 Every meaningful change must be attributable

Every meaningful change should be traceable to:
- an issue
- a commit
- a PR
- a review
- a test outcome

## 6.6 Use focused commits

Do not create vague commits like:
- fix
- update
- misc
- changes
- final

Use meaningful, scoped commit messages.

Preferred style:
- feat(runtime): add pause state for manual block
- fix(storage): avoid eager loading of array preview
- docs(adr): record external app block design

## 6.7 Tests are part of the change

A bug fix should ideally include a regression test.

A new contract should include validation or integration tests.

A major runtime behavior change should include integration coverage.

## 6.8 Documentation is part of the product

Docs are not optional.

If behavior changes, documentation must be updated accordingly.

---

# 7. Coding Boundaries

## 7.1 Prefer explicit contracts over clever shortcuts

Prefer:
- typed models
- explicit schema validation
- clear interfaces
- deterministic behavior

Avoid:
- hidden magic
- implicit side effects
- dynamic behavior without contracts
- tight coupling across packages

## 7.2 Favor composition over deep inheritance

Primitive objects should remain stable.

Domain-specific behavior should usually be layered on top via wrappers, metadata, adapters, or plugins.

Avoid complex inheritance trees unless there is a compelling reason.

## 7.3 Keep modules narrow in responsibility

Each module/package should have a clear purpose.

Do not mix:
- core contracts with plugin logic
- frontend state with backend truth
- storage mechanics with UI assumptions
- AI prompting logic with runtime policy

## 7.4 No premature optimization at the expense of clarity

Performance matters, especially for large scientific data, but premature complexity without profiling should be avoided.

Choose clarity first for the initial implementation of a subsystem, unless performance is a known requirement of that subsystem.

## 7.5 No architecture drift through convenience hacks

Do not introduce temporary shortcuts that contradict the intended architecture unless they are explicitly documented as temporary and tracked by an issue.

---

# 9. AI Assistant Operating Rules

These rules apply specifically to Claude or other AI coding assistants working in this repository.

## 9.1 Claude must preserve project intent

Claude should optimize for:
- standardized process
- architectural consistency
- traceability
- maintainability
- clear boundaries

Claude must not optimize only for short-term implementation speed.

## 9.2 Claude must not silently broaden scope

If asked to implement a feature, Claude should not quietly redesign multiple subsystems unless explicitly asked or clearly required.

Prefer the smallest architecture-consistent change.

## 9.3 Claude should identify missing process artifacts

If a task appears to require:
- a spec
- an ADR
- a new issue
- a test plan
- a migration note

Claude should say so and, where appropriate, draft the missing artifact.

## 9.4 Claude should respect incomplete skeleton modules

This repository may intentionally include empty or partially implemented modules.

Claude should not assume every placeholder must be implemented immediately.

## 9.5 Claude should not collapse boundaries for convenience

Claude must not:
- move plugin logic into core for convenience
- place runtime truth in frontend state
- bypass schemas to “make things work”
- add hidden implicit behavior

## 9.6 Claude should produce structured outputs

When asked to design or change something significant, Claude should usually provide:

- summary
- affected modules
- assumptions
- implementation approach
- risks
- test implications
- doc implications

## 9.7 Claude should prefer traceable scaffolding

When generating code, Claude should prefer:
- explicit types
- clear file placement
- documented interfaces
- TODO markers for incomplete areas
- predictable naming

---

# 10. Required Documentation Updates

The following changes usually require documentation updates.

## Update a Spec when:
- adding a subsystem
- changing execution semantics
- changing schemas
- changing block behavior
- changing storage behavior
- changing API behavior

## Update an ADR when:
- making an architectural decision
- reversing a prior architectural decision
- replacing a foundational dependency or pattern

## Update the changelog when:
- adding user-visible functionality
- fixing significant bugs
- changing behavior
- adding or removing plugin capability
- making breaking changes

## Update contributing or architecture docs when:
- changing developer workflow
- changing repo structure
- changing testing strategy
- changing plugin authoring expectations

---

# 11. Definition of Done

A task is not done just because code exists.

A task is done when:

- the scope matches the issue/spec
- code is committed in the correct module
- tests exist or the lack of tests is explicitly justified
- documentation is updated if needed
- architecture boundaries are respected
- the PR explains what changed and why
- CI passes
- reviewers can understand the change

---

# 11.5 Hotfix Mode (live-debugging exception)

Hotfix mode is a narrow exception to the gate workflow for live debugging
sessions where the user is interactively guiding the fix.

## When hotfix mode applies

Hotfix mode applies **only when the user explicitly invokes it** ("hotfix
this", "进入 hotfix 模式", "let's hotfix", or equivalent direct request).

Claude must **not** auto-promote a normal bugfix to hotfix mode. If unsure,
ask. Default to the standard 6-gate workflow.

## What hotfix mode permits

For the duration of a single hotfix round (one bug, or a small cluster of
tightly-related bugs surfaced in the same debugging session):

1. Create a `hotfix/<short-description>` branch off `main`.
2. `git checkout` it.
3. Open the user's Chrome (via Chrome MCP) and drive live test cases /
   reproduce the user's reported bug interactively.
4. Iterate code edits + live re-tests freely — **the gate workflow is
   suspended** during the round; do not run `gate.py advance` per edit.
5. Commit progress as you go (small commits are fine, gate enforcement is
   off for this branch).

## When the round ends

A round ends when the user says it's done, or when the bug is fixed and
verified live. At that point:

1. Run the **full 6-gate workflow** retroactively in one batch:
   `start → create_issue → write_change_plan → create_branch → update_docs
   → update_changelog → submit_pr`.
2. Open the PR against `main`.
3. Wait for CI green, address Codex review, merge.

## Constraints (still apply in hotfix mode)

- Out-of-scope file rules from §7 still apply (no touching frozen core
  contracts without an ADR).
- Do not push directly to `main` — always go through PR at the end.
- Hotfix mode does NOT extend to refactors, new features, or
  architecture changes. Those still require the full process from the start.
- Memory: log the hotfix round entry as a `feedback` or `project` memory if
  the live debugging surfaced rules worth carrying forward.

---

# 12. Prohibited Shortcuts

The following are discouraged or forbidden unless explicitly justified:

- direct push to protected branches
- undocumented architecture changes
- silent behavior changes
- unreviewed breaking API changes
- plugin logic inserted into core without decision records
- frontend-only workflow semantics
- bypassing tests for convenience
- adding dependencies without justification
- massive refactors hidden inside feature PRs
- “temporary” hacks without tracking issues

---

# 13. Preferred Task Checklist for Claude

When asked to implement something non-trivial, Claude should mentally follow this checklist:

1. What problem is being solved?
2. Which module should own this?
3. Does this require a spec?
4. Does this require an ADR?
5. Is there already a contract this must fit into?
6. Does this change runtime truth, storage, or plugin boundaries?
7. What tests should exist?
8. What docs should be updated?
9. What is intentionally left unimplemented?
10. What risks or follow-up tasks should be recorded?

---

# 14. Preferred Response Style for Claude

When working on this repository, Claude should:

- be concrete
- be structured
- be conservative with architectural changes
- explain tradeoffs
- call out uncertainty
- distinguish implemented behavior from planned behavior
- avoid pretending placeholders are complete

Claude should not:
- over-promise
- obscure missing pieces
- silently make broad assumptions
- claim unsupported behavior exists

---

# 15. If You Are Unsure

If a request is ambiguous, prefer this order:

1. preserve architecture
2. preserve traceability
3. preserve small scoped change
4. preserve future extensibility
5. defer broad redesign unless explicitly asked

When in doubt, document the assumption.

---

# 16. Project Priorities

When tradeoffs arise, optimize in roughly this order:

1. correctness of architecture
2. traceability and maintainability
3. stable contracts
4. extensibility
5. clear developer experience
6. implementation speed
7. polish

---

# 17. Summary

This repository is building a long-lived scientific workflow platform, not a disposable prototype.

Therefore:

- process matters
- boundaries matter
- documentation matters
- contracts matter
- traceability matters

Claude and all contributors must work in a way that keeps the system understandable, extensible, and auditable over time.

---

# Appendix A: Mandatory Workflow Gate Protocol

> **This protocol is NON-NEGOTIABLE.** Every implementation task must pass through
> the gate system. Skipping steps is a protocol violation equivalent to pushing
> directly to main.

## The Gate System

This project uses `.workflow/gate.py` as a state machine that enforces the
development pipeline. The gate CLI is the **single source of truth** for whether
a step has been completed. You cannot self-attest completion — only the gate
records count.

## Required Execution Sequence

For **every** implementation task (feature, bugfix, refactor), execute these
steps **in exact order**. Each step requires the previous step's gate to be
recorded.

### Step 1: Start Workflow + Create Issue

```bash
# 1a. Initialize workflow tracking
python .workflow/gate.py start "Brief description of the task"
# Note the TASK_ID from output

# 1b. Create the GitHub issue
gh issue create --template feature.md --title "..." --body "..."
# Note the ISSUE_NUMBER and ISSUE_URL

# 1c. Record gate completion
python .workflow/gate.py advance $TASK_ID create_issue \
  --data '{"issue_number": 42, "issue_url": "https://github.com/.../issues/42"}'
```

**You CANNOT proceed to Step 2 until `create_issue` gate is recorded.**

### Step 2: Write Change Plan

```bash
# 2a. Write the change plan as an issue comment
gh issue comment $ISSUE_NUMBER --body "## Change Plan for #$ISSUE_NUMBER
### Approach
...
### Files to Modify
| File | Action | Rationale |
|------|--------|-----------|
| ... | ... | ... |
### Risk Assessment
..."

# 2b. Record gate completion
python .workflow/gate.py advance $TASK_ID write_change_plan \
  --data '{"change_plan_comment_url": "https://...", "files_to_modify": ["src/..."]}'
```

**You CANNOT proceed to Step 3 until `write_change_plan` gate is recorded.**

### Step 3: Create Branch + Implement

```bash
# 3a. ALWAYS sync with latest main first (prevents merge conflicts)
git checkout main
git pull origin main
git checkout -b feat/issue-$ISSUE_NUMBER/short-description

# 3b. Implement changes (scoped to change plan!)

# 3c. Commit with conventional format
git add .
git commit -m "feat(#$ISSUE_NUMBER): description of change"

# 3d. Record gate completion
python .workflow/gate.py advance $TASK_ID create_branch \
  --data '{"branch_name": "feat/issue-42/...", "commit_shas": ["abc1234"]}'
```

**You CANNOT proceed to Step 4 until `create_branch` gate is recorded.**

### Step 4: Update Documentation

```bash
# 4a. Update relevant docs
# - If new public API: update API reference in docs/
# - If behavior change: update relevant spec in docs/specs/
# - If architectural decision: write/update ADR in docs/adr/

# 4b. Commit docs changes
git add docs/
git commit -m "docs(#$ISSUE_NUMBER): update documentation for ..."

# 4c. Record gate completion
python .workflow/gate.py advance $TASK_ID update_docs \
  --data '{"docs_updated": ["docs/specs/pipeline.md"]}'
```

**You CANNOT proceed to Step 5 until `update_docs` gate is recorded.**

### Step 5: Update Changelog

```bash
# 5a. Add changelog entry under [Unreleased]
# Format (ALL fields mandatory):
#   - [#ISSUE] Description (@agent, YYYY-MM-DD, branch: BRANCH_NAME, session: TASK_ID)
#
# Example:
#   - [#42] Add TIFF loader to pipeline (@claude, 2026-04-03, branch: feat/issue-42/tiff-loader, session: 20260403-013918-add-tiff-loader)
#
# Fields:
#   @agent     — who made this change (e.g. @claude, @human)
#   YYYY-MM-DD — date of the change
#   branch:    — the git branch name
#   session:   — the workflow gate TASK_ID (from gate.py start output)

# 5b. Commit
git add CHANGELOG.md
git commit -m "chore(#$ISSUE_NUMBER): update changelog"

# 5c. Record gate completion
python .workflow/gate.py advance $TASK_ID update_changelog \
  --data '{"changelog_entry": "[#42] Add TIFF loader to pipeline (@claude, 2026-04-03, branch: feat/issue-42/tiff-loader, session: 20260403-013918-add-tiff-loader)"}'
```

**You CANNOT proceed to Step 6 until `update_changelog` gate is recorded.**

### Step 6: Submit PR

```bash
# 6a. Push and create PR
git push -u origin HEAD
gh pr create --title "feat(#$ISSUE_NUMBER): ..." \
  --body "## Summary\n...\n## Related Issues\nCloses #$ISSUE_NUMBER"

# 6b. Record gate completion
python .workflow/gate.py advance $TASK_ID submit_pr \
  --data '{"pr_number": 48, "pr_url": "https://github.com/.../pull/48"}'
```

---

## Self-Check Protocol

Before executing **any** step, run:

```bash
python .workflow/gate.py status $TASK_ID
```

Verify that the **previous stage shows [DONE]** before attempting the current one.
If you see [LOCK] on the stage you are about to attempt, STOP and complete
the prerequisites first.

## What To Do When Blocked

If `gate.py advance` returns `WORKFLOW GATE: ADVANCEMENT BLOCKED`:

1. **Do not attempt to work around it.**
2. Run `python .workflow/gate.py status $TASK_ID` to see what is missing.
3. Complete the missing prerequisite stage.
4. Then retry.

## Scope Discipline

During implementation (Step 3):

- **Only modify files listed in the Change Plan** (Step 2).
- If you discover additional files need changing, **update the Change Plan comment first**.
- Do not smuggle unrelated changes into the PR.

## Small Changes Still Use Gates

If the task seems too small for the full workflow (e.g., a typo fix):

1. Still create an issue.
2. The change plan can be a single sentence.
3. Docs update can note "N/A — no docs affected".
4. Changelog can note "N/A — trivial fix".
5. **But you still must go through all 6 gates.**

The overhead is intentional. It ensures traceability even for small changes.

## Gate CLI Quick Reference

| Command | Purpose |
|---------|---------|
| `python .workflow/gate.py start "title"` | Start new workflow |
| `python .workflow/gate.py advance TASK STAGE --data '{...}'` | Advance one stage |
| `python .workflow/gate.py status TASK` | Show progress |
| `python .workflow/gate.py list` | List all workflows |
| `python .workflow/gate.py validate TASK STAGE` | Check if stage is reachable |
| `python .workflow/gate.py abort TASK --reason "..."` | Abort workflow |

## Branch Discipline

**NEVER merge into local main.** The local main branch is a read-only reference.
The only commands you run on main are:

```bash
git checkout main       # switch to it
git pull origin main    # sync it with GitHub
git checkout -b ...     # branch off it
```

Merging into main happens **only on GitHub** when the project owner clicks
"Merge pull request". If you run `git merge ... main` locally, you are doing
it wrong.

**One branch = one task.** Do not combine unrelated changes (e.g., CI fixes +
scaffold + registry refactor) in a single branch. Each independent task gets
its own branch and its own PR.

## Handling Merge Conflicts

If your PR shows conflicts on GitHub, it means `origin/main` changed after you
created your branch. Fix it like this:

```bash
git checkout your-branch-name
git fetch origin
git merge origin/main
# Git will show CONFLICT in some files
# Open the files, resolve the conflict markers (<<<< ==== >>>>)
# Then:
git add .
git commit -m "merge: resolve conflict with main"
git push
```

After pushing, the PR on GitHub will update and the conflict will disappear.

**Prevention**: Always create branches from the latest main (see Step 3a above).
If your branch lives for more than a day, periodically sync:

```bash
git fetch origin
git merge origin/main
```

## Branch Cleanup

After completing a task (PR merged or closed), clean up stale branches.

**How to identify dead branches:**

```bash
# Show all local branches with tracking status
# Branches marked "gone" = remote deleted (PR was merged/closed)
git fetch --prune
git branch -vv | grep ': gone]'

# Show branches already merged into main (safe to delete)
git branch --merged main
```

**How to clean up:**

```bash
# Delete a single local branch
git branch -d branch-name

# Delete all local branches whose remote is gone
git fetch --prune
git branch -vv | grep ': gone]' | ForEach-Object { ($_ -match '^\s*(\S+)') | Out-Null; git branch -d $Matches[1] }
```

**Rules:**
- Never delete `main`
- Only delete branches that are merged or whose remote is gone
- Run cleanup at the START of each new task, before creating a new branch
- If `git branch -d` refuses (unmerged changes), use `git branch -D` only if
  you are certain the work is no longer needed


---

# Appendix B: SpecKit Integration

## What SpecKit Is

This project uses [SpecKit](https://github.com/spec-kit) (`.specify/` directory) as the
**feature-level design pipeline**. SpecKit converts a natural language feature
description into structured artifacts (spec, plan, tasks) through a series of
slash commands in Claude Code.

SpecKit skills are auto-discovered from `.claude/skills/speckit-*`. You do NOT
need to memorize their internals — just use the slash commands.

## SpecKit vs Workflow Gate: When to Use Which

These two systems operate at **different granularities** and are complementary.

### SpecKit = Feature-level design pipeline

Use SpecKit when starting a **new feature, subsystem, or significant change**
that needs requirements analysis, design decisions, and task decomposition.

```
/speckit.specify "Add OME-TIFF support to pipeline loader"
  → generates spec.md (what & why)
/speckit.clarify
  → resolves ambiguities in spec
/speckit.plan
  → generates plan.md, data-model.md, contracts/ (how)
/speckit.tasks
  → generates tasks.md (ordered, dependency-aware task list)
/speckit.analyze
  → cross-artifact consistency check (read-only)
```

### Workflow Gate = Per-task execution pipeline

Use the Workflow Gate when **executing each individual task** from the task
list. Every task that touches code must go through the 6-stage gate:

```
gate.py start → create_issue → write_change_plan → create_branch
  → update_docs → update_changelog → submit_pr
```

### Combined Workflow (Standard Operating Procedure)

For any significant feature:

```
Phase 1: Design (SpecKit)
  /speckit.specify "..."     → spec.md
  /speckit.clarify           → refined spec.md
  /speckit.plan              → plan.md + design artifacts
  /speckit.tasks             → tasks.md with T001, T002, T003...

Phase 2: Execute (Workflow Gate, per task)
  For each task in tasks.md:
    gate.py start "T001: ..."
    gate.py advance ... create_issue
    gate.py advance ... write_change_plan
    gate.py advance ... create_branch
    [implement the task]
    gate.py advance ... update_docs
    gate.py advance ... update_changelog
    gate.py advance ... submit_pr
```

### When to Skip SpecKit

For **small, well-understood changes** (typo fixes, config tweaks, simple bug
fixes), you may skip SpecKit and go directly to the Workflow Gate. The decision
rule:

- If the change requires **design decisions** → use SpecKit first
- If the change is **obvious and scoped** → go straight to Workflow Gate

## SpecKit Quick Reference

| Command | Purpose | Output |
|---------|---------|--------|
| `/speckit.constitution` | Define project principles | `.specify/memory/constitution.md` |
| `/speckit.specify "..."` | Generate requirements spec | `specs/<branch>/spec.md` |
| `/speckit.clarify` | Resolve ambiguities (max 5 questions) | Updated `spec.md` |
| `/speckit.plan` | Generate implementation plan | `plan.md`, `data-model.md`, `contracts/` |
| `/speckit.checklist <domain>` | Requirements quality checklist | `checklists/<domain>.md` |
| `/speckit.tasks` | Generate ordered task list | `tasks.md` |
| `/speckit.analyze` | Cross-artifact consistency check | Report (read-only) |
| `/speckit.implement` | Execute tasks from tasks.md | Code changes |
| `/speckit.taskstoissues` | Convert tasks to GitHub Issues | GitHub Issues |


---

# Appendix C: Bug Fix and Issue Resolution Workflow

> Every bug fix and audit finding follows a structured resolution process.
> The goal is traceability: from issue → analysis → decision → branch → fix → tests → PR.

## Step 0: Assess the Issue

Before writing any code, determine what kind of change this is:

| Issue type | Needs ADR? | Needs spec? | Example |
|---|---|---|---|
| Simple bug (clear fix, no design decision) | No | No | #26 ZarrBackend missing axes metadata |
| Bug with design choice (multiple valid approaches) | Yes | No | #25 broadcast_apply: redesign vs scope change |
| Behavior change affecting contracts | Yes | Maybe | #24 CompositeData slot validation |
| New feature or subsystem | Yes | Yes (use SpecKit) | New storage backend |

## Step 1: Write ADR (if needed)

If the fix involves a design decision, document it BEFORE coding:

```bash
# Add a new record to docs/adr/ADR.md
# Format:
#   ## ADR-NNN: <Title>
#   **Status**: Proposed | Accepted | Superseded
#   **Context**: Why this decision is needed
#   **Decision**: What we decided
#   **Alternatives considered**: What else we evaluated
#   **Consequences**: What changes as a result
```

The ADR must be committed as part of the same PR as the fix.

## Step 2: Write Spec (if needed, use SpecKit)

For larger changes that affect contracts or behavior, use SpecKit in Claude Code:

```
/speckit.specify "Fix CompositeData slot contract enforcement"
/speckit.clarify
/speckit.plan
```

For simple bug fixes, skip SpecKit — the GitHub Issue IS the spec.

## Step 3: Create Branch and Implement

**One branch per issue. One issue per branch. No exceptions.**

```bash
git checkout main
git pull origin main
git checkout -b fix/issue-$ISSUE_NUMBER/short-description
```

During implementation:
- Only modify files relevant to THIS issue
- Write tests that cover the fix (both positive and negative cases)
- If you need to update ADR, do it in this branch
- If fixing the issue reveals a DIFFERENT bug, open a new issue — do not fix it here

## Step 4: Verify Locally

Before pushing, confirm:

```bash
# All tests pass
pytest

# Lint clean
ruff check . && ruff format --check .

# Type check clean
mypy src/scieasy/ --ignore-missing-imports
```

## Step 5: Push and Create PR

```bash
git push origin fix/issue-$ISSUE_NUMBER/short-description
gh pr create --title "fix(module): brief description (#$ISSUE_NUMBER)" \
  --body "Closes #$ISSUE_NUMBER

## Summary
...

## Changes
- ...

## ADR
- [ ] ADR updated (if applicable)
- [ ] No ADR needed (simple fix)

## Checklist
- [ ] Tests added covering the fix
- [ ] CHANGELOG updated
- [ ] CI passes"
```

## Step 6: CI Must Pass

Do NOT abandon a PR with failing CI. If CI fails:

1. Read the CI error output
2. Fix the issue locally
3. Commit and push again
4. Repeat until ALL checks pass

Only then is the PR ready for review.

## Example: Fixing Audit Finding #26 (Axes Metadata)

This is a simple bug — no ADR needed, no spec needed:

```
1. Issue #26 already exists on GitHub
2. git checkout main && git pull origin main
3. git checkout -b fix/issue-26/zarr-axes-metadata
4. Edit src/scieasy/core/storage/zarr_backend.py
   - Add axes to metadata in write()
5. Add test in tests/core/test_storage.py
   - Round-trip test: Image with axes → save → load → verify axes preserved
6. Update CHANGELOG:
   - [#26] Persist axis metadata in ZarrBackend write (@claude, 2026-04-03, branch: fix/issue-26/zarr-axes-metadata, session: ...)
7. git push → gh pr create → wait for CI green
```

## Example: Fixing Audit Finding #25 (broadcast_apply)

This requires a design decision — ADR needed:

```
1. Issue #25 already exists on GitHub
2. Write ADR-NNN: broadcast_apply scope decision
   - Option A: Redesign around ViewProxy (more work, full contract compliance)
   - Option B: Scope as in-memory utility, update docs (less work, honest contract)
   - Decision: [whichever is chosen]
3. git checkout -b fix/issue-25/broadcast-apply-scope
4. Implement per ADR decision
5. Update tests, CHANGELOG, push, PR, CI green
```
