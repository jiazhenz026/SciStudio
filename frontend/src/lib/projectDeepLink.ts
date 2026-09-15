/**
 * #2385 — the project deep link `open_gui` hands an agent.
 *
 * `?project=<absolute project path>&workflow=<workflow id>` asks this page to
 * show the project the backend already has open, instead of the welcome page.
 * The page is a second client of a session the user owns (normally the desktop
 * window), so it attaches read-only: it never re-opens the project and never
 * publishes its own editor context back to the backend.
 */

import { isDesktopShell } from "./presentation";

export interface ProjectDeepLink {
  /** Absolute project path, as the MCP context reports it. */
  project: string;
  /** Workflow id to show; `null` falls back to the backend's active workflow. */
  workflow: string | null;
}

/** Read the deep link from this page's URL, or `null` when there is none. */
export function readProjectDeepLink(
  search: string = window.location.search,
): ProjectDeepLink | null {
  // The desktop window is the session owner, never an attached client.
  if (isDesktopShell()) return null;
  const params = new URLSearchParams(search);
  const project = params.get("project")?.trim();
  if (!project) return null;
  const workflow = params.get("workflow")?.trim();
  return { project, workflow: workflow || null };
}

/**
 * Whether this page is an attached view of someone else's session. Side
 * effects that would change that session (publishing the active workflow,
 * auto-opening a project) are skipped while it is.
 */
export function isAttachedProjectView(): boolean {
  return readProjectDeepLink() !== null;
}

/** Compare two project paths, ignoring separator style and trailing separators. */
export function sameProjectPath(a: string, b: string): boolean {
  const normalise = (value: string) => value.replace(/\\/g, "/").replace(/\/+$/, "");
  return normalise(a) === normalise(b);
}
