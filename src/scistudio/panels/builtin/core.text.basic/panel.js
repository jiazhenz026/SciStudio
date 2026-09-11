/* core.text.basic — a text document.
 *
 * Built with Preact and the shared panel component set. The surface matches the
 * viewer it replaces: the content in a scrolling monospace block.
 *
 * Faithful display (#1886): a read is bounded, but the whole document is
 * reachable — the read reports where the next chunk starts, so the panel keeps
 * reading until the end instead of showing a fragment with a notice telling the
 * reader to open the file somewhere else. The size is reported as plain
 * information while the rest is still arriving, never as a caveat about data
 * that is in fact complete.
 */
import {
  html,
  render,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  ScrollArea,
} from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

/** Guard against a reader that never advances, so a read loop always ends. */
const MAX_CHUNKS = 512;

/** The text a chunk carries; the read names it both ways. */
export function chunkText(chunk) {
  const value = chunk?.text ?? chunk?.content;
  return typeof value === "string" ? value : "";
}

/**
 * Where the next read should start, or null when the document is fully read.
 *
 * A chunk that is not truncated is the end. A ``next_offset`` that does not move
 * forward is a reader that cannot advance, and is treated as the end rather than
 * being asked again.
 */
export function nextOffset(chunk, readSoFar) {
  if (!chunk || chunk.truncated !== true) return null;
  const next = chunk.next_offset;
  if (typeof next !== "number" || next <= readSoFar) return null;
  return next;
}

function TextPanel() {
  const [text, setText] = useState("");
  const [meta, setMeta] = useState(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const cancelled = useRef(false);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  useEffect(() => {
    cancelled.current = false;
    let offset = 0;
    let chunks = 0;
    const readFrom = (from) => {
      api
        .read("text.chunk", from ? { offset: from } : {})
        .then((chunk) => {
          if (cancelled.current) return;
          setText((prev) => prev + chunkText(chunk));
          setMeta(chunk);
          chunks += 1;
          const next = nextOffset(chunk, offset);
          if (next === null || chunks >= MAX_CHUNKS) {
            setDone(true);
            return;
          }
          offset = next;
          readFrom(next);
        })
        .catch((err) => {
          if (!cancelled.current) fail(err);
        });
    };
    readFrom(0);
    return () => {
      cancelled.current = true;
    };
  }, [fail]);

  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read text: ${error}<//><//>`;
  }
  if (!meta) {
    return html`<${Panel}><${LoadingState}>Loading text…<//><//>`;
  }
  if (done && text === "") {
    return html`<${Panel}><${EmptyState} data-testid="text-empty">This file is empty.<//><//>`;
  }

  const totalBytes = typeof meta.total_bytes === "number" ? meta.total_bytes : null;

  return html`<${Panel}>
    <${ScrollArea} class="text-surface">
      <pre class="text-content" data-testid="text-content">${text}</pre>
    <//>
    ${!done
      ? html`<${LoadingState} data-testid="text-loading-more">
          Reading the rest${totalBytes !== null ? ` of ${totalBytes.toLocaleString()} bytes` : ""}…
        <//>`
      : totalBytes !== null
        ? html`<div class="panel-hint" data-testid="text-size">
            ${totalBytes.toLocaleString()} bytes${meta.encoding ? ` · ${meta.encoding}` : ""}
          </div>`
        : null}
  <//>`;
}

api
  .ready()
  .then(() => {
    render(html`<${TextPanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
