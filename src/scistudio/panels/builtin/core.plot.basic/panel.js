/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { PlotView } from "../../sdk/1/renderer-plot.js";
const api = window.scistudio;
import { clampZoom, formatOf, saveName } from "../../sdk/1/renderer-plot.js";
export { clampZoom, formatOf, saveName };

function PlotPanel({ initialView }) {
  const [info, setInfo] = useState(null);
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(clampZoom(initialView.zoom ?? 1));
  const [saveFormat, setSaveFormat] = useState(initialView.save_format ?? null);
  const [page, setPage] = useState(1);
  const [saving, setSaving] = useState(false);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .read("artifact.info", {})
      .then((result) => {
        if (cancelled) return null;
        setInfo(result);
        return api.read("artifact.file", {});
      })
      .then((result) => {
        if (!cancelled && result) setFile(result);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      });
    return () => {
      cancelled = true;
    };
  }, [fail]);

  const onZoom = useCallback((next) => setZoom(clampZoom(next)), []);

  useEffect(() => {
    if (!info) return;
    api.setViewState({ zoom, save_format: saveFormat });
  }, [info, zoom, saveFormat]);

  const fmt = formatOf(file?.mime_type || info?.mime_type, info?.name);
  const formats =
    Array.isArray(info?.formats) && info.formats.length
      ? info.formats
      : fmt
        ? [fmt]
        : [];
  const chosen = formats.includes(saveFormat) ? saveFormat : formats[0] || fmt;

  const save = useCallback(() => {
    if (!chosen || saving) return;
    setSaving(true);
    /*
     * The bytes already in hand are the format being displayed. Saving any
     * other one asks for that file by name rather than relabelling these bytes,
     * which is what would produce a .pdf that is really a PNG.
     */
    const bytes =
      chosen === fmt && file?.data instanceof ArrayBuffer
        ? Promise.resolve(file)
        : api.read("artifact.file", { variant: chosen });
    bytes
      .then((variant) => {
        if (!(variant?.data instanceof ArrayBuffer))
          throw new Error("No bytes to save");
        return api.save({
          name: saveName(info?.name, chosen),
          mime: variant.mime_type || "application/octet-stream",
          data: variant.data.slice(0),
        });
      })
      .catch((err) => api.reportError(String(err?.message || err)))
      .then(() => setSaving(false));
  }, [chosen, fmt, file, info, saving]);

  return html`<${PlotView}
    info=${info}
    file=${file}
    zoom=${zoom}
    onZoom=${onZoom}
    saveFormat=${saveFormat}
    onSaveFormatChange=${setSaveFormat}
    page=${page}
    onPageChange=${setPage}
    saving=${saving}
    onSave=${save}
    error=${error}
    libBaseUrl=${api.libBaseUrl}
  />`;
}

api
  .ready()
  .then(() => {
    const view =
      api.viewState && typeof api.viewState === "object" ? api.viewState : {};
    render(
      html`<${PlotPanel} initialView=${view} />`,
      document.getElementById("root"),
    );
  })
  .catch((err) => api.reportError(String(err?.message || err)));
