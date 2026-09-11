import { useEffect, useRef, useState } from "react";
import { apiUrl, getBasePath } from "../lib/api/base-path";
import { panelsApi } from "../lib/api/panels";
import { createPanelBridge } from "./bridge";
import { savePanelBytes } from "./save";
import { observePanelTheme, readPanelTheme } from "./theme";
import type { PanelContext, PanelCreateRequest } from "./types";

export interface PanelFrameProps {
  request: PanelCreateRequest;
  onOpen?: (ref: string, contextId: string) => Promise<unknown>;
  onWriteBack?: (response: Record<string, unknown>, contextId: string) => void;
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
    const close = () => {
      if (disposed) return;
      disposed = true;
      controller.abort();
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
          setError("Panel did not call ready() within 10 seconds");
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
  const onLoad = () => {
    if (!context || !frame.current?.contentWindow || error) return;
    // The opaque frame cannot expose location. Any subsequent load (including
    // reload, hash-independent navigation or redirect) invalidates the mount.
    if (loaded.current) {
      fail("Panel navigated away from its entry page");
      return;
    }
    loaded.current = true;
    const channel = new MessageChannel();
    bridge.current = createPanelBridge(channel.port1, context, {
      read: (ref, op, params) =>
        panelsApi.read(context.context_id, ref, op, params, readsAbort.current?.signal),
      open: (ref) =>
        callbacks.current.onOpen?.(ref, context.context_id) ??
        Promise.reject(new Error("No preview host")),
      writeBack: async (response) => {
        callbacks.current.onWriteBack?.(response, context.context_id);
        return null;
      },
      save: savePanelBytes,
      viewState: (state) => callbacks.current.onViewState?.(state, context),
      resize: setHeight,
      ready: () => {
        clearTimeout(readyTimer.current);
        setReady(true);
      },
      failure: fail,
    });
    frame.current.contentWindow.postMessage(
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
      "*",
      [channel.port2],
    ); // An opaque sandbox has no target origin to name.
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="panel-host">
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
