import { useCallback, useEffect, useRef, useState } from "react";

import type { ChatMessage } from "../types/api";

export interface AIChatProps {
  messages: ChatMessage[];
  onSendChat: (message: string) => void;
  isLoading: boolean;
  error: string | null;
  onApplyWorkflow?: (workflow: Record<string, unknown>) => void;
}

/** Detect fenced code blocks (triple backticks) in a message. */
function parseMessageContent(content: string): Array<{ type: "text" | "code"; value: string; lang?: string }> {
  const parts: Array<{ type: "text" | "code"; value: string; lang?: string }> = [];
  const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Text before the code block
    if (match.index > lastIndex) {
      parts.push({ type: "text", value: content.slice(lastIndex, match.index) });
    }
    parts.push({ type: "code", value: match[2], lang: match[1] || undefined });
    lastIndex = match.index + match[0].length;
  }

  // Remaining text after last code block
  if (lastIndex < content.length) {
    parts.push({ type: "text", value: content.slice(lastIndex) });
  }

  if (parts.length === 0) {
    parts.push({ type: "text", value: content });
  }

  return parts;
}

/** Check whether a message contains workflow JSON (has "nodes" and "edges" keys). */
function extractWorkflowJson(content: string): Record<string, unknown> | null {
  const codeBlockRegex = /```(?:json)?\n([\s\S]*?)```/g;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    try {
      const parsed = JSON.parse(match[1]) as Record<string, unknown>;
      if (parsed && typeof parsed === "object" && "nodes" in parsed && "edges" in parsed) {
        return parsed;
      }
    } catch {
      // Not valid JSON, skip
    }
  }
  return null;
}

function StreamingIndicator() {
  return (
    <div className="flex items-center gap-1 px-4 py-3" data-testid="streaming-indicator">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-stone-400" />
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-stone-400 [animation-delay:150ms]" />
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-stone-400 [animation-delay:300ms]" />
      <span className="ml-2 text-sm text-stone-500">Thinking...</span>
    </div>
  );
}

function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 5000);
    return () => window.clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div
      className="mb-3 flex items-center justify-between rounded-[1.2rem] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      data-testid="error-banner"
      role="alert"
    >
      <span>{message}</span>
      <button className="ml-3 text-red-400 hover:text-red-600" onClick={onDismiss} type="button">
        Dismiss
      </button>
    </div>
  );
}

export function AIChat({ messages, onSendChat, isLoading, error, onApplyWorkflow }: AIChatProps) {
  const [draft, setDraft] = useState("");
  const [dismissedError, setDismissedError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isLoading]);

  const handleDismissError = useCallback(() => {
    setDismissedError(error);
  }, [error]);

  const showError = error && error !== dismissedError;

  return (
    <div className="flex h-full flex-col">
      {showError ? <ErrorBanner message={error} onDismiss={handleDismissError} /> : null}

      <div className="flex-1 space-y-3 overflow-auto">
        {messages.map((message) => {
          const parts = parseMessageContent(message.content);
          const workflowJson = message.role === "assistant" ? extractWorkflowJson(message.content) : null;

          return (
            <div
              className={`rounded-[1.4rem] px-4 py-3 text-sm ${
                message.role === "user" ? "bg-ink text-white" : "bg-white text-stone-700"
              }`}
              key={message.id}
            >
              <p className="text-[11px] uppercase tracking-[0.25em] opacity-70">{message.role}</p>
              <div className="mt-2">
                {parts.map((part, index) =>
                  part.type === "code" ? (
                    <pre
                      className="my-2 overflow-x-auto rounded-xl bg-stone-900 p-3 font-mono text-xs text-stone-100"
                      data-testid="code-block"
                      key={`${message.id}-part-${index}`}
                    >
                      <code>{part.value}</code>
                    </pre>
                  ) : (
                    <p className="whitespace-pre-wrap" key={`${message.id}-part-${index}`}>
                      {part.value}
                    </p>
                  ),
                )}
              </div>
              {workflowJson && onApplyWorkflow ? (
                <button
                  className="mt-2 rounded-full bg-amber-100 px-4 py-2 text-xs font-medium text-amber-800 hover:bg-amber-200"
                  data-testid="apply-to-canvas"
                  onClick={() => onApplyWorkflow(workflowJson)}
                  type="button"
                >
                  Apply to Canvas
                </button>
              ) : null}
            </div>
          );
        })}
        {isLoading ? <StreamingIndicator /> : null}
        <div ref={messagesEndRef} />
      </div>

      <div className="mt-4 flex gap-3">
        <input
          className="flex-1 rounded-full border border-stone-300 bg-white px-4 py-3"
          disabled={isLoading}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && draft.trim()) {
              event.preventDefault();
              onSendChat(draft);
              setDraft("");
            }
          }}
          placeholder="Ask to generate blocks or suggest workflows..."
          value={draft}
        />
        <button
          className="rounded-full bg-ink px-5 py-3 text-sm font-medium text-white disabled:opacity-50"
          disabled={isLoading || !draft.trim()}
          onClick={() => {
            if (!draft.trim()) {
              return;
            }
            onSendChat(draft);
            setDraft("");
          }}
          type="button"
        >
          Send
        </button>
      </div>
    </div>
  );
}
