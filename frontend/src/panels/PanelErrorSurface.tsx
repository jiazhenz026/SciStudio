/**
 * ADR-054 spec 1 — the host's own error surface and diagnostics banner.
 *
 * FR-035: these are *host chrome*, not panels. They must render when the frame
 * mechanism itself is unavailable, which is why they are ordinary React markup
 * with no frame, no message contract, and no dependency on anything in
 * `panelFrame.ts` beyond the shape of a failure. A panel that fails to load,
 * fails to validate, fails the version gate, or fails the handshake produces
 * exactly one behaviour: this surface, carrying a diagnostic that names the
 * panel and the failure (FR-014).
 *
 * Mounting the fallback panel the backend named is the *caller's* job, not
 * this component's and not `PanelHost`'s: the frontend carries no mapping from
 * a response's kind to a panel (FR-015, FR-036).
 */

import type { PanelFailure } from "./panelFrame";

/** A non-fatal report from the panel or from the host about the panel. */
export interface PanelDiagnostic {
  /** Unique within one mount; the host issues it. */
  readonly id: string;
  readonly panelId: string;
  readonly code: string;
  readonly message: string;
}

/**
 * FR-028 — the offer to revert an edited panel that will not load.
 *
 * FR-028 is a pair of obligations and the second one is why this type exists:
 * the host must report the failure explicitly **and offer to revert**, and it
 * must not quietly fall back to the panel the edit shadowed, "because a silent
 * fallback reads as an edit that was never saved". Reverting deletes the
 * shadowing copy (FR-029), restoring whatever was underneath it.
 *
 * Supplied by the caller rather than fetched here: nothing under
 * `frontend/src/panels/` reaches the store or the API client (see `index.ts`),
 * which is what lets the same host mount a panel over a preview session and
 * over a paused block. `store/usePanelRevert.ts` builds this object.
 *
 * `undefined` — not a disabled button — when the panel shadows nothing. There
 * is then no original behind it, and deleting the only copy of a panel is a
 * different request nobody made.
 */
export interface PanelRevertOffer {
  /** The tier the revert restores from: `core`, `package`, or `user`. */
  readonly restoresTier: string;
  readonly onRevert: () => void;
  /** True while the revert is in flight. */
  readonly pending?: boolean;
  /** A refusal from the revert route, shown beside the control. */
  readonly error?: string | null;
}

export interface PanelErrorSurfaceProps {
  readonly failure: PanelFailure;
  /** The panel's display name, when the descriptor carried one. */
  readonly panelName?: string;
  /** FR-028 — how to revert this panel's edit, when there is one to revert. */
  readonly revert?: PanelRevertOffer;
}

/** Human wording for each failure reason. The reason code is shown too. */
const REASON_HEADLINES: Record<string, string> = {
  invalid_descriptor: "This panel could not be validated",
  invalid_document_url: "This panel could not be validated",
  frame_unavailable: "This panel could not be framed",
  load_timeout: "This panel did not load",
  handshake_timeout: "This panel did not answer",
  version_mismatch: "This panel was built for a different host",
  panel_error: "This panel reported an error",
  torn_down: "This panel was closed while it was loading",
};

export function PanelErrorSurface({ failure, panelName, revert }: PanelErrorSurfaceProps) {
  const headline = REASON_HEADLINES[failure.reason] ?? "This panel failed";
  return (
    <div
      data-testid="panel-error-surface"
      data-panel-id={failure.panelId}
      data-panel-failure={failure.reason}
      className="space-y-1 rounded-[1rem] border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
      role="alert"
    >
      <p className="font-medium">{headline}</p>
      <p className="text-xs uppercase tracking-wider text-destructive/70">{failure.reason}</p>
      <p className="text-xs">{failure.message}</p>
      {panelName && panelName !== failure.panelId ? (
        <p className="text-xs text-destructive/70">{panelName}</p>
      ) : null}
      {revert ? (
        <div className="space-y-1 pt-2">
          <p className="text-xs">
            This panel is your edited copy. Reverting deletes it and restores the{" "}
            {revert.restoresTier} panel it replaced.
          </p>
          <button
            className="rounded-full border border-destructive/40 bg-white/70 px-3 py-1 text-xs font-medium text-destructive transition hover:bg-white disabled:opacity-50"
            data-testid="panel-error-revert"
            disabled={revert.pending}
            onClick={revert.onRevert}
            type="button"
          >
            {revert.pending ? "Reverting…" : `Revert to the ${revert.restoresTier} panel`}
          </button>
          {revert.error ? (
            <p className="text-xs text-destructive/80" data-testid="panel-error-revert-error">
              {revert.error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export interface PanelDiagnosticsBannerProps {
  readonly diagnostics: readonly PanelDiagnostic[];
}

/** Non-fatal reports, shown above a panel that is otherwise still running. */
export function PanelDiagnosticsBanner({ diagnostics }: PanelDiagnosticsBannerProps) {
  if (diagnostics.length === 0) return null;
  return (
    <div
      className="mb-2 rounded-[1rem] border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
      data-testid="panel-diagnostics"
      role="status"
    >
      {diagnostics.map((diagnostic) => (
        <p key={diagnostic.id}>
          <span className="font-medium">{diagnostic.code}</span> {diagnostic.message}
        </p>
      ))}
    </div>
  );
}
