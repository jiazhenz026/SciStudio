/*
 * frontend/src/components/Lineage/MethodsExportDialog.tsx — ADR-038 §3.8
 * ======================================================================
 *
 * SKELETON ONLY. Function body throws `new Error("TODO: D38-2.4c — ...")`.
 *
 * Purpose
 * -------
 * Modal dialog for the "Export methods" affordance. Fetches the rendered
 * markdown via api.lineage.getRunMethods(runId) (server-side renderer lives
 * in `src/scistudio/core/lineage/methods_export.py` per ADR-038 §5.1, owned
 * by the sibling D38-2.4a agent). Displays the markdown read-only inside
 * a scrollable region; offers Copy and Download .md actions.
 *
 * Props
 * -----
 *
 *   interface MethodsExportDialogProps {
 *     runId:   string;     // the run whose methods to render
 *     onClose: () => void; // bound to closeMethodsDialog by parent
 *   }
 *
 * State (local to component)
 * --------------------------
 *
 *   const [markdown, setMarkdown] = useState<string | null>(null);
 *   const [loading, setLoading]   = useState(true);
 *   const [error,   setError]     = useState<string | null>(null);
 *   const [copyOk,  setCopyOk]    = useState(false); // 2s flash after copy
 *
 * Fetch policy
 * ------------
 *   useEffect(() => {
 *     let cancelled = false;
 *     setLoading(true); setError(null);
 *     api.lineage.getRunMethods(runId).then((res) => {
 *       if (cancelled) return;
 *       setMarkdown(res.markdown);
 *       setLoading(false);
 *     }).catch((err) => {
 *       if (cancelled) return;
 *       setError(err.message ?? "Failed to render methods");
 *       setLoading(false);
 *     });
 *     return () => { cancelled = true; };
 *   }, [runId]);
 *
 * Layout markup pseudocode (vitest selectors)
 * -------------------------------------------
 *
 *   <DialogOverlay onClose={onClose}>
 *     <div
 *       role="dialog"
 *       aria-modal="true"
 *       aria-labelledby="methods-export-title"
 *       data-testid="methods-export-dialog"
 *       className="w-[800px] max-w-[90vw] rounded-3xl bg-white p-6 shadow-xl"
 *     >
 *       <header className="flex items-center gap-3">
 *         <h2 id="methods-export-title" className="text-lg font-semibold text-ink">
 *           Methods · Run {runId.slice(0, 8)}
 *         </h2>
 *         <button
 *           type="button"
 *           className="ml-auto rounded-full p-2 hover:bg-stone-100"
 *           aria-label="Close"
 *           onClick={onClose}
 *         >
 *           ×
 *         </button>
 *       </header>
 *
 *       <div className="mt-3 max-h-[60vh] overflow-y-auto rounded-2xl border border-stone-200 bg-stone-50 p-4"
 *            data-testid="methods-export-body">
 *         {loading && <p>Generating methods…</p>}
 *         {error && <p className="text-rose-700">{error}</p>}
 *         {markdown !== null && (
 *           <pre className="whitespace-pre-wrap font-mono text-xs text-ink">
 *             {markdown}
 *           </pre>
 *         )}
 *       </div>
 *
 *       <footer className="mt-4 flex items-center gap-2">
 *         <button
 *           type="button"
 *           className="rounded-full bg-ink px-4 py-2 text-sm text-white"
 *           disabled={markdown === null}
 *           data-testid="methods-export-copy"
 *           onClick={handleCopy}
 *         >
 *           {copyOk ? "Copied ✓" : "Copy"}
 *         </button>
 *         <button
 *           type="button"
 *           className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink"
 *           disabled={markdown === null}
 *           data-testid="methods-export-download"
 *           onClick={handleDownload}
 *         >
 *           Download .md
 *         </button>
 *         <button
 *           type="button"
 *           className="ml-auto rounded-full px-4 py-2 text-sm text-stone-700"
 *           onClick={onClose}
 *         >
 *           Close
 *         </button>
 *       </footer>
 *     </div>
 *   </DialogOverlay>
 *
 * Note: there is no shared DialogOverlay component as of 2026-05-15. The
 * IMPL agent should either (a) reuse one if it appears upstream of D38-2.4c,
 * or (b) implement an inline overlay div with a fixed-position backdrop
 * (matches the in-tree pattern in ProjectDialog / TabBar). Choose (b) for
 * v1 unless an overlay component exists.
 *
 * Action semantics
 * ----------------
 *
 *   handleCopy:
 *     - if markdown === null: noop
 *     - navigator.clipboard.writeText(markdown).then(() => {
 *         setCopyOk(true);
 *         setTimeout(() => setCopyOk(false), 2000);
 *       })
 *     - on clipboard rejection: setError("Could not copy. Try Download.")
 *
 *   handleDownload:
 *     - filename: `methods-${runId.slice(0,8)}.md`
 *     - blob: new Blob([markdown], { type: "text/markdown" })
 *     - trigger a synthetic <a download> click; revoke object URL after
 *
 * Copy strings (English, freeze)
 * ------------------------------
 *   Header:           "Methods · Run {short_id}"
 *   Loading:          "Generating methods…"
 *   Error fallback:   "Failed to render methods"
 *   Clipboard fail:   "Could not copy. Try Download."
 *   Copy button:      "Copy" → "Copied ✓"
 *   Download button:  "Download .md"
 *   Close label:      "Close" (button) and aria-label "Close" (× button)
 *
 * Keyboard
 * --------
 *   - Esc closes dialog (handled by an effect on this component; this lets
 *     the LineageTab top-level handler stay out of the dialog's way)
 *   - Tab is trapped inside the dialog (focus moves between buttons only).
 *     Implementation: a `useFocusTrap` hook OR a manual ref-based trap.
 *     v1: simplest approach — focus the Copy button on open; trapping not
 *     required for v1 (document trap as a polish issue if user complains).
 *
 * Accessibility
 * -------------
 *   - role="dialog" + aria-modal="true" + aria-labelledby
 *   - Close × button has aria-label="Close" (no visible text)
 *   - Focus moves to first actionable button on open (Copy)
 *   - On close, focus returns to the trigger element (RunDetail's Export
 *     methods button) — manage via a ref-saved activeElement at open time
 *
 * Edge cases
 * ----------
 *   1. markdown === "": render empty pre block; Copy/Download buttons
 *      remain disabled (markdown === null check) — but if server actually
 *      returns "" string, switch to checking markdown.length === 0.
 *      Update IMPL contract: disable buttons when !markdown (covers both).
 *   2. runId no longer exists: server returns 404; error path renders.
 *   3. Clipboard API unavailable (older browsers / non-secure context):
 *      fall back to setError suggesting Download.
 *   4. Large markdown (>1MB): scroll region keeps layout bounded. No
 *      virtualization needed; <pre> handles it natively.
 *
 * Test plan (no dedicated test file)
 * ----------------------------------
 * Covered via integration in RunDetail.test.tsx (which can trigger the
 * dialog by clicking the Export methods button and asserting that the
 * dialog appears with the expected fetch).
 */

import { useEffect, useState, type ReactElement } from "react";

import { api } from "../../lib/api";

export interface MethodsExportDialogProps {
  runId: string;
  onClose: () => void;
}

export function MethodsExportDialog({ runId, onClose }: MethodsExportDialogProps): ReactElement {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copyOk, setCopyOk] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setMarkdown(null);
    api.lineage
      .getRunMethods(runId)
      .then((res) => {
        if (cancelled) return;
        setMarkdown(res.markdown);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Failed to render methods";
        setError(msg);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Esc closes the dialog.
  useEffect(() => {
    function handleKey(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  function handleCopy(): void {
    if (!markdown) return;
    if (!navigator.clipboard?.writeText) {
      setError("Could not copy. Try Download.");
      return;
    }
    navigator.clipboard
      .writeText(markdown)
      .then(() => {
        setCopyOk(true);
        window.setTimeout(() => setCopyOk(false), 2000);
      })
      .catch(() => {
        setError("Could not copy. Try Download.");
      });
  }

  function handleDownload(): void {
    if (!markdown) return;
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `methods-${runId.slice(0, 8)}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="methods-export-title"
        data-testid="methods-export-dialog"
        className="w-[800px] max-w-[90vw] rounded-3xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3">
          <h2 id="methods-export-title" className="text-lg font-semibold text-ink">
            Methods · Run {runId.slice(0, 8)}
          </h2>
          <button
            type="button"
            className="ml-auto rounded-full p-2 hover:bg-stone-100"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div
          className="mt-3 max-h-[60vh] overflow-y-auto rounded-2xl border border-stone-200 bg-stone-50 p-4"
          data-testid="methods-export-body"
        >
          {loading && <p className="text-sm text-stone-500">Generating methods…</p>}
          {error && (
            <p className="text-sm text-rose-700" aria-live="polite">
              {error}
            </p>
          )}
          {markdown !== null && (
            <pre className="whitespace-pre-wrap font-mono text-xs text-ink">{markdown}</pre>
          )}
        </div>

        <footer className="mt-4 flex items-center gap-2">
          <button
            type="button"
            className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:bg-stone-400"
            disabled={!markdown}
            data-testid="methods-export-copy"
            onClick={handleCopy}
          >
            {copyOk ? "Copied ✓" : "Copy"}
          </button>
          <button
            type="button"
            className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink disabled:text-stone-400"
            disabled={!markdown}
            data-testid="methods-export-download"
            onClick={handleDownload}
          >
            Download .md
          </button>
          <button
            type="button"
            className="ml-auto rounded-full px-4 py-2 text-sm text-stone-700"
            onClick={onClose}
          >
            Close
          </button>
        </footer>
      </div>
    </div>
  );
}
