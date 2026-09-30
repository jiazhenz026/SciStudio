/**
 * The failure view of a preview: an `error` envelope and host diagnostics.
 *
 * Every preview renders through a panel (ADR-054). An envelope without a
 * `.panel` is an `error` envelope — routing failed, or the session could not be
 * read — and this is what the host shows for it. The compiled per-kind viewers
 * that used to draw legacy previewer envelopes were removed with the legacy
 * previewer forms (ADR-054 §8, #2493).
 */

import type { PreviewEnvelope } from "../../types/api";

/** Non-fatal diagnostics emitted by the backend or the host. */
export function DiagnosticsBanner({ diagnostics }: { diagnostics: readonly string[] }) {
  if (!diagnostics || diagnostics.length === 0) return null;
  return (
    <div
      className="mb-2 rounded-[1rem] border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
      data-testid="preview-diagnostics"
      role="status"
    >
      {diagnostics.map((d, i) => (
        <p key={i}>{d}</p>
      ))}
    </div>
  );
}

/** Typed error display for an `error` envelope (FR-029). */
export function ErrorViewer({ envelope }: { envelope: PreviewEnvelope }) {
  const error = envelope.error;
  return (
    <div
      data-testid="core-error-viewer"
      className="space-y-1 rounded-[1rem] border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
      role="alert"
    >
      <p className="font-medium">Preview failed</p>
      {error ? (
        <>
          <p className="text-xs uppercase tracking-wider text-destructive/70">
            {String(error.code)}
          </p>
          <p className="text-xs">{error.message}</p>
        </>
      ) : (
        <p className="text-xs">An unknown preview error occurred.</p>
      )}
      <DiagnosticsBanner diagnostics={envelope.diagnostics} />
    </div>
  );
}
