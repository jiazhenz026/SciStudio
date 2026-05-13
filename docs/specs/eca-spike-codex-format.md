# Spike: Codex CLI stream format

> **Status**: observed and implemented
> **Ticket**: T-ECA-403
> **Related**: ADR-033 Section 3 D1, `docs/specs/embedded-coding-agent-spec.md` Section 8 T-ECA-402
> **Date**: 2026-05-13

## 1. Purpose

This document records the Codex CLI surface that SciEasy's `CodexProvider`
adapts into the ADR-033 canonical agent event taxonomy.

The important gap from the original scaffold is that Codex is not a
Claude-Code-shaped long-running stdin process. In non-interactive mode, Codex
runs one turn per process:

```bash
codex exec --json --skip-git-repo-check -C <project_dir> -
codex exec --json --skip-git-repo-check -C <project_dir> resume <thread_id> -
```

SciEasy therefore treats `CodexSession` as a logical chat session and spawns a
new Codex subprocess for each user turn.

## 2. Observed CLI Surface

Observed on a local Windows development host with `codex-cli 0.118.0`:

| Concern | Observed behavior | SciEasy implementation |
|---|---|---|
| Non-interactive run | `codex exec` | `CodexSession.send_user_message()` spawns `codex exec` |
| JSON stream | `--json` emits JSONL frames | `CodexSession.stream_events()` reads stdout line by line |
| Working directory | `-C <dir>` | Passed for every turn |
| Resume | `codex exec ... resume <thread_id> -` | `thread.started.thread_id` is latched as `session_id` and reused |
| Prompt input | `-` reads prompt from stdin | SciEasy writes system prompt plus user message, then closes stdin |
| Model override | `--model <name>` | Passed when the frontend/API provides `model` |
| Bypass mode | `--dangerously-bypass-approvals-and-sandbox` | Used for `PermissionMode.BYPASS` |
| Strict mode | No Claude-style approval flag | SciEasy uses `--sandbox read-only` as the safe default |
| Login probe | `codex login status` | Used by `CodexProvider.discover()` as a best-effort heuristic |

## 3. Event Normalisation

Codex emits provider-specific JSONL frames. SciEasy maps the observed frames to
the canonical event types used by the frontend and transcript writer:

| Codex frame | Canonical event |
|---|---|
| `{"type": "thread.started", "thread_id": "..."}` | `InitEvent(kind="init", session_id=thread_id)` |
| `{"type": "turn.started"}` | hidden `OtherEvent` |
| `{"type": "item.completed", "item": {"type": "agent_message", "text": "..."}}` | `AssistantTextDeltaEvent` |
| `{"type": "item.completed", "item": {"type": "function_call", ...}}` | `ToolUseEvent` |
| `{"type": "item.completed", "item": {"type": "function_call_output", ...}}` | `ToolResultEvent` |
| `{"type": "turn.completed"}` | `DoneEvent` |
| `{"type": "turn.failed"}` or `{"type": "error"}` | `ErrorEvent` |
| Anything else | `OtherEvent` with the raw payload preserved |

The normaliser lives in `src/scieasy/ai/agent/codex.py` rather than the shared
Claude stream parser because Codex's `item.completed` envelope requires
provider-specific extraction.

## 4. MCP Configuration

Codex does not use Claude Code's `--mcp-config @file` flag. SciEasy injects the
project-local MCP server with Codex config overrides:

```bash
-c mcp_servers.scieasy.command="scieasy"
-c mcp_servers.scieasy.args=["mcp-bridge"]
-c mcp_servers.scieasy.env={SCIEASY_CHAT_ID="...", SCIEASY_PROJECT_DIR="..."}
```

SciEasy also injects the same environment variables into the Codex subprocess
environment:

| Variable | Purpose |
|---|---|
| `SCIEASY_CHAT_ID` | Correlates MCP/hook requests with the active chat |
| `SCIEASY_PROJECT_DIR` | Gives tools the trusted project root |
| `SCIEASY_PERMISSION_MODE` | Exposes strict/bypass mode to child processes |

## 5. Permission Model

Claude Code strict mode is built around the `PreToolUse` hook. Codex does not
currently expose the same approval flag surface in `codex exec`, so SciEasy's
Codex strict mode is intentionally conservative:

1. Native Codex filesystem/tool access is limited with `--sandbox read-only`.
2. Bypass mode maps to Codex's explicit dangerous bypass flag.
3. SciEasy MCP tools still receive `SCIEASY_PERMISSION_MODE`; write-like MCP
   enforcement must stay in the SciEasy tool layer.

This is not exact behavioral parity with Claude Code's per-tool GUI approval.
It is the safest observed mapping for the current Codex CLI.

## 6. Tests

The primary regression tests are:

| Test | Purpose |
|---|---|
| `tests/ai/test_codex_provider.py` | Provider discovery, per-turn spawn, resume, cancellation, event taxonomy, env injection |
| `tests/fixtures/stub_codex.py` | Codex-shaped `exec --json` and `exec resume --json` JSONL fixture |
| `tests/api/test_ai_chat_route.py` | Provider selection and permission-mode forwarding |
| `frontend/src/components/AIChat/__tests__/useAgentWebSocket.test.ts` | Frontend sends selected provider and permission mode |

Run the backend tests with the current worktree's `src` first on `PYTHONPATH`
if another editable SciEasy checkout is installed:

```powershell
$env:PYTHONPATH='C:\path\to\SciEasy\src'
pytest tests/ai/test_codex_provider.py tests/api/test_ai_chat_route.py tests/api/test_ai_chat_ws_v2.py -q --no-cov
```

Run the frontend hook test from `frontend/`:

```bash
npm test -- --run src/components/AIChat/__tests__/useAgentWebSocket.test.ts
```

## 7. Open Follow-Ups

1. Verify the strict-mode MCP write path end-to-end against a real Codex CLI and
   confirm SciEasy tools deny or prompt consistently.
2. Capture a small real Codex JSONL transcript fixture when the upstream event
   schema stabilizes enough to commit a sanitized sample.
3. Revisit strict-mode behavior if Codex adds a native per-tool approval
   mechanism for `codex exec`.
