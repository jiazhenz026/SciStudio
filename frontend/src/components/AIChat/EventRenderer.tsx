/**
 * Renders a single canonical AgentEvent per ADR-033 §3 D5.1.
 *
 * Dispatches on the discriminated `kind` field. Unknown kinds fall back
 * to the `OtherEvent` branch (preserved verbatim from the raw payload).
 */

import type { AgentEvent, OtherEvent } from "../../types/agentEvents";
import { MetaEventRow, RawEventRow, TextLikeRow, ToolLikeRow } from "./genericRows";

export interface EventRendererProps {
  event: AgentEvent;
}

export function EventRenderer({ event }: EventRendererProps) {
  // Issue #775 — filter out backend-marked auxiliary events (system/hook_*,
  // user-turn echoes, rate-limit notices). They're noise in the chat view.
  const raw = event.raw as Record<string, unknown> | undefined;
  if (raw && raw._chat_hidden === true) {
    return null;
  }
  // Synthetic user_message events injected by AIChat.handleSend so the
  // user's own text shows up in the conversation feed.
  if ((event.kind as string) === "user_message") {
    const content = (raw as { content?: string } | undefined)?.content ?? "";
    return (
      <div
        data-testid="ev-user"
        className="self-end ml-auto max-w-[80%] whitespace-pre-wrap rounded bg-blue-100 px-2 py-1 text-right"
      >
        {content}
      </div>
    );
  }
  // Issue #775 — Phase 5 follow-up: backend now emits `thinking` OtherEvents
  // for claude's interleaved-thinking content blocks.
  //
  // Issue #782: also catch top-level wire frames where claude streams
  // `{"type":"thinking",...}` directly (these get routed by
  // stream_json._DISPATCH fallback to OtherEvent(kind="thinking")). And
  // do NOT hide empty-text thinking frames — show the animated indicator
  // regardless; signature-only frames are still meaningful "agent is
  // thinking" signals. The thinking text only expands a folded preview
  // when it actually has content.
  const rawType = (raw as { type?: string } | undefined)?.type;
  if ((event.kind as string) === "thinking" || rawType === "thinking") {
    const text =
      (raw as { thinking?: string; text?: string } | undefined)?.thinking ??
      (raw as { text?: string } | undefined)?.text ??
      "";
    return (
      <div
        data-testid="ev-thinking"
        className="flex items-center gap-2 rounded border border-purple-200 bg-purple-50 px-2 py-1 text-sm text-purple-700"
      >
        <span
          aria-hidden="true"
          data-testid="ev-thinking-spinner"
          className="thinking-spinner inline-block font-mono"
        >
          ✻
        </span>
        {text.trim() ? (
          <details className="flex-1">
            <summary className="cursor-pointer">Thinking…</summary>
            <pre className="mt-1 whitespace-pre-wrap text-xs text-purple-900">{text}</pre>
          </details>
        ) : (
          <span>Thinking…</span>
        )}
      </div>
    );
  }
  switch (event.kind) {
    case "init":
      return (
        <div data-testid="ev-init" className="text-xs italic text-gray-500">
          Session started ({event.model ?? "unknown model"})
        </div>
      );
    case "assistant_text_delta":
      // Defensive: backend may still emit empty deltas on edge-case
      // assistant frames. Skip rendering rather than show a blank bubble.
      if (!event.delta) return null;
      return (
        <div data-testid="ev-text" className="whitespace-pre-wrap rounded bg-gray-50 px-2 py-1">
          {event.delta}
        </div>
      );
    case "tool_use":
      return (
        <details
          data-testid="ev-tool-use"
          className="rounded border border-blue-200 bg-blue-50 px-2 py-1 text-sm"
        >
          <summary className="cursor-pointer font-mono">
            {event.tool_name}({Object.keys(event.tool_input).join(", ")})
          </summary>
          <pre className="mt-1 overflow-auto text-xs">
            {JSON.stringify(event.tool_input, null, 2)}
          </pre>
        </details>
      );
    case "tool_result":
      return (
        <details
          data-testid="ev-tool-result"
          className={`rounded border px-2 py-1 text-sm ${
            event.is_error ? "border-red-200 bg-red-50" : "border-green-200 bg-green-50"
          }`}
        >
          <summary className="cursor-pointer">
            {event.is_error ? "Tool error" : "Tool result"} (id={event.tool_use_id})
          </summary>
          <pre className="mt-1 overflow-auto text-xs">
            {typeof event.output === "string"
              ? event.output
              : JSON.stringify(event.output, null, 2)}
          </pre>
        </details>
      );
    case "permission_request":
      // The modal is rendered separately (PermissionPrompt). Show a small
      // inline marker so the user sees the conversation paused.
      return (
        <div data-testid="ev-perm" className="rounded bg-yellow-50 px-2 py-1 text-sm text-yellow-800">
          Awaiting permission for <span className="font-mono">{event.tool_name}</span> ...
        </div>
      );
    case "error":
      return (
        <div data-testid="ev-error" className="rounded bg-red-100 px-2 py-1 text-sm text-red-800">
          Error: {event.message}
        </div>
      );
    case "done":
      return (
        <div data-testid="ev-done" className="text-xs text-gray-400">
          Turn complete.
        </div>
      );
    case "other":
    default: {
      // Issue #788: dispatch on the backend-classified display_class so
      // we never show the legacy "Unrecognised event: <json>" row. Any
      // unknown future kind still produces a sensible compact rendering.
      const other = event as OtherEvent;
      const cls = other.display_class ?? "raw";
      if (cls === "hidden") return null;
      if (cls === "meta") return <MetaEventRow event={other} />;
      if (cls === "text-like") return <TextLikeRow event={other} />;
      if (cls === "tool-like") return <ToolLikeRow event={other} />;
      return <RawEventRow event={other} />;
    }
  }
}
