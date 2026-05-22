// Extracted from BlockNode.tsx as part of the #1422 god-file split.
// StatusBadge — renders the status pill in the BlockNode footer. When the
// status is "error" the badge becomes a focusable button that surfaces the
// click via `onErrorClick` (consumed by the App-level handler that routes to
// the Logs bottom tab).

import { badgeStyles } from "./badgeStyles";

export function StatusBadge({
  status,
  onErrorClick,
}: {
  status?: string;
  onErrorClick?: () => void;
}) {
  const style = badgeStyles[status ?? "idle"] ?? badgeStyles.idle;

  const inner = (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium leading-none"
      style={{
        backgroundColor: style.bg,
        color: style.text,
        fontStyle: style.italic ? "italic" : undefined,
        cursor: style.clickable ? "pointer" : undefined,
      }}
    >
      <span className={style.spin ? "inline-block animate-spin" : undefined}>{style.icon}</span>
      {style.label}
    </span>
  );

  if (style.clickable && onErrorClick) {
    return (
      <button type="button" onClick={onErrorClick} className="focus:outline-none">
        {inner}
      </button>
    );
  }

  return inner;
}
