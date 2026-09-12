/**
 * Behaviour contract for core.base.fallback.
 *
 * This is what a reader gets when no type-specific panel claims their object.
 * The previewer it replaces delegated to the artifact previewer, so it could
 * describe a file — path, MIME type, size — and never said what the object was;
 * an object that reached the fallback because its type had no viewer was
 * indistinguishable from an opaque blob. The type is the one thing added.
 *
 * The rest is #1886: an object here may have no stored file and no recorded
 * metadata, and a card that quietly omitted those lines would read as details
 * that failed to load rather than details that do not exist.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.base.fallback");
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

/** The `metadata` read's shape, as panels/reads.py builds it. */
function metadataRead(overrides: Record<string, unknown> = {}) {
  return {
    type_chain: ["DataObject", "Mystery"],
    metadata: { created_by: "some.block" },
    shape: null,
    dtype: null,
    sampled: false,
    truncated: false,
    complete: true,
    ...overrides,
  };
}

function stubHost(
  meta: Record<string, unknown>,
  file: Record<string, unknown> | null = null,
) {
  const api = {
    input: { ref: "o", kind: "data_ref" },
    viewState: {},
    ready: () => Promise.resolve(api),
    read: (op: string) => {
      if (op === "metadata") return Promise.resolve(meta);
      if (op === "artifact.file") {
        return file === null
          ? Promise.reject(new Error("This read requires an individual data object"))
          : Promise.resolve(file);
      }
      return Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return api;
}

const root = () => document.getElementById("root") as HTMLElement;
const testid = (name: string) => root().querySelector(`[data-testid=${name}]`);

beforeAll(() => {
  stubHost(metadataRead());
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.base.fallback — reading the record", () => {
  it("names the object by the most specific type its chain records", async () => {
    const { typeName } = await loadPanelModule();
    expect(typeName({ type_chain: ["DataObject", "Mystery"] })).toBe("Mystery");
    expect(typeName({ type_chain: [] })).toBe("object");
    expect(typeName(null)).toBe("object");
  });

  it("shows ancestry only when there is more than the type itself", async () => {
    const { ancestry } = await loadPanelModule();
    expect(ancestry({ type_chain: ["DataObject", "Mystery"] })).toBe("DataObject → Mystery");
    // A chain of one is the type already on screen; repeating it says nothing.
    expect(ancestry({ type_chain: ["DataObject"] })).toBeNull();
    expect(ancestry({})).toBeNull();
  });

  it("treats an empty record as no record rather than as {}", async () => {
    const { recordedMetadata } = await loadPanelModule();
    expect(recordedMetadata({ metadata: { a: 1 } })).toEqual({ a: 1 });
    expect(recordedMetadata({ metadata: {} })).toBeNull();
    expect(recordedMetadata({ metadata: null })).toBeNull();
    expect(recordedMetadata({})).toBeNull();
  });
});

describe("core.base.fallback — the card", () => {
  it("says what the object is, which the viewer it replaces could not", async () => {
    stubHost(metadataRead());
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("object-type")).toBeTruthy());

    expect(testid("object-type")?.textContent).toBe("Mystery");
    expect(testid("object-chain")?.textContent).toBe("DataObject → Mystery");
    expect(testid("object-metadata")?.textContent).toContain('"created_by": "some.block"');
  });

  it("shows shape and dtype when the record carries them", async () => {
    stubHost(metadataRead({ shape: [4, 5], dtype: "float32" }));
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("object-type")).toBeTruthy());
    expect(root().textContent).toContain("shape [4, 5]");
    expect(root().textContent).toContain("dtype float32");
  });

  it("describes the stored file when the object has one", async () => {
    stubHost(metadataRead(), {
      name: "blob.bin",
      path: "/runs/r1/blob.bin",
      mime_type: "application/octet-stream",
      size: 2048,
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("object-path")).toBeTruthy());

    expect(testid("object-path")?.textContent).toBe("/runs/r1/blob.bin");
    expect(testid("object-mime")?.textContent).toBe("application/octet-stream");
    expect(testid("object-size")?.textContent).toBe("2048 bytes");
    expect(testid("object-no-file")).toBeNull();
  });

  it("shows an image inline when the stored file is one", async () => {
    stubHost(metadataRead(), {
      name: "thumb.png",
      path: "/runs/r1/thumb.png",
      mime_type: "image/png",
      size: 64,
      url: "blob:thumb",
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("object-image")).toBeTruthy());
    expect(testid("object-image")?.getAttribute("src")).toBe("blob:thumb");
  });
});

describe("core.base.fallback — saying what is absent (#1886)", () => {
  it("says so when the object was never written to storage", async () => {
    stubHost(metadataRead(), null);
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("object-no-file")).toBeTruthy());

    // Absent file lines must read as absence, not as a failed load.
    expect(testid("object-path")).toBeNull();
    expect(testid("object-no-file")?.textContent).toContain("no stored file");
    // A missing file is not a panel failure.
    expect(testid("object-type")?.textContent).toBe("Mystery");
  });

  it("says so when nothing else is recorded", async () => {
    stubHost(metadataRead({ metadata: {} }), null);
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("object-no-metadata")).toBeTruthy());
    expect(testid("object-metadata")).toBeNull();
  });

  it("does not report a missing artifact as an error", async () => {
    const api = stubHost(metadataRead(), null);
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("object-no-file")).toBeTruthy());
    expect(api.reportError).not.toHaveBeenCalled();
    expect(root().querySelector(".panel-error")).toBeNull();
  });
});

describe("core.base.fallback — edge cases", () => {
  it("surfaces a failed metadata read", async () => {
    const api = {
      input: {},
      viewState: {},
      ready: () => Promise.resolve(api),
      read: () => Promise.reject(new Error("unsupported")),
      setViewState: vi.fn(),
      reportError: vi.fn(() => Promise.resolve(null)),
    } as Record<string, unknown>;
    (window as unknown as { scistudio: unknown }).scistudio = api;
    document.body.innerHTML = '<div id="root"></div>';
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector(".panel-error")).toBeTruthy());
    expect(root().textContent).toContain("Could not read object");
    expect(api.reportError).toHaveBeenCalled();
  });
});
