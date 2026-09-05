/**
 * ADR-054 spec 1, T-011 — the hot-reload token a mounted panel is keyed on
 * (FR-030, FR-032).
 *
 * Saving a panel must reload it: every mounted instance of that panel is torn
 * down and remounted from the new document, without the person reopening the
 * view. The frame boundary is what makes that a clean operation — discarding a
 * frame leaves no cached module behind — so all the frontend needs is a value
 * that changes when the document did, and `PanelHost` does the rest through its
 * `remountToken` prop.
 *
 * The token is a *pair*: the per-panel counter, so saving one panel remounts
 * only that panel, and the global epoch, so a change that named no panel (a
 * registry rebuild, a package install, a branch switch) remounts everything on
 * screen. Reading both here rather than at each call site is what keeps the two
 * halves from drifting apart.
 *
 * **Where the two counters come from, and the FR-032 trap.** Both are written
 * by the websocket dispatcher: `blocks.reloaded` bumps the epoch, and a
 * `file.changed` naming a path inside a panel directory bumps that panel's
 * counter. The second one is the half FR-032 is about, and it is deliberately
 * keyed on the *path* rather than on who asked: an agent writing a panel file
 * on the person's behalf uses its own editing tools and makes no request the
 * product could attach an identity to. The backend's echo suppression is keyed
 * on an exact `(path, mtime, size)` signature registered by SciStudio's own
 * write endpoints, so an agent write registers nothing and is not suppressed —
 * see the report on A-007 in the issue. What the agent write needs is for the
 * watcher to emit the event at all.
 */

import { useAppStore } from ".";

/**
 * The remount token for one panel, or for "no panel in particular".
 *
 * Pass it straight to `PanelHost`'s `remountToken`. A `null` panel id yields a
 * token that tracks the epoch only, which is what a surface with no mounted
 * panel yet should hold on to.
 */
export function usePanelReloadToken(panelId: string | null | undefined): string {
  const epoch = useAppStore((state) => state.panelDocumentEpoch);
  const version = useAppStore((state) =>
    panelId ? (state.panelDocumentVersions[panelId] ?? 0) : 0,
  );
  return `${epoch}:${version}`;
}
