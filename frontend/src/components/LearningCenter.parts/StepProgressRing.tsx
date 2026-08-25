/**
 * ADR-053 Learning Center (#2136) — how far through the tutorial, without a number.
 *
 * "1 / 16" told a first-time reader the size of a commitment at the moment the
 * tutorial was asking them to make one. A ring says the same thing in the only
 * register that helps here — *some* of the way — and cannot be read as fifteen
 * more of these.
 *
 * The numbers are still available to anyone who wants them: the ring carries
 * them as its accessible name and its tooltip, and the catalogue shows progress
 * outright. This is a decision about what is unavoidable on screen, not about
 * hiding the count from a reader who goes looking for it.
 *
 * Separate from `ProgressRing`, which is the catalogue's: that one is 76px, has
 * the fraction across its middle, and takes a caption. Nothing of it survives
 * being shrunk to a heading's line height, so this is its own component rather
 * than a size prop on that one.
 */

const SIZE = 16;
const STROKE = 2.5;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function StepProgressRing({ index, total }: { index: number; total: number }) {
  /*
   * Filled by steps *finished*, not by the step being read. Landing on the
   * first step of a tutorial has achieved nothing yet, and a ring already part
   * full at that point is flattering the reader rather than informing them.
   */
  const fraction = total > 0 ? Math.min(Math.max(index / total, 0), 1) : 0;
  const label = `Step ${index + 1} of ${total}`;

  return (
    <svg
      aria-label={label}
      className="shrink-0"
      data-testid="tutorial-step-progress"
      height={SIZE}
      role="img"
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      width={SIZE}
    >
      <title>{label}</title>
      {/* Rotated so the arc starts at twelve o'clock rather than at three. */}
      <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
        <circle
          className="stroke-ink/15"
          cx={SIZE / 2}
          cy={SIZE / 2}
          fill="none"
          r={RADIUS}
          strokeWidth={STROKE}
        />
        <circle
          className="stroke-pine transition-[stroke-dashoffset] duration-500"
          cx={SIZE / 2}
          cy={SIZE / 2}
          fill="none"
          r={RADIUS}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - fraction)}
          strokeLinecap="round"
          strokeWidth={STROKE}
        />
      </g>
    </svg>
  );
}
