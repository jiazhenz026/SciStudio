/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { SeriesView, mergePages } from "../../sdk/1/renderer-series.js";
const api = window.scistudio;
export {
  gapNotice,
  readPoints,
  lineData,
  mergePages,
  toNumber,
} from "../../sdk/1/renderer-series.js";

/**
 * Where the next page starts, or null when there is no forward page to read:
 * either the series is fully read or the reader returned a `next_offset` that
 * does not move forward.
 */
export function nextPageOffset(page, current) {
  const next = page?.next_offset;
  return typeof next === "number" && next > current ? next : null;
}

function SeriesPanel({ initialView }) {
  const [mode, setMode] = useState(
    initialView.mode === "table" ? "table" : "chart",
  );
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  /*
   * Every row of the series, page by page (#2460). The chart and the table show
   * the whole series once the last page lands; until then the rows read so far
   * are shown and the view says how many of the total it holds. Nothing is
   * sampled to make a long series fit.
   */
  useEffect(() => {
    let cancelled = false;
    const pages = [];
    const readFrom = (offset) => {
      api
        .read("series.points", offset ? { offset } : {})
        .then((page) => {
          if (cancelled) return;
          pages.push(page);
          setData(mergePages(pages));
          if (page?.next_offset == null) {
            setLoading(false);
            return;
          }
          const next = nextPageOffset(page, offset);
          // A reader that cannot advance is a failure, not the end of the data.
          if (next === null) throw new Error("The series read did not advance");
          readFrom(next);
        })
        .catch((err) => {
          if (!cancelled) fail(err);
        });
    };
    readFrom(0);
    return () => {
      cancelled = true;
    };
  }, [fail]);

  useEffect(() => {
    api.setViewState({ mode });
  }, [mode]);

  return html`<${SeriesView}
    data=${data}
    loading=${loading}
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
