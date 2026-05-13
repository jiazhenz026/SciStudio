/**
 * Tool-like fallback row (issue #788).
 *
 * Wraps `<CondensedToolRow>` for `OtherEvent`s whose payload has a
 * `tool_name` / `name` + `input` shape but did not match a canonical
 * `tool_use` kind. The reusable `<CondensedToolRow>` is the shared
 * abstraction with #784's tool-collapse work.
 */

import { getOtherKind, type OtherEvent } from "../../../types/agentEvents";
import { CondensedToolRow } from "./CondensedToolRow";

export interface ToolLikeRowProps {
  event: OtherEvent;
}

export function ToolLikeRow({ event }: ToolLikeRowProps) {
  const raw = event.raw;
  let toolName: string;
  if (typeof raw.tool_name === "string" && raw.tool_name) {
    toolName = raw.tool_name;
  } else if (typeof raw.name === "string" && raw.name) {
    toolName = raw.name;
  } else {
    toolName = getOtherKind(event);
  }
  let input: Record<string, unknown> | undefined;
  if (raw.input && typeof raw.input === "object") {
    input = raw.input as Record<string, unknown>;
  } else if (raw.tool_input && typeof raw.tool_input === "object") {
    input = raw.tool_input as Record<string, unknown>;
  }
  const toolUseId = typeof raw.tool_use_id === "string" ? raw.tool_use_id : undefined;

  return (
    <CondensedToolRow
      toolName={toolName}
      input={input}
      toolUseId={toolUseId}
      testId="ev-toollike"
    />
  );
}
