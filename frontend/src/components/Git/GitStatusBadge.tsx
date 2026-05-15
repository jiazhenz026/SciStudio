/**
 * ADR-039 §3.5 — GitStatusBadge.
 *
 * Compact toolbar pill showing the working-tree state at a glance:
 *   - Clean (green dot) / Dirty (amber + N files) / Conflicted (red + N) /
 *     Loading (grey).
 * Clicking opens the CommitDialog. Hover shows the file list in a native
 * `title` tooltip (Radix tooltip primitives are available but the toolbar
 * already uses native `title=` for compact pills).
 */
import { useEffect } from "react";
import type { JSX } from "react";

import { useAppStore } from "../../store";

export interface GitStatusBadgeProps {
  onClick?: () => void;
}

function classifyStatus(
  status: ReturnType<typeof useAppStore.getState>["status"],
): { key: "clean" | "dirty" | "conflict" | "unknown"; label: string } {
  if (status === null) return { key: "unknown", label: "git: loading…" };
  if (status.conflicted.length > 0) {
    const n = status.conflicted.length;
    return { key: "conflict", label: `${n} conflict${n > 1 ? "s" : ""}` };
  }
  if (!status.dirty) return { key: "clean", label: "clean" };
  const n =
    status.modified.length + status.staged.length + status.untracked.length;
  return { key: "dirty", label: `${n} change${n > 1 ? "s" : ""}` };
}

const DOT_CLASS: Record<string, string> = {
  clean: "bg-pine",
  dirty: "bg-amber-500",
  conflict: "bg-red-500",
  unknown: "bg-stone-400",
};

const PILL_CLASS: Record<string, string> = {
  clean: "bg-pine/15 text-pine",
  dirty: "bg-amber-100 text-amber-800",
  conflict: "bg-red-100 text-red-800",
  unknown: "bg-stone-200 text-stone-500",
};

export function GitStatusBadge(props: GitStatusBadgeProps): JSX.Element | null {
  const status = useAppStore((s) => s.status);
  const loadStatus = useAppStore((s) => s.loadStatus);
  const currentProject = useAppStore((s) => s.currentProject);

  // Refresh git status whenever the active project changes (Codex P1-B on PR
  // #940): the `status` cache lives in a global slice and is not cleared by
  // `setCurrentProject`, so a stale clean/dirty/conflict pill could survive a
  // project switch and mislead the user about uncommitted changes. Keying on
  // the project id guarantees a fresh fetch per project.
  const currentProjectId = currentProject?.id ?? null;
  useEffect(() => {
    if (!currentProjectId) return;
    void loadStatus();
  }, [currentProjectId, loadStatus]);

  // Hide entirely when no project is open.
  if (!currentProject) return null;

  const { key, label } = classifyStatus(status);

  const tooltipLines: string[] = ["Working tree:"];
  if (status === null) {
    tooltipLines.push("loading…");
  } else if (!status.dirty && status.conflicted.length === 0) {
    tooltipLines.push("No uncommitted changes.");
  } else {
    for (const f of status.conflicted) tooltipLines.push(`U  ${f}`);
    for (const f of status.modified) tooltipLines.push(`M  ${f}`);
    for (const f of status.staged) tooltipLines.push(`S  ${f}`);
    for (const f of status.untracked) tooltipLines.push(`?  ${f}`);
  }

  const ariaLabel = `git: ${label}`;

  return (
    <button
      data-testid="git-status-badge"
      data-status={key}
      type="button"
      onClick={props.onClick}
      title={tooltipLines.join("\n")}
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${PILL_CLASS[key]}`}
    >
      <span
        data-testid="git-status-badge-dot"
        className={`h-2 w-2 rounded-full ${DOT_CLASS[key]}`}
      />
      {label}
    </button>
  );
}
