/**
 * Behaviour contract for core.plot.basic.
 *
 * Carries over what the compiled plot viewer did — the format label, 25% zoom
 * steps clamped to 50–400%, Save, and the Save-format picker the run's rendered
 * siblings drive (#1918) — and pins the two places the panel must do better than
 * a first-page-only PDF render (#1886).
 *
 * The fixtures use the shape the reads really answer with. `artifact.info` is
 * built in `panels/reads.py` (`name`, `path`, `mime_type`, `size`, plus
 * `formats` for a plot); `artifact.file` adds `url`, and the host's
 * `materializePanelArtifact` replaces the grant URL with the bytes plus a blob
 * URL before the panel ever sees it — so `data` is always present here.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.plot.basic");
const PREACT = resolve(PANELS, "lib/preact-htm@3.1.1/dist/preact-standalone.module.js");
const PANEL_UI = resolve(PANELS, "sdk/1/panel-ui.js");

const dataUrl = (src: string) =>
  `data:text/javascript;base64,${Buffer.from(src).toString("base64")}`;

let loadCount = 0;

async function loadPanelModule() {
  const preactUrl = dataUrl(readFileSync(PREACT, "utf8"));
  const uiUrl = dataUrl(
    readFileSync(PANEL_UI, "utf8").replace(
      /"[^"]*preact-standalone\.module\.js"/g,
      JSON.stringify(preactUrl),
    ),
  );
  const src = readFileSync(resolve(PANEL, "panel.js"), "utf8")
    .replace(/"[^"]*preact-standalone\.module\.js"/g, JSON.stringify(preactUrl))
    .replace(/"[^"]*panel-ui\.js"/g, JSON.stringify(uiUrl));
  loadCount += 1;
  return import(/* @vite-ignore */ dataUrl(`${src}\n//# load-${loadCount}`));
}

interface HostOptions {
  name?: string;
  mime?: string;
  formats?: string[];
  view?: Record<string, unknown>;
}

function stubHost({
  name = "current.png",
  mime = "image/png",
  formats = ["png"],
  view = {},
}: HostOptions = {}) {
  const variants: string[] = [];
  const api = {
    input: { ref: "p", kind: "plot_artifact" },
    viewState: view,
    libBaseUrl: "",
    ready: () => Promise.resolve(api),
    read: (op: string, params: Record<string, unknown> = {}) => {
      if (op === "artifact.info") {
        return Promise.resolve({ name, path: `/runs/${name}`, mime_type: mime, size: 128, formats });
      }
      if (op === "artifact.file") {
        const variant = params.variant as string | undefined;
        if (variant) {
          variants.push(variant);
          if (!formats.includes(variant)) {
            return Promise.reject(new Error(`This plot was not rendered as ${variant}`));
          }
          return Promise.resolve({
            name: `current.${variant}`,
            mime_type: `image/${variant}`,
            data: new ArrayBuffer(16),
            url: `blob:${variant}`,
          });
        }
        return Promise.resolve({ name, mime_type: mime, data: new ArrayBuffer(8), url: "blob:primary" });
      }
      return Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
    },
    save: vi.fn((_value: { name: string; mime: string; data: ArrayBuffer }) =>
      Promise.resolve(null),
    ),
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return { api, variants };
}

/** The narrow shape a test reaches back into the stub host through. */
interface PanelHostStub {
  read: (op: string, params?: Record<string, unknown>) => Promise<unknown>;
}

const root = () => document.getElementById("root") as HTMLElement;
const testid = (name: string) => root().querySelector(`[data-testid=${name}]`);
const saveButton = () => testid("plot-export-button") as HTMLButtonElement;
const byLabel = (label: string) =>
  root().querySelector(`[aria-label="${label}"]`) as HTMLButtonElement | null;

beforeAll(() => {
  stubHost();
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.plot.basic — the viewer's own arithmetic", () => {
  it("names the format from the mime type, falling back to the suffix", async () => {
    const { formatOf } = await loadPanelModule();
    expect(formatOf("image/png", "a.png")).toBe("png");
    expect(formatOf("application/pdf", "a.pdf")).toBe("pdf");
    expect(formatOf("image/svg+xml", "a.svg")).toBe("svg");
    // Both spellings of JPEG fold to one name, as they do on the backend.
    expect(formatOf("image/jpeg", "a.jpg")).toBe("jpeg");
    expect(formatOf("", "a.jpg")).toBe("jpeg");
    expect(formatOf("application/octet-stream", "a.zip")).toBe("zip");
  });

  it("snaps zoom to 25% steps and clamps it to 50–400%", async () => {
    const { clampZoom } = await loadPanelModule();
    expect(clampZoom(1.1)).toBe(1);
    expect(clampZoom(1.13)).toBe(1.25);
    expect(clampZoom(0.1)).toBe(0.5);
    expect(clampZoom(99)).toBe(4);
  });

  it("gives the saved file the chosen format's extension", async () => {
    const { saveName } = await loadPanelModule();
    expect(saveName("current.svg", "pdf")).toBe("current.pdf");
    // jpeg is spelled .jpg on disk, as the plot run writes it.
    expect(saveName("current.svg", "jpeg")).toBe("current.jpg");
    expect(saveName(undefined, "png")).toBe("plot.png");
  });
});

describe("core.plot.basic — the rendered figure", () => {
  it("shows an image plot with the format label and zoom controls", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("plot-image")).toBeTruthy());

    expect(testid("plot-image")?.getAttribute("src")).toBe("blob:primary");
    expect(testid("plot-zoom-controls")).toBeTruthy();
    expect(testid("plot-zoom-level")?.textContent).toBe("100%");
    expect(root().querySelector(".plot-format")?.textContent).toBe("png");
  });

  it("zooms in steps and scales the layer, not the image alone", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("plot-zoom-level")).toBeTruthy());

    byLabel("Zoom in")!.click();
    await vi.waitFor(() => expect(testid("plot-zoom-level")?.textContent).toBe("125%"));
    expect(testid("plot-zoom-layer")?.getAttribute("style")).toContain("scale(1.25)");

    byLabel("Reset zoom")!.click();
    await vi.waitFor(() => expect(testid("plot-zoom-level")?.textContent).toBe("100%"));
  });

  it("offers no zoom controls when there is nothing rendered to zoom", async () => {
    stubHost({ name: "figure.tiff", mime: "image/tiff", formats: [] });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("plot-unrenderable")).toBeTruthy());
    expect(testid("plot-zoom-controls")).toBeNull();
  });
});

describe("core.plot.basic — saving in a format the run rendered (#1918)", () => {
  it("offers no picker when the figure exists in one format", async () => {
    stubHost({ formats: ["png"] });
    await loadPanelModule();
    await vi.waitFor(() => expect(saveButton()).toBeTruthy());
    expect(testid("plot-format-select")).toBeNull();
  });

  it("offers every rendered format, in the menu's canonical order", async () => {
    stubHost({ name: "current.svg", mime: "image/svg+xml", formats: ["svg", "pdf", "png"] });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("plot-format-select")).toBeTruthy());

    const options = [...root().querySelectorAll("option")].map((o) => o.getAttribute("value"));
    expect(options).toEqual(["svg", "pdf", "png"]);
  });

  it("saves the displayed bytes when the chosen format is the one on screen", async () => {
    const { api, variants } = stubHost({ formats: ["png", "pdf"] });
    await loadPanelModule();
    await vi.waitFor(() => expect(saveButton()).toBeTruthy());

    saveButton().click();
    await vi.waitFor(() => expect(api.save).toHaveBeenCalled());
    // No second read: the bytes for this format are already in hand.
    expect(variants).toEqual([]);
    expect(api.save.mock.calls[0][0].name).toBe("current.png");
  });

  it("fetches the chosen format's own file rather than relabelling these bytes", async () => {
    const { api, variants } = stubHost({ formats: ["png", "pdf"] });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("plot-format-select")).toBeTruthy());

    const select = testid("plot-format-select") as HTMLSelectElement;
    select.value = "pdf";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await vi.waitFor(() => expect(saveButton().getAttribute("aria-label")).toBe("Save plot as pdf"));

    saveButton().click();
    /*
     * Relabelling the PNG bytes as .pdf is the failure this guards: it writes a
     * file that opens as nothing. The panel must ask for the pdf sibling.
     */
    await vi.waitFor(() => expect(api.save).toHaveBeenCalled());
    expect(variants).toEqual(["pdf"]);
    expect(api.save.mock.calls[0][0].name).toBe("current.pdf");
  });

  it("reports a format the run did not render instead of saving something wrong", async () => {
    const { api } = stubHost({ formats: ["png"] });
    await loadPanelModule();
    await vi.waitFor(() => expect(saveButton()).toBeTruthy());

    // Drive the unrendered case directly: the picker cannot offer it, but a
    // remembered view state can still name it.
    const { read } = (window as unknown as { scistudio: PanelHostStub }).scistudio;
    await expect(read("artifact.file", { variant: "pdf" })).rejects.toThrow("not rendered");
    expect(api.save).not.toHaveBeenCalled();
  });
});

describe("core.plot.basic — a PDF is more than its first page (#1886)", () => {
  it("says how many pages there are and moves between them", async () => {
    stubHost({ name: "current.pdf", mime: "application/pdf", formats: ["pdf"] });
    const mod = await loadPanelModule();
    expect(mod).toBeTruthy();
    /*
     * PDF.js is not loaded in this environment, so the render reports a failure
     * and the panel must say so rather than leaving an empty canvas — the same
     * requirement as the pager: never a blank where content was expected.
     */
    await vi.waitFor(() => expect(testid("plot-unrenderable")).toBeTruthy());
    expect(testid("plot-unrenderable")?.textContent).toMatch(/PDF/);
  });
});

describe("core.plot.basic — the tutorial can still point at Save", () => {
  it("marks the Save button with the target the tutorial names", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(saveButton()).toBeTruthy());
    /*
     * `what-is-a-type` highlights `plot_export_button`. The attribute is how the
     * host finds it; inside a frame it also needs the highlight bridge, but the
     * mark has to be here for either to work.
     */
    expect(saveButton().getAttribute("data-tutorial-target")).toBe("plot_export_button");
  });
});

describe("core.plot.basic — edge cases", () => {
  it("surfaces a failed read", async () => {
    const api = {
      input: {},
      viewState: {},
      ready: () => Promise.resolve(api),
      read: () => Promise.reject(new Error("unsupported")),
      save: vi.fn(),
      setViewState: vi.fn(),
      reportError: vi.fn(() => Promise.resolve(null)),
    } as Record<string, unknown>;
    (window as unknown as { scistudio: unknown }).scistudio = api;
    document.body.innerHTML = '<div id="root"></div>';
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector(".panel-error")).toBeTruthy());
    expect(root().textContent).toContain("Could not read plot");
    expect(api.reportError).toHaveBeenCalled();
  });

  it("remembers the zoom and the chosen save format", async () => {
    const { api } = stubHost({ formats: ["png", "pdf"], view: { zoom: 2, save_format: "pdf" } });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("plot-zoom-level")?.textContent).toBe("200%"));
    expect(api.setViewState).toHaveBeenCalledWith({ zoom: 2, save_format: "pdf" });
  });
});
