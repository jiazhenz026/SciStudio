# Spike: Codex CLI stream format

> **Status**: spike / assumption-led
> **Ticket**: T-ECA-403
> **Related**: ADR-033 §3 D1, `docs/specs/embedded-coding-agent-spec.md` §8 T-ECA-402
> **Author**: implementation agent for #747
> **Date**: 2026-05-12

---

## 1. Purpose

This document captures what we know — and explicitly what we assume — about the
upstream `codex` CLI's stream-JSON output format, so that the implementation in
`src/scieasy/ai/agent/codex.py` (T-ECA-402) can be reasoned about and audited
against a single source of truth.

The spike is **not** an experimental report. It is a contract for the Codex
provider that says: "Given these assumptions about how the Codex CLI behaves,
the provider will produce the canonical event taxonomy listed below; if any
assumption is observed to be false in production, file a follow-up ticket and
update this document."

## 2. Empirical status

**The Codex CLI was not run during this spike.** The implementation host
(Windows 11, ADR-033 Phase 4 worktree) has the Claude Code CLI installed but
not the Codex CLI. Two consequences follow:

1. The provider's discovery, spawn flags, login probe, and stream-format
   normalisation are written against the assumptions enumerated in §3
   below.
2. The test fixture (`tests/fixtures/stub_codex.py`) is hand-written to
   exercise the canonical event taxonomy via the SciEasy stream-JSON parser
   directly, without simulating Codex CLI quirks that we cannot verify.

This is consistent with ADR-033 §3 D1.3 which permits provider implementations
to be authored against documented assumptions and refined via follow-up
tickets once the upstream CLI is observed in situ.

## 3. Assumptions

### A1 — Subprocess invocation surface

The Codex CLI:

1. Reads user-turn messages from stdin one JSON envelope per line.
2. Writes a stream of JSON events to stdout, one event per line (NDJSON).
3. Exits cleanly when stdin is closed.
4. Accepts the following flags, with the listed semantics:
   - `--output-format stream-json` — enable NDJSON streaming.
   - `--append-system-prompt @<path>` — append the contents of `<path>` to
     the system prompt.
   - `--mcp-config @<path>` — load MCP server config from `<path>`.
   - `--resume <session_id>` — resume a prior session.
   - `--model <name>` — override the model.

**Where Codex flag spellings differ**, the SciEasy provider's `start_session`
will need a small adapter. We assume — pending observation — that the flag
spellings above are either accepted directly or trivially aliased.

### A2 — Login subcommand

The Codex CLI exposes `codex login status` and returns exit code 0 if a
session token is present. If that subcommand is absent on the installed
version, the discovery probe returns non-zero and the provider correctly
degrades to `logged_in=False` — see
`test_discover_treats_login_probe_nonzero_as_logged_out`.

### A3 — Event framing

Each event is a JSON object with **either** a top-level `kind` field (the
ADR-033 canonical name) **or** a top-level `type` field (the field Claude
Code currently uses). The SciEasy stream-JSON parser
(`scieasy.ai.agent.stream_json._extract_kind`) accepts both, so a Codex CLI
that emits either spelling will be normalised correctly.

### A4 — Event kinds

The Codex CLI emits — or can be normalised onto — the following canonical
event kinds:

| Canonical kind | Required fields | Notes |
|---|---|---|
| `init` | `session_id` (str); optional `model`, `schema_version` | First event in every session. |
| `assistant_text_delta` | `delta` (str) or `text` (str) | Multiple deltas per turn. |
| `tool_use` | `tool_name`/`name`, `tool_input`/`input`, `tool_use_id`/`id` | Both spellings accepted by the parser. |
| `tool_result` | `tool_use_id`, `output`/`content`, optional `is_error` | Correlated with the matching `tool_use`. |
| `permission_request` | `tool_name`, `tool_input`, `request_id` | Synthesised by the hook bridge, not the raw CLI. |
| `error` | `message` or `error` | Stream-level provider error. |
| `done` | none | Terminal event marking end of turn. |
| `other` | n/a | Catch-all for unknown kinds (spec §3 OQ5). |

The provider does **not** itself translate Codex-specific event names. The
parser's dispatch table is the single point of canonicalisation. If Codex
emits a kind that is not in the table above (e.g. `usage`, `tokens`,
`metadata`), it will surface as an `OtherEvent` with the original payload
preserved in `event.raw`, as required by ADR-033 §3 OQ5.

### A5 — Permission requests

Per ADR-033 §3 D5, permission gating is implemented through the
`PreToolUse` hook **and not** through inline stream events. The Codex
provider is therefore not responsible for emitting `permission_request`
events directly — those are synthesised by the hook bridge identically to
the Claude Code case. The provider's responsibility ends at injecting
`SCIEASY_CHAT_ID` and `SCIEASY_PROJECT_DIR` into the subprocess env so the
hook bridge can route the request back to `/api/ai/permission-check`
(issue #723).

## 4. Divergence handling

If a divergence between an assumption above and the real Codex CLI is
observed:

1. Open a follow-up ticket labelled `eca-codex-spike`.
2. Patch the assumption in this file with the observed behaviour.
3. If the divergence requires provider-specific normalisation logic (e.g.
   the Codex CLI uses a Codex-only event kind that does not map to any
   canonical kind in §3-A4), add a `_normalize_event` method to
   `CodexProvider` and route the relevant kinds through it before the
   canonical parser. Until then, an `OtherEvent` is acceptable.
4. Re-run `tests/ai/test_codex_provider.py` and confirm the canonical
   taxonomy is still produced end-to-end.

## 5. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Codex flag spellings differ from CC's | Medium | Spawn fails immediately; user sees install-hint banner. | Add Codex-specific flag aliases in `start_session` once observed. |
| Codex emits stream events without `kind` or `type` field | Low | Events surface as `OtherEvent` with INFO log. | Acceptable for v1; tighten the parser only if real Codex output requires it. |
| `codex login status` subcommand does not exist | Medium | Login probe returns non-zero; user sees "not logged in" banner. | Already handled — see `test_discover_treats_login_probe_nonzero_as_logged_out`. |
| Codex CLI's session-resume semantics differ from CC | Medium | `--resume <id>` rejected; provider falls back to a fresh session. | Acceptable for v1; refine once observed. |

## 6. Open questions for follow-up tickets

1. **Does Codex's CLI accept `--append-system-prompt @<path>`** or is the
   prompt-injection mechanism different (e.g. an env var, a config file)?
2. **Does Codex emit a `permission_request` event natively** or — like
   Claude Code — does it always go through a hook subprocess?
3. **Does Codex have a hook surface comparable to Claude Code's
   `PreToolUse`?** If not, the Codex provider may need a different
   permission-gating strategy (e.g. wrapping every tool call in an MCP
   middleware tool).
4. **What is the Codex CLI's exit semantics on `Ctrl-C` / `SIGTERM`?**
   We currently assume identical behaviour to Claude Code; if Codex
   propagates differently, the cancellation tree-kill path may need
   adjusting on POSIX.

These questions are recorded here so that whoever first runs Codex against
SciEasy can answer them by observation and close them out via doc patches.
