import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../lib/api";
import type { DataPreviewResponse } from "../../types/api";

/**
 * Hook bundle: per-active-ref slice index + slice cache + debounced fetch.
 *
 * #899 — slice 0 falls through to the parent ``previewCache`` so existing
 * behavior is unchanged. Slice > 0 fetches go through a local cache with a
 * 200 ms debounce; the last drag position wins. Slice cache is keyed by
 * ``${ref}#${slice}`` and never evicted across the component lifetime —
 * activeRef changes do not clear it so flipping between refs preserves
 * already-fetched slices.
 *
 * Returns:
 *   - activeRef / setActiveRef
 *   - activeSlice (current slice index for activeRef; defaults to 0)
 *   - handleSliceChange (called by ImageViewer's slider)
 *   - preview (resolved DataPreviewResponse | null with stale-fallback)
 *   - hasAnyPreviewForRef
 *   - isLoadingActive
 */
export function useSlicePreview({
  outputRefs,
  previewCache,
  previewLoading,
  onLoadPreview,
}: {
  outputRefs: string[];
  previewCache: Record<string, DataPreviewResponse>;
  previewLoading: Record<string, boolean>;
  onLoadPreview: (dataRef: string) => Promise<void>;
}): {
  activeRef: string | null;
  setActiveRef: (ref: string | null) => void;
  activeSlice: number;
  handleSliceChange: (idx: number) => void;
  preview: DataPreviewResponse | null;
  hasAnyPreviewForRef: boolean;
  isLoadingActive: boolean;
} {
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const [currentSliceByRef, setCurrentSliceByRef] = useState<Record<string, number>>({});
  // Local cache for non-zero slice variants. Slice 0 falls through to the
  // store's ``previewCache`` so existing behavior is unchanged.
  const sliceCacheRef = useRef<Map<string, DataPreviewResponse>>(new Map());
  const [sliceCacheVersion, setSliceCacheVersion] = useState(0);
  const sliceFetchingRef = useRef<Set<string>>(new Set());

  const activeSlice = activeRef ? (currentSliceByRef[activeRef] ?? 0) : 0;
  const activeSliceKey = activeRef ? `${activeRef}#${activeSlice}` : null;

  useEffect(() => {
    setActiveRef(outputRefs[0] ?? null);
  }, [outputRefs]);

  // Slice 0 fetch through the store (preserves existing flow).
  useEffect(() => {
    if (activeRef && activeSlice === 0 && !previewCache[activeRef] && !previewLoading[activeRef]) {
      void onLoadPreview(activeRef);
    }
  }, [activeRef, activeSlice, onLoadPreview, previewCache, previewLoading]);

  // #899 — slice > 0 fetch with 200 ms debounce. Cache hit → instant (no
  // timer). Cache miss → debounced fetch, last drag position wins.
  useEffect(() => {
    if (!activeRef || activeSlice === 0 || !activeSliceKey) return undefined;
    if (sliceCacheRef.current.has(activeSliceKey)) return undefined;
    if (sliceFetchingRef.current.has(activeSliceKey)) return undefined;
    const timer = window.setTimeout(() => {
      sliceFetchingRef.current.add(activeSliceKey);
      void api
        .getDataPreview(activeRef, activeSlice)
        .then((resp) => {
          sliceCacheRef.current.set(activeSliceKey, resp);
          setSliceCacheVersion((v) => v + 1);
        })
        .catch((err) => {
          console.warn(`getDataPreview(${activeRef}, slice=${activeSlice}) failed:`, err);
        })
        .finally(() => {
          sliceFetchingRef.current.delete(activeSliceKey);
        });
    }, 200);
    return () => window.clearTimeout(timer);
  }, [activeRef, activeSlice, activeSliceKey]);

  // Reset slice cache when activeRef changes — avoid stale entries piling up.
  useEffect(() => {
    if (!activeRef) return;
    setCurrentSliceByRef((prev) => (activeRef in prev ? prev : { ...prev, [activeRef]: 0 }));
  }, [activeRef]);

  const handleSliceChange = useCallback(
    (idx: number) => {
      if (!activeRef) return;
      setCurrentSliceByRef((cs) => ({ ...cs, [activeRef]: idx }));
    },
    [activeRef],
  );

  // Resolve the preview payload to render based on (activeRef, activeSlice).
  //
  // #899 — when the requested slice is still loading, fall back to ANY
  // cached preview for this ref (slice 0 or the most recently-loaded
  // slice). This keeps ``<ImageViewer>`` mounted across slice
  // transitions, preserving its zoom/pan/LUT state. Without the
  // fallback, the transient null between slider drag and fetch
  // completion unmounts the component and resets all its useState.
  const preview: DataPreviewResponse | null = useMemo(() => {
    if (!activeRef) return null;
    // Try the exact slice the user is requesting.
    if (activeSlice === 0) {
      const slice0 = previewCache[activeRef];
      if (slice0) return slice0;
    } else if (activeSliceKey) {
      const sliceN = sliceCacheRef.current.get(activeSliceKey);
      if (sliceN) return sliceN;
    }
    // Stale-fallback: anything we have for this ref keeps the viewer alive.
    if (previewCache[activeRef]) return previewCache[activeRef];
    for (const [key, value] of sliceCacheRef.current.entries()) {
      if (key.startsWith(`${activeRef}#`)) return value;
    }
    return null;
    // sliceCacheVersion is intentionally listed to invalidate the memo
    // whenever a new slice lands in the local cache.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRef, activeSlice, activeSliceKey, previewCache, sliceCacheVersion]);

  // Has any preview at all loaded for the current ref? Used to decide
  // between the "Preview not loaded yet" placeholder and the viewer.
  const hasAnyPreviewForRef = preview !== null;

  const isLoadingActive =
    !!activeRef &&
    !hasAnyPreviewForRef &&
    (activeSlice === 0
      ? !!previewLoading[activeRef]
      : !!activeSliceKey && sliceFetchingRef.current.has(activeSliceKey));

  return {
    activeRef,
    setActiveRef,
    activeSlice,
    handleSliceChange,
    preview,
    hasAnyPreviewForRef,
    isLoadingActive,
  };
}
