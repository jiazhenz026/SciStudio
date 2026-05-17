---
name: agent-manager
description: Use this skill when acting as an agent manager — dispatching multiple sub-agents in parallel across multi-phase work (skeleton → implementation → audit → fix → e2e). Provides standard role-templates (skeleton/implement/audit/fix), a mandatory-checklist pattern, a discipline hook, and tracking-branch convention. Trigger when the user says "dispatch agents", "派出多个agent", "parallel implementation", "ADR cascade", "multi-phase rollout", or describes work across ≥3 sub-agents.
allowed-tools: Read Write Edit Bash Glob Grep Agent
license: MIT
metadata:
    skill-author: Claude (self-authored 2026-05-14)
---

# Agent Manager

## Overview

Codifies the multi-agent dispatch protocol learned from past cascade failures (#810/#811 scope drift, #800 silent UI breakage, #834 hotfix bundle, ADR-033 Phase 1 rollback). When the user asks for parallel multi-agent execution across multiple phases, this skill ensures:

1. **Single source of truth checklist** — one document, every agent edits its own rows, drift is detected mechanically.
2. **Standard role templates** — skeleton / implement / audit / fix prompts with mandatory boilerplate burned in.
3. **Tracking branch convention** — agent feature branches → tracking branch (mergeable after audit) → DO NOT MERGE umbrella PR against main (visibility only).
4. **PostToolUse hook** — fires on checklist edits + TodoWrite/TaskUpdate, reminds to verify drift + artifact links + scope.
5. **Hygiene defaults** — worktree isolation, no `pip install -e .` from worktree, `pytest --timeout=60`, no `npm run dev` background processes.

## When to use this skill

Trigger when:
- The user describes parallel work across ≥3 sub-agents.
- The user asks for an "ADR cascade", "multi-phase rollout", "overnight dispatch", "agent manager mode".
- You're about to dispatch 4+ Agent calls and need to ensure consistency.
- Past cascades have shown drift / scope creep / silent breakage.

Do NOT trigger for:
- Single-agent dispatches.
- Read-only research dispatches (Explore agents).
- One-off bugfixes.

## Standard phase structure

```
Phase 0: Pre-flight (manager runs)
   - Tool checks (python, pytest, ruff, mypy, node, npm, gh, claude CLI)
   - Verify no editable-install pollution: `python -c "import <pkg>; print(<pkg>.__file__)"`
   - Chrome MCP probe (if e2e involves browser)
   - CI baseline (`gh run list --branch main --limit 5`)
   - Stash leftover working tree
   - Create checklist at `docs/planning/<scope>-checklist.md`
   - Install discipline hook (see scripts/remind-checklist-discipline.sh)
   - Create tracking branches off main, push
   - Open umbrella issues (one per track) + per-phase sub-issues
   - Open umbrella PRs (`[DO NOT MERGE]` against main)

Phase 1: Skeleton (parallel, 1 agent per track)
   - Use templates/skeleton-agent.md
   - All function bodies raise NotImplementedError + detailed comment block
   - Test stubs marked xfail/skip with test plan in docstring

Phase 1.5: Skeleton audit (parallel, 1 auditor per track)
   - Use templates/audit-agent.md
   - Verify checklist accuracy, comment-block sufficiency, Codex review reconcile

Phase 1.6: Skeleton fix (conditional, parallel)
   - Use templates/fix-agent.md
   - Only if audit found P1 issues

   → Manager merges skeleton PRs into tracking branches

Phase 2: Implementation (parallel, 2-4 agents per track)
   - Use templates/implement-agent.md
   - Each agent has stable skeleton interface
   - Sequence sibling agents that touch same file

Phase 2.5: Implementation audit (parallel, 1 auditor per track)
   - Use templates/audit-agent.md
   - Mandatory live Chrome smoke for UI-touching tracks

Phase 2.6: Implementation fix (parallel)
   - Use templates/fix-agent.md
   - Override deferred Codex P1

Phase 3: e2e (manager runs in hotfix mode)
   - Small fixes committed straight to tracking branch, one commit per blocker
```

## Goal-hook waiting rule (avoid frequent re-prompts)

When a session-scoped Stop hook with a multi-phase completion condition is active and you are genuinely waiting on a dispatched subagent, do NOT just reply `Waiting` and end the turn. The Stop hook re-fires on every turn end, burning tokens to reaffirm `Waiting` over and over.

Instead, run a **foreground bash `until` loop** that polls for the next concrete artifact (e.g. all expected branch names on origin):

```bash
until [ -n "$(git ls-remote origin 'feat/issue-XXX/*' 2>/dev/null)" ]; do sleep 60; done
```

This pauses the conversation while the loop runs (no stop-hook ping-pong). The harness still notifies you immediately if a subagent completes, AND notifies you when the loop itself exits (condition met).

The harness blocks bare `sleep N` but allows `until <condition>; do sleep N; done` even with long inner sleeps. Some `until` loops still get auto-backgrounded by the harness — that's fine; rely on subagent completion notifications to break out of waiting.

Rule of thumb: every time you'd otherwise reply `Waiting` more than twice in a row, replace it with a foreground until-loop watching the actual condition.

## Mandatory checklist structure

Create `docs/planning/<scope>-checklist.md` with sections:

```markdown
# <Scope> Implementation Checklist
> Mandatory tracking doc. Every agent edits the rows it owns and only those rows.
> Drift = protocol violation.

## Conventions
- [ ] not started · [~] in progress · [x] done · [!] blocked
- Each tick MUST append → <PR-or-commit-link> or → <test-name>

## <Track 1>
### Skeleton (Owner: S<n>)
- [ ] <row> [§<ADR-section>]
...
### Phase 2A (Owner: I<n>a)
...

## <Track 2>
...

## Test phase checklist (e2e — manager runs)
- [ ] <test step verbatim from user spec>

## Acceptance criteria
- [ ] All sub-issue PRs opened, audited, fixed, merged into tracking branches
- [ ] Both umbrella PRs remain [DO NOT MERGE] open
- [ ] Every checkbox checked
- [ ] e2e PASSES = identical (or other binary criterion)

## Drift log (append-only)
(empty until first violation)
```

## Standard agent roles

The four templates in `templates/` are the dispatch prompts. Each begins with the role marker `[DISPATCH-TEMPLATE-V1: <role>]` so the discipline hook (see below) can detect them.

- `templates/00-common-boilerplate.md` — shared rules (worktree isolation, no -e install, pytest --timeout=60, branch from tracking, PR target, `Closes #N`, CI must be green, Codex reconcile, checklist update, scope rules)
- `templates/skeleton-agent.md` — Phase 1: scaffold + comment-driven test plans
- `templates/implement-agent.md` — Phase 2: fill skeleton bodies + tests
- `templates/audit-agent.md` — Phase 1.5/2.5: verify + report (no PR)
- `templates/fix-agent.md` — Phase 1.6/2.6: address audit findings

Read the template, fill in the `## Task content` section at the bottom with the dispatch-specific details (branch name, files in scope, files out of scope, sub-issue number, sibling-agent coordination notes), then pass the combined prompt to `Agent`.

## Discipline hook

Install `scripts/remind-checklist-discipline.sh` at `<project>/scripts/hooks/remind-checklist-discipline.sh` (see the script for the source). Wire into `<project>/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [{"type": "command", "command": "bash scripts/hooks/remind-checklist-discipline.sh"}]
      },
      {
        "matcher": "TaskCreate|TaskUpdate|TaskStop|TodoWrite",
        "hooks": [{"type": "command", "command": "bash scripts/hooks/remind-checklist-discipline.sh"}]
      }
    ]
  }
}
```

The hook fires after every checklist-related edit, reminds the manager to verify drift / artifact links / scope. The script filters internally on `*-checklist.md` for Edit-family tools and always fires for Task-family tools.

## Tracking branch convention

For each track:
- `track/<scope>/<short-name>` is the integration branch
- Agent feature branches: `feat/issue-<sub>/short-desc` off the tracking branch
- Agent PR target: tracking branch (NOT main); mergeable after audit
- One umbrella PR per tracking branch → main, titled `[DO NOT MERGE]`, kept open for visibility

This isolates parallel tracks and keeps main clean. The umbrella PR eventually closes (without merge) when the manager rebases changes to main via a separate clean PR.

## Hygiene rules — burn into every dispatch prompt

1. `isolation: "worktree"` mandatory on every Agent call (see [[feedback_agent_worktree]]).
2. No `pip install -e .` from a worktree (see [[project_editable_install_contamination]]).
3. `pytest --timeout=60` on every pytest call (see [[feedback_agent_discipline_and_pytest_timeout]]).
4. No `npm run dev` background (see [[feedback_stale_dev_server_hygiene]]). Prefer `vitest run`.
5. PR body has `Closes #N` (see [[feedback_pr_must_close_issue]]).
6. CI must be green before report-done (see CLAUDE.md §6.4 in any project enforcing this).
7. UI-touching dispatches require live Chrome smoke (see [[feedback_mandatory_chrome_smoke_test]] and [[feedback_phase_audit_smoke_test]]).
8. Audit must reconcile every Codex auto-review comment (see [[feedback_audit_agent_codex_review]]).
9. Fix agents override deferred Codex P1 (see [[feedback_audit_p1_override]]).
10. Hotfix mode (Phase 3 e2e by manager) per [[feedback_hotfix_vs_refactor_scope]] — small fixes only, one commit per blocker.
11. **Out-of-scope work MUST leave a TODO in the repo** (see [[feedback_out_of_scope_todo]]). Any v1→v2 deferral, ADR-explicit out-of-scope item, "good-enough-for-now" approximation, or known gap MUST be marked with `# TODO(#NNN): <reason> — Out of scope per <ADR §>. Followup: <issue/section>.` Verbal "we'll do that later" is silent tech debt. Burn this into every dispatch prompt: agents must TODO-tag (with tracking link) anything they choose not to implement, rather than silently skipping or pretending it doesn't exist. The dispatch prompt should pre-enumerate the known out-of-scope items so the agent knows where TODOs are mandatory.

## Out-of-scope rules — codify per track

For each track, list explicit out-of-scope directories at the top of the dispatch prompt. Examples (from SciEasy ADR-035/036 dispatch):

- `src/<pkg>/core/` — frozen contracts
- `src/<pkg>/blocks/base/` or analogous foundational classes
- `src/<pkg>/engine/runners/` or analogous scheduler
- ANY ADR / spec / changelog except as authorized

If an agent believes it needs to modify a forbidden file, STOP, post on umbrella issue, exit. Manager escalates to user.

## Stuck-agent diagnosis

If a sub-agent runs longer than expected:
- Check stale processes: `Get-Process` for vite / pytest survivors
- TaskStop the agent if hung
- Inspect its worktree commit history; if it pushed partial work, decide: continue manually or revert
- Don't dispatch a replacement immediately — diagnose root cause first

See [[feedback_agent_discipline_and_pytest_timeout]] and [[feedback_stale_dev_server_hygiene]].

## End-of-dispatch summary template

When all phases land, post a summary to the user:
1. Render checklist with current state (% complete per section)
2. Links to all sub-issue PRs + merge status
3. Links to umbrella `[DO NOT MERGE]` PRs
4. e2e GIFs / screenshots from Chrome MCP
5. Any blockers escalated (with agent's exit comment quoted)
6. Diff of critical files vs main for user sanity-check

## Files in this skill

- `SKILL.md` (this file)
- `templates/00-common-boilerplate.md`
- `templates/skeleton-agent.md`
- `templates/implement-agent.md`
- `templates/audit-agent.md`
- `templates/fix-agent.md`
- `scripts/remind-checklist-discipline.sh` — the hook script (copy into project's `scripts/hooks/`)

## Related memory

- [[feedback_multi_agent_checklist_protocol]]
- [[feedback_ticket_dispatch_playbook]]
- [[feedback_agent_dispatch_lessons]]
- [[feedback_audit_p1_override]]
- [[feedback_mandatory_chrome_smoke_test]]
- [[feedback_phase_audit_smoke_test]]
- [[feedback_agent_discipline_and_pytest_timeout]]
- [[feedback_stale_dev_server_hygiene]]
- [[feedback_pr_must_close_issue]]
- [[feedback_audit_agent_codex_review]]
- [[feedback_hotfix_vs_refactor_scope]]
