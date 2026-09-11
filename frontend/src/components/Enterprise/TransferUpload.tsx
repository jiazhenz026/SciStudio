/**
 * ADR-055 Spec 4 FR-005 — upload a file from this computer into the project.
 *
 * On a lab server the backend and the project live on the server while the
 * user's files are on the laptop. The `transfer` capability turns on this
 * picker, which sends the chosen file through the existing staged
 * `POST /api/data/upload` route with visible progress and a working Cancel.
 * It never uses inline transfer, whatever the file's size: the staged route
 * streams the body to disk and discards it when the upload is cancelled.
 */

import { Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { UploadCancelledError, dataApi } from "../../lib/api/data";
import { errorMessage } from "./enterpriseApi";

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading"; name: string; loaded: number; total: number | null }
  | { phase: "done"; name: string }
  | { phase: "cancelled"; name: string }
  | { phase: "failed"; name: string; message: string };

function percent(loaded: number, total: number | null): number | null {
  if (total === null || total <= 0) return null;
  return Math.min(100, Math.round((loaded / total) * 100));
}

function UploadStatus({ state, onCancel }: { state: UploadState; onCancel: () => void }) {
  if (state.phase === "idle") return null;
  if (state.phase === "uploading") {
    const done = percent(state.loaded, state.total);
    return (
      <span className="inline-flex items-center gap-2 text-xs text-stone-600">
        <progress
          aria-label={`Uploading ${state.name}`}
          className="h-1.5 w-24"
          data-testid="enterprise-upload-progress"
          max={100}
          value={done ?? undefined}
        />
        <span data-testid="enterprise-upload-percent">{done === null ? "…" : `${done}%`}</span>
        <button
          aria-label={`Cancel uploading ${state.name}`}
          className="inline-flex items-center rounded-full p-0.5 text-stone-500 hover:bg-stone-100"
          data-testid="enterprise-upload-cancel"
          onClick={onCancel}
          type="button"
        >
          <X aria-hidden="true" className="size-3.5" />
        </button>
      </span>
    );
  }
  const text =
    state.phase === "done"
      ? `Uploaded ${state.name}`
      : state.phase === "cancelled"
        ? `Upload of ${state.name} cancelled`
        : `Upload of ${state.name} failed: ${state.message}`;
  return (
    <span
      className={`max-w-[16rem] truncate text-xs ${state.phase === "failed" ? "text-rose-600" : "text-stone-600"}`}
      data-testid="enterprise-upload-result"
      role={state.phase === "failed" ? "alert" : "status"}
      title={text}
    >
      {text}
    </span>
  );
}

export function TransferUpload({ projectOpen }: { projectOpen: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const [state, setState] = useState<UploadState>({ phase: "idle" });
  const uploading = state.phase === "uploading";

  // Leaving the page area mid-upload cancels it rather than orphaning it.
  useEffect(() => () => controller.current?.abort(), []);

  const upload = async (file: File) => {
    const abort = new AbortController();
    controller.current = abort;
    setState({ phase: "uploading", name: file.name, loaded: 0, total: file.size || null });
    try {
      await dataApi.uploadDataWithProgress(file, {
        signal: abort.signal,
        onProgress: ({ loaded, total }) =>
          setState({
            phase: "uploading",
            name: file.name,
            loaded,
            total: total ?? (file.size || null),
          }),
      });
      setState({ phase: "done", name: file.name });
    } catch (failure) {
      setState(
        failure instanceof UploadCancelledError
          ? { phase: "cancelled", name: file.name }
          : { phase: "failed", name: file.name, message: errorMessage(failure) },
      );
    } finally {
      if (controller.current === abort) controller.current = null;
    }
  };

  return (
    <div className="flex shrink-0 items-center gap-2" data-testid="enterprise-transfer">
      <button
        className="inline-flex items-center gap-1.5 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-50 disabled:hover:bg-transparent"
        data-testid="enterprise-upload"
        disabled={!projectOpen || uploading}
        onClick={() => inputRef.current?.click()}
        title={
          projectOpen
            ? "Upload a file from this computer into the project"
            : "Open a project to upload files into it"
        }
        type="button"
      >
        <Upload aria-hidden="true" className="size-4" />
        Upload
      </button>
      <input
        className="hidden"
        data-testid="enterprise-upload-input"
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Reset so picking the same file again still fires a change.
          event.target.value = "";
          if (file) void upload(file);
        }}
        ref={inputRef}
        tabIndex={-1}
        type="file"
      />
      <UploadStatus onCancel={() => controller.current?.abort()} state={state} />
    </div>
  );
}
