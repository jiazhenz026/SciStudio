/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { ArtifactView } from "../../sdk/1/renderer-artifact.js";
const api = window.scistudio;
export { isImage, inlineNotice } from "../../sdk/1/renderer-artifact.js";

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

  return html`<${ArtifactView}
    info=${info}
    url=${url}
    imageFailed=${imageFailed}
    onImageError=${() => setImageFailed(true)}
    error=${error}
  />`;
}

api
  .ready()
  .then(() => {
    render(html`<${ArtifactPanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
