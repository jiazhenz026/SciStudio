/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { SeriesView } from "../../sdk/1/renderer-series.js";
const api = window.scistudio;
export {
  gapNotice,
  readPoints,
  lineData,
  inferSourceIndices,
} from "../../sdk/1/renderer-series.js";

function SeriesPanel({ initialView }) {
  const [mode, setMode] = useState(
    initialView.mode === "table" ? "table" : "chart",
  );
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .read("series.points", {})
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      });
    return () => {
      cancelled = true;
    };
  }, [fail]);

  useEffect(() => {
    api.setViewState({ mode });
  }, [mode]);

  return html`<${SeriesView}
    data=${data}
    mode=${mode}
    onModeChange=${setMode}
    error=${error}
  />`;
}

api
  .ready()
  .then(() => {
    const view =
      api.viewState && typeof api.viewState === "object" ? api.viewState : {};
    render(
      html`<${SeriesPanel} initialView=${view} />`,
      document.getElementById("root"),
    );
  })
  .catch((err) => api.reportError(String(err?.message || err)));
