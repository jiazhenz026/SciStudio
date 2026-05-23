/**
 * Right-hand label column for GraphSVG. Extracted in #1413 — the inner
 * arrow function that mapped over assignments was complexity-16 and the
 * parent function was 179 lines.
 */
import { classifyPrefix } from "../../../../store/gitSlice";
import type { GitCommit } from "../../../../types/api";
import { ROW_HEIGHT } from "../colorPalette";
import type { LaneAssignment } from "../laneAssign";

const PREFIX_ICON: Record<string, string> = {
  auto: "·",
  agent: "🤖",
  user: "👤",
};

function classifyRefKind(ref: string): "tag" | "remote" | "local" {
  const isTag = ref.startsWith("tags/") || ref.startsWith("v");
  if (isTag) return "tag";
  return ref.includes("/") ? "remote" : "local";
}

function refChipClass(kind: "tag" | "remote" | "local"): string {
  if (kind === "tag") return "bg-amber-100 text-amber-800";
  if (kind === "remote") return "bg-stone-100 text-stone-600";
  return "bg-blue-100 text-blue-800";
}

interface RefChipsProps {
  shortSha: string;
  refs: string[];
}

function RefChips({ shortSha, refs }: RefChipsProps) {
  if (refs.length === 0) return null;
  return (
    <span className="flex shrink-0 items-center gap-1" data-testid={`git-graph-refs-${shortSha}`}>
      {refs.map((ref) => {
        const kind = classifyRefKind(ref);
        return (
          <span
            key={ref}
            className={`rounded-sm px-1.5 py-px font-mono text-[10px] leading-none ${refChipClass(kind)}`}
            title={ref}
          >
            {ref}
          </span>
        );
      })}
    </span>
  );
}

interface LabelRowProps {
  a: LaneAssignment;
  commit: GitCommit;
  isFocused: boolean;
  onCommitClick?: (sha: string) => void;
}

function LabelRow({ a, commit, isFocused, onCommitClick }: LabelRowProps) {
  const prefix = classifyPrefix(commit.subject);
  return (
    <li
      key={a.sha}
      data-testid={`git-graph-label-${commit.short_sha}`}
      data-commit-prefix={prefix}
      role="button"
      tabIndex={0}
      aria-selected={isFocused || undefined}
      onClick={() => onCommitClick?.(commit.sha)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onCommitClick?.(commit.sha);
        }
      }}
      className={`flex items-center gap-2 border-b border-stone-100 px-3 text-xs hover:bg-stone-50 focus:bg-stone-100 focus:outline-none ${
        isFocused ? "bg-stone-100" : ""
      } ${a.filtered_out ? "opacity-50" : ""}`}
      style={{ height: `${ROW_HEIGHT}px` }}
    >
      <span aria-hidden>{PREFIX_ICON[prefix] ?? "·"}</span>
      <code className="font-mono text-stone-500">{commit.short_sha}</code>
      <RefChips shortSha={commit.short_sha} refs={commit.branches} />
      <span className="flex-1 truncate text-ink" title={commit.subject}>
        {commit.subject}
      </span>
    </li>
  );
}

export interface GraphLabelsProps {
  assignments: LaneAssignment[];
  commits: GitCommit[];
  visibleStart: number;
  visibleEnd: number;
  height: number;
  focusedIdx?: number | null;
  onCommitClick?: (sha: string) => void;
}

export function GraphLabels({
  assignments,
  commits,
  visibleStart,
  visibleEnd,
  height,
  focusedIdx,
  onCommitClick,
}: GraphLabelsProps) {
  return (
    <ul
      data-testid="git-graph-labels"
      role="list"
      className="min-h-0 flex-1 overflow-hidden"
      style={{ height: `${height}px` }}
    >
      {visibleStart > 0 && (
        <li
          aria-hidden="true"
          data-testid="git-graph-labels-spacer-top"
          style={{ height: `${visibleStart * ROW_HEIGHT}px` }}
        />
      )}
      {assignments.slice(visibleStart, visibleEnd).map((a, offset) => {
        const idx = visibleStart + offset;
        const commit = commits[idx];
        if (!commit) return null;
        return (
          <LabelRow
            key={a.sha}
            a={a}
            commit={commit}
            isFocused={focusedIdx === idx}
            onCommitClick={onCommitClick}
          />
        );
      })}
    </ul>
  );
}
