/**
 * Preflight fetch + Esc-to-close effects for `RestoreDialog`.
 *
 * Replaces `useRerunValidation` (ADR-038 Addendum 1 §11.4, #2033). The shape
 * is the same, but the failure branch is not: the old hook caught every error
 * and substituted `{input_warnings: [], env_warnings: []}`, which the warnings
 * component then rendered as a green "No drift detected" banner. Since the
 * endpoint it called never existed, that path ran every single time.
 *
 * Here a failed request produces `error`, and the dialog says the check could
 * not run. A check that failed and a check that passed must never look alike.
 */
import { useEffect, useState } from "react";

import { api } from "../../../lib/api";
import type { RestorePreflight } from "../../../types/lineage";

export interface UseRestorePreflightResult {
  preflight: RestorePreflight | null;
  loading: boolean;
  /** Non-null when the preflight request itself failed. */
  error: string | null;
}

export function useRestorePreflight(
  commitSha: string,
  onClose: () => void,
): UseRestorePreflightResult {
  const [preflight, setPreflight] = useState<RestorePreflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPreflight(null);
    setError(null);
    api.lineage
      .validateRestore(commitSha)
      .then((res) => {
        if (cancelled) return;
        setPreflight(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [commitSha]);

  // Esc closes the dialog.
  useEffect(() => {
    function handleKey(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return { preflight, loading, error };
}
