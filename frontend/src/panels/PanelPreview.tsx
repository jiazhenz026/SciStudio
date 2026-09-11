import { useRef, useState } from "react";
import { panelsApi } from "../lib/api/panels";
import type { PreviewTarget } from "../types/api";
import { PanelFrame } from "./PanelFrame";
import type { PanelContext, PanelCreateRequest, PanelSnapshot } from "./types";

export interface PanelPreviewProps {
  target: PreviewTarget;
  panelId: string;
  previewSessionId?: string | null;
  initialViewState?: unknown;
  onSnapshot?: (snapshot: PanelSnapshot) => void;
  onFallback: () => void;
}
export function PanelPreview({ target, panelId, previewSessionId, initialViewState, onSnapshot, onFallback }: PanelPreviewProps) {
  const [stack, setStack] = useState<PanelCreateRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const root: PanelCreateRequest = { kind: "preview", target, panel_id: panelId, view_state: initialViewState,
    ...(previewSessionId ? { preview_session_id: previewSessionId } : {}) };
  const snapshots = useRef(new Map<number, PanelSnapshot>());
  const requests = [root, ...stack];
  const active = requests.length - 1;
  const remember = (index: number, request: PanelCreateRequest, context: PanelContext, viewState?: unknown) => {
    const snapshot = { target: request.target!, panelId: context.panel.id, viewState };
    snapshots.current.set(index, snapshot);
    if (index === active) onSnapshot?.(snapshot);
  };
  return <div data-testid="panel-preview">
    {stack.length ? <button type="button" onClick={() => {
      setStack((value) => value.slice(0, -1));
      const snapshot = snapshots.current.get(active - 1);
      if (snapshot) onSnapshot?.(snapshot);
    }}>← Back</button> : null}
    {requests.map((request, index) => <div key={index} hidden={index !== active}>
      <PanelFrame request={request} onFallback={onFallback}
        onContext={(context) => remember(index, request, context, request.view_state)}
        onViewState={(state, context) => remember(index, request, context, state)}
        onOpen={async (ref, contextId) => {
          if (busy || index !== active) throw new Error("Preview navigation already in progress");
          setBusy(true);
          try {
            const childRequest: PanelCreateRequest = { kind: "preview", target: { kind: "data_ref", ref }, parent_context_id: contextId };
            // Validate before changing the stack. The live child mount creates its
            // own context; this short validation context is immediately revoked.
            const child = await panelsApi.create(childRequest);
            await panelsApi.close(child.context_id);
            setStack((value) => [...value, childRequest]);
            return null;
          } finally { setBusy(false); }
        }} />
    </div>)}
  </div>;
}
