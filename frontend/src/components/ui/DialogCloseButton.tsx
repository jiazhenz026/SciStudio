import { X } from "lucide-react";
import type { ButtonHTMLAttributes, JSX } from "react";

import { cn } from "@/lib/utils";

export interface DialogCloseButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "children" | "type"
> {
  /** Accessible name; the button has no visible text. */
  label?: string;
}

/**
 * Icon-only X control for the top-right header of a popup dialog (#2378).
 *
 * Matches the existing header X buttons (Learning Center, reading window):
 * no visible text, the accessible name comes from `aria-label`.
 */
export function DialogCloseButton({
  label = "Close",
  className,
  title,
  ...rest
}: DialogCloseButtonProps): JSX.Element {
  return (
    <button
      {...rest}
      aria-label={label}
      title={title ?? label}
      type="button"
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-ink disabled:pointer-events-none disabled:opacity-40",
        className,
      )}
    >
      <X aria-hidden="true" className="size-4" />
    </button>
  );
}
