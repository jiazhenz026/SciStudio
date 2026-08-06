/**
 * A single tab in the TabStrip — title button (or rename input), running dot,
 * rename (pencil) affordance, and close button. Extracted in #1413 to keep the
 * parent functions small.
 *
 * #1994 rename discoverability:
 *   Renaming used to be double-click-only, which is invisible to a user who
 *   has never been told about it. Hovering (or keyboard-focusing) a tab now
 *   highlights its background and reveals a pencil button on the right; that
 *   button is the *only* pointer target that starts a rename. Clicking the
 *   tab body still selects the tab, which is what the owner asked for: a user
 *   who is not on a tab must be able to click it and land on it.
 *
 *   Layout note — the pencil occupies a permanent slot and is revealed with
 *   `opacity`, never by mounting/unmounting. If it were conditionally
 *   rendered, hovering a tab would push the close button sideways underneath
 *   the pointer and turn "close this tab" into "rename this tab". Opacity also
 *   keeps the button in the focus order, so keyboard users can reach rename;
 *   focusing it reveals it via `onFocus` on the row.
 */
import { Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { TerminalTab as TerminalTabModel } from "../../../store/types";

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
  const revealed = !isRenaming && (pointerOver || keyboardFocus);

  const highlight = active
    ? "bg-white text-ink shadow-sm"
    : pointerOver || keyboardFocus
      ? "bg-stone-200/70 text-stone-700"
      : "text-stone-500";

  return (
    <div
      className={`flex items-center gap-1 rounded-t-md px-2 py-1 text-xs ${highlight}`}
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
          className="select-none"
          onClick={() => onSelect(tab.id)}
          // Double-click is preserved: it predates the pencil and is muscle
          // memory for anyone who discovered it.
          onDoubleClick={() => onStartRename(tab.id, tab.title)}
          data-testid={`terminal-tab-title-${tab.id}`}
        >
          {tab.title}
          {/* ADR-035 §3.9 — AI-Block status decoration on the tab strip. */}
          {renderBadge()}
          {tab.state === "running" && tab.source !== "ai-block" ? (
            <span
              className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"
              aria-hidden
            />
          ) : null}
        </button>
      )}
      {isRenaming ? null : (
        <button
          type="button"
          className={`ml-1 rounded p-0.5 text-stone-400 transition-opacity hover:bg-stone-300 hover:text-stone-700 ${
            revealed ? "opacity-100" : "opacity-0"
          }`}
          onClick={(e) => {
            e.stopPropagation();
            onStartRename(tab.id, tab.title);
          }}
          aria-label={`Rename ${tab.title}`}
          data-testid={`terminal-tab-rename-btn-${tab.id}`}
          data-revealed={revealed ? "true" : "false"}
        >
          <Pencil size={12} aria-hidden="true" />
        </button>
      )}
      <button
        type="button"
        className="ml-1 rounded p-0.5 text-stone-400 hover:bg-stone-200 hover:text-stone-700"
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
