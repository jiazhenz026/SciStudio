# Phase 2A — I35a (ADR-035 Backend block runtime)

> Dispatch prompt prepared by manager 2026-05-14. Copy verbatim into Agent prompt
> when skeleton (S35 / #844) lands. Adjust `<SKELETON-PR>` to actual PR number.

---

[DISPATCH-TEMPLATE-V1: implement]

You are **Agent I35a — Backend block runtime** for ADR-035. Sub-issue **#845**, tracking branch **`track/adr-035/ai-block-pty`**, base your feature branch on the merged skeleton from PR #<SKELETON-PR>.

## STEP 0 — read the rules

Read these files in your worktree, follow verbatim:
1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/implement-agent.md`
3. `docs/adr/ADR-035.md` — focus §3.1, §3.2, §3.4, §3.5, §3.6, §3.9
4. `docs/planning/adr-035-036-checklist.md` — your rows are under "Phase 2A — Backend block runtime (I35a)"
5. The skeleton stubs you're filling in (read each file's docstring + comment block before implementing)

## STEP 1 — set up

```bash
git fetch origin
git checkout -b feat/issue-845/block-runtime origin/track/adr-035/ai-block-pty
python -c "import scistudio; print(scistudio.__file__)"
```
Verify scistudio resolves to your worktree. **Do NOT `pip install -e .`** from this worktree.

## STEP 2 — scope IN

You implement (filling stubs left by S35):

- `src/scistudio/blocks/ai/ai_block.py` — full `AIBlock(Block).run()` impl: writes manifest, requests PTY tab via `engine.request_pty_tab()`, transitions to PAUSED, awaits completion signal from `completion.py` watcher, validates outputs via IOBlock loaders, transitions to DONE/ERROR/CANCELLED.
- `src/scistudio/blocks/ai/run_dir.py` — `RunDir` class: per-run `.scistudio/ai-block-runs/{run_id}/` directory creation, manifest writer (atomic temp+rename), transcript copy hook, signal-file path API. Reference `src/scistudio/blocks/app/bridge.py:31-142` for analogous file-exchange pattern.
- `src/scistudio/blocks/ai/completion.py` — `CompletionWatcher` combining: (a) MCP signal file polling under `run_dir/signal/`, (b) `FileWatcher` from `src/scistudio/blocks/app/watcher.py:60-127` on declared `expected_path` outputs, (c) user-button event from engine. Returns first signal that fires, with precedence (a) > (c) > (b) per ADR-035 §3.5.
- `tests/blocks/ai/conftest.py` — `StubAgent` fixture: a fake claude/codex that does NOT spawn a real subprocess; instead it (1) reads the manifest, (2) writes the configured outputs to `expected_path`, (3) writes a finish_ai_block signal file. Used by all unit tests so they don't need real claude binary.
- `tests/blocks/ai/test_ai_block.py` (replace existing if old single-call tests exist; mark old as `@pytest.mark.xfail(reason="superseded by ADR-035")` if you can't delete cleanly): full coverage of run() state machine, manifest contents, completion-signal precedence, validation failures, all three completion paths.

## STEP 3 — scope OUT (DO NOT TOUCH)

- `src/scistudio/engine/` — that's I35b's territory. Use `engine.request_pty_tab()` etc. as opaque calls; if they don't exist as proper functions yet (only stubs), import and call the stub — your tests use `monkeypatch` to fake the IPC.
- `src/scistudio/ai/agent/mcp/tools_workflow.py` — I35b's territory. Same: import the stub, fake it in tests.
- `src/scistudio/api/routes/` — I35b's territory.
- All frontend files — I35c's territory.
- `src/scistudio/core/`, `blocks/base/`, `blocks/registry.py`, `engine/runners/`, `engine/events.py` — frozen.

If you find you need to coordinate with I35b/c, post a comment on #842 asking for the contract. Do NOT silently change the boundary.

## STEP 4 — verify locally

```
ruff format --check . || (ruff format . && git add -u)
ruff check .
pytest tests/blocks/ai -q --timeout=60
pytest -q --timeout=60  # full suite
mypy src/scistudio/blocks/ai/ --ignore-missing-imports
```

## STEP 5 — checklist + commit + PR

Update checklist Phase 2A rows with `→ <commit-sha>` per row.

```
git add -A
git commit -m "feat(adr-035): Phase 2A backend block runtime (#845)"
git push -u origin feat/issue-845/block-runtime
gh pr create --base track/adr-035/ai-block-pty --head feat/issue-845/block-runtime \
  --title "feat(adr-035): Phase 2A backend (#845)" \
  --body "Closes #845

[follow implement-agent.md PR body template; include screenshots if you wrote any debug UI]"
gh pr checks <PR-NUM> --watch
```

## STEP 6 — Codex reconcile + report

After CI green, reply to every Codex comment. Report back with PR URL, files changed, deviations, confirmation of scope. Under 500 words.
