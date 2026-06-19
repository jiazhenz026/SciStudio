import type { BlockSchemaResponse, LogEntry, WorkflowNode } from "../types/api";
import type { BottomTab } from "../types/ui";

import { TerminalTabs } from "./AIChat/TerminalTabs";
import { GitTab } from "./Git/GitTab";
import { LineageTab } from "./Lineage/LineageTab";

import { ConfigPanel } from "./BottomPanel.parts/ConfigPanel";
import { LogViewer } from "./BottomPanel.parts/LogViewer";
import { TabBar } from "./BottomPanel.parts/TabBar";

interface BottomPanelProps {
  activeTab: BottomTab;
  selectedNode: WorkflowNode | null;
  selectedSchema?: BlockSchemaResponse;
  logEntries: LogEntry[];
  onTabChange: (tab: BottomTab) => void;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
  // Unread counter for the Logs tab badge. Defaults to 0; the badge
  // renders only when > 0. (The Problems tab was removed — block errors
  // are already represented by an inline badge on the BlockNode itself
  // and by error-level rows in the Logs panel.)
  unreadLogsCount?: number;
  /**
   * When true, the bottom panel is "pinned" — App.tsx will skip the
   * canvas-pane-click auto-collapse so AI Chat sessions stay open. The
   * pin button in the tab strip toggles this via ``onTogglePin``.
   */
  pinned?: boolean;
  onTogglePin?: () => void;
}

function PlaceholderTab() {
  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-stone-400">Coming in Phase 8.5</p>
    </div>
  );
}

export function BottomPanel({
  activeTab,
  selectedNode,
  selectedSchema,
  logEntries,
  onTabChange,
  onUpdateConfig,
  unreadLogsCount = 0,
  pinned = false,
  onTogglePin,
}: BottomPanelProps) {
  // ADR-039 §3.5 — MergeFlow modal is mounted at App.tsx level (NOT
  // here) so it survives BOTH bottom-tab switches AND project close
  // (Codex round-2 P1 on PR #974, follow-up issue #975). BottomPanel
  // itself unmounts when `currentProject` becomes null, which would
  // otherwise bypass MergeFlow's mid-conflict close-guard. See
  // App.tsx for the current mount.

  return (
    <section className="flex h-full flex-col overflow-hidden bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(238,231,219,0.98))]">
      <TabBar
        activeTab={activeTab}
        onTabChange={onTabChange}
        unreadLogsCount={unreadLogsCount}
        pinned={pinned}
        onTogglePin={onTogglePin}
      />

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2 scrollbar-thin">
        {/* TerminalTabs must stay MOUNTED across bottom-panel tab switches
            so PTY subprocesses survive (unmount fires the WS cleanup hook
            which kills the child process tree). Hide via CSS when another
            tab is active.

            AI Chat owns provider/AI-block chat tabs; Terminal owns
            user-terminal tabs. Each surface renders only its own tabs so a
            running PTY is mounted exactly once.

            Hotfix #977: the inner white-card frame was removed so the
            active-tab body fills the available space without a nested
            scroll context. The lineage tab (ADR-038 §3.8) and git tab
            (ADR-039 §3.5, #972) both render inside this flat container. */}
        <div className={`h-full ${activeTab === "ai" ? "" : "hidden"}`}>
          <TerminalTabs active={activeTab === "ai"} surface="chat" />
        </div>
        <div className={`h-full ${activeTab === "terminal" ? "" : "hidden"}`}>
          <TerminalTabs active={activeTab === "terminal"} surface="terminal" />
        </div>
        {activeTab === "config" ? (
          <ConfigPanel
            onUpdateConfig={onUpdateConfig}
            schema={selectedSchema}
            selectedNode={selectedNode}
          />
        ) : activeTab === "logs" ? (
          <LogViewer entries={logEntries} />
        ) : activeTab === "lineage" ? (
          // ADR-038 §3.8 — D38-2.4b skeleton mounts <LineageTab/>.
          // The root component renders a non-throwing placeholder until
          // D38-2.4c IMPL fills the two-pane runs-list + run-detail view.
          <LineageTab />
        ) : activeTab === "git" ? (
          // ADR-039 §3.5 (#972) — Git tab. GitTab owns its own modal
          // (CommitDialog) so it unmounts when the user switches away
          // from this tab. MergeFlow is mounted separately below (its
          // conflict-state close guard must survive bottom-tab
          // switches; Codex P1 on PR #974).
          <GitTab />
        ) : activeTab !== "ai" && activeTab !== "terminal" ? (
          <PlaceholderTab />
        ) : null}
      </div>
    </section>
  );
}
