/**
 * ADR-044 FR-011 (US5) + US6 AS2 — the single "choose / import a subworkflow
 * file" flow shared by BOTH entry points:
 *
 *   1. the canvas node affordance ("Choose subworkflow file…" on a node with no
 *      ref, "Locate file…" on a broken-ref placeholder), and
 *   2. the Config-tab `SubworkflowConfigEditor` button.
 *
 * Steps (per the FE-2 P1 task brief):
 *   1. Get an external file path via the existing native dialog
 *      (`api.openNativeDialog("file")` → `{ paths }`). Empty / cancelled aborts
 *      quietly. A thrown dialog error is reported via `setLastError` (the
 *      in-app FileBrowserModal fallback ConfigField uses is out of scope here;
 *      native-first is acceptable per the brief).
 *   2. `api.importSubworkflow(paths[0])` copies the file into
 *      `<project>/subworkflows/` and returns `{ ref_path, resolved_ports }`.
 *   3. Repoint the node: write `config.ref.path = ref_path` (top-level, via
 *      `setNodeRef`) so the canvas + flattener see the new reference and the
 *      workflow autosaves.
 *   4. Refresh handles WITHOUT a reload: push the returned `resolved_ports`
 *      onto the node (`setNodeResolvedPorts`) so it un-breaks and shows its
 *      exposed-port handles immediately.
 *   5. Any failure surfaces through `setLastError`.
 *
 * Both store actions are read off the global `useAppStore` so the flow has a
 * single home and neither entry point has to prop-drill them.
 */
import type { ResolvedSubworkflowPorts } from "../types/api";
import { api } from "./api";

export interface ChooseSubworkflowFileDeps {
  /** Repoint the node's `config.ref.path` (top-level). */
  setNodeRef: (nodeId: string, refPath: string) => void;
  /** Refresh the node's response-only resolved-port surface. */
  setNodeResolvedPorts: (nodeId: string, resolvedPorts: ResolvedSubworkflowPorts) => void;
  /** Surface failures on the workspace error banner. */
  setLastError: (message: string | null) => void;
}

/**
 * Run the shared choose/import-subworkflow flow for one node id. Returns the
 * imported `ref_path` on success, or `null` when the user cancelled or an error
 * was surfaced (the caller does not need to act on the result; the store + error
 * banner already reflect the outcome).
 */
export async function chooseSubworkflowFile(
  nodeId: string,
  deps: ChooseSubworkflowFileDeps,
): Promise<string | null> {
  const { setNodeRef, setNodeResolvedPorts, setLastError } = deps;

  let sourcePath: string | undefined;
  try {
    const dialog = await api.openNativeDialog("file");
    sourcePath = dialog.paths[0];
  } catch (error) {
    setLastError((error as Error).message);
    return null;
  }
  // Empty / cancelled: abort quietly (no error banner).
  if (!sourcePath) return null;

  try {
    const { ref_path, resolved_ports } = await api.importSubworkflow(sourcePath);
    setNodeRef(nodeId, ref_path);
    setNodeResolvedPorts(nodeId, resolved_ports);
    setLastError(null);
    return ref_path;
  } catch (error) {
    setLastError((error as Error).message);
    return null;
  }
}
