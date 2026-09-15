// The Reload control shared by every left-panel section header (#2415): the
// same `RefreshCw` icon as the toolbar Reload, followed by the "Reload" label
// (#2090 — one verb for every left-panel reload). While a reload is in flight
// the icon spins and the button is disabled; sections without an in-flight
// signal simply leave `loading` unset.

import { RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";

export interface SectionReloadButtonProps {
  onClick: () => void;
  /** A reload is in flight: spin the icon and disable the button. */
  loading?: boolean;
  className?: string;
}

export function SectionReloadButton({
  onClick,
  loading = false,
  className,
}: SectionReloadButtonProps) {
  return (
    <button
      className={cn("toolbar-button inline-flex items-center gap-1 whitespace-nowrap", className)}
      disabled={loading}
      onClick={onClick}
      type="button"
    >
      <RefreshCw
        aria-hidden="true"
        className={loading ? "animate-spin" : undefined}
        data-testid="section-reload-icon"
        size={14}
      />
      Reload
    </button>
  );
}
