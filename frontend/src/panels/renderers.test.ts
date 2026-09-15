import { afterEach, describe, expect, it, vi } from "vitest";
import { loadRenderers } from "./rendererTestModules";

let unmount: (() => void) | undefined;
afterEach(() => {
  unmount?.();
  document.body.innerHTML = "";
});

async function mount(name: string, props: Record<string, unknown>) {
  delete (window as unknown as { scistudio?: unknown }).scistudio;
  const components = await loadRenderers();
  const root = document.createElement("div");
  document.body.append(root);
  const update = (next: Record<string, unknown>) =>
    components.render(components.h(components[name], next), root);
  update(props);
  unmount = () => components.render(null, root);
  return { root, update, components };
}

describe("core renderers composed without a SciStudio host", () => {
  it("renders computed ND data without flattening away the shape, with controlled slice changes", async () => {
    const data = new Float64Array([0, 1, 2, 3, 4, 5, 6, 7]);
    const onSliceChange = vi.fn();
    const props = { data, shape: [2, 2, 2], indices: { 0: 0 }, onSliceChange };
    const { root, update } = await mount("ArrayView", props);
    expect(root.querySelector('[data-testid="array-cell-1-1"]')?.textContent).toBe("3");
    const input = root.querySelector('[data-testid="array-slice-input-0"]') as HTMLInputElement;
    input.value = "1";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    expect(onSliceChange).toHaveBeenCalledWith(0, 1);
    update({ ...props, indices: { 0: 1 } });
    expect(root.querySelector('[data-testid="array-cell-1-1"]')?.textContent).toBe("7");
    expect(root.querySelector('[data-testid="array-info"]')?.textContent).toContain(
      "shape [2, 2, 2]",
    );
  });

  it("renders a raw vector and computed matrix with distinct non-finite values", async () => {
    const { root, update } = await mount("ArrayView", { data: [3, 4, 5] });
    expect(root.querySelectorAll("tbody tr[data-row]")).toHaveLength(1);
    update({
      data: [
        [NaN, Infinity],
        [-Infinity, 2],
      ],
    });
    expect(root.querySelector('[data-testid="array-cell-0-0"]')?.textContent).toBe("NaN");
    expect(root.querySelector('[data-testid="array-cell-0-1"]')?.textContent).toBe("∞");
    expect(root.querySelector('[data-testid="array-cell-1-0"]')?.textContent).toBe("-∞");
    expect(root.querySelector(".array-heatmap")).toBeTruthy();
  });

  it("reports mismatched shape and ragged data rather than reinterpreting it", async () => {
    const { root, update } = await mount("ArrayView", { data: [1, 2], shape: [3] });
    expect(root.textContent).toContain("shape does not match");
    update({ data: [[1], [2, 3]] });
    expect(root.textContent).toContain("rectangular");
  });

  it("emits controlled sort and page requests from the same table presentation", async () => {
    const onQueryChange = vi.fn();
    const query = { page: 1, pageSize: 1, sortBy: null, sortDir: null };
    const { root } = await mount("DataFrameView", {
      data: { columns: ["value"], rows: [{ value: 12 }], total: 3 },
      query,
      onQueryChange,
    });
    (root.querySelector("th") as HTMLElement).click();
    expect(onQueryChange).toHaveBeenCalledWith({
      ...query,
      page: 1,
      sortBy: "value",
      sortDir: "asc",
    });
    (root.querySelector('[aria-label="Next page"]') as HTMLElement).click();
    expect(onQueryChange).toHaveBeenCalledWith({ ...query, page: 2 });
  });

  it("switches series mode only through the caller and plots with an injected Plotly instance", async () => {
    const plotly = { react: vi.fn(), purge: vi.fn() };
    const onModeChange = vi.fn();
    const props = { data: { values: [3, 5], index: [0, 1] }, mode: "table", onModeChange, plotly };
    const { root, update } = await mount("SeriesView", props);
    expect(root.querySelector('[data-testid="series-table"]')).toBeTruthy();
    (root.querySelector("button") as HTMLElement).click();
    expect(onModeChange).toHaveBeenCalledWith("chart");
    update({ ...props, mode: "chart" });
    expect(plotly.react).toHaveBeenCalled();
  });

  it("renders text, artifact and fallback metadata from supplied values", async () => {
    const { components, root } = await mount("TextView", { text: "computed result" });
    expect(root.textContent).toContain("computed result");
    components.render(
      components.h(components.ArtifactView, {
        info: { name: "result.png", mime_type: "image/png" },
        url: "data:image/png;base64,AA==",
      }),
      root,
    );
    expect(root.querySelector("img")?.getAttribute("alt")).toBe("result.png");
    components.render(
      components.h(components.MetadataView, {
        meta: { type_chain: ["DataObject", "CustomResult"], metadata: { answer: 42 } },
      }),
      root,
    );
    expect(root.textContent).toContain("CustomResult");
    expect(root.textContent).toContain('"answer": 42');
  });

  it("routes collection and composite selections through caller callbacks", async () => {
    const onOpen = vi.fn();
    const item = { ref: "ref-1", display_name: "Result" };
    const { components, root } = await mount("CollectionView", { items: [item], onOpen });
    (root.querySelector('[data-testid="collection-item-0"]') as HTMLElement).click();
    expect(onOpen).toHaveBeenCalledWith("ref-1", item);
    const slot = { name: "signal", ref: "ref-2", type_name: "Array" };
    components.render(components.h(components.CompositeView, { slots: [slot], onOpen }), root);
    (root.querySelector('[data-testid="composite-slot-signal"]') as HTMLElement).click();
    expect(onOpen).toHaveBeenCalledWith("ref-2", slot);
  });

  it("controls figure zoom and save without host reads or downloads", async () => {
    const onZoom = vi.fn();
    const onSave = vi.fn();
    const { root } = await mount("PlotView", {
      info: { name: "figure.png", formats: ["png", "pdf"] },
      file: { mime_type: "image/png", url: "data:image/png;base64,AA==" },
      zoom: 1,
      onZoom,
      onSave,
      saveFormat: "pdf",
    });
    (root.querySelector('[aria-label="Zoom in"]') as HTMLElement).click();
    expect(onZoom).toHaveBeenCalledWith(1.25);
    (root.querySelector('[data-testid="plot-export-button"]') as HTMLElement).click();
    expect(onSave).toHaveBeenCalledWith("pdf");
  });
});
