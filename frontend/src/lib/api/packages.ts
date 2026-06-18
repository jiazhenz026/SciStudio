/**
 * Desktop/local package installation endpoints.
 */

import type { LocalPackageInstallResponse } from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const packagesApi = {
  installLocalPackage: (path: string) =>
    apiFetch<LocalPackageInstallResponse>("/api/packages/local", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ path }),
    }),
};
