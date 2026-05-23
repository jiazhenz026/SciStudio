/**
 * Run validation + Esc-to-close effects for RerunDialog. Extracted in #1413.
 */
import { useEffect, useState } from "react";

import { api } from "../../../lib/api";
import { useAppStore } from "../../../store";
import type { LineageRerunValidation } from "../../../types/lineage";

export interface UseRerunValidationResult {
  validation: LineageRerunValidation | null;
  validationLoading: boolean;
  detailLoading: boolean;
}

export function useRerunValidation(runId: string, onClose: () => void): UseRerunValidationResult {
  const detail = useAppStore((s) => s.runDetails[runId]);
  const detailLoading = useAppStore((s) => s.runDetailLoading[runId] ?? false);
  const fetchRunDetail = useAppStore((s) => s.fetchRunDetail);
  const [validation, setValidation] = useState<LineageRerunValidation | null>(null);
  const [validationLoading, setValidationLoading] = useState(true);

  // Defensive: if the dialog opens via deep-link with no detail cached, populate it.
  useEffect(() => {
    if (detail === undefined && !detailLoading) {
      void fetchRunDetail(runId);
    }
  }, [detail, detailLoading, fetchRunDetail, runId]);

  // Kick off the validation request.
  useEffect(() => {
    let cancelled = false;
    setValidationLoading(true);
    setValidation(null);
    api.lineage
      .validateRerun(runId)
      .then((res) => {
        if (cancelled) return;
        setValidation(res);
        setValidationLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        // Validation is advisory; failure should not block the user.
        setValidation({ input_warnings: [], env_warnings: [] });
        setValidationLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

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

  return { validation, validationLoading, detailLoading };
}
