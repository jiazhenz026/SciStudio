/**
 * Slash-command autocomplete picker (#786).
 *
 * Renders a floating dropdown of commands sourced from the user's local
 * Claude Code configuration when the input starts with `/`. The user
 * selects with Tab / Enter / click; we insert the command name into the
 * input and let Claude expand it server-side.
 *
 * Data source: `GET /api/ai/slash_commands?project_dir=...` — refreshed
 * every time the dropdown opens, so newly added files appear without a
 * restart.
 */

import { useEffect, useMemo, useState } from "react";

export interface SlashCommandItem {
  name: string;
  description: string;
  source: string; // "user-commands" | "user-skills" | "project" | "plugin"
  path?: string;
}

interface Props {
  projectDir: string | null;
  /** Current textarea content (the picker watches its prefix). */
  inputValue: string;
  /** Called when the user picks a command. Replaces the input. */
  onPick: (commandName: string) => void;
  /** Called when the picker wants to close (Esc, or click outside). */
  onClose: () => void;
}

const SOURCE_LABELS: Record<string, string> = {
  "user-commands": "User commands",
  "user-skills": "User skills",
  project: "Project",
  plugin: "Plugins",
};

const SOURCE_ORDER = ["user-commands", "user-skills", "project", "plugin"];

export function SlashCommandPicker({ projectDir, inputValue, onPick, onClose }: Props) {
  const [commands, setCommands] = useState<SlashCommandItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlightedIdx, setHighlightedIdx] = useState(0);

  // Only show when input starts with `/` and projectDir is known.
  const active = inputValue.startsWith("/") && projectDir !== null;
  const prefix = active ? inputValue.slice(1).split(/\s/)[0]?.toLowerCase() ?? "" : "";

  useEffect(() => {
    if (!active || projectDir === null) {
      setCommands(null);
      return;
    }
    let cancelled = false;
    fetch(`/api/ai/slash_commands?project_dir=${encodeURIComponent(projectDir)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((body) => {
        if (cancelled) return;
        const list: SlashCommandItem[] = body.commands ?? [];
        setCommands(list);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(String(err));
        setCommands([]);
      });
    return () => {
      cancelled = true;
    };
  }, [active, projectDir]);

  // Filter + group by source.
  const grouped = useMemo(() => {
    if (!commands) return [];
    const filtered = commands.filter((c) =>
      c.name.toLowerCase().startsWith(prefix),
    );
    const bySource = new Map<string, SlashCommandItem[]>();
    for (const c of filtered) {
      const arr = bySource.get(c.source) ?? [];
      arr.push(c);
      bySource.set(c.source, arr);
    }
    const out: { source: string; items: SlashCommandItem[] }[] = [];
    for (const src of SOURCE_ORDER) {
      const items = bySource.get(src);
      if (items && items.length > 0) {
        out.push({ source: src, items });
      }
    }
    return out;
  }, [commands, prefix]);

  // Flat list for keyboard navigation.
  const flat = useMemo(
    () => grouped.flatMap((g) => g.items),
    [grouped],
  );

  // Reset highlight when the filter changes.
  useEffect(() => {
    setHighlightedIdx(0);
  }, [prefix]);

  // Keyboard handling is delegated to the parent (which owns the textarea
  // focus and key events); we expose `pickAt` for the parent to call.
  // To keep the API simple here, the picker also listens for global
  // keys while open — but the parent should call our methods directly
  // via ref if it wants tight integration. For v1, attach a window
  // listener.
  useEffect(() => {
    if (!active || flat.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      // Ignore events from elements that aren't the textarea — be
      // permissive and act on every keydown while open.
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightedIdx((i) => Math.min(i + 1, flat.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightedIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        const picked = flat[highlightedIdx];
        if (picked) onPick(picked.name);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [active, flat, highlightedIdx, onPick, onClose]);

  if (!active || commands === null) return null;
  if (flat.length === 0) {
    return (
      <div
        data-testid="slash-picker-empty"
        className="absolute bottom-full left-0 mb-2 w-[20rem] rounded border border-gray-300 bg-white p-2 text-xs text-gray-500 shadow"
      >
        {error ? `Error: ${error}` : "No matching commands."}
      </div>
    );
  }

  let runningIdx = 0;
  return (
    <div
      data-testid="slash-picker"
      className="absolute bottom-full left-0 mb-2 max-h-[24rem] w-[24rem] overflow-y-auto rounded border border-gray-300 bg-white shadow-lg"
    >
      {grouped.map((group) => (
        <div key={group.source}>
          <div className="bg-gray-50 px-2 py-1 text-xs font-semibold text-gray-600">
            {SOURCE_LABELS[group.source] ?? group.source}
          </div>
          {group.items.map((item) => {
            const idx = runningIdx;
            runningIdx += 1;
            const isHighlighted = idx === highlightedIdx;
            return (
              <button
                key={`${group.source}:${item.name}`}
                type="button"
                data-testid={`slash-item-${item.name}`}
                onMouseDown={(e) => {
                  // Prevent textarea blur before onClick fires.
                  e.preventDefault();
                  onPick(item.name);
                }}
                onMouseEnter={() => setHighlightedIdx(idx)}
                className={`flex w-full flex-col items-start gap-0 px-2 py-1 text-left text-sm ${
                  isHighlighted ? "bg-blue-50" : "hover:bg-gray-50"
                }`}
              >
                <span className="font-mono text-blue-700">/{item.name}</span>
                {item.description && (
                  <span className="truncate text-xs text-gray-500">{item.description}</span>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
