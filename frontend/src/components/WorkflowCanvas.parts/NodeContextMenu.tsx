/**
 * ADR-054 spec 4 (T-003) — the canvas node context menu (FR-002, FR-003).
 *
 * The canvas has no context menu today; this is it. FR-003 says it carries the
 * explore action alone until other actions are specified, so it does — one
 * item, and no menu framework to hang the rest on later than there needs to be.
 *
 * The action is *disabled with a reason* rather than hidden when the runtime
 * reports no outputs (FR-002): a person who right-clicks a block that has not
 * run should be told why there is nothing to explore, not left wondering why
 * the menu they were told about is empty.
 *
 * Modelled on `ProjectTree.parts/ContextMenu.tsx`, which is the menu this
 * application already has: fixed position at the pointer, dismissed by an
 * outside mousedown.
 */

import { useEffect, useRef } from "react";

export interface CanvasContextMenuState {
  x: number;
  y: number;
  nodeId: string;
  nodeLabel: string;
  /** FR-002 — `false` disables the action and shows `disabledReason`. */
  canExplore: boolean;
  disabledReason: string | null;
}

export interface NodeContextMenuProps {
  menu: CanvasContextMenuState | null;
  onClose: () => void;
  onExplore: (nodeId: string) => void;
}

export function NodeContextMenu({ menu, onClose, onExplore }: NodeContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return undefined;
    const handler = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [menu, onClose]);

  if (!menu) return null;

  return (
    <div
      ref={menuRef}
      className="fixed z-50 rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
      data-testid="canvas-node-context-menu"
      style={{ left: menu.x, top: menu.y }}
    >
      <button
        className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100 disabled:cursor-not-allowed disabled:text-stone-400 disabled:hover:bg-transparent"
        data-testid="canvas-explore-outputs"
        disabled={!menu.canExplore}
        onClick={() => {
          onExplore(menu.nodeId);
          onClose();
        }}
        title={menu.canExplore ? undefined : (menu.disabledReason ?? undefined)}
        type="button"
      >
        Explore outputs
      </button>
      {!menu.canExplore && menu.disabledReason ? (
        <p
          className="max-w-56 px-4 pb-1 pt-0.5 text-[11px] text-stone-400"
          data-testid="canvas-explore-disabled-reason"
        >
          {menu.disabledReason}
        </p>
      ) : null}
    </div>
  );
}
