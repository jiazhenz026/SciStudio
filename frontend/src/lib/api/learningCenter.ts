/**
 * ADR-053 Learning Center (#2057) — client for `/api/tutorials`.
 *
 * The wire shapes below are the manager-owned HTTP contract in
 * `docs/planning/learning-center-checklist.md` §6.1.6. They are transcribed
 * here rather than invented: a field this file adds on its own would be a
 * field the backend never sends.
 *
 * Nothing in this module judges a tutorial. Spec §4.1 puts every completion
 * decision on the backend, because almost every condition the designed
 * scenarios need is a backend fact — a registered type, a git branch, a
 * succeeded run, a file on disk. The frontend reports what the user did
 * (`reportTutorialUiEvent`, FR-052), asks for a re-read of state no event
 * reaches (`evaluateActiveTutorialStep`, FR-053), and renders whatever step
 * view comes back.
 *
 * Types live beside the client rather than in `types/api.ts`, following the
 * work-import module (#2001), so the contract and the calls that depend on it
 * move together.
 */

import { apiFetch, JSON_HEADERS } from "./core";

/** §6.1.6 — the four discovery sources a tutorial can come from. */
export type TutorialSourceKind = "core" | "package" | "user" | "project";

/**
 * §6.1.6 — the state the backend reports for a catalogue entry (FR-085).
 *
 * `unavailable` always arrives with an `unavailable_reason`: a tutorial whose
 * required package is missing is still *listed*, because a user cannot decide
 * to install a package whose tutorials they were never shown.
 */
export type TutorialEntryState = "not_started" | "in_progress" | "complete" | "unavailable";

/** §6.1.6 `CatalogueEntry`. */
export interface TutorialCatalogueEntry {
  source_kind: TutorialSourceKind;
  /** `""` for core, the distribution name for a package, `user` / `project`. */
  source_id: string;
  id: string;
  title: string;
  summary: string;
  cover_url: string | null;
  order: number;
  state: TutorialEntryState;
  unavailable_reason: string | null;
  /**
   * The tutorial project directory on disk, when one exists.
   *
   * Carried on the entry so the restart confirmation can name the directory it
   * is about to delete (FR-066, FR-067, FR-087) without a second round trip.
   */
  project_directory: string | null;
  /**
   * Whether the tutorial only ever asks the reader to read on.
   *
   * Derived on the backend from the steps' own conditions rather than declared
   * in the manifest — a tutorial cannot claim to be reading while waiting on a
   * run to succeed. The Learning Center lists these under their own tab.
   */
  reading: boolean;
}

/** §6.1.6 — one source's group, with its own counts (FR-084, FR-076). */
export interface TutorialCatalogueGroup {
  source_kind: TutorialSourceKind;
  source_id: string;
  label: string;
  completed: number;
  total: number;
  tutorials: TutorialCatalogueEntry[];
}

export interface TutorialCatalogueResponse {
  groups: TutorialCatalogueGroup[];
  active: TutorialSessionResponse | null;
  /** Per-source discovery problems; one bad manifest never empties a group. */
  diagnostics: string[];
}

/**
 * §6.1.6 — the step view, rendered verbatim.
 *
 * `awaiting_continue` is the one step kind that carries a continue button
 * (FR-012, the reading case). Every other step advances on its own the moment
 * its condition holds, with no confirmation click (User Story 1, acceptance 3).
 */
/**
 * What a step points at, and which one of it.
 *
 * `args` is empty for the targets whose name is already an address, and carries
 * the selector for the ones that address an element among many of its kind:
 * `block_type` for `palette_block` and `node`, `plot_id` for `plot_card`. Kept
 * as an open record rather than a union per target so a new backend target does
 * not need a matching type change here — the closed set lives in
 * `scistudio.tutorials.manifest.HIGHLIGHT_SPECS` and is mirrored for lookup in
 * `LearningCenter.parts/targets.ts`.
 */
export interface TutorialHighlightView {
  target: string;
  args: Record<string, string>;
}

/**
 * FR-011b — a dialog this step seeds, and the values it opens holding.
 *
 * The same shape as a highlight, meaning something different: a highlight
 * points at what is already on screen, a prefill supplies the default for
 * something not yet open. The closed target set lives in
 * `scistudio.tutorials.manifest.PREFILL_SPECS`; the frontend consumer for each
 * target is what makes it do anything.
 */
export interface TutorialPrefillView {
  target: string;
  args: Record<string, string>;
}

export interface TutorialStepView {
  id: string;
  index: number;
  total: number;
  /** FR-011c — the step's own short heading; null falls back to the tutorial's. */
  title: string | null;
  say: string | null;
  highlight: TutorialHighlightView | null;
  route_to: string | null;
  prefill: TutorialPrefillView[];
  awaiting_continue: boolean;
  /**
   * FR-054a — whether this step's condition holds right now.
   *
   * What Continue reads to decide whether it is live. Reported by the backend
   * rather than worked out here: judging is spec §4.1's backend concern, and a
   * second copy of the rule in the frontend is the thing FR-002 removed.
   */
  satisfied: boolean;
}

/** §6.1.7 — the single declared replay surface and the tab carrying it. */
export interface TutorialReplayView {
  surface: string;
  tab_id: string;
}

export interface TutorialSessionResponse {
  source_kind: TutorialSourceKind;
  source_id: string;
  tutorial_id: string;
  title: string;
  project_id: string | null;
  project_path: string | null;
  step: TutorialStepView | null;
  satisfied_step_ids: string[];
  status: "active" | "complete" | "error";
  error: string | null;
  replay: TutorialReplayView | null;
}

export interface TutorialStartRequest {
  source_kind: TutorialSourceKind;
  source_id: string;
  tutorial_id: string;
  /** FR-066 — deletes the previous tutorial project and starts fresh. */
  restart: boolean;
}

export interface TutorialProgressGroup {
  source_kind: TutorialSourceKind;
  source_id: string;
  label: string;
  completed: number;
  total: number;
}

/** FR-076 — grouped counts only; there is deliberately no aggregate. */
export interface TutorialProgressResponse {
  groups: TutorialProgressGroup[];
}

/** FR-088 — the directories a clear would delete, named before it happens. */
export interface TutorialClearPreviewResponse {
  directories: string[];
}

export interface TutorialClearResponse {
  deleted_directories: string[];
}

/** FR-079 — whether the product should volunteer the work-import offer. */
export interface TutorialUnlockResponse {
  work_import_offer_pending: boolean;
}

/**
 * HTTP 409 from `POST /sessions` means another tutorial is already running.
 *
 * Named here so the Learning Center can answer it the way the spec's edge case
 * requires — state that one tutorial runs at a time and offer to leave the
 * current one — rather than showing a raw error string.
 */
export const TUTORIAL_SESSION_CONFLICT_STATUS = 409;

export const learningCenterApi = {
  getTutorialCatalogue: () => apiFetch<TutorialCatalogueResponse>("/api/tutorials/catalogue"),

  /** Resolves to `null` when no tutorial is running. */
  getActiveTutorialSession: () =>
    apiFetch<TutorialSessionResponse | null>("/api/tutorials/sessions/active"),

  /** 409 when another session is active — see the conflict constant above. */
  startTutorialSession: (body: TutorialStartRequest) =>
    apiFetch<TutorialSessionResponse>("/api/tutorials/sessions", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),

  /**
   * FR-053 — ask the backend to re-read state no mapped event reaches.
   *
   * `file.changed` is filtered to `ADR036_FILE_ALLOWLIST`, so a condition on a
   * TIFF or a Zarr store is never event-driven; this is the path that covers it.
   */
  evaluateActiveTutorialStep: () =>
    apiFetch<TutorialSessionResponse>("/api/tutorials/sessions/active/evaluate", {
      method: "POST",
    }),

  /**
   * FR-052 — report a named user-interface event.
   *
   * The only completion path that originates in the frontend, and it exists
   * because some product actions (enlarging a panel, opening a tab) leave no
   * backend state for a condition to read.
   */
  reportTutorialUiEvent: (name: string) =>
    apiFetch<TutorialSessionResponse>("/api/tutorials/sessions/active/ui-event", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ name }),
    }),

  /** FR-012 — advance a reading step the user has finished reading. */
  continueActiveTutorialStep: () =>
    apiFetch<TutorialSessionResponse>("/api/tutorials/sessions/active/continue", {
      method: "POST",
    }),

  /** FR-090 — leave at any step; the session is preserved for later. */
  leaveActiveTutorialSession: () =>
    apiFetch<void>("/api/tutorials/sessions/active/leave", { method: "POST" }),

  getTutorialProgress: () => apiFetch<TutorialProgressResponse>("/api/tutorials/progress"),

  previewTutorialDataClear: () =>
    apiFetch<TutorialClearPreviewResponse>("/api/tutorials/data/clear-preview"),

  clearTutorialData: () =>
    apiFetch<TutorialClearResponse>("/api/tutorials/data/clear", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ confirm: true }),
    }),

  getTutorialUnlock: () => apiFetch<TutorialUnlockResponse>("/api/tutorials/unlock"),

  dismissTutorialUnlock: () => apiFetch<void>("/api/tutorials/unlock/dismiss", { method: "POST" }),
};
