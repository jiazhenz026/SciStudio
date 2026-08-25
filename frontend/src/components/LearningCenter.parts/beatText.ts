/**
 * ADR-053 Learning Center (#2135) — the one piece of markup a beat may carry.
 *
 * `**like this**` renders bold, and nothing else in a beat is markup. The
 * reason it exists is narrow and worth stating: a beat is usually one sentence
 * of explanation followed by one of instruction, and the instruction is the
 * half the reader has to act on. Setting it apart is what lets someone who has
 * looked away come back and find the thing to do without re-reading the line.
 *
 * It is authored, never inferred. Guessing at imperative verbs would put weight
 * on the wrong half of a sentence eventually, in someone else's tutorial, with
 * no way for that author to say otherwise — and tutorial copy belongs to the
 * person who wrote it.
 *
 * Deliberately not Markdown. A tutorial line is a spoken sentence, not a
 * document: it has no headings, no lists, no links and no code spans, and
 * pulling a Markdown renderer in to serve one pair of asterisks would mean
 * every other construct silently starts working too — including the ones that
 * emit block elements into a fixed-height panel that cannot hold them.
 */

/** One run of a beat, and whether it is emphasized. */
export interface BeatSegment {
  text: string;
  strong: boolean;
}

/**
 * Non-greedy and non-nesting: `**` closes at the first `*` it meets, so a lone
 * asterisk in a sentence is a lone asterisk rather than the start of a span
 * that swallows the rest of the line.
 */
const EMPHASIS = /\*\*([^*]+)\*\*/g;

/** Split a beat into its plain and emphasized runs, in order. */
export function beatSegments(line: string): BeatSegment[] {
  const segments: BeatSegment[] = [];
  let index = 0;

  for (const match of line.matchAll(EMPHASIS)) {
    const at = match.index ?? 0;
    if (at > index) segments.push({ text: line.slice(index, at), strong: false });
    segments.push({ text: match[1] ?? "", strong: true });
    index = at + match[0].length;
  }

  if (index < line.length) segments.push({ text: line.slice(index), strong: false });
  return segments;
}

/**
 * How many characters the reader will see — the markers are not among them.
 *
 * This is what the typewriter counts in, which is why it is computed from the
 * segments rather than from the raw line: revealing by raw index would stall
 * for two ticks on every `**` and land the emphasis a beat late.
 */
export function beatLength(segments: readonly BeatSegment[]): number {
  return segments.reduce((total, segment) => total + segment.text.length, 0);
}
