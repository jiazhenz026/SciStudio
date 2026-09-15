import { useAppStore } from "../store";
import { isRecord } from "./types";

/** Capability advertisement is sent again after every project switch. */
export function guiDebugHello(): Record<string, unknown> {
  return {
    type: "gui.debug.hello",
    project: useAppStore.getState().currentProject?.path ?? null,
    screenshot: typeof window.scistudioDesktop?.captureGui === "function",
  };
}

class GuiTargetError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

function captureTarget(request: Record<string, unknown>) {
  if (request.target === "workspace") {
    return {
      rect: { x: 0, y: 0, width: window.innerWidth, height: window.innerHeight },
      state: "visible",
    };
  }
  if (request.target !== "miniapp")
    throw new GuiTargetError("invalid_target", "Choose workspace or miniapp.");
  const candidates = [...document.querySelectorAll<HTMLElement>("[data-gui-miniapp]")].filter(
    (node) =>
      (!request.panel_id || node.dataset.panelId === request.panel_id) &&
      (!request.context_id || node.dataset.contextId === request.context_id),
  );
  const visible = candidates.filter((node) => {
    const box = node.getBoundingClientRect();
    return (
      box.width > 0 &&
      box.height > 0 &&
      box.bottom > 0 &&
      box.right > 0 &&
      box.top < window.innerHeight &&
      box.left < window.innerWidth
    );
  });
  if (visible.length !== 1)
    throw new GuiTargetError(
      visible.length ? "ambiguous_target" : "target_not_visible",
      visible.length
        ? "Several MiniApps match; specify context_id."
        : "The requested MiniApp is not visible. Open its tab before capturing.",
    );
  const node = visible[0];
  const box = node.getBoundingClientRect();
  const x = Math.max(0, Math.ceil(box.left));
  const y = Math.max(0, Math.ceil(box.top));
  return {
    rect: {
      x,
      y,
      width: Math.floor(Math.min(window.innerWidth, box.right)) - x,
      height: Math.floor(Math.min(window.innerHeight, box.bottom)) - y,
    },
    panel_id: node.dataset.panelId,
    context_id: node.dataset.contextId || null,
    state: node.querySelector("[role=alert]")
      ? "error"
      : node.querySelector("[data-panel-ready=true]")
        ? "ready"
        : "loading",
    process_state: node.dataset.processState || "absent",
    errors: [...node.querySelectorAll("[role=alert]")]
      .slice(0, 10)
      .map((alert) => alert.textContent?.slice(0, 2000)),
  };
}

/** Read-only screenshot request. No tab focus, process start, or DOM mutation. */
export async function handleGuiDebugRequest(
  payload: unknown,
  reply: (message: Record<string, unknown>) => void,
): Promise<void> {
  if (
    !isRecord(payload) ||
    payload.type !== "gui.debug.request" ||
    typeof payload.request_id !== "string"
  )
    return;
  const envelope = {
    type: "gui.debug.response",
    request_id: payload.request_id,
    project: payload.project,
  };
  const projectInstance = useAppStore.getState().currentProject;
  const currentProject = () =>
    useAppStore.getState().currentProject === projectInstance ? projectInstance?.path : undefined;
  let changed = false;
  const invalidate = () => {
    changed = true;
  };
  const stopWatching = useAppStore.subscribe((state, previous) => {
    if (
      state.currentProject !== previous.currentProject ||
      state.activeTabId !== previous.activeTabId
    )
      invalidate();
  });
  window.addEventListener("resize", invalidate);
  try {
    if (payload.project !== currentProject())
      throw new GuiTargetError("project_changed", "This GUI is showing another project.");
    if (payload.action !== "screenshot")
      throw new GuiTargetError("unsupported", "Unsupported GUI debug action.");
    const capture = window.scistudioDesktop?.captureGui;
    if (!capture)
      throw new GuiTargetError("unsupported_gui", "This GUI has no desktop screenshot bridge.");
    const delay =
      typeof payload.wait_ms === "number" ? Math.max(0, Math.min(5000, payload.wait_ms)) : 0;
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    if (payload.project !== currentProject())
      throw new GuiTargetError("project_changed", "Project changed before capture.");
    const target = captureTarget(payload);
    const image = await capture({ rect: target.rect });
    // Never return pixels captured across a project/tab switch.
    if (
      changed ||
      payload.project !== currentProject() ||
      JSON.stringify(captureTarget(payload)) !== JSON.stringify(target)
    ) {
      throw new GuiTargetError("gui_changed", "GUI target changed during capture; retry.");
    }
    reply({ ...envelope, ...target, target: payload.target, ...image });
  } catch (error) {
    reply({
      ...envelope,
      error: {
        code: error instanceof GuiTargetError ? error.code : "capture_failed",
        message: error instanceof Error ? error.message : String(error),
      },
    });
  } finally {
    stopWatching();
    window.removeEventListener("resize", invalidate);
  }
}
