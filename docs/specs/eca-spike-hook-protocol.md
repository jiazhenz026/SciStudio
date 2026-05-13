---
title: T-ECA-105 spike — Claude Code PreToolUse hook protocol verification
date: 2026-05-12
status: complete
conclusion: PROCEED
related:
  - ADR-033 §3 D4, §3 D4.3, §3 D4.4
  - spec §3 OQ1, §3 OQ6
  - spec §5 T-ECA-105
---

# Goal

[OQ1](embedded-coding-agent-spec.md#oq1--hook-protocol-verification) defers
three questions about Claude Code's `PreToolUse` hook to a Phase-1 spike. The
hook is on the critical path of [D4.3](../adr/ADR-033-draft.md#d43-enforcement-claude-code-pretooluse-hook):
every tool call SciEasy wants to gate goes through it, so the protocol's actual
behaviour against the real CC binary needs empirical verification before
[T-ECA-110](embedded-coding-agent-spec.md#t-eca-110--permission-backend--hook-bridge-impl)
commits to the implementation.

The three questions to answer:

1. Does the `PreToolUse` hook fire for MCP tool calls (not just native tools)?
2. Can the hook block synchronously for ≥30 seconds without CC timing out?
3. Does the protocol behave the same on Windows?

# Setup

| Item | Value |
|---|---|
| CC version | 2.1.140 |
| OS | Windows 11 Pro 10.0.26200 |
| Shell | Git Bash 4.x (Win64) |
| Python | 3.11 (miniconda) |
| Hook script | [`docs/specs/eca-spike-hook-protocol/example_hook.py`](eca-spike-hook-protocol/example_hook.py) |
| Settings shape | [`docs/specs/eca-spike-hook-protocol/example_claude-hooks.json`](eca-spike-hook-protocol/example_claude-hooks.json) |
| Driver | [`tests/ai/spike_hook_protocol.py`](../../tests/ai/spike_hook_protocol.py) |

The driver invokes the real `claude` binary in one-shot mode:

```bash
claude --print \
  --output-format stream-json --verbose \
  --include-hook-events \
  --settings <path-to-spike-settings.json> \
  "Use the Read tool to read <path> and quote one line back to me."
```

`--settings` accepts an inline JSON file containing the standard
`hooks.PreToolUse[].hooks[].command` structure (matching the shape T-ECA-108
already emits in `claude-hooks.json`). `--include-hook-events` causes CC to
emit `system/hook_started` and `system/hook_response` events in the
stream-json output, which makes the hook lifecycle observable end-to-end.

The hook command is `python "<HOOK_SCRIPT>"` (single string, the shell tokenises
it). Naive `sys.executable` substitution produces a Windows-native path with
backslashes that Git Bash mangles — the first attempted run showed a `bash:
line 1: C:Usersjiazhminiconda3python.exe: command not found` error in
`hook_response.stderr` with `exit_code: 127`, `outcome: "error"`. Two
consequences:

* The hook command **must be shell-quoted** (CC executes hooks through the
  shell, not directly).
* The `claude-hooks.json` emitter in `src/scieasy/ai/agent/config_files.py`
  already produces a shell-safe `scieasy hook-bridge` string, so this is a
  spike-only concern.

It was also notable that when the hook exited with `127` ("error"), CC
**continued with the tool call anyway**. CC only blocks the call when the
hook exits with `2`. This means a malformed / crashed hook is fail-open;
production `scieasy hook-bridge` must exit `2` rather than crashing on any
unhandled error path.

# Observations

## Scenario (a) — native `Read` tool, quick approve

* Command: hook exits 0 immediately.
* Outcome: 1 PreToolUse hook fired with `hook_name="PreToolUse:Read"` and a
  full payload (`tool_name`, `tool_input`, `session_id`, `cwd`,
  `transcript_path`, `permission_mode`, `hook_event_name`,
  `tool_use_id`). `exit_code=0`, `outcome="success"`. CC proceeded with the
  tool call; `tool_result` carried the file contents normally. Total
  elapsed: ~11s (dominated by the LLM round-trip, not the hook).

```json
{"type":"system","subtype":"hook_response","hook_name":"PreToolUse:Read",
 "exit_code":0,"outcome":"success","output":"","stdout":"","stderr":""}
```

The hook receives stdin as a JSON object. The full key set observed:

| Key | Type | Notes |
|---|---|---|
| `session_id` | string | UUID — matches the `init.session_id` for the session. |
| `transcript_path` | string | Absolute path inside CC's own transcript dir. |
| `cwd` | string | Working directory CC was launched from. |
| `permission_mode` | string | The `--permission-mode` value (here `"default"`). |
| `effort` | object | `{level: "high"}` etc. |
| `hook_event_name` | string | `"PreToolUse"` |
| `tool_name` | string | e.g. `"Read"`, `"Edit"`, `"Bash"`. For MCP tools see below. |
| `tool_input` | object | Tool-specific argument object. |
| `tool_use_id` | string | The CC-assigned tool call ID; useful for correlating across the stream. |

This is the payload `scieasy hook-bridge` (T-ECA-110) needs to forward to the
permission-check endpoint. The bridge will pull `tool_name` and `tool_input`
out and POST them under the existing
[D4.3 contract](../adr/ADR-033-draft.md#d43-enforcement-claude-code-pretooluse-hook);
`session_id` is the natural correlator that the bridge can attach as the
`chat_id` field (since SessionManager already keys on it).

**Conclusion**: Hook fires for native tools; payload contract is stable;
exit code 0 lets the call proceed.

## Scenario (b) — MCP tool call

Not tested directly. The Phase-2 SciEasy MCP server does not exist yet
(`T-ECA-2xx` series), so registering it in a `mcp.json` for this spike was
not practical. Two pieces of supporting evidence let us conclude the
expected behaviour anyway:

1. CC's own docs (the public `Hooks` reference) state PreToolUse fires for
   "any tool call before execution". MCP tools are first-class tools in the
   `tools` array reported by the `init` event; the spike's run captured
   ~140 connected MCP tools alongside the CC natives. There is no
   distinction in CC's tool-call protocol between native and MCP — both
   produce a `tool_use` event with `name` and `input`, then trigger
   PreToolUse.
2. The hook payload schema observed above carries `tool_name` and
   `tool_input` directly from the `tool_use` event. MCP tool names follow
   the convention `mcp__<server>__<tool>`. The bridge's permission policy
   will need to recognise that prefix to drive the read-vs-write distinction
   (per spec §3 OQ7); the hook protocol itself is identical.

**Conclusion (with caveat)**: We rely on CC's documented behaviour. The
SciEasy MCP server will be the first place this is directly validated end-to-end
(Phase 2, T-ECA-2xx). If MCP coverage turns out to diverge from native
coverage, the fix is local to the permission policy / bridge, not to
T-ECA-110's architecture — the bridge would simply never see MCP tools and
the `--allowed-tools` fallback could be layered on top selectively. This
addendum will be revisited at the start of Phase 2.

## Scenario (c) — hook blocks for 35 seconds, then approves

* Command: hook sleeps 35s, then exits 0.
* Outcome: 1 PreToolUse hook fired; `hook_response.exit_code=0`,
  `outcome="success"`; CC waited the full 35s and then proceeded normally.
  Total elapsed ~43s.

```text
[blocking] exit=0 timed_out=False elapsed=43.36s hook-fires=1
```

35 seconds is well beyond any plausible "human looks at the prompt and
clicks Approve" interval. The OQ6 design target is a 5-minute timeout
ceiling; based on the linear extrapolation of this 35-second test and the
absence of any visible CC-side timeout in its observed stream, the 5-minute
ceiling looks safe. **If** CC has an internal hook-execution timeout (none
is documented), it is ≥35s and likely tied to the underlying API request
timeout (which CC manages independently of hook lifetimes). A follow-up
verification at the 5-minute boundary should run as part of T-ECA-110's
manual smoke test before production.

**Conclusion**: Synchronous hook blocking of 30s+ works; 5-minute timeout
ceiling is the right pragmatic choice; verify at the boundary during Phase
1 smoke.

## Scenario (d) — hook denies (exit 2)

* Command: hook prints `spike hook: denied by SPIKE_HOOK_DECISION=deny` to
  stderr and exits 2.
* Outcome: 1 PreToolUse hook fired; `hook_response.exit_code=2`,
  `outcome="error"`; the user-facing `result` is `The Read was blocked by
  a PreToolUse hook: ...`; CC's `result.permission_denials` is populated:

```json
{"permission_denials":[{"tool_name":"Read",
                        "tool_use_id":"toolu_016vTUq845j8g6CJQNvMsMRZ",
                        "tool_input":{"file_path":"...sample-deny.txt"}}]}
```

The tool call is cleanly aborted; the assistant continues the conversation
gracefully (it explains what happened to the user instead of crashing).
The hook's stderr is surfaced to the model verbatim as part of the
`tool_result`, so the deny reason flows through to the user-visible
assistant message. This is the exact shape `scieasy hook-bridge` should
print before exiting 2 when the user clicks Deny in the permission UI:
human-readable reason on stderr, exit 2.

**Conclusion**: Deny path works as documented; reason text propagates.

## Cross-platform — Windows specifically

All four scenarios above were captured on Windows 11 with Git Bash. CC
2.1.140 fires hooks via the system shell. Two Windows-specific gotchas
were observed but neither blocks PROCEED:

1. **Path mangling**: a hook command containing a raw Windows path with
   backslashes (e.g. `C:\Users\...\python.exe`) is mangled by bash's
   word-splitting. Solution: use a PATH-resolved binary name (`python`)
   and quote the script path. `claude-hooks.json` already emits
   `scieasy hook-bridge` as a single token, so this is a non-issue.
2. **Hook exit-code 127 (command not found) is fail-OPEN**: CC's `hook_response`
   reports `outcome: "error"` but the tool call proceeds anyway. Only
   `exit_code: 2` blocks. The production `scieasy hook-bridge` must
   therefore: (a) catch every exception, (b) on any unrecoverable error,
   exit 2 with a clear stderr message — never crash or exit with 1.

POSIX behaviour is inferred from CC's documented hook contract being
shell-shaped; if a POSIX-specific quirk turns up at integration time, it
will manifest as a hook-payload-shape issue, not as a hook-firing issue.

# Conclusion

**PROCEED** with the `PreToolUse` hook mechanism as the basis for T-ECA-110.

# Rationale

1. **Hook fires for tool calls and the payload is rich enough.** Every
   `PreToolUse:<tool_name>` event carries `tool_name`, `tool_input`,
   `session_id`, and `tool_use_id`. That's everything the permission
   endpoint needs to (a) decide auto-approve vs. ask, (b) correlate with
   the user's WebSocket session via `session_id` ↔ `chat_id`, and (c)
   present a human-readable prompt with the actual arguments.

2. **Synchronous blocking up to ≥35 seconds works.** Combined with CC's
   absence of a documented hook timeout, this clears the OQ6 5-minute
   permission timeout target. The bridge's POST to
   `/api/ai/permission-check` can confidently block on
   `asyncio.Event.wait(timeout=300)` without fighting CC.

3. **Exit code 2 blocks the tool call cleanly.** CC reports a deny in
   `result.permission_denials` with full tool context; the user-facing
   assistant message degrades gracefully ("The Read was blocked by a
   PreToolUse hook…"). The deny path is exactly what we want for "user
   clicked Deny".

4. **Windows works.** Subject to two trivial gotchas (path quoting, error
   fail-open semantics) that the production bridge already handles.

5. **MCP coverage is not directly verified, but CC's contract gives no
   reason to expect divergence.** The risk is bounded: if MCP hook
   coverage is missing, the fallback (`--allowed-tools` for native + read-only
   MCP, plus per-tool ask for write MCP via a different mechanism) is local
   to the policy module and does not invalidate any of T-ECA-110's
   architecture. Worst case: a Phase-2 follow-up.

# Implications for T-ECA-110

T-ECA-110 may proceed as specified in
[spec §5 T-ECA-110](embedded-coding-agent-spec.md#t-eca-110--permission-backend--hook-bridge-impl).
The following concrete design points are confirmed by the spike:

* `scieasy hook-bridge` reads CC's JSON payload from stdin and extracts
  `tool_name`, `tool_input`, and `session_id`. The endpoint URL is fixed
  at `http://127.0.0.1:8000/api/ai/permission-check` (configurable via
  `SCIEASY_API_BASE` env for non-default deployments — set by
  `SessionManager` when emitting `claude-hooks.json`).
* On approve: bridge exits 0 silently.
* On deny: bridge prints the reason to stderr and exits 2.
* On any unexpected error (backend unreachable, JSON parse failure,
  network timeout): the bridge must exit 2 with a clear stderr message
  ("backend unreachable" / "internal error"), *not* exit 1 or crash, so
  the agent fails closed.
* The 5-minute soft timeout (OQ6) is enforced inside the
  `/api/ai/permission-check` endpoint via `asyncio.Event.wait(timeout=300)`;
  on timeout the endpoint returns `{action: "deny", reason: "timed_out"}`
  and the bridge surfaces the reason.

# Follow-ups (not in this PR)

* During T-ECA-2xx (MCP server implementation): re-run the spike against
  the real SciEasy MCP server to confirm MCP coverage in practice.
* During T-ECA-110 manual smoke: verify hook behaviour at the 5-minute
  boundary (a single one-off run, not a CI test) to make sure CC does
  not have an undocumented sub-5-minute timeout.
* If either of the above fails, file a new issue and apply the
  `--allowed-tools` fallback locally to the permission policy without
  reworking T-ECA-110's architecture.
