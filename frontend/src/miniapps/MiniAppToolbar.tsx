/**
 * ADR-054 FR-021 — the MiniApp tab's toolbar: the process state and its
 * resident memory (FR-015), Restart, Stop, and Convert to interactive block
 * (FR-036).
 */
import { residentBytes } from "../panels/types";
import type { PanelProcessStatus } from "../panels/types";
import { formatResidentMemory } from "./types";

/** The words FR-015 names, in the order a reader meets them. */
const STATE_LABEL: Record<PanelProcessStatus["state"], string> = {
  starting: "Starting",
  running: "Running",
  unresponsive: "Unresponsive",
  stopped: "Stopped",
  crashed: "Crashed",
  start_failed: "Failed to start",
};

const STATE_TONE: Record<PanelProcessStatus["state"], string> = {
  starting: "bg-amber-100 text-amber-900",
  running: "bg-emerald-100 text-emerald-900",
  unresponsive: "bg-amber-100 text-amber-900",
  stopped: "bg-stone-200 text-stone-700",
  crashed: "bg-red-100 text-red-900",
  start_failed: "bg-red-100 text-red-900",
};

export interface MiniAppToolbarProps {
  name: string;
  /** `null` until the context exists, or for a MiniApp with no `panel.py`. */
  status: PanelProcessStatus | null;
  /** True when the context reported it has no process at all. */
  processAbsent: boolean;
  busy: boolean;
  onRestart: () => void;
  onStop: () => void;
  /** FR-036 — opens the Convert to interactive block dialog. */
  onConvert: () => void;
}

export function MiniAppToolbar(props: MiniAppToolbarProps) {
  const { status, processAbsent, busy } = props;
  const memory = formatResidentMemory(residentBytes(status));
  return (
    <div
      className="flex items-center gap-3 border-b border-stone-200 px-4 py-2 text-xs"
      data-testid="miniapp-toolbar"
    >
      <span className="truncate font-medium text-ink">{props.name}</span>
      {processAbsent ? (
        <span className="text-stone-500" data-testid="miniapp-process-absent">
          No Python process
        </span>
      ) : status ? (
        <>
          <span
            className={`rounded-full px-2 py-0.5 font-medium ${STATE_TONE[status.state]}`}
            data-testid="miniapp-process-state"
          >
            {STATE_LABEL[status.state]}
          </span>
          <span className="text-stone-500" data-testid="miniapp-process-memory">
            {memory}
          </span>
          {/* FR-014 — the exit code is what tells a stopped tab from a crash. */}
          {typeof status.exit_code === "number" ? (
            <span className="text-stone-500" data-testid="miniapp-process-exit">
              exit {status.exit_code}
            </span>
          ) : null}
        </>
      ) : (
        <span className="text-stone-500" data-testid="miniapp-process-state">
          Starting
        </span>
      )}
      <span className="flex-1" />
      <button
        type="button"
        className="toolbar-button"
        disabled={busy || processAbsent}
        onClick={props.onRestart}
      >
        Restart
      </button>
      <button
        type="button"
        className="toolbar-button"
        disabled={busy || processAbsent}
        onClick={props.onStop}
      >
        Stop
      </button>
      <button type="button" className="toolbar-button" onClick={props.onConvert}>
        Convert to interactive block
      </button>
    </div>
  );
}
