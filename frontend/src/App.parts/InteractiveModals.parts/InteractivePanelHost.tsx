/**
 * ADR-054 spec 1, T-007 and D-018 — the window a paused interactive block puts
 * on screen, and the host chrome around it.
 *
 * This replaces `DynamicPanel.tsx`, which imported a package's ES module into
 * the application's own realm. A producing panel is a document in a sandboxed
 * frame now (FR-007), mounted by the same `mountPanelFrame` that mounts a
 * preview panel — there is one loader in the frontend, not two (SC-001).
 *
 * **Why Confirm and Cancel are drawn here and not in the panel** (D-018). A
 * producing panel's only outbound path is `emit` (FR-012), so it owns no
 * Confirm button: it has no way to say "and commit this". The host renders both
 * controls around the frame. Confirm commits the panel's most recent emission;
 * with no emission yet it is disabled, because there is nothing to commit. Each
 * built-in producing document re-emits its whole decision on every change and
 * says so in a header comment, which is the property that makes "most recent"
 * mean "current".
 *
 * **The title bar, the close control and ESC are kept deliberately.** They exist
 * because of a P1 (#2195): this overlay covers the toolbar's Stop control, so a
 * panel that wires no exit of its own would leave the whole application
 * unreachable. Every one of them drives the same run-scoped `onCancel` the old
 * host drove. A panel that handles ESC itself and stops propagation keeps
 * winning; one that does not gets the host's cancel.
 *
 * **When the backend named no panel.** The response is the error surface plus
 * Cancel — never a silent `null`. That is the same P1 again: a person must
 * never be left on a paused block with no window and no way out.
 */

import { X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { PanelDescriptor, PanelDiagnostic, PanelFailure } from "../../panels";
import { PanelDiagnosticsBanner, PanelErrorSurface, PanelHost } from "../../panels";
import type { PanelFrameFactory } from "../../panels";
import { Button } from "../../components/ui/button";
import { usePanelReloadToken } from "../../store/usePanelReload";
import type { PanelDescriptorResponse } from "../../types/api";

export interface InteractivePanelHostProps {
  /** The descriptor the backend resolved for this block's panel, or `null`. */
  descriptor: PanelDescriptorResponse | null;
  /** The paused block id the panel resolves. */
  blockId: string;
  /** The block-built, window-sized JSON view the panel renders from. */
  panelPayload: Record<string, unknown>;
  /** The panel id the block's manifest named, for the diagnostic when there is
   *  no descriptor to mount. */
  panelId?: string | null;
  /** Send the panel's JSON-safe decision back to the backend (run-scoped). */
  onConfirm: (responseData: Record<string, unknown>) => void;
  /** Cancel the interactive block (run-scoped). */
  onCancel: () => void;
  /** #2195 — what the host-drawn title bar calls this window. */
  blockName?: string;
  /** Test seam: the frame-creation seam `mountPanelFrame` builds through. */
  frameFactory?: PanelFrameFactory;
}

/**
 * What a producing panel emitted, and what the host does with it.
 *
 * FR-012 is explicit that the panel loading machinery MUST NOT interpret what a
 * panel emits, and ADR-054 §3.6 puts the statement whitelist where an emission
 * is *queued* — the explore session — rather than here. So the host holds the
 * emission verbatim and hands it back verbatim under the key the block reads.
 */
const EMITTED_CODE_KEY = "code";

export function InteractivePanelHost({
  descriptor,
  blockId,
  panelPayload,
  panelId,
  onConfirm,
  onCancel,
  blockName,
  frameFactory,
}: InteractivePanelHostProps) {
  const [failure, setFailure] = useState<PanelFailure | null>(null);
  const [diagnostics, setDiagnostics] = useState<PanelDiagnostic[]>([]);
  // D-018: the panel's most recent emission. `null` until it emits once, which
  // is exactly when Confirm has nothing to commit.
  const [emitted, setEmitted] = useState<string | null>(null);

  // Keep the latest confirm/cancel without re-rendering the frame: the parent
  // re-creates these each render and the frame must not remount for that.
  const onConfirmRef = useRef(onConfirm);
  const onCancelRef = useRef(onCancel);
  onConfirmRef.current = onConfirm;
  onCancelRef.current = onCancel;

  const reloadToken = usePanelReloadToken(descriptor?.panel_id ?? null);

  /*
   * FR-013 — the panel is *bound* to what the block is asking about, rather
   * than shown a snapshot of it. A producing panel may be bound to more than
   * one variable; a block prompt binds exactly one, its own window-sized view,
   * and names it after the block so a document that inspects its bindings sees
   * something meaningful rather than a positional slot.
   */
  const bindings = useMemo(
    () => ({ prompt: { type: "interactive_prompt", snapshot: panelPayload } }),
    [panelPayload],
  );

  const handleClose = useCallback(() => onCancelRef.current(), []);

  // #2195 — ESC is the host's second escape hatch, bound while ANY interactive
  // panel is open, whether the frame mounted or the error surface is showing.
  // Bubble phase on `window`, deliberately: a capture listener would swallow
  // ESC before the panel document ever saw it.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      onCancelRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const onEmit = useCallback((code: string) => setEmitted(code), []);
  const onDiagnostic = useCallback(
    (diagnostic: PanelDiagnostic) => setDiagnostics((current) => [...current, diagnostic]),
    [],
  );

  const confirm = useCallback(() => {
    if (emitted === null) return;
    onConfirmRef.current({ [EMITTED_CODE_KEY]: emitted });
  }, [emitted]);

  // The block's own name when the prompt carried one, else its id — the title
  // bar always names the node the reader is being asked about.
  const title = blockName?.trim() ? blockName.trim() : blockId;

  const missing: PanelFailure = {
    panelId: panelId ?? blockId,
    reason: "invalid_descriptor",
    message: panelId
      ? `this block asked for panel "${panelId}" but the prompt carried no descriptor for it, ` +
        "so there is no document to mount"
      : "this block's prompt named no panel to mount",
  };

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
      data-testid="interactive-panel"
      data-block-id={blockId}
      role="dialog"
      aria-modal="true"
      aria-label={`${title} — interactive block`}
    >
      <div className="flex max-h-[85vh] w-[900px] flex-col overflow-hidden rounded-xl border border-ink/10 bg-white shadow-panel">
        {/* #2195 — host-drawn title bar. Chrome the host owns, never the panel
            document's DOM, so the exit exists no matter what the panel draws. */}
        <div
          className="flex shrink-0 items-center justify-between gap-3 border-b border-ink/10 bg-ink/[0.03] px-4 py-2"
          data-testid="interactive-panel-titlebar"
        >
          <div className="truncate text-sm font-medium text-ink/80" title={title}>
            {title}
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="-mr-1 rounded p-1 text-ink/50 transition-colors hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/30"
            aria-label="Close panel and cancel this block"
            title="Close and cancel (Esc)"
            data-testid="interactive-panel-close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto" data-testid="interactive-panel-mount">
          <PanelDiagnosticsBanner diagnostics={diagnostics} />
          {descriptor ? (
            <PanelHost
              className="h-[60vh]"
              descriptor={descriptor as PanelDescriptor}
              bindings={bindings}
              target={panelPayload}
              remountToken={reloadToken}
              onEmit={onEmit}
              onFailure={setFailure}
              onDiagnostic={onDiagnostic}
              frameFactory={frameFactory}
            />
          ) : (
            <div className="p-5">
              <PanelErrorSurface failure={missing} />
            </div>
          )}
        </div>

        {/* D-018 — Confirm and Cancel are host chrome. The panel emits; the host
            commits. Confirm stays disabled until the panel has emitted at least
            once, because until then there is no decision to send. */}
        <div
          className="flex shrink-0 items-center justify-end gap-2 border-t border-ink/10 bg-ink/[0.02] px-4 py-3"
          data-testid="interactive-panel-actions"
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleClose}
            data-testid="interactive-panel-cancel"
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={confirm}
            disabled={emitted === null || failure !== null}
            title={
              emitted === null
                ? "This panel has not made a decision yet"
                : "Send this decision back to the block"
            }
            data-testid="interactive-panel-confirm"
          >
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}
