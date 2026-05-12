---
title: Embedded coding agent — implementation spec & task decomposition
status: draft
issue: 697
adr: 033
date: 2026-05-12
---

# Embedded coding agent implementation spec

## 1. Purpose

This document is the **task-decomposition standard** for the ADR-033 embedded coding agent cascade. It is the single source of truth that:

- The **skeleton agent** of each phase reads to know which files to delete, which to create as placeholders, which directory layout to scaffold, and which imports to wire.
- Each **implementation agent** reads to know exactly which files it owns, what its acceptance criteria are, and where its work fits in the dependency graph for the phase.
- Each **audit agent** reads to verify that an implementation PR did not silently broaden scope, did not weaken type contracts, and satisfied the per-ticket acceptance criteria.

This document does **not** replace ADR-033. It is a *decomposition layer* that breaks the ADR into implementation-sized work units. The ADR remains authoritative for the *what* and *why*; this document is authoritative for *how to dispatch*.

Source documents:

- ADR-033 (PR #696) — embedded coding agent decision record.
- `docs/architecture/ARCHITECTURE.md` §7 — Layer 4 description.
- `docs/architecture/PROJECT_TREE.md` — target file tree.
- `CLAUDE.md` — workflow gate (Appendix A), §6.7 (tests are part of the change), §9.2 (no silent scope expansion).
- `docs/specs/phase11-implementation-standards.md` — precedent for the skeleton / implementation / audit agent contract.

This spec is the checkpoint between *design* (ADR) and *implementation* (PRs). After this document merges, the Phase 1 skeleton agent may be dispatched. Before this document merges, no implementation agent may spawn.

---

## 2. Scope

### In scope (covered by tickets in this spec)

- All code, tests, and documentation changes needed to make the agent chat work end-to-end with a locally installed Claude Code CLI, against a SciEasy project workspace.
- A Codex-CLI alternate provider implementation (Phase 4).
- Deletion of pre-ADR-033 AI surfaces: `ai/generation/`, `ai/synthesis/`, `ai/optimization/`, `ai/config.py`, single-call providers, three legacy REST endpoints, the keyword-routed `AIChat`.
- New user-facing guide `docs/guides/ai-chat.md`.
- Updates to `README.md` and `ROADMAP.md` to point at the new agent layer.

### Out of scope (deliberately deferred)

- **AIBlock revision.** Kept as-is per ADR-033 D9. A separate ADR + spec will decide whether to rewrite AIBlock on top of `AgentProvider` in non-interactive mode.
- **Skill marketplace / sharing.** ADR-033 D7 supports project-local skills, but no GUI for browsing / installing shared skills.
- **Multi-user / collaboration.** One user, one machine; concurrent chats on the same project are supported but cross-user is not.
- **Telemetry / usage analytics.** SciEasy does not collect agent usage data in this phase.
- **Cloud-mode CC** (`claude.ai` web interface, no local install). Local CLI only.

---

## 3. Open Question resolutions

ADR-033 §7 lists ten Open Questions deferred from the ADR. This spec resolves them.

### OQ1 — Hook protocol verification

**Resolution**: Use Claude Code's `PreToolUse` hook as primary mechanism. Fallback to `--allowed-tools` static list + post-hoc diff review if the spike (T-ECA-105) reveals one of these:

- Hook does not fire for MCP tool calls.
- Hook cannot synchronously block on a user decision longer than 5 minutes without CC timing out.
- Hook protocol differs on Windows.

T-ECA-105 is **blocking** for T-ECA-110 (permission backend implementation). If the spike fails, the audit agent for Phase 1 escalates to the human reviewer; the fallback design is then specified in an addendum to this spec.

### OQ2 — MCP transport

**Resolution**: **stdio bridge subprocess**. The FastAPI process exposes the MCP server via a Unix domain socket (POSIX) or named pipe (Windows). A small `scieasy mcp-bridge` subprocess, spawned by CC per the `mcp.json` config, opens the socket and proxies JSON-RPC frames between CC (stdin/stdout) and the socket. Rationale:

- Pure-Python implementation; no extra non-stdlib runtime deps.
- Survives CC restarts (the bridge dies, the FastAPI server keeps running).
- Avoids the in-process MCP-server-as-asyncio-task pitfalls (event-loop blocking, contention with FastAPI request handlers).

### OQ3 — Concurrent-chat resource accounting

**Resolution**: Agent sessions are **NOT** counted by `ResourceManager`. They are tracked by a separate `AgentSessionManager` with its own cap (default 5). Rationale: `ResourceManager` slots are for block executions; an agent session is an idle subprocess most of the time. Conflating the two would either starve real block runs or let agents grab GPU slots they don't use. The two pools are independent.

### OQ4 — Login-state detection

**Resolution**: Spawn `<binary> config get -g installMethod` (Claude Code) or equivalent for Codex with a 2-second timeout. Exit code 0 ⇒ `logged_in=True`. Any non-zero or timeout ⇒ `logged_in=False`. If the user is wrong (we said True but they aren't), the first user message yields an `error` event from stream-json which we surface verbatim. Acceptably imperfect.

### OQ5 — Stream-json schema versioning

**Resolution**: Defensive parser. Unknown event kinds are routed to a generic `OtherEvent { kind, raw_json }` and logged at INFO level; the WebSocket forwards them transparently to the frontend, which renders unknown kinds as a small "(unknown event)" tag. Unknown fields on known event kinds are accepted and ignored. Schema version is read from the `init` event if present and recorded in session metadata; otherwise it is `null`.

### OQ6 — Permission-decision UI latency

**Resolution**: **5-minute soft timeout** for the pending approval. After 5 minutes the backend returns `deny` to the hook with reason `"timed_out"`. The frontend shows a `pending-permission-expired` banner so the user knows what happened. The 5-minute value is configurable in `{project}/.scieasy/settings.json`.

### OQ7 — MCP write tool atomicity

**Resolution**: All MCP write tools that modify on-disk files (`write_workflow`, `update_block_config`) implement a **read-modify-write with file lock**:

```python
with filelock.FileLock(path + ".lock", timeout=10):
    current = load(path)
    new = patch(current, changes)
    write_atomically(path, new)  # write to tmp + rename
```

The frontend's workflow store listens for file-system change events and refreshes the canvas. There is a known race: the user edits on the canvas at exactly the moment the agent is patching the file. Resolution: the canvas debounces edits by 500ms; the file lock holds; whichever write completes first wins, and the other is rejected with a clear conflict error in the chat.

### OQ8 — Codex provider parity

**Resolution**: `AgentProvider` abstracts over the wire protocol. Both providers normalize to a **canonical event stream** with these event kinds: `init`, `assistant_text_delta`, `tool_use`, `tool_result`, `permission_request`, `error`, `done`. Provider-specific events are mapped to canonical ones by the provider's stream parser; provider-unique fields are preserved on the canonical event as a `raw` blob for forensic logging. The frontend renders only canonical events.

If Codex's stream format differs significantly enough that a tool-use round-trip cannot be normalized, the spike at T-ECA-403 (Codex provider proof-of-concept) reports the gap and an addendum to this spec adds a CodexEvent translation table.

### OQ9 — Skill propagation

**Resolution**: **Copy, not symlink**, because of Windows permission constraints. On `start_session()` the provider runs:

```python
src_skills = project_dir / ".scieasy" / "skills"
dst_skills = project_dir / ".claude" / "skills"
if src_skills.exists():
    shutil.copytree(src_skills, dst_skills, dirs_exist_ok=True)
```

User-authored content lives in `.scieasy/skills/`; `.claude/skills/` is a regenerated mirror that SciEasy treats as build output (added to `.gitignore` automatically).

### OQ10 — Project security boundary

**Resolution**: Strict mode (the default) catches `Bash`, `WebFetch`, and any `Edit`/`Write` regardless of path. Strict mode is sufficient as the security boundary. No additional sandboxing env vars or chroot. Bypass mode is by definition outside the security boundary; users opting in own the consequences.

---

## 4. Cross-cutting standards

### 4.1 Logging

Every module under `src/scieasy/ai/agent/` uses `logging.getLogger(__name__)` and emits at these levels:

- `DEBUG` — every stream-json event received; every MCP tool call args + result preview; subprocess stdin writes.
- `INFO` — session start / end; provider discovery results; permission decisions; session ID assignment.
- `WARNING` — unknown stream-json events; degraded paths (e.g., skill copy fails); timed-out permission requests; fallback type construction in MCP write tools.
- `ERROR` — subprocess crash; hook bridge failure; MCP transport breakage; write-tool atomicity violations.

No `print()`. No bare `except:`. No swallowed exceptions without an `ERROR` log + re-raise (or graceful degradation with a `WARNING`).

### 4.2 Error model

A new exception hierarchy under `src/scieasy/ai/agent/errors.py`:

```
AgentError                     # base
├── AgentNotInstalledError     # binary not found
├── AgentNotLoggedInError      # binary present but no OAuth
├── AgentLaunchError           # subprocess failed to spawn or init
├── AgentSessionError          # session-level failures (cap, resume failed)
├── AgentStreamError           # stream-json parse error
├── PermissionDeniedError      # user denied
├── PermissionTimeoutError     # 5-min timeout
└── MCPError                   # base for MCP tool failures
    ├── MCPToolNotFoundError
    ├── MCPInvalidInputError
    ├── MCPInternalError
    └── MCPAtomicityError      # filelock race
```

All errors are HTTP-mapped at the API boundary (`api/routes/ai.py`):

| Exception | HTTP |
|-----------|------|
| `AgentNotInstalledError` | 503 |
| `AgentNotLoggedInError` | 401 |
| `AgentLaunchError`, `AgentSessionError`, `AgentStreamError` | 500 |
| `PermissionDeniedError` | (over WebSocket; not HTTP) |
| `PermissionTimeoutError` | (over WebSocket) |
| MCP errors | (MCP JSON-RPC error frames; not HTTP) |

### 4.3 Testing conventions

- **Unit tests**: per file under `tests/ai/`. Use `pytest`. Mock external subprocesses with `pytest-asyncio` + a stub binary script. **Required for every ticket** unless explicitly waived.
- **Integration tests**: per-phase, in `tests/integration/test_agent_*.py`. Use a real `claude` CLI only when available (skip with `pytest.skip` otherwise) for end-to-end validation.
- **Architecture tests**: extend `tests/architecture/test_layer_deps.py` to verify `ai/agent/` follows Layer 4 rules. Extend `tests/architecture/test_placement.py` to verify the new file layout.
- **Coverage**: project-wide 85% gate must still pass (`pyproject.toml` line). New modules contribute their own tests; lowering the project gate is not acceptable.

### 4.4 Type hints + docstrings

- `from __future__ import annotations` at the top of every new module.
- All public functions / methods have full annotations including return types.
- `Protocol`-typed parameters and structural types where appropriate.
- Module docstrings explain *purpose*; class docstrings explain *invariants*; method docstrings explain *contract*. No "this function does X" filler — the signature already says that.
- mypy `--strict`-equivalent compliance: no `Any` leakage at module boundaries.

### 4.5 Commit & PR conventions

- Branch naming: `feat/issue-<N>/eca-<short>` for implementation; `refactor/issue-<N>/eca-<short>` for the deletion ticket; `docs/issue-<N>/eca-<short>` for docs-only.
- Commit messages: conventional (`feat(ai): ...`, `fix(ai): ...`, etc.).
- Every ticket = one issue + one branch + one PR + 6 gate stages. No bundled PRs across tickets.

### 4.6 Audit agent acceptance gate

An audit agent **must** verify, in order:

1. The PR's diff is confined to the files listed in the ticket's `Owned files`.
2. mypy and ruff are clean (`mypy src/scieasy/ --ignore-missing-imports` and `ruff check . && ruff format --check .`).
3. Unit tests for the ticket exist and pass.
4. Coverage for the new code is ≥ 85%.
5. The acceptance criteria in the ticket are each individually satisfied.
6. No CLAUDE.md violations (commit format, branch naming, gate stages).
7. (For phases 2+) Open Question resolutions in §3 are honoured.

If any check fails, the audit agent leaves a review comment with `CHANGES_REQUESTED` and the specific failure. Audit does NOT push fixes — the implementation agent re-runs.

---

## 5. Phase 1 — Agent runtime backbone

**Goal**: End-to-end stream-json flow from CC subprocess to chat WebSocket, with one tool (Claude Code's native `Read`) working through permission gating.

**Prerequisite**: ADR-033 (PR #696) merged or in-flight; spec (this doc) merged.

**Exit gate**: A developer can fire `python -c "import asyncio; from scieasy.ai.agent import demo; asyncio.run(demo())"` and see a mocked CC session produce stream-json that flows out the chat WebSocket, with permission requests round-tripping correctly.

**Phase-1 tickets**:

### T-ECA-101 — Module skeleton (scaffold)

**Agent role**: SCAFFOLD AGENT for Phase 1.
**Owned files** (create empty / stub):

- `src/scieasy/ai/agent/__init__.py`
- `src/scieasy/ai/agent/provider.py` — `AgentProvider` Protocol, `ProviderStatus` dataclass, `PermissionMode` enum, `AgentEvent` dataclass, `AgentSession` Protocol; all class bodies populated with full signatures + docstrings + `raise NotImplementedError`.
- `src/scieasy/ai/agent/errors.py` — full exception hierarchy from §4.2.
- `src/scieasy/ai/agent/binary_discovery.py` — `find_binary(name: str) -> Path | None` stub.
- `src/scieasy/ai/agent/stream_json.py` — `parse_event(line: bytes) -> AgentEvent` stub.
- `src/scieasy/ai/agent/session.py` — `AgentSessionManager` stub.
- `src/scieasy/ai/agent/permission.py` — `PermissionPolicy` stub with the strict / bypass mode constants.
- `src/scieasy/ai/agent/transcript.py` — `TranscriptWriter` stub.
- `src/scieasy/ai/agent/system_prompt.py` — empty module with section A / B / C / D module-level constants set to `""`.
- `src/scieasy/ai/agent/claude_code.py` — `ClaudeCodeProvider` class with `discover()` and `start_session()` stubs.
- `tests/ai/__init__.py` (if missing)
- `tests/ai/test_phase1_skeleton.py` — verifies the module imports and the Protocols are implementable. Single test: `def test_module_imports_clean(): from scieasy.ai.agent import provider, errors, ...`.

**Acceptance criteria**:

- All listed files exist with the specified contents.
- `mypy src/scieasy/ai/agent/` is clean (`--ignore-missing-imports`).
- `pytest tests/ai/test_phase1_skeleton.py` passes.
- No file in `src/scieasy/ai/agent/` references `anthropic` or `openai` SDK imports.

**Dependencies**: none.

### T-ECA-102 — Binary discovery (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-103).
**Owned files**: `src/scieasy/ai/agent/binary_discovery.py`, `tests/ai/test_binary_discovery.py`.

**Implementation requirements**:

- `find_binary(name: str) -> Path | None` searches the 8 fallback locations from ADR-033 §3 D1.2 in the specified order. First hit wins.
- Returns `None` if not found anywhere.
- Logs at DEBUG which paths were searched and which path was a hit.
- Windows registry access uses `winreg.OpenKey(HKEY_CURRENT_USER, "Environment")` + `HKEY_LOCAL_MACHINE\System\CurrentControlSet\Control\Session Manager\Environment` and parses the `Path` value.
- Login-shell resolution: `subprocess.run(["bash", "-lc", f"command -v {name}"], capture_output=True, timeout=2)` with a try/except that treats `FileNotFoundError` (no bash) as a non-match.

**Tests**:

- 8 unit tests, one per fallback location, mocking the filesystem and `subprocess.run`.
- 1 integration test that skips when `claude` isn't on PATH but otherwise verifies `find_binary("claude")` returns a real path.
- Tests run on Linux + macOS + Windows in CI (existing matrix).

**Acceptance criteria**:

- All 9 tests pass on all 3 OSes.
- Empty-PATH environment returns `None` not an error.
- Windows-registry path is exercised by a mock on non-Windows runners.

**Dependencies**: T-ECA-101 (skeleton).

### T-ECA-103 — Stream-JSON parser (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-102).
**Owned files**: `src/scieasy/ai/agent/stream_json.py`, `tests/ai/test_stream_json.py`, `tests/fixtures/stream_json/*.ndjson`.

**Implementation requirements**:

- `parse_event(line: bytes) -> AgentEvent` parses one NDJSON line.
- Unknown event kinds → `OtherEvent { kind, raw_json }`, logged at INFO.
- Unknown fields on known event kinds → silently ignored.
- Canonical event kinds: `init`, `assistant_text_delta`, `tool_use`, `tool_result`, `permission_request`, `error`, `done`. Each has a dataclass under `AgentEvent` union.
- `parse_stream(stream: AsyncIterator[bytes]) -> AsyncIterator[AgentEvent]` async generator wrapper that handles bounded buffering (no event longer than 1 MiB; longer ⇒ `AgentStreamError`).

**Tests**:

- Round-trip tests using fixtures captured from a real CC session (provided in `tests/fixtures/stream_json/`).
- Malformed-line tests (truncated JSON, non-UTF8, oversized lines).
- Unknown-kind test verifies `OtherEvent` path.

**Acceptance criteria**:

- 100% line coverage on `stream_json.py`.
- mypy clean.
- Fixtures committed; no real API keys in fixtures.

**Dependencies**: T-ECA-101 (skeleton).

### T-ECA-104 — ClaudeCodeProvider + subprocess lifecycle (impl)

**Agent role**: IMPLEMENTATION AGENT (sequential after T-ECA-102 and T-ECA-103).
**Owned files**: `src/scieasy/ai/agent/claude_code.py`, `tests/ai/test_claude_code.py`, `tests/fixtures/stub_claude.py`.

**Implementation requirements**:

- `ClaudeCodeProvider.discover()` calls `find_binary("claude")`, runs `<bin> --version` with 5-second timeout, runs the login-state probe (OQ4), returns a `ProviderStatus`.
- `ClaudeCodeProvider.start_session()`:
  - Composes spawn args: `--output-format stream-json --verbose --append-system-prompt @<prompt_file> --mcp-config @<mcp_file>` (+ `--resume <id>` if resuming, `--model <m>` if specified).
  - Writes prompt and mcp config to temp files via `tempfile.NamedTemporaryFile(delete=False)`; tracks them for cleanup on session close.
  - Spawns via `asyncio.create_subprocess_exec(stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=project_dir)`.
  - On Windows, passes `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`.
  - Returns an `AgentSession` instance wrapping the `Popen` + the stream parser.
- `AgentSession.send_user_message(content)` writes the message JSON to stdin and flushes (does **not** close stdin — CC supports multi-turn over one process).
- `AgentSession.stream_events()` async-yields canonical `AgentEvent`s from the parser.
- `AgentSession.cancel()` calls `os.killpg` (POSIX) or `taskkill /T /F /PID` (Windows) for tree-kill.
- `AgentSession.close()` awaits the subprocess, releases temp files.

**Stub binary**:

`tests/fixtures/stub_claude.py` is a Python script that mimics `claude --output-format stream-json` for tests: reads stdin JSON, emits a canned stream-json sequence (init → assistant_text_delta×N → tool_use → tool_result → done) on stdout. The test passes `--binary-path` pointing at this stub to bypass real CC.

**Tests**:

- 6+ unit tests: spawn + happy path, spawn + crash, send_user_message + multi-turn, cancel mid-stream, close cleanup, temp-file lifecycle.
- 1 Windows-specific test asserting `CREATE_NEW_PROCESS_GROUP` flag (mocked).
- 1 cancellation test asserting child-process group is killed.

**Acceptance criteria**:

- All tests pass on Linux + macOS + Windows.
- mypy clean.
- No temp-file leaks (test fixture verifies `tempfile.gettempdir()` count is unchanged after `close()`).

**Dependencies**: T-ECA-102, T-ECA-103.

### T-ECA-105 — Hook protocol spike

**Agent role**: IMPLEMENTATION AGENT (sequential, blocking T-ECA-110).
**Owned files**: `docs/specs/eca-spike-hook-protocol.md` (write-up only), `tests/ai/spike_hook_protocol.py` (excluded from CI test run).

**Goal**: empirically verify the three properties in OQ1 by running against a real CC binary. The spike writes a short hook script, registers it in `claude-hooks.json`, runs a CC session that triggers a `Read` and an MCP read tool, and observes:

1. Does the hook fire for the MCP tool call?
2. Can the hook block for 30 seconds and still get a clean approve flow?
3. Same on Windows.

**Deliverables**:

- A 100-300 line write-up in `docs/specs/eca-spike-hook-protocol.md` with: what was run, what was observed, conclusion (PROCEED with hooks / FALLBACK to allowlist).
- If FALLBACK: addendum to this spec adding T-ECA-110-FALLBACK ticket; T-ECA-110 is replaced.
- If PROCEED: addendum-free; T-ECA-110 proceeds as specified.

**Acceptance criteria**:

- Write-up committed.
- Conclusion is unambiguous (PROCEED or FALLBACK).
- If PROCEED: example `claude-hooks.json` + example hook script are committed under `docs/specs/`.

**Dependencies**: T-ECA-104 (needs a working session to spike against).

### T-ECA-106 — SessionManager + state persistence (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-105 spike).
**Owned files**: `src/scieasy/ai/agent/session.py`, `src/scieasy/ai/agent/transcript.py`, `tests/ai/test_session_manager.py`, `tests/ai/test_transcript.py`.

**Implementation requirements**:

- `AgentSessionManager`:
  - `dict[tuple[Path, str], AgentSession]` keyed by `(project_dir, chat_id)`.
  - Cap = 5 per project; 6th `start_session` raises `AgentSessionError("concurrent chat cap reached")`.
  - `start_session(project_dir, chat_id, ...)` writes / updates `{project_dir}/.scieasy/sessions/{chat_id}.json` metadata before spawning.
  - `get_session(project_dir, chat_id)` returns the live session or None.
  - `close_session(project_dir, chat_id)` calls `session.close()`, leaves metadata file in place.
  - `shutdown_all()` for FastAPI lifespan teardown.
- Session metadata format:
  ```json
  {
    "chat_id": "uuid",
    "title": "user-editable",
    "created": "ISO 8601",
    "last_active": "ISO 8601",
    "provider": "claude-code",
    "model": "...",
    "system_prompt_hash": "sha256",
    "session_id": "from-init-event",
    "bypass_mode": false,
    "total_turns": 0
  }
  ```
- `TranscriptWriter` opens `{project_dir}/.scieasy/sessions/{chat_id}/transcript.jsonl` in append mode, writes one canonical event per line, flushes after each. Best-effort: write failures log WARNING but do not raise.

**Tests**:

- Cap-exceeded test.
- Metadata persistence: kill session midway, reopen, verify metadata reflects state.
- Transcript write-fail test (read-only directory) verifies graceful degradation.

**Acceptance criteria**:

- Cap is enforced.
- Metadata schema validated by Pydantic model.
- Transcript file format compatible with line-oriented `jq` consumption (each line a valid JSON event).

**Dependencies**: T-ECA-104.

### T-ECA-107 — WebSocket chat route + status route (impl)

**Agent role**: IMPLEMENTATION AGENT (sequential after T-ECA-106).
**Owned files**: `src/scieasy/api/routes/ai.py`, `src/scieasy/api/schemas.py` (additions only — no deletions yet), `tests/api/test_ai_chat_route.py`.

**Implementation requirements**:

- `WS /api/ai/chat/{chat_id}` route:
  - On connect: ensures the chat session exists (start it if first connect, else attach).
  - Accepts client messages: `{ "type": "user_message", "content": str }`, `{ "type": "cancel" }`. (Permission decisions are handled in T-ECA-110.)
  - Forwards every canonical `AgentEvent` from the session's stream to the client as `{ "type": "agent_event", "event": {...} }`.
  - On client disconnect: closes the session (does NOT delete metadata).
- `GET /api/ai/status` route:
  - Returns `{ providers: [...ProviderStatus] }` for all registered providers (initially just Claude Code; Codex added in Phase 4).
- New Pydantic schemas in `schemas.py`: `ProviderStatusResponse`, `ChatClientMessage`, `AgentEventEnvelope`.

**Tests**:

- Status endpoint mocked provider returns correct dict.
- WS happy-path: client sends `user_message`, gets `agent_event` stream until `done`.
- WS cancel: client sends `cancel`, session is killed.
- WS disconnect: closing the WS cleans up the session.

**Acceptance criteria**:

- mypy clean; `from typing import ...` import discipline matches the rest of `api/routes/`.
- The three old `POST /api/ai/*` routes are NOT touched (deletion happens in Phase 4).
- New endpoints follow the existing `APIRouter(prefix="/api/ai", tags=["ai"])` convention.

**Dependencies**: T-ECA-106.

### T-ECA-108 — Static MCP config + hook config emission (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-107).
**Owned files**: `src/scieasy/ai/agent/config_files.py`, `tests/ai/test_config_files.py`.

**Implementation requirements**:

- `write_mcp_config(project_dir, chat_id) -> Path` writes `{project_dir}/.scieasy/mcp.json` (overwriting) with the MCP server config from ADR-033 §3 D2.3.
- `write_hook_config(project_dir, permission_mode) -> Path` writes `{project_dir}/.scieasy/claude-hooks.json` configuring the `PreToolUse` hook to point at `scieasy hook-bridge`.
- Both functions are idempotent — same input ⇒ same output ⇒ no spurious git diffs.

**Tests**:

- Round-trip: write → read → verify exact bytes.
- Bypass mode → hook config omits the PreToolUse hook entirely.
- Permission strict mode → hook config registers the bridge.

**Acceptance criteria**:

- Generated files are valid JSON with stable key ordering.
- `.scieasy/` directory is auto-created if missing.

**Dependencies**: T-ECA-101.

### T-ECA-109 — Phase-1 demo + integration test (impl)

**Agent role**: IMPLEMENTATION AGENT (sequential after T-ECA-107, T-ECA-108).
**Owned files**: `src/scieasy/ai/agent/demo.py`, `tests/integration/test_phase1_end_to_end.py`.

**Implementation requirements**:

- `scieasy.ai.agent.demo.main()` async function that spawns a CC session via the stub binary, sends a synthetic "list files" prompt, prints each event.
- Integration test that runs the demo against the stub and asserts a specific event sequence (init → assistant_text_delta × N → done).

**Acceptance criteria**:

- Demo runs in < 5 seconds against the stub.
- Test deterministic on all OSes.

**Dependencies**: T-ECA-107, T-ECA-108.

### T-ECA-110 — Permission backend + hook bridge (impl)

**Agent role**: IMPLEMENTATION AGENT (sequential after T-ECA-105 spike confirms PROCEED).
**Owned files**: `src/scieasy/ai/agent/permission.py`, `src/scieasy/api/routes/ai.py` (add the two permission endpoints), `src/scieasy/cli/hook_bridge.py`, `tests/ai/test_permission.py`.

**Implementation requirements**:

- `PermissionPolicy` class:
  - `mode: PermissionMode` (STRICT | BYPASS).
  - `should_auto_approve(tool_name, tool_input) -> bool`. STRICT mode: only the 8 read-only Claude Code natives (`Read`, `Glob`, `Grep`, `WebSearch`, `TodoWrite`, `NotebookRead`, `BashOutput`, `KillShell`) + every MCP read tool (per §6 ticket list). All else returns False.
- `POST /api/ai/permission-check` endpoint:
  - Receives `{chat_id, tool_name, tool_input}`.
  - If auto-approve → returns `{action: "approve"}` immediately.
  - Else creates an `asyncio.Event` keyed by a fresh `request_id`, broadcasts a `permission_request` WS message to the chat connection, awaits the event with 5-minute timeout. On timeout returns `{action: "deny", reason: "timed_out"}`.
- `POST /api/ai/permission-decision` endpoint:
  - Receives `{chat_id, request_id, decision: "approve" | "deny"}`.
  - Signals the matching `asyncio.Event` with the decision.
- `scieasy hook-bridge` CLI subcommand:
  - Reads CC's PreToolUse hook payload from stdin (JSON).
  - POSTs to `/api/ai/permission-check`.
  - Exits 0 on approve, 2 on deny.

**Tests**:

- Auto-approve path returns immediately.
- Approval-with-user happy path.
- Denial path returns 2 from `hook-bridge`.
- Timeout path returns 2 from `hook-bridge` with `deny:timed_out` reason in logs.
- Bypass mode auto-approves everything.

**Acceptance criteria**:

- mypy clean.
- The hook bridge is invokable as `scieasy hook-bridge` (registered in `pyproject.toml` `[project.scripts]`).
- WS messages for permission requests don't block other agent events on the same connection.

**Dependencies**: T-ECA-105 (spike), T-ECA-107 (WS infrastructure).

### Phase-1 audit ticket

### T-ECA-119 — Phase-1 audit pass

**Agent role**: AUDIT AGENT for Phase 1.
**Owned files**: none (review-only); produces review comments on T-ECA-101..110 PRs.

**Audit checklist** (in addition to §4.6):

- [ ] All 9 implementation tickets have their PRs merged or open with green CI.
- [ ] Architecture tests pass; `ai/` does not import from `engine/` / `api/` (forbidden direction).
- [ ] Stream-json parser handles every fixture in `tests/fixtures/stream_json/`.
- [ ] T-ECA-105 spike conclusion is honoured by T-ECA-110.
- [ ] No `pyproject.toml` `[project.scripts]` entry name collisions for `scieasy hook-bridge`.
- [ ] No file outside `src/scieasy/ai/agent/`, `src/scieasy/api/routes/ai.py`, `src/scieasy/api/schemas.py`, `src/scieasy/cli/`, `tests/ai/`, `tests/integration/` is touched.

**Acceptance criteria**:

- All 10 tickets cleared by audit OR have a clear list of required fixes.
- Phase-1 demo runs end-to-end successfully on Linux + macOS + Windows.

**Dependencies**: All of T-ECA-101..110.

---

## 6. Phase 2 — MCP server + tools

**Goal**: Agent can call the 25 SciEasy MCP tools with correct semantics, permissions, and error handling.

**Prerequisite**: Phase 1 complete; T-ECA-119 audit passed.

**Exit gate**: A developer spawns a CC session and types "what blocks are installed?" The agent correctly invokes `list_blocks` via MCP and reports the result. Same for "validate this workflow" → `validate_workflow`.

### T-ECA-201 — MCP server skeleton (scaffold)

**Agent role**: SCAFFOLD AGENT for Phase 2.
**Owned files**:

- `src/scieasy/ai/agent/mcp/__init__.py`
- `src/scieasy/ai/agent/mcp/server.py` — server scaffold + stdio transport over Unix socket / named pipe.
- `src/scieasy/ai/agent/mcp/tools_workflow.py` — stub functions for all 9 (a) tools.
- `src/scieasy/ai/agent/mcp/tools_authoring.py` — stub for all 5 (b) tools.
- `src/scieasy/ai/agent/mcp/tools_inspection.py` — stub for all 7 (c) tools.
- `src/scieasy/ai/agent/mcp/tools_qa.py` — stub for all 4 (d) tools.
- `src/scieasy/cli/mcp_bridge.py` — `scieasy mcp-bridge` subcommand.
- `tests/ai/test_mcp_server_skeleton.py` — verifies server starts, accepts connections, responds to `list_tools` request.

**Acceptance criteria**:

- All stubs implement the tool name and schema; bodies raise `NotImplementedError`.
- `scieasy mcp-bridge --help` works.
- `pytest tests/ai/test_mcp_server_skeleton.py` passes.

**Dependencies**: T-ECA-119 (Phase 1 complete).

### T-ECA-202 — Category (a) workflow tools (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-203 and T-ECA-204).
**Owned files**: `src/scieasy/ai/agent/mcp/tools_workflow.py`, `tests/ai/test_mcp_tools_workflow.py`.

**Tools to implement** (9):

| Tool | Impl notes |
|------|-----------|
| `list_blocks()` | Call `get_block_registry().all_specs()`; serialize via existing `BlockSpec.to_dict()`-equivalent or new helper. |
| `get_block_schema(type_name)` | Call `BlockRegistry.instantiate(...)` and return ports + `config_schema`. |
| `list_types()` | Call `get_type_registry().all_types()` and return hierarchy. |
| `get_workflow(path)` | `workflow.serializer.load_yaml(path)` then `WorkflowDefinition.model_dump()`. |
| `validate_workflow(yaml_or_path)` | If string starts with `name:` or contains `nodes:` treat as YAML inline; else as path. Call `validate_workflow()`. |
| `write_workflow(path, yaml)` | File-locked atomic write (OQ7). Logs `INFO` for each successful write. |
| `run_workflow(path)` | `await scheduler.execute(workflow)` returning the assigned `run_id` immediately (do not wait for completion). |
| `cancel_run(run_id)` | Emit `CANCEL_WORKFLOW_REQUEST` event. |
| `get_run_status(run_id)` | Query the scheduler's in-memory run-state dict. |

**Tests**: one happy-path + one error-path per tool. 18 tests total.

**Acceptance criteria**:

- mypy clean.
- All 9 tools registered in the MCP server's `list_tools` response.
- Write-class tools (3 of 9) go through the permission policy (auto-approve in tests via bypass mode).

**Dependencies**: T-ECA-201.

### T-ECA-203 — Categories (b) + (c) tools (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-202 and T-ECA-204).
**Owned files**: `src/scieasy/ai/agent/mcp/tools_authoring.py`, `src/scieasy/ai/agent/mcp/tools_inspection.py`, `tests/ai/test_mcp_tools_authoring.py`, `tests/ai/test_mcp_tools_inspection.py`.

**Tools to implement** (5 + 7 = 12):

| Tool | Impl notes |
|------|-----------|
| `read_block_source(type_name)` | `inspect.getfile(block_cls)` + `Path.read_text()`. |
| `list_block_examples(category)` | Hard-coded curated list under `src/scieasy/blocks/{category}/` to start; configurable in v2. |
| `scaffold_block(name, category)` | Renders from `docs/block-development/templates/` (existing) into `{project}/blocks/{name}.py`. |
| `reload_blocks()` | `get_block_registry().hot_reload()`. |
| `run_block_tests(type_name)` | Discovers the test path heuristically (`tests/blocks/test_<name>.py`) and runs `pytest --tb=short` capturing output. |
| `get_block_output(run_id, block_id, port)` | Look up the run's recorded output map; return `StorageReference` + `TypeSignature`. |
| `inspect_data(ref)` | Query `MetadataStore` (ADR-032). |
| `preview_data(ref, fmt)` | Type-dispatch: DataFrame→arrow.slice(100).to_pylist; Array→thumbnail PIL→PNG base64 (clamp to 256×256); Series→first 200; Text→first 4096 chars; Artifact→size + thumbnail if image. |
| `get_lineage(ref)` | `MetadataStore.ancestors_recursive(...)`. |
| `get_block_config(workflow_path, block_id)` | Load workflow, find node, return `node.config.params`. |
| `update_block_config(workflow_path, block_id, params)` | File-locked update (OQ7). |
| `get_block_logs(run_id, block_id)` | Return captured stdout/stderr from the run's log store. |

**Tests**: 24 tests (one happy + one error per tool).

**Acceptance criteria**:

- mypy clean.
- `preview_data` for arrays does not OOM on a 4 GB synthetic array (test verifies thumbnail computation uses `iter_chunks` not `to_memory`).
- `update_block_config` round-trip preserves comments and key order in the YAML (use `ruamel.yaml`, not `pyyaml`, for round-trip fidelity).

**Dependencies**: T-ECA-201.

### T-ECA-204 — Category (d) tools + system prompt builtin (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-202 and T-ECA-203).
**Owned files**: `src/scieasy/ai/agent/mcp/tools_qa.py`, `src/scieasy/ai/agent/system_prompt.py`, `tests/ai/test_mcp_tools_qa.py`, `tests/ai/test_system_prompt.py`.

**Tools to implement** (4):

| Tool | Impl notes |
|------|-----------|
| `search_docs(query, scope)` | Walk `docs/`; filter by `scope` if specified; return top-N matches with line numbers via a simple substring or fuzzy match. |
| `get_doc(path)` | Validate path is within `docs/`; read; return text. |
| `list_data(project_dir)` | Enumerate `data/zarr/`, `data/parquet/`, `data/artifacts/`. |
| `get_project_info()` | Read `project.yaml`, list workflows, return last-N run summaries from lineage store. |

**System prompt builtin**:

- Implement `compose_system_prompt(project_dir) -> str` that returns the three-tier concatenation per ADR-033 §3 D3.
- The builtin content matches ADR-033 §3 D3.2 Sections A–D verbatim. Sections C and D are populated by enumerating the MCP tool registry at runtime so the prompt is always in sync with the actual tool set.

**Tests**:

- Each tool: 1 happy + 1 error.
- System prompt: sections A, B, C, D all present; section C lists every registered MCP tool exactly once; overlays append correctly.

**Acceptance criteria**:

- mypy clean.
- System prompt is reproducible (same project_dir + same registry ⇒ same hash).

**Dependencies**: T-ECA-201.

### T-ECA-205 — MCP integration in-process wiring (impl)

**Agent role**: IMPLEMENTATION AGENT (sequential after T-ECA-202, T-ECA-203, T-ECA-204).
**Owned files**: `src/scieasy/ai/agent/mcp/server.py` (finalize), `src/scieasy/api/app.py` (add MCP server startup hook), `tests/integration/test_phase2_mcp_end_to_end.py`.

**Implementation requirements**:

- FastAPI lifespan handler starts an MCP server bound to a local socket; teardown stops it.
- `scieasy mcp-bridge --socket <path>` proxies stdin/stdout to/from that socket.
- All 25 tools dispatched correctly via JSON-RPC.

**Tests**:

- End-to-end: spawn CC against the stub, instruct it to call `list_blocks`, verify the response reaches the chat WebSocket as `tool_result`.

**Acceptance criteria**:

- Integration test passes on all OSes (Windows uses named pipe transport).
- Server graceful shutdown on Ctrl+C.

**Dependencies**: T-ECA-202, T-ECA-203, T-ECA-204.

### T-ECA-225 — Phase-2 audit pass

**Agent role**: AUDIT AGENT for Phase 2.

**Audit checklist**:

- [ ] 25 tools all wired in `list_tools` MCP response.
- [ ] No tool talks to the network without the user's permission scope (i.e. no tool calls Anthropic / OpenAI APIs directly).
- [ ] `inspect_data` / `preview_data` do not load payloads larger than 8 MiB into memory.
- [ ] All write tools log INFO with the diff summary.
- [ ] System prompt's Section C tool enumeration matches the actual registered tool set.

**Dependencies**: T-ECA-201..205.

---

## 7. Phase 3 — Frontend rewrite + permission UI + session sidebar

**Goal**: Browser user can install CC, log in, open the AIChat tab, ask the agent to modify a workflow, see a permission prompt with diff preview, approve / deny, and see the result.

**Prerequisite**: Phase 2 complete; T-ECA-225 audit passed.

### T-ECA-301 — Frontend scaffold + old code deletion (scaffold)

**Agent role**: SCAFFOLD AGENT for Phase 3.
**Owned files**:

- DELETE: `frontend/src/components/AIChat.tsx` (the existing keyword-routed one), `frontend/src/components/AIChat.test.tsx`.
- DELETE in `frontend/src/App.tsx`: the `onSendChat` callback + its imports.
- CREATE empty stubs:
  - `frontend/src/components/AIChat/AIChat.tsx`
  - `frontend/src/components/AIChat/ChatMessageList.tsx`
  - `frontend/src/components/AIChat/EventRenderer.tsx`
  - `frontend/src/components/AIChat/SessionSidebar.tsx`
  - `frontend/src/components/AIChat/AgentStatusBanner.tsx`
  - `frontend/src/components/AIChat/PermissionPrompt.tsx`
  - `frontend/src/components/AIChat/SettingsPanel.tsx`
  - `frontend/src/components/AIChat/index.ts`
  - `frontend/src/hooks/useAgentWebSocket.ts`
  - `frontend/src/stores/aiChatSlice.ts`
  - `frontend/src/types/agentEvents.ts`

Each stub exports the component / hook / slice with empty render / no-op body.

**Acceptance criteria**:

- `npm run build` succeeds.
- `npm run typecheck` clean.
- No reference to the old `AIChat.tsx` remains in the codebase (`grep -r "AIChat" frontend/src/` only matches the new path).

**Dependencies**: T-ECA-225.

### T-ECA-302 — Backend WS protocol finalize (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-303).
**Owned files**: `src/scieasy/api/routes/ai.py` (extend), `src/scieasy/api/schemas.py` (event envelope schemas), `tests/api/test_ai_chat_ws_v2.py`.

**Implementation requirements**:

- WS message types finalized per ADR-033 §3 D5.2:
  - Client → server: `user_message`, `cancel`, `permission_decision`.
  - Server → client: `agent_event`, `permission_request`, `session_ended`, `error`.
- All envelopes typed in `schemas.py` as `BaseModel`s; the WS handler validates via `model_validate`.

**Acceptance criteria**:

- Each message type has a Pydantic model.
- Tests cover every (client_msg → expected_server_msg) pair.

**Dependencies**: T-ECA-301.

### T-ECA-303 — Frontend AIChat + EventRenderer (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-302).
**Owned files**: `frontend/src/components/AIChat/*`, `frontend/src/hooks/useAgentWebSocket.ts`, `frontend/src/stores/aiChatSlice.ts`, `frontend/src/types/agentEvents.ts`, `frontend/src/components/AIChat/__tests__/*.test.tsx`.

**Implementation requirements** (highlights):

- `AIChat.tsx` composes the sub-components per ADR-033 §3 D5.1.
- `useAgentWebSocket` opens `WS /api/ai/chat/{chatId}`, dispatches events into `aiChatSlice`, handles reconnect with backoff.
- `EventRenderer.tsx` dispatches on event kind:
  - `assistant_text` → streaming text bubble.
  - `tool_use` → collapsed card showing tool name + args summary.
  - `tool_result` → nested card under the tool_use.
  - `permission_request` → invokes `PermissionPrompt` modal.
  - `thinking`, `error`, `done` → small inline badges.
- `SessionSidebar.tsx` lists sessions from `GET /api/projects/{id}/sessions` (new helper endpoint or inline list); supports create / rename / delete.
- `AgentStatusBanner.tsx` polls `GET /api/ai/status` on mount + every 60s; renders `not_installed` / `installed_not_logged_in` / `bypass_mode_active` / hidden.
- `PermissionPrompt.tsx` modal with tool name, args, diff preview (Monaco diff for Edit/Write/update_block_config/write_workflow), three buttons: Approve / Deny / Always-allow-this-tool.
- `SettingsPanel.tsx` lives under the bottom panel; provider selector, permission mode, concurrent-chat cap.

**Tests** (Vitest + RTL):

- Each component: render test, interaction test, ~10 tests total.
- `useAgentWebSocket`: reconnect, message dispatch.

**Acceptance criteria**:

- `npm run typecheck` + `npm run lint` + `npm run test` all green.
- The component tree is purely functional; no class components; Zustand for state.

**Dependencies**: T-ECA-301.

### T-ECA-318 — Phase-3 audit pass

**Agent role**: AUDIT AGENT for Phase 3.

**Audit checklist**:

- [ ] Old `AIChat.tsx` and `onSendChat` keyword router are confirmed deleted (no references).
- [ ] Old `POST /api/ai/generate-block` etc. are still present (deleted in Phase 4 only).
- [ ] `npm run build` produces a bundle that successfully renders the AIChat tab in a manual smoke test.
- [ ] Permission prompts block agent progress until the user decides (no race where the agent advances on its own).
- [ ] Bypass mode banner is visible at all times when active.

**Dependencies**: T-ECA-301..303.

---

## 8. Phase 4 — Deprecations + Codex provider + docs

**Goal**: All pre-ADR-033 AI surfaces deleted; Codex provider implemented; docs updated to point at the new system.

**Prerequisite**: Phase 3 complete; T-ECA-318 audit passed.

### T-ECA-401 — Deprecation scaffold (scaffold)

**Agent role**: SCAFFOLD AGENT for Phase 4.
**Owned files** (delete):

- `src/scieasy/ai/generation/` (entire directory).
- `src/scieasy/ai/synthesis/` (entire directory).
- `src/scieasy/ai/optimization/` (entire directory).
- `src/scieasy/ai/config.py`.
- The three legacy route handlers in `src/scieasy/api/routes/ai.py` (`generate-block`, `suggest-workflow`, `optimize-params`).
- Their associated Pydantic schemas in `src/scieasy/api/schemas.py`.
- `tests/ai/test_block_generator.py`, `test_type_generator.py`, `test_workflow_planner.py` (if still present).

**Plus** narrow exception per ADR-033 §3 D9 for AIBlock:

- KEEP `src/scieasy/blocks/ai/providers.py` and `src/scieasy/blocks/ai/ai_block.py` unchanged.
- KEEP `tests/blocks/test_ai_block.py`.

**Acceptance criteria**:

- `git grep -rE 'SCIEASY_AI_(PROVIDER|API_KEY|MODEL)' src/` returns no matches.
- `pyproject.toml` `[project.optional-dependencies].ai` is unchanged (AIBlock still uses `anthropic` / `openai` SDKs in its own scope).
- All deleted files have no remaining references (`grep` confirms).
- `pytest` still passes (deleted tests should be accompanied by their fixtures and any orphan imports cleaned up).

**Dependencies**: T-ECA-318.

### T-ECA-402 — Codex provider (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-403 docs).
**Owned files**: `src/scieasy/ai/agent/codex.py`, `tests/ai/test_codex_provider.py`, `tests/fixtures/stub_codex.py`.

**Implementation requirements**:

- `CodexProvider(AgentProvider)` mirrors `ClaudeCodeProvider`. Differences:
  - Different binary name (`codex`).
  - Different spawn flags (Codex CLI specifics — TBD via T-ECA-403 spike).
  - Different stream format normalisation in `_normalize_event`.
- All canonical event kinds produced by `ClaudeCodeProvider` must also be produced by `CodexProvider`.

**Tests**: same shape as `test_claude_code.py`, using a stub_codex.py.

**Acceptance criteria**:

- `GET /api/ai/status` returns both providers when both binaries are installed.
- A frontend "Provider" dropdown switches between them (already wired in T-ECA-303).

**Dependencies**: T-ECA-401, plus a spike (T-ECA-403) on Codex stream format if needed.

### T-ECA-403 — Codex stream-format spike + docs (impl)

**Agent role**: IMPLEMENTATION AGENT (parallel with T-ECA-402 once the spike is done).
**Owned files**: `docs/specs/eca-spike-codex-format.md`, `docs/guides/ai-chat.md`, `README.md`, `docs/roadmap/ROADMAP.md`, `docs/adr/ADR.md`.

**Spike requirements**:

- Run a Codex session, observe the stream format, document event-kind mapping to canonical events.
- Write the addendum if non-trivial divergence is found.

**Doc requirements**:

- `docs/guides/ai-chat.md` new: install, login, basic usage, permission policy, customising system prompt, troubleshooting. ~500 lines.
- `README.md` AI section rewritten to describe the agent.
- `docs/roadmap/ROADMAP.md` Phase 9 retitled "Embedded Coding Agent" and updated.
- `docs/adr/ADR.md` index gets an entry for ADR-033 (formal acceptance).

**Acceptance criteria**:

- Guide is verifiable: a new user can follow it from a clean install to a first successful chat.
- All cross-doc references resolve.

**Dependencies**: T-ECA-401.

### T-ECA-410 — Phase-4 audit pass

**Agent role**: AUDIT AGENT for Phase 4.

**Audit checklist**:

- [ ] All deletions in T-ECA-401 confirmed.
- [ ] Codex provider parity with Claude Code provider (same canonical events; same permission gating).
- [ ] Guide is readable by a non-developer scientist (test by re-reading without prior context).
- [ ] CI green across all checks.
- [ ] `CHANGELOG.md` `[Unreleased] > Removed` lists every deleted env var, endpoint, and module.
- [ ] AIBlock still imports and tests still pass.

**Dependencies**: T-ECA-401..403.

---

## 9. Agent dispatch protocol

For each phase the dispatching process is:

1. **Read this spec and the matching phase section.**
2. **Dispatch the scaffold agent.** (1 agent.) Owns the scaffold ticket. Sequential.
3. **Once scaffold PR is merged**, dispatch up to **2 implementation agents in parallel**. Each owns one or more tickets in the phase that are non-overlapping in `Owned files`. The phase ticket table identifies parallel-safe groups.
4. **Once all implementation PRs are merged**, dispatch the **audit agent**. (1 agent.) The audit agent reviews each implementation PR via GitHub comments OR opens follow-up PRs for blockers.
5. **Once audit clears**, the phase is complete. Proceed to the next phase's scaffold agent.

Total agents per phase: **3** (1 scaffold + 2 implementation OR 1 scaffold + 1 implementation + 1 audit, depending on phase size).

**Parallel-safe groups per phase**:

- Phase 1: { T-ECA-102, T-ECA-103, T-ECA-108 } can run in parallel after scaffold. { T-ECA-104 } depends on 102+103. { T-ECA-105 } depends on 104. { T-ECA-106 } depends on 104. { T-ECA-107 } depends on 106. { T-ECA-109 } depends on 107+108. { T-ECA-110 } depends on 105+107.
- Phase 2: { T-ECA-202, T-ECA-203, T-ECA-204 } run in parallel after scaffold. { T-ECA-205 } depends on all three.
- Phase 3: { T-ECA-302, T-ECA-303 } run in parallel after scaffold.
- Phase 4: { T-ECA-402, T-ECA-403 } run in parallel after scaffold (with the spike inside T-ECA-403 done first).

**Within-phase deadlock recovery**: if an implementation agent reports unresolvable blocking, the human reviewer is paged via a GitHub issue tagged `agent-stuck`.

---

## 10. Inter-phase dependency graph

```
            Phase 1 (T-ECA-101..119)
                    │
                    ▼  (T-ECA-119 audit pass)
            Phase 2 (T-ECA-201..225)
                    │
                    ▼  (T-ECA-225 audit pass)
            Phase 3 (T-ECA-301..318)
                    │
                    ▼  (T-ECA-318 audit pass)
            Phase 4 (T-ECA-401..410)
```

No phase may begin its scaffold ticket until the prior phase's audit ticket is closed. Implementation tickets within a phase may overlap as documented in §9.

---

## 11. Test plan

### 11.1 Unit tests

Every ticket includes its own unit tests as specified in the ticket's `Tests` field. Coverage gate: ≥ 85% on the new modules, project-wide gate unchanged.

### 11.2 Integration tests

- `tests/integration/test_phase1_end_to_end.py` (T-ECA-109): stub_claude → WS chat round trip.
- `tests/integration/test_phase2_mcp_end_to_end.py` (T-ECA-205): stub_claude → MCP `list_blocks` → tool_result.
- `tests/integration/test_phase3_browser_e2e.py` (T-ECA-318): manual smoke test plan (no Playwright in this phase).
- `tests/integration/test_phase4_dual_provider.py` (T-ECA-410): both providers, status endpoint, switching.

### 11.3 Architecture tests

Extend:

- `tests/architecture/test_layer_deps.py` — `ai/agent/` does not import `engine/` directly; uses dependency injection.
- `tests/architecture/test_placement.py` — files live in their owned paths.
- `tests/architecture/test_registries.py` — MCP tool registry is exhaustive (all 25 tools).

### 11.4 End-to-end manual test plan (human-driven)

Located at `docs/testing/eca-manual-tests.md` (written in T-ECA-403). Covers:

- Install + first-run flow.
- Workflow design via chat.
- Block authoring via chat.
- Permission denial.
- Bypass mode.
- Session resume after browser refresh.
- Codex provider equivalent.

---

## 12. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| CC stream-json schema changes upstream | Medium | High | Defensive parser (OQ5). Pin tested CC version range in `docs/guides/ai-chat.md`. |
| Hook protocol doesn't behave as expected on Windows | Medium | High | T-ECA-105 spike runs before T-ECA-110. Fallback to allowlist if needed. |
| MCP tool latency makes the agent feel sluggish | Low | Medium | All read tools must respond in < 200 ms; benchmarked in audit phase 2. |
| User loses work due to a malicious / buggy agent edit | Low | High | Strict permission policy by default. AppBlock is not auto-approved. Bypass mode requires explicit opt-in per session. |
| The MCP server crashes and takes down FastAPI with it | Medium | Medium | MCP server runs as a separate asyncio task with its own exception boundary; failures log ERROR but don't propagate to FastAPI handlers. |
| Permission UI race where user's edit and agent's write conflict | Medium | Low | File-lock + 500ms canvas debounce (OQ7). Conflict surfaces as a chat error, not data loss. |
| Concurrent-chat cap is too low for power users | Low | Low | Configurable in `settings.json`. |
| Stub binaries diverge from real CC behaviour | Medium | Medium | Integration tests gated on real CC availability run nightly; surface divergences as failures. |

---

## 13. Out-of-spec follow-ups (for later)

- **AIBlock revisit ADR** — decide rewrite / keep / retire.
- **MCP marketplace** — let users install third-party MCP tools without code changes.
- **Skill marketplace** — same for Claude Code skills.
- **Multi-project awareness** — agent can switch between projects mid-chat.
- **Cloud CC support** — talk to `claude.ai` web API instead of local CLI.
- **Telemetry opt-in** — anonymized usage stats for upstream feedback.

These are recognised but explicitly out of scope for this implementation cascade.

---

## Appendix A: Ticket index

| Ticket | Phase | Role | Owned area |
|--------|-------|------|-----------|
| T-ECA-101 | 1 | scaffold | module skeleton |
| T-ECA-102 | 1 | impl | binary discovery |
| T-ECA-103 | 1 | impl | stream-json parser |
| T-ECA-104 | 1 | impl | ClaudeCodeProvider + subprocess |
| T-ECA-105 | 1 | impl (spike) | hook protocol verification |
| T-ECA-106 | 1 | impl | SessionManager + transcript |
| T-ECA-107 | 1 | impl | WS chat + status routes |
| T-ECA-108 | 1 | impl | MCP + hook config emission |
| T-ECA-109 | 1 | impl | demo + integration |
| T-ECA-110 | 1 | impl | permission backend + bridge |
| T-ECA-119 | 1 | audit | Phase 1 audit |
| T-ECA-201 | 2 | scaffold | MCP server skeleton |
| T-ECA-202 | 2 | impl | workflow tools |
| T-ECA-203 | 2 | impl | authoring + inspection tools |
| T-ECA-204 | 2 | impl | Q&A tools + system prompt |
| T-ECA-205 | 2 | impl | MCP wiring |
| T-ECA-225 | 2 | audit | Phase 2 audit |
| T-ECA-301 | 3 | scaffold | frontend skeleton + old deletion |
| T-ECA-302 | 3 | impl | WS protocol finalize |
| T-ECA-303 | 3 | impl | AIChat UI + permission UI |
| T-ECA-318 | 3 | audit | Phase 3 audit |
| T-ECA-401 | 4 | scaffold | deprecation deletes |
| T-ECA-402 | 4 | impl | Codex provider |
| T-ECA-403 | 4 | impl | docs + spike |
| T-ECA-410 | 4 | audit | Phase 4 audit |
