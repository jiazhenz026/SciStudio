import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { LogEntry } from "../../types/api";
import { LogViewer } from "./LogViewer";

afterEach(() => {
  cleanup();
});

describe("LogViewer", () => {
  it("shows a concise error message with expandable traceback details", () => {
    const entries: LogEntry[] = [
      {
        timestamp: "2026-05-26T00:00:00Z",
        level: "error",
        message: "Choose a new output path.",
        details: [
          "Traceback (most recent call last):",
          '  File "worker.py", line 1, in main',
          "ValueError: Choose a new output path.",
        ].join("\n"),
        workflow_id: "wf-1",
        block_id: "save-1",
      },
    ];

    render(<LogViewer entries={entries} />);

    expect(screen.getByText("Choose a new output path.")).toBeInTheDocument();
    expect(screen.getByText("Show traceback")).toBeInTheDocument();
    expect(screen.getByText(/Traceback/)).toBeInTheDocument();
  });
});
