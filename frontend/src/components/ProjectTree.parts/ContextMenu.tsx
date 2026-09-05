/**
 * Right-click context menu for ProjectTree. Extracted in #1413.
 */
import { useEffect, useRef } from "react";

import type { ContextMenuState, TreeNodeData } from "./types";

export interface ContextMenuProps {
  contextMenu: ContextMenuState | null;
  onClose: () => void;
  onCopyName: (name: string) => void;
  onCopyPath: (path: string) => void;
  onReveal: (node: TreeNodeData) => void;
  /**
   * ADR-054 FR-002 / FR-003 - open an Explore session over this file.
   *
   * OPTIONAL, and offered only for a file: the tree renders directories with
   * the same menu, and "explore this folder" is not a session the backend can
   * open. Absent means the action is not shown at all, which is what the
   * Project tree gets - FR-002 names the *data* tree.
   */
  onExplore?: (node: TreeNodeData) => void;
}

export function ContextMenu({
  contextMenu,
  onClose,
  onCopyName,
  onCopyPath,
  onReveal,
  onExplore,
}: ContextMenuProps) {
  const contextMenuRef = useRef<HTMLDivElement>(null);

  // Close on outside click.
  useEffect(() => {
    if (!contextMenu) return undefined;
    const handler = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [contextMenu, onClose]);

  if (!contextMenu) return null;

  return (
    <div
      ref={contextMenuRef}
      className="fixed z-50 rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
      style={{ left: contextMenu.x, top: contextMenu.y }}
    >
      {/* ADR-054 FR-002 - first, because it is the action the menu exists for
          on a data file; the three clipboard actions predate it. */}
      {onExplore && contextMenu.node.type === "file" ? (
        <button
          className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
          data-testid="tree-explore-file"
          onClick={() => {
            onExplore(contextMenu.node);
            onClose();
          }}
          type="button"
        >
          Explore in notebook
        </button>
      ) : null}
      <button
        className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
        onClick={() => onCopyName(contextMenu.node.name)}
        type="button"
      >
        Copy Name
      </button>
      <button
        className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
        onClick={() => onCopyPath(contextMenu.node.path)}
        type="button"
      >
        Copy Path
      </button>
      <button
        className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
        onClick={() => onReveal(contextMenu.node)}
        type="button"
      >
        Reveal in Explorer
      </button>
    </div>
  );
}
