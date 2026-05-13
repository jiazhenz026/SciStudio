/**
 * Meta event row (issue #788).
 *
 * One-line muted "[meta] <kind>: <summary>" row with click-to-expand
 * for the raw payload. Used for session metadata that's worth seeing
 * but not interesting enough to dominate the chat view (rate-limit
 * notices, model-change announcements, system bookkeeping).
 */

import { getOtherKind, type OtherEvent } from "../../../types/agentEvents";

export interface MetaEventRowProps {
  event: OtherEvent;
}

function _summarise(raw: Record<string, unknown>): string {
  // Prefer the most-informative fields if present.
  for (const key of ["subtype", "message", "summary", "result", "stop_reason"]) {
    const v = raw[key];
    if (typeof v === "string" && v.trim()) return v.slice(0, 80);
  }
  return "";
}

export function MetaEventRow({ event }: MetaEventRowProps) {
  const summary = _summarise(event.raw);
  return (
    <details data-testid="ev-meta" className="text-xs text-gray-500">
      <summary className="cursor-pointer">
        <span className="font-mono uppercase tracking-wide text-gray-400">[meta]</span>{" "}
        <span className="font-mono">{getOtherKind(event)}</span>
        {summary ? <span className="ml-1 text-gray-500">: {summary}</span> : null}
      </summary>
      <pre className="mt-1 overflow-auto rounded bg-gray-50 p-1 text-[10px] text-gray-600">
        {JSON.stringify(event.raw, null, 2)}
      </pre>
    </details>
  );
}
