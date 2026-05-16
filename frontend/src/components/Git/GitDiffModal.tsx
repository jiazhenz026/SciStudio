/**
 * ADR-039 §3.5 — GitDiffModal.
 *
 * Modal viewer for the unified diff returned by `GET /api/git/diff`.
 *
 * Implementation choice (D39-2.3b): the skeleton documented the option of
 * pulling in `react-diff-viewer-continued`. We implement this v1 with a
 * minimal in-tree renderer for the unified-diff output instead, because:
 *   1. The backend `/api/git/diff` already returns unified-diff text — no
 *      side-by-side split is needed for v1 (per ADR §3.5).
 *   2. Adding a new frontend dep here would force the user to run
 *      `npm install` in the main checkout; the cascade hygiene rules
 *      discourage worktree dep changes (CLAUDE.md §6 cascade boilerplate).
 *   3. Line-by-line colorization with monospaced `<pre>` matches the
 *      existing aesthetics (CodeEditor, Logs panel) and is keyboard /
 *      screen-reader friendly without third-party widgetry.
 * D39-2.4a/b can upgrade to a richer diff viewer when MergeFlow lands.
 */
import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { api } from "../../lib/api";

export interface GitDiffModalProps {
  open: boolean;
  onClose: () => void;
  from: string;
  to?: string;
  file?: string;
  title?: string;
}

function classifyLine(line: string): {
  cls: string;
  marker: string;
} {
  if (line.startsWith("diff --git") || line.startsWith("index ")) {
    return { cls: "text-stone-500 font-semibold", marker: "" };
  }
  if (line.startsWith("---") || line.startsWith("+++")) {
    return { cls: "text-stone-600 font-semibold", marker: "" };
  }
  if (line.startsWith("@@")) {
    return { cls: "text-blue-600", marker: "" };
  }
  if (line.startsWith("+")) {
    return { cls: "bg-green-50 text-green-800", marker: "+" };
  }
  if (line.startsWith("-")) {
    return { cls: "bg-red-50 text-red-800", marker: "-" };
  }
  return { cls: "text-stone-700", marker: " " };
}

export function GitDiffModal(props: GitDiffModalProps): JSX.Element | null {
  const { open, onClose, from, to, file, title } = props;

  const [loading, setLoading] = useState(false);
  const [diffText, setDiffText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !from) return;
    setLoading(true);
    setError(null);
    setDiffText(null);
    api
      .gitDiff({ from, to, file })
      .then((resp) => {
        setDiffText(resp.diff);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load diff");
      })
      .finally(() => setLoading(false));
  }, [open, from, to, file]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    },
    [onClose],
  );

  if (!open) return null;

  const headerTitle = title ?? `Diff ${from}${to ? ` → ${to}` : " → working"}`;
  const lines = diffText !== null ? diffText.split("\n") : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="git-diff-title"
      onKeyDown={handleKeyDown}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        data-testid="git-diff-modal"
        className="flex max-h-[85vh] w-full max-w-5xl flex-col rounded-lg bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3">
          <h2 id="git-diff-title" className="text-base font-semibold text-ink">
            {headerTitle}
          </h2>
          <Button
            data-testid="git-diff-close"
            variant="toolbar"
            size="toolbar"
            type="button"
            onClick={onClose}
          >
            Close
          </Button>
        </div>

        {/*
          Hotfix #1007: `min-w-0` prevents this flex-1 child from being
          sized to its intrinsic content width, which would push the
          parent modal beyond its `max-w-5xl` cap when a diff line is
          very long. With `min-w-0` the child can shrink below content
          width and the `overflow-auto` actually creates a horizontal
          scrollbar instead of stretching the modal.
        */}
        <div className="min-h-0 min-w-0 flex-1 overflow-auto px-2 py-2">
          {loading ? (
            <div data-testid="git-diff-loading" className="p-4 text-sm text-stone-500">
              Loading diff…
            </div>
          ) : error ? (
            <div
              role="alert"
              data-testid="git-diff-error"
              className="p-4 text-sm text-red-700"
            >
              {error}
            </div>
          ) : diffText === "" ? (
            <div data-testid="git-diff-empty" className="p-4 text-sm text-stone-500">
              No differences.
            </div>
          ) : (
            <pre
              data-testid="git-diff-viewer"
              className="font-mono text-xs leading-relaxed"
            >
              {lines.map((line, i) => {
                const { cls } = classifyLine(line);
                return (
                  <div key={i} className={`whitespace-pre px-2 ${cls}`}>
                    {line || " "}
                  </div>
                );
              })}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
