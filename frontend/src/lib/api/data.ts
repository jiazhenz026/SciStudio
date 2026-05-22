/**
 * Data-artifact REST endpoints (uploads, metadata, preview slices).
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 */

import type {
  DataMetadataResponse,
  DataPreviewQuery,
  DataPreviewResponse,
  DataUploadResponse,
} from "../../types/api";
import { apiFetch } from "./core";

export const dataApi = {
  uploadData: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<DataUploadResponse>("/api/data/upload", {
      method: "POST",
      body: formData,
    });
  },
  getDataMetadata: (dataRef: string) =>
    apiFetch<DataMetadataResponse>(`/api/data/${encodeURIComponent(dataRef)}`),
  getDataPreview: (dataRef: string, opts?: number | DataPreviewQuery) => {
    // Backwards-compat: a bare number is interpreted as ``slice`` (image flow).
    // Object form covers slice + DataFrame paging (page/page_size/sort_by/sort_dir).
    const o: DataPreviewQuery = typeof opts === "number" ? { slice: opts } : (opts ?? {});
    const params = new URLSearchParams();
    if (o.slice !== undefined) params.set("slice", String(o.slice));
    if (o.page !== undefined) params.set("page", String(o.page));
    if (o.pageSize !== undefined) params.set("page_size", String(o.pageSize));
    if (o.sortBy) params.set("sort_by", o.sortBy);
    if (o.sortDir) params.set("sort_dir", o.sortDir);
    const qs = params.toString();
    const url = `/api/data/${encodeURIComponent(dataRef)}/preview${qs ? `?${qs}` : ""}`;
    return apiFetch<DataPreviewResponse>(url);
  },
};
