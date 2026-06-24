import { useMemo, useState } from "react";

import { exportDiagnosticBundle } from "../../lib/logger";
import type { LogEntry } from "../../types/api";

export function LogViewer({ entries }: { entries: LogEntry[] }) {
  const [level, setLevel] = useState("all");
  const [exporting, setExporting] = useState(false);
  const filtered = useMemo(() => {
    return entries.filter((entry) => level === "all" || entry.level === level);
  }, [entries, level]);

  // #1760 bug2: disable + label the button while the bundle is built/written so
  // the click has immediate feedback and can't be double-fired. The native save
  // dialog now appears first, so this state mostly covers the background write.
  const onExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      await exportDiagnosticBundle();
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/*
       * Live hotfix batch: Logs adopt the light Git-history list aesthetic
       * (bordered rows on the panel background) instead of the old dark
       * stone-950 console card.
       */}
      <div className="flex items-center gap-2 border-b border-stone-200 px-3 py-2">
        <select
          className="rounded border border-stone-300 bg-white px-2 py-1 text-xs"
          onChange={(event) => setLevel(event.target.value)}
          value={level}
        >
          <option value="all">All levels</option>
          <option value="info">Info</option>
          <option value="error">Error</option>
        </select>
        {/* #1741: one-click diagnostic bundle (logs + environment + run logs)
            so a beta tester can attach everything a developer needs to a report. */}
        <button
          type="button"
          onClick={() => void onExport()}
          disabled={exporting}
          className="ml-auto rounded border border-stone-300 bg-white px-2 py-1 text-xs hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-60"
          title="Export logs + environment as a zip for bug reports"
        >
          {exporting ? "Exporting…" : "Export logs"}
        </button>
      </div>
      {filtered.length ? (
        <ul role="list" className="min-h-0 flex-1 overflow-y-auto">
          {filtered.map((entry) => {
            // Error-level rows are tinted red (label + message) so a new error
            // is eye-catching against the lighter info rows.
            const isError = entry.level === "error";
            return (
              <li
                className={`border-b border-stone-100 px-3 py-2 text-sm hover:bg-stone-50 ${
                  isError ? "bg-red-50/60" : ""
                }`}
                data-level={entry.level}
                key={[
                  entry.timestamp,
                  entry.level,
                  entry.workflow_id ?? "workflow",
                  entry.block_id ?? "system",
                  entry.message,
                ].join("|")}
              >
                <p
                  className={`text-[11px] uppercase tracking-[0.3em] ${
                    isError ? "text-red-500" : "text-stone-400"
                  }`}
                >
                  {entry.level} · {entry.workflow_id ?? "workflow"} · {entry.block_id ?? "system"}
                </p>
                <p
                  className={`mt-1 break-words ${isError ? "font-medium text-red-600" : "text-ink"}`}
                >
                  {entry.message}
                </p>
                {entry.details && entry.details !== entry.message ? (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-stone-500 hover:text-ink">
                      Show traceback
                    </summary>
                    <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded border border-stone-200 bg-stone-50 p-3 text-xs leading-5 text-stone-700">
                      {entry.details}
                    </pre>
                  </details>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="px-3 py-4 text-xs text-stone-500">No logs yet.</p>
      )}
    </div>
  );
}
