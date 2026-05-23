/**
 * Working-tree file list inside CommitDialog. Extracted in #1413.
 */
import type { GitStatus } from "../../../types/api";

export interface WorkingTreeListProps {
  status: GitStatus | null;
}

export function WorkingTreeList({ status }: WorkingTreeListProps) {
  const fileEntries: { kind: string; path: string }[] = [];
  if (status) {
    for (const p of status.modified) fileEntries.push({ kind: "M", path: p });
    for (const p of status.staged) fileEntries.push({ kind: "S", path: p });
    for (const p of status.untracked) fileEntries.push({ kind: "A", path: p });
  }

  return (
    <div className="mt-3">
      <p className="text-xs font-semibold uppercase text-stone-500">Working tree</p>
      {status === null ? (
        <p className="mt-1 text-xs text-stone-400">Loading file list…</p>
      ) : !status.dirty ? (
        <p className="mt-1 text-xs text-stone-400">No changes to commit.</p>
      ) : (
        <ul
          data-testid="commit-dialog-files"
          className="mt-1 max-h-24 overflow-y-auto text-xs font-mono"
        >
          {fileEntries.map((entry, i) => (
            <li key={`${entry.kind}-${entry.path}-${i}`} className="text-stone-600">
              {entry.kind} {entry.path}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
