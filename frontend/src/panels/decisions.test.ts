import { afterEach, expect, it, vi } from "vitest";
import { dispatchWorkflowEvent } from "../hooks/useWebSocket.parts/dispatchEvent";
import { submitPanelDecision } from "./decisions";
const identity = { context_id: "pc-1", workflow_id: "wf-1", block_id: "b-1" };
const deps = { appendLog: vi.fn(), setWorkflow: vi.fn(), upsertInteractivePrompt: vi.fn() };
const dispatch = (patch: Record<string, unknown>) =>
  dispatchWorkflowEvent(
    {
      type: "panel_accepted",
      data: {},
      timestamp: "",
      ...identity,
      ...patch,
    },
    deps,
  );
afterEach(() => vi.useRealTimers());
it("requires matching context, workflow and block before settling", async () => {
  const settled = vi.fn();
  const sent = vi.fn();
  const promise = submitPanelDecision(identity, sent).then(settled);
  expect(sent).toHaveBeenCalledOnce();
  dispatch({ context_id: "other" });
  dispatch({ workflow_id: "other" });
  dispatch({ block_id: "other" });
  await Promise.resolve();
  expect(settled).not.toHaveBeenCalled();
  expect(dispatch({})).toBe(true);
  await promise;
  expect(settled).toHaveBeenCalledOnce();
});
it("surfaces a rejected decision and releases the pending acknowledgement", async () => {
  const promise = submitPanelDecision(identity, vi.fn());
  const rejected = expect(promise).rejects.toMatchObject({
    code: "stale_context",
    message: "Remount",
  });
  dispatch({ type: "panel_error", error: { code: "stale_context", message: "Remount" } });
  await rejected;
});
it("times out without treating the decision as accepted", async () => {
  vi.useFakeTimers();
  const promise = submitPanelDecision(identity, vi.fn());
  const rejected = expect(promise).rejects.toMatchObject({ code: "timeout" });
  await vi.advanceTimersByTimeAsync(30000);
  await rejected;
});
it("aborts a pending decision on unmount", async () => {
  const controller = new AbortController();
  const promise = submitPanelDecision(identity, vi.fn(), controller.signal);
  const rejected = expect(promise).rejects.toMatchObject({ name: "AbortError" });
  controller.abort();
  await rejected;
  dispatch({});
});
