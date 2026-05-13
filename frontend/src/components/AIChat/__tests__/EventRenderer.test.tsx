import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AgentEvent } from "../../../types/agentEvents";
import { EventRenderer } from "../EventRenderer";

describe("EventRenderer", () => {
  afterEach(() => cleanup());

  it("renders an init event", () => {
    const ev: AgentEvent = {
      kind: "init",
      raw: {},
      session_id: "s1",
      schema_version: null,
      model: "claude-sonnet-4",
    };
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-init")).toHaveTextContent(/claude-sonnet-4/);
  });

  it("renders an assistant text delta", () => {
    const ev: AgentEvent = {
      kind: "assistant_text_delta",
      raw: {},
      delta: "hello world",
    };
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-text")).toHaveTextContent("hello world");
  });

  it("renders a tool_use event with tool name", () => {
    const ev: AgentEvent = {
      kind: "tool_use",
      raw: {},
      tool_name: "Edit",
      tool_input: { file_path: "/x" },
      tool_use_id: "tu-1",
    };
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-tool-use")).toHaveTextContent(/Edit/);
  });

  it("renders a tool_result with error styling when is_error=true", () => {
    const ev: AgentEvent = {
      kind: "tool_result",
      raw: {},
      tool_use_id: "tu-1",
      output: "boom",
      is_error: true,
    };
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-tool-result")).toHaveTextContent(/Tool error/);
  });

  it("renders an error event", () => {
    const ev: AgentEvent = {
      kind: "error",
      raw: {},
      message: "stream broken",
      error_type: null,
    };
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-error")).toHaveTextContent(/stream broken/);
  });

  it("renders a done event", () => {
    const ev: AgentEvent = { kind: "done", raw: {} };
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-done")).toBeInTheDocument();
  });

  it("renders OtherEvent with display_class='raw' as a compact <kind> chip (issue #788)", () => {
    // The legacy "Unrecognised event: <json>" row is gone. Unknown
    // kinds fall through to the display_class taxonomy; without an
    // explicit class the renderer defaults to `raw`.
    const ev = {
      kind: "future_unknown",
      raw: { provider_specific: "thing" },
      display_class: "raw" as const,
    } as unknown as AgentEvent;
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-raw")).toHaveTextContent("future_unknown");
    expect(screen.queryByTestId("ev-other")).toBeNull();
  });

  it("dispatches display_class='hidden' to null (issue #788)", () => {
    const ev = {
      kind: "heartbeat",
      raw: {},
      display_class: "hidden" as const,
    } as unknown as AgentEvent;
    const { container } = render(<EventRenderer event={ev} />);
    expect(container.firstChild).toBeNull();
  });

  it("dispatches display_class='meta' to MetaEventRow (issue #788)", () => {
    const ev = {
      kind: "system/hook_started",
      raw: { subtype: "hook_started" },
      display_class: "meta" as const,
    } as unknown as AgentEvent;
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-meta")).toHaveTextContent("system/hook_started");
  });

  it("dispatches display_class='text-like' to TextLikeRow (issue #788)", () => {
    const ev = {
      kind: "future_kind",
      raw: { text: "hello there" },
      display_class: "text-like" as const,
    } as unknown as AgentEvent;
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-textlike")).toHaveTextContent("hello there");
  });

  it("dispatches display_class='tool-like' to ToolLikeRow (issue #788)", () => {
    const ev = {
      kind: "future_tool",
      raw: { tool_name: "MagicTool", input: { x: 1 } },
      display_class: "tool-like" as const,
    } as unknown as AgentEvent;
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-toollike")).toHaveTextContent("MagicTool");
  });
});
