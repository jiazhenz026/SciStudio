import Plot from "react-plotly.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { extractOMEFromMetadata, getOMEMetadata, type OMETree } from "../api/capabilities";
import { api } from "../lib/api";
import type { DataPreviewResponse } from "../types/api";

import { OMEMetadataPanel, hasOMEContent } from "./OutputPreview/OMEMetadataPanel";

interface DataPreviewProps {
  selectedNodeId: string | null;
  selectedNodeLabel: string;
  blockOutputs: Record<string, Record<string, unknown>>;
  previewCache: Record<string, DataPreviewResponse>;
  previewLoading: Record<string, boolean>;
  onLoadPreview: (dataRef: string) => Promise<void>;
}

/**
 * #898 — every output dict in ``blockOutputs[block_id]`` already carries
 * ``metadata.framework.source`` (full source file path stamped by
 * LoadImage and other IO blocks). Walk the payload and pair each
 * ``data_ref`` with a human-friendly display name so the pill labels
 * read e.g. ``beads.tif`` instead of ``data-873de``.
 */
export interface RefEntry {
  ref: string;
  displayName: string;
}

function basename(p: string): string {
  const trimmed = p.replace(/[\\/]+$/, "");
  const parts = trimmed.split(/[\\/]/);
  return parts[parts.length - 1] || trimmed;
}

function deriveDisplayName(ref: string, dataItem: Record<string, unknown>): string {
  const md = dataItem.metadata;
  if (md && typeof md === "object") {
    const mdRec = md as Record<string, unknown>;
    // 1. framework.source — set by IO loaders (LoadImage etc.)
    const framework = mdRec.framework;
    if (framework && typeof framework === "object") {
      const src = (framework as Record<string, unknown>).source;
      if (typeof src === "string" && src) return basename(src);
    }
    // 2. meta.source_file — typed Image.Meta
    const meta = mdRec.meta;
    if (meta && typeof meta === "object") {
      const sourceFile = (meta as Record<string, unknown>).source_file;
      if (typeof sourceFile === "string" && sourceFile) return basename(sourceFile);
      // 3. meta.file_path — Artifact
      const filePath = (meta as Record<string, unknown>).file_path;
      if (typeof filePath === "string" && filePath) return basename(filePath);
    }
  }
  // 4. Fallback: truncated ref (today's behavior)
  return ref.slice(0, 10);
}

export function extractRefEntries(payload: unknown): RefEntry[] {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const record = payload as Record<string, unknown>;
  if (typeof record.data_ref === "string") {
    return [{ ref: record.data_ref, displayName: deriveDisplayName(record.data_ref, record) }];
  }
  if (record.kind === "collection" && Array.isArray(record.items)) {
    return record.items.flatMap((item) => extractRefEntries(item));
  }
  return Object.values(record).flatMap((value) => extractRefEntries(value));
}

// ─── LUT Colormaps (canvas-based, matching OptEasy) ─────────────────────────

function buildLUT(fn: (t: number) => [number, number, number]): [number, number, number][] {
  return Array.from({ length: 256 }, (_, i) => {
    const [r, g, b] = fn(i);
    return [
      Math.max(0, Math.min(255, Math.round(r))),
      Math.max(0, Math.min(255, Math.round(g))),
      Math.max(0, Math.min(255, Math.round(b))),
    ] as [number, number, number];
  });
}

const LUTS: Record<string, [number, number, number][]> = {
  gray: Array.from({ length: 256 }, (_, i) => [i, i, i] as [number, number, number]),
  fire: buildLUT((t) => [
    Math.min(255, t * 3),
    Math.max(0, (t - 85) * 3),
    Math.max(0, (t - 170) * 3),
  ]),
  ice: buildLUT((t) => [
    Math.max(0, (t - 170) * 3),
    Math.max(0, (t - 85) * 3),
    Math.min(255, t * 3),
  ]),
  green: buildLUT((t) => [0, t, 0]),
  red: buildLUT((t) => [t, 0, 0]),
  blue: buildLUT((t) => [0, 0, t]),
  cyan: buildLUT((t) => [0, t, t]),
  magenta: buildLUT((t) => [t, 0, t]),
  viridis: buildLUT((t) => {
    const r = Math.round(68 + (253 - 68) * Math.sin((t / 256) * Math.PI * 0.8));
    const g = Math.round(1 + (231 - 1) * (t / 255));
    const b = Math.round(84 + (37 - 84) * (t / 255));
    return [Math.min(255, r), Math.min(255, g), Math.max(0, b)];
  }),
};

function lutGradient(lut: [number, number, number][]): string {
  const stops = [0, 64, 128, 192, 255].map((i) => {
    const [r, g, b] = lut[i];
    return `rgb(${r},${g},${b})`;
  });
  return stops.join(", ");
}

function applyLUTToImage(
  dataUrl: string,
  lut: [number, number, number][],
  minVal: number,
  maxVal: number,
): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = imageData.data;
      const range = maxVal - minVal || 1;

      for (let i = 0; i < pixels.length; i += 4) {
        const gray = pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114;
        const normalized = Math.max(0, Math.min(255, ((gray - minVal) / range) * 255));
        const idx = Math.round(normalized);
        const [r, g, b] = lut[idx] ?? [idx, idx, idx];
        pixels[i] = r;
        pixels[i + 1] = g;
        pixels[i + 2] = b;
      }

      ctx.putImageData(imageData, 0, 0);
      resolve(canvas.toDataURL("image/png"));
    };
    img.src = dataUrl;
  });
}

interface ImageViewerProps {
  src: string;
  shape?: number[];
  /**
   * #899 — when the underlying array is 3-D and a slider axis was
   * detected by the backend, these props drive the horizontal slider
   * shown below the image canvas. ``onSliceChange`` is called with the
   * new integer index on every drag; the parent handles fetch +
   * cache + debounce. Render no slider when ``sliceAxisSize`` is null
   * or ``<= 1``.
   */
  sliceAxisName?: string | null;
  sliceAxisSize?: number | null;
  sliceIndex?: number | null;
  onSliceChange?: (idx: number) => void;
}

function ImageViewer({
  src,
  shape,
  sliceAxisName,
  sliceAxisSize,
  sliceIndex,
  onSliceChange,
}: ImageViewerProps) {
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [lutName, setLutName] = useState("gray");
  const [minDisplay, setMinDisplay] = useState(0);
  const [maxDisplay, setMaxDisplay] = useState(255);
  const [isDragging, setIsDragging] = useState(false);
  const [processedUrl, setProcessedUrl] = useState<string | null>(null);
  const dragStart = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Apply LUT when settings change
  useEffect(() => {
    if (!src) {
      setProcessedUrl(null);
      return;
    }
    if (lutName === "gray" && minDisplay === 0 && maxDisplay === 255) {
      setProcessedUrl(src);
      return;
    }
    void applyLUTToImage(src, LUTS[lutName] ?? LUTS.gray, minDisplay, maxDisplay).then(
      setProcessedUrl,
    );
  }, [src, lutName, minDisplay, maxDisplay]);

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    setScale((prev) => Math.max(0.1, Math.min(20, prev * (e.deltaY < 0 ? 1.15 : 0.87))));
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  const onMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    dragStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y };
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !dragStart.current) return;
    setPan({
      x: dragStart.current.px + (e.clientX - dragStart.current.mx),
      y: dragStart.current.py + (e.clientY - dragStart.current.my),
    });
  };

  const onMouseUp = () => {
    setIsDragging(false);
    dragStart.current = null;
  };

  const zoom = (delta: number) => {
    setScale((prev) => Math.max(0.1, Math.min(20, prev * delta)));
  };

  const reset = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
    setLutName("gray");
    setMinDisplay(0);
    setMaxDisplay(255);
  };

  const displaySrc = processedUrl ?? src;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0px" }}>
      {/* Dark image viewport */}
      <div
        ref={containerRef}
        style={{
          position: "relative",
          overflow: "hidden",
          borderRadius: "0.8rem 0.8rem 0 0",
          background: "#1e293b",
          height: "300px",
          cursor: isDragging ? "grabbing" : "grab",
        }}
        onMouseDown={onMouseDown}
        onMouseLeave={onMouseUp}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
      >
        {displaySrc && (
          <img
            alt="Preview"
            draggable={false}
            src={displaySrc}
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              transform: `translate(-50%, -50%) translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
              imageRendering: scale > 2 ? "pixelated" : "auto",
              maxWidth: "none",
              maxHeight: "none",
              userSelect: "none",
            }}
          />
        )}

        {/* Info badge */}
        <div
          data-testid="image-info-badge"
          style={{
            position: "absolute",
            bottom: 6,
            left: 6,
            fontSize: 10,
            color: "#94a3b8",
            background: "rgba(0,0,0,0.5)",
            padding: "2px 8px",
            borderRadius: 3,
            pointerEvents: "none",
          }}
        >
          {shape ? `${shape.join(" \u00d7 ")} | ` : ""}
          {Math.round(scale * 100)}%
        </div>
      </div>

      {/* LUT & Display controls */}
      <div
        style={{
          padding: "8px 10px",
          borderRadius: "0 0 0.8rem 0.8rem",
          border: "1px solid #e7e5e4",
          borderTop: "none",
          background: "#fff",
          fontSize: 10,
        }}
      >
        {/*
         * #899 — 3-D slice slider. Renders only when the backend
         * reports a slider axis with > 1 entries. Slider position
         * updates parent state immediately; parent handles 200 ms
         * debounce + slice cache + fetch.
         */}
        {sliceAxisSize !== null &&
        sliceAxisSize !== undefined &&
        sliceAxisSize > 1 &&
        onSliceChange ? (
          <div
            data-testid="image-slice-slider-row"
            style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}
          >
            <span style={{ width: 70, color: "#78716c" }}>
              {(sliceAxisName ?? "axis") + ` (${sliceAxisSize})`}
            </span>
            <input
              aria-label={`Slice slider for ${sliceAxisName ?? "axis"}`}
              data-testid="image-slice-slider"
              type="range"
              min={0}
              max={sliceAxisSize - 1}
              value={sliceIndex ?? 0}
              onChange={(e) => onSliceChange(Number(e.target.value))}
              style={{ flex: 1 }}
            />
            <span style={{ minWidth: 38, textAlign: "right", color: "#78716c" }}>
              {(sliceIndex ?? 0) + 1}/{sliceAxisSize}
            </span>
          </div>
        ) : null}

        {/* Zoom row */}
        <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 6 }}>
          <button
            aria-label="Zoom in"
            onClick={() => zoom(1.25)}
            type="button"
            style={{
              fontSize: 12,
              padding: "1px 8px",
              border: "1px solid #d6d3d1",
              borderRadius: 4,
              cursor: "pointer",
              background: "#fff",
            }}
          >
            +
          </button>
          <span style={{ minWidth: "3rem", textAlign: "center", color: "#78716c" }}>
            {Math.round(scale * 100)}%
          </span>
          <button
            aria-label="Zoom out"
            onClick={() => zoom(0.8)}
            type="button"
            style={{
              fontSize: 12,
              padding: "1px 8px",
              border: "1px solid #d6d3d1",
              borderRadius: 4,
              cursor: "pointer",
              background: "#fff",
            }}
          >
            {"\u2212"}
          </button>
          <button
            onClick={reset}
            type="button"
            style={{
              fontSize: 10,
              padding: "2px 8px",
              border: "1px solid #d6d3d1",
              borderRadius: 4,
              cursor: "pointer",
              background: "#fff",
              color: "#78716c",
              marginLeft: "auto",
            }}
          >
            Reset
          </button>
        </div>

        {/* LUT selector (gradient swatches) */}
        <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
          <span style={{ width: 30, color: "#78716c" }}>LUT</span>
          <div style={{ display: "flex", gap: 2, flex: 1, flexWrap: "wrap" }}>
            {Object.keys(LUTS).map((name) => (
              <button
                key={name}
                aria-label={`LUT ${name}`}
                onClick={() => setLutName(name)}
                title={name}
                type="button"
                style={{
                  width: 20,
                  height: 14,
                  borderRadius: 2,
                  cursor: "pointer",
                  padding: 0,
                  border: name === lutName ? "2px solid #3b82f6" : "1px solid #475569",
                  background: `linear-gradient(to right, ${lutGradient(LUTS[name])})`,
                }}
              />
            ))}
          </div>
        </div>

        {/* Min/Max display range */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
          <span style={{ width: 30, color: "#78716c" }}>Min</span>
          <input
            aria-label="Display minimum"
            type="range"
            min={0}
            max={254}
            value={minDisplay}
            onChange={(e) => setMinDisplay(Math.min(Number(e.target.value), maxDisplay - 1))}
            style={{ flex: 1 }}
          />
          <span style={{ width: 24, textAlign: "right", color: "#78716c" }}>{minDisplay}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 30, color: "#78716c" }}>Max</span>
          <input
            aria-label="Display maximum"
            type="range"
            min={1}
            max={255}
            value={maxDisplay}
            onChange={(e) => setMaxDisplay(Math.max(Number(e.target.value), minDisplay + 1))}
            style={{ flex: 1 }}
          />
          <span style={{ width: 24, textAlign: "right", color: "#78716c" }}>{maxDisplay}</span>
        </div>
      </div>
    </div>
  );
}

interface TableViewerInitial {
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
  dataRef: string;
  initial: TableViewerInitial;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

function readTablePayload(preview: Record<string, unknown>): TableViewerInitial {
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

function TableViewer({ dataRef, initial }: TableViewerProps) {
  const [data, setData] = useState<TableViewerInitial>(initial);
  const [loading, setLoading] = useState(false);
  const [pageInput, setPageInput] = useState(String(initial.page));
  // Track the (page, sortBy, sortDir) that ``data`` was loaded for so we know
  // when the parent-supplied ``initial`` is what we already show. Refetches
  // are scheduled when the user changes any of these.
  const requestedRef = useRef({
    page: initial.page,
    sortBy: initial.sortBy,
    sortDir: initial.sortDir,
  });

  // Track in-flight requests so a slow earlier response doesn't overwrite
  // a faster later one.
  const inflightRef = useRef(0);

  useEffect(() => {
    setPageInput(String(data.page));
  }, [data.page]);

  const requestPage = useCallback(
    (page: number, sortBy: string | null, sortDir: "asc" | "desc" | null) => {
      requestedRef.current = { page, sortBy, sortDir };
      const ticket = ++inflightRef.current;
      setLoading(true);
      api
        .getDataPreview(dataRef, {
          page,
          sortBy: sortBy ?? undefined,
          sortDir: sortDir ?? undefined,
        })
        .then((resp) => {
          if (ticket !== inflightRef.current) return; // a newer request superseded us
          setData(readTablePayload(resp.preview));
        })
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.warn(`getDataPreview(${dataRef}) page=${page} sort=${sortBy} failed:`, err);
        })
        .finally(() => {
          if (ticket === inflightRef.current) setLoading(false);
        });
    },
    [dataRef],
  );

  const goToPage = useCallback(
    (target: number) => {
      const clamped = Math.max(1, Math.min(target, data.totalPages));
      if (clamped === data.page) return;
      requestPage(clamped, data.sortBy, data.sortDir);
    },
    [data.page, data.sortBy, data.sortDir, data.totalPages, requestPage],
  );

  const toggleSort = useCallback(
    (column: string) => {
      // Cycle: unsorted → asc → desc → unsorted
      let nextSortBy: string | null;
      let nextSortDir: "asc" | "desc" | null;
      if (data.sortBy !== column) {
        nextSortBy = column;
        nextSortDir = "asc";
      } else if (data.sortDir === "asc") {
        nextSortBy = column;
        nextSortDir = "desc";
      } else {
        nextSortBy = null;
        nextSortDir = null;
      }
      requestPage(1, nextSortBy, nextSortDir);
    },
    [data.sortBy, data.sortDir, requestPage],
  );

  const commitPageInput = useCallback(() => {
    const n = Number.parseInt(pageInput, 10);
    if (Number.isNaN(n)) {
      setPageInput(String(data.page));
      return;
    }
    goToPage(n);
  }, [data.page, goToPage, pageInput]);

  const { columns, rows, totalRows, page, totalPages, sortBy, sortDir } = data;

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
          <thead>
            <tr>
              {columns.map((column) => {
                const isSorted = sortBy === column;
                const indicator = isSorted ? (sortDir === "desc" ? " \u25bc" : " \u25b2") : "";
                return (
                  <th
                    key={column}
                    aria-sort={
                      isSorted ? (sortDir === "desc" ? "descending" : "ascending") : "none"
                    }
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
          {totalRows.toLocaleString()} row{totalRows !== 1 ? "s" : ""} {"\u00d7"} {columns.length}{" "}
          column
          {columns.length !== 1 ? "s" : ""}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button
            aria-label="First page"
            disabled={loading || page <= 1}
            onClick={() => goToPage(1)}
            style={paginationButtonStyle(loading || page <= 1)}
            type="button"
          >
            {"\u00ab"}
          </button>
          <button
            aria-label="Previous page"
            disabled={loading || page <= 1}
            onClick={() => goToPage(page - 1)}
            style={paginationButtonStyle(loading || page <= 1)}
            type="button"
          >
            {"\u2039"}
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
            {"\u203a"}
          </button>
          <button
            aria-label="Last page"
            disabled={loading || page >= totalPages}
            onClick={() => goToPage(totalPages)}
            style={paginationButtonStyle(loading || page >= totalPages)}
            type="button"
          >
            {"\u00bb"}
          </button>
        </div>
      </div>
    </div>
  );
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

interface PreviewRendererProps {
  preview: Record<string, unknown>;
  /** Backing data_ref — required for paginated/sortable lazy refetch (table). */
  dataRef: string;
  /**
   * #899 — parent-driven slider position. Takes precedence over the
   * backend-echoed ``preview.slice_index`` so the slider does not
   * snap back to a stale value while a new slice is in flight.
   */
  currentSlice?: number;
  onSliceChange?: (idx: number) => void;
}

function PreviewRenderer({ preview, dataRef, currentSlice, onSliceChange }: PreviewRendererProps) {
  switch (preview.kind) {
    case "table":
      return <TableViewer key={dataRef} dataRef={dataRef} initial={readTablePayload(preview)} />;
    case "image": {
      // Slider position: prefer the live parent state so dragging never
      // snaps back to the backend's last-rendered index.
      const sliceIndex = currentSlice ?? (preview.slice_index as number | null | undefined) ?? null;
      return (
        <ImageViewer
          shape={preview.shape as number[] | undefined}
          src={String(preview.src)}
          sliceAxisName={(preview.slice_axis_name as string | null | undefined) ?? null}
          sliceAxisSize={(preview.slice_axis_size as number | null | undefined) ?? null}
          sliceIndex={sliceIndex}
          onSliceChange={onSliceChange}
        />
      );
    }
    case "chart":
      return (
        <Plot
          className="w-full"
          data={[
            {
              x:
                (preview.points as Array<{ x: number; y: number }> | undefined)?.map(
                  (point) => point.x,
                ) ?? [],
              y:
                (preview.points as Array<{ x: number; y: number }> | undefined)?.map(
                  (point) => point.y,
                ) ?? [],
              type: "scatter",
              mode: "lines+markers",
              marker: { color: "#f06a44" },
            },
          ]}
          layout={{
            autosize: true,
            margin: { l: 30, r: 10, b: 30, t: 10 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: { family: "IBM Plex Sans, sans-serif", size: 12 },
          }}
          style={{ width: "100%", height: "260px" }}
          useResizeHandler
        />
      );
    case "text":
      return (
        <pre className="max-h-80 overflow-auto rounded-[1.4rem] border border-stone-200 bg-white p-4 text-sm">
          {String(preview.content ?? "")}
        </pre>
      );
    case "composite":
      return (
        <div className="space-y-2">
          {Object.entries((preview.slots as Record<string, unknown> | undefined) ?? {}).map(
            ([slot, value]) => (
              <div className="rounded-2xl border border-stone-200 bg-white px-4 py-3" key={slot}>
                <p className="text-xs uppercase tracking-[0.25em] text-stone-500">{slot}</p>
                <p className="mt-1 text-sm text-ink">{String(value)}</p>
              </div>
            ),
          )}
        </div>
      );
    default:
      return (
        <div className="rounded-[1.4rem] border border-stone-200 bg-white p-4 text-sm text-stone-600">
          <p>Artifact preview</p>
          <p className="mt-2 text-xs">{String(preview.path ?? "")}</p>
          <p className="text-xs">{String(preview.mime_type ?? "")}</p>
        </div>
      );
  }
}

export function DataPreview({
  selectedNodeId,
  selectedNodeLabel,
  blockOutputs,
  previewCache,
  previewLoading,
  onLoadPreview,
}: DataPreviewProps) {
  const [activeRef, setActiveRef] = useState<string | null>(null);
  // #898 — pill labels become source filenames (with truncated-ref fallback).
  const refEntries = useMemo(() => {
    if (!selectedNodeId) return [];
    return extractRefEntries(blockOutputs[selectedNodeId] ?? {});
  }, [blockOutputs, selectedNodeId]);
  const outputRefs = useMemo(() => refEntries.map((e) => e.ref), [refEntries]);

  // #899 — per-active-ref current slice index. Reset when activeRef changes.
  const [currentSliceByRef, setCurrentSliceByRef] = useState<Record<string, number>>({});
  // Local cache for non-zero slice variants. Slice 0 falls through to the
  // store's ``previewCache`` so existing behavior is unchanged.
  const sliceCacheRef = useRef<Map<string, DataPreviewResponse>>(new Map());
  const [sliceCacheVersion, setSliceCacheVersion] = useState(0);
  const sliceFetchingRef = useRef<Set<string>>(new Set());

  const activeSlice = activeRef ? (currentSliceByRef[activeRef] ?? 0) : 0;
  const activeSliceKey = activeRef ? `${activeRef}#${activeSlice}` : null;

  useEffect(() => {
    setActiveRef(outputRefs[0] ?? null);
  }, [outputRefs]);

  // Slice 0 fetch through the store (preserves existing flow).
  useEffect(() => {
    if (activeRef && activeSlice === 0 && !previewCache[activeRef] && !previewLoading[activeRef]) {
      void onLoadPreview(activeRef);
    }
  }, [activeRef, activeSlice, onLoadPreview, previewCache, previewLoading]);

  // #899 — slice > 0 fetch with 200 ms debounce. Cache hit → instant (no
  // timer). Cache miss → debounced fetch, last drag position wins.
  useEffect(() => {
    if (!activeRef || activeSlice === 0 || !activeSliceKey) return undefined;
    if (sliceCacheRef.current.has(activeSliceKey)) return undefined;
    if (sliceFetchingRef.current.has(activeSliceKey)) return undefined;
    const timer = window.setTimeout(() => {
      sliceFetchingRef.current.add(activeSliceKey);
      void api
        .getDataPreview(activeRef, activeSlice)
        .then((resp) => {
          sliceCacheRef.current.set(activeSliceKey, resp);
          setSliceCacheVersion((v) => v + 1);
        })
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.warn(`getDataPreview(${activeRef}, slice=${activeSlice}) failed:`, err);
        })
        .finally(() => {
          sliceFetchingRef.current.delete(activeSliceKey);
        });
    }, 200);
    return () => window.clearTimeout(timer);
  }, [activeRef, activeSlice, activeSliceKey]);

  // Reset slice cache when activeRef changes — avoid stale entries piling up.
  useEffect(() => {
    if (!activeRef) return;
    setCurrentSliceByRef((prev) => (activeRef in prev ? prev : { ...prev, [activeRef]: 0 }));
  }, [activeRef]);

  const handleSliceChange = useCallback(
    (idx: number) => {
      if (!activeRef) return;
      setCurrentSliceByRef((cs) => ({ ...cs, [activeRef]: idx }));
    },
    [activeRef],
  );

  // Resolve the preview payload to render based on (activeRef, activeSlice).
  //
  // #899 — when the requested slice is still loading, fall back to ANY
  // cached preview for this ref (slice 0 or the most recently-loaded
  // slice). This keeps ``<ImageViewer>`` mounted across slice
  // transitions, preserving its zoom/pan/LUT state. Without the
  // fallback, the transient null between slider drag and fetch
  // completion unmounts the component and resets all its useState.
  const preview: DataPreviewResponse | null = useMemo(() => {
    if (!activeRef) return null;
    // Try the exact slice the user is requesting.
    if (activeSlice === 0) {
      const slice0 = previewCache[activeRef];
      if (slice0) return slice0;
    } else if (activeSliceKey) {
      const sliceN = sliceCacheRef.current.get(activeSliceKey);
      if (sliceN) return sliceN;
    }
    // Stale-fallback: anything we have for this ref keeps the viewer alive.
    if (previewCache[activeRef]) return previewCache[activeRef];
    for (const [key, value] of sliceCacheRef.current.entries()) {
      if (key.startsWith(`${activeRef}#`)) return value;
    }
    return null;
    // sliceCacheVersion is intentionally listed to invalidate the memo
    // whenever a new slice lands in the local cache.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRef, activeSlice, activeSliceKey, previewCache, sliceCacheVersion]);

  // Has any preview at all loaded for the current ref? Used to decide
  // between the "Preview not loaded yet" placeholder and the viewer.
  const hasAnyPreviewForRef = preview !== null;

  const isLoadingActive =
    !!activeRef &&
    !hasAnyPreviewForRef &&
    (activeSlice === 0
      ? !!previewLoading[activeRef]
      : !!activeSliceKey && sliceFetchingRef.current.has(activeSliceKey));

  // ADR-043 FR-013 — OME metadata panel toggle.
  //
  // First try the cached preview's metadata (the preview endpoint already
  // returns `metadata` alongside `preview`). When absent, fall back to a
  // lazy `/api/data/{ref}` fetch the first time the user clicks the
  // "OME metadata" button.
  const previewMetadata = useMemo<Record<string, unknown> | null>(() => {
    if (!preview) return null;
    const md = (preview as unknown as { metadata?: Record<string, unknown> }).metadata;
    return md && typeof md === "object" ? md : null;
  }, [preview]);
  const previewOme = useMemo<OMETree | null>(
    () => extractOMEFromMetadata(previewMetadata),
    [previewMetadata],
  );
  const [omeOpen, setOmeOpen] = useState(false);
  const [fetchedOmeByRef, setFetchedOmeByRef] = useState<Record<string, OMETree | null>>({});
  const [omeFetching, setOmeFetching] = useState<Record<string, boolean>>({});
  const activeFetchedOme = activeRef ? (fetchedOmeByRef[activeRef] ?? null) : null;
  const activeOme = previewOme ?? activeFetchedOme;
  const omeAvailable = hasOMEContent(activeOme) || (!previewOme && activeRef != null);
  // Reset the open state when the active ref changes.
  useEffect(() => {
    setOmeOpen(false);
  }, [activeRef]);

  const handleOpenOme = useCallback(() => {
    setOmeOpen(true);
    if (!activeRef || previewOme) return;
    if (fetchedOmeByRef[activeRef] !== undefined) return;
    if (omeFetching[activeRef]) return;
    setOmeFetching((prev) => ({ ...prev, [activeRef]: true }));
    getOMEMetadata(activeRef)
      .then((ome) => {
        setFetchedOmeByRef((prev) => ({ ...prev, [activeRef]: ome }));
      })
      .catch(() => {
        setFetchedOmeByRef((prev) => ({ ...prev, [activeRef]: null }));
      })
      .finally(() => {
        setOmeFetching((prev) => ({ ...prev, [activeRef]: false }));
      });
  }, [activeRef, previewOme, fetchedOmeByRef, omeFetching]);

  return (
    <aside className="flex h-full flex-col overflow-hidden border-l border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(245,241,232,0.98))] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Preview</p>
          <h2 className="mt-2 font-display text-2xl text-ink">
            {selectedNodeId ? selectedNodeLabel : "Select a node"}
          </h2>
        </div>
      </div>

      {!selectedNodeId ? (
        <div className="mt-6 rounded-[1.8rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
          Pick a block to inspect its latest outputs and cached previews.
        </div>
      ) : outputRefs.length === 0 ? (
        <div className="mt-6 rounded-[1.8rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
          This block has no previewable outputs yet.
        </div>
      ) : (
        <>
          <div className="mt-5 flex flex-wrap gap-2">
            {refEntries.map((entry) => (
              <button
                className={`rounded-full px-3 py-1 text-xs ${activeRef === entry.ref ? "bg-ink text-white" : "bg-white text-stone-600"}`}
                key={entry.ref}
                onClick={() => setActiveRef(entry.ref)}
                title={entry.ref}
                type="button"
              >
                {entry.displayName}
              </button>
            ))}
          </div>
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            {isLoadingActive ? (
              <div className="rounded-[1.6rem] border border-stone-200 bg-white p-4 text-sm text-stone-500">
                Loading preview…
              </div>
            ) : preview && activeRef ? (
              <>
                <PreviewRenderer
                  preview={preview.preview}
                  dataRef={activeRef}
                  currentSlice={activeSlice}
                  onSliceChange={handleSliceChange}
                />
                {/* ADR-043 FR-013 — OME metadata browser. Always render the
                    button when a ref is active; the panel itself surfaces
                    a "No OME metadata" message when the underlying object
                    has none. */}
                {omeAvailable ? (
                  <div className="mt-3">
                    {!omeOpen ? (
                      <button
                        type="button"
                        className="rounded-full border border-stone-300 bg-white px-3 py-1 text-xs text-stone-600 hover:bg-stone-50"
                        onClick={handleOpenOme}
                        data-testid="open-ome-metadata"
                      >
                        OME metadata
                      </button>
                    ) : (
                      <OMEMetadataPanel ome={activeOme} onClose={() => setOmeOpen(false)} />
                    )}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="rounded-[1.6rem] border border-stone-200 bg-white p-4 text-sm text-stone-500">
                Preview not loaded yet.
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
