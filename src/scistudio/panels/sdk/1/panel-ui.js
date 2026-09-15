/**
 * @overview
 * SciStudio panel component set (SDK major 1).
 *
 * A small set of Preact components covering the shapes panels actually need, so
 * a panel — built-in, packaged, or agent-written — is assembled from named parts
 * instead of re-deriving markup and styling. Pair it with `panel.css`, which gives
 * these components the application's look through the host-injected design
 * tokens.
 *
 * ```javascript
 * import { html, render } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
 * import { Panel, Card, Meta, Field, Button } from "../../sdk/1/panel-ui.js";
 *
 * render(html`<${Panel}>
 *   <${Meta} items=${["Array", "shape [3, 3]"]} />
 *   <${Card}>…<//>
 * <//>`, document.getElementById("root"));
 * ```
 *
 * Components take plain props and children; nothing here talks to the host —
 * data comes from the SDK (`window.scistudio`) in the panel's own code. Props a
 * component does not name are passed to its root element.
 */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

/**
 * The panel shell: a padded column with the standard vertical rhythm. Use it as the root of a panel.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] Content.
 */
export function Panel({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/**
 * A vertical stack with the standard gap.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] Content.
 */
export function Stack({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-stack", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/**
 * A horizontal row. Put a `Spacer` between children to push them apart.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] Content.
 */
export function Row({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-row", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/**
 * Flexible empty space inside a `Row`.
 */
export function Spacer() {
  return html`<div class="panel-spacer"></div>`;
}

/**
 * The bordered surface the application uses for grouped content.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {boolean} [props.tight] Use the smaller padding.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] Content.
 */
export function Card({ class: cls, tight, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-card", tight && "panel-card-tight", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/**
 * A metadata strip such as `["Array", "shape [3, 3]", "dtype float64"]`. The first item is emphasised, matching the application's summary bars.
 *
 * @param {string[]} [props.items] The entries; empty, `null`, and `undefined` entries are skipped.
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] Extra content after the items.
 */
export function Meta({ items, class: cls, children, ...rest }) {
  const parts = (items || []).filter((item) => item !== null && item !== undefined && item !== "");
  return html`<div class=${cx("panel-card", "panel-meta", cls)} ...${rest}>
    ${parts.map((item, i) =>
      i === 0
        ? html`<span class="panel-meta-key">${item}</span>`
        : html`<span>${item}</span>`,
    )}
    ${children}
  </div>`;
}

/**
 * Muted helper text.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] Content.
 */
export function Hint({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-hint", cls)} ...${rest}>${children}</div>`;
}

/**
 * A small uppercase section label.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] Content.
 */
export function Label({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-label", cls)} ...${rest}>${children}</div>`;
}

/**
 * A rounded pill for counts and states.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] Content.
 */
export function Badge({ class: cls, children, ...rest }) {
  return html`<span class=${cx("panel-badge", cls)} ...${rest}>${children}</span>`;
}

/**
 * A button in the application's style. It is `type="button"`, so it never submits a form.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {boolean} [props.primary] Use the emphasised style for the main action.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] The button's label.
 */
export function Button({ class: cls, primary, elementRef, children, ...rest }) {
  return html`<button
    type="button"
    class=${cx("panel-button", primary && "panel-button-primary", cls)}
    ref=${elementRef}
    ...${rest}
  >${children}</button>`;
}

/**
 * A text input in the application's style.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {boolean} [props.number] Use the narrow numeric width.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 */
export function Input({ class: cls, number, elementRef, ...rest }) {
  return html`<input class=${cx("panel-input", number && "panel-input-number", cls)} ref=${elementRef} ...${rest} />`;
}

/**
 * A drop-down list in the application's style.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {Array<string | {value, label}>} [props.options] The choices; a string is both value and label.
 * @param {any} [props.children] Extra `<option>` elements after `options`.
 */
export function Select({ class: cls, options, children, ...rest }) {
  return html`<select class=${cx("panel-select", cls)} ...${rest}>
    ${(options || []).map((o) =>
      html`<option value=${o.value !== undefined ? o.value : o}>${o.label !== undefined ? o.label : o}</option>`,
    )}
    ${children}
  </select>`;
}

/**
 * A labelled control row: a name, the control, and an optional readout. The shape the slice selectors and similar per-axis controls use.
 *
 * @param {any} [props.name] The label before the control.
 * @param {any} [props.readout] A value shown after the control.
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] The control.
 */
export function Field({ name, readout, class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-field", cls)} ...${rest}>
    ${name !== undefined ? html`<span class="panel-field-name">${name}</span>` : null}
    ${children}
    ${readout !== undefined ? html`<span class="panel-readout">${readout}</span>` : null}
  </div>`;
}

/**
 * A scrollable data surface; put a table or grid inside.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the scrolling element.
 * @param {any} [props.children] Content.
 */
export function ScrollArea({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-scroll", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/**
 * A dense table with sticky headers.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] The `<thead>` and `<tbody>`.
 */
export function Table({ class: cls, elementRef, children, ...rest }) {
  return html`<table class=${cx("panel-table", cls)} ref=${elementRef} ...${rest}>${children}</table>`;
}

/**
 * A value-scale legend: minimum label, colour ramp, optional middle label, maximum label.
 *
 * @param {any} [props.min] Label at the low end.
 * @param {any} [props.mid] Label in the middle; omitted when undefined.
 * @param {any} [props.max] Label at the high end.
 * @param {string[]} [props.stops] CSS colours forming the ramp, low to high.
 * @param {string} [props.class] Extra class names added to the root element.
 */
export function Legend({ min, mid, max, stops, class: cls, ...rest }) {
  const ramp = (stops || []).join(",");
  return html`<div class=${cx("panel-legend", cls)} ...${rest}>
    <span>${min}</span>
    <div class="panel-legend-ramp" style=${`background:linear-gradient(to right,${ramp})`}></div>
    ${mid !== undefined ? html`<span>${mid}</span>` : null}
    <span>${max}</span>
  </div>`;
}

/**
 * A responsive grid of `Item` cards, for collection or composite children.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] Content.
 */
export function ItemGrid({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-grid", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/**
 * One clickable item card: a name over a secondary line.
 *
 * @param {any} [props.name] The item's name.
 * @param {any} [props.sub] The secondary line, such as its type.
 * @param {string} [props.title] Tooltip text.
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] Extra content.
 */
export function Item({ name, sub, title, class: cls, elementRef, children, ...rest }) {
  return html`<button type="button" class=${cx("panel-item", cls)} title=${title} ref=${elementRef} ...${rest}>
    ${name !== undefined ? html`<span class="panel-item-name">${name}</span>` : null}
    ${sub !== undefined ? html`<span class="panel-item-sub">${sub}</span>` : null}
    ${children}
  </button>`;
}

/**
 * One full-width clickable row: a label over a value, and an optional trailing hint on the right. The shape a slot inventory or any name/type listing uses.
 *
 * @param {any} [props.label] The row's label.
 * @param {any} [props.value] The value under the label.
 * @param {any} [props.trailing] A hint on the right, such as `Preview →`.
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {object} [props.elementRef] A Preact ref that receives the root DOM element (a plain `ref` on a function component does not reach it).
 * @param {any} [props.children] Extra content under the value.
 */
export function ListRow({ label, value, trailing, class: cls, elementRef, children, ...rest }) {
  return html`<button type="button" class=${cx("panel-list-row", cls)} ref=${elementRef} ...${rest}>
    <span class="panel-list-row-text">
      ${label !== undefined ? html`<span class="panel-list-row-label">${label}</span>` : null}
      ${value !== undefined ? html`<span class="panel-list-row-value">${value}</span>` : null}
      ${children}
    </span>
    ${trailing !== undefined ? html`<span class="panel-list-row-trailing">${trailing}</span>` : null}
  </button>`;
}

/**
 * Plain navigation for complete, paginated data: a label such as `rows 1–50 of 200 · page 1/4` between Previous and Next. Paging is navigation, never a sign that data is partial, so do not show a truncation warning beside it.
 *
 * @param {number} props.page The current page, from 1.
 * @param {number} props.totalPages The number of pages.
 * @param {string} [props.label] The text between the buttons; defaults to `page <page>/<totalPages>`.
 * @param {function} [props.onPrev] Called by Previous; disabled on page 1.
 * @param {function} [props.onNext] Called by Next; disabled on the last page.
 * @param {string} [props.class] Extra class names added to the root element.
 */
export function Pager({ page, totalPages, label, onPrev, onNext, class: cls, ...rest }) {
  return html`<div class=${cx("panel-pager", cls)} ...${rest}>
    <${Button} onClick=${onPrev} disabled=${page <= 1}>Previous<//>
    <span>${label !== undefined ? label : `page ${page}/${totalPages}`}</span>
    <${Button} onClick=${onNext} disabled=${page >= totalPages}>Next<//>
  </div>`;
}

/**
 * A lucide icon by name, in lucide's PascalCase (`ChevronRight`) or kebab-case (`chevron-right`). Needs the lucide library loaded as `window.lucide`; renders nothing when the library is absent or the name is unknown, so a missing icon never breaks a panel.
 *
 * @param {string} props.name The icon name.
 * @param {string} [props.class] Extra class names added to the root element.
 */
export function Icon({ name, class: cls, ...rest }) {
  const lucide = typeof window !== "undefined" ? window.lucide : undefined;
  if (!lucide || !name) return null;
  const children = lucide[name] || lucide[toPascal(name)] || lucide.icons?.[toPascal(name)];
  if (!Array.isArray(children)) return null;
  return html`<svg
    class=${cx("panel-icon", cls)}
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    ...${rest}
  >${children.map(([tag, attrs], i) => html`<${tag} key=${i} ...${attrs} />`)}</svg>`;
}

function toPascal(name) {
  return String(name).replace(/(^|-)([a-z])/g, (_, __, c) => c.toUpperCase());
}

/**
 * An error state (`role="alert"`). Use it for a read that failed, never for complete data that is paged.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] The message.
 */
export function ErrorState({ class: cls, children, ...rest }) {
  return html`<div role="alert" class=${cx("panel-error", cls)} ...${rest}>${children}</div>`;
}

/**
 * A loading state (`aria-busy`). Show it until the first data arrives, so a slow read does not flash an empty surface.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] The message; defaults to `Loading…`.
 */
export function LoadingState({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-loading", cls)} aria-busy="true" ...${rest}>
    <span class="panel-loading-dot"></span>${children || "Loading…"}
  </div>`;
}

/**
 * An empty state for a target that genuinely has nothing to show.
 *
 * @param {string} [props.class] Extra class names added to the root element.
 * @param {any} [props.children] The message.
 */
export function EmptyState({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-empty", cls)} ...${rest}>${children}</div>`;
}
