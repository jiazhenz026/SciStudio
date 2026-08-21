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
import { BottomPanel } from "../BottomPanel";
import { PlotsTab } from "../BottomPanel.parts/PlotsTab";
import { DataPreview } from "../DataPreview";
import {
  HIGHLIGHT_TARGETS,
  HIGHLIGHT_TARGET_KEYS,
  ROUTE_TARGETS,
  ROUTE_TARGET_BOTTOM_TABS,
  ROUTE_TARGET_LEFT_TABS,
  applyStepRoute,
  tutorialTargetSelector,
  type HighlightTarget,
} from "../LearningCenter.parts/targets";
import { TargetHighlight } from "../LearningCenter.parts/TargetHighlight";
import { RestoreRunButton } from "../Lineage/RunDetail.parts/restore";
import { renderNode } from "../nodes/__tests__/BlockNode/test-utils";
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
 * One case per highlight target: the arguments a manifest would address it
 * with, and a mount of the real component in the state where it is on screen.
 *
 * `args` is empty for the targets whose name is already an address. For the
 * entity targets it carries the same selector a manifest writes, so this proves
 * the whole path — manifest argument, `data-tutorial-target-key`, selector —
 * rather than only that some element carries the target name.
 */
interface TargetCase {
  args: Record<string, string>;
  render: () => void | Promise<void>;
}

const LOAD_BLOCK = {
  name: "Load Data",
  type_name: "load_data",
  base_category: "io",
  description: "Reads one file from disk.",
  input_ports: [],
  output_ports: [{ name: "data", direction: "output", accepted_types: ["DataFrame"] }],
} as unknown as Parameters<typeof BlockPalette>[0]["blocks"][number];

/** Mount the Plots tab with a list the API would have returned. */
async function renderPlotsTabWith(plots: unknown[]): Promise<void> {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, status: 200, json: async () => ({ plots }) })),
  );
  useAppStore.setState({ workflowId: "main" });
  render(<PlotsTab />);
  await screen.findByTestId(`plot-card-${(plots[0] as { plot_id: string }).plot_id}`);
}

const RENDERERS: Record<HighlightTarget, TargetCase> = {
  palette_block: {
    args: { block_type: "load_data" },
    render: () => {
      render(
        <BlockPalette
          blocks={[LOAD_BLOCK]}
          collapsed={false}
          onAddBlock={vi.fn()}
          onReload={vi.fn()}
          onSearch={vi.fn()}
          search=""
        />,
      );
    },
  },

  node: {
    args: { block_type: "load_data" },
    render: () => {
      renderNode({ blockType: "load_data", label: "Load Data" });
    },
  },

  plot_card: {
    args: { plot_id: "normalized_activity" },
    render: () =>
      renderPlotsTabWith([
        {
          plot_id: "normalized_activity",
          title: "Normalized activity",
          node_id: "n1",
          port: "normalized",
          broken: false,
        },
      ]),
  },

  block_palette: {
    args: {},
    render: () => {
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
  },

  canvas: {
    args: {},
    render: () => {
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
  },

  run_button: {
    args: {},
    render: () => {
      render(<Toolbar {...toolbarProps()} />);
    },
  },

  new_menu_button: {
    args: {},
    render: () => {
      // The trigger, not the menu: a step saying "press New" points at what is
      // on screen before the reader acts, and the menu does not exist yet.
      render(<Toolbar {...toolbarProps()} />);
    },
  },

  plots_new_button: {
    args: {},
    render: () => {
      // The button is disabled without a workflow, but a disabled button is
      // still an element the highlight can be drawn around.
      useAppStore.setState({ workflowId: "main" });
      render(<PlotsTab />);
    },
  },

  bring_in_my_work_button: {
    args: {},
    render: () => {
      // The permanent toolbar entry (#2061): the work-import level ends by
      // pointing at the control the reader will use with their own data.
      render(<Toolbar {...toolbarProps()} />);
    },
  },

  history_restore_button: {
    args: {},
    render: () => {
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
  },

  data_preview: {
    args: {},
    render: () => {
      render(<DataPreview blockOutputs={{}} selectedNodeId={null} selectedNodeLabel="" />);
    },
  },

  config_panel: {
    args: {},
    render: () => {
      // Rendered with nothing selected on purpose: a step points here to say
      // "now set its path", and the panel is the target whether or not it has
      // a block in it yet.
      render(
        <BottomPanel
          activeTab="config"
          blockOutputs={{}}
          edges={[]}
          logEntries={[]}
          onTabChange={vi.fn()}
          onUpdateConfig={vi.fn()}
          selectedNode={null}
          selectedSchema={undefined}
        />,
      );
    },
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
  it.each(HIGHLIGHT_TARGETS)("%s is carried by a real element", async (target) => {
    const testCase = RENDERERS[target];
    await testCase.render();

    const element = document.querySelector(tutorialTargetSelector(target, testCase.args));

    expect(element).not.toBeNull();
  });

  it("covers every member of the vocabulary, with nothing left over", () => {
    expect(Object.keys(RENDERERS).sort()).toEqual([...HIGHLIGHT_TARGETS].sort());
  });

  it("gives every entity target the argument the backend requires", () => {
    /*
     * The frontend half of the backend's `HIGHLIGHT_SPECS[].required`. A target
     * that needs an argument on one side and not the other resolves to nothing:
     * the manifest passes `block_type`, the selector ignores it, and the
     * highlight lands on whichever palette entry happens to be first.
     */
    expect(HIGHLIGHT_TARGET_KEYS).toEqual({
      palette_block: "block_type",
      node: "block_type",
      plot_card: "plot_id",
    });
  });

  it.each(Object.keys(HIGHLIGHT_TARGET_KEYS) as HighlightTarget[])(
    "%s addresses one element among its siblings",
    async (target) => {
      /*
       * The point of the entity targets. Rendering the same surface and asking
       * for a value nothing carries must find nothing — a selector that ignored
       * its argument would pass the test above and still point at the wrong
       * element in front of a user.
       */
      await RENDERERS[target].render();

      const wrong = document.querySelector(
        tutorialTargetSelector(target, { block_type: "nope", plot_id: "nope" }),
      );

      expect(wrong).toBeNull();
    },
  );
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

  it("declines to scroll rather than throwing when the host has no scrollIntoView", async () => {
    // The scroll runs in a requestAnimationFrame callback, where a throw is
    // uncatchable by any caller. jsdom omits the method, which makes this the
    // real check it looks like rather than a hypothetical one.
    await RENDERERS.canvas.render();
    applyStepRoute("canvas", { openBottomTab: vi.fn(), setLeftTab: vi.fn() });

    await new Promise((resolve) => setTimeout(resolve, 20));
    // Reaching here at all is the assertion: an unhandled rejection in the
    // frame callback fails the run even when every expectation passed.
    expect(document.querySelector(tutorialTargetSelector("canvas"))).not.toBeNull();
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

describe("the highlight guides without confining", () => {
  it("never takes a click away from the surface underneath it", () => {
    /*
     * The owner's 2026-08-10 ruling, held as a test because it is the whole
     * safety argument for drawing over the product at all. A target that resolves to
     * the wrong element — or a step whose target is momentarily gone — must
     * cost the user a moment of confusion, never the ability to click anything.
     * An overlay that swallowed clicks would strand them with no exit but
     * abandoning the tutorial.
     */
    render(<TargetHighlight rect={{ top: 100, left: 100, width: 200, height: 40 }} />);

    const overlay = screen.getByTestId("tutorial-highlight");

    expect(overlay.className).toContain("pointer-events-none");
    for (const child of Array.from(overlay.querySelectorAll("*"))) {
      expect(child.className).toContain("pointer-events-none");
    }
  });

  it("paints nothing at all when the step points nowhere", () => {
    /*
     * A ring around nothing is a ring in the corner of the screen with no
     * meaning, and there is nothing for it to point at. `useHighlightRect`
     * returns null for a step with no `highlight`, for a target that has not
     * rendered yet, and for one laid out to zero; all three land here.
     */
    render(<TargetHighlight rect={null} />);

    expect(screen.queryByTestId("tutorial-highlight")).not.toBeInTheDocument();
  });
});

describe("the data_types route target (#2061)", () => {
  it("routes to the left panel's Data types tab, not a bottom tab", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();

    applyStepRoute("data_types", { openBottomTab, setLeftTab });

    expect(openBottomTab).not.toHaveBeenCalled();
    expect(setLeftTab).toHaveBeenCalledWith("types");
  });
});
