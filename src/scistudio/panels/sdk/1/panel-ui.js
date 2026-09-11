/* SciStudio panel component set (SDK major 1).
 *
 * A small set of Preact components covering the shapes panels actually need, so
 * a panel — built-in, packaged, or agent-written — is assembled from named parts
 * instead of re-deriving markup and styling. Pair it with panel.css, which gives
 * these components the application's look through the host-injected design
 * tokens.
 *
 *   import { html, render } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
 *   import { Panel, Card, Meta, Field, Button } from "../../sdk/1/panel-ui.js";
 *
 *   render(html`<${Panel}>
 *     <${Meta} items=${["Array", "shape [3, 3]"]} />
 *     <${Card}>…<//>
 *   <//>`, document.getElementById("root"));
 *
 * Components take plain props and children; nothing here talks to the host —
 * data comes from the SDK (window.scistudio) in the panel's own code.
 */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

/** The panel shell: a padded column with the standard vertical rhythm. */
export function Panel({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/** A vertical stack with the standard gap. */
export function Stack({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-stack", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/** A horizontal row; pass `spacer` children to push things apart. */
export function Row({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-row", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

export function Spacer() {
  return html`<div class="panel-spacer"></div>`;
}

/** The bordered surface the application uses for grouped content. */
export function Card({ class: cls, tight, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-card", tight && "panel-card-tight", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/**
 * Metadata strip, e.g. ``["Array", "shape [3, 3]", "dtype float64"]``. The first
 * item is emphasised, matching the application's summary bars. Pass `items` as
 * strings, or children for full control.
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

/** Muted helper text. */
export function Hint({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-hint", cls)} ...${rest}>${children}</div>`;
}

/** Small uppercase section label. */
export function Label({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-label", cls)} ...${rest}>${children}</div>`;
}

/** Rounded pill for counts and states. */
export function Badge({ class: cls, children, ...rest }) {
  return html`<span class=${cx("panel-badge", cls)} ...${rest}>${children}</span>`;
}

export function Button({ class: cls, primary, elementRef, children, ...rest }) {
  return html`<button
    type="button"
    class=${cx("panel-button", primary && "panel-button-primary", cls)}
    ref=${elementRef}
    ...${rest}
  >${children}</button>`;
}

export function Input({ class: cls, number, elementRef, ...rest }) {
  return html`<input class=${cx("panel-input", number && "panel-input-number", cls)} ref=${elementRef} ...${rest} />`;
}

export function Select({ class: cls, options, children, ...rest }) {
  return html`<select class=${cx("panel-select", cls)} ...${rest}>
    ${(options || []).map((o) =>
      html`<option value=${o.value !== undefined ? o.value : o}>${o.label !== undefined ? o.label : o}</option>`,
    )}
    ${children}
  </select>`;
}

/**
 * A labelled control row: name, the control itself, and an optional readout —
 * the shape the slice selectors and similar per-axis controls use.
 */
export function Field({ name, readout, class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-field", cls)} ...${rest}>
    ${name !== undefined ? html`<span class="panel-field-name">${name}</span>` : null}
    ${children}
    ${readout !== undefined ? html`<span class="panel-readout">${readout}</span>` : null}
  </div>`;
}

/**
 * Scrollable data surface; put a table or grid inside.
 *
 * Pass `elementRef` to get the scrolling element itself — a plain `ref` on a
 * function component does not reach the DOM node.
 */
export function ScrollArea({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-scroll", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/** Dense numeric table with sticky headers. */
export function Table({ class: cls, elementRef, children, ...rest }) {
  return html`<table class=${cx("panel-table", cls)} ref=${elementRef} ...${rest}>${children}</table>`;
}

/**
 * Value-scale legend: min label, colour ramp, optional mid label, max label.
 * `stops` is an array of CSS colours forming the ramp.
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

/** Responsive grid of item cards (collection/composite children). */
export function ItemGrid({ class: cls, elementRef, children, ...rest }) {
  return html`<div class=${cx("panel-grid", cls)} ref=${elementRef} ...${rest}>${children}</div>`;
}

/** One clickable item card: a name and a secondary line. */
export function Item({ name, sub, title, class: cls, elementRef, children, ...rest }) {
  return html`<button type="button" class=${cx("panel-item", cls)} title=${title} ref=${elementRef} ...${rest}>
    ${name !== undefined ? html`<span class="panel-item-name">${name}</span>` : null}
    ${sub !== undefined ? html`<span class="panel-item-sub">${sub}</span>` : null}
    ${children}
  </button>`;
}

/**
 * One full-width clickable row: a label over a value on the left, and an
 * optional trailing hint on the right — the shape a slot inventory or any
 * name/type listing uses.
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
 * Plain navigation for complete, paginated data: "rows 1–50 of 200 · page 1/4"
 * with prev/next. Paging is navigation, never a warning that the data is partial
 * (#1886 Part 1) — do not render a "truncated" badge alongside it.
 */
export function Pager({ page, totalPages, label, onPrev, onNext, class: cls, ...rest }) {
  return html`<div class=${cx("panel-pager", cls)} ...${rest}>
    <${Button} onClick=${onPrev} disabled=${page <= 1}>Previous<//>
    <span>${label !== undefined ? label : `page ${page}/${totalPages}`}</span>
    <${Button} onClick=${onNext} disabled=${page >= totalPages}>Next<//>
  </div>`;
}

/**
 * A lucide icon by name — accepts either lucide's own PascalCase (`ChevronRight`)
 * or the kebab-case spelling (`chevron-right`). Requires the lucide library to be
 * loaded; renders nothing when it is absent or the name is unknown, so a missing
 * icon never breaks a panel.
 *
 * lucide exposes each icon as an array of child elements, `[[tag, attrs], …]`;
 * the surrounding `<svg>` and its stroke defaults belong to the caller.
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

/** Error state; use for a read that failed, never for complete-but-paged data. */
export function ErrorState({ class: cls, children, ...rest }) {
  return html`<div role="alert" class=${cx("panel-error", cls)} ...${rest}>${children}</div>`;
}

/**
 * Loading state. Reading a large target takes a moment, and an empty surface in
 * the meantime reads as a blank flash; show this until the first data lands.
 */
export function LoadingState({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-loading", cls)} aria-busy="true" ...${rest}>
    <span class="panel-loading-dot"></span>${children || "Loading…"}
  </div>`;
}

/** Empty state for a target that genuinely has nothing to show. */
export function EmptyState({ class: cls, children, ...rest }) {
  return html`<div class=${cx("panel-empty", cls)} ...${rest}>${children}</div>`;
}
