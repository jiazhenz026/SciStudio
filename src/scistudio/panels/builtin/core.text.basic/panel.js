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

/**
 * Chunks read in one go before the panel pauses and offers Read more. A pause,
 * not a cap: the rest of the document stays one press away (#2460).
 */
const CHUNKS_PER_BATCH = 512;

/** The text a chunk carries; the read names it both ways. */
export function chunkText(chunk) {
  const value = chunk?.text ?? chunk?.content;
  return typeof value === "string" ? value : "";
}

/**
 * Where the next read should start, or null when there is no forward read.
 *
 * A chunk that is not truncated is the end. A ``next_offset`` that does not move
 * forward is a reader that cannot advance; the panel reports it as a failure.
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
  const [resume, setResume] = useState(null);
  const [error, setError] = useState(null);
  const cancelled = useRef(false);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  const readBatch = useCallback(
    (start) => {
      setResume(null);
      let offset = start;
      let chunks = 0;
      const readFrom = (from) => {
        api
          .read("text.chunk", from ? { offset: from } : {})
          .then((chunk) => {
            if (cancelled.current) return;
            setText((prev) => prev + chunkText(chunk));
            setMeta(chunk);
            chunks += 1;
            if (chunk?.truncated !== true) {
              setDone(true);
              return;
            }
            const next = nextOffset(chunk, offset);
            // A reader that cannot advance is a failure, not the end of the text.
            if (next === null) throw new Error("The text read did not advance");
            offset = next;
            if (chunks >= CHUNKS_PER_BATCH) {
              setResume(next);
              return;
            }
            readFrom(next);
          })
          .catch((err) => {
            if (!cancelled.current) fail(err);
          });
      };
      readFrom(start);
    },
    [fail],
  );

  useEffect(() => {
    cancelled.current = false;
    readBatch(0);
    return () => {
      cancelled.current = true;
    };
  }, [readBatch]);

  return html`<${TextView}
    text=${text}
    meta=${meta}
    done=${done}
    hasMore=${resume !== null}
    onReadMore=${() => resume !== null && readBatch(resume)}
    error=${error}
  />`;
}

api
  .ready()
  .then(() => {
    render(html`<${TextPanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
