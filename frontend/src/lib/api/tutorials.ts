/**
 * Onboarding tutorial endpoints.
 */

import type {
  RunFirstWorkflowBootstrapRequest,
  RunFirstWorkflowBootstrapResponse,
} from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const tutorialsApi = {
  bootstrapRunFirstWorkflowTutorial: (body: RunFirstWorkflowBootstrapRequest = {}) =>
    apiFetch<RunFirstWorkflowBootstrapResponse>("/api/tutorials/run-first-workflow/bootstrap", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
};
