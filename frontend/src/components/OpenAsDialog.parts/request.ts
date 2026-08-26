/**
 * The promise broker behind the "open as" picker (#2112).
 *
 * Kept out of the component file because the caller is `ProjectTree`'s plain
 * async double-click handler, not a component: it awaits an answer rather than
 * rendering one. Its own module so the component file exports only a
 * component, which is what keeps fast refresh working.
 */

import type { DataOpenAsCandidate } from "../../types/api";

export interface OpenAsRequest {
  /** File name shown in the heading. */
  displayName: string;
  /** Normalized extension the choice is keyed on (".tif"). */
  extension: string;
  /** Ordered project -> package -> core; the first entry is preselected. */
  candidates: DataOpenAsCandidate[];
  /** The current remembered type, when the picker was reopened to change it. */
  remembered?: string | null;
}

export interface OpenAsAnswer {
  typeName: string;
  remember: boolean;
}

export type PendingOpenAs = OpenAsRequest & { resolve: (answer: OpenAsAnswer | null) => void };

type Listener = (request: PendingOpenAs | null) => void;

let listener: Listener | null = null;

/** Register the mounted dialog as the answerer. Returns an unsubscribe. */
export function subscribeToOpenAsRequests(next: Listener): () => void {
  listener = next;
  return () => {
    listener = null;
  };
}

/**
 * Whether a dialog is mounted to answer {@link requestOpenAs}.
 *
 * Callers check this rather than treating an unanswerable request as a cancel:
 * with no dialog mounted (a test rendering a bare tree, a headless render) the
 * right behaviour is to fall through to the backend's own type resolution, not
 * to refuse to open the file.
 */
export function isOpenAsDialogMounted(): boolean {
  return listener !== null;
}

/** Ask which type to open a file as; resolves null when cancelled. */
export function requestOpenAs(request: OpenAsRequest): Promise<OpenAsAnswer | null> {
  if (listener === null) return Promise.resolve(null);
  return new Promise<OpenAsAnswer | null>((resolve) => {
    listener?.({ ...request, resolve });
  });
}
