import type { BlockSchemaResponse, LogEntry, WorkflowEdge, WorkflowNode } from "../types/api";
import type { BottomTab } from "../types/ui";

import { TerminalTabs } from "./AIChat/TerminalTabs";
import { GitTab } from "./Git/GitTab";
import { LineageTab } from "./Lineage/LineageTab";

import { ConfigPanel } from "./BottomPanel.parts/ConfigPanel";
import { LogViewer } from "./BottomPanel.parts/LogViewer";
import { PlotsTab } from "./BottomPanel.parts/PlotsTab";
import { TabBar } from "./BottomPanel.parts/TabBar";

interface BottomPanelProps {
  activeTab: BottomTab;
  selectedNode: WorkflowNode | null;
  selectedSchema?: BlockSchemaResponse;
  logEntries: LogEntry[];
  onTabChange: (tab: BottomTab) => void;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
  /**
   * ADR-050 FR-014 — ``blockId -> output payload`` map forwarded to the
   * Config tab so it can compute the upstream OME fields used by the
   * selected save node's lossy-save warning detail. OPTIONAL; FE-2's
   * App-level wiring supplies it. When absent the Config tab simply omits
   * the lossy detail (graceful degradation).
   */
  blockOutputs?: Record<string, Record<string, unknown>>;
  /**
   * ADR-050 FR-014 — workflow edges forwarded to the Config tab to resolve
   * which upstream blocks feed the selected node. OPTIONAL for the same
   * reason as ``blockOutputs``.
   */
  edges?: WorkflowEdge[];
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
  blockOutputs,
  edges,
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

      {/* ADR-034 FR-021g — this wrapper is a flex COLUMN, not a plain block.
          It still owns the scroll affordance (`overflow-y-auto`) that Config /
          Logs / Plots / Lineage / Git rely on; the only addition is
          `flex flex-col`, which lets its children size from flexbox instead of
          from a `height: 100%` percentage chain. See the surface wrappers
          below for why that matters. */}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 py-2 scrollbar-thin">
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
            (ADR-039 §3.5, #972) both render inside this flat container.

            ADR-034 FR-021g / spec §4.1 — these two wrappers were `h-full`
            blocks, and the spec expected a definite height to be lost in that
            percentage chain. Measured in Chromium while implementing T-011c,
            it is not: this conversion produces byte-identical geometry at
            every panel height. It is kept because it takes the height from
            flexbox rather than from percentage resolution, so the chain no
            longer depends on every ancestor keeping a resolvable height — but
            it is NOT what fixes FR-021g. The remaining defect is a crush below
            ~193px of panel height, diagnosed in
            `e2e/specs/adr034-setup-action-bar.spec.ts`.

            The mount structure and the `hidden` toggle are deliberately
            untouched: unmounting these wrappers fires the WS cleanup hook and
            kills the live agent subprocess (spec §4.5). Note that `hidden` and
            `flex` are both display utilities — `hidden` wins on Tailwind's
            emission order, and the e2e spec asserts the resolved value rather
            than trusting that. */}
        <div className={`flex min-h-0 flex-1 flex-col ${activeTab === "ai" ? "" : "hidden"}`}>
          <TerminalTabs active={activeTab === "ai"} surface="chat" />
        </div>
        <div className={`flex min-h-0 flex-1 flex-col ${activeTab === "terminal" ? "" : "hidden"}`}>
          <TerminalTabs active={activeTab === "terminal"} surface="terminal" />
        </div>
        {activeTab === "config" ? (
          <ConfigPanel
            onUpdateConfig={onUpdateConfig}
            schema={selectedSchema}
            selectedNode={selectedNode}
            blockOutputs={blockOutputs}
            edges={edges}
          />
        ) : activeTab === "logs" ? (
          <LogViewer entries={logEntries} />
        ) : activeTab === "plots" ? (
          // #1713 — dedicated Plots panel. Self-contained: reads workflowId /
          // selectedNodeId from the store and publishes Run results to
          // plotPreviewTarget for the Preview panel to render.
          <PlotsTab />
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
