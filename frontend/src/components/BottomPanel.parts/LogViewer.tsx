import { useMemo, useState } from "react";

import type { LogEntry } from "../../types/api";

export function LogViewer({ entries }: { entries: LogEntry[] }) {
  const [level, setLevel] = useState("all");
  const filtered = useMemo(() => {
    return entries.filter((entry) => level === "all" || entry.level === level);
  }, [entries, level]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center gap-3">
        <select
          className="rounded-full border border-stone-300 bg-white px-3 py-2 text-sm"
          onChange={(event) => setLevel(event.target.value)}
          value={level}
        >
          <option value="all">All levels</option>
          <option value="info">Info</option>
          <option value="error">Error</option>
        </select>
      </div>
      <div className="flex-1 overflow-auto rounded-[1.4rem] border border-stone-200 bg-stone-950 p-4">
        {filtered.length ? (
          filtered.map((entry) => (
            <div
              className="border-b border-stone-800 py-2 text-sm text-stone-100"
              key={[
                entry.timestamp,
                entry.level,
                entry.workflow_id ?? "workflow",
                entry.block_id ?? "system",
                entry.message,
              ].join("|")}
            >
              <p className="text-[11px] uppercase tracking-[0.3em] text-stone-500">
                {entry.level} · {entry.workflow_id ?? "workflow"} · {entry.block_id ?? "system"}
              </p>
              <p className="mt-1 break-words">{entry.message}</p>
              {entry.details && entry.details !== entry.message ? (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-medium text-stone-400 hover:text-stone-200">
                    Show traceback
                  </summary>
                  <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded border border-stone-800 bg-stone-900 p-3 text-xs leading-5 text-stone-300">
                    {entry.details}
                  </pre>
                </details>
              ) : null}
            </div>
          ))
        ) : (
          <p className="text-sm text-stone-500">No logs yet.</p>
        )}
      </div>
    </div>
  );
}
