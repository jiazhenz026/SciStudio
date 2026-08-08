/**
 * ADR-053 spec 2 (#2001) — client for the Bring In My Work session endpoint.
 *
 * Contract C3 (`docs/planning/adr-053-work-import-checklist.md` §7.3):
 *
 *   POST /api/work-import/sessions
 *   body: ImportSessionContext in snake_case + `project_dir` (absolute path)
 *   200:  {tab_id, title, brief_path, provider, permission_mode}
 *
 * The backend composes the brief, writes it to disk in full, and only then
 * spawns the PTY (FR-024). By the time this call resolves the session already
 * exists, so the frontend adds a terminal tab carrying the returned `tab_id`
 * and joins the pre-spawned PTY over the existing `WS /api/ai/pty/{tab_id}`
 * route — no new WS frame type is introduced.
 */
import type { PermissionMode } from "../../components/AIChat/SetupScreen.parts/types";

import { apiFetch, JSON_HEADERS } from "./core";

/** FR-011 — the two destinations the dialog offers. */
export type WorkImportDestinationTier = "project" | "user_library";

/**
 * Checklist §7.4 — the known boundary trap.
 *
 * The frontend permission-mode union is `"safe" | "dangerous"` (ADR-034,
 * `AIChat/SetupScreen.parts/types.ts`); the backend PTY spawn spells the same
 * two modes `"safe" | "bypass"`. The mapping happens here, at the request
 * boundary, exactly once — a second spelling anywhere else is how a session
 * silently launches in the wrong mode.
 */
export type BackendPermissionMode = "safe" | "bypass";

/** C2 — the three questions that may be skipped rather than answered. */
export type WorkImportSkippableQuestion =
  | "workflow_description"
  | "interaction_wishes"
  | "other_software";

/**
 * The request body: `ImportSessionContext` in snake_case plus `project_dir`.
 *
 * Field names and types mirror the frozen dataclass in contract C2 so the
 * payload deserialises without a translation layer on the backend.
 */
export interface WorkImportSessionRequest {
  /** Absolute path of the open project. The session writes blocks into it. */
  project_dir: string;
  /** FR-008 — where the user's work lives, or null in no-codebase mode. */
  source_location: string | null;
  /** FR-009 — the explicit "I don't have a codebase" path. */
  has_no_codebase: boolean;
  destination_tier: WorkImportDestinationTier;
  /** FR-013 — selected preset labels, exactly as the user saw them. */
  data_kinds: string[];
  /** FR-013 — the free-text field for anything not listed. */
  data_kinds_other: string | null;
  workflow_description: string | null;
  interaction_wishes: string | null;
  other_software: string | null;
  /**
   * FR-021 — questions the user did not answer, conveyed as skipped rather
   * than omitted, so the agent can tell "the user did not say" from "the user
   * said nothing applies".
   */
  skipped: WorkImportSkippableQuestion[];
  /** FR-044 — the provider the user chose (provider-registry key). */
  provider: string;
  /** FR-044 — the permission mode the user chose, in backend spelling. */
  permission_mode: BackendPermissionMode;
}

export interface WorkImportSessionResponse {
  tab_id: string;
  title: string;
  brief_path: string;
  provider: string;
  permission_mode: BackendPermissionMode;
}

/** Checklist §7.4 — frontend spelling → backend spelling. */
export function toBackendPermissionMode(mode: PermissionMode): BackendPermissionMode {
  return mode === "dangerous" ? "bypass" : "safe";
}

/**
 * Checklist §7.4 — backend spelling → frontend spelling.
 *
 * Used on the response so the terminal tab records the mode the backend
 * actually spawned with, rather than the one the dialog asked for.
 */
export function fromBackendPermissionMode(mode: BackendPermissionMode): PermissionMode {
  return mode === "bypass" ? "dangerous" : "safe";
}

/** C2 — the only three questions the backend accepts in `skipped`. */
export const WORK_IMPORT_SKIPPABLE_QUESTIONS: readonly WorkImportSkippableQuestion[] = [
  "workflow_description",
  "interaction_wishes",
  "other_software",
];

/**
 * The backend's validation rules for `ImportSessionContext`, restated on this
 * side of the wire (A2, #2002).
 *
 * These are not a second source of truth — the endpoint rejects a bad body
 * either way. They exist so a violation surfaces as a sentence in the dialog
 * rather than as an HTTP 422 the user cannot act on, and so a future edit to
 * the form's own rules that breaks the contract fails a unit test here instead
 * of failing at the first real session.
 *
 * Returns one message per violation; an empty array means the body is
 * acceptable to the endpoint.
 */
export function validateWorkImportRequest(request: WorkImportSessionRequest): string[] {
  const problems: string[] = [];

  if (!request.project_dir.trim()) {
    problems.push("The project path is missing.");
  }

  // FR-044 — a provider is chosen, never defaulted (ADR-034 FR-020c).
  if (!request.provider.trim()) {
    problems.push("No agent was chosen to run the session.");
  }

  // Checklist §7.4 — the backend spelling, not the frontend's.
  if (request.permission_mode !== "safe" && request.permission_mode !== "bypass") {
    problems.push(`"${String(request.permission_mode)}" is not a valid permission mode.`);
  }

  if (request.destination_tier !== "project" && request.destination_tier !== "user_library") {
    problems.push(`"${String(request.destination_tier)}" is not a valid destination.`);
  }

  /*
   * FR-008 / FR-009 — exactly one of the two, never both and never neither.
   * Both would leave the agent unsure whether to read the folder or the
   * description; neither leaves it with nothing at all to start from.
   */
  const hasSource =
    typeof request.source_location === "string" && request.source_location.trim().length > 0;
  if (hasSource && request.has_no_codebase) {
    problems.push(
      'A source location and "I don\'t have a codebase" cannot both be sent. Clear one of them.',
    );
  }
  if (!hasSource && !request.has_no_codebase) {
    problems.push('Say where your work is, or choose "I don\'t have a codebase".');
  }

  const seen = new Set<string>();
  for (const key of request.skipped as readonly string[]) {
    if (!(WORK_IMPORT_SKIPPABLE_QUESTIONS as readonly string[]).includes(key)) {
      problems.push(`"${key}" is not a question that can be skipped.`);
      continue;
    }
    if (seen.has(key)) problems.push(`"${key}" is marked as skipped more than once.`);
    seen.add(key);
  }

  /*
   * FR-021 — "skipped" and "answered" are exclusive claims about the same
   * question. A question that carries both tells the agent two different
   * things, and a blank answer that is NOT marked skipped tells it nothing at
   * all when it should be told "the user did not say".
   */
  const answers: Record<WorkImportSkippableQuestion, string | null> = {
    workflow_description: request.workflow_description,
    interaction_wishes: request.interaction_wishes,
    other_software: request.other_software,
  };
  for (const key of WORK_IMPORT_SKIPPABLE_QUESTIONS) {
    const answer = answers[key];
    const answered = typeof answer === "string" && answer.trim().length > 0;
    if (seen.has(key) && answered) {
      problems.push(`"${key}" is marked as skipped but also carries an answer.`);
    }
    if (!seen.has(key) && !answered) {
      problems.push(`"${key}" has no answer and is not marked as skipped.`);
    }
  }

  return problems;
}

/**
 * Start a work-import session (FR-022, FR-024).
 *
 * Resolves only after the backend has written the brief and spawned the PTY,
 * so the caller may attach the returned `tab_id` immediately.
 *
 * The body is validated before it leaves: this is the last point at which a
 * malformed context can be turned into a sentence rather than a 422.
 */
export async function startWorkImportSession(
  request: WorkImportSessionRequest,
): Promise<WorkImportSessionResponse> {
  const problems = validateWorkImportRequest(request);
  if (problems.length > 0) {
    throw new Error(`Cannot start the session: ${problems.join(" ")}`);
  }
  return apiFetch<WorkImportSessionResponse>("/api/work-import/sessions", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(request),
  });
}
