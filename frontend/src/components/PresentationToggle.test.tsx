import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PresentationToggle } from "./PresentationToggle";
import { ActivityBar } from "./ActivityBar";
import { TooltipProvider } from "./ui/tooltip";
import { setPresentation } from "../lib/presentation";

afterEach(() => {
  cleanup();
  delete window.scistudioDesktop;
  window.history.replaceState(null, "", "/");
});

it("switches both ways and exposes distinct Preview and Previewers cards only in AI mode", () => {
  const select = vi.fn();
  render(
    <TooltipProvider>
      <PresentationToggle />
      <ActivityBar activeTab="blocks" panelOpen onSelect={select} />
    </TooltipProvider>,
  );
  expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Switch to AI host layout" }));
  expect(window.location.search).toBe("?ui=ai");
  expect(screen.getByRole("button", { name: "Previewers" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
  expect(select).toHaveBeenCalledWith("preview");
  fireEvent.click(screen.getByRole("button", { name: "Switch to full workbench" }));
  expect(window.location.search).toBe("?ui=workbench");
  expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
});

it("reflects an explicit AI entry before project creation", () => {
  act(() => setPresentation("ai"));
  render(
    <TooltipProvider>
      <PresentationToggle />
    </TooltipProvider>,
  );
  expect(screen.getByRole("button", { name: "Switch to full workbench" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

it("does not offer a layout switch in Electron", () => {
  window.scistudioDesktop = {
    platform: "win32",
    versions: { electron: "test", chrome: "test" },
    relaunch: async () => {},
    onMenuAction: () => () => {},
  };
  window.history.replaceState(null, "", "/?ui=ai");
  render(
    <TooltipProvider>
      <PresentationToggle />
    </TooltipProvider>,
  );
  expect(screen.queryByTestId("presentation-toggle")).not.toBeInTheDocument();
});
