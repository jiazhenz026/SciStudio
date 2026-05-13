# Codex Provider Gap Analysis and Implementation Plan

Date: 2026-05-13
Owner context: ADR-033 embedded coding agent

## Summary

Claude Code is wired to SciEasy's current agent runtime and can start real chat
sessions. Codex is not functionally integrated yet, even though the repo
contains a `CodexProvider` scaffold and the frontend exposes a provider picker.

There are two independent blockers:

1. The frontend/backend session start path never selects Codex at all.
2. The current `CodexProvider` is built around Claude-style assumptions that do
   not match the real `codex` CLI.

Because of (2), simply wiring the provider selector would still not make Codex
work.

## Evidence

### 1. Provider selection is not wired

- Frontend settings expose a `codex` option, but that state is only stored
  locally and never sent over the WebSocket:
  - `frontend/src/components/AIChat/SettingsPanel.tsx`
  - `frontend/src/hooks/useAgentWebSocket.ts`
- The chat WebSocket message schema does not carry provider/model/permission
  fields:
  - `src/scieasy/api/schemas.py`
- Backend session creation always instantiates `ClaudeCodeProvider()` and always
  starts in bypass mode:
  - `src/scieasy/api/routes/ai.py`

### 2. The current Codex provider assumes a Claude-like CLI contract

Current `CodexProvider` assumes:

- one long-lived subprocess per chat session
- stdin accepts JSON chat envelopes
- stdout emits Claude-style `stream-json`
- spawn flags include:
  - `--output-format stream-json`
  - `--append-system-prompt @<path>`
  - `--mcp-config @<path>`
  - `--resume <session_id>`

Those assumptions are encoded in:

- `src/scieasy/ai/agent/codex.py`
- `tests/fixtures/stub_codex.py`
- `tests/ai/test_codex_provider.py`
- `docs/specs/eca-spike-codex-format.md`

### 3. Real Codex CLI behavior differs materially

Observed on this machine (`codex-cli 0.118.0`):

- `codex --help` shows the non-interactive path is `codex exec`, not bare
  `codex --output-format ...`
- `codex exec --help` exposes `--json`, not `--output-format stream-json`
- `codex exec` does not accept `-a/--ask-for-approval`
- `codex login status` exists and returns `Logged in using ChatGPT`
- `codex exec --json "Reply with exactly hi and nothing else."` emits JSONL
  events like:
  - `thread.started`
  - `turn.started`
  - `item.completed`
  - `turn.completed`
- `codex exec --json ... resume <thread_id> -` resumes successfully, which means
  Codex supports session continuity, but via new-process-per-turn resume rather
  than a Claude-style long-lived stdin session

## Root-cause analysis

### Blocker A: control-plane gap

SciEasy's chat startup flow is still effectively hard-coded for Claude Code.
The provider dropdown is UI-only.

Impact:

- selecting `Codex` in the UI has no effect
- permission mode in the UI also does not control backend session startup

### Blocker B: provider contract mismatch

`AgentSession` and `CodexSession` are currently shaped around Claude's
"persistent subprocess + repeated `send_user_message()` over stdin" model.

Real Codex appears to fit a different model:

- one process per turn (`codex exec --json`)
- session continuity through `exec resume <thread_id>`
- different event taxonomy
- likely different MCP/config injection surface
- no Claude-style hook contract exposed in current local help

Impact:

- the current `CodexProvider.start_session()` argv is invalid for real Codex
- even if spawn succeeded, `stream_json.parse_stream()` would classify real
  Codex events as mostly `OtherEvent`
- current tests give false confidence because the stub reproduces the same wrong
  assumptions

### Blocker C: docs and tests are assumption-locked

The current spike doc and tests document/verify the scaffolded assumption set,
not the real CLI behavior.

Impact:

- green tests do not imply real Codex compatibility
- user-facing guide currently overstates support

## Implementation plan

### Phase 1: wire provider selection end-to-end

Goal: make the chosen provider explicit in the protocol and session metadata.

Changes:

- extend `ChatClientMessage` with:
  - `provider`
  - `permission_mode`
  - optional `model`
- update `useAgentWebSocket` to include those fields on first `user_message`
- change `_start_default_session()` into a provider-aware factory
- stop hard-coding `ClaudeCodeProvider()` and `PermissionMode.BYPASS`
- persist the selected provider and permission mode in session metadata

Acceptance:

- selecting `codex` reaches the backend factory
- selecting strict/bypass affects session startup
- backend tests cover both providers at the session-factory boundary

### Phase 2: redesign Codex runtime integration around exec/resume

Goal: implement a real Codex provider instead of a Claude-shaped shim.

Recommended design:

- keep the public `AgentProvider` interface if possible
- change `CodexSession` internals to "spawn per turn"
- on first turn:
  - run `codex exec --json ...`
  - capture `thread_id` from `thread.started`
- on later turns:
  - run `codex exec --json ... resume <thread_id> -`
- `send_user_message()` should enqueue the next prompt text, then spawn a fresh
  subprocess for that turn
- `stream_events()` should stream events from the active turn subprocess only

Open design choice:

- either generalize `AgentSession` docs to support per-turn subprocesses, or
- keep the protocol and let Codex satisfy it via an internal turn-runner state

Acceptance:

- first-turn + resumed-turn smoke tests pass against a real local Codex binary
- metadata stores the real Codex `thread_id`

### Phase 3: add Codex event normalization

Goal: translate real Codex JSONL into SciEasy's canonical chat event taxonomy.

Changes:

- add Codex-specific event normalization before canonical event construction
- map at minimum:
  - `thread.started` -> `InitEvent`
  - `item.completed(agent_message)` -> `AssistantTextDeltaEvent` or final
    assistant message event(s)
  - tool-related item events -> `ToolUseEvent` / `ToolResultEvent` where
    present
  - `turn.completed` -> `DoneEvent`
- keep unknown Codex frames as `OtherEvent`

Acceptance:

- simple prompt renders correctly in SciEasy chat
- resumed prompt renders correctly
- parser tests use captured real Codex fixtures instead of the current
  Claude-style stub stream

### Phase 4: solve MCP injection for Codex

Goal: make SciEasy MCP tools visible to Codex without mutating global user state.

Tasks:

- determine the supported per-invocation MCP config surface for Codex
- prefer ephemeral config override over `codex mcp add` global mutation
- if needed, generate a temporary Codex config TOML and launch with `-c` /
  profile overrides
- pass `SCIEASY_CHAT_ID` and `SCIEASY_PROJECT_DIR` through the MCP server
  launch env

Acceptance:

- Codex can call a read-only SciEasy MCP tool such as `list_blocks`
- no persistent mutation of the user's global Codex MCP config is required

### Phase 5: permission-model strategy for Codex

Goal: replace the Claude-specific permission assumption with a Codex-compatible
strategy.

Tasks:

- verify whether Codex exposes a pre-tool hook comparable to Claude's
  `PreToolUse`
- if yes, integrate through the existing permission-check backend
- if no, define fallback behavior explicitly:
  - use Codex sandbox/approval flags where available
  - keep SciEasy write-side MCP tools gated server-side
  - document reduced parity for native file/shell tools if unavoidable

Acceptance:

- strict mode has a defined enforcement path for Codex
- bypass mode has a defined low-friction path for Codex
- limitations are documented if Codex cannot match Claude hook parity

### Phase 6: replace fake-confidence tests with real-contract tests

Goal: ensure CI distinguishes scaffold assumptions from actual upstream support.

Changes:

- split tests into:
  - pure unit tests for normalization helpers
  - real-binary smoke tests guarded by `skipif(find_binary("codex") is None)`
- replace `stub_codex.py` as the primary acceptance oracle
- add captured fixture files from real `codex exec --json` runs
- add an integration test for:
  - first turn
  - resumed turn
  - MCP tool call once MCP wiring lands

Acceptance:

- a green Codex test suite implies compatibility with the real CLI surface,
  not just the stub

### Phase 7: docs cleanup

Update:

- `docs/specs/eca-spike-codex-format.md`
- `docs/guides/ai-chat.md`
- `README.md`
- ADR-033 addendum if the provider model diverges from the original assumption

Must document:

- actual command surface (`exec`, `exec resume`, `--json`)
- actual login-status behavior
- any permission-model caveats
- whether Codex has full parity or partial parity with Claude Code

## Recommended PR breakdown

1. Provider selection plumbing
2. Codex session/runtime redesign
3. Codex event normalization + fixture-based tests
4. Codex MCP integration
5. Codex permission handling
6. Docs and guide corrections

## Recommended immediate next step

Start with Phase 1 plus a minimal slice of Phase 2:

- wire provider selection through the WebSocket
- add a real `CodexSession` prototype that can run:
  - `codex exec --json`
  - `codex exec --json ... resume <thread_id> -`
- do not attempt MCP or strict permissions in the same PR

That creates a small but honest milestone: "Codex can chat in SciEasy using
real upstream commands," after which MCP and permission parity can be layered on
without keeping the current false-positive scaffold in place.
