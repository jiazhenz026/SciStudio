# Phase 2B — I35b (ADR-035 Engine PTY control IPC + finish_ai_block MCP tool)

> Dispatch prompt prepared by manager 2026-05-14. Adjust `<SKELETON-PR>` to actual PR.

---

[DISPATCH-TEMPLATE-V1: implement]

You are **Agent I35b — Engine PTY control + MCP** for ADR-035. Sub-issue **#846**, tracking branch **`track/adr-035/ai-block-pty`**, base on merged skeleton PR #<SKELETON-PR>.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/implement-agent.md`
3. `docs/adr/ADR-035.md` — focus §3.5, §3.7, §3.10
4. `docs/planning/adr-035-036-checklist.md` — your rows: "Phase 2B — Engine PTY control + MCP (I35b)"
5. `src/scieasy/api/routes/ai_pty.py:62-226` — the existing user-launched WS PTY route (READ ONLY; you add a sibling endpoint).
6. `src/scieasy/ai/agent/terminal.py:443-535` — `spawn_claude` / `spawn_codex` argv builders (call as-is).
7. `src/scieasy/ai/agent/mcp/_registry.py:33-243` — `ToolEntry` shape + 25-tool catalog (mirror style for `finish_ai_block`).

## STEP 1 — set up

```
git fetch origin
git checkout -b feat/issue-846/engine-mcp origin/track/adr-035/ai-block-pty
python -c "import scieasy; print(scieasy.__file__)"
```
**No `pip install -e .` from worktree.**

## STEP 2 — scope IN

- `src/scieasy/engine/pty_control.py` — full impl of `request_pty_tab(title, spawn_argv, cwd, initial_stdin, block_run_id) -> tab_id` and `notify_block_pty_event(block_run_id, event, detail)`. Worker-side IPC: send a request over the existing engine↔worker channel and block until engine confirms. If no existing engine↔worker channel, you may have to introduce a tiny one — but keep it scoped (single new module file); do NOT modify EventBus contract or scheduler.
- `src/scieasy/ai/agent/mcp/tools_workflow.py` — full impl of `finish_ai_block(outputs: dict[str, str]) -> dict`. Validates: (a) called from inside an AI Block context (presence of `SCIEASY_AI_BLOCK_RUN_ID` env var or signal file path), (b) outputs is dict[str, str], (c) every key matches a declared output port from the manifest. Writes a `signal/finish.json` file under `run_dir`. Returns `{ok: true}` or error envelope `{ok: false, code: "not_in_ai_block_context"|"invalid_outputs"|"already_finished", message: ...}`. Multi-call rejection: second call returns `already_finished` error.
- `src/scieasy/api/routes/ai_pty.py` — ADD a new HTTP endpoint (e.g. `POST /api/ai/pty/engine-spawn`) for engine-initiated tab opens, returning a tab_id. **Do NOT modify** the existing `WS /api/ai/pty/{tab_id}` handler. Your new endpoint internally allocates a tab via the same `_active_ptys` dict + spawn_claude/codex builders, then broadcasts `block_pty_opened` over the workflow WS to the frontend.
- `tests/engine/test_pty_control.py` — IPC roundtrip with mock engine fixture; no real PTY spawned.
- `tests/ai/agent/mcp/test_finish_ai_block.py` — error envelope shapes, multi-call rejection, context detection, output validation.
- `tests/api/test_ai_pty_engine_spawn.py` — endpoint smoke test with monkeypatched spawn_claude.

## STEP 3 — scope OUT

- `src/scieasy/blocks/ai/` — I35a's territory (call AIBlock as opaque consumer; tests use mocks).
- All frontend — I35c's territory.
- The existing `WS /api/ai/pty/{tab_id}` handler — frozen.
- `src/scieasy/core/`, `blocks/base/`, `blocks/registry.py`, `engine/runners/`, `engine/events.py` — frozen. **You MAY emit existing events** (`BLOCK_PAUSED`, `PROCESS_SPAWNED`, `PROCESS_EXITED`) but MAY NOT add new event types.

## STEP 4 — verify

```
ruff format --check . || (ruff format . && git add -u)
ruff check .
pytest tests/engine tests/ai/agent/mcp tests/api/test_ai_pty_engine_spawn.py -q --timeout=60
pytest -q --timeout=60
mypy src/scieasy/engine/ src/scieasy/ai/agent/mcp/ --ignore-missing-imports
```

## STEP 5 — checklist + commit + PR

Update checklist 2B rows. Commit, push, PR with `--base track/adr-035/ai-block-pty`. Body has `Closes #846`. Wait CI green.

## STEP 6 — Codex + report

Reconcile every Codex comment. Report back with PR URL + summary. Under 500 words.
