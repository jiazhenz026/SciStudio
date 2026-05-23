/**
 * Shared types for ProjectTree and its parts. Extracted in #1413.
 */
import type { TreeEntry } from "../../types/api";

export interface TreeNodeData extends TreeEntry {
  path: string;
  children?: TreeNodeData[];
  loaded: boolean;
  expanded: boolean;
}

export interface ContextMenuState {
  x: number;
  y: number;
  node: TreeNodeData;
}
