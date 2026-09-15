/* Reusable core presentation. Host reads and persistence stay in the caller. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import {
  Button,
  ErrorState,
  LoadingState,
  Panel,
  Row,
  Select,
  Spacer,
} from "./panel-ui.js";

const PDFJS_VERSION = "5.4.149";

/** Formats that render as a plain image. */
const IMAGE_FORMATS = new Set(["png", "jpeg", "jpg", "gif", "webp", "svg"]);

/** The canonical format of the file being shown. */
export function formatOf(mime, name) {
  const value = (mime || "").toLowerCase();
  if (value.includes("pdf")) return "pdf";
  if (value.includes("svg")) return "svg";
  if (value.includes("png")) return "png";
  if (value.includes("jpeg") || value.includes("jpg")) return "jpeg";
  if (value.includes("gif")) return "gif";
  if (value.includes("webp")) return "webp";
  const suffix = ((name || "").split(".").pop() || "").toLowerCase();
  return suffix === "jpg" ? "jpeg" : suffix;
}

/** Clamp to the viewer's range and snap to its 25% steps. */
export function clampZoom(value) {
  return Math.min(4, Math.max(0.5, Math.round(value * 4) / 4));
}

/** The file name a save in *fmt* should carry. */
export function saveName(name, fmt) {
  const base = (name || "plot").replace(/\.[^.]*$/, "") || "plot";
  return `${base}.${fmt === "jpeg" ? "jpg" : fmt}`;
}

function ZoomControls({ zoom, onZoom }) {
  return html`<span class="plot-zoom" data-testid="plot-zoom-controls">
    <${Button} aria-label="Zoom out" onClick=${() => onZoom(zoom - 0.25)}>−<//>
    <span class="plot-zoom-level" data-testid="plot-zoom-level"
      >${Math.round(zoom * 100)}%</span
    >
    <${Button} aria-label="Zoom in" onClick=${() => onZoom(zoom + 0.25)}>+<//>
    <${Button} aria-label="Reset zoom" onClick=${() => onZoom(1)}>Reset<//>
  </span>`;
}

/**
 * A PDF, one page at a time, with the page count always visible.
 *
 * `onPages` reports the document's length upward so the pager can exist outside
 * the canvas — a reader has to be able to see that there are more pages before
 * deciding whether to look for them.
 */
function PdfPage({ data, page, onPages, onFail, libBaseUrl }) {
  const canvas = useRef(null);
  useEffect(() => {
    let cancelled = false;
    const base = libBaseUrl;
    if (!base) {
      onFail("The PDF renderer is unavailable in this context.");
      return;
    }
    if (!(data instanceof ArrayBuffer)) {
      onFail("The PDF bytes were not delivered.");
      return;
    }
    import(`${base}pdfjs@${PDFJS_VERSION}/build/pdf.min.mjs`)
      .then((pdfjs) => {
        pdfjs.GlobalWorkerOptions.workerSrc = `${base}pdfjs@${PDFJS_VERSION}/build/pdf.worker.min.mjs`;
        return pdfjs.getDocument({ data: new Uint8Array(data.slice(0)) })
          .promise;
      })
      .then((document_) => {
        if (cancelled) return null;
        onPages(document_.numPages);
        return document_.getPage(Math.min(page, document_.numPages));
      })
      .then((rendered) => {
        if (cancelled || !rendered || !canvas.current) return null;
        const viewport = rendered.getViewport({ scale: 1.5 });
        canvas.current.width = viewport.width;
        canvas.current.height = viewport.height;
        return rendered.render({
          canvasContext: canvas.current.getContext("2d"),
          viewport,
        }).promise;
      })
      .catch((err) => {
        if (!cancelled)
          onFail(`Could not render the PDF: ${err?.message || err}`);
      });
    return () => {
      cancelled = true;
    };
  }, [data, page, onPages, onFail, libBaseUrl]);
  return html`<canvas data-testid="plot-pdf-canvas" ref=${canvas}></canvas>`;
}

export function PlotView({
  info,
  file,
  zoom = 1,
  onZoom = () => {},
  saveFormat,
  onSaveFormatChange = () => {},
  page = 1,
  onPageChange = () => {},
  saving = false,
  onSave,
  error,
  libBaseUrl,
}) {
  const [pdfError, setPdfError] = useState(null);
  const [pages, setPages] = useState(1);
  const onPages = useCallback((count) => setPages(count), []);
  useLayoutEffect(() => {
    setPdfError(null);
    setPages(1);
  }, [file]);
  const fmt = formatOf(file?.mime_type || info?.mime_type, info?.name);
  const formats =
    Array.isArray(info?.formats) && info.formats.length
      ? info.formats
      : fmt
        ? [fmt]
        : [];
  const chosen = formats.includes(saveFormat) ? saveFormat : formats[0] || fmt;

  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read plot: ${error}<//><//>`;
  }
  if (!info) {
    return html`<${Panel}><${LoadingState}>Loading plot…<//><//>`;
  }

  const isPdf = fmt === "pdf";
  const isImage = IMAGE_FORMATS.has(fmt);
  const renderable =
    Boolean(file) && (isPdf ? !pdfError : isImage && Boolean(file.url));

  return html`<${Panel}>
    <div class="plot-surface" data-testid="plot-surface">
      <div
        class="plot-zoom-layer"
        style=${`transform:scale(${zoom})`}
        data-testid="plot-zoom-layer"
      >
        ${!file
          ? html`<${LoadingState}>Loading figure…<//>`
          : isPdf
            ? pdfError
              ? html`<div class="plot-note" data-testid="plot-unrenderable">
                  ${pdfError}
                </div>`
              : html`<${PdfPage}
                  data=${file.data}
                  page=${page}
                  onPages=${onPages}
                  onFail=${setPdfError}
                  libBaseUrl=${libBaseUrl}
                />`
            : isImage && file.url
              ? html`<img
                  class="plot-image"
                  data-testid="plot-image"
                  src=${file.url}
                  alt=${`Plot ${fmt}`}
                />`
              : html`<div class="plot-note" data-testid="plot-unrenderable">
                  No renderable plot artifact (${fmt || "unknown format"}).
                </div>`}
      </div>
    </div>
    ${isPdf && !pdfError && pages > 1
      ? html`<${Row} class="plot-pages" data-testid="plot-pdf-pager">
          <${Button}
            aria-label="Previous page"
            disabled=${page <= 1}
            onClick=${() => onPageChange(page - 1)}
            >‹<//
          >
          <span data-testid="plot-pdf-page">Page ${page} of ${pages}</span>
          <${Button}
            aria-label="Next page"
            disabled=${page >= pages}
            onClick=${() => onPageChange(page + 1)}
            >›<//
          >
        <//>`
      : null}
    <${Row} class="plot-bar">
      <span class="plot-format">${fmt || info.mime_type || ""}</span>
      ${renderable
        ? html`<${ZoomControls}
            zoom=${zoom}
            onZoom=${(value) => onZoom(clampZoom(value))}
          />`
        : null}
      <${Spacer} />
      ${formats.length > 1
        ? html`<${Select}
            class="plot-format-select"
            data-testid="plot-format-select"
            aria-label="Save format"
            value=${chosen}
            onChange=${(e) => onSaveFormatChange(e.target.value)}
            options=${formats.map((f) => ({
              value: f,
              label: f.toUpperCase(),
            }))}
          />`
        : null}
      <${Button}
        data-testid="plot-export-button"
        data-tutorial-target="plot_export_button"
        aria-label=${`Save plot as ${chosen || "file"}`}
        disabled=${!onSave || !chosen || saving}
        onClick=${() => onSave?.(chosen)}
        >Save<//
      >
    <//>
  <//>`;
}
