/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { MetadataView } from "../../sdk/1/renderer-base.js";
const api = window.scistudio;
export {
  typeName,
  ancestry,
  recordedMetadata,
} from "../../sdk/1/renderer-base.js";

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

  return html`<${MetadataView}
    meta=${meta}
    file=${file}
    imageFailed=${imageFailed}
    onImageError=${() => setImageFailed(true)}
    error=${error}
  />`;
}

api
  .ready()
  .then(() => {
    render(html`<${FallbackPanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
