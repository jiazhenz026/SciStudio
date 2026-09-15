/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { CollectionView } from "../../sdk/1/renderer-collection.js";
const api = window.scistudio;
export { itemLabel } from "../../sdk/1/renderer-collection.js";

function CollectionPanel({ input }) {
  const [items, setItems] = useState(() => [...(input.items ?? [])]);
  const [cursor, setCursor] = useState(input.next_cursor ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const count = typeof input.count === "number" ? input.count : items.length;
  const itemType = input.item_type || "items";

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  // Pages are pulled in the background until the collection is fully listed, so
  // the reader simply sees their items — the viewer this replaces stopped at the
  // first page and flagged the rest as "sampled" (#1886 item B).
  useEffect(() => {
    if (!cursor || loading) return;
    let cancelled = false;
    setLoading(true);
    api
      .read("collection.items", { cursor })
      .then((page) => {
        if (cancelled) return;
        const got = page.items ?? [];
        setItems((prev) => [...prev, ...got]);
        // A cursor that returns nothing is a stalled cursor, not more data.
        setCursor(got.length ? (page.next_cursor ?? null) : null);
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
  }, [cursor, fail]); // eslint-disable-line react-hooks/exhaustive-deps

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
    loading=${Boolean(cursor)}
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
