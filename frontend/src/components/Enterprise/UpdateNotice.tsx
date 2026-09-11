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
 */

import { ArrowUpCircle } from "lucide-react";
import { useState } from "react";

import type { UpdateCapability } from "../../lib/capabilities";
import {
  browserNavigation,
  errorMessage,
  postForLocation,
  type UpdateStatus,
} from "./enterpriseApi";
import { useUpdateStatus } from "./useUpdateStatus";

interface RestartDialogProps {
  status: UpdateStatus;
  restarting: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

function RestartDialog({ status, restarting, error, onConfirm, onCancel }: RestartDialogProps) {
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
          Restart into SciStudio {status.installedVersion}?
        </p>
        <p className="mb-3 text-sm text-stone-700">
          This SciStudio is running {status.runningVersion}. Restarting stops it and starts the
          installed version; the page reconnects when it is ready.
        </p>
        {status.runsActive ? (
          <p
            className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800"
            data-testid="enterprise-restart-runs-warning"
            role="alert"
          >
            Workflow runs are still active. Restarting now stops them.
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
            disabled={restarting}
            onClick={onConfirm}
            type="button"
          >
            {restarting
              ? "Restarting…"
              : status.runsActive
                ? "Stop runs and restart"
                : "Restart now"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function UpdateNotice({ update }: { update: UpdateCapability }) {
  const { status, refresh } = useUpdateStatus(update);
  const [confirming, setConfirming] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === null || !status.updateAvailable) return null;

  const openConfirmation = () => {
    setError(null);
    setConfirming(true);
    // Re-read so the runs-active warning reflects this moment, not the last poll.
    void refresh();
  };

  const restart = async () => {
    setRestarting(true);
    setError(null);
    try {
      browserNavigation.assign(await postForLocation(update.restartUrl));
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
          onClick={openConfirmation}
          title={`Running ${status.runningVersion}; ${status.installedVersion} is installed`}
          type="button"
        >
          Restart…
        </button>
      </div>
      {confirming ? (
        <RestartDialog
          error={error}
          onCancel={() => setConfirming(false)}
          onConfirm={() => void restart()}
          restarting={restarting}
          status={status}
        />
      ) : null}
    </>
  );
}
