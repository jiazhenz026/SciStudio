// ADR-053 §6.2 FR-025 — E1, E2 and E5 share one implementation.
//
// The assertion that matters is not "each surface has a button"; it is that
// each surface's button is *the same component* driving *the same action*.
// `runPromotion` is the app's only call into `promoteToUserLibrary`, so
// mocking it and watching what each entry point hands it proves there is one
// implementation behind all three — and that they agree on the item.
//
// FR-019 is asserted here too, on the surfaces that render it: a built-in,
// packaged, or already-in-library item shows **no control at all**, not a
// disabled one.

import { ReactFlowProvider } from "@xyflow/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as CodeApi from "../../../lib/api/code";
import { useAppStore } from "../../../store";
import { resetAppStore } from "../../../testUtils";
import type { BlockNodeData } from "../../../types/ui";
import type { BlockSummary, TypeSummary } from "../../../types/api";
import { BlockPalette } from "../../BlockPalette";
import { BlockNode } from "../../nodes/BlockNode";
import { POPOVER_OPEN_DELAY_MS } from "../../palette/hoverPopover";
import { FileOperationsGroup } from "../../Toolbar.parts/FileOperationsGroup";
import { TypePalette } from "../../TypePalette";
import { makeBlock, makeType } from "./fixtures";

const runPromotion = vi.hoisted(() => vi.fn(async (_item: unknown) => undefined));
vi.mock("../runPromotion", () => ({ runPromotion }));

const listTypes = vi.fn();
vi.mock("../../../lib/api/code", async (importOriginal) => {
  const actual = await importOriginal<typeof CodeApi>();
  return { codeApi: { ...actual.codeApi, listTypes: () => listTypes() } };
});

const projectBlock = makeBlock({
  type_name: "normalize",
  name: "Normalize",
  origin: "project",
});
const builtinBlock = makeBlock({ type_name: "load_data", name: "Load", origin: "builtin" });
const libraryBlock = makeBlock({ type_name: "my_util", name: "MyUtil", origin: "user" });
const packagedBlock = makeBlock({
  type_name: "imaging.seg",
  name: "Segment",
  origin: "package",
  package_name: "Imaging",
});

const projectTypeSummary = makeType({
  name: "Spectrum",
  origin: "project",
  file_path: "/home/dev/proj/types/spectrum.py",
});
const coreTypeSummary = makeType({ name: "Array", origin: "core" });

function actions(): HTMLElement[] {
  return screen.queryAllByTestId("promote-to-library-action");
}

beforeEach(() => {
  resetAppStore();
  runPromotion.mockClear();
  listTypes.mockResolvedValue({ types: [] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// ---------------------------------------------------------------- E1 -------

function openEditorTab(filePath: string, blocks: BlockSummary[] = [projectBlock]) {
  useAppStore.setState({
    blocks,
    tabs: [
      {
        kind: "file",
        id: `file:${filePath}`,
        filePath,
        displayName: filePath,
        language: "python",
        content: "",
        contentLoadedAt: 0,
        dirty: false,
        readOnly: false,
      },
    ],
    activeTabId: `file:${filePath}`,
  });
}

function renderToolbar() {
  return render(
    <TooltipProvider>
      <FileOperationsGroup
        currentProject={{ id: "p1", name: "Proj" } as never}
        isFileTab
        onImport={vi.fn()}
        onInstallPackage={vi.fn()}
        onNewWorkflow={vi.fn()}
        onSave={vi.fn()}
        onSaveAs={vi.fn()}
      />
    </TooltipProvider>,
  );
}

describe("E1 — block source editor toolbar", () => {
  it("offers promotion for the open project drop-in block", () => {
    openEditorTab("blocks/normalize.py");
    renderToolbar();

    const button = screen.getByTestId("promote-to-library-action");
    expect(button).toHaveAttribute("data-entry-point", "E1");

    fireEvent.click(button);
    expect(runPromotion).toHaveBeenCalledWith(
      expect.objectContaining({
        target: "blocks",
        origin: "project",
        source: { from: "projectFile", path: "blocks/normalize.py" },
      }),
    );
  });

  it("renders nothing when the open file is not a drop-in", () => {
    openEditorTab("notes/todo.md");
    renderToolbar();
    expect(actions()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------- E2 -------

function renderNode(summary?: BlockSummary) {
  const data: BlockNodeData = {
    label: summary?.name ?? "Node",
    blockType: summary?.type_name ?? "node",
    category: "process",
    inputPorts: [],
    outputPorts: [],
    config: {},
    summary,
  };
  return render(
    <ReactFlowProvider>
      <BlockNode
        {...({
          id: "n1",
          type: "block",
          data,
          selected: true,
          isConnectable: false,
          positionAbsoluteX: 0,
          positionAbsoluteY: 0,
          zIndex: 0,
        } as Parameters<typeof BlockNode>[0])}
      />
    </ReactFlowProvider>,
  );
}

describe("E2 — canvas node action menu", () => {
  it("offers promotion for a project-tier node, in the existing menu", () => {
    renderNode(projectBlock);
    const button = screen.getByTestId("promote-to-library-action");
    expect(button).toHaveAttribute("data-entry-point", "E2");
    expect(screen.getByTestId("node-action-toolbar")).toContainElement(button);

    fireEvent.click(button);
    expect(runPromotion).toHaveBeenCalledWith(
      expect.objectContaining({
        target: "blocks",
        origin: "project",
        source: { from: "block", blockType: "normalize" },
      }),
    );
  });

  it.each([
    ["built-in", builtinBlock],
    ["packaged", packagedBlock],
    ["already in the library", libraryBlock],
  ])("hides — not disables — the action for a %s block (FR-019)", (_label, block) => {
    renderNode(block);
    expect(actions()).toHaveLength(0);
    // The rest of the node menu is untouched.
    expect(screen.getByTestId("node-action-toolbar")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- E5 -------

function hoverFirstTile(testId: string) {
  vi.useFakeTimers();
  const tile = screen.getAllByTestId(testId)[0];
  fireEvent.mouseEnter(tile);
  act(() => {
    vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS + 1);
  });
  vi.useRealTimers();
}

describe("E5 — palette hover popovers", () => {
  it("offers promotion in the block popover's action row", () => {
    render(
      <BlockPalette
        blocks={[projectBlock]}
        collapsed={false}
        onAddBlock={vi.fn()}
        onReload={vi.fn()}
        onSearch={vi.fn()}
        search=""
      />,
    );
    hoverFirstTile("palette-block-tile");

    const button = screen.getByTestId("promote-to-library-action");
    expect(button).toHaveAttribute("data-entry-point", "E5");
    expect(screen.getByTestId("palette-popover-actions")).toContainElement(button);

    fireEvent.click(button);
    expect(runPromotion).toHaveBeenCalledWith(
      expect.objectContaining({
        target: "blocks",
        source: { from: "block", blockType: "normalize" },
      }),
    );
  });

  it.each([
    ["built-in", builtinBlock],
    ["packaged", packagedBlock],
    ["already in the library", libraryBlock],
  ])("hides the block action row entirely for a %s block (FR-019)", (_label, block) => {
    render(
      <BlockPalette
        blocks={[block]}
        collapsed={false}
        onAddBlock={vi.fn()}
        onReload={vi.fn()}
        onSearch={vi.fn()}
        search=""
      />,
    );
    hoverFirstTile("palette-block-tile");
    expect(screen.getByTestId("block-detail-popover")).toBeInTheDocument();
    expect(actions()).toHaveLength(0);
    expect(screen.queryByTestId("palette-popover-actions")).not.toBeInTheDocument();
  });

  function renderTypes(types: TypeSummary[]) {
    render(<TypePalette />);
    act(() => {
      useAppStore.getState().setTypes(types);
    });
  }

  it("offers promotion in the type popover's action row", () => {
    renderTypes([projectTypeSummary]);
    hoverFirstTile("palette-type-tile");

    const button = screen.getByTestId("promote-to-library-action");
    expect(button).toHaveAttribute("data-entry-point", "E5");
    expect(screen.getByTestId("palette-popover-actions")).toContainElement(button);

    fireEvent.click(button);
    expect(runPromotion).toHaveBeenCalledWith(
      expect.objectContaining({
        target: "types",
        source: { from: "projectFile", path: "types/spectrum.py" },
      }),
    );
  });

  it("hides the type action row for a core type (FR-019)", () => {
    renderTypes([coreTypeSummary]);
    hoverFirstTile("palette-type-tile");
    expect(screen.getByTestId("type-detail-popover")).toBeInTheDocument();
    expect(actions()).toHaveLength(0);
  });
});

// ------------------------------------------------------- FR-025 ------------

describe("FR-025 — one implementation behind every entry point", () => {
  it("routes E1, E2 and E5 through the same action for the same block", () => {
    openEditorTab("blocks/normalize.py");
    renderToolbar();
    fireEvent.click(screen.getByTestId("promote-to-library-action"));
    cleanup();

    renderNode(projectBlock);
    fireEvent.click(screen.getByTestId("promote-to-library-action"));
    cleanup();

    render(
      <BlockPalette
        blocks={[projectBlock]}
        collapsed={false}
        onAddBlock={vi.fn()}
        onReload={vi.fn()}
        onSearch={vi.fn()}
        search=""
      />,
    );
    hoverFirstTile("palette-block-tile");
    fireEvent.click(screen.getByTestId("promote-to-library-action"));

    expect(runPromotion).toHaveBeenCalledTimes(3);
    for (const call of runPromotion.mock.calls) {
      expect(call[0]).toMatchObject({ target: "blocks", kind: "block", origin: "project" });
    }
  });
});
