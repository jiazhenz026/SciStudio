/**
 * ADR-053 Learning Center (#2057) — the highlight vocabulary must reach real
 * elements.
 *
 * A `highlight` naming a target nothing carries is worse than the plain text it
 * replaced: the step says "look here", the ring is drawn nowhere, and the user
 * is left with no guidance at all and no way to tell that anything was
 * supposed to appear. The backend validates that a manifest only names members
 * of `HIGHLIGHT_TARGETS`; this file is the other half of that guarantee —
 * every member resolves to an element this UI actually renders.
 *
 * The renderer map is typed `Record<HighlightTarget, ...>`, so adding a target
 * to the vocabulary without giving it a way to render fails the typecheck
 * rather than leaving a hole discovered by a user mid-tutorial.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BlockPalette } from "../BlockPalette";
import { PlotsTab } from "../BottomPanel.parts/PlotsTab";
import { DataPreview } from "../DataPreview";
import {
  HIGHLIGHT_TARGETS,
  ROUTE_TARGETS,
  ROUTE_TARGET_BOTTOM_TABS,
  ROUTE_TARGET_LEFT_TABS,
  applyStepRoute,
  tutorialTargetSelector,
  type HighlightTarget,
} from "../LearningCenter.parts/targets";
import { RestoreRunButton } from "../Lineage/RunDetail.parts/restore";
import { Toolbar } from "../Toolbar";
import { WorkflowCanvas } from "../WorkflowCanvas";
import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";

/** React Flow measures its container; jsdom has no ResizeObserver. */
class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function toolbarProps(): React.ComponentProps<typeof Toolbar> {
  return {
    currentProject: {
      id: "p1",
      name: "Demo",
      description: "",
      path: "/projects/demo",
      workflow_count: 1,
      workflows: ["main"],
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
  } as React.ComponentProps<typeof Toolbar>;
}

/**
 * One renderer per highlight target, each mounting the real component in the
 * state where the target is on screen.
 */
const RENDERERS: Record<HighlightTarget, () => void> = {
  block_palette: () => {
    render(
      <BlockPalette
        blocks={[]}
        collapsed={false}
        onAddBlock={vi.fn()}
        onReload={vi.fn()}
        onSearch={vi.fn()}
        search=""
      />,
    );
  },

  canvas: () => {
    render(
      <ReactFlowProvider>
        <WorkflowCanvas
          blockErrorSummaries={{}}
          blockErrors={{}}
          blockStates={{}}
          blocks={[]}
          edges={[]}
          minimapVisible={false}
          nodes={[]}
          onAddNode={vi.fn()}
          onConnect={vi.fn(async () => {})}
          onDeleteEdge={vi.fn()}
          onDeleteNode={vi.fn()}
          onErrorClick={vi.fn()}
          onResizeNode={vi.fn()}
          onRunBlock={vi.fn()}
          onSelectNode={vi.fn()}
          onUpdateNodeConfig={vi.fn()}
          onUpdateNodePosition={vi.fn()}
          schemas={{}}
          selectedNodeId={null}
        />
      </ReactFlowProvider>,
    );
  },

  run_button: () => {
    render(<Toolbar {...toolbarProps()} />);
  },

  plots_new_button: () => {
    // The button is disabled without a workflow, but a disabled button is
    // still an element a ring can be drawn around.
    useAppStore.setState({ workflowId: "main" });
    render(<PlotsTab />);
  },

  history_restore_button: () => {
    render(
      <RestoreRunButton
        onRestored={vi.fn()}
        run={{
          run_id: "r1",
          workflow_id: "main",
          workflow_git_commit: "abc1234",
          started_at: "2026-01-01T00:00:00Z",
        }}
      />,
    );
  },

  data_preview: () => {
    render(<DataPreview blockOutputs={{}} selectedNodeId={null} selectedNodeLabel="" />);
  },
};

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", StubResizeObserver);
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, status: 200, json: async () => ({ plots: [] }) })),
  );
  resetAppStore();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("tutorial highlight targets resolve to rendered elements", () => {
  it.each(HIGHLIGHT_TARGETS)("%s is carried by a real element", (target) => {
    RENDERERS[target]();
    const element = document.querySelector(tutorialTargetSelector(target));
    expect(element).not.toBeNull();
  });

  it("covers every member of the vocabulary, with nothing left over", () => {
    expect(Object.keys(RENDERERS).sort()).toEqual([...HIGHLIGHT_TARGETS].sort());
  });
});

describe("route targets map onto this UI (FR-089 companion)", () => {
  it("gives every route target a decision — a tab, a left tab, or neither", () => {
    for (const target of ROUTE_TARGETS) {
      expect(ROUTE_TARGET_BOTTOM_TABS).toHaveProperty(target);
    }
    expect(Object.keys(ROUTE_TARGET_BOTTOM_TABS).sort()).toEqual([...ROUTE_TARGETS].sort());
  });

  it("maps the two renamed names onto their internal keys", () => {
    // The UI shows "History"; the BottomTab key stayed `lineage` after the
    // owner-requested rename. `ai_chat` is the AI Chat tab, keyed `ai`.
    expect(ROUTE_TARGET_BOTTOM_TABS.history).toBe("lineage");
    expect(ROUTE_TARGET_BOTTOM_TABS.ai_chat).toBe("ai");
  });

  it("leaves the five unrenamed bottom-panel names alone", () => {
    for (const name of ["terminal", "config", "logs", "plots", "git"] as const) {
      expect(ROUTE_TARGET_BOTTOM_TABS[name]).toBe(name);
    }
  });

  it("opens the bottom tab rather than only selecting it", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();

    applyStepRoute("history", { openBottomTab, setLeftTab });

    // `openBottomTab` expands a collapsed panel; `setActiveBottomTab` would
    // change the tab behind a shut panel and look like nothing happened.
    expect(openBottomTab).toHaveBeenCalledWith("lineage");
    expect(setLeftTab).not.toHaveBeenCalled();
  });

  it("routes block_palette to the left panel's Blocks tab, not a bottom tab", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();

    applyStepRoute("block_palette", { openBottomTab, setLeftTab });

    expect(setLeftTab).toHaveBeenCalledWith("blocks");
    expect(openBottomTab).not.toHaveBeenCalled();
    expect(ROUTE_TARGET_LEFT_TABS.block_palette).toBe("blocks");
  });

  it("switches no surface for canvas — it is already the main one", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();

    applyStepRoute("canvas", { openBottomTab, setLeftTab });

    expect(openBottomTab).not.toHaveBeenCalled();
    expect(setLeftTab).not.toHaveBeenCalled();
  });

  it("ignores a name outside the vocabulary instead of throwing", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();

    applyStepRoute("not_a_target", { openBottomTab, setLeftTab });

    expect(openBottomTab).not.toHaveBeenCalled();
    expect(setLeftTab).not.toHaveBeenCalled();
  });
});

describe("the highlight ring does not occlude what it points at (FR-089)", () => {
  it("is drawn pointer-events-none so clicks and drags reach the element", async () => {
    const { StepHighlight } = await import("../LearningCenter.parts/StepHighlight");

    RENDERERS.canvas();
    // Give the canvas element a non-zero box; jsdom reports zeros otherwise and
    // the ring correctly declines to draw around nothing.
    const canvas = document.querySelector<HTMLElement>(tutorialTargetSelector("canvas"));
    if (!canvas) throw new Error("canvas target did not render");
    canvas.getBoundingClientRect = () =>
      ({ top: 10, left: 20, width: 300, height: 200 }) as DOMRect;

    useAppStore.setState({
      learningCenterSession: {
        source_kind: "core",
        source_id: "",
        tutorial_id: "first-workflow",
        title: "Run your first workflow",
        project_id: "p1",
        project_path: "/tmp/p1",
        step: {
          id: "drag-load",
          index: 0,
          total: 3,
          say: "Drag a Load block onto the canvas.",
          highlight: "canvas",
          route_to: "canvas",
          awaiting_continue: false,
        },
        satisfied_step_ids: [],
        status: "active",
        error: null,
        replay: null,
      },
    });

    render(<StepHighlight />);

    const ring = await screen.findByTestId("tutorial-step-highlight");
    expect(ring.className).toContain("pointer-events-none");
  });
});
