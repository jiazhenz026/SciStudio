/**
 * ADR-055 Spec 4 FR-007 — the user-chosen update notice.
 *
 * After an administrator installs a new version, the backend's status route
 * starts answering `update_available`. This notice then appears in the
 * toolbar: non-blocking, announced politely, and never taking focus, so it
 * cannot interrupt someone typing in the editor. Restart asks for
 * confirmation first and warns while workflow runs are active; only then does
 * it `POST` the restart route and follow the `{location}` it answers. Nothing
 * here restarts or reloads on its own.
 *
 * The runs-active warning is never read from a stale poll (#2322 audit P2-2):
 * opening the dialog reads the status afresh and keeps Confirm disabled until
 * that answer arrives, and Confirm reads it once more before posting. If runs
 * started in between, the dialog shows the warning and asks again.
 *
 * The backend can enforce the warning too (umbrella #2321): the restart POST
 * carries `confirm_active_runs`, `true` only once the warning has been shown
 * and accepted. A `409` answer means the backend saw active runs the status
 * read did not; the dialog then names them and asks again.
 */

import { ArrowUpCircle } from "lucide-react";
import { useState } from "react";

import type { UpdateCapability } from "../../lib/capabilities";
import { browserNavigation, errorMessage, postRestart, type UpdateStatus } from "./enterpriseApi";
import { useUpdateStatus } from "./useUpdateStatus";

const STATUS_UNREADABLE =
  "Could not check whether workflow runs are active. Close this and try again.";

interface RestartDialogProps {
  /** The status read when the dialog opened, or `null` while it is being read. */
  status: UpdateStatus | null;
  /** Runs a `409` restart answer named, or `null` when none was received. */
  activeRuns: string[] | null;
  restarting: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

function RestartDialog({
  status,
  activeRuns,
  restarting,
  error,
  onConfirm,
  onCancel,
}: RestartDialogProps) {
  const checking = status === null && error === null;
  const warn = Boolean(status?.runsActive) || activeRuns !== null;
  const named = activeRuns !== null && activeRuns.length > 0 ? `: ${activeRuns.join(", ")}` : "";
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      data-testid="enterprise-restart-dialog"
    >
      <div
        aria-labelledby="enterprise-restart-title"
        aria-modal="true"
        className="w-96 rounded-2xl bg-white p-4 shadow-lg"
        role="dialog"
      >
        <p className="mb-2 text-sm font-semibold text-ink" id="enterprise-restart-title">
          {status !== null
            ? `Restart into SciStudio ${status.installedVersion}?`
            : "Restart SciStudio?"}
        </p>
        {status !== null ? (
          <p className="mb-3 text-sm text-stone-700">
            This SciStudio is running {status.runningVersion}. Restarting stops it and starts the
            installed version; the page reconnects when it is ready.
          </p>
        ) : null}
        {checking ? (
          <p className="mb-3 text-sm text-stone-500" data-testid="enterprise-restart-checking">
            Checking whether workflow runs are active…
          </p>
        ) : null}
        {warn ? (
          <p
            className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800"
            data-testid="enterprise-restart-runs-warning"
            role="alert"
          >
            Workflow runs are still active{named}. Restarting now stops them.
          </p>
        ) : null}
        {error !== null ? (
          <p className="mb-3 text-sm text-rose-600" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            className="rounded-full border border-stone-300 px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-50"
            data-testid="enterprise-restart-cancel"
            onClick={onCancel}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full bg-ink px-3 py-1.5 text-sm text-white hover:opacity-90 disabled:opacity-50"
            data-testid="enterprise-restart-confirm"
            disabled={restarting || status === null}
            onClick={onConfirm}
            type="button"
          >
            {restarting ? "Restarting…" : warn ? "Stop runs and restart" : "Restart now"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function UpdateNotice({ update }: { update: UpdateCapability }) {
  const { status, refresh } = useUpdateStatus(update);
  const [confirming, setConfirming] = useState(false);
  // The status the user is confirming against, read when the dialog opened.
  const [confirmed, setConfirmed] = useState<UpdateStatus | null>(null);
  // Runs a 409 restart answer named; non-null means the warning is showing.
  const [activeRuns, setActiveRuns] = useState<string[] | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === null || !status.updateAvailable) return null;

  const openConfirmation = async () => {
    setConfirming(true);
    setConfirmed(null);
    setActiveRuns(null);
    setError(null);
    const fresh = await refresh();
    if (fresh === null) {
      setError(STATUS_UNREADABLE);
      return;
    }
    setConfirmed(fresh);
  };

  const closeConfirmation = () => {
    setConfirming(false);
    setConfirmed(null);
    setActiveRuns(null);
    setError(null);
  };

  const restart = async () => {
    if (confirmed === null) return;
    // Whether the runs-active warning is on screen as the user confirms.
    const warned = confirmed.runsActive || activeRuns !== null;
    setRestarting(true);
    setError(null);
    // Read once more: runs may have started while the dialog was open.
    const latest = await refresh();
    if (latest === null) {
      setError(STATUS_UNREADABLE);
      setRestarting(false);
      return;
    }
    if (latest.runsActive && !warned) {
      // The user confirmed without the warning; show it and ask again.
      setConfirmed(latest);
      setRestarting(false);
      return;
    }
    try {
      const outcome = await postRestart(update.restartUrl, warned);
      if (outcome.kind === "runs-active") {
        // The backend saw runs the status read did not; name them and ask again.
        setActiveRuns(outcome.runs);
        setConfirmed({ ...latest, runsActive: true });
        setRestarting(false);
        return;
      }
      browserNavigation.assign(outcome.location);
    } catch (failure) {
      setError(`Restart failed: ${errorMessage(failure)}`);
      setRestarting(false);
    }
  };

  return (
    <>
      <div
        aria-live="polite"
        className="inline-flex shrink-0 items-center gap-2 rounded-full border border-pine/40 bg-pine/10 px-3 py-1 text-xs font-medium text-pine"
        data-testid="enterprise-update-notice"
        role="status"
      >
        <ArrowUpCircle aria-hidden="true" className="size-4" />
        <span>
          Update ready: {status.installedVersion}
          <span className="sr-only"> (running {status.runningVersion})</span>
        </span>
        <button
          className="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-pine hover:bg-stone-50"
          data-testid="enterprise-update-restart"
          onClick={() => void openConfirmation()}
          title={`Running ${status.runningVersion}; ${status.installedVersion} is installed`}
          type="button"
        >
          Restart…
        </button>
      </div>
      {confirming ? (
        <RestartDialog
          activeRuns={activeRuns}
          error={error}
          onCancel={closeConfirmation}
          onConfirm={() => void restart()}
          restarting={restarting}
          status={confirmed}
        />
      ) : null}
    </>
  );
}
