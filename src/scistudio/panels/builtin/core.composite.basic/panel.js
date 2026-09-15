/* Core preview shell: read authority and view persistence. */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import { CompositeView } from "../../sdk/1/renderer-composite.js";
const api = window.scistudio;

function CompositePanel() {
  const [slots, setSlots] = useState(null);
  const [error, setError] = useState(null);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  /*
   * Every slot, page by page: a composite with more slots than one read carries
   * is paged by cursor, and the list shows all of them once the last page
   * lands (#2460).
   */
  useEffect(() => {
    let cancelled = false;
    const collected = [];
    const readFrom = (cursor) => {
      api
        .read("composite.slots", cursor ? { cursor } : {})
        .then((data) => {
          if (cancelled) return;
          const got = data.slots ?? [];
          collected.push(...got);
          const next = data.next_cursor ?? null;
          if (next && got.length) {
            readFrom(next);
            return;
          }
          if (next) throw new Error("The slot read did not advance");
          setSlots([...collected]);
        })
        .catch((err) => {
          if (!cancelled) fail(err);
        });
    };
    readFrom(null);
    return () => {
      cancelled = true;
    };
  }, [fail]);

  const open = useCallback(
    (ref) => {
      if (!api.open || !ref) return;
      // The row stays selectable: the reader returns here from the child view
      // and must be able to open the same slot again.
      api.open(ref).catch(fail);
    },
    [fail],
  );

  return html`<${CompositeView}
    slots=${slots}
    error=${error}
    onOpen=${api.open ? open : undefined}
  />`;
}

api
  .ready()
  .then(() => {
    render(html`<${CompositePanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
