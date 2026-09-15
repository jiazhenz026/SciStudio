/* Reusable core presentation. Host reads and persistence stay in the caller. */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import {
  EmptyState,
  ErrorState,
  ListRow,
  LoadingState,
  Panel,
} from "./panel-ui.js";

/**
 * The slot inventory of a composite, one row per slot.
 *
 * @param {object[] | null} [props.slots] The slots `{name, type_name?, ref?}`, as `composite.slots` returns them; `null` shows the loading state.
 * @param {string} [props.error] A displayable message. It takes precedence over any data, so a failed read never leaves earlier values looking current.
 * @param {function} [props.onOpen] `(ref, slot)` when the reader opens a slot; rows are not clickable without it.
 */
export function CompositeView({ slots = [], error, onOpen }) {
  if (error) {
    return html`<${Panel}
      ><${ErrorState}>Could not read slots: ${error}<//><//
    >`;
  }
  if (slots === null) {
    return html`<${Panel}><${LoadingState}>Loading slots…<//><//>`;
  }
  if (!slots.length) {
    return html`<${Panel}>
      <${EmptyState} data-testid="composite-empty"
        >This composite has no slots.<//
      >
    <//>`;
  }

  return html`<${Panel}>
    <div class="panel-label" data-testid="composite-summary">
      ${slots.length} slot${slots.length === 1 ? "" : "s"}
    </div>
    ${slots.map(
      (slot) =>
        html`<${ListRow}
          key=${slot.name}
          data-testid=${`composite-slot-${slot.name}`}
          label=${slot.name}
          value=${String(slot.type_name || "")}
          trailing=${onOpen ? "Preview →" : undefined}
          title=${slot.ref ?? ""}
          onClick=${onOpen ? () => onOpen(slot.ref, slot) : undefined}
        />`,
    )}
  <//>`;
}
