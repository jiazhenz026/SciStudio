import { useCallback, useEffect, useRef, useState } from "react";

export interface TableViewerInitial {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  totalRows: number;
  page: number;
  pageSize: number;
  totalPages: number;
  sortBy: string | null;
  sortDir: "asc" | "desc" | null;
}

interface TableViewerProps {
  initial: TableViewerInitial;
  /**
   * Merge pagination/sort state into the routed preview session and re-render
   * the envelope (ADR-048 routed session API). The refreshed table payload
   * flows back in through ``initial`` on the next render — the same pattern the
   * ArrayViewer uses for slice selection. When absent (e.g. a static/test
   * mount) the table is read-only.
   */
  onPatchQuery?: (query: Record<string, unknown>) => void;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

export function readTablePayload(preview: Record<string, unknown>): TableViewerInitial {
  const columns = (preview.columns as string[] | undefined) ?? [];
  const rows = (preview.rows as Array<Record<string, unknown>> | undefined) ?? [];
  const totalRows =
    typeof preview.total_rows === "number"
      ? preview.total_rows
      : typeof preview.row_count === "number"
        ? preview.row_count
        : rows.length;
  const pageSize =
    typeof preview.page_size === "number" ? preview.page_size : Math.max(rows.length, 1);
  const totalPages =
    typeof preview.total_pages === "number"
      ? preview.total_pages
      : Math.max(1, Math.ceil(totalRows / Math.max(pageSize, 1)));
  const page = typeof preview.page === "number" ? preview.page : 1;
  const sortByRaw = preview.sort_by;
  const sortDirRaw = preview.sort_dir;
  return {
    columns,
    rows,
    totalRows,
    page,
    pageSize,
    totalPages,
    sortBy: typeof sortByRaw === "string" ? sortByRaw : null,
    sortDir: sortDirRaw === "asc" || sortDirRaw === "desc" ? sortDirRaw : null,
  };
}

function paginationButtonStyle(disabled: boolean): React.CSSProperties {
  return {
    width: 22,
    height: 20,
    padding: 0,
    border: "1px solid #d6d3d1",
    borderRadius: 4,
    background: disabled ? "#f5f5f4" : "#fff",
    color: disabled ? "#a8a29e" : "#475569",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: 10,
    lineHeight: 1,
  };
}

/**
 * Drive pagination/sort through the routed preview session.
 *
 * The table state is whatever the backend last echoed back in ``initial``
 * (the session envelope payload). A page/sort change is pushed through
 * ``onPatchQuery`` — the host PATCHes the session, the backend re-renders the
 * DataFrame plane, and the new payload arrives as a fresh ``initial`` prop.
 * We only keep a transient ``loading`` flag locally so the UI dims while the
 * patched envelope is in flight; the authoritative data lives in the session.
 */
function useTablePaging(
  initial: TableViewerInitial,
  onPatchQuery?: (query: Record<string, unknown>) => void,
): {
  loading: boolean;
  requestPage: (page: number, sortBy: string | null, sortDir: "asc" | "desc" | null) => void;
} {
  const [loading, setLoading] = useState(false);
  // The page/sort we last asked the session for. When ``initial`` catches up
  // to it, the patched envelope has landed and we can clear ``loading``.
  const pendingRef = useRef<{ page: number; sortBy: string | null } | null>(null);

  useEffect(() => {
    const pending = pendingRef.current;
    if (pending && pending.page === initial.page && pending.sortBy === initial.sortBy) {
      pendingRef.current = null;
      setLoading(false);
    }
  }, [initial.page, initial.sortBy]);

  const requestPage = useCallback(
    (page: number, sortBy: string | null, sortDir: "asc" | "desc" | null) => {
      if (!onPatchQuery) return;
      pendingRef.current = { page, sortBy };
      setLoading(true);
      onPatchQuery({
        page,
        page_size: initial.pageSize,
        sort_by: sortBy ?? undefined,
        sort_dir: sortDir ?? undefined,
      });
    },
    [onPatchQuery, initial.pageSize],
  );

  return { loading, requestPage };
}

function TableHeader({
  columns,
  sortBy,
  sortDir,
  toggleSort,
}: {
  columns: string[];
  sortBy: string | null;
  sortDir: "asc" | "desc" | null;
  toggleSort: (column: string) => void;
}) {
  return (
    <thead>
      <tr>
        {columns.map((column) => {
          const isSorted = sortBy === column;
          const indicator = isSorted ? (sortDir === "desc" ? " ▼" : " ▲") : "";
          return (
            <th
              key={column}
              aria-sort={isSorted ? (sortDir === "desc" ? "descending" : "ascending") : "none"}
              onClick={() => toggleSort(column)}
              style={{
                whiteSpace: "nowrap",
                padding: "6px 10px",
                borderBottom: "1px solid #cbd5e1",
                fontWeight: 600,
                fontSize: 11,
                color: isSorted ? "#1c1917" : "#475569",
                background: "#fff",
                position: "sticky",
                top: 0,
                zIndex: 1,
                cursor: "pointer",
                userSelect: "none",
              }}
              title={isSorted ? `Sorted ${sortDir}; click to change` : "Click to sort"}
            >
              {column}
              <span style={{ fontSize: 9, color: "#a8a29e" }}>{indicator}</span>
            </th>
          );
        })}
      </tr>
    </thead>
  );
}

function TableBody({ columns, rows }: { columns: string[]; rows: Array<Record<string, unknown>> }) {
  return (
    <tbody>
      {rows.map((row, index) => (
        <tr key={index} style={{ borderBottom: "1px solid #f1f5f9" }}>
          {columns.map((column) => (
            <td
              key={column}
              style={{
                whiteSpace: "nowrap",
                padding: "3px 10px",
                fontSize: 10,
                color: "#334155",
                borderBottom: "1px solid #f1f5f9",
              }}
            >
              {formatCell(row[column])}
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

function PaginationControls({
  page,
  totalPages,
  loading,
  pageInput,
  setPageInput,
  goToPage,
  commitPageInput,
}: {
  page: number;
  totalPages: number;
  loading: boolean;
  pageInput: string;
  setPageInput: (s: string) => void;
  goToPage: (n: number) => void;
  commitPageInput: () => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <button
        aria-label="First page"
        disabled={loading || page <= 1}
        onClick={() => goToPage(1)}
        style={paginationButtonStyle(loading || page <= 1)}
        type="button"
      >
        «
      </button>
      <button
        aria-label="Previous page"
        disabled={loading || page <= 1}
        onClick={() => goToPage(page - 1)}
        style={paginationButtonStyle(loading || page <= 1)}
        type="button"
      >
        ‹
      </button>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
        Page
        <input
          aria-label="Jump to page"
          disabled={loading}
          onBlur={commitPageInput}
          onChange={(e) => setPageInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitPageInput();
            }
          }}
          style={{
            width: 44,
            padding: "1px 4px",
            fontSize: 10,
            border: "1px solid #d6d3d1",
            borderRadius: 4,
            textAlign: "center",
          }}
          type="text"
          value={pageInput}
        />
        / {totalPages.toLocaleString()}
      </span>
      <button
        aria-label="Next page"
        disabled={loading || page >= totalPages}
        onClick={() => goToPage(page + 1)}
        style={paginationButtonStyle(loading || page >= totalPages)}
        type="button"
      >
        ›
      </button>
      <button
        aria-label="Last page"
        disabled={loading || page >= totalPages}
        onClick={() => goToPage(totalPages)}
        style={paginationButtonStyle(loading || page >= totalPages)}
        type="button"
      >
        »
      </button>
    </div>
  );
}

export function TableViewer({ initial, onPatchQuery }: TableViewerProps) {
  const { loading, requestPage } = useTablePaging(initial, onPatchQuery);
  const [pageInput, setPageInput] = useState(String(initial.page));

  useEffect(() => {
    setPageInput(String(initial.page));
  }, [initial.page]);

  const goToPage = useCallback(
    (target: number) => {
      const clamped = Math.max(1, Math.min(target, initial.totalPages));
      if (clamped === initial.page) return;
      requestPage(clamped, initial.sortBy, initial.sortDir);
    },
    [initial.page, initial.sortBy, initial.sortDir, initial.totalPages, requestPage],
  );

  const toggleSort = useCallback(
    (column: string) => {
      let nextSortBy: string | null;
      let nextSortDir: "asc" | "desc" | null;
      if (initial.sortBy !== column) {
        nextSortBy = column;
        nextSortDir = "asc";
      } else if (initial.sortDir === "asc") {
        nextSortBy = column;
        nextSortDir = "desc";
      } else {
        nextSortBy = null;
        nextSortDir = null;
      }
      requestPage(1, nextSortBy, nextSortDir);
    },
    [initial.sortBy, initial.sortDir, requestPage],
  );

  const commitPageInput = useCallback(() => {
    const n = Number.parseInt(pageInput, 10);
    if (Number.isNaN(n)) {
      setPageInput(String(initial.page));
      return;
    }
    goToPage(n);
  }, [initial.page, goToPage, pageInput]);

  const { columns, rows, totalRows, page, totalPages, sortBy, sortDir } = initial;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      <div
        style={{
          overflow: "auto",
          borderRadius: "0.8rem",
          border: "1px solid #e7e5e4",
          background: "#fff",
          maxHeight: "360px",
          opacity: loading ? 0.6 : 1,
          transition: "opacity 120ms ease",
        }}
      >
        <table
          style={{
            borderCollapse: "collapse",
            minWidth: "100%",
            textAlign: "left",
            fontSize: 11,
          }}
        >
          <TableHeader
            columns={columns}
            sortBy={sortBy}
            sortDir={sortDir}
            toggleSort={toggleSort}
          />
          <TableBody columns={columns} rows={rows} />
        </table>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 6,
          padding: "6px 4px 0",
          fontSize: 10,
          color: "#78716c",
        }}
      >
        <span>
          {totalRows.toLocaleString()} row{totalRows !== 1 ? "s" : ""} × {columns.length} column
          {columns.length !== 1 ? "s" : ""}
        </span>
        <PaginationControls
          page={page}
          totalPages={totalPages}
          loading={loading}
          pageInput={pageInput}
          setPageInput={setPageInput}
          goToPage={goToPage}
          commitPageInput={commitPageInput}
        />
      </div>
    </div>
  );
}
