/**
 * ADR-048 SPEC 1 — core fallback viewers (FR-012 .. FR-019).
 *
 * One viewer per {@link EnvelopeKind} plus the {@link CoreFallbackRenderer}
 * dispatcher the {@link PreviewHost} mounts when an envelope carries no
 * validated previewer manifest (or a dynamic previewer failed to load).
 *
 * These viewers read ONLY the bounded payload/metadata already on the
 * envelope (and, where interactive, the session helpers passed in). They are
 * deliberately generic:
 *   - `ArrayViewer` is GENERIC numeric inspection only — shape/dtype/axes,
 *     scalar / 1-D chart / 2-D numeric heatmap table (PyCharm-style: actual
 *     values + per-cell heatmap color + min..max legend), and a per-axis slice
 *     selector for every non-displayed dimension. It has NO image-domain
 *     LUT/OME/channel/label semantics (FR-013/FR-014); those belong to the
 *     imaging package.
 *
 * Each viewer renders the FR-011 metadata flags (sampled/truncated/...) so the
 * user always knows whether the displayed data is bounded.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Plot from "react-plotly.js";

import type { EnvelopeKind, PreviewEnvelope, PreviewResource } from "../../types/api";

import { TableViewer, type TableViewerInitial } from "./TableViewer";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

/** FR-011 status flag chips so the user always sees whether data is bounded. */
function MetadataBadges({ envelope }: { envelope: PreviewEnvelope }) {
  const m = envelope.metadata ?? {};
  const flags: Array<[string, boolean | undefined]> = [
    ["sampled", m.sampled],
    ["truncated", m.truncated],
    ["cached", m.cached],
    ["derived", m.derived],
    ["incomplete", m.complete === false],
  ];
  const active = flags.filter(([, on]) => on);
  if (active.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1" data-testid="preview-metadata-badges">
      {active.map(([label]) => (
        <span
          key={label}
          className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-800"
        >
          {label}
        </span>
      ))}
    </div>
  );
}

/** Non-fatal diagnostics emitted by the provider or the host. */
export function DiagnosticsBanner({ diagnostics }: { diagnostics: readonly string[] }) {
  if (!diagnostics || diagnostics.length === 0) return null;
  return (
    <div
      className="mb-2 rounded-[1rem] border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
      data-testid="preview-diagnostics"
      role="status"
    >
      {diagnostics.map((d, i) => (
        <p key={i}>{d}</p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DataFrame (FR-012) — reuses the paginated/sortable TableViewer
// ---------------------------------------------------------------------------

function readTableInitial(payload: Record<string, unknown>): TableViewerInitial {
  const rows = (payload.rows as Array<Record<string, unknown>> | undefined) ?? [];
  const pageSize = asNumber(payload.page_size, Math.max(rows.length, 1));
  const totalRows = asNumber(payload.total_rows, rows.length);
  const sortDir = payload.sort_dir;
  return {
    columns: (payload.columns as string[] | undefined) ?? [],
    rows,
    totalRows,
    page: asNumber(payload.page, 1),
    pageSize,
    totalPages: asNumber(
      payload.total_pages,
      Math.max(1, Math.ceil(totalRows / Math.max(pageSize, 1))),
    ),
    sortBy: typeof payload.sort_by === "string" ? payload.sort_by : null,
    sortDir: sortDir === "asc" || sortDir === "desc" ? sortDir : null,
  };
}

export function DataFrameViewer({ envelope }: { envelope: PreviewEnvelope }) {
  const initial = useMemo(() => readTableInitial(envelope.payload), [envelope.payload]);
  return (
    <div data-testid="core-dataframe-viewer">
      <TableViewer dataRef={envelope.target.ref} initial={initial} />
      <MetadataBadges envelope={envelope} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Array (FR-013 / FR-014) — GENERIC numeric only
//
// PyCharm-style numeric inspection: the displayed 2-D plane is rendered as a
// table of the ACTUAL numeric values, each cell heatmap-colored by a real
// colormap (diverging for signed data — negatives are NOT clipped), with a
// value-scale legend (min..max). Every non-displayed axis gets its own index
// picker so an N-D array is fully navigable. NO image-domain LUT/OME/channel/
// label semantics (those belong to the imaging package).
// ---------------------------------------------------------------------------

/** One non-displayed axis descriptor echoed by the backend. */
interface ArraySliceAxis {
  axis: number;
  name: string;
  size: number;
  index: number;
}

function readSliceAxes(payload: Record<string, unknown>): ArraySliceAxis[] {
  const raw = payload.slice_axes;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry) => {
      const r = asRecord(entry);
      return {
        axis: asNumber(r.axis, -1),
        name: asString(r.name, "axis"),
        size: asNumber(r.size, 0),
        index: asNumber(r.index, 0),
      };
    })
    .filter((a) => a.axis >= 0 && a.size > 0);
}

/**
 * Per-axis slice state. Each non-displayed axis is independently selectable;
 * changes are pushed to the session query as ``axis_indices`` (a map keyed by
 * axis position) plus a legacy ``slice_index`` for the first extra axis, and
 * the backend echoes the clamped selection back through ``slice_axes``.
 */
function useArraySlices(
  envelope: PreviewEnvelope,
  onPatchQuery?: (q: Record<string, unknown>) => void,
) {
  const sliceAxes = useMemo(() => readSliceAxes(envelope.payload), [envelope.payload]);
  const echoed = useMemo(() => {
    const m: Record<number, number> = {};
    for (const a of sliceAxes) m[a.axis] = a.index;
    return m;
  }, [sliceAxes]);
  const [indices, setIndices] = useState<Record<number, number>>(echoed);
  useEffect(() => {
    setIndices(echoed);
  }, [echoed]);

  const change = useCallback(
    (axis: number, idx: number) => {
      setIndices((prev) => {
        const next = { ...prev, [axis]: idx };
        const axisIndices: Record<string, number> = {};
        for (const [k, v] of Object.entries(next)) axisIndices[k] = v;
        const patch: Record<string, unknown> = { axis_indices: axisIndices };
        // Legacy single-axis control: keep ``slice_index`` in sync with the
        // first extra axis so the compatibility path stays consistent.
        if (sliceAxes.length > 0 && axis === sliceAxes[0].axis) {
          patch.slice_index = idx;
        }
        onPatchQuery?.(patch);
        return next;
      });
    },
    [onPatchQuery, sliceAxes],
  );

  return { sliceAxes, indices, change };
}

export function ArrayViewer({
  envelope,
  onPatchQuery,
}: {
  envelope: PreviewEnvelope;
  onPatchQuery?: (q: Record<string, unknown>) => void;
}) {
  const payload = envelope.payload;
  const shape = (payload.shape as number[] | undefined) ?? [];
  const dtype = asString(payload.dtype, "?");
  const axes = (payload.axes as string[] | undefined) ?? [];
  const ndim = asNumber(payload.ndim, shape.length);
  const { sliceAxes, indices, change } = useArraySlices(envelope, onPatchQuery);

  // Scalar (0-D) display — no raster, just the value.
  const isScalar = ndim === 0 || shape.length === 0;
  // 1-D — a generic line chart of the matrix row.
  const matrix = (payload.matrix ?? payload.thumbnail) as number[][] | number[] | undefined;
  const is1D = ndim === 1;
  const matrix2d = useMemo(() => to2D(matrix), [matrix]);
  const { vmin, vmax } = useMemo(() => resolveExtent(payload, matrix2d), [payload, matrix2d]);

  return (
    <div data-testid="core-array-viewer" className="space-y-2">
      <div
        className="flex flex-wrap items-center gap-2 rounded-[1rem] border border-stone-200 bg-white px-3 py-2 text-xs text-stone-600"
        data-testid="array-info"
      >
        <span className="font-medium text-ink">Array</span>
        <span>shape [{shape.join(", ")}]</span>
        <span>dtype {dtype}</span>
        {axes.length > 0 ? <span>axes [{axes.join(", ")}]</span> : null}
      </div>

      {isScalar ? (
        <div
          className="rounded-[1rem] border border-stone-200 bg-white p-4 text-sm"
          data-testid="array-scalar"
        >
          {String(scalarValue(matrix) ?? "")}
        </div>
      ) : is1D ? (
        <Array1DChart values={flatten1D(matrix)} />
      ) : (
        <>
          <ArrayHeatmapTable matrix={matrix2d} vmin={vmin} vmax={vmax} shape={shape} />
          <ArrayLegend vmin={vmin} vmax={vmax} />
        </>
      )}

      {/* Per-axis slice selectors — one index picker per non-displayed axis. */}
      {sliceAxes.length > 0 ? (
        <div className="space-y-1" data-testid="array-slice-selectors">
          {sliceAxes.map((ax) => {
            const value = indices[ax.axis] ?? ax.index;
            return (
              <div
                key={ax.axis}
                className="flex items-center gap-2 text-xs text-stone-600"
                data-testid={`array-slice-row-${ax.axis}`}
              >
                <span className="w-24 truncate">
                  {ax.name} ({ax.size})
                </span>
                <input
                  aria-label={`Slice along ${ax.name}`}
                  data-testid={`array-slice-slider-${ax.axis}`}
                  type="range"
                  min={0}
                  max={ax.size - 1}
                  value={value}
                  onChange={(e) => change(ax.axis, Number(e.target.value))}
                  className="flex-1"
                />
                <input
                  aria-label={`Index along ${ax.name}`}
                  data-testid={`array-slice-input-${ax.axis}`}
                  type="number"
                  min={0}
                  max={ax.size - 1}
                  value={value}
                  onChange={(e) => change(ax.axis, clampIndex(Number(e.target.value), ax.size))}
                  className="w-16 rounded border border-stone-300 bg-white px-1 py-0.5 text-right"
                />
                <span className="w-12 text-right">
                  {value + 1}/{ax.size}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}

      <MetadataBadges envelope={envelope} />
    </div>
  );
}

function clampIndex(value: number, size: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(Math.trunc(value), size - 1));
}

function scalarValue(matrix: number[][] | number[] | undefined): number | undefined {
  if (!Array.isArray(matrix)) return undefined;
  const first = matrix[0];
  if (Array.isArray(first)) return first[0];
  return first as number | undefined;
}

function flatten1D(matrix: number[][] | number[] | undefined): number[] {
  if (!Array.isArray(matrix)) return [];
  if (matrix.length > 0 && Array.isArray(matrix[0])) {
    return (matrix as number[][])[0] ?? [];
  }
  return matrix as number[];
}

/** Normalize a 1-D or 2-D payload matrix to a 2-D row-major array. */
function to2D(matrix: number[][] | number[] | undefined): number[][] {
  if (!Array.isArray(matrix)) return [];
  if (matrix.length === 0) return [];
  if (Array.isArray(matrix[0])) return matrix as number[][];
  return [matrix as number[]];
}

/** Resolve the value extent from the backend echo, falling back to the data. */
function resolveExtent(
  payload: Record<string, unknown>,
  matrix2d: number[][],
): { vmin: number; vmax: number } {
  const pMin = payload.vmin;
  const pMax = payload.vmax;
  if (
    typeof pMin === "number" &&
    typeof pMax === "number" &&
    Number.isFinite(pMin) &&
    Number.isFinite(pMax)
  ) {
    return { vmin: pMin, vmax: pMax };
  }
  let lo = Infinity;
  let hi = -Infinity;
  for (const row of matrix2d) {
    for (const v of row) {
      if (Number.isFinite(v)) {
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { vmin: 0, vmax: 1 };
  return { vmin: lo, vmax: hi };
}

/**
 * Map a value to an rgb() heatmap color. Signed extents use a diverging blue→
 * white→red scale centered at 0 (negatives stay distinct, never clipped to
 * black); all-nonnegative (or all-nonpositive) extents use a sequential
 * light→dark scale. NaN/inf render transparent.
 */
export function heatmapColor(value: number, vmin: number, vmax: number): string {
  if (!Number.isFinite(value)) return "transparent";
  const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
  if (vmin < 0 && vmax > 0) {
    // Diverging, centered at 0 with a symmetric magnitude so 0 is white.
    const mag = Math.max(Math.abs(vmin), Math.abs(vmax)) || 1;
    const t = Math.max(-1, Math.min(1, value / mag));
    if (t < 0) {
      const k = -t; // 0..1 toward blue
      return `rgb(${lerp(247, 33, k)}, ${lerp(247, 102, k)}, ${lerp(247, 172, k)})`;
    }
    const k = t; // 0..1 toward red
    return `rgb(${lerp(247, 178, k)}, ${lerp(247, 24, k)}, ${lerp(247, 43, k)})`;
  }
  // Sequential light→dark teal over [vmin, vmax].
  const span = vmax - vmin || 1;
  const t = Math.max(0, Math.min(1, (value - vmin) / span));
  return `rgb(${lerp(247, 8, t)}, ${lerp(252, 64, t)}, ${lerp(253, 129, t)})`;
}

/** Pick readable text color for a heatmap cell given its intensity. */
function cellTextColor(value: number, vmin: number, vmax: number): string {
  if (!Number.isFinite(value)) return "#94a3b8";
  const mag =
    vmin < 0 && vmax > 0 ? Math.max(Math.abs(vmin), Math.abs(vmax)) || 1 : vmax - vmin || 1;
  const intensity = vmin < 0 && vmax > 0 ? Math.abs(value) / mag : (value - vmin) / mag;
  return intensity > 0.6 ? "#f8fafc" : "#0f172a";
}

/** Format a numeric cell compactly but readably. */
export function formatCell(value: number): string {
  if (!Number.isFinite(value)) return Number.isNaN(value) ? "NaN" : value > 0 ? "∞" : "-∞";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (Number.isInteger(value) && abs < 1e6) return String(value);
  if (abs >= 1e5 || abs < 1e-3) return value.toExponential(2);
  return value.toFixed(3);
}

function Array1DChart({ values }: { values: number[] }) {
  return (
    <Plot
      className="w-full"
      data={[{ y: values, type: "scatter", mode: "lines", line: { color: "#f06a44" } }]}
      layout={{
        autosize: true,
        margin: { l: 30, r: 10, b: 30, t: 10 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
      }}
      style={{ width: "100%", height: "220px" }}
      useResizeHandler
    />
  );
}

/** PyCharm-style numeric heatmap: actual values + per-cell heatmap background. */
export function ArrayHeatmapTable({
  matrix,
  vmin,
  vmax,
  shape,
}: {
  matrix: number[][];
  vmin: number;
  vmax: number;
  shape: number[];
}) {
  const rows = matrix.length;
  const cols = matrix[0]?.length ?? 0;
  return (
    <div data-testid="array-2d-heatmap" className="space-y-1">
      <div className="max-h-80 overflow-auto rounded-[0.8rem] border border-stone-200 bg-white">
        <table className="border-collapse text-[10px] tabular-nums">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-10 bg-stone-100 px-1 py-0.5 text-stone-400" />
              {Array.from({ length: cols }, (_, c) => (
                <th
                  key={c}
                  className="sticky top-0 bg-stone-100 px-1 py-0.5 font-normal text-stone-400"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, r) => (
              <tr key={r}>
                <th className="sticky left-0 z-10 bg-stone-100 px-1 py-0.5 font-normal text-stone-400">
                  {r}
                </th>
                {row.map((value, c) => (
                  <td
                    key={c}
                    data-testid={`array-cell-${r}-${c}`}
                    title={String(value)}
                    className="whitespace-nowrap px-1 py-0.5 text-right"
                    style={{
                      backgroundColor: heatmapColor(value, vmin, vmax),
                      color: cellTextColor(value, vmin, vmax),
                    }}
                  >
                    {formatCell(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-[10px] text-stone-400" data-testid="array-grid-info">
        {shape.length ? `${shape.join(" × ")} | ` : ""}
        displaying {rows} × {cols}
      </div>
    </div>
  );
}

/** Min..max value-scale legend matching the heatmap colormap. */
export function ArrayLegend({ vmin, vmax }: { vmin: number; vmax: number }) {
  const stops = Array.from({ length: 9 }, (_, i) => {
    const v = vmin + ((vmax - vmin) * i) / 8;
    return heatmapColor(v, vmin, vmax);
  });
  const mid = vmin < 0 && vmax > 0 ? 0 : (vmin + vmax) / 2;
  return (
    <div className="flex items-center gap-2 text-[10px] text-stone-500" data-testid="array-legend">
      <span data-testid="array-legend-min">{formatCell(vmin)}</span>
      <div
        className="h-2 flex-1 rounded"
        style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }}
      />
      <span data-testid="array-legend-mid">{formatCell(mid)}</span>
      <span data-testid="array-legend-max">{formatCell(vmax)}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Series (FR-015) — chart + table modes, data already decimated by backend
// ---------------------------------------------------------------------------

export function SeriesViewer({ envelope }: { envelope: PreviewEnvelope }) {
  const payload = envelope.payload;
  const points = (payload.points as Array<{ x: number; y: number }> | undefined) ?? [];
  const table = asRecord(payload.table);
  const tableRows = (table.rows as Array<Record<string, unknown>> | undefined) ?? [];
  const [mode, setMode] = useState<"chart" | "table">("chart");
  return (
    <div data-testid="core-series-viewer" className="space-y-2">
      <div className="flex gap-1 text-xs">
        <button
          type="button"
          onClick={() => setMode("chart")}
          aria-pressed={mode === "chart"}
          className={`rounded-full px-3 py-0.5 ${mode === "chart" ? "bg-ink text-white" : "bg-white text-stone-600"}`}
        >
          Chart
        </button>
        <button
          type="button"
          onClick={() => setMode("table")}
          aria-pressed={mode === "table"}
          className={`rounded-full px-3 py-0.5 ${mode === "table" ? "bg-ink text-white" : "bg-white text-stone-600"}`}
        >
          Table
        </button>
      </div>
      {mode === "chart" ? (
        <Plot
          className="w-full"
          data={[
            {
              x: points.map((p) => p.x),
              y: points.map((p) => p.y),
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
          }}
          style={{ width: "100%", height: "260px" }}
          useResizeHandler
        />
      ) : (
        <div
          className="max-h-72 overflow-auto rounded-[1rem] border border-stone-200 bg-white"
          data-testid="series-table"
        >
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr>
                <th className="border-b border-stone-200 px-3 py-1">index</th>
                <th className="border-b border-stone-200 px-3 py-1">value</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((r, i) => (
                <tr key={i}>
                  <td className="border-b border-stone-100 px-3 py-1">{String(r.index ?? "")}</td>
                  <td className="border-b border-stone-100 px-3 py-1">{String(r.value ?? "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <MetadataBadges envelope={envelope} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Text (FR-016) — bounded, truncation marker, editor handoff
// ---------------------------------------------------------------------------

export function TextViewer({ envelope }: { envelope: PreviewEnvelope }) {
  const payload = envelope.payload;
  const content = asString(payload.content);
  const truncated = payload.truncated === true || envelope.metadata.truncated === true;
  const handoff = asRecord(payload.editor_handoff);
  return (
    <div data-testid="core-text-viewer" className="space-y-2">
      <pre className="max-h-80 overflow-auto rounded-[1rem] border border-stone-200 bg-white p-4 text-sm">
        {content}
      </pre>
      {truncated ? (
        <div
          className="flex items-center justify-between rounded-[1rem] border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          data-testid="text-truncation"
        >
          <span>
            Showing a bounded preview
            {typeof handoff.total_bytes === "number" ? ` of ${handoff.total_bytes} bytes` : ""}.
            Open in the editor to see the full content.
          </span>
        </div>
      ) : null}
      <MetadataBadges envelope={envelope} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Artifact — metadata + safe inline (data URI only, never remote)
// ---------------------------------------------------------------------------

export function ArtifactViewer({ envelope }: { envelope: PreviewEnvelope }) {
  const payload = envelope.payload;
  const path = asString(payload.path);
  const mime = asString(payload.mime_type, "application/octet-stream");
  const size = payload.size_bytes;
  const src = asString(payload.src);
  const inlineImage = src.startsWith("data:image/");
  return (
    <div
      data-testid="core-artifact-viewer"
      className="space-y-2 rounded-[1rem] border border-stone-200 bg-white p-4 text-sm text-stone-600"
    >
      <p className="font-medium text-ink">Artifact</p>
      <p className="break-all text-xs">{path}</p>
      <p className="text-xs">{mime}</p>
      {typeof size === "number" ? <p className="text-xs">{size} bytes</p> : null}
      {/* Only inline same-origin data URIs (FR-019 spirit: never load remote). */}
      {inlineImage ? (
        <img alt="Artifact preview" src={src} className="mt-2 max-h-72 rounded" />
      ) : null}
      <MetadataBadges envelope={envelope} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Composite (FR-017) — slot inventory first, child routed only on select
// ---------------------------------------------------------------------------

export function CompositeViewer({
  envelope,
  onOpenResource,
}: {
  envelope: PreviewEnvelope;
  onOpenResource?: (resource: PreviewResource) => void;
}) {
  const slots = asRecord(envelope.payload.slots);
  const slotResources = envelope.resources.filter((r) => r.resource_id.startsWith("slot:"));
  return (
    <div data-testid="core-composite-viewer" className="space-y-2">
      <p className="text-xs uppercase tracking-wider text-stone-500">
        {Object.keys(slots).length} slot{Object.keys(slots).length === 1 ? "" : "s"}
      </p>
      {Object.entries(slots).map(([name, typeName]) => {
        const resource = slotResources.find((r) => r.params?.slot === name);
        return (
          <button
            key={name}
            type="button"
            data-testid={`composite-slot-${name}`}
            onClick={() => (resource && onOpenResource ? onOpenResource(resource) : undefined)}
            className="flex w-full items-center justify-between rounded-2xl border border-stone-200 bg-white px-4 py-3 text-left hover:bg-stone-50"
          >
            <span>
              <span className="text-xs uppercase tracking-wider text-stone-500">{name}</span>
              <span className="mt-1 block text-sm text-ink">{String(typeName)}</span>
            </span>
            {resource && onOpenResource ? (
              <span className="text-xs text-stone-400">Preview →</span>
            ) : null}
          </button>
        );
      })}
      <MetadataBadges envelope={envelope} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collection (FR-009) — gallery/list of sampled item refs + child routing
// ---------------------------------------------------------------------------

export function CollectionViewer({
  envelope,
  onOpenResource,
}: {
  envelope: PreviewEnvelope;
  onOpenResource?: (resource: PreviewResource) => void;
}) {
  const payload = envelope.payload;
  const count = asNumber(payload.count, 0);
  const itemType = asString(payload.item_type, "items");
  const items = (payload.items as Array<Record<string, unknown>> | undefined) ?? [];
  const itemResources = envelope.resources.filter((r) => r.resource_id.startsWith("item:"));
  return (
    <div data-testid="core-collection-viewer" className="space-y-2">
      <p
        className="text-xs uppercase tracking-wider text-stone-500"
        data-testid="collection-summary"
      >
        {count} {itemType} (showing {items.length})
      </p>
      <div className="grid grid-cols-2 gap-2">
        {items.map((item, idx) => {
          const resource = itemResources[idx];
          const ref = asString(item.data_ref ?? item.ref, `item ${idx}`);
          return (
            <button
              key={idx}
              type="button"
              data-testid={`collection-item-${idx}`}
              onClick={() => (resource && onOpenResource ? onOpenResource(resource) : undefined)}
              className="rounded-2xl border border-stone-200 bg-white px-3 py-2 text-left text-xs hover:bg-stone-50"
            >
              <span className="block truncate text-ink">{ref}</span>
              <span className="text-stone-400">{asString(item.type_name, itemType)}</span>
            </button>
          );
        })}
      </div>
      <MetadataBadges envelope={envelope} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plot (FR-018 / FR-019) — PNG/JPEG/SVG/PDF, sandboxed SVG, export controls
// ---------------------------------------------------------------------------

export function PlotViewer({
  envelope,
  onExport,
}: {
  envelope: PreviewEnvelope;
  onExport?: (resource: PreviewResource) => void;
}) {
  const payload = envelope.payload;
  const format = asString(payload.format, "");
  const mime = asString(payload.mime_type, "application/octet-stream");
  const src = asString(payload.src);
  const svg = asString(payload.svg);
  const exportResource = envelope.resources.find((r) => r.resource_id === "export");

  return (
    <div data-testid="core-plot-viewer" className="space-y-2">
      <DiagnosticsBanner diagnostics={envelope.diagnostics} />
      <div className="rounded-[1rem] border border-stone-200 bg-white p-3">
        {format === "svg" && svg ? (
          // FR-019 — SVG is sanitized by the backend AND rendered in a
          // sandboxed iframe (no scripts, no same-origin) so nothing executes
          // in the app context even if sanitization missed something.
          <iframe
            data-testid="plot-svg-frame"
            title="Plot SVG"
            sandbox=""
            srcDoc={svg}
            className="h-72 w-full rounded border-0 bg-white"
          />
        ) : format === "pdf" && src ? (
          <iframe
            data-testid="plot-pdf-frame"
            title="Plot PDF"
            src={src}
            className="h-96 w-full rounded border-0"
          />
        ) : src ? (
          <img
            alt={`Plot ${format}`}
            data-testid="plot-image"
            src={src}
            className="max-h-96 w-full object-contain"
          />
        ) : (
          <p className="text-xs text-stone-500">No renderable plot artifact.</p>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-stone-600">
        <span className="uppercase tracking-wider text-stone-400">{format || mime}</span>
        <button
          type="button"
          data-testid="plot-export-button"
          aria-label={`Export plot as ${format || "file"}`}
          disabled={!exportResource}
          onClick={() => (exportResource && onExport ? onExport(exportResource) : undefined)}
          className="ml-auto rounded border border-stone-300 bg-white px-3 py-0.5 disabled:opacity-50"
        >
          Export / Save
        </button>
      </div>
      <MetadataBadges envelope={envelope} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error — typed error display (FR-029)
// ---------------------------------------------------------------------------

export function ErrorViewer({ envelope }: { envelope: PreviewEnvelope }) {
  const error = envelope.error;
  return (
    <div
      data-testid="core-error-viewer"
      className="space-y-1 rounded-[1rem] border border-red-300 bg-red-50 p-4 text-sm text-red-800"
      role="alert"
    >
      <p className="font-medium">Preview failed</p>
      {error ? (
        <>
          <p className="text-xs uppercase tracking-wider text-red-500">{String(error.code)}</p>
          <p className="text-xs">{error.message}</p>
        </>
      ) : (
        <p className="text-xs">An unknown preview error occurred.</p>
      )}
      <DiagnosticsBanner diagnostics={envelope.diagnostics} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dispatcher
// ---------------------------------------------------------------------------

export interface CoreFallbackRendererProps {
  envelope: PreviewEnvelope;
  /** Merge query state into the session and re-render (slice/page/sort/...). */
  onPatchQuery?: (query: Record<string, unknown>) => void;
  /** Open a child/slot/item resource (composite + collection child routing). */
  onOpenResource?: (resource: PreviewResource) => void;
  /** Export/save the displayed artifact (plot export controls). */
  onExport?: (resource: PreviewResource) => void;
}

/** Routes an envelope to the core fallback viewer for its {@link EnvelopeKind}. */
export function CoreFallbackRenderer({
  envelope,
  onPatchQuery,
  onOpenResource,
  onExport,
}: CoreFallbackRendererProps) {
  const kind: EnvelopeKind = envelope.kind;
  switch (kind) {
    case "dataframe":
      return <DataFrameViewer envelope={envelope} />;
    case "array":
      return <ArrayViewer envelope={envelope} onPatchQuery={onPatchQuery} />;
    case "series":
      return <SeriesViewer envelope={envelope} />;
    case "text":
      return <TextViewer envelope={envelope} />;
    case "artifact":
      return <ArtifactViewer envelope={envelope} />;
    case "composite":
      return <CompositeViewer envelope={envelope} onOpenResource={onOpenResource} />;
    case "collection":
      return <CollectionViewer envelope={envelope} onOpenResource={onOpenResource} />;
    case "plot":
      return <PlotViewer envelope={envelope} onExport={onExport} />;
    case "error":
      return <ErrorViewer envelope={envelope} />;
    default:
      return <ArtifactViewer envelope={envelope} />;
  }
}
