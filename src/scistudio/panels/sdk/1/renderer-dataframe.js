/* Reusable core presentation. Host reads and persistence stay in the caller. */
import {
  html,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Panel,
  ScrollArea,
  Table,
} from "./panel-ui.js";

const DEFAULT_PAGE_SIZE = 50;
// Column virtualization geometry. The width is fixed so the padding cells can
// reserve the off-window columns in CSS pixels and the scrollbar stays true.
const COL_W = 120;
const COL_OVERSCAN = 4;
const DEFAULT_VIEWPORT_W = 640;

/**
 * Format one cell as the table viewer did, with one addition: a value JSON
 * cannot carry arrives as a sentinel string, and a missing measurement is shown
 * as what it is rather than left to read as the literal text "NaN" (#1886 E).
 */
const SENTINELS = { NaN: "NaN", Infinity: "∞", "-Infinity": "-∞" };

export function formatCell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" && value in SENTINELS) return SENTINELS[value];
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "NaN";
    if (!Number.isFinite(value)) return value > 0 ? "∞" : "-∞";
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

/** Cycle a column through ascending, descending, then unsorted. */
export function nextSort(current, column) {
  if (current.by !== column) return { by: column, dir: "asc" };
  if (current.dir === "asc") return { by: column, dir: "desc" };
  return { by: null, dir: null };
}

export function DataFrameView({
  data,
  query = { page: 1, pageSize: 50 },
  loading = false,
  error,
  onQueryChange = () => {},
}) {
  const [pageInput, setPageInput] = useState(String(query.page ?? 1));
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(DEFAULT_VIEWPORT_W);
  const scrollRef = useRef(null);

  // The backend clamps and echoes the paging state; follow its answer.
  const columns = data?.columns ?? [];
  const rows = data?.rows ?? [];
  const totalRows =
    typeof data?.total === "number"
      ? data.total
      : (data?.total_rows ?? rows.length);
  const pageSize = data?.page_size ?? query.pageSize;
  const page = data?.page ?? query.page;
  const totalPages =
    data?.total_pages ??
    Math.max(1, Math.ceil(totalRows / Math.max(pageSize, 1)));
  const sort = data?.sort ?? {};
  const sortBy = sort.by ?? null;
  const sortDir = sort.direction ?? null;

  useEffect(() => {
    setPageInput(String(page));
  }, [page]);

  useLayoutEffect(() => {
    const width = scrollRef.current?.clientWidth ?? 0;
    if (width > 0 && width !== viewportWidth) setViewportWidth(width);
  });

  const goToPage = useCallback(
    (target) => {
      const clamped = Math.max(1, Math.min(target, totalPages));
      onQueryChange({ ...query, page: clamped });
    },
    [totalPages, query, onQueryChange],
  );

  const toggleSort = useCallback(
    (column) => {
      const next = nextSort({ by: sortBy, dir: sortDir }, column);
      // Re-sorting reorders the whole table, so the reader returns to its start.
      onQueryChange({ ...query, page: 1, sortBy: next.by, sortDir: next.dir });
    },
    [sortBy, sortDir, query, onQueryChange],
  );

  const commitPageInput = useCallback(() => {
    const n = Number.parseInt(pageInput, 10);
    if (Number.isNaN(n)) setPageInput(String(page));
    else goToPage(n);
  }, [pageInput, page, goToPage]);

  if (error) {
    return html`<${Panel}
      ><${ErrorState}>Could not read table: ${error}<//><//
    >`;
  }
  if (!data) {
    return html`<${Panel}><${LoadingState}>Loading table…<//><//>`;
  }
  if (!columns.length) {
    return html`<${Panel}
      ><${EmptyState} data-testid="dataframe-empty"
        >This table has no columns.<//
      ><//
    >`;
  }

  /*
   * Only the columns in view are in the DOM. A wide table — thousands of
   * columns is normal for a feature matrix — would otherwise put a cell in the
   * document for every column of every row on the page, and the browser spends
   * its frames on layout instead of scrolling. The columns outside the window
   * become one padding cell on each side that reserves exactly their width, so
   * the scrollbar still describes the whole table and every column is reachable.
   */
  const firstCol = Math.max(0, Math.floor(scrollLeft / COL_W) - COL_OVERSCAN);
  const visibleCols = Math.ceil(viewportWidth / COL_W) + 2 * COL_OVERSCAN;
  const lastCol = Math.min(columns.length, firstCol + visibleCols);
  const window_ = columns.slice(firstCol, lastCol);
  const leftPad = firstCol * COL_W;
  const rightPad = Math.max(0, columns.length - lastCol) * COL_W;

  return html`<${Panel}>
    <${ScrollArea}
      class="dataframe-scroll"
      style=${loading ? "opacity:0.6" : undefined}
      elementRef=${scrollRef}
      onScroll=${(e) => setScrollLeft(e.currentTarget.scrollLeft)}
    >
      <${Table} class="dataframe-table" data-testid="dataframe-table">
        <thead>
          <tr>
            ${leftPad
              ? html`<th
                  class="dataframe-pad"
                  style=${`min-width:${leftPad}px`}
                ></th>`
              : null}
            ${window_.map((column) => {
              const isSorted = sortBy === column;
              const indicator = isSorted
                ? sortDir === "desc"
                  ? " ▼"
                  : " ▲"
                : "";
              return html`<th
                key=${column}
                aria-sort=${isSorted
                  ? sortDir === "desc"
                    ? "descending"
                    : "ascending"
                  : "none"}
                title=${isSorted
                  ? `Sorted ${sortDir}; click to change`
                  : "Click to sort"}
                onClick=${() => toggleSort(column)}
              >
                ${column}${indicator}
              </th>`;
            })}
            ${rightPad
              ? html`<th
                  class="dataframe-pad"
                  style=${`min-width:${rightPad}px`}
                ></th>`
              : null}
          </tr>
        </thead>
        <tbody>
          ${rows.map(
            (row, index) =>
              html`<tr key=${index}>
                ${leftPad
                  ? html`<td
                      class="dataframe-pad"
                      style=${`min-width:${leftPad}px`}
                    ></td>`
                  : null}
                ${window_.map(
                  (column) =>
                    html`<td key=${column}>${formatCell(row[column])}</td>`,
                )}
                ${rightPad
                  ? html`<td
                      class="dataframe-pad"
                      style=${`min-width:${rightPad}px`}
                    ></td>`
                  : null}
              </tr>`,
          )}
        </tbody>
      <//>
    <//>
    <div class="dataframe-bar">
      <span data-testid="dataframe-summary">
        ${totalRows.toLocaleString()} row${totalRows !== 1 ? "s" : ""} ×
        ${columns.length} column${columns.length !== 1 ? "s" : ""}
      </span>
      <span class="dataframe-pager">
        <${Button}
          aria-label="First page"
          disabled=${loading || page <= 1}
          onClick=${() => goToPage(1)}
          >«<//
        >
        <${Button}
          aria-label="Previous page"
          disabled=${loading || page <= 1}
          onClick=${() => goToPage(page - 1)}
          >‹<//
        >
        <${Input}
          class="dataframe-page-input"
          type="text"
          aria-label="Jump to page"
          value=${pageInput}
          onInput=${(e) => setPageInput(e.target.value)}
          onBlur=${commitPageInput}
          onKeyDown=${(e) => {
            if (e.key === "Enter") commitPageInput();
          }}
        />
        <span data-testid="dataframe-page-of">/ ${totalPages}</span>
        <${Button}
          aria-label="Next page"
          disabled=${loading || page >= totalPages}
          onClick=${() => goToPage(page + 1)}
          >›<//
        >
        <${Button}
          aria-label="Last page"
          disabled=${loading || page >= totalPages}
          onClick=${() => goToPage(totalPages)}
          >»<//
        >
      </span>
    </div>
  <//>`;
}
