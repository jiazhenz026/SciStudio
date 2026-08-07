// Shared palette hover-popover geometry and state machine.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §10.1 (hover positioning: anchor computation, POPOVER_GAP,
//   POPOVER_MAX_HEIGHT, open delay), §9.3 FR-044 (the popover becomes
//   interactive and survives the tile→popover gap), FR-046 (one popover
//   implementation serves blocks and types).
//
// The left palettes are pinned to the window's left edge, so a tile popover
// always opens to the right. The canvas has its own anchor
// (`nodes/BlockNode.parts/nodeDetailAnchor.ts`) because a placed node can sit
// anywhere and the viewport pans/zooms; that geometry is deliberately separate.

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
  right: number;
  top: number;
}

/**
 * Anchor a popover to the right of `rect`, clamped so the card stays on screen.
 *
 * `viewportHeight` defaults to `window.innerHeight`; when neither is available
 * (SSR / a bare jsdom document) the tile's own top is used unclamped.
 */
export function computeTileAnchor(rect: TileRect, viewportHeight?: number): PopoverAnchor {
  const height = viewportHeight ?? (typeof window === "undefined" ? undefined : window.innerHeight);
  const maxTop =
    height === undefined ? rect.top : Math.max(POPOVER_GAP, height - POPOVER_MAX_HEIGHT);
  return { left: rect.right + POPOVER_GAP, top: Math.min(rect.top, maxTop) };
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

  // Never leave a timer behind on unmount.
  useEffect(() => closeNow, [closeNow]);

  const openFor = useCallback(
    (item: T, rect: TileRect) => {
      clearOpen();
      keepOpen();
      const anchor = computeTileAnchor(rect);
      openTimer.current = setTimeout(() => {
        openTimer.current = null;
        setHovered({ item, anchor });
      }, POPOVER_OPEN_DELAY_MS);
    },
    [clearOpen, keepOpen],
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
