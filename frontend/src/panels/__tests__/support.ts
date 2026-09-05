/**
 * Shared test support for the panel host suites.
 *
 * **What is real and what is substituted.** jsdom parses an `iframe` and gives
 * it a real `contentWindow`, and it delivers `postMessage` in both directions,
 * but it never *fetches* the document named by `src` — so a real panel frame
 * never fires `load` under the runner. The single seam in `panelFrame.ts`, the
 * `PanelFrameFactory`, is therefore substituted with one that creates the frame
 * with the production factory and replaces nothing but the load observation.
 *
 * Everything else in these suites is real: the `iframe` element and its sandbox
 * attribute, its `contentWindow`, the `init` envelope the host posts into that
 * window, and the `MessageEvent`s the "panel" posts back, which carry the real
 * frame's window as `event.source`.
 */

import type { PanelFrameFactory, PanelFrameHandle, PanelFrameSpec } from "../panelFrame";
import { createSandboxedPanelFrame } from "../panelFrame";
import type { PanelToHostPayloads, PanelToHostType } from "../panelMessages";
import { panelToHostMessage } from "../panelMessages";

export interface RealFrameSeam {
  /** Pass this as `frameFactory`; it is stable across renders. */
  readonly factory: PanelFrameFactory;
  /** The spec the host asked for, once the factory has been called. */
  spec(): PanelFrameSpec;
  /** The real `iframe` production code created. */
  element(): HTMLIFrameElement;
  /** That frame's real content window. */
  contentWindow(): Window;
  /** Was the factory called at all? */
  created(): boolean;
  /**
   * Start recording what the frame's window receives. Safe to call repeatedly;
   * `reportLoaded` calls it too. It is separate so a test can observe the frame
   * *before* the document is reported loaded and assert that nothing was sent.
   */
  observe(): void;
  /** Report the entry document loaded, and start recording what it receives. */
  reportLoaded(): void;
  /** Report that the entry document could not be loaded. */
  reportLoadFailure(message: string): void;
  /** Post a well-formed panel-to-host message as the real frame's window. */
  fromPanel<K extends PanelToHostType>(
    token: string,
    type: K,
    payload: PanelToHostPayloads[K],
  ): void;
  /** Post arbitrary data, optionally from another window entirely. */
  raw(data: unknown, source?: Window | null): void;
  /** A real Window that is not this frame's, for the `event.source` check. */
  otherWindow(): Window;
  /** Everything the host posted into the frame, in order. */
  received(): readonly unknown[];
  /** Discard the recorded traffic. */
  clearReceived(): void;
}

export function createRealFrameSeam(): RealFrameSeam {
  let handle: PanelFrameHandle | null = null;
  let spec: PanelFrameSpec | null = null;
  let other: HTMLIFrameElement | null = null;
  let resolveLoaded: (() => void) | null = null;
  let rejectLoaded: ((error: unknown) => void) | null = null;
  const received: unknown[] = [];

  const loaded = new Promise<void>((resolve, reject) => {
    resolveLoaded = resolve;
    rejectLoaded = reject;
  });

  const factory: PanelFrameFactory = (requested) => {
    spec = requested;
    const real = createSandboxedPanelFrame(requested);
    handle = {
      element: real.element,
      get contentWindow() {
        return real.contentWindow;
      },
      whenLoaded: () => loaded,
      dispose: () => real.dispose(),
    };
    return handle;
  };

  const requireHandle = (): PanelFrameHandle => {
    if (!handle) throw new Error("the frame factory has not been called yet");
    return handle;
  };

  const requireWindow = (): Window => {
    const contentWindow = requireHandle().contentWindow;
    if (!contentWindow) throw new Error("the frame has no content window");
    return contentWindow;
  };

  const observed = new Set<Window>();
  const observe = () => {
    const contentWindow = handle?.contentWindow;
    if (!contentWindow || observed.has(contentWindow)) return;
    observed.add(contentWindow);
    contentWindow.addEventListener("message", (event) => {
      received.push((event as MessageEvent).data);
    });
  };

  return {
    factory,
    spec: () => {
      if (!spec) throw new Error("the frame factory has not been called yet");
      return spec;
    },
    element: () => requireHandle().element as HTMLIFrameElement,
    contentWindow: requireWindow,
    created: () => handle !== null,
    observe,
    reportLoaded() {
      observe();
      resolveLoaded?.();
    },
    reportLoadFailure(message: string) {
      rejectLoaded?.(new Error(message));
    },
    fromPanel(token, type, payload) {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: panelToHostMessage(token, type, payload),
          source: requireWindow(),
        }),
      );
    },
    raw(data, source) {
      window.dispatchEvent(
        new MessageEvent("message", {
          data,
          source: source === undefined ? requireWindow() : source,
        }),
      );
    },
    otherWindow() {
      if (!other) {
        other = document.createElement("iframe");
        document.body.appendChild(other);
      }
      const contentWindow = other.contentWindow;
      if (!contentWindow) throw new Error("the decoy frame has no content window");
      return contentWindow;
    },
    received: () => received,
    clearReceived: () => {
      received.length = 0;
    },
  };
}

/**
 * Wait for jsdom's asynchronous `postMessage` delivery to settle. jsdom queues
 * a posted message on the task queue, and the host's own handling of it queues
 * more, so a few turns of the macrotask queue are drained rather than one.
 */
export async function flush(rounds = 5): Promise<void> {
  for (let round = 0; round < rounds; round += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

/** The envelopes of one type the host posted into the frame. */
export function receivedOfType(seam: RealFrameSeam, type: string): Record<string, unknown>[] {
  return seam
    .received()
    .filter(
      (entry): entry is Record<string, unknown> =>
        typeof entry === "object" && entry !== null && (entry as { type?: unknown }).type === type,
    )
    .map((entry) => entry);
}
