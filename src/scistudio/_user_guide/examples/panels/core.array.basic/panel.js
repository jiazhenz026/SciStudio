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

export function resolveAxisIndices(sliceAxes, chosen) {
  const resolved = {};
  for (const axis of sliceAxes || []) {
    const picked = (chosen || {})[axis.axis];
    resolved[axis.axis] = typeof picked === "number" ? picked : axis.index;
  }
  return resolved;
}

/**
 * The first non-displayed axis's selection, in the backend's own axis order.
 *
 * ``Object.keys`` order is not that order once an axis is missing, and this is
 * the value the backend applies when it has to default one.
 */
export function firstAxisIndex(sliceAxes, resolved) {
  const first = (sliceAxes || [])[0];
  if (!first) return 0;
  const picked = (resolved || {})[first.axis];
  return typeof picked === "number" ? picked : first.index;
}

/**
 * Run one job at a time, keeping only the latest of those that arrive meanwhile.
 *
 * A range input emits an event per pointer move and each plane read is
 * expensive, so a drag must not become a queue of reads for positions the
 * pointer has already left. A failed job releases the queue like a successful
 * one: a read that errors must not freeze every later move.
 */
export function coalescingQueue(run) {
  let busy = false;
  let queued = null;
  const start = (value) => {
    busy = true;
    // Started now, not on the next microtask: the first move of a drag should
    // reach the reader immediately, and only what follows it needs collapsing.
    let running;
    try {
      running = run(value);
    } catch {
      running = undefined;
    }
    Promise.resolve(running)
      .then(
        () => undefined,
        () => undefined,
      )
      .then(() => {
        const next = queued;
        queued = null;
        if (next !== null) start(next);
        else busy = false;
      });
  };
  return (value) => {
    if (busy) {
      queued = value;
      return;
    }
    start(value);
  };
}

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
  // A tile read is cheap and scroll-driven, so only the newest response is
  // applied. A plane read is not; see `readPlane` for why it is serialised.
  const tileReq = useRef(0);

  const meta = useMemo(() => (plane ? planeMeta(plane) : null), [plane]);
  const sliceAxes = plane?.slice_axes ?? [];
  // The queue outlives any one render, so the axis order it resolves against is
  // read through a ref rather than captured when the queue was built.
  const sliceAxesRef = useRef(sliceAxes);
  sliceAxesRef.current = sliceAxes;
  /*
   * Every non-displayed axis, with the reader's choice where they made one and
   * the read's own echo where they did not. Sending a partial set left the
   * backend to fill the first non-displayed axis from `slice_index`, so moving
   * any *other* axis moved that one to the same position and showed a different
   * plane — real values from somewhere the reader had not asked for.
   */
  const axisIndices = useMemo(
    () => resolveAxisIndices(sliceAxes, indices),
    [sliceAxes, indices],
  );
  const firstIndex = useMemo(
    () => firstAxisIndex(sliceAxes, axisIndices),
    [sliceAxes, axisIndices],
  );

  /*
   * One plane read at a time, and only the latest position still wanted.
   *
   * Reading a plane is not cheap: the backend scans it to find the real extrema
   * for the legend, which for a large array is the whole plane. A range input
   * emits an event per pointer move, so a read per event put dozens of
   * whole-plane scans in flight at once — enough to saturate the reader and, on
   * a large enough array, to exhaust memory. Dropping stale *responses* did not
   * help: the work had already been started.
   */
  const planeQueue = useRef(null);
  const readPlane = useCallback(
    (selection) => {
      if (!planeQueue.current) {
        planeQueue.current = coalescingQueue((wanted) =>
          api
            .read("array.plane", {
              slice_index: firstAxisIndex(sliceAxesRef.current, wanted),
              axis_indices: wanted,
            })
            .then(
              (p) => {
                setPlane(p);
                setError(null);
              },
              (err) => fail(err),
            ),
        );
      }
      planeQueue.current(selection);
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
    readPlane(axisIndices);
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
          axis_indices: axisIndices,
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
