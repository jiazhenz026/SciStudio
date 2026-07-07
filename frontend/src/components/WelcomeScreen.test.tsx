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

describe("WelcomeScreen tutorial prompt", () => {
  it("shows the first-workflow tutorial callout when requested", () => {
    render(<WelcomeScreen {...baseProps} tutorialPromptVisible />);

    expect(screen.getByText("Run Your First SciStudio Workflow")).toBeInTheDocument();
    expect(screen.getByText("Start tutorial")).toBeInTheDocument();
    expect(screen.getByText("Not now")).toBeInTheDocument();
    expect(screen.getByText("Don't show again")).toBeInTheDocument();
  });

  it("wires tutorial prompt actions", () => {
    const onStartTutorial = vi.fn();
    const onDismissTutorial = vi.fn();
    const onSuppressTutorial = vi.fn();

    render(
      <WelcomeScreen
        {...baseProps}
        tutorialPromptVisible
        onStartTutorial={onStartTutorial}
        onDismissTutorial={onDismissTutorial}
        onSuppressTutorial={onSuppressTutorial}
      />,
    );

    fireEvent.click(screen.getByText("Start tutorial"));
    fireEvent.click(screen.getByText("Not now"));
    fireEvent.click(screen.getByText("Don't show again"));

    expect(onStartTutorial).toHaveBeenCalledTimes(1);
    expect(onDismissTutorial).toHaveBeenCalledTimes(1);
    expect(onSuppressTutorial).toHaveBeenCalledTimes(1);
  });

  it("hides the tutorial callout when not requested", () => {
    render(<WelcomeScreen {...baseProps} />);

    expect(screen.queryByText("Run Your First SciStudio Workflow")).not.toBeInTheDocument();
  });
});
