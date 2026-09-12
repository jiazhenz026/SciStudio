/* core.artifact.basic — an opaque file artifact.
 *
 * Built with Preact and the shared panel component set. The surface matches the
 * viewer it replaces: a card headed "Artifact" carrying the storage path, the
 * MIME type, the size in bytes, and an image shown inline when the artifact is
 * one.
 *
 * Faithful display (#1886): the viewer showed an image only when the reading
 * layer had inlined one, and said nothing at all otherwise — so "this artifact
 * has no picture to show" and "the picture could not be loaded" looked exactly
 * alike, both of them an empty space below the metadata. Whenever there is no
 * inline view, this panel says which of those it is.
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

function ArtifactPanel() {
  const [info, setInfo] = useState(null);
  const [url, setUrl] = useState(null);
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
      .read("artifact.info", {})
      .then((result) => {
        if (cancelled) return null;
        setInfo(result);
        /*
         * The grant is a second, separately authorized read. Losing it costs
         * the inline view, not the card: the metadata already in hand is real
         * and still worth showing, and `inlineNotice` explains the absence.
         */
        return api.read("artifact.file", {}).then(
          (file) => {
            if (!cancelled) setUrl(file?.url ?? null);
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
    return html`<${Panel}><${ErrorState}>Could not read artifact: ${error}<//><//>`;
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
        ? html`<div class="artifact-field" data-testid="artifact-size">${size} bytes</div>`
        : null}
      ${isImage(mime) && url && !imageFailed
        ? html`<img
            class="artifact-image"
            data-testid="artifact-image"
            src=${url}
            alt=${info.name || "Artifact"}
            onError=${() => setImageFailed(true)}
          />`
        : null}
      ${notice ? html`<${Hint} data-testid="artifact-inline-notice">${notice}<//>` : null}
    <//>
  <//>`;
}

api
  .ready()
  .then(() => {
    render(html`<${ArtifactPanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
