// Extracted from BlockNode.tsx as part of the #1422 god-file split.
// ErrorMessage — inline truncated error message rendered next to the
// StatusBadge when status === "error". Full error text is exposed via the
// `title` attribute (first MAX_TOOLTIP_LINES lines).

const MAX_INLINE_ERROR_LEN = 80;
const MAX_TOOLTIP_LINES = 10;

export function ErrorMessage({ message }: { message: string }) {
  const truncated =
    message.length > MAX_INLINE_ERROR_LEN ? `${message.slice(0, MAX_INLINE_ERROR_LEN)}…` : message;

  // Build a tooltip that shows up to MAX_TOOLTIP_LINES lines of the error
  const lines = message.split("\n");
  const tooltipText =
    lines.length > MAX_TOOLTIP_LINES
      ? lines.slice(0, MAX_TOOLTIP_LINES).join("\n") + "\n…(click for full trace)"
      : message;

  return (
    <span
      className="ml-2 min-w-0 flex-1 truncate text-[10px] leading-tight text-red-500"
      title={tooltipText}
    >
      {truncated}
    </span>
  );
}
