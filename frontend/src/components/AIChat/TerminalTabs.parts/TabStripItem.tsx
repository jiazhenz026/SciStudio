/**
 * A single tab in the TabStrip — title button (or rename input), running dot,
 * and close button. Extracted in #1413 to keep the parent functions small.
 */
import type { ReactNode } from "react";

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
  return (
    <div
      className={`flex items-center gap-1 rounded-t-md px-2 py-1 text-xs ${
        active ? "bg-white text-ink shadow-sm" : "text-stone-500 hover:text-stone-700"
      }`}
      role="tab"
      aria-selected={active}
      data-testid={`terminal-tab-${tab.id}`}
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
