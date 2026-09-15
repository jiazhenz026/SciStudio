/* core.interactive.pair_editor — line items up across ports so the right ones pair.
 *
 * Built with Preact and the shared panel component set. The surface matches the
 * modal it replaces: the title and its instruction, one column per port, one row
 * per pairing position with the row's items sharing a colour, and Confirm.
 * Cancel is the host's — the frame sits in a dialog that offers it, and Escape.
 *
 * Interactive context. `api.input` carries:
 *   ports:             [portName, ...]
 *   items_per_port:    { portName: [{ index, name, type }, ...] }
 *   collection_length: the shared length the ports are supposed to have
 * Confirm submits the block's decision unchanged:
 *   writeBack({ reorder: { port: [originalIndex, ...] } })
 * each list being that port's new order as original item indices.
 *
 * Faithful display (#1886), in two places the modal got away with and a themed
 * frame does not:
 *
 *   - A port with fewer items than the shared length left a blank cell saying
 *     nothing. A row where one port has no item is exactly what this editor
 *     exists to reveal, so the gap is named.
 *   - Every column was headed with the *shared* length, so a port holding two
 *     of three items still claimed three. The count is now the port's own.
 */
import {
  html,
  render,
  useCallback,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import { Button, ErrorState, Panel, Row, Spacer } from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

/*
 * Hues for the row colours. Only the hue is fixed here: the stylesheet turns it
 * into a tint that suits the current theme, because the modal's fixed pastels
 * were readable only against its permanently white background and this frame
 * follows the application's.
 */
const ROW_HUES = [214, 146, 265, 32, 344, 190, 250, 88, 168, 12];

/** Move the item at *from* to *to* within one port's order. */
export function moveWithin(order, from, to) {
  if (!Array.isArray(order)) return order;
  if (from === to || from < 0 || to < 0 || from >= order.length || to >= order.length) return order;
  const next = [...order];
  next.splice(to, 0, next.splice(from, 1)[0]);
  return next;
}

/** Each port's starting order: the order its items arrived in. */
export function initialOrders(ports, itemsPerPort) {
  const orders = {};
  for (const port of ports || []) {
    orders[port] = (itemsPerPort[port] || []).map((item) => item.index);
  }
  return orders;
}

/** Index each port's items by their original index, for lookup by order entry. */
export function itemsByIndex(ports, itemsPerPort) {
  const lookup = {};
  for (const port of ports || []) {
    lookup[port] = {};
    for (const item of itemsPerPort[port] || []) lookup[port][item.index] = item;
  }
  return lookup;
}

/**
 * How many rows to show.
 *
 * The declared length, but never fewer than a port actually holds: an item that
 * exists and is not on screen cannot be reordered, and would be submitted in
 * whatever position it happened to start in.
 */
export function rowCount(length, ports, itemsPerPort) {
  let rows = typeof length === "number" && length > 0 ? length : 0;
  for (const port of ports || []) rows = Math.max(rows, (itemsPerPort[port] || []).length);
  return rows;
}

function PairPanel({ ports, itemsPerPort, length }) {
  const [orders, setOrders] = useState(() => initialOrders(ports, itemsPerPort));
  /*
   * Where the drag started. A ref rather than state because the drop handler
   * has to read the value the dragstart just wrote, and a state update is not
   * visible to a handler running before the next render — which is exactly the
   * order a fast drag produces.
   */
  const source = useRef({ port: null, row: -1 });
  const [drag, setDrag] = useState({ port: null, row: -1 });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const lookup = itemsByIndex(ports, itemsPerPort);
  const rows = rowCount(length, ports, itemsPerPort);
  const columns = `repeat(${Math.max(ports.length, 1)}, minmax(0, 1fr))`;

  const submit = useCallback(() => {
    if (submitting) return;
    setSubmitting(true);
    api.writeBack({ reorder: orders }).catch((err) => {
      setSubmitting(false);
      const message = err?.message || String(err);
      setError(message);
      api.reportError(message);
    });
  }, [orders, submitting]);

  if (error) {
    return html`<${Panel}><${ErrorState}>${error}<//><//>`;
  }

  return html`<${Panel} class="pair">
    <div class="pair-head">
      <div class="pair-title">Pair Editor</div>
      <div class="pair-hint">
        Reorder items within each port so same-row items (same colour) are paired. Drag to reorder.
      </div>
    </div>
    <div class="pair-grid" style=${`grid-template-columns:${columns}`}>
      ${ports.map(
        (port) => html`<div class="pair-port-name" key=${port}>
          ${port} <span class="pair-count">(${(itemsPerPort[port] || []).length})</span>
        </div>`,
      )}
    </div>
    ${Array.from({ length: rows }, (_, row) => {
      const hue = ROW_HUES[row % ROW_HUES.length];
      return html`<div
        class="pair-grid"
        key=${row}
        style=${`grid-template-columns:${columns}`}
        data-testid=${`pair-row-${row}`}
      >
        ${ports.map((port) => {
          const originalIndex = (orders[port] || [])[row];
          const item = originalIndex === undefined ? null : lookup[port][originalIndex];
          if (!item) {
            // Naming the gap is the point: a port short of the others is the
            // mispairing this editor is for.
            return html`<div class="pair-cell pair-missing" key=${port} data-testid=${`pair-${port}-row-${row}`}>
              <span class="pair-rownum">${row + 1}</span>
              <span class="pair-none">no item on this row</span>
            </div>`;
          }
          return html`<div
            class=${`pair-cell${drag.port === port && drag.row === row ? " pair-over" : ""}`}
            key=${port}
            style=${`--pair-hue:${hue}`}
            data-testid=${`pair-${port}-row-${row}`}
            draggable="true"
            onDragStart=${(event) => {
              source.current = { port, row };
              setDrag({ port, row });
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("text/plain", `${port}:${row}`);
            }}
            onDragOver=${(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
            }}
            onDrop=${(event) => {
              event.preventDefault();
              // Reordering is within one port: an item cannot change which port
              // it came from, only where in that port's order it sits.
              const from = source.current;
              if (from.port === port) {
                setOrders((prev) => ({ ...prev, [port]: moveWithin(prev[port], from.row, row) }));
              }
              source.current = { port: null, row: -1 };
              setDrag({ port: null, row: -1 });
            }}
          >
            <span class="pair-rownum">${row + 1}</span>
            <span class="pair-name" title=${item.name}>${item.name}</span>
            <span class="pair-type">${item.type}</span>
          </div>`;
        })}
      </div>`;
    })}
    <${Row} class="pair-foot">
      <${Spacer} />
      <${Button} primary data-testid="pair-confirm" disabled=${submitting} onClick=${submit}>
        Confirm
      <//>
    <//>
  <//>`;
}

api
  .ready()
  .then(() => {
    const payload = api.input && typeof api.input === "object" ? api.input : {};
    const ports = Array.isArray(payload.ports) ? payload.ports : [];
    const itemsPerPort =
      payload.items_per_port && typeof payload.items_per_port === "object" ? payload.items_per_port : {};
    render(
      html`<${PairPanel} ports=${ports} itemsPerPort=${itemsPerPort} length=${payload.collection_length} />`,
      document.getElementById("root"),
    );
  })
  .catch((err) => api.reportError(String(err?.message || err)));
