// ADR-044 FR-011 (US5) — Config-tab editor for a SubWorkflowBlock node.
//
// The SubWorkflowBlock `config_schema` declares a NESTED `ref.path`
// (ui_widget `subworkflow_picker`). `ConfigPanel` only renders TOP-LEVEL schema
// fields, so the generic renderer would show a broken `ref` object field. This
// editor mirrors the CodeBlock special-case (`isCodeBlockConfigTarget` →
// `CodeBlockConfigEditor`): it shows the current `config.ref.path` and a
// "Choose subworkflow file…" button that runs the SAME shared import flow the
// canvas node affordance uses (`chooseSubworkflowFile`), repointing
// `config.ref.path` and refreshing the node's resolved-port handles in place.

import { useState } from "react";

import { chooseSubworkflowFile } from "../../lib/chooseSubworkflowFile";
import { useAppStore } from "../../store";
import { subworkflowRefPath } from "./subworkflowConfig";
import type { WorkflowNode } from "../../types/api";

export function SubworkflowConfigEditor({ selectedNode }: { selectedNode: WorkflowNode }) {
  const setNodeRef = useAppStore((state) => state.setNodeRef);
  const setNodeResolvedPorts = useAppStore((state) => state.setNodeResolvedPorts);
  const setLastError = useAppStore((state) => state.setLastError);
  const [busy, setBusy] = useState(false);

  const refPath = subworkflowRefPath(selectedNode);

  const handleChoose = async () => {
    setBusy(true);
    try {
      await chooseSubworkflowFile(selectedNode.id, {
        setNodeRef,
        setNodeResolvedPorts,
        setLastError,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid max-w-2xl gap-4" data-testid="subworkflow-config-editor">
      <div className="grid gap-2 text-sm">
        <span className="font-medium text-ink">Subworkflow file</span>
        <p className="text-xs text-stone-500">
          References an external workflow file (project-relative). Choosing a file imports a copy
          into <code>subworkflows/</code> and exposes its <code>exposed_ports</code> as the handles
          on this node.
        </p>
        <div className="flex w-full min-w-0 items-stretch gap-2">
          <input
            className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3"
            data-testid="subworkflow-config-ref-path"
            readOnly
            value={refPath ?? ""}
            placeholder="No subworkflow file chosen"
          />
          <button
            type="button"
            data-testid="subworkflow-config-choose"
            disabled={busy}
            className="shrink-0 rounded-2xl border border-stone-300 bg-white px-4 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void handleChoose()}
          >
            Choose subworkflow file…
          </button>
        </div>
      </div>
    </div>
  );
}
