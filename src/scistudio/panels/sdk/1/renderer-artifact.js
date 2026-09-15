/* Reusable core presentation. Host reads and persistence stay in the caller. */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { Card, ErrorState, Hint, LoadingState, Panel } from "./panel-ui.js";

/** Whether this artifact is a kind the panel can show inline. */
export function isImage(mime) {
  return typeof mime === "string" && mime.toLowerCase().startsWith("image/");
}

/**
 * Explain an absent inline view, or return null when one is on screen.
 *
 * Every branch here is a distinct reason, because the reader cannot tell them
 * apart from the blank space alone: a file with no visual form, a file whose
 * bytes were never granted, and an image the browser refused are three
 * different situations that the viewer this replaces rendered identically.
 */
export function inlineNotice({ mime, url, imageFailed }) {
  if (!isImage(mime)) return `No inline view for ${mime || "this file type"}.`;
  if (!url) return "This image could not be opened for display.";
  if (imageFailed) return "This image could not be displayed.";
  return null;
}

export function ArtifactView({
  info,
  url,
  imageFailed = false,
  onImageError = () => {},
  error,
}) {
  if (error) {
    return html`<${Panel}
      ><${ErrorState}>Could not read artifact: ${error}<//><//
    >`;
  }
  if (!info) {
    return html`<${Panel}><${LoadingState}>Loading artifact…<//><//>`;
  }

  const mime = info.mime_type || "application/octet-stream";
  const path = info.path || info.name || "";
  const size = typeof info.size === "number" ? info.size : null;
  const notice = inlineNotice({ mime, url, imageFailed });

  return html`<${Panel}>
    <${Card}>
      <div class="artifact-title">Artifact</div>
      <div class="artifact-path" data-testid="artifact-path">${path}</div>
      <div class="artifact-field" data-testid="artifact-mime">${mime}</div>
      ${size !== null
        ? html`<div class="artifact-field" data-testid="artifact-size">
            ${size} bytes
          </div>`
        : null}
      ${isImage(mime) && url && !imageFailed
        ? html`<img
            class="artifact-image"
            data-testid="artifact-image"
            src=${url}
            alt=${info.name || "Artifact"}
            onError=${() => onImageError()}
          />`
        : null}
      ${notice
        ? html`<${Hint} data-testid="artifact-inline-notice">${notice}<//>`
        : null}
    <//>
  <//>`;
}
