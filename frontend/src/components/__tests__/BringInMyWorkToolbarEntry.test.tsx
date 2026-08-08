/**
 * ADR-053 spec 2 (#2001) — the toolbar entry (FR-001, FR-002).
 *
 * FR-001 is a rule about what the entry must NOT depend on: not Learning Center
 * progress, not project count, not elapsed time. ADR-053 §4.2's threshold
 * governs when the product volunteers the capability, never whether it can be
 * reached — so the entry renders on every toolbar, in every tab kind, and its
 * only condition is FR-002's open project.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toolbar } from "../Toolbar";
import { ENTRY_LABEL } from "../BringInMyWorkDialog.parts/copy";

afterEach(cleanup);

function makeProps(overrides: Partial<React.ComponentProps<typeof Toolbar>> = {}) {
  return {
    currentProject: {
      id: "p1",
      name: "Demo",
      description: "",
      path: "/projects/demo",
      workflows: [],
      current_workflow_id: "main",
    },
    workflowId: "main",
    workflowName: "main",
    workflowDirty: false,
    selectedNodeId: null,
    wsConnected: true,
    sseConnected: true,
    recentProjects: [],
    onNewProject: vi.fn(),
    onOpenProject: vi.fn(),
    onOpenRecent: vi.fn(),
    onCloseProject: vi.fn(),
    onNewWorkflow: vi.fn(),
    onSave: vi.fn(),
    onSaveAs: vi.fn(),
    onImport: vi.fn(),
    onRun: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
    onStop: vi.fn(),
    onReset: vi.fn(),
    onDelete: vi.fn(),
    onReloadBlocks: vi.fn(),
    onStartFromSelected: vi.fn(),
    onAddAnnotation: vi.fn(),
    isRunning: false,
    ...overrides,
  } as React.ComponentProps<typeof Toolbar>;
}

describe("toolbar entry — Bring in my work (#2001)", () => {
  it('is labelled "Bring in my work" and enabled with a project open', () => {
    render(<Toolbar {...makeProps()} />);
    const entry = screen.getByRole("button", { name: ENTRY_LABEL });
    expect(entry).toBeEnabled();
  });

  it("is disabled with no project open, because a session writes into a project", () => {
    render(<Toolbar {...makeProps({ currentProject: null })} />);
    expect(screen.getByRole("button", { name: ENTRY_LABEL })).toBeDisabled();
  });

  it("is present on the file toolbar too — it is not a workflow-only affordance", () => {
    render(<Toolbar {...makeProps({ activeTabKind: "file" })} />);
    expect(screen.getByRole("button", { name: ENTRY_LABEL })).toBeEnabled();
  });

  it("opens the dialog when activated", () => {
    render(<Toolbar {...makeProps()} />);
    expect(screen.queryByTestId("work-import-dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: ENTRY_LABEL }));
    expect(screen.getByTestId("work-import-dialog")).toBeTruthy();
  });

  it("does not mount the dialog — and therefore does not probe — until asked", () => {
    render(<Toolbar {...makeProps()} />);
    expect(screen.queryByTestId("work-import-dialog")).toBeNull();
  });
});
