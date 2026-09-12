/**
 * Pointing a tutorial step at something inside a panel frame (ADR-054).
 *
 * A step's highlight is measured by walking the host document for
 * `[data-tutorial-target]` and reading the element's box. A panel's elements are
 * in another document, so that walk cannot see them — and when it finds nothing
 * the step degrades silently to a centred card with no ring. Two of the core
 * tutorials' targets moved into panels (`preview_item` in the collection panel,
 * `plot_export_button` in the plot panel), so six steps of `what-is-a-type`
 * pointed at nothing and said so to nobody.
 *
 * This is the small amount of shared state the two sides need, kept out of the
 * app store deliberately: it is per-frame measurement that changes with layout,
 * not application state, and nothing outside this file and its two callers has
 * any use for it.
 *
 * How it fits together:
 *
 *   - `useHighlightRect` says which target is wanted; only then does a panel
 *     measure anything, so a frame with no step pointing into it does no work.
 *   - `PanelFrame` forwards that to its frame and reports the box back.
 *   - `measure()` asks here when the host document has no such element, and gets
 *     a viewport box built from the frame's current position plus the box the
 *     panel reported inside it.
 *
 * The frame element is held rather than its box so that scrolling or resizing
 * the host moves the ring without the panel having to notice and report again:
 * only movement *inside* the frame needs a new report.
 */

/** A box in some viewport's coordinates. */
export interface PanelHighlightRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** The target a step is pointing at, as a panel would match it. */
export interface PanelHighlightRequest {
  target: string;
  /** The `data-tutorial-target-key` value, for targets that annotate many elements. */
  key: string | null;
}

interface Reported {
  request: PanelHighlightRequest;
  /** The element's box in the frame's own viewport coordinates. */
  rect: PanelHighlightRect;
  frame: HTMLIFrameElement;
}

let wanted: PanelHighlightRequest | null = null;
const listeners = new Set<(request: PanelHighlightRequest | null) => void>();
/** Keyed by frame, so closing one panel cannot leave another's box behind. */
const reported = new Map<HTMLIFrameElement, Reported>();

function sameRequest(a: PanelHighlightRequest | null, b: PanelHighlightRequest | null): boolean {
  if (a === null || b === null) return a === b;
  return a.target === b.target && a.key === b.key;
}

/**
 * Say which target the step is pointing at, or `null` while it points at none.
 *
 * Idempotent: repeating the current request notifies nobody, which matters
 * because the caller is a per-frame loop.
 */
export function requestPanelHighlight(request: PanelHighlightRequest | null): void {
  if (sameRequest(wanted, request)) return;
  wanted = request;
  if (request === null) reported.clear();
  for (const listener of listeners) listener(wanted);
}

/** Follow the wanted target; the listener is called immediately with the current one. */
export function subscribePanelHighlight(
  listener: (request: PanelHighlightRequest | null) => void,
): () => void {
  listeners.add(listener);
  listener(wanted);
  return () => {
    listeners.delete(listener);
  };
}

/** A frame reports where its matching element sits, or that it has none. */
export function reportPanelHighlight(
  frame: HTMLIFrameElement,
  request: PanelHighlightRequest,
  rect: PanelHighlightRect | null,
): void {
  if (rect === null) reported.delete(frame);
  else reported.set(frame, { request, rect, frame });
}

/** Forget a frame's report; call this when the frame goes away. */
export function forgetPanelHighlight(frame: HTMLIFrameElement): void {
  reported.delete(frame);
}

/**
 * The wanted target's box in host viewport coordinates, or `null`.
 *
 * The frame's position is read now rather than when the panel reported, so the
 * ring follows the host's own scrolling and resizing for free.
 */
export function panelHighlightRect(target: string, key: string | null): PanelHighlightRect | null {
  for (const entry of reported.values()) {
    if (entry.request.target !== target || entry.request.key !== key) continue;
    if (!entry.frame.isConnected) continue;
    const frameBox = entry.frame.getBoundingClientRect();
    if (frameBox.width <= 0 || frameBox.height <= 0) continue;
    const box = {
      top: frameBox.top + entry.rect.top,
      left: frameBox.left + entry.rect.left,
      width: entry.rect.width,
      height: entry.rect.height,
    };
    if (box.width <= 0 || box.height <= 0) continue;
    return box;
  }
  return null;
}

/** Test seam: drop every request and report. */
export function resetPanelHighlights(): void {
  wanted = null;
  reported.clear();
  listeners.clear();
}
