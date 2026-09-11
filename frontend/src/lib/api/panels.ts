/** Guarded host operations. Static tokens are never sent as operation credentials. */
import { apiFetch, JSON_HEADERS } from "./core";
import type { PanelContext, PanelCreateRequest } from "../../panels/types";
import { PanelError } from "../../panels/types";

const contextPath = (id: string) => `/api/panels/contexts/${encodeURIComponent(id)}`;
export const panelsApi = {
  create: (request: PanelCreateRequest) => apiFetch<PanelContext>("/api/panels/contexts", {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify(request), timeoutMs: 15000,
  }),
  close: (id: string) => apiFetch<void>(contextPath(id), { method: "DELETE", keepalive: true }),
  renew: (id: string) => apiFetch<PanelContext>(`${contextPath(id)}/renew`, {
    method: "POST", headers: JSON_HEADERS, body: "{}", timeoutMs: 15000,
  }),
  async read(id: string, ref: string, op: string, params: Record<string, unknown>) {
    // JSON requests use the shared mutation/auth seam. Binary uses the same
    // guarded route and prefix source, with no static token in its credentials.
    if (params.format !== "binary") return apiFetch<Record<string, unknown>>(`${contextPath(id)}/read`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ ref, op, params }), timeoutMs: 30000,
    });
    const response = await apiFetch<Response>(`${contextPath(id)}/read`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ ref, op, params }), responseType: "response", timeoutMs: 30000,
    });
    if (!response.headers.get("Content-Type")?.startsWith("application/octet-stream")) {
      throw new PanelError("invalid_response", "Expected a binary panel response");
    }
    return {
      ...JSON.parse(response.headers.get("X-Panel-Metadata") ?? "{}"),
      dtype: response.headers.get("X-Panel-Dtype"),
      shape: JSON.parse(response.headers.get("X-Panel-Shape") ?? "[]"),
      data: await response.arrayBuffer(),
    };
  },
};
