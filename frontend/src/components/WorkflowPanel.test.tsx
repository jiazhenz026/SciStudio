// #2090 — the Workflows left-panel section: lists every workflow in the open
// project with its YAML description, highlights the one on the canvas, and
// opens one on click.

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../lib/api";
import { api } from "../lib/api";
import { useAppStore } from "../store";
import { WorkflowPanel } from "./WorkflowPanel";

vi.mock("../lib/api", async () => {
  // Partial mock: the real store (imported for the watcher-counter test)
  // pulls in the full api surface, so only the two endpoints the panel
  // calls are replaced.
  const actual = await vi.importActual<typeof ApiModule>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listWorkflows: vi.fn(),
      getWorkflow: vi.fn(),
    },
  };
});

const listWorkflows = vi.mocked(api.listWorkflows);
const getWorkflow = vi.mocked(api.getWorkflow);

function workflowResponse(id: string, description: string) {
  return {
    id,
    version: "1.0.0",
    description,
    nodes: [],
    edges: [],
    metadata: {},
  };
}

afterEach(cleanup);

beforeEach(() => {
  vi.resetAllMocks();
  // The panel subscribes to this watcher counter (Codex P2 on #2106); keep
  // every test starting from the no-bump baseline.
  useAppStore.setState({ projectTreeRefreshCounter: 0 });
});

describe("WorkflowPanel", () => {
  it("lists every workflow with its YAML description", async () => {
    listWorkflows.mockResolvedValue(["main", "qc"]);
    getWorkflow.mockImplementation(async (id) =>
      workflowResponse(id, id === "main" ? "Primary pipeline" : "Quality control"),
    );

    render(<WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />);

    expect(await screen.findByText("main")).toBeInTheDocument();
    expect(screen.getByText("Primary pipeline")).toBeInTheDocument();
    expect(screen.getByText("qc")).toBeInTheDocument();
    expect(screen.getByText("Quality control")).toBeInTheDocument();
  });

  it("opens a workflow on click", async () => {
    listWorkflows.mockResolvedValue(["main"]);
    getWorkflow.mockResolvedValue(workflowResponse("main", ""));
    const onOpenWorkflow = vi.fn();

    render(
      <WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={onOpenWorkflow} />,
    );

    fireEvent.click(await screen.findByText("main"));
    expect(onOpenWorkflow).toHaveBeenCalledWith("main", "main");
  });

  it("highlights the workflow on the canvas", async () => {
    listWorkflows.mockResolvedValue(["main", "qc"]);
    getWorkflow.mockImplementation(async (id) => workflowResponse(id, ""));

    render(<WorkflowPanel projectId="p1" activeWorkflowId="qc" onOpenWorkflow={vi.fn()} />);

    const activeRow = await screen.findByText("qc");
    expect(activeRow.closest("button")).toHaveAttribute("aria-current", "true");
    expect(screen.getByText("main").closest("button")).toHaveAttribute("aria-current", "false");
  });

  it("still lists a workflow whose detail fetch fails, without a description", async () => {
    listWorkflows.mockResolvedValue(["broken", "main"]);
    getWorkflow.mockImplementation(async (id) => {
      if (id === "broken") throw new Error("mid-write YAML");
      return workflowResponse(id, "Primary pipeline");
    });

    render(<WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />);

    expect(await screen.findByText("broken")).toBeInTheDocument();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getAllByText("Primary pipeline")).toHaveLength(1);
  });

  it("shows the empty state when the project has no workflows", async () => {
    listWorkflows.mockResolvedValue([]);

    render(<WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />);

    expect(await screen.findByText("No workflows found")).toBeInTheDocument();
  });

  it("refetches on Reload", async () => {
    listWorkflows.mockResolvedValue(["main"]);
    getWorkflow.mockImplementation(async (id) => workflowResponse(id, ""));

    render(<WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />);

    await screen.findByText("main");
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    await screen.findByText("main");
    expect(listWorkflows).toHaveBeenCalledTimes(2);
  });

  // Codex P2 on #2106.
  it("ignores a stale refresh that resolves after a project switch", async () => {
    let resolveOld!: (ids: string[]) => void;
    listWorkflows
      .mockImplementationOnce(() => new Promise<string[]>((resolve) => (resolveOld = resolve)))
      .mockResolvedValue(["wf-new"]);
    getWorkflow.mockImplementation(async (id) => workflowResponse(id, `desc of ${id}`));

    const { rerender } = render(
      <WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />,
    );
    // Switch projects while p1's list request is still outstanding.
    rerender(<WorkflowPanel projectId="p2" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />);
    expect(await screen.findByText("wf-new")).toBeInTheDocument();

    // The old project's request finishes last — it must not overwrite p2's list.
    await act(async () => resolveOld(["wf-old"]));
    expect(screen.queryByText("wf-old")).not.toBeInTheDocument();
    expect(screen.getByText("wf-new")).toBeInTheDocument();
  });

  // Codex P2 on #2106 — same watcher counter the project tree subscribes to.
  it("refreshes when the structural workflow counter bumps", async () => {
    listWorkflows.mockResolvedValue(["main"]);
    getWorkflow.mockImplementation(async (id) => workflowResponse(id, ""));

    render(<WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />);
    await screen.findByText("main");
    expect(listWorkflows).toHaveBeenCalledTimes(1);

    await act(async () => {
      useAppStore.setState({ projectTreeRefreshCounter: 1 });
    });
    expect(listWorkflows).toHaveBeenCalledTimes(2);
  });
});
