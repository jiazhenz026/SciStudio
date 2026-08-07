/**
 * A single tab in the TabStrip — title button (or rename input), status
 * decorations, rename (pencil) affordance, and close button. Extracted in
 * #1413 to keep the parent functions small.
 *
 * #1994 rename discoverability:
 *   Renaming used to be double-click-only, which is invisible to a user who
 *   has never been told about it. Hovering a tab now highlights its background,
 *   and on the *focused* tab a pencil button appears at the trailing edge; that
 *   button is the only pointer target that starts a rename. Clicking the tab
 *   body still selects the tab — a user who is not on a tab must be able to
 *   click it and land on it.
 *
 * Layout contract (owner review, #1994) — two rules that fight each other:
 *
 *   1. The affordance must not reserve space. An always-present slot revealed
 *      with `opacity` visibly widens the tab with an empty gap next to the ×.
 *   2. No control may move under the pointer when the affordance appears. If
 *      the pencil were simply mounted into the flex flow on hover, it would
 *      push the close button rightwards into the exact pixels a cursor aimed
 *      at × was travelling towards, turning "close this tab" into "rename it".
 *
 *   Both hold here because neither trailing control participates in layout:
 *   the close button is pinned with `absolute right-2` (its position is a
 *   function of the row's right edge alone, so nothing in the flow can shift
 *   it) and the pencil is pinned with `absolute right-7`, mounting and
 *   unmounting without contributing a single pixel of width. The row's right
 *   padding (`pr-8`) reserves exactly what the close button already occupied
 *   before this change, so tabs did not get wider.
 *
 *   The cost, stated plainly: the pencil overlays the last ~12px of the title
 *   on the focused tab while it is hovered. With no reserved space and a fixed
 *   close button, the trailing edge of the label is the only free real estate
 *   left. It is softened with a fade mask so the label slides under the button
 *   instead of being hard-clipped, and status decorations are moved to the
 *   *leading* edge so the pencil can never cover a running dot or an AI-Block
 *   badge. Trailing edge = actions, leading edge = status.
 */
import { Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { TerminalTab as TerminalTabModel } from "../../../store/types";

/**
 * Fades the trailing edge of the title so the overlaid pencil reads as the
 * label passing underneath it rather than as a glyph cut in half. Purely
 * visual — masks do not affect layout, so this cannot move anything.
 */
const TITLE_FADE = "linear-gradient(to right, #000 calc(100% - 14px), transparent 100%)";

export interface TabStripItemProps {
  tab: TerminalTabModel;
  active: boolean;
  isRenaming: boolean;
  renameDraft: string;
  onSelect: (id: string) => void;
  onStartRename: (id: string, title: string) => void;
  onRenameDraftChange: (value: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onRequestClose: (id: string) => void;
  renderBadge: () => ReactNode;
}

export function TabStripItem({
  tab,
  active,
  isRenaming,
  renameDraft,
  onSelect,
  onStartRename,
  onRenameDraftChange,
  onRenameCommit,
  onRenameCancel,
  onRequestClose,
  renderBadge,
}: TabStripItemProps) {
  // Drives both the hover highlight and the pencil reveal. Kept in React state
  // rather than a Tailwind `group-hover:` rule so the behaviour is observable
  // (and therefore testable) instead of living only in a stylesheet.
  const [pointerOver, setPointerOver] = useState(false);
  const [keyboardFocus, setKeyboardFocus] = useState(false);
  const engaged = pointerOver || keyboardFocus;

  // Only the focused tab offers rename. Background tabs show nothing at all:
  // you rename the tab you are working in, and a tab you are not on should
  // present exactly one pointer target — "switch to me".
  const revealed = active && !isRenaming && engaged;

  const highlight = active
    ? "bg-white text-ink shadow-sm"
    : engaged
      ? "bg-stone-200/70 text-stone-700"
      : "text-stone-500";

  // AI-Block badge and the running dot both live on the leading edge; see the
  // layout contract above. Mirrors AiBlockStatusBadge's own null check so the
  // wrapper (and its spacing) is omitted entirely when there is no decoration.
  const hasBadge = tab.source === "ai-block";
  const hasRunningDot = tab.state === "running" && !hasBadge;

  return (
    <div
      className={`relative flex items-center rounded-t-md py-1 pl-2 pr-8 text-xs ${highlight}`}
      role="tab"
      aria-selected={active}
      data-testid={`terminal-tab-${tab.id}`}
      data-hovered={pointerOver ? "true" : "false"}
      onMouseEnter={() => setPointerOver(true)}
      onMouseLeave={() => setPointerOver(false)}
      // React synthesises focusin/focusout here, so this covers any control
      // inside the row (title, pencil, close).
      onFocus={() => setKeyboardFocus(true)}
      onBlur={() => setKeyboardFocus(false)}
    >
      {isRenaming ? (
        <input
          className="w-24 rounded border border-stone-300 px-1 py-0 text-xs"
          value={renameDraft}
          autoFocus
          onChange={(e) => onRenameDraftChange(e.target.value)}
          onBlur={onRenameCommit}
          onKeyDown={(e) => {
            if (e.key === "Enter") onRenameCommit();
            else if (e.key === "Escape") onRenameCancel();
          }}
          data-testid={`terminal-tab-rename-input-${tab.id}`}
        />
      ) : (
        <button
          type="button"
          className="flex select-none items-center"
          onClick={() => onSelect(tab.id)}
          // Double-click is preserved: it predates the pencil and is muscle
          // memory for anyone who discovered it.
          onDoubleClick={() => onStartRename(tab.id, tab.title)}
          style={revealed ? { maskImage: TITLE_FADE, WebkitMaskImage: TITLE_FADE } : undefined}
          data-testid={`terminal-tab-title-${tab.id}`}
        >
          {hasBadge || hasRunningDot ? (
            <span
              className="-ml-1 mr-0.5 flex shrink-0 items-center"
              data-testid={`terminal-tab-status-${tab.id}`}
            >
              {/* ADR-035 §3.9 — AI-Block status decoration on the tab strip. */}
              {renderBadge()}
              {hasRunningDot ? (
                <span
                  className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"
                  aria-hidden
                />
              ) : null}
            </span>
          ) : null}
          {/* Only the label truncates. Status decorations sit outside this span
              so a long title can never clip them. */}
          <span className="max-w-[10rem] truncate" data-testid={`terminal-tab-label-${tab.id}`}>
            {tab.title}
          </span>
        </button>
      )}
      {revealed ? (
        <button
          type="button"
          // `absolute` is load-bearing, not decoration: it keeps this button
          // out of the flex flow so mounting it cannot displace the close
          // button. Do not convert this to an in-flow element.
          className="absolute right-7 inline-flex h-4 w-4 items-center justify-center rounded text-stone-400 hover:bg-stone-300 hover:text-stone-700"
          onClick={(e) => {
            e.stopPropagation();
            onStartRename(tab.id, tab.title);
          }}
          aria-label={`Rename ${tab.title}`}
          data-testid={`terminal-tab-rename-btn-${tab.id}`}
        >
          <Pencil size={12} aria-hidden="true" />
        </button>
      ) : null}
      <button
        type="button"
        // Pinned to the row's right edge; `pr-8` above reserves its space.
        // Nothing in the flow — including the pencil — can move it.
        className="absolute right-2 inline-flex h-4 w-4 items-center justify-center rounded text-stone-400 hover:bg-stone-200 hover:text-stone-700"
        onClick={(e) => {
          e.stopPropagation();
          onRequestClose(tab.id);
        }}
        aria-label={`Close ${tab.title}`}
        data-testid={`terminal-tab-close-btn-${tab.id}`}
      >
        ×
      </button>
    </div>
  );
}
