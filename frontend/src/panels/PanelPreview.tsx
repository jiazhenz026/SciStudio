import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { panelsApi } from "../lib/api/panels";
import type { PreviewEnvelope, PreviewTarget } from "../types/api";
import { PanelFrame } from "./PanelFrame";
import type { PanelContext, PanelCreateRequest, PanelSnapshot } from "./types";

export interface PanelPreviewProps {
  target: PreviewTarget;
  panelId: string;
  previewSessionId?: string | null;
  initialViewState?: unknown;
  onSnapshot?: (snapshot: PanelSnapshot) => void;
  onFallback: () => void;
  renderChild: (
    envelope: PreviewEnvelope,
    onSnapshot?: (snapshot: PanelSnapshot | null) => void,
  ) => ReactNode;
}
export function PanelPreview({
  target,
  panelId,
  previewSessionId,
  initialViewState,
  onSnapshot,
  onFallback,
  renderChild,
}: PanelPreviewProps) {
  const [child, setChild] = useState<PreviewEnvelope | null>(null);
  const busy = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const rootSnapshot = useRef<PanelSnapshot>();
  const root: PanelCreateRequest = {
    kind: "preview",
    target,
    panel_id: panelId,
    view_state: initialViewState,
    ...(previewSessionId ? { preview_session_id: previewSessionId } : {}),
  };
  const remember = (context: PanelContext, viewState?: unknown) => {
    const kind = context.input.kind;
    const snapshot: PanelSnapshot = {
      target: {
        ...target,
        ...(kind === "data_ref" || kind === "collection_ref" || kind === "plot_artifact"
          ? { kind }
          : {}),
      },
      panelId: context.panel.id,
      ...(previewSessionId ? { previewSessionId } : {}),
      viewState,
    };
    rootSnapshot.current = snapshot;
    if (!child) onSnapshot?.(snapshot);
  };
  return (
    <div data-testid="panel-preview">
      {child ? (
        <button
          type="button"
          onClick={() => {
            setChild(null);
            if (rootSnapshot.current) onSnapshot?.(rootSnapshot.current);
          }}
        >
          ← Back
        </button>
      ) : null}
      <div hidden={child !== null}>
        <PanelFrame
          request={root}
          onFallback={onFallback}
          onContext={(context) => remember(context, initialViewState)}
          onViewState={(state, context) => remember(context, state)}
          onOpen={async (ref, contextId) => {
            if (busy.current || child) throw new Error("Preview navigation already in progress");
            busy.current = true;
            try {
              // The backend authorizes the child through the parent and freezes an
              // independent preview session, including composite-local slot refs.
              const envelope = await panelsApi.open(contextId, ref);
              if (mounted.current) setChild(envelope);
              /*
               * ADR-053 FR-052 — `preview_item_opened`, in the closed
               * `UI_EVENT_NAMES` set. The compiled collection/composite viewers
               * reported this when the reader opened one child; a panel cannot
               * reach the store from its frame, so the host reports it here for
               * every panel. Without it a tutorial step that asks the reader to
               * open an item can never finish. Imported lazily: the store pulls
               * in every slice, and this module is rendered by tests that mock a
               * narrow API surface.
               */
              void import("../store").then(({ useAppStore }) =>
                useAppStore.getState().reportTutorialUiEvent("preview_item_opened"),
              );
              return null;
            } finally {
              busy.current = false;
            }
          }}
        />
      </div>
      {child
        ? renderChild(child, (snapshot) => {
            if (snapshot) onSnapshot?.(snapshot);
          })
        : null}
    </div>
  );
}
