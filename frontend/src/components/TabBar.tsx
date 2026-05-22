import type { TabState } from "../store/types";

interface TabBarProps {
  tabs: TabState[];
  activeTabId: string | null;
  onSwitchTab: (tabId: string) => void;
  onCloseTab: (tabId: string) => void;
  onNewTab: () => void;
}

export function TabBar({ tabs, activeTabId, onSwitchTab, onCloseTab, onNewTab }: TabBarProps) {
  return (
    <div className="flex items-center gap-0 border-b border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] px-1">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTabId;
        // ADR-036 §3.10: discriminated-union read site. Workflow tabs
        // surface the workflow name + workflowDirty; file tabs surface
        // displayName + their own dirty flag.
        const label = tab.kind === "workflow" ? tab.workflowName : tab.displayName;
        const isDirty = tab.kind === "workflow" ? tab.workflowDirty : tab.dirty;
        return (
          <div
            key={tab.id}
            className={`group flex max-w-[180px] items-center gap-1 border-r border-stone-200 px-3 py-1.5 text-xs transition-colors ${
              isActive
                ? "border-b-2 border-b-ember bg-white/80 font-medium text-ink"
                : "cursor-pointer text-stone-500 hover:bg-white/40 hover:text-stone-700"
            }`}
            onClick={() => onSwitchTab(tab.id)}
            role="tab"
            aria-selected={isActive}
          >
            <span className="min-w-0 flex-1 truncate" title={label}>
              {label}
            </span>
            <span
              style={{ visibility: isDirty ? "visible" : "hidden" }}
              className="shrink-0 text-[10px] text-amber-500"
              title="Unsaved changes"
            >
              {" *"}
            </span>
            <button
              type="button"
              className="ml-1 shrink-0 rounded p-0.5 text-stone-400 opacity-0 transition-opacity hover:bg-stone-200 hover:text-stone-600 group-hover:opacity-100"
              title="Close tab"
              onClick={(e) => {
                e.stopPropagation();
                onCloseTab(tab.id);
              }}
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 10 10"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path d="M2 2l6 6M8 2l-6 6" />
              </svg>
            </button>
          </div>
        );
      })}
      <button
        type="button"
        className="ml-1 rounded p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600"
        title="New workflow tab"
        onClick={onNewTab}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M6 2v8M2 6h8" />
        </svg>
      </button>
    </div>
  );
}
