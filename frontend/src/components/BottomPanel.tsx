import { useLayoutEffect, useMemo, useRef, useState } from "react";

import { useAppStore } from "../store";
import type { BlockSchemaResponse, LogEntry, WorkflowNode } from "../types/api";
import type { BottomTab } from "../types/ui";
import { TerminalTabs } from "./AIChat/TerminalTabs";
import { GitTab } from "./Git/GitTab";
import { MergeFlow } from "./Git/MergeFlow";
import { type PortRow, PortEditorTable } from "./PortEditorTable";

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
}

const TAB_LABELS: Record<BottomTab, string> = {
  ai: "\u{1F4AC} AI Chat",
  config: "\u{1F4CB} Config",
  logs: "\u{1F4DC} Logs",
  lineage: "\u{1F517} Lineage",
  jobs: "\u{1F4CA} Jobs",
  // ADR-039 §3.5 (#972) — Git versioning surface moved out of the top
  // Toolbar into a dedicated bottom-panel tab so the commit history /
  // branch graph / merge flows are reachable without overflowing the
  // toolbar on narrow viewports.
  git: "\u{1F500} Git",
};

// Problems was removed: it duplicated the block_error rows already in Logs
// (filterable via LogViewer's level selector) plus the inline error badge
// rendered on the BlockNode itself by WorkflowCanvas.
const ALL_TABS: BottomTab[] = ["ai", "config", "logs", "lineage", "jobs", "git"];

// Controlled text input that preserves caret position across re-renders (#710).
//
// The standard React controlled-input pattern resets the browser caret to
// the end of the value whenever the `value` prop is replaced by a non-
// synchronous round-trip (e.g. onChange -> Zustand -> next render). This
// component captures selectionStart/selectionEnd on each change and restores
// them in a layout effect after the value prop has been applied.
//
// Audit follow-up (#710): only restore when the re-render originated from
// this input's own onChange. Previously selectionRef stayed live across
// renders, which meant any unrelated re-render while the field stayed
// focused (e.g. user moves the caret with mouse/arrow keys, then a sibling
// state update fires) would force the caret back to the stale post-edit
// position. We now store the pending selection only between onChange and
// the next layout effect, then null it out so subsequent renders are
// no-ops unless another onChange refills the ref. The activeElement guard
// still ensures we never steal selection from another input (the canvas
// BlockNode renders the same field, bound to the same store).
function CaretPreservingTextInput({
  value,
  onChange,
  type,
  className,
  placeholder,
}: {
  value: string;
  onChange: (next: string) => void;
  type: "text" | "number";
  className?: string;
  placeholder?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingSelectionRef = useRef<{ start: number; end: number } | null>(
    null,
  );
  useLayoutEffect(() => {
    const pending = pendingSelectionRef.current;
    const el = inputRef.current;
    if (pending && el && document.activeElement === el) {
      try {
        el.setSelectionRange(pending.start, pending.end);
      } catch {
        // setSelectionRange is not supported on type=number; ignore.
      }
    }
    // Always clear after attempting restore so the next render does
    // nothing unless another onChange refills the ref.
    pendingSelectionRef.current = null;
  });
  return (
    <input
      ref={inputRef}
      className={className}
      onChange={(event) => {
        // type=number does not expose selectionStart/selectionEnd in most
        // browsers; values come back as null which we coalesce to 0. The
        // activeElement guard above still gates the restore, so unfocused
        // mirrors do not steal selection.
        pendingSelectionRef.current = {
          start: event.target.selectionStart ?? 0,
          end: event.target.selectionEnd ?? 0,
        };
        onChange(event.target.value);
      }}
      placeholder={placeholder}
      type={type}
      value={value}
    />
  );
}

function ConfigPanel({
  selectedNode,
  schema,
  onUpdateConfig,
}: {
  selectedNode: WorkflowNode | null;
  schema?: BlockSchemaResponse;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
}) {
  const params = ((selectedNode?.config.params as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
  const properties = schema?.config_schema.properties ?? {};
  const ordered = Object.entries(properties)
    .filter(([key, value]) => {
      // For io_block, hide "direction" — it is already determined by whether
      // the user dragged a Load Block or Save Block from the palette.
      if ((schema?.direction || selectedNode?.block_type === "io_block") && key === "direction") return false;
      // Skip port_editor fields — rendered separately as PortEditorTable below.
      if ((value as Record<string, unknown>).ui_widget === "port_editor") return false;
      return true;
    })
    .sort(([, left], [, right]) => {
      return Number(left.ui_priority ?? 99) - Number(right.ui_priority ?? 99);
    });

  const isVariadicInputs = schema?.variadic_inputs === true;
  const isVariadicOutputs = schema?.variadic_outputs === true;
  const inputPorts = Array.isArray(params["input_ports"]) ? (params["input_ports"] as PortRow[]) : [];
  const outputPorts = Array.isArray(params["output_ports"]) ? (params["output_ports"] as PortRow[]) : [];
  const typeHierarchy = schema?.type_hierarchy ?? [];
  const allowedInputTypes = schema?.allowed_input_types ?? [];
  const allowedOutputTypes = schema?.allowed_output_types ?? [];

  if (!selectedNode || !schema) {
    return <div className="text-sm text-stone-500">Select a node to edit its JSON-schema-driven configuration.</div>;
  }

  return (
    <div>
      {isVariadicInputs && (
        <PortEditorTable
          allowedTypes={allowedInputTypes}
          direction="input"
          maxPorts={schema.max_input_ports}
          minPorts={schema.min_input_ports}
          onChange={(ports) => onUpdateConfig({ input_ports: ports })}
          ports={inputPorts}
          typeHierarchy={typeHierarchy}
        />
      )}
      {isVariadicOutputs && (
        <PortEditorTable
          allowedTypes={allowedOutputTypes}
          direction="output"
          maxPorts={schema.max_output_ports}
          minPorts={schema.min_output_ports}
          onChange={(ports) => onUpdateConfig({ output_ports: ports })}
          ports={outputPorts}
          typeHierarchy={typeHierarchy}
        />
      )}
      <div className="grid gap-4 md:grid-cols-2">
      {ordered.map(([key, value]) => {
        const currentValue = params[key] ?? value.default ?? "";
        if (Array.isArray(value.enum)) {
          return (
            <label className="grid gap-2 text-sm" key={key}>
              <span className="font-medium text-ink">{String(value.title ?? key)}</span>
              <select
                className="rounded-2xl border border-stone-300 bg-white px-4 py-3"
                onChange={(event) => onUpdateConfig({ [key]: event.target.value })}
                value={String(currentValue)}
              >
                {value.enum.map((option) => (
                  <option key={String(option)} value={String(option)}>
                    {String(option)}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        return (
          <label className="grid gap-2 text-sm" key={key}>
            <span className="font-medium text-ink">{String(value.title ?? key)}</span>
            <CaretPreservingTextInput
              className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3"
              onChange={(next) =>
                onUpdateConfig({
                  [key]: value.type === "number" ? Number(next) : next,
                })
              }
              placeholder={key === "path" ? "Type or paste file/directory path" : undefined}
              type={value.type === "number" ? "number" : "text"}
              value={String(currentValue)}
            />
          </label>
        );
      })}
      </div>
    </div>
  );
}

function LogViewer({ entries }: { entries: LogEntry[] }) {
  const [level, setLevel] = useState("all");
  const filtered = useMemo(() => {
    return entries.filter((entry) => level === "all" || entry.level === level);
  }, [entries, level]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center gap-3">
        <select className="rounded-full border border-stone-300 bg-white px-3 py-2 text-sm" onChange={(event) => setLevel(event.target.value)} value={level}>
          <option value="all">All levels</option>
          <option value="info">Info</option>
          <option value="error">Error</option>
        </select>
      </div>
      <div className="flex-1 overflow-auto rounded-[1.4rem] border border-stone-200 bg-stone-950 p-4">
        {filtered.length ? (
          filtered.map((entry, index) => (
            <div className="border-b border-stone-800 py-2 text-sm text-stone-100" key={`${entry.timestamp}-${index}`}>
              <p className="text-[11px] uppercase tracking-[0.3em] text-stone-500">
                {entry.level} · {entry.workflow_id ?? "workflow"} · {entry.block_id ?? "system"}
              </p>
              <p className="mt-1">{entry.message}</p>
            </div>
          ))
        ) : (
          <p className="text-sm text-stone-500">No logs yet.</p>
        )}
      </div>
    </div>
  );
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
}: BottomPanelProps) {
  const badgeFor = (tab: BottomTab): number => {
    if (tab === activeTab) return 0;
    if (tab === "logs") return unreadLogsCount;
    return 0;
  };
  const formatBadge = (n: number): string => (n > 99 ? "99+" : String(n));

  // ADR-039 §3.5 (#972 — Codex P1 on PR #974) — MergeFlow is mounted
  // here (NOT inside GitTab) so a bottom-tab switch during a conflict
  // resolution does not unmount the modal and bypass its close guard.
  // Driven by `gitSlice.mergeFlowSource`: BranchPicker sets the source
  // and the merge-flow setter clears it on success/abort/close.
  const mergeFlowSource = useAppStore((s) => s.mergeFlowSource);
  const setMergeFlowSource = useAppStore((s) => s.setMergeFlowSource);
  const openFileTab = useAppStore((s) => s.openFileTab);

  return (
    <section className="flex h-full flex-col overflow-hidden bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(238,231,219,0.98))]">
      <div className="flex items-center gap-3 border-b border-stone-200 px-4 py-3">
        <div className="flex gap-2">
          {ALL_TABS.map((tab) => {
            const badge = badgeFor(tab);
            return (
              <button
                className={`rounded-full px-4 py-2 text-sm font-medium ${activeTab === tab ? "bg-ink text-white" : "bg-white text-stone-600"}`}
                key={tab}
                onClick={() => onTabChange(tab)}
                type="button"
              >
                {TAB_LABELS[tab]}
                {badge > 0 ? (
                  <span
                    className="ml-2 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-rose-500 px-1.5 text-xs font-semibold text-white"
                    data-testid={`unread-badge-${tab}`}
                  >
                    {formatBadge(badge)}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 scrollbar-thin">
        <div className="h-full rounded-[1.8rem] border border-stone-200 bg-white/80 p-4">
          {/* TerminalTabs must stay MOUNTED across bottom-panel tab switches
              so the PTY subprocess survives (unmount fires the WS cleanup
              hook which kills the child process tree). Hide via CSS when
              another tab is active. */}
          <div className={`h-full ${activeTab === "ai" ? "" : "hidden"}`}>
            <TerminalTabs />
          </div>
          {activeTab === "config" ? (
            <ConfigPanel onUpdateConfig={onUpdateConfig} schema={selectedSchema} selectedNode={selectedNode} />
          ) : activeTab === "logs" ? (
            <LogViewer entries={logEntries} />
          ) : activeTab === "git" ? (
            // ADR-039 §3.5 (#972) — Git tab. GitTab owns its own modals
            // (CommitDialog / StashListPanel / MergeFlow) so they unmount
            // when the user switches away from this tab.
            <GitTab />
          ) : activeTab !== "ai" ? (
            <PlaceholderTab />
          ) : null}
        </div>
      </div>

      {/* ADR-039 §3.5 (#972) — MergeFlow is rendered here so it survives
          bottom-tab switches; its conflict-state close guard would
          otherwise be bypassed if the Git tab unmounted mid-resolution
          (Codex P1 on PR #974). */}
      <MergeFlow
        sourceBranch={mergeFlowSource ?? ""}
        isOpen={mergeFlowSource !== null}
        onClose={() => setMergeFlowSource(null)}
        onOpenFile={(path) => {
          openFileTab(path);
        }}
      />
    </section>
  );
}
