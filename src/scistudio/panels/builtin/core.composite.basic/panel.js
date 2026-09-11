/* core.composite.basic — the slot inventory of a composite, with drill-down.
 *
 * Built with Preact and the shared panel component set. The surface matches the
 * viewer it replaces: a slot count, then one full-width row per slot showing the
 * slot's name over the type it holds, with a trailing preview hint. Selecting a
 * row opens that slot, which the host renders with its own panel and a Back
 * action — the composite lists what is inside it and routes; it never renders a
 * child itself.
 */
import {
  html,
  render,
  useCallback,
  useEffect,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import {
  EmptyState,
  ErrorState,
  ListRow,
  LoadingState,
  Panel,
} from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

function CompositePanel() {
  const [slots, setSlots] = useState(null);
  const [error, setError] = useState(null);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .read("composite.slots", {})
      .then((data) => {
        if (!cancelled) setSlots(data.slots ?? []);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      });
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

  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read slots: ${error}<//><//>`;
  }
  if (slots === null) {
    return html`<${Panel}><${LoadingState}>Loading slots…<//><//>`;
  }
  if (!slots.length) {
    return html`<${Panel}>
      <${EmptyState} data-testid="composite-empty">This composite has no slots.<//>
    <//>`;
  }

  return html`<${Panel}>
    <div class="panel-label" data-testid="composite-summary">
      ${slots.length} slot${slots.length === 1 ? "" : "s"}
    </div>
    ${slots.map(
      (slot) => html`<${ListRow}
        key=${slot.name}
        data-testid=${`composite-slot-${slot.name}`}
        label=${slot.name}
        value=${String(slot.type_name || "")}
        trailing=${api.open ? "Preview →" : undefined}
        title=${slot.ref ?? ""}
        onClick=${() => open(slot.ref)}
      />`,
    )}
  <//>`;
}

api
  .ready()
  .then(() => {
    render(html`<${CompositePanel} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
