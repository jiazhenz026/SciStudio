import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AIBlockPresentationNotice } from "./AIBlockPresentationNotice";
import { setPresentation } from "../lib/presentation";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

it("explains the hidden interaction surface and follows presentation changes", () => {
  setPresentation("ai");
  render(<AIBlockPresentationNotice blockType="ai.agent" />);
  expect(screen.getByText("Use Workbench for AI Block")).toBeVisible();
  expect(screen.getByText(/prompts and permission requests/)).toHaveTextContent(
    "It does not use the AI host you are chatting with.",
  );
  act(() => setPresentation("workbench"));
  expect(screen.queryByText("Use Workbench for AI Block")).not.toBeInTheDocument();
  act(() => setPresentation("ai"));
  expect(screen.getByText("Use Workbench for AI Block")).toBeVisible();
});

it("does not infer local-agent requirements from a different block's name or category", () => {
  setPresentation("ai");
  const { container } = render(<AIBlockPresentationNotice blockType="my.ai_classifier" />);
  expect(container).toBeEmptyDOMElement();
});
