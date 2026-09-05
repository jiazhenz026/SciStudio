/**
 * ADR-054 spec 1, T-011 — which project files are panel files, and which panel
 * they belong to (FR-030, FR-032).
 *
 * A panel is a directory on disk in every tier (D-015), so a change to any file
 * inside `<project>/panels/<panel_id>/` is a change to that panel: the entry
 * document, its declaration, an asset it loads. The legacy `previewers/`
 * drop-in directory is recognised on the same terms, because FR-020 keeps it
 * working and a person editing one expects the same reload.
 *
 * **Why the path is what identifies the panel.** The reload trigger has to fire
 * for a file the *agent* wrote on the person's behalf (FR-032), and an agent
 * writes a file with its own editing tools rather than through a SciStudio
 * endpoint — so there is no request to attach a panel id to. The path is the
 * only thing both writers have in common, which is why this reads an id out of
 * it rather than taking one from whoever asked.
 *
 * This module deliberately imports nothing: it is read by the websocket
 * dispatcher, which must stay cheap, and by tests that hand it strings.
 */

/** The two directory names a panel tier uses, most specific first. */
export const PANEL_DIRECTORY_NAMES = ["panels", "previewers"] as const;

/**
 * The panel id a changed project file belongs to, or `null`.
 *
 * `path` is project-relative, in the spelling the `file.changed` event carries
 * (POSIX separators). Backslashes are accepted anyway, because a watcher on
 * Windows is one platform detail away from producing them and a reload that
 * silently stopped working on one platform is exactly the failure FR-032 is
 * written against.
 *
 * A file directly inside the directory (`panels/thing.py`, the old flat drop-in
 * form) belongs to no panel *directory* and returns `null`: it is a module-form
 * previewer, reloaded by rebuilding the registry rather than by remounting one
 * panel.
 */
export function panelIdForProjectPath(path: unknown): string | null {
  if (typeof path !== "string" || path === "") return null;
  const parts = path.split(/[\\/]+/).filter((part) => part !== "" && part !== ".");
  if (parts.length < 3) return null;
  if (!(PANEL_DIRECTORY_NAMES as readonly string[]).includes(parts[0])) return null;
  const panelId = parts[1];
  // A panel id is a directory name; `..` would be a traversal rather than one.
  if (panelId === "" || panelId === "..") return null;
  return panelId;
}

/** Is `path` a file inside some panel's directory? */
export function isPanelProjectPath(path: unknown): boolean {
  return panelIdForProjectPath(path) !== null;
}
