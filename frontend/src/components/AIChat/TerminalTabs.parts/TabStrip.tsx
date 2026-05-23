/**
 * Tab strip across the top of TerminalTabs.
 *
 * Extracted in #1413 so the TerminalTabs container function stays under 150
 * lines. State (renaming draft, active id, etc.) lives in the parent and
 * flows in via props.
 */
import type { TerminalTab as TerminalTabModel } from "../../../store/types";
import { AiBlockStatusBadge } from "../TerminalTab";
import { TabStripItem } from "./TabStripItem";

export interface TabStripProps {
  tabs: TerminalTabModel[];
  activeTabId: string | null;
  renamingId: string | null;
  renameDraft: string;
  onSelect: (id: string) => void;
  onStartRename: (id: string, title: string) => void;
  onRenameDraftChange: (value: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onRequestClose: (id: string) => void;
  onAdd: () => void;
}

export function TabStrip(props: TabStripProps) {
  const { tabs, activeTabId, onAdd } = props;
  return (
    <div
      className="flex shrink-0 items-center gap-1 border-b border-stone-200 bg-stone-50/60 px-2 py-1"
      role="tablist"
      data-testid="terminal-tabs-strip"
    >
      {tabs.map((tab) => (
        <TabStripItem
          key={tab.id}
          tab={tab}
          active={tab.id === activeTabId}
          isRenaming={props.renamingId === tab.id}
          renameDraft={props.renameDraft}
          onSelect={props.onSelect}
          onStartRename={props.onStartRename}
          onRenameDraftChange={props.onRenameDraftChange}
          onRenameCommit={props.onRenameCommit}
          onRenameCancel={props.onRenameCancel}
          onRequestClose={props.onRequestClose}
          renderBadge={() => <AiBlockStatusBadge tabId={tab.id} />}
        />
      ))}
      <button
        type="button"
        className="ml-1 rounded p-1 text-stone-500 hover:bg-stone-200 hover:text-stone-700"
        onClick={onAdd}
        aria-label="New chat tab"
        data-testid="terminal-tabs-add"
      >
        +
      </button>
    </div>
  );
}
