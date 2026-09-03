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
import { CollectionViewer } from "../DataPreview.parts/coreViewers";
import { PlotViewer } from "../DataPreview.parts/PlotViewer";
import { DataPreview } from "../DataPreview";
import { PermissionModePicker } from "../AIChat/SetupScreen.parts/PermissionModePicker";
import { ProviderPicker } from "../AIChat/SetupScreen.parts/ProviderPicker";
import { PanelPalette } from "../PanelPalette";
import { ProjectTree } from "../ProjectTree";
import { TypePalette } from "../TypePalette";
import { WorkflowPanel } from "../WorkflowPanel";
import {
  BOTTOM_TAB_TUTORIAL_NAMES,
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
import { RunsList } from "../Lineage/RunsList";
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

/** One finished run, which is what History holds by the time a step points at it. */
const COMPLETED_RUN = {
  run_id: "r1",
  workflow_id: "main",
  workflow_git_commit: "abc1234",
  workflow_dirty: false,
  started_at: "2026-05-15T14:30:00Z",
  finished_at: "2026-05-15T14:30:12Z",
  status: "completed" as const,
  triggered_by: "user" as const,
  parent_run_id: null,
  execute_from_block_id: null,
  block_count: 3,
  duration_ms: 12_000,
};

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

  // The Data section of the left panel. `ProjectTree` renders both it and the
  // Project tree; only the Data one is given a tutorial target, which is why
  // the prop is passed here rather than hard-coded in the component.
  data: {
    args: {},
    render: () => {
      render(
        <ProjectTree
          projectId="p1"
          projectPath="/tmp/p1"
          title="Data"
          rootPath="data"
          tutorialTarget="data"
          onLoadWorkflow={vi.fn()}
          onReloadBlocks={vi.fn()}
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

  workflow_list: {
    args: {},
    render: () => {
      /*
       * The panel as a whole. Core tutorial 1's opening points here to say
       * where a project keeps its workflows, so the ring goes round the list
       * rather than round one row — and an empty list is still that list.
       */
      vi.stubGlobal(
        "fetch",
        vi.fn(() => Promise.resolve({ ok: true, status: 200, json: async () => [] })),
      );
      render(<WorkflowPanel activeWorkflowId={null} onOpenWorkflow={vi.fn()} projectId="p1" />);
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

  type_palette: {
    args: {},
    render: () => {
      /*
       * Empty or not, for the same reason as the Previewers list below: the
       * step pointing here is about where types live, and tutorial 2's first
       * step points at it precisely to show that the reader's type is *not*
       * there yet.
       */
      vi.stubGlobal(
        "fetch",
        vi.fn(() =>
          Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ types: [], diagnostics: [] }),
          }),
        ),
      );
      render(<TypePalette />);
    },
  },

  previewer_palette: {
    args: {},
    render: () => {
      /*
       * The list, empty or not: the step that points here is about where
       * previewers live, and a project with none installed still has the place
       * they would live. The catalogue fetch is stubbed away because what is
       * being proved is that the element carrying the target exists at all.
       */
      vi.stubGlobal(
        "fetch",
        vi.fn(() =>
          Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ previewers: [], diagnostics: [], choices: [] }),
          }),
        ),
      );
      render(<PanelPalette />);
    },
  },

  view_source_button: {
    args: {},
    render: () => {
      // Shown only with a workflow open, which is the only state a step that
      // points at it can be reached in.
      render(<Toolbar {...toolbarProps()} onViewSource={vi.fn()} />);
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

  preview_item: {
    args: { index: "0" },
    render: () => {
      // One card per item of a collection preview, keyed by position.
      render(
        <CollectionViewer
          envelope={
            {
              previewer_id: "core.collection",
              target: { kind: "block_output", ref: "out://x" },
              kind: "collection",
              payload: {
                count: 2,
                item_type: "Image",
                items: [
                  { data_ref: "a", display_name: "cells_01.tif", type_name: "Image" },
                  { data_ref: "b", display_name: "cells_02.tif", type_name: "Image" },
                ],
              },
              metadata: {},
              resources: [
                { resource_id: "item:0", params: {} },
                { resource_id: "item:1", params: {} },
              ],
            } as never
          }
          onOpenResource={vi.fn()}
        />,
      );
    },
  },

  plot_export_button: {
    args: {},
    render: () => {
      // The Save button lives in the plot panel, so the target only exists
      // once a figure is on screen — which is the only state a step pointing at
      // it can be reached in.
      render(
        <PlotViewer
          envelope={
            {
              previewer_id: "core.plot",
              target: { kind: "plot_artifact", ref: "plot://x" },
              kind: "plot",
              payload: { src: "data:image/png;base64,AA==", path: "figure.png" },
              metadata: {},
              resources: [{ resource_id: "export", params: { format: "png" } }],
            } as never
          }
          onExport={vi.fn()}
        />,
      );
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

  history_runs_list: {
    args: {},
    render: () => {
      // One run in the store, because the list renders an empty-state
      // paragraph instead of itself when there are none — and the step that
      // points here follows a run the reader has just made.
      useAppStore.setState({ runs: [COMPLETED_RUN], runsLoading: false });
      render(<RunsList />);
    },
  },

  bottom_tab: {
    // The manifest's spelling of the tab, not the `BottomTab` key: this is the
    // whole point of `BOTTOM_TAB_TUTORIAL_NAMES`, so the case addresses it the
    // way a tutorial does.
    args: { tab: "history" },
    render: () => {
      render(
        <BottomPanel
          activeTab="lineage"
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

  // #2083 — the AI Chat setup screen. Core tutorial 3 points at both of these
  // before any session is launched, which is the only moment either is on
  // screen: once a tab is running, the setup screen is gone.
  ai_provider_picker: {
    args: {},
    render: () => {
      render(
        <ProviderPicker
          tabId="t1"
          providers={[]}
          statusLoading={false}
          provider={null}
          onChange={vi.fn()}
        />,
      );
    },
  },

  ai_permission_modes: {
    args: {},
    render: () => {
      render(<PermissionModePicker tabId="t1" permissionMode={null} onChange={vi.fn()} />);
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
      preview_item: "index",
      bottom_tab: "tab",
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
        tutorialTargetSelector(target, {
          block_type: "nope",
          plot_id: "nope",
          tab: "nope",
          // A position, so "nope" is not a value it could ever carry — an index
          // past the end of the batch is.
          index: "99",
        }),
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

  it("names every tab back, so a step rings the tab it routed to", () => {
    /*
     * `BOTTOM_TAB_TUTORIAL_NAMES` is the tab strip's annotation, derived by
     * inverting the routing map. A `BottomTab` missing from it annotates its
     * button with `undefined` and a `bottom_tab` highlight naming that tab
     * silently finds nothing.
     */
    for (const [route, tab] of Object.entries(ROUTE_TARGET_BOTTOM_TABS)) {
      if (tab === null) continue;
      expect(BOTTOM_TAB_TUTORIAL_NAMES[tab]).toBe(route);
    }
    expect(Object.keys(BOTTOM_TAB_TUTORIAL_NAMES).sort()).toEqual([
      "ai",
      "config",
      "git",
      "lineage",
      "logs",
      "plots",
      "terminal",
    ]);
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
    const showCanvas = vi.fn();

    applyStepRoute("history", { openBottomTab, setLeftTab, showCanvas });

    // `openBottomTab` expands a collapsed panel; `setActiveBottomTab` would
    // change the tab behind a shut panel and look like nothing happened.
    expect(openBottomTab).toHaveBeenCalledWith("lineage");
    expect(setLeftTab).not.toHaveBeenCalled();
  });

  it("routes block_palette to the left panel's Blocks tab, not a bottom tab", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();
    const showCanvas = vi.fn();

    applyStepRoute("block_palette", { openBottomTab, setLeftTab, showCanvas });

    expect(setLeftTab).toHaveBeenCalledWith("blocks");
    expect(openBottomTab).not.toHaveBeenCalled();
    expect(ROUTE_TARGET_LEFT_TABS.block_palette).toBe("blocks");
  });

  it("declines to scroll rather than throwing when the host has no scrollIntoView", async () => {
    // The scroll runs in a requestAnimationFrame callback, where a throw is
    // uncatchable by any caller. jsdom omits the method, which makes this the
    // real check it looks like rather than a hypothetical one.
    await RENDERERS.canvas.render();
    applyStepRoute("canvas", { openBottomTab: vi.fn(), setLeftTab: vi.fn(), showCanvas: vi.fn() });

    await new Promise((resolve) => setTimeout(resolve, 20));
    // Reaching here at all is the assertion: an unhandled rejection in the
    // frame callback fails the run even when every expectation passed.
    expect(document.querySelector(tutorialTargetSelector("canvas"))).not.toBeNull();
  });

  it("switches no surface for canvas — it is already the main one", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();
    const showCanvas = vi.fn();

    applyStepRoute("canvas", { openBottomTab, setLeftTab, showCanvas });

    expect(openBottomTab).not.toHaveBeenCalled();
    expect(setLeftTab).not.toHaveBeenCalled();
  });

  it("ignores a name outside the vocabulary instead of throwing", () => {
    const openBottomTab = vi.fn();
    const setLeftTab = vi.fn();
    const showCanvas = vi.fn();

    applyStepRoute("not_a_target", { openBottomTab, setLeftTab, showCanvas });

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
    const showCanvas = vi.fn();

    applyStepRoute("data_types", { openBottomTab, setLeftTab, showCanvas });

    expect(openBottomTab).not.toHaveBeenCalled();
    expect(setLeftTab).toHaveBeenCalledWith("types");
  });
});
