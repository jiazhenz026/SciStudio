import type { PanelContext, PanelMessage, PanelTheme } from "./types";
import { isJsonSafe, isRecord, PanelError } from "./types";
import { ApiError } from "../lib/api/core";

export interface PanelBridgeHandlers {
  read: (ref: string, op: string, params: Record<string, unknown>) => Promise<unknown>;
  open: (ref: string) => Promise<unknown>;
  writeBack: (response: Record<string, unknown>) => Promise<unknown>;
  save: (payload: unknown) => Promise<unknown>;
  viewState: (state: unknown) => void;
  resize: (height: number) => void;
  ready: () => void;
  failure: (message: string) => void;
}
const READ_OPS = new Set(["metadata", "table.page", "table.xy", "array.plane", "array.tile", "series.points", "text.chunk", "artifact.info", "artifact.file", "composite.slots", "collection.items"]);

/** A single mount has a single port. No window message listener is installed. */
export function createPanelBridge(port: MessagePort, context: PanelContext, handlers: PanelBridgeHandlers) {
  let disposed = false;
  let ready = false;
  let decisionUsed = false;
  const pending = new Set<string>();
  const send = (message: PanelMessage, transfer: Transferable[] = []) => {
    if (!disposed) port.postMessage(message, transfer);
  };
  const dispatch = async (type: string, payload: unknown) => {
    if (type === "ready") { if (!ready) { ready = true; handlers.ready(); } return null; }
    if (type === "reportError") {
      if (typeof payload !== "string") throw new PanelError("invalid_request", "Expected an error message");
      handlers.failure(payload); return null;
    }
    if (!ready) throw new PanelError("not_ready", "Call ready() before panel operations");
    if (type === "viewState") {
      if (!isJsonSafe(payload)) throw new PanelError("invalid_request", "View state must be JSON-safe");
      handlers.viewState(payload); return null;
    }
    if (type === "resize") {
      if (!isRecord(payload) || typeof payload.height !== "number" || !Number.isFinite(payload.height)) throw new PanelError("invalid_request", "Invalid height");
      handlers.resize(Math.max(120, Math.min(4096, payload.height))); return null;
    }
    if (type === "save" && context.services.includes("save")) return handlers.save(payload);
    if (type === "read" && context.kind === "preview" && context.operations.includes("read")) {
      if (!isRecord(payload) || typeof payload.op !== "string" || !READ_OPS.has(payload.op) || !isRecord(payload.params)) throw new PanelError("invalid_request", "Unknown read operation or invalid parameters");
      const ref = payload.ref ?? context.input.ref;
      if (typeof ref !== "string") throw new PanelError("invalid_request", "Read requires a reference");
      return handlers.read(ref, payload.op, payload.params);
    }
    if (type === "open" && context.kind === "preview" && context.services.includes("open")) {
      if (!isRecord(payload) || typeof payload.ref !== "string") throw new PanelError("invalid_request", "Open requires a child reference");
      return handlers.open(payload.ref); // Backend validates parent-child reachability.
    }
    if (type === "writeBack" && context.kind === "interactive" && context.operations.includes("writeBack")) {
      if (decisionUsed) throw new PanelError("already_used", "This decision was already submitted");
      if (!isRecord(payload) || !isJsonSafe(payload)) throw new PanelError("invalid_request", "Decision must be a JSON-safe object");
      decisionUsed = true;
      return handlers.writeBack(payload);
    }
    throw new PanelError("unsupported", `Operation ${type} is unavailable in ${context.kind}`);
  };
  port.onmessage = async (event: MessageEvent<unknown>) => {
    const message = event.data;
    if (disposed || !isRecord(message) || message.v !== 1 || typeof message.id !== "string" || message.id.length > 128 || typeof message.type !== "string") return;
    const { id, type, payload } = message;
    if (pending.has(id)) return;
    if (pending.size >= 64) { send({ v: 1, id, type: "error", payload: { code: "busy", message: "Too many pending panel requests" } }); return; }
    pending.add(id);
    try {
      const result = await dispatch(type, payload);
      const buffers: Transferable[] = [];
      if (isRecord(result) && result.data instanceof ArrayBuffer) buffers.push(result.data);
      send({ v: 1, id, type: "result", payload: result }, buffers);
    } catch (error) {
      const code = error instanceof PanelError ? error.code : error instanceof ApiError && error.status === 403 ? "forbidden" : "operation_failed";
      send({ v: 1, id, type: "error", payload: { code, message: error instanceof Error ? error.message : String(error) } });
    } finally { pending.delete(id); }
  };
  port.onmessageerror = () => handlers.failure("Panel sent an unreadable message");
  port.start();
  return {
    theme: (theme: PanelTheme) => send({ v: 1, id: "theme", type: "theme", payload: theme }),
    dispose() {
      if (disposed) return;
      send({ v: 1, id: "dispose", type: "dispose", payload: null });
      disposed = true;
      port.onmessage = null;
      port.onmessageerror = null;
      port.close();
      pending.clear();
    },
  };
}
