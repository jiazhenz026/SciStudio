/**
 * ADR-053 FR-001 (#2057) — this file used to cover only the first-workflow
 * tutorial prompt card, which is removed. What remains is the pane's own
 * surface: the two project actions and the recent list.
 *
 * The FR-083 first-run offer is not tested here, because it is no longer this
 * component's business — the Learning Center is the landing, and its own test
 * (`__tests__/LearningCenter.test.tsx`) covers it.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WelcomeScreen } from "./WelcomeScreen";

afterEach(() => cleanup());

const baseProps = {
  recentProjects: [],
  onNewProject: vi.fn(),
  onOpenProject: vi.fn(),
  onOpenRecent: vi.fn(),
};

describe("WelcomeScreen", () => {
  it("offers the two project actions", () => {
    const onNewProject = vi.fn();
    const onOpenProject = vi.fn();
    render(
      <WelcomeScreen {...baseProps} onNewProject={onNewProject} onOpenProject={onOpenProject} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "New Project" }));
    fireEvent.click(screen.getByRole("button", { name: "Open Project" }));

    expect(onNewProject).toHaveBeenCalledTimes(1);
    expect(onOpenProject).toHaveBeenCalledTimes(1);
  });

  it("lists recent projects and opens the one that is clicked", () => {
    const onOpenRecent = vi.fn();
    render(
      <WelcomeScreen
        {...baseProps}
        onOpenRecent={onOpenRecent}
        recentProjects={[
          {
            id: "p1",
            name: "Assay redo",
            description: "",
            path: "/projects/assay-redo",
            workflow_count: 1,
            workflows: ["main"],
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByText("Assay redo"));
    expect(onOpenRecent).toHaveBeenCalledWith("p1");
  });

  it("says so plainly when there are no recent projects", () => {
    render(<WelcomeScreen {...baseProps} />);
    expect(screen.getByText("No recent projects yet.")).toBeInTheDocument();
  });

  it("no longer carries the removed single-tutorial prompt (FR-001)", () => {
    render(<WelcomeScreen {...baseProps} />);
    expect(screen.queryByText("Run Your First SciStudio Workflow")).not.toBeInTheDocument();
    expect(screen.queryByText("Start tutorial")).not.toBeInTheDocument();
  });
});
