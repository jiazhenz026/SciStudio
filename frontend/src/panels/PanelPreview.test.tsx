import { bootstrapFrame } from "./testUtils";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { mockBackend, reply, type MockBackend } from "../__tests__/contract/mockBackend";
import { PanelPreview } from "./PanelPreview";
import type { PanelContext } from "./types";
let backend: MockBackend;
afterEach(() => {
  cleanup();
  backend?.restore();
  vi.unstubAllGlobals();
});
it("keeps independent parent/child mounts and restores the parent's view state on Back", async () => {
  let count = 0;
  backend = mockBackend({
    "POST /api/panels/contexts": (request) => {
      const target = (request.body as { target: { ref: string } }).target;
      return {
        context_id: `pc-${++count}`,
        bootstrap_proof: "a".repeat(64),
        panel: { id: `lab.${target.ref}`, api_version: "1.0", name: target.ref },
        kind: "preview",
        operations: ["read"],
        services: ["open", "save"],
        input: { ref: target.ref, kind: "data_ref" },
        token: "token",
        expires_at: 999999,
        entry_url: `/api/panels/t/token/assets/lab.${target.ref}/index.html`,
        sdk_url: "/api/panels/t/token/sdk/1/scistudio-panel.js",
        lib_base_url: "/api/panels/t/token/lib/",
      } satisfies PanelContext;
    },
    "DELETE /api/panels/contexts/{context_id}": reply(204),
  });
  const channels: MessagePort[] = [];
  vi.stubGlobal(
    "MessageChannel",
    class {
      port1 = {
        onmessage: null,
        postMessage: vi.fn(),
        start: vi.fn(),
        close: vi.fn(),
      } as unknown as MessagePort;
      port2 = {};
      constructor() {
        channels.push(this.port1);
      }
    },
  );
  const snapshot = vi.fn();
  render(
    <PanelPreview
      target={{ kind: "data_ref", ref: "root" }}
      panelId="lab.root"
      onSnapshot={snapshot}
      onFallback={vi.fn()}
    />,
  );
  const root = await screen.findByTitle("root");
  bootstrapFrame(root as HTMLIFrameElement);
  fireEvent.load(root);
  const message = async (port: MessagePort, type: string, payload: unknown) => {
    await act(async () => {
      await port.onmessage?.({ data: { v: 1, id: type, type, payload } } as MessageEvent);
    });
  };
  await message(channels[0], "ready", null);
  await message(channels[0], "viewState", { zoom: 4 });
  await message(channels[0], "open", { ref: "child" });
  const child = await screen.findByTitle("child");
  bootstrapFrame(child as HTMLIFrameElement);
  fireEvent.load(child);
  expect(screen.getByTitle("root")).toBe(root);
  expect(channels[0].close).not.toHaveBeenCalled();
  expect(backend.callsTo("POST /api/panels/contexts")[1].body).toMatchObject({
    parent_context_id: "pc-1",
    bootstrap_proof: "a".repeat(64),
    target: { ref: "child" },
  });
  fireEvent.click(screen.getByText("← Back"));
  await waitFor(() => expect(screen.queryByTitle("child")).not.toBeInTheDocument());
  expect(snapshot).toHaveBeenLastCalledWith({
    target: { kind: "data_ref", ref: "root" },
    panelId: "lab.root",
    viewState: { zoom: 4 },
  });
  expect(channels[1].close).toHaveBeenCalledOnce();
});
