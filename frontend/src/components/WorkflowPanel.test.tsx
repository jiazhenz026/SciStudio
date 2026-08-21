// #2090 — the Workflows left-panel section: lists every workflow in the open
// project with its YAML description, highlights the one on the canvas, and
// opens one on click.

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { WorkflowPanel } from "./WorkflowPanel";

vi.mock("../lib/api", () => ({
  api: {
    listWorkflows: vi.fn(),
    getWorkflow: vi.fn(),
  },
}));

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

  it("refetches on Refresh", async () => {
    listWorkflows.mockResolvedValue(["main"]);
    getWorkflow.mockImplementation(async (id) => workflowResponse(id, ""));

    render(<WorkflowPanel projectId="p1" activeWorkflowId={null} onOpenWorkflow={vi.fn()} />);

    await screen.findByText("main");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByText("main");
    expect(listWorkflows).toHaveBeenCalledTimes(2);
  });
});
