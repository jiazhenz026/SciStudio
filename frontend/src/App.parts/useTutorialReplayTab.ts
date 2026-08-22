/**
 * ADR-053 FR-061a / #2083 — adopt the tutorial's scripted replay tab.
 *
 * The tutorial runtime opens a scripted PTY-shaped byte source when a step's
 * replay plays, and names it in the session response as
 * `session.replay = {surface, tab_id}`. That field was typed and delivered
 * from the day the runtime landed, and consumed by nothing — the transcript
 * played into a byte source no surface ever attached to. This hook is the
 * consumer: it folds the named tab into the AI Chat tab strip the way the
 * work-import dialog folds in its own prespawned session, so the tab strip,
 * the terminal component, and the tab lifecycle stay the product's real ones
 * and only the byte source differs (FR-061a's whole design).
 *
 * Three rules, each load-bearing:
 *
 * **Adopt only on a change observed while this page is alive.** A replay tab
 * cannot survive the page: closing the WebSocket tears the scripted session
 * down on the backend (FR-061c teardown parity), so a `replay` value already
 * present when this hook first looks — a reload mid-tutorial, a second
 * window — names a session this page can no longer join. Joining a stale id
 * would not even fail politely: the PTY route spawns a fresh terminal for an
 * unknown tab id, which is a real shell nobody asked for. The first
 * observation is therefore recorded, never acted on.
 *
 * **Tear down with the session.** When the replay clears — the reader leaves
 * the tutorial, finishes it, or the session errors — the adopted tab is
 * closed rather than left to die visibly. A dead "Terminal exited" card
 * inviting a Reopen that cannot work is worse than the tab being gone.
 *
 * **One tab id, one adoption.** `continue_tab` replays (#2089) append to the
 * same tab and never change `tab_id`, so re-renders and refetches are
 * naturally idempotent here; only a genuinely new id re-adopts.
 */

import { useEffect, useRef } from "react";

import { useAppStore } from "../store";

/** The tab strip label for the scripted session. Honest on its face. */
export const TUTORIAL_REPLAY_TAB_TITLE = "Scripted AI session";

export function useTutorialReplayTab(): void {
  const replayTabId = useAppStore((state) => state.learningCenterSession?.replay?.tab_id ?? null);
  const adoptTutorialReplayTab = useAppStore((state) => state.adoptTutorialReplayTab);
  const closeTerminalTab = useAppStore((state) => state.closeTerminalTab);
  const openBottomTab = useAppStore((state) => state.openBottomTab);

  /*
   * `stale` holds the replay id that was already in the store when this page
   * mounted — the one session this page must never join (see the module
   * comment). Captured at first render rather than in the effect, so an
   * effect that runs twice (StrictMode, remounts) cannot mistake the stale
   * value for a fresh transition. Any *observed change* clears it: from that
   * point the page has watched the value move and every id is live.
   */
  const stale = useRef<string | null>(replayTabId);
  /* The tab this page has adopted, or null. */
  const adopted = useRef<string | null>(null);

  useEffect(() => {
    if (stale.current !== null && replayTabId === stale.current) return;
    stale.current = null;

    if (replayTabId === adopted.current) return;
    if (adopted.current !== null) {
      closeTerminalTab(adopted.current);
    }
    if (replayTabId !== null) {
      adoptTutorialReplayTab({ tabId: replayTabId, title: TUTORIAL_REPLAY_TAB_TITLE });
      /*
       * The step that started the replay routes to `ai_chat` on entry, but the
       * replay opens on the reader's *press*, which can come long after entry
       * — after they wandered to Logs, say. Opening the AI tab here is what
       * makes the reply they just asked for appear where they can see it.
       */
      openBottomTab("ai");
    }
    adopted.current = replayTabId;
  }, [replayTabId, adoptTutorialReplayTab, closeTerminalTab, openBottomTab]);

  /*
   * Unmount is not teardown: the backend owns the replay lifecycle, and the
   * session (with its tab) may outlive this component tree in tests. The tab
   * is closed by the transition above or dropped by rehydration on reload.
   */
}
