/* core.collection.basic — the items of a collection, with drill-down.
 *
 * Built with Preact and the shared panel component set. The surface matches the
 * viewer it replaces: a summary line and a grid of item cards showing each
 * item's source filename over its type, where clicking a card opens that item.
 *
 * Faithful display (#1886 item B): every item is reachable. Pages are fetched
 * through the cursor path as the reader asks for them, and the summary states
 * how many of the collection's items are currently listed — nothing is silently
 * capped at the first page.
 */
import {
  html,
  render,
  useCallback,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import {
  Button,
  EmptyState,
  ErrorState,
  Item,
  ItemGrid,
  LoadingState,
  Panel,
  Row,
} from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

/**
 * The label for one item card.
 *
 * The backend resolves the canonical name and stamps `display_name` on the
 * descriptor; the metadata chain below is the compatibility path for
 * descriptors that predate the stamp, and mirrors the precedence the viewer
 * applied (typed source file, then the loader's framework source, then the
 * ref). A ref is the last resort, never the first answer — showing `data-8f2a…`
 * for a file the reader named is what this exists to avoid.
 */
export function itemLabel(item) {
  if (!item || typeof item !== "object") return "item";
  const stamped = item.display_name;
  if (typeof stamped === "string" && stamped) return stamped;

  const md = item.metadata;
  if (md && typeof md === "object") {
    const user = md.user;
    if (user && typeof user === "object" && typeof user.display_name === "string" && user.display_name) {
      return user.display_name;
    }
    for (const value of [md.source_file, md.file_path, md.meta?.source_file, md.meta?.file_path]) {
      if (typeof value === "string" && value) return basename(value);
    }
    const source = md.framework?.source;
    // A package name is provenance, not a filename; only a path is a name.
    if (typeof source === "string" && /[\\/]/.test(source)) return basename(source);
  }
  const ref = item.ref || item.data_ref;
  return typeof ref === "string" && ref ? ref.slice(0, 10) : "item";
}

function basename(path) {
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1] || String(path);
}

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

  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read collection: ${error}<//><//>`;
  }
  if (!items.length && cursor) {
    return html`<${Panel}><${LoadingState}>Loading items…<//><//>`;
  }
  if (!items.length) {
    return html`<${Panel}><${EmptyState} data-testid="collection-empty">This collection has no items.<//><//>`;
  }

  return html`<${Panel}>
    <div class="panel-label" data-testid="collection-summary">
      ${count} ${itemType} (showing ${items.length} of ${count})
    </div>
    <${ItemGrid} data-testid="collection-grid">
      ${items.map((item, idx) => {
        const ref = item.ref ?? item.data_ref;
        return html`<${Item}
          key=${ref ?? idx}
          data-testid=${`collection-item-${idx}`}
          data-tutorial-target="preview_item"
          data-tutorial-target-key=${String(idx)}
          name=${itemLabel(item)}
          sub=${String(item.type_name || itemType)}
          title=${ref ?? ""}
          onClick=${() => open(ref)}
        />`;
      })}
    <//>
    ${cursor
      ? html`<${Row} class="collection-more">
          <${Button} data-testid="collection-more" disabled=${loading} onClick=${loadMore}>
            ${loading ? "Loading…" : "Show more"}
          <//>
        <//>`
      : null}
  <//>`;
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
