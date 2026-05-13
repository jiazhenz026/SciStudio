/**
 * Reusable condensed tool row (issue #788, consumed by #784).
 *
 * Renders a one-line summary of a tool invocation:
 *   ⏺ tool_name(input_preview)              ✔/✖
 *
 * Click to expand and reveal full input + optional output. Both #788's
 * generic `tool-like` fallback (`ToolLikeRow`) and #784's native
 * `tool_use` / `tool_result` arms consume this component so the
 * rendering stays consistent.
 */

import { useState } from "react";

export interface CondensedToolRowProps {
  /** Tool name displayed in the collapsed summary. */
  toolName: string;
  /** Tool input dict. Pretty-printed when expanded; preview keys shown collapsed. */
  input?: Record<string, unknown>;
  /** Optional tool output (string or object). When present, rendered as a sub-block. */
  output?: string | Record<string, unknown>;
  /** Indicates the tool result was an error; flips icon to ✖ and styles red. */
  isError?: boolean;
  /** Optional tool_use_id for correlation; surfaced in the expanded view. */
  toolUseId?: string;
  /**
   * Initial expansion state. When omitted the row is collapsed by default.
   * #784 supplies this from a global Zustand store driven by Ctrl+O.
   */
  expanded?: boolean;
  /** Optional test id override for snapshot tests targeting specific rows. */
  testId?: string;
}

function _truncatePreview(input: Record<string, unknown> | undefined): string {
  if (!input) return "";
  const keys = Object.keys(input);
  if (keys.length === 0) return "";
  // Try to surface a single-line preview of the first scalar key if any.
  for (const k of keys) {
    const v = input[k];
    if (typeof v === "string" && v.length <= 40) return `${k}: ${v}`;
    if (typeof v === "number" || typeof v === "boolean") return `${k}: ${v}`;
  }
  return keys.join(", ");
}

export function CondensedToolRow({
  toolName,
  input,
  output,
  isError = false,
  toolUseId,
  expanded: expandedProp,
  testId = "ev-condensed-tool",
}: CondensedToolRowProps) {
  const [localExpanded, setLocalExpanded] = useState<boolean>(false);
  // When parent passes `expanded` explicitly, it controls the row; otherwise
  // we manage state locally on click.
  const expanded = expandedProp ?? localExpanded;
  const icon = isError ? "✖" : "✔";
  const iconClass = isError ? "text-red-600" : "text-green-600";
  const borderClass = isError ? "border-red-200 bg-red-50" : "border-blue-200 bg-blue-50";
  const preview = _truncatePreview(input);

  return (
    <div
      data-testid={testId}
      data-expanded={expanded ? "true" : "false"}
      className={`rounded border ${borderClass} px-2 py-1 text-sm`}
    >
      <button
        type="button"
        onClick={() => setLocalExpanded((v) => !v)}
        className="flex w-full items-center gap-2 text-left"
      >
        <span aria-hidden="true" className={`font-mono ${iconClass}`}>
          ⏺
        </span>
        <span className="font-mono font-semibold">{toolName}</span>
        {preview ? <span className="truncate text-xs text-gray-600">({preview})</span> : null}
        <span className={`ml-auto font-mono ${iconClass}`} aria-hidden="true">
          {icon}
        </span>
      </button>
      {expanded ? (
        <div data-testid={`${testId}-detail`} className="mt-1 space-y-1">
          {input ? (
            <pre className="overflow-auto rounded bg-white/60 p-1 text-xs">
              {JSON.stringify(input, null, 2)}
            </pre>
          ) : null}
          {output !== undefined ? (
            <pre className="overflow-auto rounded bg-white/60 p-1 text-xs">
              {typeof output === "string" ? output : JSON.stringify(output, null, 2)}
            </pre>
          ) : null}
          {toolUseId ? (
            <div className="text-[10px] text-gray-500">id={toolUseId}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
