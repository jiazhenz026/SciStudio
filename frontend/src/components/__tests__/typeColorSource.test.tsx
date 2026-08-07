// The canvas colour source switch (ADR-053 §7.1, spec §12.2 step 12).
//
// FR-066 — a type declaring `ui_color` renders in that colour on BOTH a
//   palette tile and a canvas port, because both read the types listing.
// FR-067 — ports render the existing resolution before the listing lands and
//   neither flash nor re-layout when it does.
// FR-052 — a malformed declaration warns and falls through without breaking
//   either surface.
//
// The two surfaces are rendered in one file on purpose: FR-066 is a claim
// about them agreeing, and a test that exercised only one of them could not
// fail the way the drift it prevents would.

import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReactFlowProvider } from "@xyflow/react";

import { resolveTypeColor, resetDeclaredColorWarnings } from "../../config/typeColorMap";
import { useAppStore } from "../../store";
import { resetTypeCatalogLoader } from "../../store/useTypeCatalog";
import { resetAppStore } from "../../testUtils";
import type { BlockNodeData } from "../../types/ui";
import type { BlockPortResponse, BlockSchemaResponse, TypeSummary } from "../../types/api";
import { makeType } from "../TypePalette.parts/__tests__/fixtures";
import { BlockNode } from "../nodes/BlockNode";
import { TypePalette } from "../TypePalette";

const listTypes = vi.fn();
vi.mock("../../lib/api/code", () => ({
  codeApi: {
    listTypes: () => listTypes(),
  },
}));

const DECLARED_HEX = "#4f8ef7";
const DECLARED_RGB = "rgb(79, 142, 247)";

const declaredType = makeType({
  name: "Declared",
  base_type: "Array",
  origin: "project",
  ui_color: DECLARED_HEX,
});
const plainType = makeType({ name: "Array" });

function port(name: string, accepted: string[]): BlockPortResponse {
  return {
    name,
    direction: "output",
    accepted_types: accepted,
    required: true,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

function schema(overrides: Partial<BlockSchemaResponse> = {}): BlockSchemaResponse {
  return {
    name: "Test Block",
    type_name: "test_block",
    base_category: "process",
    subcategory: "",
    description: "",
    version: "1.0",
    input_ports: [],
    output_ports: [],
    config_schema: { type: "object", properties: {} },
    // The hierarchy still carries `base_type` and never a fill colour — FR-066
    // is exactly the claim that colour no longer travels on this payload.
    type_hierarchy: [
      { name: "Array", base_type: "DataObject", description: "" },
      { name: "Declared", base_type: "Array", description: "" },
    ],
    dynamic_ports: null,
    direction: null,
    ...overrides,
  };
}

function renderNodeWithPorts(ports: BlockPortResponse[]) {
  const data: BlockNodeData = {
    label: "Test Block",
    blockType: "test_block",
    category: "process",
    inputPorts: [],
    outputPorts: ports,
    config: {},
    schema: schema({ output_ports: ports }),
  };
  const props = {
    id: "node-1",
    type: "block",
    data,
    selected: false,
    isConnectable: false,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
  } as Parameters<typeof BlockNode>[0];
  return render(
    <ReactFlowProvider>
      <BlockNode {...props} />
    </ReactFlowProvider>,
  );
}

function handleFor(container: HTMLElement, portName: string): HTMLElement {
  const handle = container.querySelector(`[data-handleid="${portName}"]`);
  if (!(handle instanceof HTMLElement)) {
    throw new Error(`no handle for ${portName}`);
  }
  return handle;
}

function landCatalogue(types: TypeSummary[]): void {
  act(() => {
    useAppStore.getState().setTypes(types);
  });
}

function tileSwatch(name: string): HTMLElement {
  const tile = screen
    .queryAllByTestId("palette-type-tile")
    .find((element) => within(element).queryByText(name) !== null);
  if (!tile) {
    throw new Error(`no tile for ${name}`);
  }
  return tile.querySelector("span[aria-hidden='true']") as HTMLElement;
}

beforeEach(() => {
  resetAppStore();
  resetTypeCatalogLoader();
  resetDeclaredColorWarnings();
  listTypes.mockResolvedValue({ types: [] });
});

afterEach(() => {
  cleanup();
  listTypes.mockReset();
  vi.restoreAllMocks();
});

describe("colour parity across palette and canvas (FR-066)", () => {
  it("renders a declared colour on both a palette tile and a canvas port", () => {
    const { container } = renderNodeWithPorts([port("out", ["Declared"])]);
    render(<TypePalette />);
    landCatalogue([plainType, declaredType]);

    expect(handleFor(container, "out").style.backgroundColor).toBe(DECLARED_RGB);
    expect(tileSwatch("Declared").style.backgroundColor).toBe(DECLARED_RGB);
  });

  it("keeps an undeclared type identical on both surfaces", () => {
    const { container } = renderNodeWithPorts([port("out", ["Array"])]);
    render(<TypePalette />);
    landCatalogue([plainType, declaredType]);

    const expected = "rgb(59, 130, 246)"; // typeColorMap.Array, unchanged
    expect(handleFor(container, "out").style.backgroundColor).toBe(expected);
    expect(tileSwatch("Array").style.backgroundColor).toBe(expected);
  });

  it("does not read a colour off type_hierarchy (FR-066 rejects a second supply point)", () => {
    // `Declared` declares nothing in this catalogue, so despite being present
    // in `type_hierarchy` it must resolve through the ordinary precedence —
    // here, its `base_type` Array.
    const { container } = renderNodeWithPorts([port("out", ["Declared"])]);
    landCatalogue([plainType, makeType({ name: "Declared", base_type: "Array" })]);
    expect(handleFor(container, "out").style.backgroundColor).toBe("rgb(59, 130, 246)");
  });
});

describe("the loading window (FR-067)", () => {
  it("renders the existing resolution before the listing lands", () => {
    const { container } = renderNodeWithPorts([
      port("plain", ["Array"]),
      port("declaring", ["Declared"]),
    ]);
    expect(useAppStore.getState().typesLoaded).toBe(false);

    // Both ports show exactly what they showed before ADR-053 — no
    // placeholder, no grey, no "unknown" colour.
    expect(handleFor(container, "plain").style.backgroundColor).toBe("rgb(59, 130, 246)");
    expect(handleFor(container, "declaring").style.backgroundColor).toBe(
      `rgb(59, 130, 246)`, // resolved through base_type Array, as today
    );
    expect(resolveTypeColor(["Declared"], schema().type_hierarchy)).toBe("#3b82f6");
  });

  it("does not flash an undeclared port when the listing lands", () => {
    const { container } = renderNodeWithPorts([port("plain", ["Array"])]);
    const before = handleFor(container, "plain").style.backgroundColor;
    landCatalogue([plainType, declaredType]);
    expect(handleFor(container, "plain").style.backgroundColor).toBe(before);
  });

  it("does not re-layout any port when the listing lands", () => {
    const { container } = renderNodeWithPorts([
      port("plain", ["Array"]),
      port("declaring", ["Declared"]),
    ]);
    const geometry = (name: string) => {
      const style = handleFor(container, name).style;
      return { top: style.top, left: style.left, right: style.right };
    };
    const before = { plain: geometry("plain"), declaring: geometry("declaring") };

    landCatalogue([plainType, declaredType]);

    // Colour is paint-only: port Y comes from `portRailOffset` and the rail
    // side from the direction, neither of which the catalogue touches.
    expect(geometry("plain")).toEqual(before.plain);
    expect(geometry("declaring")).toEqual(before.declaring);
    // ...and the declaring port did take its declared colour, so the
    // no-re-layout assertion above is not vacuous.
    expect(handleFor(container, "declaring").style.backgroundColor).toBe(DECLARED_RGB);
  });
});

describe("a malformed declaration (FR-052)", () => {
  it("warns and falls through without breaking either surface", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { container } = renderNodeWithPorts([port("out", ["Declared"])]);
    render(<TypePalette />);
    landCatalogue([
      plainType,
      makeType({ name: "Declared", base_type: "Array", ui_color: "#nope" }),
    ]);

    expect(warn).toHaveBeenCalled();
    // Both surfaces fall through to the next precedence level (base_type
    // Array) and keep rendering.
    expect(handleFor(container, "out").style.backgroundColor).toBe("rgb(59, 130, 246)");
    expect(tileSwatch("Declared").style.backgroundColor).toBe("rgb(59, 130, 246)");
  });
});
