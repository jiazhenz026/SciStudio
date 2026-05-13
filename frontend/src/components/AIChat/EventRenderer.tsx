/**
 * Renders a single canonical AgentEvent per ADR-033 §3 D5.1.
 *
 * Dispatches on the discriminated `kind` field. Unknown kinds fall back
 * to the `OtherEvent` branch, classified per issue #788 display_class.
 *
 * Issue #784 (this file's changes):
 *  - `assistant_text_delta` content is rendered as sanitised markdown
 *    (react-markdown + rehype-sanitize + remark-gfm).
 *  - `tool_use` / `tool_result` rows use the shared `<CondensedToolRow>`
 *    from #788, collapsed by default. The global expansion preference
 *    (`toolRowsExpanded`) toggled via Ctrl+O drives them via the
 *    Zustand store; per-row click-to-expand still works locally.
 */

import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { useAppStore } from "../../store";
import type { AgentEvent, OtherEvent } from "../../types/agentEvents";
import { CondensedToolRow, MetaEventRow, RawEventRow, TextLikeRow, ToolLikeRow } from "./genericRows";

export interface EventRendererProps {
  event: AgentEvent;
}

/**
 * Custom react-markdown component overrides — keep links safe and code
 * blocks readable. Sanitization is delegated to `rehype-sanitize` so we
 * don't need to defend manually against raw HTML.
 */
const MARKDOWN_COMPONENTS = {
  a: ({ href, children, ...rest }: { href?: string; children?: React.ReactNode } & Record<string, unknown>) => (
    <a
      {...rest}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 underline"
    >
      {children}
    </a>
  ),
  code: ({ inline, className, children, ...rest }: { inline?: boolean; className?: string; children?: React.ReactNode } & Record<string, unknown>) => {
    if (inline) {
      return (
        <code className="rounded bg-gray-200 px-1 font-mono text-[0.85em]" {...rest}>
          {children}
        </code>
      );
    }
    return (
      <code className={`block ${className ?? ""}`} {...rest}>
        {children}
      </code>
    );
  },
  pre: ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => (
    <pre
      {...rest}
      className="my-1 overflow-auto rounded border border-gray-200 bg-white p-2 font-mono text-xs"
    >
      {children}
    </pre>
  ),
} as const;

export function EventRenderer({ event }: EventRendererProps) {
  // Issue #784 Bug 2 — global tool-row expansion preference (Ctrl+O).
  // Subscribed here so EventRenderer re-renders when toggled; the prop is
  // passed to `<CondensedToolRow>` as the `expanded` controlled value.
  const toolRowsExpanded = useAppStore((s) => s.toolRowsExpanded);

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
      // Issue #784 Bug 1: render delta as sanitised markdown.
      return (
        <div
          data-testid="ev-text"
          className="prose prose-sm max-w-none rounded bg-gray-50 px-2 py-1 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSanitize]}
            components={MARKDOWN_COMPONENTS as never}
          >
            {event.delta}
          </ReactMarkdown>
        </div>
      );
    case "tool_use":
      // Issue #784 Bug 2: collapsed by default; global Ctrl+O preference
      // expands all rows at once.
      return (
        <CondensedToolRow
          toolName={event.tool_name}
          input={event.tool_input}
          toolUseId={event.tool_use_id}
          expanded={toolRowsExpanded ? true : undefined}
          testId="ev-tool-use"
        />
      );
    case "tool_result":
      return (
        <CondensedToolRow
          // No tool name on the wire for results — use a placeholder that
          // matches Claude Code's own UI convention.
          toolName={event.is_error ? "Tool error" : "Tool result"}
          input={undefined}
          output={event.output}
          isError={event.is_error}
          toolUseId={event.tool_use_id}
          expanded={toolRowsExpanded ? true : undefined}
          testId="ev-tool-result"
        />
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
