import { useState } from "react";

import { Button } from "../ui/button";
import type { PreviewEnvelope, PreviewResource } from "../../types/api";

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

// Canonical order the Save-as menu offers plot export formats in.
const PLOT_EXPORT_FORMAT_ORDER = ["svg", "pdf", "png", "jpeg"] as const;

// Formats the plot run actually rendered (approach B, #1918): the backend
// surfaces one sibling file per allowed format, so Save can produce a valid
// png/pdf/svg/jpeg without re-rendering. Falls back to the primary format when
// the list is absent (older runs / non-plot artifacts).
function availableFormats(payload: PreviewEnvelope["payload"]): string[] {
  const raw = payload?.available_formats;
  const found = new Set<string>();
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      if (typeof entry === "string" && entry) found.add(entry === "jpg" ? "jpeg" : entry);
    }
  }
  const primary = asString(payload?.format, "");
  if (primary) found.add(primary === "jpg" ? "jpeg" : primary);
  const ordered = PLOT_EXPORT_FORMAT_ORDER.filter((f) => found.has(f));
  return ordered.length > 0 ? ordered : primary ? [primary] : [];
}

// Build the export resource for a chosen format by overriding the descriptor's
// `format` param. The backend export resource resolves the sibling file for
// that format and returns valid bytes (or a clean error if it was not rendered).
function exportResourceForFormat(base: PreviewResource, format: string): PreviewResource {
  return { ...base, params: { ...(base.params ?? {}), format } };
}

// The surface sizes to the figure (no fixed height) so the plot fills the width
// with no large empty top/bottom margins, capped by max-height. A single
// overflow here handles pan when zoomed; the parent preview panel already
// scrolls, so we avoid the nested double-scrollbar.
const PLOT_PREVIEW_SURFACE_CLASS = "w-full max-h-[78vh] overflow-auto rounded bg-white";

// Aspect ratio (w/h) parsed from the SVG so the iframe can derive its height
// from its width and the figure fills the frame instead of leaving gaps.
function svgAspectRatio(svg: string): number | null {
  const vb = svg.match(/viewBox\s*=\s*["']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)/i);
  if (vb) {
    const w = parseFloat(vb[1]);
    const h = parseFloat(vb[2]);
    if (w > 0 && h > 0) return w / h;
  }
  const wMatch = svg.match(/\bwidth\s*=\s*["']([\d.]+)/i);
  const hMatch = svg.match(/\bheight\s*=\s*["']([\d.]+)/i);
  if (wMatch && hMatch) {
    const w = parseFloat(wMatch[1]);
    const h = parseFloat(hMatch[1]);
    if (w > 0 && h > 0) return w / h;
  }
  return null;
}

function buildSvgPreviewDocument(svg: string): string {
  // svg fills the iframe width; the iframe's aspect-ratio drives its height.
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body { width: 100%; margin: 0; padding: 0; background: white; }
      svg { display: block; width: 100%; height: auto; }
    </style>
  </head>
  <body>${svg}</body>
</html>`;
}

function buildPdfPreviewSrc(src: string): string {
  return src.includes("#") ? src : `${src}#view=Fit`;
}

function PlotMetadataBadges({ envelope }: { envelope: PreviewEnvelope }) {
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

function PlotDiagnosticsBanner({ diagnostics }: { diagnostics: readonly string[] }) {
  if (!diagnostics || diagnostics.length === 0) return null;
  return (
    <div
      className="mb-2 rounded-[1rem] border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
      data-testid="preview-diagnostics"
      role="status"
    >
      {diagnostics.map((d) => (
        <p key={d}>{d}</p>
      ))}
    </div>
  );
}

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
  const hasRenderable = Boolean((format === "svg" && svg) || (format === "pdf" && src) || src);
  const svgRatio = format === "svg" && svg ? svgAspectRatio(svg) : null;

  const formats = availableFormats(payload);
  // The format the user chose to save in. Defaults to the preview (preferred)
  // format so a plain Save keeps today's behaviour; the menu lets the user pick
  // any format the run rendered (approach B, #1918).
  const [saveFormat, setSaveFormat] = useState(format || formats[0] || "svg");
  const effectiveSaveFormat = formats.includes(saveFormat)
    ? saveFormat
    : formats[0] || format || "svg";
  const canSave = Boolean(exportResource) && formats.length > 0;

  const handleSave = () => {
    if (!exportResource || !onExport) return;
    onExport(exportResourceForFormat(exportResource, effectiveSaveFormat));
  };

  const [zoom, setZoom] = useState(1);
  // Clamp to a sensible range and snap to 25% steps.
  const applyZoom = (next: number) => setZoom(Math.min(4, Math.max(0.5, Math.round(next * 4) / 4)));

  return (
    <div data-testid="core-plot-viewer" className="space-y-2">
      <PlotDiagnosticsBanner diagnostics={envelope.diagnostics} />
      <div className="rounded-[1rem] border border-ink/10 bg-white p-3">
        <div className={PLOT_PREVIEW_SURFACE_CLASS} data-testid="plot-preview-surface">
          {/* Zoom layer: scale from the top-left so the whole figure stays
              reachable via the surface's scrollbars when zoomed in. At 100%
              the layer is the figure's natural size (no empty margins). SVG/PDF
              stay crisp because they are vector. */}
          <div
            className="w-full"
            style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }}
            data-testid="plot-zoom-layer"
          >
            {format === "svg" && svg ? (
              // SVG in a sandboxed iframe; height follows the figure's aspect
              // ratio so it fills the width without top/bottom gaps.
              <iframe
                data-testid="plot-svg-frame"
                title="Plot SVG"
                sandbox=""
                srcDoc={buildSvgPreviewDocument(svg)}
                className="block w-full border-0 bg-white"
                style={svgRatio ? { aspectRatio: String(svgRatio) } : { height: "70vh" }}
              />
            ) : format === "pdf" && src ? (
              <iframe
                data-testid="plot-pdf-frame"
                title="Plot PDF"
                src={buildPdfPreviewSrc(src)}
                className="block w-full border-0 bg-white"
                style={{ height: "70vh" }}
              />
            ) : src ? (
              <img
                alt={`Plot ${format}`}
                data-testid="plot-image"
                src={src}
                className="block w-full"
              />
            ) : (
              <p className="text-xs text-ink/60">No renderable plot artifact.</p>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs text-ink/70">
        <span className="uppercase tracking-wider text-ink/45">{format || mime}</span>
        {hasRenderable ? (
          <div className="flex items-center gap-1" data-testid="plot-zoom-controls">
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Zoom out"
              data-testid="plot-zoom-out"
              onClick={() => applyZoom(zoom - 0.25)}
              className="h-7 px-2"
            >
              −
            </Button>
            <span className="w-12 text-center tabular-nums" data-testid="plot-zoom-level">
              {Math.round(zoom * 100)}%
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Zoom in"
              data-testid="plot-zoom-in"
              onClick={() => applyZoom(zoom + 0.25)}
              className="h-7 px-2"
            >
              +
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Reset zoom"
              data-testid="plot-zoom-reset"
              onClick={() => setZoom(1)}
              className="h-7 px-2"
            >
              Reset
            </Button>
          </div>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          {formats.length > 1 ? (
            <select
              data-testid="plot-format-select"
              aria-label="Save format"
              value={effectiveSaveFormat}
              onChange={(e) => setSaveFormat(e.target.value)}
              className="h-7 rounded border border-ink/20 bg-white px-1 text-xs uppercase tracking-wider text-ink/70"
            >
              {formats.map((f) => (
                <option key={f} value={f}>
                  {f.toUpperCase()}
                </option>
              ))}
            </select>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="plot-export-button"
            aria-label={`Save plot as ${effectiveSaveFormat || "file"}`}
            disabled={!canSave}
            onClick={handleSave}
            className="h-7"
          >
            Save
          </Button>
        </div>
      </div>
      <PlotMetadataBadges envelope={envelope} />
    </div>
  );
}
