/**
 * ADR-053 Learning Center (#2057) — one source's completion, drawn as a ring.
 *
 * The number in the middle is the whole message; the ring is how far along it
 * reads at a glance. Both come from a single group's own counts, never from a
 * sum across groups — FR-076 forbids reporting one, and this component has no
 * way to be handed one, because it takes two integers and no list.
 */

const RADIUS = 32;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function ProgressRing({
  completed,
  total,
  label,
}: {
  completed: number;
  total: number;
  label: string;
}) {
  /*
   * A source shipping no tutorials draws a full ring rather than dividing by
   * zero. There is nothing left to do, which is what a full ring says.
   */
  const fraction = total > 0 ? Math.min(Math.max(completed / total, 0), 1) : 1;

  return (
    <div className="flex flex-col items-center gap-2" data-testid="learning-center-progress-ring">
      <svg
        aria-label={`${completed} of ${total} complete`}
        className="size-[76px]"
        role="img"
        viewBox="0 0 76 76"
      >
        {/*
         * Only the arcs are rotated, by attribute rather than by a CSS class,
         * so the fill starts at twelve o'clock while the text below stays
         * upright without a counter-rotation to keep in step with it.
         */}
        <g transform="rotate(-90 38 38)">
          <circle
            className="stroke-stone-200"
            cx="38"
            cy="38"
            fill="none"
            r={RADIUS}
            strokeWidth="6"
          />
          <circle
            className="stroke-pine transition-[stroke-dashoffset] duration-500"
            cx="38"
            cy="38"
            fill="none"
            r={RADIUS}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - fraction)}
            strokeLinecap="round"
            strokeWidth="6"
          />
        </g>
        <text
          className="fill-ink font-display text-[19px]"
          dominantBaseline="central"
          textAnchor="middle"
          x="38"
          y="38"
        >
          {completed}/{total}
        </text>
      </svg>
      <p className="text-center text-xs leading-4 text-stone-500">{label}</p>
    </div>
  );
}
