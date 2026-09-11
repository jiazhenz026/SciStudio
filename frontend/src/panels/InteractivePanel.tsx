import { useEffect } from "react";
import { PanelFrame } from "./PanelFrame";

export interface InteractivePanelProps {
  panelId: string;
  workflowId: string;
  blockId: string;
  blockName?: string;
  onConfirm: (data: Record<string, unknown>, contextId: string) => void;
  onCancel: () => void;
}
export function InteractivePanel({ panelId, workflowId, blockId, blockName, onConfirm, onCancel }: InteractivePanelProps) {
  useEffect(() => {
    const cancel = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel(); };
    window.addEventListener("keydown", cancel);
    return () => window.removeEventListener("keydown", cancel);
  }, [onCancel]);
  return <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40" role="dialog" aria-modal="true" aria-label={`${blockName ?? blockId} — interactive block`}>
    <div className="flex max-h-[85vh] w-[900px] flex-col overflow-auto rounded-xl bg-white p-4">
      <div className="mb-2 flex justify-between"><h2>{blockName ?? blockId}</h2><button type="button" onClick={onCancel}>Cancel</button></div>
      <PanelFrame request={{ kind: "interactive", workflow_id: workflowId, block_id: blockId, panel_id: panelId }}
        onWriteBack={onConfirm} onCancel={onCancel} />
    </div>
  </div>;
}
