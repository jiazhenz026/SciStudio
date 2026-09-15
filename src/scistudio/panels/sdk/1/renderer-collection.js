/* Reusable core presentation. Host reads and persistence stay in the caller. */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import {
  Button,
  Row,
  EmptyState,
  ErrorState,
  Item,
  ItemGrid,
  LoadingState,
  Panel,
} from "./panel-ui.js";

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
    if (
      user &&
      typeof user === "object" &&
      typeof user.display_name === "string" &&
      user.display_name
    ) {
      return user.display_name;
    }
    for (const value of [
      md.source_file,
      md.file_path,
      md.meta?.source_file,
      md.meta?.file_path,
    ]) {
      if (typeof value === "string" && value) return basename(value);
    }
    const source = md.framework?.source;
    // A package name is provenance, not a filename; only a path is a name.
    if (typeof source === "string" && /[\\/]/.test(source))
      return basename(source);
  }
  const ref = item.ref || item.data_ref;
  return typeof ref === "string" && ref ? ref.slice(0, 10) : "item";
}

function basename(path) {
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1] || String(path);
}

/**
 * A grid of a collection's items. The caller owns paging and what opening an item does.
 *
 * @param {object[]} [props.items] The items read so far, `{ref?, data_ref?, display_name?, type_name?, metadata?}`.
 * @param {number} [props.count] Total number of items in the collection.
 * @param {string} [props.itemType] What the items are called in the summary.
 * @param {boolean} [props.loading] Marks a read in flight.
 * @param {boolean} [props.hasMore] Show the Show more control.
 * @param {function} [props.onLoadMore] Called by Show more.
 * @param {string} [props.error] A displayable message. It takes precedence over any data, so a failed read never leaves earlier values looking current.
 * @param {function} [props.onOpen] `(ref, item)` when the reader opens an item; items are not clickable without it.
 */
export function CollectionView({
  items = [],
  count = items.length,
  itemType = "items",
  loading = false,
  hasMore = false,
  onLoadMore,
  error,
  onOpen,
}) {
  if (error) {
    return html`<${Panel}
      ><${ErrorState}>Could not read collection: ${error}<//><//
    >`;
  }
  if (!items.length && loading) {
    return html`<${Panel}><${LoadingState}>Loading items…<//><//>`;
  }
  if (!items.length) {
    return html`<${Panel}
      ><${EmptyState} data-testid="collection-empty"
        >This collection has no items.<//
      ><//
    >`;
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
          onClick=${onOpen ? () => onOpen(ref, item) : undefined}
        />`;
      })}
    <//>
    ${hasMore
      ? html`<${Row} class="collection-more">
          <${Button}
            data-testid="collection-more"
            disabled=${loading}
            onClick=${onLoadMore}
          >
            ${loading ? "Loading…" : "Show more"}
          <//>
        <//>`
      : null}
  <//>`;
}
