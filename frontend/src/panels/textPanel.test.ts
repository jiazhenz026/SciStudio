/**
 * Behaviour contract for core.text.basic.
 *
 * The viewer this replaces showed one bounded chunk and, when there was more,
 * an amber notice telling the reader to open the file elsewhere. A read reports
 * where the next chunk begins, so the whole document is reachable: the panel
 * reads to the end and shows the file, with its size as plain information
 * rather than a caveat about data that is in fact complete (#1886).
 *
 * The fixtures below use the response shape the read was observed to produce —
 * `content`/`text`, `total_bytes`, `offset`/`next_offset`, `truncated`,
 * `language`, `encoding`.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.text.basic");
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

/** One chunk in the shape the read emits. */
function chunk(content: string, offset: number, total: number, more: boolean) {
  return {
    content,
    text: content,
    total_bytes: total,
    offset,
    next_offset: offset + content.length,
    truncated: more,
    complete: !more,
    sampled: false,
    language: "txt",
    encoding: "utf-8",
  };
}

/** A backend that serves a document in fixed-size chunks. */
function stubHost(document_: string, chunkSize = 10) {
  const reads: Array<Record<string, unknown>> = [];
  const api = {
    input: { ref: "t", kind: "data_ref" },
    viewState: {},
    ready: () => Promise.resolve(api),
    read: (op: string, params: Record<string, unknown> = {}) => {
      if (op !== "text.chunk") {
        return Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
      }
      reads.push(params);
      const offset = (params.offset as number) ?? 0;
      const slice = document_.slice(offset, offset + chunkSize);
      return Promise.resolve(
        chunk(slice, offset, document_.length, offset + slice.length < document_.length),
      );
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return { api, reads };
}

const root = () => document.getElementById("root") as HTMLElement;
const content = () => root().querySelector("[data-testid=text-content]")?.textContent ?? "";

beforeAll(() => {
  stubHost("");
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.text.basic — reading to the end", () => {
  it("takes the text from either name the read uses", async () => {
    const { chunkText } = await loadPanelModule();
    expect(chunkText({ text: "a", content: "b" })).toBe("a");
    expect(chunkText({ content: "b" })).toBe("b");
    expect(chunkText({})).toBe("");
    expect(chunkText(null)).toBe("");
  });

  it("stops at the end, and stops on a reader that cannot advance", async () => {
    const { nextOffset } = await loadPanelModule();
    // More to read: continue from where the read says.
    expect(nextOffset({ truncated: true, next_offset: 100 }, 0)).toBe(100);
    // Complete: nothing more to ask for.
    expect(nextOffset({ truncated: false, next_offset: 100 }, 0)).toBeNull();
    // A next offset that does not move forward would loop forever.
    expect(nextOffset({ truncated: true, next_offset: 50 }, 50)).toBeNull();
    expect(nextOffset({ truncated: true, next_offset: 10 }, 50)).toBeNull();
    expect(nextOffset({ truncated: true }, 0)).toBeNull();
  });
});

describe("core.text.basic — the rendered document", () => {
  it("shows a short file in full", async () => {
    stubHost("line one\n", 100);
    await loadPanelModule();
    await vi.waitFor(() => expect(content()).toBe("line one\n"));
    expect(root().querySelector("[data-testid=text-loading-more]")).toBeNull();
  });

  it("keeps reading until the whole document is shown (#1886)", async () => {
    const document_ = "abcdefghijklmnopqrstuvwxyz0123456789";
    const { reads } = stubHost(document_, 10);
    await loadPanelModule();
    await vi.waitFor(() => expect(content()).toBe(document_));

    // The reader asked for each following chunk by its reported offset.
    expect(reads.length).toBe(4);
    expect(reads.map((r) => r.offset ?? 0)).toEqual([0, 10, 20, 30]);
    // Nothing tells the reader the content is partial once it is all here.
    const text = (root().textContent ?? "").toLowerCase();
    expect(text).not.toContain("truncated");
    expect(text).not.toContain("open in the editor");
  });

  it("reports the size as information once the document is complete", async () => {
    stubHost("hello world", 100);
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=text-size]")).toBeTruthy());
    expect(root().querySelector("[data-testid=text-size]")?.textContent).toContain("11 bytes");
  });

  it("says it is still reading while chunks are arriving", async () => {
    // A document long enough that the first render happens mid-read.
    const { api } = stubHost("x".repeat(500), 10);
    let resolveSecond: ((value: unknown) => void) | null = null;
    const original = api.read;
    let calls = 0;
    api.read = (op: string, params: Record<string, unknown> = {}) => {
      calls += 1;
      if (calls === 2) {
        return new Promise((resolve) => {
          resolveSecond = () => resolve(original(op, params));
        });
      }
      return original(op, params);
    };
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=text-loading-more]")).toBeTruthy(),
    );
    resolveSecond?.(null);
  });
});

describe("core.text.basic — edge cases", () => {
  it("says so for an empty file", async () => {
    stubHost("", 10);
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=text-empty]")).toBeTruthy());
  });

  it("surfaces a failed read", async () => {
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
    expect(root().textContent).toContain("Could not read text");
    expect(api.reportError).toHaveBeenCalled();
  });
});
