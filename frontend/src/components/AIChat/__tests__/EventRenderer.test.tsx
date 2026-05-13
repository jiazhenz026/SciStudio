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

  it("falls back to OtherEvent for unknown kinds", () => {
    const ev: AgentEvent = {
      kind: "other",
      raw: { provider_specific: "thing" },
    };
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-other")).toHaveTextContent(/Unrecognised event/);
  });
});
