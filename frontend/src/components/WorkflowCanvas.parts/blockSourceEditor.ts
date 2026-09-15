import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import type { BlockSummary } from "../../types/api";

export const canEditBlockSource = (summary: BlockSummary) =>
  summary.origin === "project" || summary.origin === "user";

const normalized = (path: string) => path.replace(/\\/g, "/").replace(/\/$/, "");

/** Resolve registered source first; existing file APIs retain write authority. */
export async function openBlockEditor(summary: BlockSummary): Promise<void> {
  if (!canEditBlockSource(summary)) {
    useAppStore.getState().openBlockSourceTab(summary.type_name);
    return;
  }
  const project = useAppStore.getState().currentProject;
  try {
    const source = await api.getBlockSource(summary.type_name);
    if (useAppStore.getState().currentProject !== project)
      throw new Error("The project changed while resolving block source. Please try again.");
    const path = normalized(source.path);
    if (source.origin === "project" && project) {
      const prefix = `${normalized(project.path)}/`;
      if (!path.startsWith(prefix))
        throw new Error("The block source is outside the current project.");
      const relative = path.slice(prefix.length);
      if (!relative || relative.split("/").some((part) => part === ".." || part === "."))
        throw new Error("The block source has no valid project file path.");
      useAppStore.getState().openFileTab(relative);
      return;
    }
    if (source.origin === "user") {
      const filename = path.split("/").pop();
      if (!filename) throw new Error("The block source has no file name.");
      // A basename alone could name a different file in a nested or changed
      // library. Resolve it through the existing library route and compare.
      const file = await api.getUserLibraryFile("blocks", filename);
      if (useAppStore.getState().currentProject !== project)
        throw new Error("The project changed while resolving block source. Please try again.");
      if (normalized(file.path) !== path)
        throw new Error("This block source is not the editable file in My Library.");
      useAppStore.getState().openUserLibraryFileTab("blocks", filename);
      return;
    }
    throw new Error("This block source is no longer editable from this project.");
  } catch (error) {
    window.alert(`Could not edit block: ${error instanceof Error ? error.message : String(error)}`);
  }
}
