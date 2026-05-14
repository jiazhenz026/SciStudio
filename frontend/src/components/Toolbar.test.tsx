/**
 * ADR-036 §3.7 — Toolbar kind-swap tests (I36b).
 *
 * Verifies that:
 *   - When ``activeTabKind === "workflow"`` (default), the existing button
 *     set is rendered: Run / Pause / Stop / Reset / Reload / Delete /
 *     Note / Group are all present.
 *   - When ``activeTabKind === "file"``, those workflow-only buttons are
 *     hidden; only New / Import / Save remain.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toolbar } from "./Toolbar";

afterEach(() => {
  cleanup();
});

function makeProps(overrides: Partial<React.ComponentProps<typeof Toolbar>> = {}) {
  return {
    currentProject: {
      id: "p1",
      name: "Demo",
      description: "",
      path: "/tmp/p1",
      workflows: [],
      current_workflow_id: "main",
    },
    workflowId: "main",
    workflowName: "main",
    workflowDirty: false,
    selectedNodeId: "node-1",
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
    onAddGroup: vi.fn(),
    isRunning: false,
    ...overrides,
  } as React.ComponentProps<typeof Toolbar>;
}

describe("Toolbar — ADR-036 §3.7 kind-swap", () => {
  it("workflow tab: Run / Pause / Stop / Reset / Reload / Delete / Note / Group are visible", () => {
    render(<Toolbar {...makeProps({ activeTabKind: "workflow" })} />);
    // Group 2 (always present)
    expect(screen.getByRole("button", { name: /^new$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy();
    // Workflow-only groups
    expect(screen.getByRole("button", { name: /^run$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^pause$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^stop$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^reset$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^reload$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^note$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^group$/i })).toBeTruthy();
  });

  it("workflow tab: defaults to workflow when activeTabKind is omitted", () => {
    render(<Toolbar {...makeProps()} />);
    expect(screen.getByRole("button", { name: /^run$/i })).toBeTruthy();
  });

  it("file tab: only New / Import / Save are visible; workflow-only buttons hidden", () => {
    render(<Toolbar {...makeProps({ activeTabKind: "file" })} />);
    // Group 2 still present
    expect(screen.getByRole("button", { name: /^new$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy();
    // Workflow-only groups hidden
    expect(screen.queryByRole("button", { name: /^run$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^running$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^pause$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^stop$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^reset$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^delete$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^reload$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^note$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^group$/i })).toBeNull();
  });
});
