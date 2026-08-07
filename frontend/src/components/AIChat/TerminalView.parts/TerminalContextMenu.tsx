/**
 * ADR-034 — right-click Copy / Paste menu for the embedded PTY (#1994).
 *
 * Deliberately hand-rolled rather than pulled from a menu library: two items,
 * no submenus, no portal. It is positioned absolutely inside TerminalView's
 * already-`relative` frame, so the coordinates the caller passes are
 * frame-relative, not viewport-relative — that keeps the menu pinned to the
 * terminal when the bottom panel scrolls or resizes.
 *
 * Styling follows the terminal chrome (dark surface, white/10 hairline border)
 * rather than the app's light surfaces, so it reads as part of the terminal.
 *
 * Dismissal: Escape, any pointer-down outside the menu, or picking an item.
 * The outside-click listener runs on the capture phase so it still fires when
 * the click lands on xterm's own textarea, which stops propagation.
 *
 * Edge handling: the frame is `overflow-hidden`, so a menu opened near an edge
 * used to be clipped away entirely and became unclickable. After mount we
 * measure it and flip it to the other side of the cursor on either axis (see
 * resolveMenuPlacement). Measuring happens in useLayoutEffect, before paint, so
 * the corrected position is the first one the user sees — no visible jump.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { resolveMenuPlacement } from "./menuPlacement";

export interface TerminalContextMenuProps {
  /** Owning terminal tab; used for stable test ids. */
  tabId: string;
  /** Position within the terminal frame, in px. */
  x: number;
  y: number;
  /** False when the terminal has no selection — Copy is then disabled. */
  canCopy: boolean;
  onCopy: () => void;
  onPaste: () => void;
  onClose: () => void;
}

const ITEM_CLASS =
  "block w-full px-3 py-1.5 text-left text-xs text-stone-200 transition hover:bg-white/10 disabled:cursor-default disabled:text-stone-500 disabled:hover:bg-transparent";

export function TerminalContextMenu({
  tabId,
  x,
  y,
  canCopy,
  onCopy,
  onPaste,
  onClose,
}: TerminalContextMenuProps) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [placement, setPlacement] = useState<{ left: number; top: number }>({ left: x, top: y });

  // Measure and correct before paint. offsetParent is the `relative` terminal
  // frame the menu is absolutely positioned inside, which is the box the menu
  // must stay within; fall back to the viewport if the layout ever changes.
  useLayoutEffect(() => {
    const node = menuRef.current;
    if (!node) return;
    const frame = node.offsetParent as HTMLElement | null;
    const { left, top } = resolveMenuPlacement({
      x,
      y,
      menuWidth: node.offsetWidth,
      menuHeight: node.offsetHeight,
      frameWidth: frame?.clientWidth ?? window.innerWidth,
      frameHeight: frame?.clientHeight ?? window.innerHeight,
    });
    setPlacement({ left, top });
  }, [x, y]);

  useEffect(() => {
    const onPointerDown = (ev: MouseEvent) => {
      const node = menuRef.current;
      if (node && ev.target instanceof Node && node.contains(ev.target)) return;
      onClose();
    };
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        onClose();
      }
    };
    window.addEventListener("mousedown", onPointerDown, true);
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.removeEventListener("mousedown", onPointerDown, true);
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, [onClose]);

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label="Terminal actions"
      data-testid={`terminal-context-menu-${tabId}`}
      className="absolute z-50 min-w-[8rem] overflow-hidden rounded-lg border border-white/10 bg-[#252526] py-1 shadow-lg"
      style={{ left: placement.left, top: placement.top }}
    >
      <button
        type="button"
        role="menuitem"
        className={ITEM_CLASS}
        disabled={!canCopy}
        aria-disabled={!canCopy}
        data-testid={`terminal-context-copy-${tabId}`}
        onClick={onCopy}
      >
        Copy
      </button>
      <button
        type="button"
        role="menuitem"
        className={ITEM_CLASS}
        data-testid={`terminal-context-paste-${tabId}`}
        onClick={onPaste}
      >
        Paste
      </button>
    </div>
  );
}
