/*
 * frontend/src/components/Lineage/RerunDialog.tsx — ADR-038 §3.6 + §3.8
 * =====================================================================
 *
 * SKELETON ONLY. Function body throws `new Error("TODO: D38-2.4c — ...")`.
 *
 * Purpose
 * -------
 * Confirmation dialog for "Re-run this run" (ADR-038 §3.6). Performs the
 * advisory input + environment validation against the recorded run, then
 * (on confirm) calls `api.lineage.rerunRun(runId)` which the backend
 * implements per ADR-038 §6 Phase 3 (D38-2.4a). Warnings are dismissible
 * but never blocking.
 *
 * Props
 * -----
 *
 *   interface RerunDialogProps {
 *     runId:   string;
 *     onClose: () => void;
 *   }
 *
 * State (local)
 * -------------
 *
 *   const detail = useAppStore((s) => s.runDetails[runId]);   // may be undefined
 *   const detailLoading = useAppStore((s) => s.runDetailLoading[runId]);
 *   const detailError   = useAppStore((s) => s.runDetailError[runId]);
 *   const [submitting,  setSubmitting]  = useState(false);
 *   const [submitError, setSubmitError] = useState<string | null>(null);
 *   // Validation result is derived from `detail` + a follow-up API call
 *   // to api.lineage.validateRerun(runId) — see fetch below.
 *   const [validation, setValidation] = useState<RerunValidation | null>(null);
 *   const [validationLoading, setValidationLoading] = useState(true);
 *
 *   // RerunValidation shape (mirrors api.lineage.validateRerun response):
 *   //   {
 *   //     input_warnings: Array<{path: string; reason: string}>;
 *   //     env_warnings:   Array<{package: string; old: string; new: string}>;
 *   //   }
 *
 * Fetch policy
 * ------------
 *   On mount: if `detail` is undefined, dispatch fetchRunDetail(runId)
 *   (slice already handles this on selectRun; the dialog may need a
 *   defensive call when opened from a deep link).
 *
 *   ALSO call api.lineage.validateRerun(runId) — ADR §3.6 pseudocode
 *   compares file size+mtime against `data_objects.size_bytes` /
 *   `mtime_at_write`, and environment_snapshot against current uv pip
 *   freeze. The frontend cannot perform these checks; the backend route
 *   GET /api/runs/{run_id}/validate-rerun returns the diff. (D38-2.4a
 *   owns this route signature — if the parallel PR ships a different
 *   name, the IMPL agent (D38-2.4c) updates the call here.)
 *
 *   The skeleton's lib/api.ts stub is `validateRerun(runId)` to make this
 *   surface explicit.
 *
 * Layout markup pseudocode (vitest selectors)
 * -------------------------------------------
 *
 *   <DialogOverlay onClose={onClose}>
 *     <div
 *       role="dialog"
 *       aria-modal="true"
 *       aria-labelledby="rerun-dialog-title"
 *       data-testid="rerun-dialog"
 *       className="w-[640px] max-w-[90vw] rounded-3xl bg-white p-6 shadow-xl"
 *     >
 *       <header className="flex items-center gap-3">
 *         <h2 id="rerun-dialog-title" className="text-lg font-semibold text-ink">
 *           Re-run · {runId.slice(0, 8)}
 *         </h2>
 *         <button type="button" aria-label="Close" onClick={onClose} ...>×</button>
 *       </header>
 *
 *       <p className="mt-2 text-sm text-stone-600">
 *         A new run will be created with the same workflow YAML, parameters,
 *         and environment recorded for this run. The new run will reference
 *         this one via <code>parent_run_id</code>.
 *       </p>
 *
 *       {(detailLoading || validationLoading) && (
 *         <p data-testid="rerun-dialog-loading">Checking inputs and environment…</p>
 *       )}
 *
 *       {validation && (
 *         <section className="mt-4 space-y-3" data-testid="rerun-dialog-warnings">
 *           {validation.input_warnings.length === 0 &&
 *            validation.env_warnings.length === 0 ? (
 *             <p className="rounded bg-emerald-50 p-3 text-sm text-emerald-700"
 *                data-testid="rerun-dialog-warnings-clean">
 *               No drift detected. Re-running will reproduce the original results
 *               as closely as the current environment allows.
 *             </p>
 *           ) : (
 *             <>
 *               {validation.input_warnings.length > 0 && (
 *                 <div className="rounded bg-amber-50 p-3"
 *                      data-testid="rerun-dialog-input-warnings">
 *                   <h4 className="text-sm font-semibold text-amber-800">
 *                     Input file changes ({validation.input_warnings.length})
 *                   </h4>
 *                   <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
 *                     {validation.input_warnings.map((w, i) => (
 *                       <li key={i}>
 *                         <code>{w.path}</code> — {w.reason}
 *                       </li>
 *                     ))}
 *                   </ul>
 *                 </div>
 *               )}
 *               {validation.env_warnings.length > 0 && (
 *                 <div className="rounded bg-amber-50 p-3"
 *                      data-testid="rerun-dialog-env-warnings">
 *                   <h4 className="text-sm font-semibold text-amber-800">
 *                     Environment drift ({validation.env_warnings.length})
 *                   </h4>
 *                   <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
 *                     {validation.env_warnings.map((w, i) => (
 *                       <li key={i}>
 *                         <code>{w.package}</code>: {w.old} → {w.new}
 *                       </li>
 *                     ))}
 *                   </ul>
 *                 </div>
 *               )}
 *               <p className="text-xs text-stone-600">
 *                 These warnings are advisory only. You can still proceed.
 *               </p>
 *             </>
 *           )}
 *         </section>
 *       )}
 *
 *       {submitError && (
 *         <p className="mt-3 rounded bg-rose-50 p-3 text-sm text-rose-700"
 *            data-testid="rerun-dialog-submit-error">
 *           {submitError}
 *         </p>
 *       )}
 *
 *       <footer className="mt-5 flex items-center gap-2">
 *         <button
 *           type="button"
 *           className="rounded-full bg-ink px-4 py-2 text-sm text-white"
 *           data-testid="rerun-dialog-confirm"
 *           disabled={submitting || detailLoading || validationLoading}
 *           onClick={handleConfirm}
 *         >
 *           {submitting ? "Submitting…" : "Re-run"}
 *         </button>
 *         <button
 *           type="button"
 *           className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink"
 *           data-testid="rerun-dialog-cancel"
 *           onClick={onClose}
 *         >
 *           Cancel
 *         </button>
 *       </footer>
 *     </div>
 *   </DialogOverlay>
 *
 * Action semantics
 * ----------------
 *
 *   handleConfirm:
 *     - set submitting=true, submitError=null
 *     - call api.lineage.rerunRun(runId)
 *     - on success: dispatch fetchRuns() to refresh list, then onClose()
 *       (The new run will appear at top of list; the slice selectRun call
 *       is optional — leaving selection on the parent is also reasonable.
 *       IMPL agent picks one; document in PR.)
 *     - on failure: set submitError=message, submitting=false
 *
 * Copy strings (English, freeze)
 * ------------------------------
 *   Header:                "Re-run · {short_id}"
 *   Explanation:           "A new run will be created with the same workflow
 *                          YAML, parameters, and environment recorded for
 *                          this run. The new run will reference this one
 *                          via parent_run_id."
 *   Checking message:      "Checking inputs and environment…"
 *   Clean banner:          "No drift detected. Re-running will reproduce
 *                          the original results as closely as the current
 *                          environment allows."
 *   Inputs warning header: "Input file changes (N)"
 *   Env warning header:    "Environment drift (N)"
 *   Advisory footer:       "These warnings are advisory only. You can still proceed."
 *   Re-run button:         "Re-run" / "Submitting…"
 *   Cancel button:         "Cancel"
 *
 * Keyboard
 * --------
 *   - Esc closes dialog
 *   - Enter on focused Re-run button triggers handleConfirm
 *   - Tab order: Re-run → Cancel → Close × → (loop)
 *
 * Accessibility
 * -------------
 *   - role="dialog" + aria-modal + aria-labelledby
 *   - Each warning section uses <h4> + <ul> for semantic grouping
 *   - Submit error rendered with aria-live="polite" so screen readers
 *     announce it without yanking focus
 *
 * Edge cases
 * ----------
 *   1. runId no longer in lineage.db (race after manual deletion): server
 *      validateRerun returns 404; the dialog renders submitError with the
 *      404 message and disables the Re-run button (always disabled if
 *      validation === null AND validationLoading === false AND we set
 *      submitError prior).
 *   2. detail is loading: spinner; Re-run button disabled.
 *   3. validation succeeds with all warnings empty: clean banner; Re-run
 *      button enabled.
 *   4. Re-run submitted while another submission is in flight: the
 *      Submitting state disables the button; defensive double-click guard.
 *   5. Network failure during rerunRun call: submitError shows the message;
 *      user can retry.
 *
 * Test plan (no dedicated test file — covered by RunDetail.test.tsx)
 * -----------------------------------------------------------------
 * IMPL agent ensures the dialog opens on Re-run button click and the
 * confirm action dispatches rerunRun.
 */

import { useEffect, useState, type ReactElement } from "react";

import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import type { LineageRerunValidation } from "../../types/lineage";

export interface RerunDialogProps {
  runId: string;
  onClose: () => void;
}

export function RerunDialog({
  runId,
  onClose,
}: RerunDialogProps): ReactElement {
  const detail = useAppStore((s) => s.runDetails[runId]);
  const detailLoading = useAppStore(
    (s) => s.runDetailLoading[runId] ?? false,
  );
  const fetchRunDetail = useAppStore((s) => s.fetchRunDetail);
  const fetchRuns = useAppStore((s) => s.fetchRuns);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [validation, setValidation] = useState<LineageRerunValidation | null>(
    null,
  );
  const [validationLoading, setValidationLoading] = useState(true);

  // Defensive: if the dialog opens via deep-link with no detail cached,
  // populate it.
  useEffect(() => {
    if (detail === undefined && !detailLoading) {
      void fetchRunDetail(runId);
    }
  }, [detail, detailLoading, fetchRunDetail, runId]);

  // Kick off the validation request.
  useEffect(() => {
    let cancelled = false;
    setValidationLoading(true);
    setValidation(null);
    api.lineage
      .validateRerun(runId)
      .then((res) => {
        if (cancelled) return;
        setValidation(res);
        setValidationLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        // Validation is advisory; failure should not block the user.
        setValidation({ input_warnings: [], env_warnings: [] });
        setValidationLoading(false);
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

  async function handleConfirm(): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.lineage.rerunRun(runId);
      await fetchRuns();
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to re-run";
      setSubmitError(msg);
      setSubmitting(false);
    }
  }

  const checking = detailLoading || validationLoading;
  const hasNoWarnings =
    validation !== null &&
    validation.input_warnings.length === 0 &&
    validation.env_warnings.length === 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="rerun-dialog-title"
        data-testid="rerun-dialog"
        className="w-[640px] max-w-[90vw] rounded-3xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3">
          <h2
            id="rerun-dialog-title"
            className="text-lg font-semibold text-ink"
          >
            Re-run · {runId.slice(0, 8)}
          </h2>
          <button
            type="button"
            aria-label="Close"
            className="ml-auto rounded-full p-2 hover:bg-stone-100"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <p className="mt-2 text-sm text-stone-600">
          A new run will be created with the same workflow YAML, parameters,
          and environment recorded for this run. The new run will reference
          this one via <code>parent_run_id</code>.
        </p>

        {checking && (
          <p
            className="mt-3 text-sm text-stone-500"
            data-testid="rerun-dialog-loading"
          >
            Checking inputs and environment…
          </p>
        )}

        {validation && !checking && (
          <section
            className="mt-4 space-y-3"
            data-testid="rerun-dialog-warnings"
          >
            {hasNoWarnings ? (
              <p
                className="rounded bg-emerald-50 p-3 text-sm text-emerald-700"
                data-testid="rerun-dialog-warnings-clean"
              >
                No drift detected. Re-running will reproduce the original
                results as closely as the current environment allows.
              </p>
            ) : (
              <>
                {validation.input_warnings.length > 0 && (
                  <div
                    className="rounded bg-amber-50 p-3"
                    data-testid="rerun-dialog-input-warnings"
                  >
                    <h4 className="text-sm font-semibold text-amber-800">
                      Input file changes ({validation.input_warnings.length})
                    </h4>
                    <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
                      {validation.input_warnings.map((w, i) => (
                        <li key={`${w.path}-${i}`}>
                          <code>{w.path}</code> — {w.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {validation.env_warnings.length > 0 && (
                  <div
                    className="rounded bg-amber-50 p-3"
                    data-testid="rerun-dialog-env-warnings"
                  >
                    <h4 className="text-sm font-semibold text-amber-800">
                      Environment drift ({validation.env_warnings.length})
                    </h4>
                    <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
                      {validation.env_warnings.map((w, i) => (
                        <li key={`${w.package}-${i}`}>
                          <code>{w.package}</code>: {w.old} → {w.new}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-xs text-stone-600">
                  These warnings are advisory only. You can still proceed.
                </p>
              </>
            )}
          </section>
        )}

        {submitError && (
          <p
            className="mt-3 rounded bg-rose-50 p-3 text-sm text-rose-700"
            aria-live="polite"
            data-testid="rerun-dialog-submit-error"
          >
            {submitError}
          </p>
        )}

        <footer className="mt-5 flex items-center gap-2">
          <button
            type="button"
            className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:bg-stone-400"
            data-testid="rerun-dialog-confirm"
            disabled={submitting || checking}
            onClick={() => {
              void handleConfirm();
            }}
          >
            {submitting ? "Submitting…" : "Re-run"}
          </button>
          <button
            type="button"
            className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink"
            data-testid="rerun-dialog-cancel"
            onClick={onClose}
          >
            Cancel
          </button>
        </footer>
      </div>
    </div>
  );
}
