// #2090 — the VS Code-style activity bar: icon rail, hover tooltips, and the
// active-section marker (hidden while the panel is collapsed).

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActivityBar, type ActivityBarProps } from "./ActivityBar";
import { TooltipProvider } from "./ui/tooltip";

afterEach(cleanup);

function renderBar(overrides: Partial<ActivityBarProps> = {}) {
  const onSelect = vi.fn();
  render(
    <TooltipProvider delayDuration={0}>
      <ActivityBar activeTab="blocks" panelOpen onSelect={onSelect} {...overrides} />
    </TooltipProvider>,
  );
  return onSelect;
}

describe("ActivityBar", () => {
  it("renders one icon button per left-panel section", () => {
    renderBar();
    expect(screen.getByTestId("activity-bar")).toBeInTheDocument();
    for (const label of ["Blocks", "Data types", "Workflows", "Data", "Project"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("reports the clicked section", () => {
    const onSelect = renderBar();
    fireEvent.click(screen.getByRole("button", { name: "Workflows" }));
    expect(onSelect).toHaveBeenCalledWith("workflows");
    fireEvent.click(screen.getByRole("button", { name: "Project" }));
    expect(onSelect).toHaveBeenCalledWith("project");
  });

  it("marks the active section only while the panel is open", () => {
    renderBar({ activeTab: "types", panelOpen: true });
    expect(screen.getByRole("button", { name: "Data types" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Blocks" })).toHaveAttribute("aria-pressed", "false");

    cleanup();
    renderBar({ activeTab: "types", panelOpen: false });
    // VS Code behavior: a collapsed panel shows no active marker at all.
    expect(screen.getByRole("button", { name: "Data types" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("shows the section name in a tooltip on hover/focus", async () => {
    renderBar();
    fireEvent.focus(screen.getByRole("button", { name: "Workflows" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Workflows");
  });
});
