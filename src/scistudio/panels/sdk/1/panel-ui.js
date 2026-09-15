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
 *
 * The questionnaire components ask the user what a MiniApp should do before it
 * is built. The questions are data: `panels/<id>/questionnaire.json`, rendered
 * by `Questionnaire`, submitted through `scistudio.submitAnswers`, and checked
 * by the `validate_panel` agent tool. Every question is optional and every
 * question offers "Decide for me"; a spec cannot change either.
 *
 * ```javascript
 * import { Questionnaire } from "../../sdk/1/panel-ui.js";
 *
 * await scistudio.ready();
 * const spec = await (await fetch("questionnaire.json")).json();
 * render(html`<${Panel}><${Questionnaire} spec=${spec} onSubmit=${scistudio.submitAnswers} /><//>`, root);
 * ```
 *
 * `questionnaire.json` is `{title, intro?, submit_label?, questions}`. Each
 * question has `id` (lowercase, unique), `type`, `prompt`, and optional `help`:
 * `single` and `multiple` take `options` (at least two `{value, label,
 * description?}`) and `allow_other`; `text` takes `multiline` and
 * `placeholder`; `number` takes `min`, `max`, `step`, `unit`, `placeholder`;
 * `range` is a slider and needs `min` and `max`. An answer is `{status:
 * "answered", value, other?}`, `{status: "decide_for_me"}`, or `{status:
 * "skipped"}`.
 */
import { html, useState } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

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

// ---------------------------------------------------------------------------
// Questionnaire (ADR-054 MiniApp FR-049 to FR-052)
// ---------------------------------------------------------------------------

const DECIDE = "decide_for_me";
const QUESTION_TYPES = ["single", "multiple", "text", "number", "range"];
const TYPE_KEYS = {
  single: ["options", "allow_other"],
  multiple: ["options", "allow_other"],
  text: ["multiline", "placeholder"],
  number: ["min", "max", "step", "unit", "placeholder"],
  range: ["min", "max", "step", "unit"],
};
const TOP_KEYS = ["title", "intro", "submit_label", "questions"];
const OPTION_KEYS = ["value", "label", "description"];
const SKIPPED = { status: "skipped" };

const isText = (v) => typeof v === "string" && v.trim() !== "";
const isNumber = (v) => typeof v === "number" && Number.isFinite(v);
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/*
 * The spec rules, mirrored from scistudio.panels.questionnaire.validate_spec so
 * a broken questionnaire shows its problems instead of a half-drawn form. The
 * Python side is the authority (the submit route and validate_panel use it);
 * tests/fixtures/questionnaire/cases.json holds the cases both must agree on.
 */
function questionnaireProblems(spec) {
  if (!isObject(spec)) return ["questionnaire.json: the top level must be an object with 'title' and 'questions'."];
  const out = [];
  for (const key of Object.keys(spec)) if (!TOP_KEYS.includes(key)) out.push(`unknown top-level key '${key}'`);
  if (!isText(spec.title)) out.push("'title' is missing or empty");
  for (const key of ["intro", "submit_label"]) if (key in spec && typeof spec[key] !== "string") out.push(`'${key}' must be a string`);
  if (!Array.isArray(spec.questions) || spec.questions.length === 0) {
    out.push("'questions' must be a non-empty list");
    return out;
  }
  if (spec.questions.length > 50) out.push("more than 50 questions");
  const ids = new Set();
  spec.questions.forEach((q, i) => {
    const where = `questions[${i}]`;
    if (!isObject(q)) { out.push(`${where}: must be an object`); return; }
    if (typeof q.id !== "string" || !/^[a-z][a-z0-9_]{0,63}$/.test(q.id)) out.push(`${where}: invalid 'id'`);
    else if (ids.has(q.id)) out.push(`${where}: id '${q.id}' is repeated`);
    else ids.add(q.id);
    if ("required" in q) out.push(`${where}: remove 'required' — every question is optional`);
    if (DECIDE in q || "decideForMe" in q) out.push(`${where}: remove '${DECIDE}' — it is always shown`);
    if (!QUESTION_TYPES.includes(q.type)) { out.push(`${where}: unknown type ${JSON.stringify(q.type)}`); return; }
    if (!isText(q.prompt)) out.push(`${where}: 'prompt' is missing`);
    if ("help" in q && typeof q.help !== "string") out.push(`${where}: 'help' must be a string`);
    const allowed = ["id", "type", "prompt", "help", ...TYPE_KEYS[q.type]];
    for (const key of Object.keys(q)) {
      if (!allowed.includes(key) && key !== "required" && key !== DECIDE && key !== "decideForMe") out.push(`${where}: '${key}' does not apply to ${q.type}`);
    }
    if (q.type === "single" || q.type === "multiple") {
      if ("allow_other" in q && typeof q.allow_other !== "boolean") out.push(`${where}: 'allow_other' must be a boolean`);
      if (!Array.isArray(q.options) || q.options.length < 2) { out.push(`${where}: needs at least two options`); return; }
      if (q.options.length > 30) out.push(`${where}: more than 30 options`);
      const values = new Set();
      q.options.forEach((o, j) => {
        if (!isObject(o)) { out.push(`${where}.options[${j}]: must be an object`); return; }
        for (const key of Object.keys(o)) if (!OPTION_KEYS.includes(key)) out.push(`${where}.options[${j}]: unknown key '${key}'`);
        if (!isText(o.value)) out.push(`${where}.options[${j}]: 'value' is missing`);
        else if (o.value === DECIDE) out.push(`${where}.options[${j}]: '${DECIDE}' is reserved`);
        else if (values.has(o.value)) out.push(`${where}.options[${j}]: value '${o.value}' is repeated`);
        else values.add(o.value);
        if (!isText(o.label)) out.push(`${where}.options[${j}]: 'label' is missing`);
        if ("description" in o && typeof o.description !== "string") out.push(`${where}.options[${j}]: 'description' must be a string`);
      });
    } else if (q.type === "text") {
      if ("multiline" in q && typeof q.multiline !== "boolean") out.push(`${where}: 'multiline' must be a boolean`);
      if ("placeholder" in q && typeof q.placeholder !== "string") out.push(`${where}: 'placeholder' must be a string`);
    } else {
      for (const key of ["min", "max", "step"]) if (key in q && !isNumber(q[key])) out.push(`${where}: '${key}' must be a number`);
      for (const key of ["unit", "placeholder"]) if (key in q && typeof q[key] !== "string") out.push(`${where}: '${key}' must be a string`);
      if (q.type === "range" && !(isNumber(q.min) && isNumber(q.max))) out.push(`${where}: a range needs 'min' and 'max'`);
      if (isNumber(q.min) && isNumber(q.max) && q.min >= q.max) out.push(`${where}: 'min' must be less than 'max'`);
      if (isNumber(q.step) && q.step <= 0) out.push(`${where}: 'step' must be greater than zero`);
    }
  });
  return out;
}

function QuestionCard({ question, answer, onChange, children }) {
  const status = (answer || SKIPPED).status;
  const deciding = status === DECIDE;
  return html`<div
    class="panel-card panel-question"
    data-question-id=${question.id}
    data-status=${status}
  >
    <p class="panel-question-prompt">${question.prompt}<span class="panel-question-optional">optional</span></p>
    ${question.help ? html`<p class="panel-question-help">${question.help}</p>` : null}
    ${children}
    <div class="panel-choices">
      <button
        type="button"
        class="panel-choice panel-choice-decide"
        aria-pressed=${deciding ? "true" : "false"}
        data-decide-for-me=${question.id}
        onClick=${() => onChange && onChange(deciding ? SKIPPED : { status: DECIDE })}
      >Decide for me</button>
    </div>
  </div>`;
}

/**
 * A single-choice question: one pill per option, plus "Decide for me". Choosing the chosen option again clears it back to skipped.
 *
 * @param {object} props.question The question from the spec: `{id, prompt, help?, options, allow_other?}`.
 * @param {object} [props.answer] The current answer; skipped when absent.
 * @param {function} [props.onChange] Receives the new answer.
 */
export function SingleChoiceQuestion({ question, answer, onChange }) {
  const current = answer || SKIPPED;
  const set = (next) => onChange && onChange(next);
  const other = current.status === "answered" && current.other !== undefined ? current.other : "";
  return html`<${QuestionCard} question=${question} answer=${current} onChange=${set}>
    <div class="panel-choices" role="radiogroup" aria-label=${question.prompt}>
      ${(question.options || []).map((option) => {
        const chosen = current.status === "answered" && current.value === option.value;
        return html`<button
          type="button"
          class="panel-choice"
          aria-pressed=${chosen ? "true" : "false"}
          data-option=${option.value}
          onClick=${() => set(chosen ? SKIPPED : { status: "answered", value: option.value })}
        >${option.label}${option.description ? html`<span class="panel-choice-description">${option.description}</span>` : null}</button>`;
      })}
    </div>
    ${question.allow_other
      ? html`<${Input}
          class="panel-question-other"
          placeholder="Something else…"
          value=${other}
          onInput=${(event) => {
            const text = event.currentTarget.value;
            set(text.trim() ? { status: "answered", other: text } : SKIPPED);
          }}
        />`
      : null}
  <//>`;
}

/**
 * A multiple-choice question: pills that toggle independently, plus "Decide for me". Clearing every pill returns the question to skipped.
 *
 * @param {object} props.question The question from the spec: `{id, prompt, help?, options, allow_other?}`.
 * @param {object} [props.answer] The current answer; skipped when absent.
 * @param {function} [props.onChange] Receives the new answer.
 */
export function MultipleChoiceQuestion({ question, answer, onChange }) {
  const current = answer || SKIPPED;
  const chosen = current.status === "answered" && Array.isArray(current.value) ? current.value : [];
  const other = current.status === "answered" && current.other !== undefined ? current.other : "";
  const set = (values, text) => {
    if (!onChange) return;
    const next = { status: "answered", value: values };
    if (text && text.trim()) next.other = text;
    onChange(values.length || next.other ? next : SKIPPED);
  };
  return html`<${QuestionCard} question=${question} answer=${current} onChange=${onChange}>
    <div class="panel-choices" role="group" aria-label=${question.prompt}>
      ${(question.options || []).map((option) => {
        const on = chosen.includes(option.value);
        return html`<button
          type="button"
          class="panel-choice"
          aria-pressed=${on ? "true" : "false"}
          data-option=${option.value}
          onClick=${() => set(on ? chosen.filter((v) => v !== option.value) : [...chosen, option.value], other)}
        >${option.label}${option.description ? html`<span class="panel-choice-description">${option.description}</span>` : null}</button>`;
      })}
    </div>
    ${question.allow_other
      ? html`<${Input}
          class="panel-question-other"
          placeholder="Something else…"
          value=${other}
          onInput=${(event) => set(chosen, event.currentTarget.value)}
        />`
      : null}
  <//>`;
}

/**
 * A free-text question, one line or several, plus "Decide for me". Empty text is skipped.
 *
 * @param {object} props.question The question from the spec: `{id, prompt, help?, multiline?, placeholder?}`.
 * @param {object} [props.answer] The current answer; skipped when absent.
 * @param {function} [props.onChange] Receives the new answer.
 */
export function TextQuestion({ question, answer, onChange }) {
  const current = answer || SKIPPED;
  const value = current.status === "answered" ? current.value : "";
  const onInput = (event) => {
    const text = event.currentTarget.value;
    if (onChange) onChange(text.trim() ? { status: "answered", value: text } : SKIPPED);
  };
  return html`<${QuestionCard} question=${question} answer=${current} onChange=${onChange}>
    ${question.multiline
      ? html`<textarea class="panel-input" placeholder=${question.placeholder || ""} value=${value} onInput=${onInput}></textarea>`
      : html`<${Input} placeholder=${question.placeholder || ""} value=${value} onInput=${onInput} />`}
  <//>`;
}

/**
 * A number question — a number box, or a slider when the spec's type is `range` — plus "Decide for me". An empty box is skipped.
 *
 * @param {object} props.question The question from the spec: `{id, type, prompt, help?, min?, max?, step?, unit?, placeholder?}`.
 * @param {object} [props.answer] The current answer; skipped when absent.
 * @param {function} [props.onChange] Receives the new answer.
 */
export function NumberQuestion({ question, answer, onChange }) {
  const current = answer || SKIPPED;
  const answered = current.status === "answered" && isNumber(current.value);
  const onInput = (event) => {
    const raw = event.currentTarget.value;
    const parsed = raw === "" ? NaN : Number(raw);
    if (onChange) onChange(Number.isFinite(parsed) ? { status: "answered", value: parsed } : SKIPPED);
  };
  const slider = question.type === "range";
  return html`<${QuestionCard} question=${question} answer=${current} onChange=${onChange}>
    <${Field} readout=${slider ? (answered ? `${current.value}${question.unit ? ` ${question.unit}` : ""}` : "not set") : question.unit}>
      ${slider
        ? html`<input
            type="range"
            class="panel-field-range"
            min=${question.min}
            max=${question.max}
            step=${question.step || "any"}
            value=${answered ? current.value : question.min}
            onInput=${onInput}
          />`
        : html`<${Input}
            type="number"
            min=${question.min}
            max=${question.max}
            step=${question.step || "any"}
            placeholder=${question.placeholder || ""}
            value=${answered ? current.value : ""}
            onInput=${onInput}
          />`}
    <//>
  <//>`;
}

/**
 * One question of any type, drawn by the component for its `type`.
 *
 * @param {object} props.question The question from the spec.
 * @param {object} [props.answer] The current answer; skipped when absent.
 * @param {function} [props.onChange] Receives the new answer.
 */
export function Question({ question, answer, onChange }) {
  const view = {
    single: SingleChoiceQuestion,
    multiple: MultipleChoiceQuestion,
    text: TextQuestion,
    number: NumberQuestion,
    range: NumberQuestion,
  }[question && question.type];
  if (!view) return html`<${ErrorState}>Unknown question type ${JSON.stringify(question && question.type)}<//>`;
  return html`<${view} question=${question} answer=${answer} onChange=${onChange} />`;
}

/**
 * The bar under the questions: a Submit button that is enabled with any number of answers, and the message a submit left behind.
 *
 * @param {string} [props.label] The button text; defaults to `Submit`.
 * @param {boolean} [props.busy] A submit is in flight; the button is disabled only then.
 * @param {string} [props.message] Text beside the button, such as the submit result's `message`.
 * @param {string} [props.kind] `"done"`, `"return"` (go back to your AI chat), or `"error"`; colours the message.
 * @param {function} [props.onSubmit] Called when the button is pressed.
 */
export function SubmitBar({ label, busy, message, kind, onSubmit }) {
  return html`<div class="panel-submit-bar" data-testid="questionnaire-submit-bar">
    <${Button} primary disabled=${Boolean(busy)} onClick=${onSubmit} data-testid="questionnaire-submit">
      ${busy ? "Sending…" : label || "Submit"}
    <//>
    ${message ? html`<span class="panel-submit-message" data-kind=${kind || "done"} role="status">${message}</span>` : null}
  </div>`;
}

/**
 * A whole questionnaire from its spec: title, intro, every question, and the submit bar. A spec that breaks a rule renders an error state that lists each problem instead of a form. Submitting sends one answer per question — `skipped` for those left alone — to `onSubmit` and shows the message it resolves with; the result's `notified: false` shows as a reminder to return to the AI chat.
 *
 * @param {object} props.spec The parsed `questionnaire.json`.
 * @param {function} [props.onSubmit] Receives the answers keyed by question id and returns a promise; pass `scistudio.submitAnswers`.
 * @param {object} [props.initialAnswers] Answers to start from, keyed by question id.
 * @param {string} [props.class] Extra class names added to the root element.
 */
export function Questionnaire({ spec, onSubmit, initialAnswers, class: cls, ...rest }) {
  const [answers, setAnswers] = useState(() => ({ ...(initialAnswers || {}) }));
  const [state, setState] = useState({ busy: false, message: "", kind: "done" });
  const problems = questionnaireProblems(spec);
  if (problems.length) {
    return html`<div class=${cx("panel-stack", "panel-questionnaire", cls)} ...${rest}>
      <${ErrorState} data-testid="questionnaire-invalid">
        <strong>This questionnaire cannot be shown.</strong> Fix questionnaire.json and run validate_panel:
        <ul>${problems.map((p) => html`<li>${p}</li>`)}</ul>
      <//>
    </div>`;
  }
  const submit = async () => {
    if (typeof onSubmit !== "function") {
      setState({ busy: false, message: "This page has no submit handler; pass scistudio.submitAnswers as onSubmit.", kind: "error" });
      return;
    }
    const payload = {};
    for (const q of spec.questions) payload[q.id] = answers[q.id] || SKIPPED;
    setState({ busy: true, message: "", kind: "done" });
    try {
      const result = await onSubmit(payload);
      const notified = !result || result.notified !== false;
      const message = (result && result.message) || (notified ? "Sent." : "Saved. Go back to your AI chat and say you have submitted.");
      setState({ busy: false, message, kind: notified ? "done" : "return" });
    } catch (error) {
      setState({ busy: false, message: `Not sent: ${(error && error.message) || error}`, kind: "error" });
    }
  };
  return html`<div class=${cx("panel-stack", "panel-questionnaire", cls)} ...${rest}>
    <h1 class="panel-questionnaire-title">${spec.title}</h1>
    ${spec.intro ? html`<p class="panel-questionnaire-intro">${spec.intro}</p>` : null}
    ${spec.questions.map((q) => html`<${Question}
      key=${q.id}
      question=${q}
      answer=${answers[q.id]}
      onChange=${(next) => setAnswers((prev) => ({ ...prev, [q.id]: next }))}
    />`)}
    <${SubmitBar} label=${spec.submit_label} busy=${state.busy} message=${state.message} kind=${state.kind} onSubmit=${submit} />
  </div>`;
}
