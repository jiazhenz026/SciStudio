/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { TextView } from "../../sdk/1/renderer-text.js";
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

  return html`<${TextView}
    text=${text}
    meta=${meta}
    done=${done}
    error=${error}
  />`;
}

api
  .ready()
  .then(() => {
    render(html`<${TextPanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
