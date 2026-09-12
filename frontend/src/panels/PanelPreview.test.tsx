import { bootstrapFrame } from "./testUtils";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { mockBackend, reply, type MockBackend } from "../__tests__/contract/mockBackend";
import { PreviewHost } from "../components/DataPreview.parts/PreviewHost";
import type { PanelContext, PanelSnapshot } from "./types";
import type { PreviewEnvelope } from "../types/api";
vi.mock("react-plotly.js", () => ({ default: () => null }));
let backend: MockBackend;
const channels: MessagePort[] = [];
afterEach(() => {
  cleanup();
  backend?.restore();
  vi.unstubAllGlobals();
  channels.length = 0;
});
function envelope(ref: string, panel = true): PreviewEnvelope {
  return {
    session_id: `pv-${ref}`,
    target: { kind: "data_ref", ref },
    previewer_id: panel ? `lab.${ref}` : "core.text.basic",
    kind: panel ? "panel" : "text",
    ...(panel ? { panel: { id: `lab.${ref}`, api_version: "1.0" } } : {}),
    payload: panel ? {} : { content: `Text ${ref}` },
    resources: [],
    diagnostics: [],
    error: null,
    metadata: {
      sampled: false,
      truncated: false,
      cached: false,
      derived: false,
      complete: true,
      failed: false,
    },
  };
}
function install(children: Record<string, PreviewEnvelope>, resource?: PreviewEnvelope) {
  backend = mockBackend({
    "POST /api/panels/contexts": (request) => {
      const { target, preview_session_id } = request.body as {
        target: { ref: string };
        preview_session_id?: string;
      };
      if (target.ref.includes("#")) expect(preview_session_id).toBe(`pv-${target.ref}`);
      return {
        context_id: `pc-${target.ref}`,
        bootstrap_proof: "a".repeat(64),
        panel: { id: `lab.${target.ref}`, api_version: "1.0", name: target.ref },
        kind: "preview",
        operations: ["read"],
        services: ["open", "save"],
        input: { ref: target.ref, kind: "data_ref" },
        token: "token",
        expires_at: 999999,
        entry_url: "/api/panels/t/token/assets/lab.fixture/index.html",
        sdk_url: "/api/panels/t/token/sdk/1/scistudio-panel.js",
        lib_base_url: "/api/panels/t/token/lib/",
      } satisfies PanelContext;
    },
    "POST /api/panels/contexts/{context_id}/open": (request) =>
      children[(request.body as { ref: string }).ref],
    "GET /api/previews/sessions/{session_id}": (request) =>
      Object.values(children).find((env) =>
        request.path.endsWith(encodeURIComponent(env.session_id!)),
      )!,
    "GET /api/previews/sessions/{session_id}/resources/{resource_id}": {
      resource_id: "slot:part",
      data: resource ?? {},
    },
    "DELETE /api/panels/contexts/{context_id}": reply(204),
  });
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
}
async function message(port: MessagePort, type: string, payload: unknown) {
  await act(async () => {
    await port.onmessage?.({ data: { v: 1, id: type, type, payload } } as MessageEvent);
  });
}
async function mountPanel(ref: string) {
  const frame = (await screen.findByTitle(ref)) as HTMLIFrameElement;
  bootstrapFrame(frame);
  fireEvent.load(frame);
  const port = channels[channels.length - 1];
  await message(port, "ready", null);
  return { frame, port };
}
it("opens panel and legacy children through authorized sessions and restores each parent on Back", async () => {
  install({ child: envelope("child"), leaf: envelope("leaf", false) });
  const snapshot = vi.fn();
  render(
    <PreviewHost
      target={envelope("root").target}
      initialEnvelope={envelope("root")}
      onPanelSnapshot={snapshot}
    />,
  );
  const root = await mountPanel("root");
  await message(root.port, "viewState", { zoom: 4 });
  await message(root.port, "open", { ref: "child" });
  const child = await mountPanel("child");
  await message(child.port, "viewState", { page: 2 });
  await message(child.port, "open", { ref: "leaf" });
  expect(await screen.findByText("Text leaf")).toBeInTheDocument();
  expect(
    backend.callsTo("POST /api/panels/contexts/{context_id}/open").map((call) => call.body),
  ).toEqual([{ ref: "child" }, { ref: "leaf" }]);
  expect(backend.callsTo("POST /api/panels/contexts")).toHaveLength(2);
  expect(root.port.close).not.toHaveBeenCalled();
  expect(child.port.close).not.toHaveBeenCalled();
  const backButtons = screen.getAllByText("← Back");
  fireEvent.click(backButtons[backButtons.length - 1]);
  expect(screen.queryByText("Text leaf")).not.toBeInTheDocument();
  expect(snapshot).toHaveBeenLastCalledWith({
    target: { kind: "data_ref", ref: "child" },
    panelId: "lab.child",
    previewSessionId: "pv-child",
    viewState: { page: 2 },
  });
  fireEvent.click(screen.getByText("← Back"));
  expect(screen.getByTitle("root")).toBe(root.frame);
  expect(snapshot).toHaveBeenLastCalledWith({
    target: { kind: "data_ref", ref: "root" },
    panelId: "lab.root",
    previewSessionId: "pv-root",
    viewState: { zoom: 4 },
  });
  expect(child.port.close).toHaveBeenCalledOnce();
});
it("keeps Back visible when a legacy composite drills down to a panel", async () => {
  const legacy = {
    ...envelope("composite", false),
    kind: "composite" as const,
    payload: { slots: { part: "Text" } },
    resources: [{ resource_id: "slot:part", kind: "preview", params: { slot: "part" } }],
  };
  install({ composite: legacy }, envelope("part"));
  render(<PreviewHost target={envelope("root").target} initialEnvelope={envelope("root")} />);
  const root = await mountPanel("root");
  await message(root.port, "open", { ref: "composite" });
  fireEvent.click(await screen.findByTestId("composite-slot-part"));
  await mountPanel("part");
  fireEvent.click(screen.getByTestId("preview-host-back"));
  expect(screen.getByTestId("composite-slot-part")).toBeInTheDocument();
  fireEvent.click(screen.getByText("← Back"));
  expect(screen.getByTitle("root")).toBe(root.frame);
});
it.each([true, false])(
  "maximizes a composite-local child after parent disposal (panel=%s)",
  async (panel) => {
    const child = envelope("root#slot", panel);
    install({ "root#slot": child });
    let snapshot: PanelSnapshot | null = null;
    const mounted = render(
      <PreviewHost
        target={envelope("root").target}
        initialEnvelope={envelope("root")}
        onPanelSnapshot={(value) => {
          snapshot = value;
        }}
      />,
    );
    const root = await mountPanel("root");
    await message(root.port, "open", { ref: "root#slot" });
    if (panel) await mountPanel("root#slot");
    else await screen.findByText("Text root#slot");
    await waitFor(() => expect(snapshot?.previewSessionId).toBe("pv-root#slot"));
    mounted.unmount();
    await waitFor(() =>
      expect(backend.callsTo("DELETE /api/panels/contexts/{context_id}").length).toBeGreaterThan(0),
    );
    const frozen = snapshot! as PanelSnapshot;
    render(
      <PreviewHost
        target={frozen.target}
        previewSessionId={frozen.previewSessionId}
        panelId={frozen.panelId}
        initialViewState={frozen.viewState}
      />,
    );
    if (panel) await mountPanel("root#slot");
    else await screen.findByText("Text root#slot");
    expect(backend.callsTo("GET /api/previews/sessions/{session_id}")).toHaveLength(1);
    expect(backend.callsTo("POST /api/panels/contexts/{context_id}/open")).toHaveLength(1);
  },
);
