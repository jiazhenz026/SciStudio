/**
 * ADR-039 §3.5 + §3.7 — StashListPanel.
 *
 * Right-side drawer surfacing the stash list. Lets the user inspect /
 * apply / drop entries and create a new stash from the current working
 * tree.
 *
 * Implementation choice (D39-2.3b): the skeleton documented Radix Sheet.
 * We render a simple right-aligned fixed panel — the cascade hygiene rule
 * discourages adding new shadcn/Radix primitives without an ADR. The
 * markup keeps the documented `data-testid` contract.
 */
import { useCallback, useEffect, useState } from "react";
import type { JSX } from "react";

import { Button } from "@/components/ui/button";

import { api } from "../../lib/api";
import { useAppStore } from "../../store";

export interface StashListPanelProps {
  open: boolean;
  onClose: () => void;
}

export function StashListPanel(props: StashListPanelProps): JSX.Element | null {
  const { open, onClose } = props;
  const stashes = useAppStore((s) => s.stashes);
  const loadStashes = useAppStore((s) => s.loadStashes);
  const loadStatus = useAppStore((s) => s.loadStatus);
  const setLastError = useAppStore((s) => s.setLastError);

  const [newPromptOpen, setNewPromptOpen] = useState(false);
  const [newMessage, setNewMessage] = useState("");

  useEffect(() => {
    if (open) void loadStashes();
  }, [open, loadStashes]);

  const handleApply = useCallback(
    async (sid: string) => {
      try {
        await api.gitStashApply(sid);
        void loadStatus();
        void loadStashes();
      } catch (err) {
        setLastError(err instanceof Error ? err.message : "Stash apply failed");
      }
    },
    [loadStashes, loadStatus, setLastError],
  );

  const handleDrop = useCallback(
    async (sid: string) => {
      const ok = window.confirm(`Drop stash '${sid}'? This cannot be undone.`);
      if (!ok) return;
      try {
        await api.gitStashDrop(sid);
        void loadStashes();
      } catch (err) {
        setLastError(err instanceof Error ? err.message : "Stash drop failed");
      }
    },
    [loadStashes, setLastError],
  );

  const handleNewStash = useCallback(async () => {
    const message = newMessage.trim() || undefined;
    try {
      await api.gitStashSave(message);
      void loadStashes();
      void loadStatus();
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Stash save failed");
    } finally {
      setNewPromptOpen(false);
      setNewMessage("");
    }
  }, [loadStashes, loadStatus, newMessage, setLastError]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          onClose();
        }
      }}
    >
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
        aria-hidden
      />
      <aside
        data-testid="stash-list-panel"
        role="dialog"
        aria-label="Stashes"
        className="absolute right-0 top-0 flex h-full w-[24rem] flex-col border-l border-stone-200 bg-white shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
          <h2 className="text-base font-semibold text-ink">Stashes</h2>
          <div className="flex gap-2">
            <Button
              data-testid="stash-list-new"
              variant="toolbar"
              size="toolbar"
              type="button"
              onClick={() => setNewPromptOpen(true)}
            >
              New stash…
            </Button>
            <Button variant="toolbar" size="toolbar" type="button" onClick={onClose}>
              Close
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {stashes === null ? (
            <div
              data-testid="stash-list-loading"
              className="px-4 py-6 text-sm text-stone-500"
            >
              Loading stashes…
            </div>
          ) : stashes.length === 0 ? (
            <div
              data-testid="stash-list-empty"
              className="px-4 py-6 text-sm text-stone-500"
            >
              No stashes yet.
            </div>
          ) : (
            <ul data-testid="stash-list-rows" role="list">
              {stashes.map((s, i) => (
                <li
                  key={s.stash_id}
                  data-testid={`stash-row-${i}`}
                  className="flex flex-col gap-1 border-b border-stone-100 px-4 py-3"
                >
                  <div className="flex items-center gap-2">
                    <code
                      data-testid="stash-row-id"
                      className="font-mono text-xs text-stone-500"
                    >
                      {s.stash_id}
                    </code>
                    <time
                      data-testid="stash-row-date"
                      className="ml-auto text-[10px] text-stone-400"
                      dateTime={s.date}
                    >
                      {new Date(s.date).toLocaleString()}
                    </time>
                  </div>
                  <p
                    data-testid="stash-row-msg"
                    className="truncate text-sm text-ink"
                    title={s.message}
                  >
                    {s.message || <em className="text-stone-400">(no message)</em>}
                  </p>
                  <div className="mt-1 flex gap-2">
                    <Button
                      data-testid={`stash-row-apply-${i}`}
                      variant="toolbar-dark"
                      size="toolbar"
                      type="button"
                      onClick={() => void handleApply(s.stash_id)}
                    >
                      Apply
                    </Button>
                    <Button
                      data-testid={`stash-row-drop-${i}`}
                      variant="toolbar"
                      size="toolbar"
                      type="button"
                      onClick={() => void handleDrop(s.stash_id)}
                      className="!text-red-700"
                    >
                      Drop
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {newPromptOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="stash-new-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) setNewPromptOpen(false);
          }}
        >
          <div
            className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="stash-new-title" className="text-base font-semibold">
              Save current changes to a new stash
            </h2>
            <label
              htmlFor="stash-new-message"
              className="mt-3 block text-xs uppercase text-stone-500"
            >
              Stash message (optional):
            </label>
            <input
              id="stash-new-message"
              type="text"
              autoFocus
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void handleNewStash();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setNewPromptOpen(false);
                }
              }}
              className="mt-1 block w-full rounded border border-stone-300 px-3 py-2 text-sm outline-none focus:border-pine"
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="toolbar"
                size="toolbar"
                type="button"
                onClick={() => setNewPromptOpen(false)}
              >
                Cancel
              </Button>
              <Button
                variant="toolbar-dark"
                size="toolbar"
                type="button"
                onClick={() => void handleNewStash()}
              >
                Save stash
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
