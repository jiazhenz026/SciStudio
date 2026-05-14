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

export type ExistenceProbeResult =
  | { kind: "exists" }
  | { kind: "missing" }
  | { kind: "unknown"; message: string };

export async function probeProjectFileExistence(
  projectId: string,
  filePath: string,
): Promise<ExistenceProbeResult> {
  try {
    await api.getProjectFile(projectId, filePath);
    return { kind: "exists" };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { kind: "missing" };
    }
    const message = error instanceof Error ? error.message : String(error);
    return { kind: "unknown", message };
  }
}
