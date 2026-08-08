/**
 * #2019: the project dialog while a create/open is in flight.
 *
 * `submitProjectDialog` only closes the dialog after the request settles, so
 * the dialog is on screen for the whole switch. Re-clicking "Create project"
 * during that window would race two project switches — each of which rebinds
 * registries, stores, git state, and the MCP transport server-side. The button
 * therefore reports progress and refuses a second submit, while Cancel stays
 * live so the user is never trapped.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProjectDialog } from "./ProjectDialog";

afterEach(() => cleanup());

const baseProps = {
  open: true,
  mode: "new" as const,
  name: "demo",
  description: "",
  path: "/tmp/projects",
  recentProjects: [],
  onChange: vi.fn(),
  onOpenRecent: vi.fn(),
};

describe("ProjectDialog busy state (#2019)", () => {
  it("submits normally when idle", () => {
    const onSubmit = vi.fn();
    render(<ProjectDialog {...baseProps} onClose={vi.fn()} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByTestId("project-dialog-submit"));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("labels the submit button so a slow switch reads as progress", () => {
    render(<ProjectDialog {...baseProps} busy onClose={vi.fn()} onSubmit={vi.fn()} />);

    expect(screen.getByTestId("project-dialog-submit")).toHaveTextContent("Working…");
  });

  it("refuses a second submit while a switch is in flight", () => {
    const onSubmit = vi.fn();
    render(<ProjectDialog {...baseProps} busy onClose={vi.fn()} onSubmit={onSubmit} />);

    const submit = screen.getByTestId("project-dialog-submit");
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("keeps Cancel live while busy so the user is never trapped", () => {
    const onClose = vi.fn();
    render(<ProjectDialog {...baseProps} busy onClose={onClose} onSubmit={vi.fn()} />);

    fireEvent.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
