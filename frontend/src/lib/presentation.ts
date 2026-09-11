import { useSyncExternalStore } from "react";

export type Presentation = "workbench" | "ai";
const CHANGE_EVENT = "scistudio:presentation-changed";

export function isDesktopShell(): boolean {
  return Boolean(window.scistudioDesktop);
}

/** Presentation belongs to this page's URL, independently of host capabilities. */
export function readPresentation(): Presentation {
  if (isDesktopShell()) return "workbench";
  return new URLSearchParams(window.location.search).get("ui") === "ai" ? "ai" : "workbench";
}

export function setPresentation(mode: Presentation): void {
  if (isDesktopShell()) return;
  const url = new URL(window.location.href);
  url.searchParams.set("ui", mode);
  window.history.replaceState(window.history.state, "", url);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("popstate", onChange);
  };
}

export function usePresentation(): Presentation {
  return useSyncExternalStore(subscribe, readPresentation, () => "workbench");
}

/** The sidebar and its overlays share one placement contract. */
export function useSidebarSide(): "left" | "right" {
  return usePresentation() === "ai" ? "right" : "left";
}
