/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { ArrayView } from "../../sdk/1/renderer-array.js";
const api = window.scistudio;
const VIEWPORT = 320;
const OVERSCAN = 8;
const COL_W = 44;
const ROW_H = 19;
const TILE_CAP = 256;
import {
  planeMeta,
  formatCell,
  heatmapColor,
  displayAxes,
} from "../../sdk/1/renderer-array.js";
export { formatCell, heatmapColor, displayAxes };

function ArrayPanel({ initialView }) {
  const [plane, setPlane] = useState(null);
  const [tile, setTile] = useState(null);
  const [error, setError] = useState(null);
  // A failed read is shown here AND reported to the host: the surrounding
  // preview shell offers the remount / core-preview recovery on that signal.
  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);
  const [indices, setIndices] = useState(initialView.axis_indices || {});
  const [rowHeight, setRowHeight] = useState(ROW_H);

  const scrollRef = useRef(null);
  const scrollPos = useRef({
    top: initialView.scrollTop || 0,
    left: initialView.scrollLeft || 0,
  });
  // Only the newest response is applied, and at most one read of each kind is in
  // flight, so dragging an axis tracks the pointer instead of queueing a
  // round-trip per intermediate index.
  const planeReq = useRef(0);
  const tileReq = useRef(0);

  const meta = useMemo(() => (plane ? planeMeta(plane) : null), [plane]);
  const sliceAxes = plane?.slice_axes ?? [];
  const firstIndex = useMemo(() => {
    const keys = Object.keys(indices);
    return keys.length ? indices[keys[0]] : 0;
  }, [indices]);

  const readPlane = useCallback(
    (axisIndices) => {
      const req = ++planeReq.current;
      const keys = Object.keys(axisIndices);
      const slice = keys.length ? axisIndices[keys[0]] : 0;
      api
        .read("array.plane", { slice_index: slice, axis_indices: axisIndices })
        .then((p) => {
          if (req === planeReq.current) {
            setPlane(p);
            setError(null);
          }
        })
        .catch((err) => {
          if (req === planeReq.current) fail(err);
        });
    },
    [fail],
  );

  const readTile = useCallback(() => {
    if (!meta || meta.scalar) return;
    const box = scrollRef.current;
    const maxRow = Math.max(0, meta.rows - 1);
    const maxCol = Math.max(0, meta.cols - 1);
    const firstRow = Math.max(
      0,
      Math.min(
        Math.floor(scrollPos.current.top / rowHeight) - OVERSCAN,
        maxRow,
      ),
    );
    const firstCol = Math.max(
      0,
      Math.min(Math.floor(scrollPos.current.left / COL_W) - OVERSCAN, maxCol),
    );
    const visRows =
      Math.ceil((box?.clientHeight || VIEWPORT) / rowHeight) + 2 * OVERSCAN;
    const visCols = Math.ceil((box?.clientWidth || 480) / COL_W) + 2 * OVERSCAN;
    const height = Math.max(
      1,
      Math.min(TILE_CAP, visRows, meta.rows - firstRow),
    );
    const width = Math.max(
      1,
      Math.min(TILE_CAP, visCols, meta.cols - firstCol),
    );
    const req = ++tileReq.current;
    api
      .read("array.tile", {
        y0: firstRow,
        x0: firstCol,
        height,
        width,
        slice_index: firstIndex,
        axis_indices: indices,
      })
      .then((t) => {
        if (req === tileReq.current) setTile(t);
      })
      .catch((err) => {
        if (req === tileReq.current) fail(err);
      });
  }, [meta, rowHeight, firstIndex, indices, fail]);

  // First read, and a re-read whenever the selected slice changes.
  useEffect(() => {
    readPlane(indices);
  }, [indices, readPlane]);

  // The plane defines the geometry; load the window it exposes. A 0-D source has
  // exactly one cell, so read that instead of a window.
  useEffect(() => {
    if (!meta) return;
    if (meta.scalar) {
      const req = ++tileReq.current;
      api
        .read("array.tile", {
          y0: 0,
          x0: 0,
          height: 1,
          width: 1,
          slice_index: firstIndex,
          axis_indices: indices,
        })
        .then((t) => {
          if (req === tileReq.current) setTile(t);
        })
        .catch((err) => {
          if (req === tileReq.current) fail(err);
        });
      return;
    }
    readTile();
  }, [meta]); // eslint-disable-line react-hooks/exhaustive-deps

  // Measure a real row once so the spacer heights match the rendered rows.
  useLayoutEffect(() => {
    const row = scrollRef.current?.querySelector("tbody tr[data-row]");
    const measured = row instanceof HTMLElement ? row.offsetHeight : 0;
    if (measured > 0 && measured !== rowHeight) setRowHeight(measured);
  }, [tile, rowHeight]);

  // Restore the scroll offset after the geometry is known.
  useLayoutEffect(() => {
    const box = scrollRef.current;
    if (!box) return;
    if (box.scrollTop !== scrollPos.current.top)
      box.scrollTop = scrollPos.current.top;
    if (box.scrollLeft !== scrollPos.current.left)
      box.scrollLeft = scrollPos.current.left;
  }, [meta]);

  useEffect(() => {
    api.setViewState({
      axis_indices: indices,
      scrollTop: scrollPos.current.top,
      scrollLeft: scrollPos.current.left,
    });
  }, [indices, tile]);

  const onScroll = useCallback(
    (e) => {
      scrollPos.current = {
        top: e.currentTarget.scrollTop,
        left: e.currentTarget.scrollLeft,
      };
      readTile();
    },
    [readTile],
  );

  const onSliceChange = useCallback((axis, index) => {
    scrollPos.current = { top: 0, left: 0 };
    setIndices((prev) =>
      prev[axis] === index ? prev : { ...prev, [axis]: index },
    );
  }, []);

  return html`<${ArrayView}
    plane=${plane}
    tile=${tile}
    indices=${indices}
    onSliceChange=${onSliceChange}
    rowHeight=${rowHeight}
    onScroll=${onScroll}
    scrollRef=${scrollRef}
    error=${error}
  />`;
}

api
  .ready()
  .then(() => {
    const view =
      api.viewState && typeof api.viewState === "object" ? api.viewState : {};
    render(
      html`<${ArrayPanel} initialView=${view} />`,
      document.getElementById("root"),
    );
  })
  .catch((err) => api.reportError(String(err?.message || err)));

window.__panel = { formatCell, heatmapColor, displayAxes };
