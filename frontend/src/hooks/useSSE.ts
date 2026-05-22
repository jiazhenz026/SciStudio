import { useEffect, useState } from "react";

import type { LogEntry } from "../types/api";
import { useAppStore } from "../store";

export function useLogStream(
  workflowId: string | null,
  blockId: string | null,
): { connected: boolean } {
  const appendLog = useAppStore((state) => state.appendLog);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!workflowId) {
      return undefined;
    }

    const params = new URLSearchParams({ workflow_id: workflowId });
    if (blockId) {
      params.set("block_id", blockId);
    }

    const source = new EventSource(`/api/logs/stream?${params.toString()}`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("log", (event) => {
      const message = JSON.parse((event as MessageEvent<string>).data) as LogEntry;
      appendLog(message);
    });

    return () => {
      source.close();
      setConnected(false);
    };
  }, [appendLog, blockId, workflowId]);

  return { connected };
}
