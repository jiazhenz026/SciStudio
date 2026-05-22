// Extracted from BlockNode.tsx as part of the #1422 god-file split.
// Category icon map + status badge style table — pure-data lookups consumed
// by the BlockNode header (category icon) and StatusBadge (badge styling).

export const categoryIcons: Record<string, string> = {
  io: "📁",
  process: "⚙️",
  code: "💻",
  app: "🖥️",
  ai: "✨",
  subworkflow: "📦",
  custom: "🧩",
};

export interface BadgeStyle {
  icon: string;
  label: string;
  bg: string;
  text: string;
  spin?: boolean;
  italic?: boolean;
  clickable?: boolean;
}

export const badgeStyles: Record<string, BadgeStyle> = {
  idle: { icon: "○", label: "Idle", bg: "rgba(156,163,175,0.15)", text: "#9CA3AF" },
  ready: { icon: "◉", label: "Ready", bg: "rgba(59,130,246,0.15)", text: "#3B82F6" },
  running: {
    icon: "⟳",
    label: "Running",
    bg: "rgba(59,130,246,0.15)",
    text: "#3B82F6",
    spin: true,
  },
  paused: { icon: "⏸", label: "Paused", bg: "rgba(245,158,11,0.15)", text: "#F59E0B" },
  done: { icon: "✅", label: "Done", bg: "rgba(34,197,94,0.15)", text: "#22C55E" },
  error: {
    icon: "❌",
    label: "Error",
    bg: "rgba(239,68,68,0.15)",
    text: "#EF4444",
    clickable: true,
  },
  cancelled: { icon: "⊘", label: "Cancelled", bg: "rgba(249,115,22,0.15)", text: "#F97316" },
  skipped: {
    icon: "⊘",
    label: "Skipped",
    bg: "rgba(156,163,175,0.15)",
    text: "#9CA3AF",
    italic: true,
  },
};
