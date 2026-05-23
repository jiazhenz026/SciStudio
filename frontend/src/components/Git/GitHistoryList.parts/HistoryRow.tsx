/**
 * One commit row in the List view of GitHistoryList. Extracted in #1413.
 */
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { classifyPrefix } from "../../../store/gitSlice";
import type { GitCommit } from "../../../types/api";

const PREFIX_ICON: Record<string, string> = {
  auto: "·",
  agent: "🤖",
  user: "👤",
};

export interface HistoryRowProps {
  commit: GitCommit;
  isSelected: boolean;
  onSelect: (commit: GitCommit) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLLIElement>, commit: GitCommit) => void;
  onDiff: (commit: GitCommit) => void;
  onRestore: (commit: GitCommit) => void;
}

export function HistoryRow({
  commit,
  isSelected,
  onSelect,
  onKeyDown,
  onDiff,
  onRestore,
}: HistoryRowProps) {
  const prefix = classifyPrefix(commit.subject);
  return (
    <li
      key={commit.sha}
      data-testid={`git-history-row-${commit.short_sha}`}
      data-commit-prefix={prefix}
      data-selected={isSelected ? "true" : undefined}
      tabIndex={0}
      onClick={() => onSelect(commit)}
      onKeyDown={(e) => onKeyDown(e, commit)}
      className={`flex items-center gap-2 border-b border-stone-100 px-3 py-2 text-xs hover:bg-stone-50 focus:bg-stone-100 focus:outline-none ${
        isSelected ? "bg-stone-100" : ""
      }`}
    >
      <span data-testid="git-history-row-icon" aria-hidden>
        {PREFIX_ICON[prefix] ?? "·"}
      </span>
      <code data-testid="git-history-row-short-sha" className="font-mono text-stone-500">
        {commit.short_sha}
      </code>
      <span
        data-testid="git-history-row-subject"
        className="flex-1 truncate text-ink"
        title={commit.subject}
      >
        {commit.subject}
      </span>
      <span data-testid="git-history-row-author" className="hidden text-stone-500 sm:inline">
        {commit.author_name}
      </span>
      <time
        data-testid="git-history-row-date"
        dateTime={commit.author_date}
        className="text-stone-400"
      >
        {new Date(commit.author_date).toLocaleString()}
      </time>
      <button
        type="button"
        data-testid={`git-history-row-diff-${commit.short_sha}`}
        onClick={(e) => {
          e.stopPropagation();
          onDiff(commit);
        }}
        title="Show diff against parent commit."
        className="ml-2 rounded border border-stone-300 px-2 py-0.5 text-[10px] hover:bg-stone-100"
      >
        Diff
      </button>
      <button
        type="button"
        data-testid={`git-history-row-restore-${commit.short_sha}`}
        onClick={(e) => {
          e.stopPropagation();
          onRestore(commit);
        }}
        title="Soft-restore: copy this commit's files into the working tree without moving HEAD."
        className="ml-1 rounded border border-stone-300 px-2 py-0.5 text-[10px] hover:bg-stone-100"
      >
        Restore this version
      </button>
    </li>
  );
}
