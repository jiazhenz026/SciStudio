/**
 * ADR-053 Learning Center — a session that stopped, said out loud.
 *
 * FR-044 ends a session on a driver failure and keeps the record so the reader
 * can be told what happened. Told where matters: the dialogue is the natural
 * place, and the dialogue is not always on screen — it stands inside the
 * canvas's box and hides itself while the tutorial's project is not the open
 * one. An error is exactly the case where that project may never have opened,
 * and a reader was then left pressing a tutorial that did nothing at all with
 * no sign that anything had gone wrong.
 *
 * So this is a banner rather than part of the scene: fixed to the top of the
 * window, above everything, owing nothing to the canvas or the project. It is
 * the one piece of the tutorial surface that is unconditional.
 */

import { X } from "lucide-react";

export interface TutorialProblemBannerProps {
  /** What the tutorial was, so the reader knows which thing stopped. */
  title: string;
  /** The backend's own account of the failure (FR-044, FR-060). */
  message: string;
  /** FR-090 — leaving is possible at any step, this one included. */
  onLeave: () => void;
}

export function TutorialProblemBanner({ title, message, onLeave }: TutorialProblemBannerProps) {
  return (
    <div
      aria-live="assertive"
      className="pointer-events-auto fixed inset-x-0 top-0 z-[60] flex items-start gap-3 border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700 shadow-[0_6px_20px_rgba(28,33,27,0.12)]"
      data-testid="tutorial-problem-banner"
      role="alert"
    >
      <span className="flex-1 whitespace-pre-wrap">
        <strong className="font-semibold">{title}</strong> stopped. {message}
      </span>
      <button
        aria-label="Leave tutorial"
        className="inline-flex size-6 shrink-0 items-center justify-center rounded-full text-red-700/60 transition hover:bg-red-100 hover:text-red-800"
        onClick={onLeave}
        title="Leave this tutorial"
        type="button"
      >
        <X aria-hidden="true" className="size-3.5" />
      </button>
    </div>
  );
}
