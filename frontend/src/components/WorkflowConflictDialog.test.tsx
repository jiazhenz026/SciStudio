import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowConflictDialog } from "./WorkflowConflictDialog";
import type { VersionConflictState } from "../store/types";

afterEach(() => {
  cleanup();
});

function conflict(overrides: Partial<VersionConflictState> = {}): VersionConflictState {
  return {
    entityClass: "workflow",
    entityId: "demo",
    kind: "modified",
    source: "agent",
    sourceId: null,
    baseVersion: 5,
    pendingVersion: 5,
    remoteVersion: 6,
    detectedAt: "2026-06-30T00:00:00Z",
    message: "remote change",
    remoteWorkflow: {
      id: "demo",
      version: "1.0.0",
      description: "",
      nodes: [],
      edges: [],
      metadata: {},
    },
    ...overrides,
  };
}

describe("WorkflowConflictDialog (#1891)", () => {
  it("renders nothing when there is no conflict", () => {
    const { container } = render(<WorkflowConflictDialog conflict={null} onResolve={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a non-workflow conflict", () => {
    const { container } = render(
      <WorkflowConflictDialog conflict={conflict({ entityClass: "file" })} onResolve={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("names the agent as the remote writer", () => {
    render(<WorkflowConflictDialog conflict={conflict()} onResolve={vi.fn()} />);
    expect(screen.getByTestId("workflow-conflict-dialog")).toHaveTextContent("the AI agent");
  });

  it("resolves keepLocal when the user keeps their version", () => {
    const onResolve = vi.fn();
    render(<WorkflowConflictDialog conflict={conflict()} onResolve={onResolve} />);
    fireEvent.click(screen.getByTestId("workflow-conflict-keep-local"));
    expect(onResolve).toHaveBeenCalledWith("keepLocal");
  });

  it("resolves loadRemote when the user loads the remote version", () => {
    const onResolve = vi.fn();
    render(<WorkflowConflictDialog conflict={conflict()} onResolve={onResolve} />);
    const button = screen.getByTestId("workflow-conflict-load-remote");
    expect(button).toHaveTextContent("Load their version");
    fireEvent.click(button);
    expect(onResolve).toHaveBeenCalledWith("loadRemote");
  });

  it("labels the load button as a discard when there is no remote payload", () => {
    render(
      <WorkflowConflictDialog conflict={conflict({ remoteWorkflow: null })} onResolve={vi.fn()} />,
    );
    expect(screen.getByTestId("workflow-conflict-load-remote")).toHaveTextContent(
      "Discard my edits",
    );
  });
});
