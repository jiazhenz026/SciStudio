/* Reusable core presentation. Host reads and persistence stay in the caller. */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  ScrollArea,
} from "./panel-ui.js";

/**
 * A text document, shown literally in a scrolling surface.
 *
 * @param {string} [props.text] The text read so far.
 * @param {object} [props.meta] `{total_bytes?, encoding?}`; `null` shows the loading state.
 * @param {boolean} [props.done] `false` while more text is still being read.
 * @param {string} [props.error] A displayable message. It takes precedence over any data, so a failed read never leaves earlier values looking current.
 */
export function TextView({ text = "", meta = {}, done = true, error }) {
  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read text: ${error}<//><//>`;
  }
  if (!meta) {
    return html`<${Panel}><${LoadingState}>Loading text…<//><//>`;
  }
  if (done && text === "") {
    return html`<${Panel}
      ><${EmptyState} data-testid="text-empty">This file is empty.<//><//
    >`;
  }

  const totalBytes =
    typeof meta.total_bytes === "number" ? meta.total_bytes : null;

  return html`<${Panel}>
    <${ScrollArea} class="text-surface">
      <pre class="text-content" data-testid="text-content">${text}</pre>
    <//>
    ${!done
      ? html`<${LoadingState} data-testid="text-loading-more">
          Reading the
          rest${totalBytes !== null
            ? ` of ${totalBytes.toLocaleString()} bytes`
            : ""}…
        <//>`
      : totalBytes !== null
        ? html`<div class="panel-hint" data-testid="text-size">
            ${`${totalBytes.toLocaleString()} bytes${meta.encoding ? ` · ${meta.encoding}` : ""}`}
          </div>`
        : null}
  <//>`;
}
