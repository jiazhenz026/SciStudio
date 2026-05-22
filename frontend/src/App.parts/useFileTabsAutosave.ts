// Extracted from App.tsx as part of the #1422 god-file split.
//
// ADR-036 §3.9 — auto-save loop for file tabs (mirrors the workflow
// auto-save). Each dirty file tab gets an independent 800 ms debounce
// timer; editing one tab does not affect another.
//
// #870: per-tab timer state must live OUTSIDE the effect closure. The
// naive `useEffect` cleanup pattern tears down every dirty tab's timer
// on every keystroke (because `tabs` changes identity each
// updateFileTabContent call), so editing tab A keeps cancelling tab B's
// debounce and B never autosaves. We track `{timerId, contentSnapshot}`
// per tab id in a ref so each tab's timer survives unrelated keystrokes.

import { useEffect, useRef } from "react";

import type { ProjectResponse } from "../types/api";
import type { AnyTab, FileTab } from "../store/types";

export interface UseFileTabsAutosaveDeps {
  currentProject: ProjectResponse | null;
  tabs: AnyTab[];
  saveFileTab: (tabId: string) => Promise<void>;
}

export function useFileTabsAutosave({
  currentProject,
  tabs,
  saveFileTab,
}: UseFileTabsAutosaveDeps): void {
  const fileTabAutosaveTimers = useRef<Map<string, { timerId: number; contentSnapshot: string }>>(
    new Map(),
  );

  useEffect(() => {
    const timers = fileTabAutosaveTimers.current;
    if (!currentProject) {
      // Project closed — drop everything pending.
      timers.forEach(({ timerId }) => window.clearTimeout(timerId));
      timers.clear();
      return undefined;
    }
    const dirtyFileTabs = tabs.filter(
      (t) => t.kind === "file" && t.dirty && !t.readOnly,
    ) as FileTab[];
    const dirtyIds = new Set(dirtyFileTabs.map((t) => t.id));

    // Cancel timers for tabs no longer dirty / no longer present.
    timers.forEach(({ timerId }, id) => {
      if (!dirtyIds.has(id)) {
        window.clearTimeout(timerId);
        timers.delete(id);
      }
    });

    // For each dirty tab, schedule (or reset only if content changed).
    // Leaving an in-flight timer untouched when content is unchanged is
    // the load-bearing part of the fix — that is what lets tab B's
    // debounce reach 800 ms while the user keeps typing in tab A.
    for (const tab of dirtyFileTabs) {
      const existing = timers.get(tab.id);
      if (existing && existing.contentSnapshot === tab.content) continue;
      if (existing) window.clearTimeout(existing.timerId);
      const timerId = window.setTimeout(() => {
        timers.delete(tab.id);
        void saveFileTab(tab.id).catch((error) => {
          console.warn(`saveFileTab(${tab.id}) failed:`, error);
        });
      }, 800);
      timers.set(tab.id, { timerId, contentSnapshot: tab.content });
    }
    return undefined;
  }, [currentProject, tabs, saveFileTab]);

  // Defensive: cancel all pending file-tab autosaves on unmount so a
  // timer cannot fire against a torn-down store. The ref Map is also
  // intentionally not in any dep array elsewhere.
  useEffect(() => {
    const timers = fileTabAutosaveTimers.current;
    return () => {
      timers.forEach(({ timerId }) => window.clearTimeout(timerId));
      timers.clear();
    };
  }, []);
}
