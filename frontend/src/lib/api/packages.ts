/**
 * Desktop/local package installation and Package Manager endpoints (#1784).
 */

import type {
  InstalledPackagesResponse,
  LocalPackageInstallResponse,
  PackageActionResponse,
  PackageUpdatesResponse,
} from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const packagesApi = {
  installLocalPackage: (path: string) =>
    apiFetch<LocalPackageInstallResponse>("/api/packages/local", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ path }),
    }),

  listInstalledPackages: () => apiFetch<InstalledPackagesResponse>("/api/packages/installed"),

  checkPackageUpdates: () => apiFetch<PackageUpdatesResponse>("/api/packages/updates"),

  updatePackage: (packageName: string) =>
    apiFetch<PackageActionResponse>(`/api/packages/${encodeURIComponent(packageName)}/update`, {
      method: "POST",
    }),

  rollbackPackage: (packageName: string) =>
    apiFetch<PackageActionResponse>(`/api/packages/${encodeURIComponent(packageName)}/rollback`, {
      method: "POST",
    }),

  deletePackage: (packageName: string) =>
    apiFetch<PackageActionResponse>(`/api/packages/${encodeURIComponent(packageName)}`, {
      method: "DELETE",
    }),
};
