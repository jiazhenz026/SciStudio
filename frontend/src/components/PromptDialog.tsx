import { useEffect, useRef, useState } from "react";

/**
 * Promise-based text-input modal.
 *
 * Electron's embedded Chromium does not implement `window.prompt()` (it returns
 * null and logs "prompt() is and will not be supported"), so the toolbar's
 * "New workflow / note / custom block" actions silently did nothing on the
 * desktop build. This dialog is the supported replacement: callers request a
 * value via `promptInput(...)` and await the entered string (or null on
 * cancel), with optional inline validation.
 */
export interface PromptRequest {
  /** Heading shown at the top of the dialog. */
  title: string;
  /** Label above the input. */
  label: string;
  /** Initial input value. */
  defaultValue?: string;
  /** Native input placeholder. */
  placeholder?: string;
  /** Confirm button text (defaults to "Create"). */
  submitLabel?: string;
  /**
   * Optional validator. Return an error string to keep the dialog open and
   * show the message, or null when the value is acceptable.
   */
  validate?: (value: string) => string | null;
  /** Internal: resolves the awaiting `promptInput` promise. */
  resolve: (value: string | null) => void;
}

export function PromptDialog({
  request,
  onClose,
}: {
  request: PromptRequest | null;
  onClose: () => void;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reseed local state each time a new prompt opens.
  useEffect(() => {
    if (!request) return;
    setValue(request.defaultValue ?? "");
    setError(null);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [request]);

  if (!request) return null;

  const finish = (result: string | null) => {
    request.resolve(result);
    onClose();
  };

  const handleSubmit = () => {
    const trimmed = value.trim();
    const validationError = request.validate?.(trimmed) ?? null;
    if (validationError) {
      setError(validationError);
      return;
    }
    finish(trimmed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        className="w-full max-w-md rounded-[1.5rem] border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <h2 className="font-display text-2xl text-ink">{request.title}</h2>

        <label className="mt-5 block text-sm font-medium text-stone-700">
          {request.label}
          <input
            ref={inputRef}
            className="mt-1 w-full rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
            value={value}
            placeholder={request.placeholder}
            onChange={(event) => setValue(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleSubmit();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                finish(null);
              }
            }}
            data-testid="prompt-dialog-input"
          />
        </label>

        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-full border border-stone-300 px-4 py-2 text-sm"
            onClick={() => finish(null)}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine"
            onClick={handleSubmit}
            type="button"
            data-testid="prompt-dialog-submit"
          >
            {request.submitLabel ?? "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
