/**
 * Text-like fallback row (issue #788).
 *
 * Renders a muted text bubble for events that look like assistant text
 * but aren't carried on a canonical AssistantTextDeltaEvent (e.g. a
 * future kind that ships with a `text` / `content` / `message` field).
 *
 * Lighter styling than the real assistant bubble so users can tell
 * "this is the renderer's best guess at unknown content, not a
 * first-class assistant turn".
 *
 * Markdown rendering of the canonical assistant text is added in #784;
 * the fallback here keeps to plain pre-wrap to stay minimal — #784 may
 * choose to also pipe this through react-markdown.
 */

import { getOtherKind, type OtherEvent } from "../../../types/agentEvents";

export interface TextLikeRowProps {
  event: OtherEvent;
}

function _extractText(raw: Record<string, unknown>): string {
  for (const key of ["text", "content", "message", "delta", "thinking"]) {
    const v = raw[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return "";
}

export function TextLikeRow({ event }: TextLikeRowProps) {
  const text = _extractText(event.raw);
  if (!text) return null;
  return (
    <div
      data-testid="ev-textlike"
      className="whitespace-pre-wrap rounded border border-gray-100 bg-gray-50/60 px-2 py-1 text-sm text-gray-700"
    >
      <span className="mr-1 font-mono text-[10px] uppercase tracking-wide text-gray-400">
        {getOtherKind(event)}
      </span>
      {text}
    </div>
  );
}
