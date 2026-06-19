import type { PreviewEnvelope, PreviewResource } from "../../types/api";

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

const PLOT_PREVIEW_SURFACE_CLASS =
  "flex h-[min(62vh,36rem)] min-h-64 w-full items-center justify-center overflow-hidden rounded bg-white";

function buildSvgPreviewDocument(svg: string): string {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html,
      body {
        width: 100%;
        height: 100%;
        margin: 0;
        overflow: hidden;
        background: white;
      }
      body {
        display: flex;
        align-items: center;
        justify-content: center;
      }
      svg {
        display: block;
        max-width: 100%;
        max-height: 100%;
        width: auto;
        height: auto;
      }
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

  return (
    <div data-testid="core-plot-viewer" className="space-y-2">
      <PlotDiagnosticsBanner diagnostics={envelope.diagnostics} />
      <div className="rounded-[1rem] border border-stone-200 bg-white p-3">
        <div className={PLOT_PREVIEW_SURFACE_CLASS} data-testid="plot-preview-surface">
          {format === "svg" && svg ? (
            // SVG is rendered in a sandboxed iframe; the wrapper document keeps
            // the figure contained instead of letting the iframe scroll.
            <iframe
              data-testid="plot-svg-frame"
              title="Plot SVG"
              sandbox=""
              srcDoc={buildSvgPreviewDocument(svg)}
              className="h-full w-full border-0 bg-white"
            />
          ) : format === "pdf" && src ? (
            <iframe
              data-testid="plot-pdf-frame"
              title="Plot PDF"
              src={buildPdfPreviewSrc(src)}
              className="h-full w-full border-0 bg-white"
            />
          ) : src ? (
            <img
              alt={`Plot ${format}`}
              data-testid="plot-image"
              src={src}
              className="h-full w-full object-contain"
            />
          ) : (
            <p className="text-xs text-stone-500">No renderable plot artifact.</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs text-stone-600">
        <span className="uppercase tracking-wider text-stone-400">{format || mime}</span>
        <button
          type="button"
          data-testid="plot-export-button"
          aria-label={`Save plot as ${format || "file"}`}
          disabled={!exportResource}
          onClick={() => (exportResource && onExport ? onExport(exportResource) : undefined)}
          className="ml-auto rounded border border-stone-300 bg-white px-3 py-0.5 disabled:opacity-50"
        >
          Save
        </button>
      </div>
      <PlotMetadataBadges envelope={envelope} />
    </div>
  );
}
