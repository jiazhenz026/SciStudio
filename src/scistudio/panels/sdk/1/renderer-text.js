/* Reusable core presentation. Host reads and persistence stay in the caller. */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import {
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  ScrollArea,
} from "./panel-ui.js";

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
