/** Unit-test entry bootstrap; production entry injection is backend-owned. */
import { vi } from "vitest";
export const BOOTSTRAP_PROOF = "a".repeat(64);
export function bootstrapFrame(iframe: HTMLIFrameElement, proof = BOOTSTRAP_PROOF) {
  const port = { postMessage: vi.fn(), close: vi.fn(), start: vi.fn() } as unknown as MessagePort;
  window.dispatchEvent(
    new MessageEvent("message", {
      source: iframe.contentWindow,
      data: { v: 1, id: "bootstrap", type: "bootstrap", proof },
      ports: [port],
    }),
  );
  return port;
}
