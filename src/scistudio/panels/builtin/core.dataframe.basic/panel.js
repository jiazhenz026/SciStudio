/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { DataFrameView } from "../../sdk/1/renderer-dataframe.js";
const api = window.scistudio;
const DEFAULT_PAGE_SIZE = 50;
export { formatCell, nextSort } from "../../sdk/1/renderer-dataframe.js";

function DataFramePanel({ initialView }) {
  const [query, setQuery] = useState({
    page: initialView.page ?? 1,
    pageSize: initialView.page_size ?? DEFAULT_PAGE_SIZE,
    sortBy: initialView.sort_by ?? null,
    sortDir: initialView.sort_dir ?? null,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = { page: query.page, page_size: query.pageSize };
    if (query.sortBy) {
      params.sort_by = query.sortBy;
      params.sort_dir = query.sortDir || "asc";
    }
    api
      .read("table.page", params)
      .then((page) => {
        if (cancelled) return;
        setData(page);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoading(false);
        fail(err);
      });
    return () => {
      cancelled = true;
    };
  }, [query, fail]);

  useEffect(() => {
    if (data)
      api.setViewState({
        page: data.page ?? query.page,
        page_size: data.page_size ?? query.pageSize,
        sort_by: data.sort?.by ?? null,
        sort_dir: data.sort?.direction ?? null,
      });
  }, [data, query]);
  return html`<${DataFrameView}
    data=${data}
    query=${query}
    loading=${loading}
    error=${error}
    onQueryChange=${setQuery}
  />`;
}

api
  .ready()
  .then(() => {
    const view =
      api.viewState && typeof api.viewState === "object" ? api.viewState : {};
    render(
      html`<${DataFramePanel} initialView=${view} />`,
      document.getElementById("root"),
    );
  })
  .catch((err) => api.reportError(String(err?.message || err)));
