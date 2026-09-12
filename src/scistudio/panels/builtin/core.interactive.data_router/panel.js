/* core.interactive.data_router — send each input item to an output port.
 *
 * Built with Preact and the shared panel component set. The surface matches the
 * modal it replaces: the title and its instruction, the input ports on the left,
 * an arrow, the output ports on the right as drop zones, and a footer saying
 * how much is left to do beside Confirm. Cancel is the host's — the frame sits
 * in a dialog that offers it, and Escape, for every interactive panel.
 *
 * Interactive context. `api.input` carries:
 *   input_ports:    [portName, ...]
 *   items_per_port: { portName: [{ index, port, ref, name, type }, ...] }
 *   output_ports:   [portName, ...]
 * Confirm submits the block's decision unchanged:
 *   writeBack({ assignments: { outputPort: [ref, ...] } })
 * Every declared output port is present, empty when nothing was routed to it,
 * so the block produces every output it declared.
 */
import {
  html,
  render,
  useCallback,
  useMemo,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import { Button, ErrorState, Panel, Row, Spacer } from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

/** Every output port, in order, each seeded with nothing routed to it. */
export function emptyAssignments(outputPorts) {
  const assignments = {};
  for (const port of outputPorts || []) assignments[port] = [];
  return assignments;
}

/**
 * Route *ref* to *port*, taking it off whichever port currently holds it.
 *
 * An item belongs to exactly one output, so assigning is a move: leaving the
 * old entry behind would send one item to two outputs and make the counts lie.
 */
export function assignTo(assignments, ref, port) {
  if (!Object.prototype.hasOwnProperty.call(assignments, port)) return assignments;
  const next = unassignRef(assignments, ref);
  return { ...next, [port]: [...next[port], ref] };
}

/** Take *ref* off every output port, leaving it to be routed again. */
export function unassignRef(assignments, ref) {
  const next = {};
  for (const port of Object.keys(assignments)) {
    next[port] = assignments[port].filter((value) => value !== ref);
  }
  return next;
}

/** The items still waiting to be routed. */
export function unassigned(items, assignments) {
  const routed = new Set(Object.values(assignments).flat());
  return (items || []).filter((item) => !routed.has(item.ref));
}

function Chip({ item, onDragStart }) {
  return html`<div
    class="router-chip"
    data-testid=${`router-item-${item.ref}`}
    draggable="true"
    onDragStart=${(event) => onDragStart(event, item.ref)}
  >
    <span class="router-chip-name" title=${item.name}>${item.name}</span>
    <span class="router-chip-type">${item.type}</span>
  </div>`;
}

function RouterPanel({ inputPorts, outputPorts, itemsPerPort, items }) {
  const [assignments, setAssignments] = useState(() => emptyAssignments(outputPorts));
  const [over, setOver] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const waiting = useMemo(() => unassigned(items, assignments), [items, assignments]);
  const routedRefs = useMemo(
    () => new Set(Object.values(assignments).flat()),
    [assignments],
  );
  const byRef = useMemo(() => {
    const map = {};
    for (const item of items) map[item.ref] = item;
    return map;
  }, [items]);

  /*
   * Nothing left to route is done, including when there was nothing to route in
   * the first place. Requiring at least one item leaves a block whose inputs all
   * arrived empty with a Confirm that can never be pressed, and a run paused on
   * it until someone cancels — and submitting the empty assignment is valid:
   * every declared output port is present and produces an empty collection.
   */
  const done = waiting.length === 0;

  const onDragStart = useCallback((event, ref) => {
    event.dataTransfer.setData("text/plain", ref);
    event.dataTransfer.effectAllowed = "move";
  }, []);
  const allowDrop = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const submit = useCallback(() => {
    if (submitting) return;
    setSubmitting(true);
    api.writeBack({ assignments }).catch((err) => {
      setSubmitting(false);
      const message = err?.message || String(err);
      setError(message);
      api.reportError(message);
    });
  }, [assignments, submitting]);

  if (error) {
    return html`<${Panel}><${ErrorState}>${error}<//><//>`;
  }

  return html`<${Panel} class="router">
    <div class="router-head">
      <div class="router-title">Data Router</div>
      <div class="router-hint">
        Drag items from input ports onto output ports. All items must be assigned.
      </div>
    </div>
    <div class="router-body">
      <div
        class="router-col"
        data-testid="router-inputs"
        onDragOver=${allowDrop}
        onDrop=${(event) => {
          event.preventDefault();
          const ref = event.dataTransfer.getData("text/plain");
          if (ref) setAssignments((prev) => unassignRef(prev, ref));
        }}
      >
        <div class="router-caption">Inputs</div>
        ${inputPorts.map((port) => {
          const all = itemsPerPort[port] || [];
          const free = all.filter((item) => !routedRefs.has(item.ref));
          return html`<div class="router-port" key=${port}>
            <div class="router-port-name">
              ${port} <span class="router-count">(${free.length}/${all.length})</span>
            </div>
            <div class="router-chips">
              ${free.length
                ? free.map(
                    (item) => html`<${Chip} key=${item.ref} item=${item} onDragStart=${onDragStart} />`,
                  )
                : html`<span class="router-empty">All items assigned</span>`}
            </div>
          </div>`;
        })}
      </div>
      <div class="router-arrow">→</div>
      <div class="router-col" data-testid="router-outputs">
        <div class="router-caption">Outputs</div>
        ${outputPorts.map((port) => {
          const refs = assignments[port] || [];
          return html`<div
            class=${`router-port router-drop${over === port ? " router-over" : ""}`}
            key=${port}
            data-testid=${`router-output-${port}`}
            onDragOver=${(event) => {
              allowDrop(event);
              setOver(port);
            }}
            onDragLeave=${() => setOver((value) => (value === port ? null : value))}
            onDrop=${(event) => {
              event.preventDefault();
              setOver(null);
              const ref = event.dataTransfer.getData("text/plain");
              if (ref) setAssignments((prev) => assignTo(prev, ref, port));
            }}
          >
            <div class="router-port-name">
              ${port} <span class="router-count">(${refs.length})</span>
            </div>
            <div class="router-chips">
              ${refs.length
                ? refs.map((ref) =>
                    byRef[ref]
                      ? html`<${Chip} key=${ref} item=${byRef[ref]} onDragStart=${onDragStart} />`
                      : null,
                  )
                : html`<span class="router-empty">Drop items here</span>`}
            </div>
          </div>`;
        })}
      </div>
    </div>
    <${Row} class="router-foot">
      <span
        class=${`router-status${done ? " router-done" : " router-todo"}`}
        data-testid="router-status"
      >
        ${done ? "All items assigned" : `${waiting.length} item(s) not yet assigned`}
      </span>
      <${Spacer} />
      <${Button} primary data-testid="router-confirm" disabled=${!done || submitting} onClick=${submit}>
        Confirm
      <//>
    <//>
  <//>`;
}

api
  .ready()
  .then(() => {
    const payload = api.input && typeof api.input === "object" ? api.input : {};
    const inputPorts = Array.isArray(payload.input_ports) ? payload.input_ports : [];
    const outputPorts = Array.isArray(payload.output_ports) ? payload.output_ports : [];
    const itemsPerPort =
      payload.items_per_port && typeof payload.items_per_port === "object" ? payload.items_per_port : {};
    const items = inputPorts.flatMap((port) => itemsPerPort[port] || []);
    render(
      html`<${RouterPanel}
        inputPorts=${inputPorts}
        outputPorts=${outputPorts}
        itemsPerPort=${itemsPerPort}
        items=${items}
      />`,
      document.getElementById("root"),
    );
  })
  .catch((err) => api.reportError(String(err?.message || err)));
