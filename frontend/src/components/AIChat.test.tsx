import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "../types/api";
import { AIChat } from "./AIChat";

function makeProps(overrides: Partial<Parameters<typeof AIChat>[0]> = {}) {
  return {
    messages: [] as ChatMessage[],
    onSendChat: vi.fn(),
    isLoading: false,
    error: null,
    ...overrides,
  };
}

describe("AIChat", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders message list", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "Hello", timestamp: "2026-01-01T00:00:00Z" },
      { id: "2", role: "assistant", content: "Hi there!", timestamp: "2026-01-01T00:00:01Z" },
    ];

    render(<AIChat {...makeProps()} messages={messages} />);

    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Hi there!")).toBeInTheDocument();
  });

  it("shows loading spinner when isLoading=true", () => {
    render(<AIChat {...makeProps()} isLoading={true} />);

    expect(screen.getByTestId("streaming-indicator")).toBeInTheDocument();
    expect(screen.getByText("Thinking...")).toBeInTheDocument();
  });

  it("does not show loading spinner when isLoading=false", () => {
    render(<AIChat {...makeProps()} isLoading={false} />);

    expect(screen.queryByTestId("streaming-indicator")).not.toBeInTheDocument();
  });

  it("shows error banner when error is set", () => {
    render(<AIChat {...makeProps()} error="Something went wrong" />);

    expect(screen.getByTestId("error-banner")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("does not show error banner when error is null", () => {
    render(<AIChat {...makeProps()} error={null} />);

    expect(screen.queryByTestId("error-banner")).not.toBeInTheDocument();
  });

  it("renders code blocks for messages with backtick-fenced code", () => {
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "assistant",
        content: "Here is some code:\n\n```python\nprint('hello')\n```\n\nDone!",
        timestamp: "2026-01-01T00:00:00Z",
      },
    ];

    render(<AIChat {...makeProps()} messages={messages} />);

    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock).toBeInTheDocument();
    expect(codeBlock).toHaveTextContent("print('hello')");
  });

  it("calls onSendChat when Send button clicked", () => {
    const onSendChat = vi.fn();
    render(<AIChat {...makeProps()} onSendChat={onSendChat} />);

    const input = screen.getByPlaceholderText("Ask to generate blocks or suggest workflows...");
    fireEvent.change(input, { target: { value: "Hello AI" } });

    const sendButton = screen.getByText("Send");
    fireEvent.click(sendButton);

    expect(onSendChat).toHaveBeenCalledWith("Hello AI");
  });

  it("does not call onSendChat when input is empty", () => {
    const onSendChat = vi.fn();
    render(<AIChat {...makeProps()} onSendChat={onSendChat} />);

    const sendButton = screen.getByText("Send");
    fireEvent.click(sendButton);

    expect(onSendChat).not.toHaveBeenCalled();
  });

  it("does not call onSendChat when input is whitespace only", () => {
    const onSendChat = vi.fn();
    render(<AIChat {...makeProps()} onSendChat={onSendChat} />);

    const input = screen.getByPlaceholderText("Ask to generate blocks or suggest workflows...");
    fireEvent.change(input, { target: { value: "   " } });

    const sendButton = screen.getByText("Send");
    fireEvent.click(sendButton);

    expect(onSendChat).not.toHaveBeenCalled();
  });

  it("clears input after sending", () => {
    render(<AIChat {...makeProps()} onSendChat={vi.fn()} />);

    const input = screen.getByPlaceholderText("Ask to generate blocks or suggest workflows...");
    fireEvent.change(input, { target: { value: "test message" } });
    fireEvent.click(screen.getByText("Send"));

    expect(input).toHaveValue("");
  });

  it("disables Send button and input when loading", () => {
    render(<AIChat {...makeProps()} isLoading={true} />);

    const input = screen.getByPlaceholderText("Ask to generate blocks or suggest workflows...");
    const sendButton = screen.getByText("Send");

    expect(input).toBeDisabled();
    expect(sendButton).toBeDisabled();
  });

  it("shows Apply to Canvas button when assistant message contains workflow JSON", () => {
    const workflowJson = JSON.stringify(
      { nodes: [{ id: "n1" }], edges: [{ source: "n1", target: "n2" }] },
      null,
      2,
    );
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "assistant",
        content: `Here is a workflow:\n\n\`\`\`json\n${workflowJson}\n\`\`\``,
        timestamp: "2026-01-01T00:00:00Z",
      },
    ];

    const onApplyWorkflow = vi.fn();
    render(<AIChat {...makeProps()} messages={messages} onApplyWorkflow={onApplyWorkflow} />);

    const applyButton = screen.getByTestId("apply-to-canvas");
    expect(applyButton).toBeInTheDocument();
    expect(applyButton).toHaveTextContent("Apply to Canvas");

    fireEvent.click(applyButton);
    expect(onApplyWorkflow).toHaveBeenCalledWith(
      expect.objectContaining({ nodes: expect.any(Array), edges: expect.any(Array) }),
    );
  });

  it("does not show Apply to Canvas for user messages", () => {
    const workflowJson = JSON.stringify({ nodes: [], edges: [] }, null, 2);
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "user",
        content: `\`\`\`json\n${workflowJson}\n\`\`\``,
        timestamp: "2026-01-01T00:00:00Z",
      },
    ];

    render(<AIChat {...makeProps()} messages={messages} onApplyWorkflow={vi.fn()} />);

    expect(screen.queryByTestId("apply-to-canvas")).not.toBeInTheDocument();
  });

  it("sends message on Enter key press", () => {
    const onSendChat = vi.fn();
    render(<AIChat {...makeProps()} onSendChat={onSendChat} />);

    const input = screen.getByPlaceholderText("Ask to generate blocks or suggest workflows...");
    fireEvent.change(input, { target: { value: "Hello from Enter" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSendChat).toHaveBeenCalledWith("Hello from Enter");
  });
});
