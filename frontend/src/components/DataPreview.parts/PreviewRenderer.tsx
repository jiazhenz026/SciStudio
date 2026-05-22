import Plot from "react-plotly.js";

import { ImageViewer } from "./ImageViewer";
import { TableViewer, readTablePayload } from "./TableViewer";

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

function renderImagePreview(
  preview: Record<string, unknown>,
  currentSlice: number | undefined,
  onSliceChange: ((idx: number) => void) | undefined,
) {
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

function renderChartPreview(preview: Record<string, unknown>) {
  const points = preview.points as Array<{ x: number; y: number }> | undefined;
  return (
    <Plot
      className="w-full"
      data={[
        {
          x: points?.map((point) => point.x) ?? [],
          y: points?.map((point) => point.y) ?? [],
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
}

function renderTextPreview(preview: Record<string, unknown>) {
  return (
    <pre className="max-h-80 overflow-auto rounded-[1.4rem] border border-stone-200 bg-white p-4 text-sm">
      {String(preview.content ?? "")}
    </pre>
  );
}

function renderCompositePreview(preview: Record<string, unknown>) {
  const slots = (preview.slots as Record<string, unknown> | undefined) ?? {};
  return (
    <div className="space-y-2">
      {Object.entries(slots).map(([slot, value]) => (
        <div className="rounded-2xl border border-stone-200 bg-white px-4 py-3" key={slot}>
          <p className="text-xs uppercase tracking-[0.25em] text-stone-500">{slot}</p>
          <p className="mt-1 text-sm text-ink">{String(value)}</p>
        </div>
      ))}
    </div>
  );
}

function renderArtifactPreview(preview: Record<string, unknown>) {
  return (
    <div className="rounded-[1.4rem] border border-stone-200 bg-white p-4 text-sm text-stone-600">
      <p>Artifact preview</p>
      <p className="mt-2 text-xs">{String(preview.path ?? "")}</p>
      <p className="text-xs">{String(preview.mime_type ?? "")}</p>
    </div>
  );
}

export function PreviewRenderer({
  preview,
  dataRef,
  currentSlice,
  onSliceChange,
}: PreviewRendererProps) {
  switch (preview.kind) {
    case "table":
      return <TableViewer key={dataRef} dataRef={dataRef} initial={readTablePayload(preview)} />;
    case "image":
      return renderImagePreview(preview, currentSlice, onSliceChange);
    case "chart":
      return renderChartPreview(preview);
    case "text":
      return renderTextPreview(preview);
    case "composite":
      return renderCompositePreview(preview);
    default:
      return renderArtifactPreview(preview);
  }
}
