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

  it("renders an animated Thinking… indicator for kind=thinking", () => {
    // Issue #782 Bug 1: backend emits OtherEvent(kind='thinking') for
    // claude's interleaved-thinking content blocks. Renderer must show
    // an animated indicator with `data-testid="ev-thinking"`, not fall
    // back to the generic "Unrecognised event" row.
    const ev = {
      kind: "thinking",
      raw: { text: "step-by-step plan" },
    } as unknown as AgentEvent;
    render(<EventRenderer event={ev} />);
    const row = screen.getByTestId("ev-thinking");
    expect(row).toBeInTheDocument();
    expect(screen.getByTestId("ev-thinking-spinner")).toBeInTheDocument();
    // No fall-through to OtherEvent
    expect(screen.queryByTestId("ev-other")).toBeNull();
  });

  it("still shows the Thinking… indicator when thinking text is empty", () => {
    // Issue #782 Bug 1: empty-text thinking frames (signature-only) must
    // still surface the indicator — previously they returned null and
    // the user saw silence while the agent reasoned.
    const ev = {
      kind: "thinking",
      raw: { text: "", signature: "Er0CClkIDR..." },
    } as unknown as AgentEvent;
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-thinking")).toBeInTheDocument();
    expect(screen.queryByTestId("ev-other")).toBeNull();
  });

  it("renders ev-thinking even when only raw.type === 'thinking'", () => {
    // Issue #782 Bug 1: defensive fallback — if a top-level wire frame
    // somehow reaches the renderer with `kind: 'other'` but its raw
    // payload carries `type: 'thinking'`, we still render the indicator
    // rather than letting it slip through as "Unrecognised event".
    const ev = {
      kind: "other",
      raw: { type: "thinking", thinking: "", signature: "Er0CClk..." },
    } as unknown as AgentEvent;
    render(<EventRenderer event={ev} />);
    expect(screen.getByTestId("ev-thinking")).toBeInTheDocument();
    expect(screen.queryByTestId("ev-other")).toBeNull();
  });
});
