/* core.base.fallback — anything no other panel claims.
 *
 * Built with Preact and the shared panel component set, on the same card the
 * artifact panel uses: the previewer this replaces *was* the artifact previewer
 * (the tier-8 fallback delegated straight to it), so a reader who lands here
 * sees the surface they already know.
 *
 * One thing is added, and it is the reason this panel exists separately: the
 * object's type. The previewer it replaces could describe a file — a path, a
 * MIME type, a size — but never said what the thing was, so an object that
 * reached the fallback because its type had no panel looked exactly like an
 * opaque blob. The chain is read from the object's own record.
 *
 * Faithful display (#1886): an object here may have no stored file at all, and
 * a card that simply omitted those lines would read as a file whose details
 * failed to load. Absence is stated.
 */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import { Card, ErrorState, Hint, LoadingState, Panel } from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

/** The object's own type: the most specific name its chain records. */
export function typeName(meta) {
  const chain = meta?.type_chain;
  if (Array.isArray(chain) && chain.length) return String(chain[chain.length - 1]);
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
  if (!recorded || typeof recorded !== "object" || Array.isArray(recorded)) return null;
  return Object.keys(recorded).length ? recorded : null;
}

function FallbackPanel() {
  const [meta, setMeta] = useState(null);
  const [file, setFile] = useState(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [error, setError] = useState(null);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .read("metadata", {})
      .then((result) => {
        if (cancelled) return null;
        setMeta(result);
        /*
         * Bytes are optional here: a fallback target may be an object the run
         * never wrote to storage. Losing this read costs the file lines, not
         * the card.
         */
        return api.read("artifact.file", {}).then(
          (result_) => {
            if (!cancelled) setFile(result_);
          },
          () => {},
        );
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      });
    return () => {
      cancelled = true;
    };
  }, [fail]);

  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read object: ${error}<//><//>`;
  }
  if (!meta) {
    return html`<${Panel}><${LoadingState}>Loading object…<//><//>`;
  }

  const chain = ancestry(meta);
  const recorded = recordedMetadata(meta);
  const mime = file?.mime_type || "";
  const isImage = typeof mime === "string" && mime.toLowerCase().startsWith("image/");
  const size = typeof file?.size === "number" ? file.size : null;

  return html`<${Panel}>
    <${Card}>
      <div class="object-title" data-testid="object-type">${typeName(meta)}</div>
      ${chain ? html`<div class="object-field" data-testid="object-chain">${chain}</div>` : null}
      ${meta.shape
        ? html`<div class="object-field">shape [${[].concat(meta.shape).join(", ")}]</div>`
        : null}
      ${meta.dtype ? html`<div class="object-field">dtype ${meta.dtype}</div>` : null}
      ${file
        ? html`<div class="object-field" data-testid="object-path">${file.path || file.name || ""}</div>
            <div class="object-field" data-testid="object-mime">${mime || "application/octet-stream"}</div>
            ${size !== null
              ? html`<div class="object-field" data-testid="object-size">${size} bytes</div>`
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
            onError=${() => setImageFailed(true)}
          />`
        : null}
      ${recorded
        ? html`<pre class="object-metadata" data-testid="object-metadata">
${JSON.stringify(recorded, null, 2)}</pre
          >`
        : html`<${Hint} data-testid="object-no-metadata">Nothing else is recorded about it.<//>`}
    <//>
  <//>`;
}

api
  .ready()
  .then(() => {
    render(html`<${FallbackPanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
