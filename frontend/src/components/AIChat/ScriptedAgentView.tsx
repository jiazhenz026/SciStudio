/**
 * ADR-053 FR-061a (#2083) — the scripted session, shaped like an agent CLI.
 *
 * A recorded transcript played into a bare terminal reads as a log file, not as
 * an agent: the reader's own question arrives the same way the answer does, out
 * of nowhere, already written. What makes an agent CLI legible as one is the
 * part a transcript cannot contain — a prompt box at the bottom that you type
 * into and send, with the conversation scrolling above it.
 *
 * So the box is real furniture and the question is typed into it: the reader
 * watches the question appear a character at a time where a question is
 * actually written, watches it sent, and then watches the answer arrive above.
 * Nothing about it is interactive, and it does not pretend to be — the box
 * takes no keystrokes and says so. It is an animation of an exchange, which is
 * exactly what the level declares it to be.
 *
 * **The conversation is still the product's real terminal.** FR-061a's point —
 * the tab strip, the terminal component and the tab lifecycle stay the real
 * ones and only the byte source differs — is unaffected: `TerminalView` renders
 * the transcript here exactly as it renders a live agent, ANSI colours and all.
 * What this component adds is chrome around it and a home for the one line the
 * terminal was the wrong place for.
 */
import { useCallback, useState } from "react";

import { useAppStore } from "../../store";
import type { TerminalProvider } from "../../store/types";
import { scriptedAgentBanner } from "./scriptedAgentBanner";
import type { PromptSink } from "./scriptedPacing";
import { TerminalView } from "./TerminalView";

export interface ScriptedAgentViewProps {
  tabId: string;
  projectDir: string;
  provider: TerminalProvider;
  onExit: (code: number) => void;
  onError: (message: string) => void;
}

export function ScriptedAgentView({
  tabId,
  projectDir,
  provider,
  onExit,
  onError,
}: ScriptedAgentViewProps) {
  /* What is currently sitting in the prompt box, mid-question or empty. */
  const [typed, setTyped] = useState("");

  const promptSink: PromptSink = {
    onType: useCallback((text: string) => setTyped((current) => current + text), []),
    onSubmit: useCallback(() => setTyped(""), []),
  };

  /*
   * #2083 — the reply is on screen, so what it claimed can land now.
   *
   * The tutorial runtime holds a replay segment's file writes from the moment
   * the button is pressed until this call, which is what stops the canvas
   * rearranging itself while the agent is still describing the change. Posting
   * when nothing is pending is defined to be harmless, so this fires on every
   * quiet terminal without having to know what the reply bound.
   */
  const settleReplay = useAppStore((state) => state.settleActiveTutorialReplay);
  const handleIdle = useCallback(() => {
    void settleReplay();
  }, [settleReplay]);

  return (
    <div
      className="flex h-full flex-col overflow-hidden rounded-2xl border border-stone-200 bg-[#1e1e1e] font-mono"
      data-testid={`scripted-agent-${tabId}`}
    >
      {/* The conversation, with the name plate written into the top of its own
          buffer rather than pinned above it: a CLI prints its name once and
          then gets on with the session, and a header that never leaves would
          keep taking that room from the conversation for the rest of it.
          `paced` is what makes the reply arrive rather than appear, and
          `promptSink` is what diverts the question into the box below instead
          of typing it here. */}
      <div className="min-h-0 flex-1">
        <TerminalView
          tabId={tabId}
          projectDir={projectDir}
          provider={provider}
          dangerous={false}
          onExit={onExit}
          onError={onError}
          paced
          promptSink={promptSink}
          chromeless
          banner={scriptedAgentBanner()}
          onScriptedIdle={handleIdle}
        />
      </div>

      {/* The prompt box, pinned. It is always present, even while empty:
          furniture that came and went with each question would read as a
          notification, not as the place your questions go. */}
      <div className="shrink-0 px-4 pb-3 pt-1">
        <div
          className="rounded-lg border border-stone-600 bg-black/40 px-3 py-2 text-sm text-stone-100"
          data-testid={`scripted-agent-prompt-${tabId}`}
        >
          <span className="select-none text-stone-500">{"> "}</span>
          <span className="whitespace-pre-wrap break-words">{typed}</span>
          {/* The caret sits after whatever has been typed so far, so an empty
              box still looks like somewhere text is about to go. */}
          <span
            aria-hidden
            className="ml-px inline-block w-[0.55em] animate-pulse bg-stone-300 align-text-bottom"
          >
            &nbsp;
          </span>
        </div>
        <div className="pt-1.5 text-[11px] leading-none text-stone-500 select-none">
          Recorded session — the box types itself, and takes no input.
        </div>
      </div>
    </div>
  );
}
