/**
 * ADR-036 — file-existence probe used by "New custom block" / "New note"
 * before PUT. Audit 2026-05-14 P1 #2: those flows used to PUT directly,
 * silently overwriting any existing file. They now call this helper first
 * and refuse to create if the file already exists.
 *
 * Returns:
 *   - "exists"       — GET returned 200 → file is there, do NOT overwrite.
 *   - "missing"      — GET returned 404 → safe to create.
 *   - "unknown"      — any other error (network, 500, 415, …). Caller MUST
 *                      surface this rather than treating it as either branch.
 */
import { ApiError, api } from "./api";
import type { UserLibraryTarget } from "../types/api";

export type ExistenceProbeResult =
  | { kind: "exists" }
  | { kind: "missing" }
  | { kind: "unknown"; message: string };

/** Map a read attempt onto the three-way probe verdict. */
async function probe(read: () => Promise<unknown>): Promise<ExistenceProbeResult> {
  try {
    await read();
    return { kind: "exists" };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { kind: "missing" };
    }
    const message = error instanceof Error ? error.message : String(error);
    return { kind: "unknown", message };
  }
}

export async function probeProjectFileExistence(
  projectId: string,
  filePath: string,
): Promise<ExistenceProbeResult> {
  return probe(() => api.getProjectFile(projectId, filePath));
}

/**
 * ADR-053 FR-031 — the same probe against the user library.
 *
 * `GET /api/user-library/file` was given the project endpoint's 200/404 shape
 * on purpose (spec §4), so the destination-aware new-file flow (FR-029/FR-030)
 * needs one probe protocol rather than two: only the call differs.
 */
export async function probeUserLibraryFileExistence(
  target: UserLibraryTarget,
  filename: string,
): Promise<ExistenceProbeResult> {
  return probe(() => api.getUserLibraryFile(target, filename));
}
