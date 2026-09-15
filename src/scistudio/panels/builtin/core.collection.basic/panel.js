/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { CollectionView } from "../../sdk/1/renderer-collection.js";
const api = window.scistudio;
export { itemLabel } from "../../sdk/1/renderer-collection.js";

function CollectionPanel({ input }) {
  const [items, setItems] = useState(() => [...(input.items ?? [])]);
  const [cursor, setCursor] = useState(input.next_cursor ?? null);
  const [loading, setLoading] = useState(false);
  // Guards the request itself, which a state flag cannot: two presses in the
  // same tick both see the old state and both start a read.
  const loadingRef = useRef(false);
  const [error, setError] = useState(null);

  const count = typeof input.count === "number" ? input.count : items.length;
  const itemType = input.item_type || "items";

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  /*
   * Every item is reachable, one page at a time.
   *
   * The viewer this replaces stopped at the first hundred and flagged the rest
   * as "sampled" — a collection whose tail the reader could not get to at all
   * (#1886 item B). Chasing the cursor to the end instead makes every item
   * reachable, but for a collection of tens of thousands it is an unbounded
   * run of requests, an unbounded backend child-authority cache, and an
   * unbounded grid: reachable in principle, unusable in practice.
   *
   * So the reader asks for the next page. Nothing is hidden — the count says
   * how many there are and how many are on screen — and nothing is fetched that
   * nobody looked for.
   */
  const loadMore = useCallback(() => {
    if (!cursor || loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    api
      .read("collection.items", { cursor })
      .then((page) => {
        const got = page.items ?? [];
        setItems((prev) => [...prev, ...got]);
        // A cursor that returns nothing is a stalled cursor, not more data.
        setCursor(got.length ? (page.next_cursor ?? null) : null);
        loadingRef.current = false;
        setLoading(false);
      })
      .catch((err) => {
        loadingRef.current = false;
        setLoading(false);
        fail(err);
      });
  }, [cursor, fail]);

  const open = useCallback(
    (ref) => {
      if (!api.open || !ref) return;
      // The card is never left disabled: the reader comes back to this panel
      // after drilling in and must be able to open the same item again.
      api.open(ref).catch(fail);
    },
    [fail],
  );

  return html`<${CollectionView}
    items=${items}
    count=${count}
    itemType=${itemType}
    loading=${loading}
    hasMore=${Boolean(cursor)}
    onLoadMore=${loadMore}
    error=${error}
    onOpen=${open}
  />`;
}

api
  .ready()
  .then(() => {
    render(
      html`<${CollectionPanel} input=${api.input ?? {}} />`,
      document.getElementById("root"),
    );
  })
  .catch((err) => api.reportError(String(err?.message || err)));
