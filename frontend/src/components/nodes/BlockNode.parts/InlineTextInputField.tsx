// Extracted from BlockNode.tsx as part of the #1422 god-file split.
//
// InlineTextInputField — the default text-input branch of InlineConfigField.
// Splitting this into its own component preserves the Wave 1 (#1420) fix:
// useState / useRef / useLayoutEffect now sit at the top level of every
// component in this file rather than after the early returns in
// InlineConfigField. The default-branch invocation MUST stay rendered as a
// child component so its hook chain is independent of the discriminator.
//
// Behaviour:
//   - `ui_widget="file_browser"` / `"directory_browser"` renders a "..."
//     Browse button next to the input (#484). Click opens the native OS
//     dialog via `api.openNativeDialog`; on HTTP 500 / non-ApiError we fall
//     back to the in-app FileBrowserModal; on HTTP 504 we surface a
//     console.error rather than silently falling back (#678).
//   - `ui_widget="directory_browser"` also renders a clipboard-copy button.
//   - Caret preservation (#710): selectionStart / selectionEnd are captured
//     on every onChange and restored after the controlled-input round-trip
//     so typing in the middle of a path does not jump the caret to the end.
//     The pendingSelectionRef is cleared after every layout effect so an
//     unrelated re-render does NOT replay the stale caret position (#710
//     audit follow-up).

import { useLayoutEffect, useRef, useState } from "react";

import { api, ApiError } from "../../../lib/api";
import { FileBrowserModal } from "./FileBrowserModal";
import type { ConfigProperty } from "./inlineConfigHelpers";

/** Extract the parent directory for the native-dialog `initial_dir` argument. */
function deriveInitialDir(uiWidget: string | undefined, currentVal: string): string | undefined {
  if (!currentVal) return undefined;
  const sep = currentVal.includes("\\") ? "\\" : "/";
  const parts = currentVal.split(sep);
  if (parts.length > 1 && uiWidget === "file_browser") {
    const last = parts[parts.length - 1];
    return last.includes(".") ? parts.slice(0, -1).join(sep) : currentVal;
  }
  return currentVal;
}

/** Compute the initial directory for the FileBrowserModal fallback. */
function deriveModalInitialPath(uiWidget: string | undefined, val: string): string {
  if (!val) return "";
  const sep = val.includes("\\") ? "\\" : "/";
  const parts = val.split(sep);
  if (parts.length > 1) {
    const last = parts[parts.length - 1];
    if (uiWidget === "file_browser" && last.includes(".")) {
      return parts.slice(0, -1).join(sep);
    }
  }
  return val;
}

/** Apply the native-dialog result to the field value, picking array vs scalar
 *  based on the schema. */
function applyNativeDialogResult(
  key: string,
  schemaType: unknown,
  paths: string[],
  onChange: (key: string, val: unknown) => void,
): void {
  // Only pass an array when the field schema explicitly supports it
  // (type includes "array"). Fields like app_command and script_path
  // are pure strings and must not receive an array.
  const supportsArray = Array.isArray(schemaType)
    ? schemaType.includes("array")
    : schemaType === "array";
  if (supportsArray && paths.length > 1) {
    onChange(key, paths);
  } else {
    onChange(key, paths[0]);
  }
}

/** Translate a native-dialog rejection into "open the in-app modal" vs
 *  "do not fall back" per #678. Returns true when the caller should open the
 *  in-app FileBrowserModal instead. */
function shouldFallbackToInAppModal(err: unknown): boolean {
  if (err instanceof ApiError) {
    if (err.status === 504) {
      // HTTP 504 = dialog timed out. Backend no longer enforces a timeout
      // so this should not happen in practice; if it does, do NOT fall back
      // silently — surface the error so we notice. Just log; the deprecated
      // in-app picker is a worse experience than a no-op.
      console.error(
        "Native file dialog timed out (HTTP 504); not falling back to in-app picker.",
        err,
      );
      return false;
    }
    // 500 and any other HTTP error: fall back to in-app picker.
    return true;
  }
  // Non-ApiError (network failure, etc.): fall back defensively.
  return true;
}

function ClipboardCopyButton({ value }: { value: string }) {
  const [clipCopied, setClipCopied] = useState(false);
  return (
    <button
      type="button"
      className="nodrag shrink-0 rounded border border-stone-200 bg-white px-1.5 py-1 text-xs text-stone-600 hover:bg-stone-50"
      title={clipCopied ? "Copied!" : "Copy path to clipboard"}
      onClick={() => {
        if (value) {
          void navigator.clipboard.writeText(value);
          setClipCopied(true);
          setTimeout(() => setClipCopied(false), 1500);
        }
      }}
    >
      {clipCopied ? (
        <span className="text-green-600 text-[10px]">✓</span>
      ) : (
        <svg
          width="12"
          height="12"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <rect x="5" y="5" width="9" height="9" rx="1" />
          <path d="M11 5V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h2" />
        </svg>
      )}
    </button>
  );
}

export function InlineTextInputField({
  prop,
  value,
  onChange,
}: {
  prop: ConfigProperty;
  value: unknown;
  onChange: (key: string, val: unknown) => void;
}) {
  const { key, schema } = prop;
  const label = (schema.title as string) ?? key;

  // When ui_widget is "file_browser" or "directory_browser", render a "..."
  // browse button next to the input that opens the FileBrowserModal (#484).
  const uiWidget = schema.ui_widget as string | undefined;
  const hasBrowse = uiWidget === "file_browser" || uiWidget === "directory_browser";
  const [browseOpen, setBrowseOpen] = useState(false);

  const handleBrowseClick = async () => {
    // Try native OS dialog first, fall back to in-app FileBrowserModal
    const nativeMode = uiWidget === "directory_browser" ? "directory" : "file";
    const currentVal = String(value ?? schema.default ?? "");
    const initialDir = deriveInitialDir(uiWidget, currentVal);
    try {
      const result = await api.openNativeDialog(nativeMode, initialDir);
      if (result.paths.length > 0) {
        applyNativeDialogResult(key, schema.type, result.paths, onChange);
      }
      // If paths is empty, user cancelled — do nothing.
    } catch (err) {
      // Status-aware fallback (#678).
      if (shouldFallbackToInAppModal(err)) {
        setBrowseOpen(true);
      }
    }
  };

  // Caret-preservation pattern for controlled text inputs (#710).
  //
  // Because the value flows out to a Zustand store and back as a new `value`
  // prop on the next render, the browser does not reliably preserve the
  // caret position when typing in the middle of an existing string — the
  // caret jumps to the end. We capture selectionStart/selectionEnd on every
  // change and restore them after the value prop is applied.
  //
  // Audit follow-up (#710): only restore when the re-render originated from
  // this input's own onChange. The previous shape kept selectionRef live
  // across renders, so any unrelated re-render while the field stayed
  // focused (e.g. the user moves the caret with the mouse/arrow keys, then
  // a sibling state update fires) would force the caret back to the stale
  // position from the last typed character. We now store the pending
  // selection only between onChange and the next layout effect, then null
  // it out so subsequent renders are no-ops unless another onChange fills
  // it in. The document.activeElement guard ensures the unfocused mirror
  // (e.g. the BottomPanel input bound to the same store entry) does not
  // steal selection from the canvas input.
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingSelectionRef = useRef<{ start: number; end: number } | null>(null);
  useLayoutEffect(() => {
    const pending = pendingSelectionRef.current;
    const el = inputRef.current;
    if (pending && el && document.activeElement === el) {
      try {
        el.setSelectionRange(pending.start, pending.end);
      } catch {
        // setSelectionRange throws on input types where selection is not
        // applicable; harmless to ignore here.
      }
    }
    // Always clear after attempting restore so the next render does
    // nothing unless another onChange refills the ref.
    pendingSelectionRef.current = null;
  });

  const stringValue = String(value ?? schema.default ?? "");

  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="shrink-0 text-stone-500">{label}</span>
      <div className="flex min-w-0 flex-1 gap-1">
        <input
          ref={inputRef}
          type="text"
          className="nodrag nowheel min-w-0 flex-1 truncate rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
          placeholder={key === "path" || key === "script_path" ? "Type or paste path" : undefined}
          title={stringValue}
          value={stringValue}
          onChange={(e) => {
            pendingSelectionRef.current = {
              start: e.target.selectionStart ?? 0,
              end: e.target.selectionEnd ?? 0,
            };
            onChange(key, e.target.value);
          }}
        />
        {hasBrowse && (
          <button
            type="button"
            className="nodrag shrink-0 rounded border border-stone-200 bg-white px-1.5 py-1 text-xs text-stone-600 hover:bg-stone-50"
            title="Browse filesystem"
            onClick={() => void handleBrowseClick()}
          >
            ...
          </button>
        )}
        {uiWidget === "directory_browser" && <ClipboardCopyButton value={stringValue} />}
      </div>
      {browseOpen && hasBrowse && (
        <FileBrowserModal
          mode={uiWidget as "file_browser" | "directory_browser"}
          initialPath={deriveModalInitialPath(uiWidget, stringValue)}
          onSelect={(selectedPath) => {
            onChange(key, selectedPath);
            setBrowseOpen(false);
          }}
          onCancel={() => setBrowseOpen(false)}
        />
      )}
    </label>
  );
}
