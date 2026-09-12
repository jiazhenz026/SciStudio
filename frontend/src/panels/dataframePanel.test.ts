/**
 * Behaviour contract for core.dataframe.basic.
 *
 * Carries over what the compiled table viewer did — a scrolling table, sortable
 * headers that cycle ascending → descending → unsorted, the row and column
 * count, and First/Previous/Next/Last with a page box — and pins #1886 Part 1:
 * a paged table is complete by construction, so the pager is plain navigation
 * and must never be accompanied by a "truncated" or "incomplete" badge.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.dataframe.basic");
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

interface Page {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  sort?: { by?: string | null; direction?: string | null };
}

/** A backend that answers table.page honestly from a fixed table. */
function stubHost(table: Array<Record<string, unknown>>, columns: string[], pageSize = 2) {
  const ops: Array<{ op: string; params: Record<string, unknown> }> = [];
  const api = {
    input: { ref: "t", kind: "data_ref" },
    viewState: undefined as unknown,
    ready: () => Promise.resolve(api),
    read: (op: string, params: Record<string, unknown> = {}) => {
      ops.push({ op, params });
      if (op !== "table.page") {
        return Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
      }
      const sortBy = params.sort_by as string | undefined;
      const sortDir = (params.sort_dir as string | undefined) ?? "asc";
      const sorted = sortBy
        ? [...table].sort((a, b) => {
            const x = a[sortBy] as number;
            const y = b[sortBy] as number;
            return sortDir === "desc" ? y - x : x - y;
          })
        : table;
      // The backend caps the page size to its own budget and echoes what it
      // used, exactly as the row budget does in production.
      const size = Math.min((params.page_size as number) ?? pageSize, pageSize);
      const totalPages = Math.max(1, Math.ceil(sorted.length / size));
      const page = Math.max(1, Math.min((params.page as number) ?? 1, totalPages));
      const result: Page = {
        columns,
        rows: sorted.slice((page - 1) * size, page * size),
        total: sorted.length,
        page,
        page_size: size,
        total_pages: totalPages,
        sort: { by: sortBy ?? null, direction: sortBy ? sortDir : null },
      };
      return Promise.resolve(result);
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return { api, ops };
}

const root = () => document.getElementById("root") as HTMLElement;
const cells = () => [...root().querySelectorAll("tbody td")].map((td) => td.textContent);
const headers = () => [...root().querySelectorAll("thead th")] as HTMLElement[];
const byLabel = (label: string) =>
  root().querySelector(`[aria-label="${label}"]`) as HTMLButtonElement | HTMLInputElement | null;

const TABLE = [
  { id: 1, score: 9.5, label: "a" },
  { id: 2, score: 3.25, label: "b" },
  { id: 3, score: 7, label: "c" },
  { id: 4, score: 1.125, label: "d" },
  { id: 5, score: 5, label: "e" },
];
const COLUMNS = ["id", "score", "label"];

beforeAll(() => {
  stubHost([], []);
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.dataframe.basic — cell formatting", () => {
  it("keeps integers exact, fixes decimals, and renders a missing value as empty", async () => {
    const { formatCell } = await loadPanelModule();
    expect(formatCell(42)).toBe("42");
    expect(formatCell(3.25)).toBe("3.2500");
    expect(formatCell("text")).toBe("text");
    expect(formatCell(null)).toBe("");
    expect(formatCell(undefined)).toBe("");
  });

  it("shows a value JSON cannot carry as what it is (#1886 E)", async () => {
    // A table holding NaN or a timestamp used to fail to serialise, taking the
    // whole preview down; the backend now sends sentinels and ISO text, and a
    // missing measurement reads as NaN rather than an empty cell.
    const { formatCell } = await loadPanelModule();
    expect(formatCell("NaN")).toBe("NaN");
    expect(formatCell("Infinity")).toBe("\u221e");
    expect(formatCell("-Infinity")).toBe("-\u221e");
    expect(formatCell("2026-09-11T23:04:33")).toBe("2026-09-11T23:04:33");
  });

  it("cycles a column through ascending, descending, then unsorted", async () => {
    const { nextSort } = await loadPanelModule();
    expect(nextSort({ by: null, dir: null }, "id")).toEqual({ by: "id", dir: "asc" });
    expect(nextSort({ by: "id", dir: "asc" }, "id")).toEqual({ by: "id", dir: "desc" });
    expect(nextSort({ by: "id", dir: "desc" }, "id")).toEqual({ by: null, dir: null });
    // Choosing a different column starts that column ascending.
    expect(nextSort({ by: "id", dir: "desc" }, "score")).toEqual({ by: "score", dir: "asc" });
  });
});

describe("core.dataframe.basic — the rendered table", () => {
  it("renders the page's rows under their column headers", async () => {
    stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=dataframe-table]")).toBeTruthy(),
    );

    expect(headers().map((th) => th.textContent)).toEqual(COLUMNS);
    expect(cells()).toEqual(["1", "9.5000", "a", "2", "3.2500", "b"]);
  });

  it("summarises the table by rows and columns", async () => {
    stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=dataframe-summary]")).toBeTruthy(),
    );
    const summary = root().querySelector("[data-testid=dataframe-summary]")?.textContent ?? "";
    expect(summary).toContain("5 rows");
    expect(summary).toContain("3 columns");
  });

  it("shows no truncation badge for a complete paged table (#1886 Part 1)", async () => {
    stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=dataframe-table]")).toBeTruthy(),
    );

    const text = (root().textContent ?? "").toLowerCase();
    // Pagination is navigation, not a caveat about the data.
    expect(text).not.toContain("truncated");
    expect(text).not.toContain("incomplete");
    expect(text).not.toContain("sampled");
  });
});

describe("core.dataframe.basic — paging reaches every row", () => {
  it("steps forward and back, and jumps to the first and last page", async () => {
    stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() => expect(cells().length).toBe(6));

    (byLabel("Next page") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(cells()).toEqual(["3", "7", "c", "4", "1.1250", "d"]));

    (byLabel("Last page") as HTMLButtonElement).click();
    // The final page of five rows at two per page holds the fifth row alone.
    await vi.waitFor(() => expect(cells()).toEqual(["5", "5", "e"]));

    (byLabel("Previous page") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(cells()).toEqual(["3", "7", "c", "4", "1.1250", "d"]));

    (byLabel("First page") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(cells()).toEqual(["1", "9.5000", "a", "2", "3.2500", "b"]));
  });

  it("disables the ends of the range", async () => {
    stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() => expect(byLabel("Next page")).toBeTruthy());

    expect((byLabel("First page") as HTMLButtonElement).disabled).toBe(true);
    expect((byLabel("Previous page") as HTMLButtonElement).disabled).toBe(true);
    expect((byLabel("Next page") as HTMLButtonElement).disabled).toBe(false);

    (byLabel("Last page") as HTMLButtonElement).click();
    await vi.waitFor(() => expect((byLabel("Next page") as HTMLButtonElement).disabled).toBe(true));
    expect((byLabel("Last page") as HTMLButtonElement).disabled).toBe(true);
  });

  it("jumps to a typed page and clamps one out of range", async () => {
    stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() => expect(byLabel("Jump to page")).toBeTruthy());

    // Typing then committing, with the render in between — the box is
    // controlled, so the typed value reaches state on the next paint.
    const type = async (value: string) => {
      const box = byLabel("Jump to page") as HTMLInputElement;
      box.value = value;
      box.dispatchEvent(new Event("input", { bubbles: true }));
      await vi.waitFor(() =>
        expect((byLabel("Jump to page") as HTMLInputElement).value).toBe(value),
      );
      (byLabel("Jump to page") as HTMLInputElement).dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
      );
    };

    await type("3");
    await vi.waitFor(() => expect(cells()).toEqual(["5", "5", "e"]));

    await type("99");
    // Clamped to the last page rather than rejected.
    await vi.waitFor(() => expect(cells()).toEqual(["5", "5", "e"]));
  });
});

describe("core.dataframe.basic — sorting", () => {
  it("sorts ascending, then descending, then returns to the recorded order", async () => {
    const { ops } = stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() => expect(headers().length).toBe(3));

    const scoreHeader = () => headers()[1];
    scoreHeader().click();
    await vi.waitFor(() => expect(cells()).toEqual(["4", "1.1250", "d", "2", "3.2500", "b"]));
    expect(scoreHeader().getAttribute("aria-sort")).toBe("ascending");
    expect(scoreHeader().textContent).toContain("▲");

    scoreHeader().click();
    await vi.waitFor(() => expect(cells()).toEqual(["1", "9.5000", "a", "3", "7", "c"]));
    expect(scoreHeader().getAttribute("aria-sort")).toBe("descending");
    expect(scoreHeader().textContent).toContain("▼");

    scoreHeader().click();
    await vi.waitFor(() => expect(cells()).toEqual(["1", "9.5000", "a", "2", "3.2500", "b"]));
    expect(scoreHeader().getAttribute("aria-sort")).toBe("none");

    // Sorting is done by the backend over the whole table, not in the page.
    const sorted = ops.filter((o) => o.params.sort_by === "score");
    expect(sorted.length).toBeGreaterThan(0);
  });

  it("returns to the first page when the order changes", async () => {
    const { ops } = stubHost(TABLE, COLUMNS);
    await loadPanelModule();
    await vi.waitFor(() => expect(headers().length).toBe(3));

    (byLabel("Next page") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(cells()).toEqual(["3", "7", "c", "4", "1.1250", "d"]));

    headers()[1].click();
    await vi.waitFor(() => {
      const last = ops[ops.length - 1];
      expect(last.params.sort_by).toBe("score");
      expect(last.params.page).toBe(1);
    });
  });
});

describe("core.dataframe.basic — edge cases", () => {
  it("says so when the table has no columns", async () => {
    stubHost([], []);
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=dataframe-empty]")).toBeTruthy(),
    );
  });

  it("surfaces a failed page read", async () => {
    const api = {
      input: {},
      ready: () => Promise.resolve(api),
      read: () => Promise.reject(new Error("read_budget")),
      setViewState: vi.fn(),
      reportError: vi.fn(() => Promise.resolve(null)),
    } as Record<string, unknown>;
    (window as unknown as { scistudio: unknown }).scistudio = api;
    document.body.innerHTML = '<div id="root"></div>';
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector(".panel-error")).toBeTruthy());
    expect(root().textContent).toContain("Could not read table");
    expect(api.reportError).toHaveBeenCalled();
  });
});

describe("core.dataframe.basic — a wide table stays responsive", () => {
  it("keeps only the columns in view in the DOM, and reaches the rest by scrolling", async () => {
    // A feature matrix is thousands of columns wide; rendering a cell per column
    // per row put a quarter of a million cells in the document and the browser
    // spent its frames on layout instead of scrolling.
    const columns = Array.from({ length: 5000 }, (_, i) => `c${i}`);
    const row: Record<string, number> = {};
    columns.forEach((c, i) => (row[c] = i));
    stubHost([row, { ...row }], columns, 2);
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=dataframe-table]")).toBeTruthy(),
    );

    const rendered = () =>
      [...root().querySelectorAll("thead th")].filter(
        (th) => !th.classList.contains("dataframe-pad"),
      );
    expect(rendered().length).toBeGreaterThan(0);
    expect(rendered().length).toBeLessThan(100);
    // The first columns are the ones on screen.
    expect(rendered()[0].textContent).toBe("c0");

    // Padding cells reserve the columns that are not rendered, so the scrollbar
    // still describes the whole table.
    expect(root().querySelector("thead .dataframe-pad")).toBeTruthy();

    // Scrolling right brings later columns into the document.
    const surface = root().querySelector(".dataframe-scroll") as HTMLElement;
    Object.defineProperty(surface, "clientWidth", { value: 640, configurable: true });
    surface.scrollLeft = 120 * 1000;
    surface.dispatchEvent(new Event("scroll", { bubbles: true }));
    await vi.waitFor(() => expect(rendered()[0].textContent).not.toBe("c0"));
    const names = rendered().map((th) => th.textContent);
    expect(names.some((n) => n && Number(n.slice(1)) >= 990)).toBe(true);
  });
});
