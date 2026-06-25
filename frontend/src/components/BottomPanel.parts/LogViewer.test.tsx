import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LogEntry } from "../../types/api";
import { LogViewer } from "./LogViewer";

const exportMock = vi.fn();
vi.mock("../../lib/logger", () => ({
  exportDiagnosticBundle: () => exportMock(),
}));

afterEach(() => {
  cleanup();
  exportMock.mockReset();
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

  it("disables the export button and shows 'Exporting…' while the bundle is built (#1760 bug2)", async () => {
    let release: () => void = () => {};
    exportMock.mockReturnValue(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );

    render(<LogViewer entries={[]} />);
    const button = screen.getByRole("button", { name: "Export logs" });
    expect(button).not.toBeDisabled();

    fireEvent.click(button);

    // Immediate feedback: disabled + relabelled while the export is in flight.
    const exporting = await screen.findByRole("button", { name: "Exporting…" });
    expect(exporting).toBeDisabled();
    expect(exportMock).toHaveBeenCalledTimes(1);

    release();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Export logs" })).not.toBeDisabled(),
    );
  });
});
