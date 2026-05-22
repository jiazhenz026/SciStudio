import { useCallback, useEffect, useMemo, useState } from "react";

import { extractOMEFromMetadata, getOMEMetadata, type OMETree } from "../../api/capabilities";
import { hasOMEContent } from "../OutputPreview/OMEMetadataPanel";
import type { DataPreviewResponse } from "../../types/api";

/**
 * ADR-043 FR-013 — OME metadata panel toggle.
 *
 * First try the cached preview's metadata (the preview endpoint already
 * returns `metadata` alongside `preview`). When absent, fall back to a
 * lazy `/api/data/{ref}` fetch the first time the user clicks the
 * "OME metadata" button.
 */
export function useOmeMetadata({
  activeRef,
  preview,
}: {
  activeRef: string | null;
  preview: DataPreviewResponse | null;
}): {
  omeOpen: boolean;
  setOmeOpen: (open: boolean) => void;
  activeOme: OMETree | null;
  omeAvailable: boolean;
  handleOpenOme: () => void;
} {
  const previewMetadata = useMemo<Record<string, unknown> | null>(() => {
    if (!preview) return null;
    const md = (preview as unknown as { metadata?: Record<string, unknown> }).metadata;
    return md && typeof md === "object" ? md : null;
  }, [preview]);
  const previewOme = useMemo<OMETree | null>(
    () => extractOMEFromMetadata(previewMetadata),
    [previewMetadata],
  );
  const [omeOpen, setOmeOpen] = useState(false);
  const [fetchedOmeByRef, setFetchedOmeByRef] = useState<Record<string, OMETree | null>>({});
  const [omeFetching, setOmeFetching] = useState<Record<string, boolean>>({});
  const activeFetchedOme = activeRef ? (fetchedOmeByRef[activeRef] ?? null) : null;
  const activeOme = previewOme ?? activeFetchedOme;
  const omeAvailable =
    hasOMEContent(activeOme) || (!previewOme && activeRef !== null && activeRef !== undefined);
  // Reset the open state when the active ref changes.
  useEffect(() => {
    setOmeOpen(false);
  }, [activeRef]);

  const handleOpenOme = useCallback(() => {
    setOmeOpen(true);
    if (!activeRef || previewOme) return;
    if (fetchedOmeByRef[activeRef] !== undefined) return;
    if (omeFetching[activeRef]) return;
    setOmeFetching((prev) => ({ ...prev, [activeRef]: true }));
    getOMEMetadata(activeRef)
      .then((ome) => {
        setFetchedOmeByRef((prev) => ({ ...prev, [activeRef]: ome }));
      })
      .catch(() => {
        setFetchedOmeByRef((prev) => ({ ...prev, [activeRef]: null }));
      })
      .finally(() => {
        setOmeFetching((prev) => ({ ...prev, [activeRef]: false }));
      });
  }, [activeRef, previewOme, fetchedOmeByRef, omeFetching]);

  return { omeOpen, setOmeOpen, activeOme, omeAvailable, handleOpenOme };
}
