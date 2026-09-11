// Shared palette hover-popover geometry and state machine.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §10.1 (hover positioning: anchor computation, POPOVER_GAP,
//   POPOVER_MAX_HEIGHT, open delay), §9.3 FR-044 (the popover becomes
//   interactive and survives the tile→popover gap), FR-046 (one popover
//   implementation serves blocks and types).
//
// Palette popovers open toward the workspace stage, based on sidebar placement. The canvas has its own anchor
// (`nodes/BlockNode.parts/nodeDetailAnchor.ts`) because a placed node can sit
// anywhere and the viewport pans/zooms; that geometry is deliberately separate.

import { useSidebarSide } from "../../lib/presentation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export interface PopoverAnchor {
  /** Viewport-space left edge for the popover. */
  left: number;
  /** Viewport-space top edge for the popover. */
  top: number;
}

/** Gap (px) between a tile's right edge and the detail popover. */
export const POPOVER_GAP = 8;
/** Hover dwell before the detail popover opens. */
export const POPOVER_OPEN_DELAY_MS = 150;
/** Rough popover height used to keep the card inside the viewport. */
export const POPOVER_MAX_HEIGHT = 240;
/**
 * Grace period after the pointer leaves a tile before the popover closes.
 *
 * FR-044: the `POPOVER_GAP` between tile and popover is dead space with no
 * element under the cursor, so a leave/enter pair fires while the pointer is
 * in transit. Closing immediately would make the popover unreachable and no
 * button inside it could ever be clicked. The popover cancels this timer on
 * its own pointer-enter.
 */
export const POPOVER_CLOSE_DELAY_MS = 120;

/** The part of a `DOMRect` the tile anchor needs. */
export interface TileRect {
  left?: number;
  right: number;
  top: number;
}

export const POPOVER_WIDTH = 256;

/** Prefer the stage-facing side, flip on collision, then clamp to the viewport. */
export function computeTileAnchor(
  rect: TileRect,
  viewportHeight = window.innerHeight,
  {
    preferredSide = "right",
    viewportWidth = window.innerWidth,
  }: {
    preferredSide?: "left" | "right";
    viewportWidth?: number;
  } = {},
): PopoverAnchor {
  const width = Math.min(POPOVER_WIDTH, Math.max(0, viewportWidth - 2 * POPOVER_GAP));
  const right = rect.right + POPOVER_GAP;
  const left = (rect.left ?? rect.right) - POPOVER_GAP - width;
  const fits = (x: number) => x >= POPOVER_GAP && x + width <= viewportWidth - POPOVER_GAP;
  const preferred = preferredSide === "left" ? left : right;
  const alternate = preferredSide === "left" ? right : left;
  const candidate = fits(preferred) ? preferred : fits(alternate) ? alternate : preferred;
  return {
    left: Math.max(POPOVER_GAP, Math.min(candidate, viewportWidth - POPOVER_GAP - width)),
    top: Math.max(POPOVER_GAP, Math.min(rect.top, viewportHeight - POPOVER_MAX_HEIGHT)),
  };
}

/** The item a popover is currently open for, and where it sits. */
export interface HoverTarget<T> {
  item: T;
  anchor: PopoverAnchor;
}

/**
 * Props a surface spreads onto its popover so the popover keeps itself open
 * while the pointer is inside it (FR-044). Spreading this is what makes a
 * popover interactive — a caller that does not spread it (the canvas node
 * popover, `frontend-block-palette` spec §10) stays display-only.
 */
export interface PopoverHoverProps {
  interactive: true;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export interface HoverPopoverController<T> {
  /** The currently open target, or `null`. */
  hovered: HoverTarget<T> | null;
  /** Tile pointer-enter: open after the dwell delay, anchored to `rect`. */
  openFor: (item: T, rect: TileRect) => void;
  /** Tile pointer-leave: close after the transit grace period. */
  scheduleClose: () => void;
  /** Cancel a pending close (the pointer reached the popover). */
  keepOpen: () => void;
  /** Close now, cancelling everything pending (drag start, add, unmount). */
  closeNow: () => void;
  /** Spread onto the popover to make it interactive. */
  popoverProps: PopoverHoverProps;
}

/**
 * Hover state machine shared by the Blocks and Data types palettes.
 *
 * Open is delayed by `POPOVER_OPEN_DELAY_MS` so the popover does not flash
 * while the pointer sweeps the grid; close is delayed by
 * `POPOVER_CLOSE_DELAY_MS` so the pointer can cross `POPOVER_GAP` into the
 * card and click what is inside it.
 */
export function useHoverPopover<T>(): HoverPopoverController<T> {
  const sidebarSide = useSidebarSide();
  const preferredSide = sidebarSide === "right" ? "left" : "right";
  const openTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [hovered, setHovered] = useState<HoverTarget<T> | null>(null);

  const clearOpen = useCallback(() => {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
  }, []);

  const keepOpen = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const closeNow = useCallback(() => {
    clearOpen();
    keepOpen();
    setHovered(null);
  }, [clearOpen, keepOpen]);

  // A moved/resized/scrolled sidebar invalidates viewport-space anchors.
  useEffect(() => {
    closeNow();
    window.addEventListener("resize", closeNow);
    const onScroll = (event: Event) => {
      if (event.target instanceof Element && event.target.closest("[data-palette-popover]")) return;
      closeNow();
    };
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", closeNow);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [preferredSide, closeNow]);

  // Never leave a timer behind on unmount.
  useEffect(() => closeNow, [closeNow]);

  const openFor = useCallback(
    (item: T, rect: TileRect) => {
      clearOpen();
      keepOpen();
      const anchor = computeTileAnchor(rect, window.innerHeight, { preferredSide });
      openTimer.current = setTimeout(() => {
        openTimer.current = null;
        setHovered({ item, anchor });
      }, POPOVER_OPEN_DELAY_MS);
    },
    [clearOpen, keepOpen, preferredSide],
  );

  const scheduleClose = useCallback(() => {
    clearOpen();
    keepOpen();
    closeTimer.current = setTimeout(() => {
      closeTimer.current = null;
      setHovered(null);
    }, POPOVER_CLOSE_DELAY_MS);
  }, [clearOpen, keepOpen]);

  const popoverProps = useMemo<PopoverHoverProps>(
    () => ({ interactive: true, onMouseEnter: keepOpen, onMouseLeave: scheduleClose }),
    [keepOpen, scheduleClose],
  );

  return { hovered, openFor, scheduleClose, keepOpen, closeNow, popoverProps };
}
