/**
 * ADR-055 Spec 4 — the requests and navigations behind the capability-gated
 * enterprise controls (`docs/specs/adr-055-enterprise-support.md`, #2322).
 *
 * Every capability URL is a backend route path without the service prefix.
 * `apiFetch` and `apiUrl` resolve it under the prefix exactly as they resolve
 * any API call, so the same code works at the root mount and under
 * `/user/<name>/scistudio`. This module implements no enterprise route; it
 * only calls the ones a capability names.
 */

import { apiUrl } from "../../lib/api/base-path";
import { apiFetch } from "../../lib/api/core";
import { downloadRoutePath, type TransferCapability } from "../../lib/capabilities";

/** How long a capability request may take before the control gives up. */
const REQUEST_TIMEOUT_MS = 15_000;

/** What `GET status_url` answers, read into frontend casing. */
export interface UpdateStatus {
  readonly runningVersion: string;
  readonly installedVersion: string;
  readonly updateAvailable: boolean;
  readonly runsActive: boolean;
}

/**
 * The one place the enterprise controls leave the page. Tests replace
 * `assign`, because jsdom does not implement navigation.
 */
export const browserNavigation = {
  assign(url: string): void {
    window.location.assign(url);
  },
};

function asRecord(raw: unknown): Record<string, unknown> | null {
  return typeof raw === "object" && raw !== null && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : null;
}

/**
 * The `location` a logout or restart route returned, when it is safe to
 * follow: an `http(s)` URL, absolute or relative to this page. Anything else,
 * a `javascript:` URL included, is refused.
 */
export function safeLocation(raw: unknown): string | null {
  if (typeof raw !== "string" || raw.trim() === "") return null;
  let resolved: URL;
  try {
    resolved = new URL(raw, window.location.href);
  } catch {
    return null;
  }
  return resolved.protocol === "http:" || resolved.protocol === "https:" ? resolved.href : null;
}

/**
 * Send a same-origin `POST` to a capability route and return the location its
 * `{location}` answer names. Used for logout and restart: the route does the
 * work, and the browser then goes where it says.
 */
export async function postForLocation(routePath: string): Promise<string> {
  const body = await apiFetch<unknown>(routePath, {
    method: "POST",
    credentials: "same-origin",
    timeoutMs: REQUEST_TIMEOUT_MS,
  });
  const location = safeLocation(asRecord(body)?.location);
  if (location === null) {
    throw new Error("SciStudio did not say where to go next. Try again, or reload the page.");
  }
  return location;
}

/** Read `GET status_url`; `null` when the answer is not the contract's shape. */
export async function fetchUpdateStatus(statusUrl: string): Promise<UpdateStatus | null> {
  const record = asRecord(await apiFetch<unknown>(statusUrl, { timeoutMs: REQUEST_TIMEOUT_MS }));
  if (record === null) return null;
  const {
    running_version: runningVersion,
    installed_version: installedVersion,
    update_available: updateAvailable,
    runs_active: runsActive,
  } = record;
  if (typeof runningVersion !== "string" || typeof installedVersion !== "string") return null;
  if (typeof updateAvailable !== "boolean" || typeof runsActive !== "boolean") return null;
  return { runningVersion, installedVersion, updateAvailable, runsActive };
}

/** The browser URL that downloads one project file, under the service prefix. */
export function buildDownloadUrl(transfer: TransferCapability, relativePath: string): string {
  return apiUrl(downloadRoutePath(transfer, relativePath));
}

/**
 * Send the browser to a download URL without leaving the page: an anchor with
 * a `download` attribute saves the response instead of navigating to it, so a
 * refused download never replaces the workbench with an error body.
 */
export function triggerDownload(url: string, filename: string): void {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
  }
}

/** A readable message for a failed control action. */
export function errorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "Something went wrong.";
}
