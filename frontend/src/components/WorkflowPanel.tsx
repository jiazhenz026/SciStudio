// The Workflows left-panel section (#2090): every workflow in the current
// project with the `description` from its YAML, single-click to open it on
// the canvas.
//
// Data comes from the existing endpoints — `GET /api/workflows/list` for the
// ids, then one `GET /api/workflows/{id}` per workflow for the description —
// so the panel needed no backend change. Layout and the Refresh affordance
// mirror `ProjectTree` so the left panel reads as one surface.

import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import { cn } from "@/lib/utils";

interface WorkflowListItem {
  id: string;
  description: string;
}

export interface WorkflowPanelProps {
  /** Refetch trigger: the list belongs to the open project. */
  projectId: string;
  /** The workflow currently on the canvas, highlighted in the list. */
  activeWorkflowId: string | null;
  onOpenWorkflow: (workflowId: string, displayName: string) => void;
}

export function WorkflowPanel({ projectId, activeWorkflowId, onOpenWorkflow }: WorkflowPanelProps) {
  const [items, setItems] = useState<WorkflowListItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const ids = await api.listWorkflows();
      const summaries = await Promise.all(
        ids.map(async (id): Promise<WorkflowListItem> => {
          try {
            const workflow = await api.getWorkflow(id);
            return { id, description: workflow.description ?? "" };
          } catch {
            // A workflow that fails to load (e.g. a mid-write YAML) still
            // belongs in the list — just without a description.
            return { id, description: "" };
          }
        }),
      );
      setItems(summaries);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setItems([]);
    void refresh();
  }, [projectId, refresh]);

  return (
    <aside
      className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-4"
      data-testid="workflow-panel"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-xl text-ink">Workflows</p>
        <button
          className="toolbar-button"
          disabled={loading}
          onClick={() => void refresh()}
          type="button"
        >
          {loading ? "..." : "Refresh"}
        </button>
      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pb-6 scrollbar-thin">
        {!loading && items.length === 0 ? (
          <p className="text-xs text-stone-400">No workflows found</p>
        ) : null}
        <div className="flex flex-col gap-1">
          {items.map((item) => (
            <button
              aria-current={item.id === activeWorkflowId}
              className={cn(
                "flex w-full flex-col gap-0.5 rounded px-2 py-1.5 text-left transition",
                item.id === activeWorkflowId ? "bg-white shadow-sm" : "hover:bg-stone-100",
              )}
              key={item.id}
              onClick={() => onOpenWorkflow(item.id, item.id)}
              type="button"
            >
              <span className="truncate text-sm font-medium text-stone-700">{item.id}</span>
              {item.description ? (
                <span className="line-clamp-2 text-xs text-stone-400">{item.description}</span>
              ) : null}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
