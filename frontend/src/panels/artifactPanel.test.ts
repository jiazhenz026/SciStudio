/**
 * Behaviour contract for core.artifact.basic.
 *
 * Carries over what the compiled artifact viewer showed — the heading, the
 * storage path, the MIME type, the size in bytes, and an inline image — and
 * pins the one thing it did not do (#1886): the viewer rendered nothing at all
 * when there was no image, so a file with no visual form and an image that
 * failed to load were the same blank space. Each absence now says which it is.
 *
 * The fixtures use the shape the read really answers with. `artifact.info` and
 * `artifact.file` are built in `panels/reads.py` from the resolved file —
 * `name`, `path`, `mime_type`, `size` — and the route adds
 * `sampled`/`truncated`/`complete` and absolutises `url`. There is no
 * `data_uri` on this path: bytes travel through the token-scoped artifact URL.
 */
import { readFileSync } from "node:fs";
import { rewriteRendererImports } from "./rendererTestModules";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.artifact.basic");
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
  const src = rewriteRendererImports(
    readFileSync(resolve(PANEL, "panel.js"), "utf8"),
    preactUrl,
    uiUrl,
  )
    .replace(/"[^"]*preact-standalone\.module\.js"/g, JSON.stringify(preactUrl))
    .replace(/"[^"]*panel-ui\.js"/g, JSON.stringify(uiUrl));
  loadCount += 1;
  return import(/* @vite-ignore */ dataUrl(`${src}\n//# load-${loadCount}`));
}

/** An `artifact.info` answer in the shape the route sends. */
function info(overrides: Record<string, unknown> = {}) {
  return {
    name: "figure.png",
    path: "/project/runs/r1/figure.png",
    mime_type: "image/png",
    size: 2048,
    sampled: false,
    truncated: false,
    complete: true,
    ...overrides,
  };
}

/**
 * A backend serving both artifact reads.
 *
 * `file` may be `null` to model a grant that fails while the metadata read
 * succeeds — the two are separately authorized reads, not one call.
 */
function stubHost(
  infoResult: Record<string, unknown>,
  fileUrl: string | null = "/api/panels/t/tok/artifact/g1",
) {
  const api = {
    input: { ref: "art", kind: "data_ref" },
    viewState: {},
    ready: () => Promise.resolve(api),
    read: (op: string) => {
      if (op === "artifact.info") return Promise.resolve(infoResult);
      if (op === "artifact.file") {
        return fileUrl === null
          ? Promise.reject(new Error("grant refused"))
          : Promise.resolve({ ...infoResult, url: fileUrl });
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
const image = () => root().querySelector<HTMLImageElement>("[data-testid=artifact-image]");

beforeAll(() => {
  stubHost(info());
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.artifact.basic — explaining an absent inline view (#1886)", () => {
  it("says nothing when the image is on screen", async () => {
    const { inlineNotice } = await loadPanelModule();
    expect(inlineNotice({ mime: "image/png", url: "/a", imageFailed: false })).toBeNull();
  });

  it("distinguishes the three ways an inline view can be missing", async () => {
    const { inlineNotice } = await loadPanelModule();
    // A file with no visual form at all.
    expect(inlineNotice({ mime: "application/pdf", url: "/a", imageFailed: false })).toContain(
      "No inline view for application/pdf",
    );
    // An image whose bytes were never granted.
    expect(inlineNotice({ mime: "image/png", url: null, imageFailed: false })).toContain(
      "could not be opened",
    );
    // An image the browser refused.
    expect(inlineNotice({ mime: "image/png", url: "/a", imageFailed: true })).toContain(
      "could not be displayed",
    );
    // An unknown type still names something rather than trailing off.
    expect(inlineNotice({ mime: "", url: null, imageFailed: false })).toContain("this file type");
  });

  it("treats only an image/* type as displayable", async () => {
    const { isImage } = await loadPanelModule();
    expect(isImage("image/png")).toBe(true);
    expect(isImage("IMAGE/JPEG")).toBe(true);
    expect(isImage("application/pdf")).toBe(false);
    expect(isImage(undefined)).toBe(false);
  });
});

describe("core.artifact.basic — the card the viewer showed", () => {
  it("shows the path, the MIME type and the size in bytes", async () => {
    stubHost(info());
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("artifact-path")).toBeTruthy());

    // The path, not the bare name: two run outputs are routinely both
    // `figure.png`, and only the path tells them apart.
    expect(testid("artifact-path")?.textContent).toBe("/project/runs/r1/figure.png");
    expect(testid("artifact-mime")?.textContent).toBe("image/png");
    expect(testid("artifact-size")?.textContent).toBe("2048 bytes");
    expect(root().textContent).toContain("Artifact");
  });

  it("shows an image inline from the granted URL", async () => {
    stubHost(info(), "/api/panels/t/tok/artifact/g7");
    await loadPanelModule();
    await vi.waitFor(() => expect(image()).toBeTruthy());
    expect(image()?.getAttribute("src")).toBe("/api/panels/t/tok/artifact/g7");
    // Nothing to explain while the image is there.
    expect(testid("artifact-inline-notice")).toBeNull();
  });

  it("falls back to the name when the read carries no path", async () => {
    stubHost(info({ path: undefined }));
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("artifact-path")).toBeTruthy());
    expect(testid("artifact-path")?.textContent).toBe("figure.png");
  });

  it("omits the size line when the read reports no size", async () => {
    stubHost(info({ size: null }));
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("artifact-mime")).toBeTruthy());
    expect(testid("artifact-size")).toBeNull();
  });
});

describe("core.artifact.basic — artifacts with no picture", () => {
  it("shows the metadata and says why there is no inline view", async () => {
    stubHost(
      info({ name: "report.bin", path: "/p/report.bin", mime_type: "application/octet-stream" }),
    );
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("artifact-inline-notice")).toBeTruthy());

    expect(image()).toBeNull();
    expect(testid("artifact-inline-notice")?.textContent).toContain(
      "No inline view for application/octet-stream",
    );
    // The metadata is real and still shown.
    expect(testid("artifact-path")?.textContent).toBe("/p/report.bin");
  });

  it("keeps the card when the file grant fails, and says the image is unavailable", async () => {
    const api = stubHost(info(), null);
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("artifact-inline-notice")).toBeTruthy());

    expect(testid("artifact-path")?.textContent).toBe("/project/runs/r1/figure.png");
    expect(testid("artifact-inline-notice")?.textContent).toContain("could not be opened");
    // A missing grant is not a panel failure; it must not be reported as one.
    expect(api.reportError).not.toHaveBeenCalled();
  });

  it("replaces an image the browser refuses with the reason", async () => {
    stubHost(info());
    await loadPanelModule();
    await vi.waitFor(() => expect(image()).toBeTruthy());

    image()!.dispatchEvent(new Event("error"));
    await vi.waitFor(() => expect(testid("artifact-inline-notice")).toBeTruthy());
    expect(image()).toBeNull();
    expect(testid("artifact-inline-notice")?.textContent).toContain("could not be displayed");
  });
});

describe("core.artifact.basic — edge cases", () => {
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
    expect(root().textContent).toContain("Could not read artifact");
    expect(api.reportError).toHaveBeenCalled();
  });
});
