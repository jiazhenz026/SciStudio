import { useEffect, useRef, useState } from "react";
import { apiUrl, getBasePath } from "../lib/api/base-path";
import { panelsApi } from "../lib/api/panels";
import { createPanelBridge } from "./bridge";
import {
  forgetPanelHighlight,
  reportPanelHighlight,
  subscribePanelHighlight,
} from "./panelHighlights";
import { savePanelBytes } from "./save";
import { observePanelTheme, readPanelTheme } from "./theme";
import { isRecord } from "./types";
import type { PanelContext, PanelCreateRequest } from "./types";

export interface PanelFrameProps {
  request: PanelCreateRequest;
  onOpen?: (ref: string, contextId: string) => Promise<unknown>;
  onWriteBack?: (
    response: Record<string, unknown>,
    contextId: string,
    signal?: AbortSignal,
  ) => void | Promise<void>;
  onViewState?: (state: unknown, context: PanelContext) => void;
  onContext?: (context: PanelContext) => void;
  onFallback?: () => void;
  onCancel?: () => void;
}

/** Shared by preview columns, main-stage tabs and interactive windows. */
export function PanelFrame(props: PanelFrameProps) {
  const callbacks = useRef(props);
  callbacks.current = props;
  const frame = useRef<HTMLIFrameElement>(null);
  const bridge = useRef<ReturnType<typeof createPanelBridge> | null>(null);
  const teardown = useRef<() => void>(() => {});
  const [context, setContext] = useState<PanelContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [height, setHeight] = useState(420);
  const [ready, setReady] = useState(false);
  const loaded = useRef(false);
  const bootstrapPort = useRef<MessagePort | null>(null);
  const initialize = useRef<() => void>(() => {});
  const readsAbort = useRef<AbortController | null>(null);
  const readyTimer = useRef<ReturnType<typeof setTimeout>>();
  const requestKey = JSON.stringify(props.request);

  useEffect(() => {
    let disposed = false;
    let active: PanelContext | null = null;
    const controller = new AbortController();
    readsAbort.current = controller;
    let renewal: ReturnType<typeof setInterval> | undefined;
    setContext(null);
    setError(null);
    setReady(false);
    loaded.current = false;
    bootstrapPort.current = null;
    const receiveBootstrap = (event: MessageEvent<unknown>) => {
      const message = event.data;
      if (
        event.source !== frame.current?.contentWindow ||
        !isRecord(message) ||
        message.type !== "bootstrap"
      )
        return;
      if (
        disposed ||
        bootstrapPort.current ||
        !active ||
        message.v !== 1 ||
        typeof active.bootstrap_proof !== "string" ||
        active.bootstrap_proof.length < 32 ||
        message.proof !== active.bootstrap_proof ||
        event.ports.length !== 1
      ) {
        event.ports.forEach((port) => port.close());
        return;
      }
      bootstrapPort.current = event.ports[0];
      if (loaded.current) initialize.current();
    };
    window.addEventListener("message", receiveBootstrap);
    const close = () => {
      if (disposed) return;
      disposed = true;
      controller.abort();
      window.removeEventListener("message", receiveBootstrap);
      bootstrapPort.current?.close();
      clearTimeout(readyTimer.current);
      clearInterval(renewal);
      bridge.current?.dispose();
      bridge.current = null;
      if (active) void panelsApi.close(active.context_id).catch(() => {});
    };
    teardown.current = close;
    void panelsApi
      .create(JSON.parse(requestKey))
      .then((result) => {
        if (disposed) {
          void panelsApi.close(result.context_id).catch(() => {});
          return;
        }
        active = result;
        setContext(result);
        callbacks.current.onContext?.(result);
        readyTimer.current = setTimeout(() => {
          close();
          setError(
            bootstrapPort.current
              ? "Panel did not call ready() within 10 seconds"
              : "Panel did not establish its entry handshake within 10 seconds",
          );
        }, 10000);
        // Renew before the 600-second expiry. Static imports require no cookie;
        // this host heartbeat retains the guarded context lifetime while mounted.
        renewal = setInterval(() => {
          if (!active || disposed) return;
          void panelsApi.renew(active.context_id).catch((err: unknown) => {
            if (disposed) return;
            close();
            setError(err instanceof Error ? err.message : String(err));
          });
        }, 240000);
      })
      .catch((err: unknown) => {
        if (!disposed) setError(err instanceof Error ? err.message : String(err));
      });
    return close;
  }, [requestKey, attempt]);

  useEffect(() => observePanelTheme((theme) => bridge.current?.theme(theme)), []);

  const fail = (message: string) => {
    teardown.current();
    setError(message);
  };
  const connect = () => {
    if (!context || !bootstrapPort.current || bridge.current || error) return;
    const channel = new MessageChannel();
    bridge.current = createPanelBridge(channel.port1, context, {
      read: (ref, op, params) =>
        panelsApi.read(context.context_id, ref, op, params, readsAbort.current?.signal),
      // ADR-054 FR-016 — only a miniapp context is granted `call`; the bridge
      // refuses it everywhere else, so wiring it unconditionally is safe.
      call: (fn, args) => panelsApi.call(context.context_id, fn, args, readsAbort.current?.signal),
      open: (ref) =>
        callbacks.current.onOpen?.(ref, context.context_id) ??
        Promise.reject(new Error("No preview host")),
      writeBack: async (response) => {
        const signal = readsAbort.current?.signal;
        try {
          await callbacks.current.onWriteBack?.(response, context.context_id, signal);
          return null;
        } catch (error) {
          if (!signal?.aborted) fail(error instanceof Error ? error.message : String(error));
          throw error;
        }
      },
      save: savePanelBytes,
      viewState: (state) => callbacks.current.onViewState?.(state, context),
      resize: setHeight,
      highlightRect: (request, rect) => {
        if (frame.current) reportPanelHighlight(frame.current, request, rect);
      },
      // The same withdrawal the surrounding window's Cancel performs, reached
      // from inside the frame — by `api.cancel()`, or by Escape, which cannot
      // reach the host's own window from in there.
      cancel: () => callbacks.current.onCancel?.(),
      ready: () => {
        clearTimeout(readyTimer.current);
        setReady(true);
      },
      failure: fail,
    });
    bootstrapPort.current.postMessage(
      {
        v: 1,
        id: "init",
        type: "init",
        payload: {
          context: context.kind,
          operations: context.operations,
          services: context.services,
          input: context.input,
          theme: readPanelTheme(),
          viewState: context.view_state,
          apiVersion: context.panel.api_version,
          basePath: getBasePath(),
          sdkUrl: context.sdk_url,
          libBaseUrl: context.lib_base_url,
        },
      },
      [channel.port2],
    );
  };
  initialize.current = connect;

  /*
   * A tutorial step can point at something inside a panel (`preview_item` in the
   * collection panel, `plot_export_button` in the plot panel). The host's own
   * measurement walks its document and cannot reach in here, so the frame is
   * told which target is wanted and reports where it sits; `panelHighlights`
   * turns that into viewport coordinates for the ring and the step card.
   *
   * Told only while a step points at something, so a panel nobody is pointing
   * at is never asked to measure anything.
   */
  useEffect(() => {
    // Captured now, not read in the cleanup: by then the ref may already point
    // at the next frame, and the report that needs forgetting belongs to this
    // one — forgetting the wrong frame leaves a ring over a panel that is gone.
    const element = frame.current;
    const stop = subscribePanelHighlight((request) => bridge.current?.highlight(request));
    return () => {
      stop();
      if (element) forgetPanelHighlight(element);
    };
  }, [ready]);
  const onLoad = () => {
    if (!context || error) return;
    if (loaded.current) {
      fail("Panel navigated away from its entry page");
      return;
    }
    loaded.current = true;
    // Never hand input to contentWindow: it can already be a different document.
    // An early hello may be queued behind load; retain no authority until its
    // proof-bound, original-document port arrives (the ready deadline still runs).
    connect();
  };

  return (
    <div
      className="flex min-h-0 flex-1 flex-col"
      data-testid="panel-host"
      data-panel-ready={ready && !error}
    >
      {error ? (
        <div role="alert" className="rounded border border-red-300 p-3 text-sm">
          <p>
            Panel {context?.panel.id ?? props.request.panel_id ?? "preview"}: {error}
          </p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>
            Remount panel
          </button>
          {props.onFallback ? (
            <button type="button" onClick={props.onFallback}>
              Use core preview
            </button>
          ) : null}
          {props.onCancel ? (
            <button type="button" onClick={props.onCancel}>
              Cancel
            </button>
          ) : null}
        </div>
      ) : (
        <>
          {!ready ? (
            <p role="status" className="text-xs text-stone-500">
              Loading panel…
            </p>
          ) : null}
          {context ? (
            <iframe
              ref={frame}
              key={`${context.context_id}:${attempt}`}
              title={context.panel.name ?? context.panel.id}
              sandbox="allow-scripts"
              referrerPolicy="no-referrer"
              src={apiUrl(context.entry_url)}
              className="w-full flex-1 border-0"
              style={{ minHeight: height }}
              onLoad={onLoad}
              onError={() => fail("Could not load panel entry page")}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
