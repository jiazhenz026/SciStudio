// ADR-050 §2.1 — block-kind category icon table.
//
// The square canvas node body shows the block category as a compact mark
// (ADR-050 §2.1 / FR-006), sourced from `data.category`. This is the only
// lookup the square node needs from this module.
//
// The former runtime-status badge style table (`badgeStyles` / `BadgeStyle`)
// was removed under ADR-050: runtime/problem state now renders exclusively
// through `NodeStatusSurface`, which owns its own style table. There is no
// inline status pill in the node body anymore.

export const categoryIcons: Record<string, string> = {
  io: "📁",
  process: "⚙️",
  code: "💻",
  app: "🖥️",
  ai: "✨",
  subworkflow: "📦",
  custom: "🧩",
};
