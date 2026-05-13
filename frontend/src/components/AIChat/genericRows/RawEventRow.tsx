/**
 * Raw event row (issue #788).
 *
 * Last-resort renderer for `OtherEvent`s the classifier couldn't place
 * into any structural class. Shows a small monospace `<kind>` chip with
 * click-to-expand pretty-printed JSON.
 *
 * Strictly better than the legacy "Unrecognised event: <80-char JSON>"
 * row — the kind name is foregrounded and the full payload is one click
 * away.
 */

import { getOtherKind, type OtherEvent } from "../../../types/agentEvents";

export interface RawEventRowProps {
  event: OtherEvent;
}

export function RawEventRow({ event }: RawEventRowProps) {
  return (
    <details data-testid="ev-raw" className="text-xs text-gray-500">
      <summary className="cursor-pointer">
        <span className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[11px] text-gray-700">
          {getOtherKind(event)}
        </span>
        <span className="ml-1 italic text-gray-400">(click to expand)</span>
      </summary>
      <pre className="mt-1 overflow-auto rounded bg-gray-50 p-1 text-[10px] text-gray-600">
        {JSON.stringify(event.raw, null, 2)}
      </pre>
    </details>
  );
}
