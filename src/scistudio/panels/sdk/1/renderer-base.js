/* Reusable core presentation. Host reads and persistence stay in the caller. */
import { html } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { Card, ErrorState, Hint, LoadingState, Panel } from "./panel-ui.js";

/** The object's own type: the most specific name its chain records. */
export function typeName(meta) {
  const chain = meta?.type_chain;
  if (Array.isArray(chain) && chain.length)
    return String(chain[chain.length - 1]);
  return "object";
}

/** The ancestry to show beside it, or null when the type has none worth showing. */
export function ancestry(meta) {
  const chain = meta?.type_chain;
  if (!Array.isArray(chain) || chain.length < 2) return null;
  return chain.join(" → ");
}

/** Recorded metadata worth printing, or null when the record carries none. */
export function recordedMetadata(meta) {
  const recorded = meta?.metadata;
  if (!recorded || typeof recorded !== "object" || Array.isArray(recorded))
    return null;
  return Object.keys(recorded).length ? recorded : null;
}

/**
 * The fallback view for any data object: its type and ancestry, shape and dtype, stored file, and recorded metadata.
 *
 * @param {object} [props.meta] A `metadata` result `{type_chain?, shape?, dtype?, metadata?}`; the loading state shows until it is given.
 * @param {object} [props.file] The stored file `{name?, path?, mime_type?, size?, url?}`, when there is one.
 * @param {boolean} [props.imageFailed] Set after the image failed to load.
 * @param {function} [props.onImageError] Called when the inline image fails to load.
 * @param {string} [props.error] A displayable message. It takes precedence over any data, so a failed read never leaves earlier values looking current.
 */
export function MetadataView({
  meta,
  file,
  imageFailed = false,
  onImageError = () => {},
  error,
}) {
  if (error) {
    return html`<${Panel}
      ><${ErrorState}>Could not read object: ${error}<//><//
    >`;
  }
  if (!meta) {
    return html`<${Panel}><${LoadingState}>Loading object…<//><//>`;
  }

  const chain = ancestry(meta);
  const recorded = recordedMetadata(meta);
  const mime = file?.mime_type || "";
  const isImage =
    typeof mime === "string" && mime.toLowerCase().startsWith("image/");
  const size = typeof file?.size === "number" ? file.size : null;

  return html`<${Panel}>
    <${Card}>
      <div class="object-title" data-testid="object-type">
        ${typeName(meta)}
      </div>
      ${chain
        ? html`<div class="object-field" data-testid="object-chain">
            ${chain}
          </div>`
        : null}
      ${meta.shape
        ? html`<div class="object-field">
            shape [${[].concat(meta.shape).join(", ")}]
          </div>`
        : null}
      ${meta.dtype
        ? html`<div class="object-field">dtype ${meta.dtype}</div>`
        : null}
      ${file
        ? html`<div class="object-field" data-testid="object-path">
              ${file.path || file.name || ""}
            </div>
            <div class="object-field" data-testid="object-mime">
              ${mime || "application/octet-stream"}
            </div>
            ${size !== null
              ? html`<div class="object-field" data-testid="object-size">
                  ${size} bytes
                </div>`
              : null}`
        : html`<${Hint} data-testid="object-no-file">
            This object has no stored file; what is recorded about it is below.
          <//>`}
      ${isImage && file?.url && !imageFailed
        ? html`<img
            class="object-image"
            data-testid="object-image"
            src=${file.url}
            alt=${typeName(meta)}
            onError=${() => onImageError()}
          />`
        : null}
      ${recorded
        ? html`<pre class="object-metadata" data-testid="object-metadata">
${JSON.stringify(recorded, null, 2)}</pre
          >`
        : html`<${Hint} data-testid="object-no-metadata"
            >Nothing else is recorded about it.<//
          >`}
    <//>
  <//>`;
}
