/**
 * ADR-053 Learning Center (#2135) — the markup a beat may carry.
 *
 * `**like this**` renders bold, and `[like this](doc:page)` opens a page of the
 * user guide. Nothing else in a beat is markup.
 *
 * **Emphasis** exists for a narrow reason worth stating: a beat is usually one
 * sentence of explanation followed by one of instruction, and the instruction
 * is the half the reader has to act on. Setting it apart is what lets someone
 * who has looked away come back and find the thing to do without re-reading
 * the line.
 *
 * **The doc link** exists because a tutorial's last beat sometimes has to hand
 * the reader somewhere the tutorial cannot take them (#2083). Core tutorial 3
 * ends by saying that a live agent needs a provider installed — and the page
 * explaining how to install one is in the Learning Center's reading tab, on
 * the other side of closing the project. A sentence that names a page the
 * reader then has to go and find is a sentence that gets ignored.
 *
 * Both are authored, never inferred. Guessing at imperative verbs would put
 * weight on the wrong half of a sentence eventually, in someone else's
 * tutorial, with no way for that author to say otherwise — and tutorial copy
 * belongs to the person who wrote it.
 *
 * Deliberately not Markdown, still. A tutorial line is a spoken sentence, not
 * a document: it has no headings, no lists and no code spans, and pulling a
 * Markdown renderer in to serve two constructs would mean every other one
 * silently starts working too — including the ones that emit block elements
 * into a fixed-height panel that cannot hold them. The link syntax borrows
 * Markdown's shape because it is the shape everyone already reads, and its
 * target is restricted to `doc:` for the same reason the highlight vocabulary
 * is closed: a beat that could name any URL is a beat that could send a reader
 * anywhere.
 */

/** One run of a beat: plain, emphasized, or a link to a user-guide page. */
export interface BeatSegment {
  text: string;
  strong: boolean;
  /** User-guide page path this run opens, or null for ordinary text. */
  doc: string | null;
}

/**
 * Non-greedy and non-nesting: `**` closes at the first `*` it meets, so a lone
 * asterisk in a sentence is a lone asterisk rather than the start of a span
 * that swallows the rest of the line. The link alternative is matched in the
 * same pass so a bold run inside a link, or the reverse, cannot half-parse.
 */
const MARKUP = /\*\*([^*]+)\*\*|\[([^\]]+)\]\(doc:([^)\s]+)\)/g;

/** Split a beat into its plain, emphasized and linked runs, in order. */
export function beatSegments(line: string): BeatSegment[] {
  const segments: BeatSegment[] = [];
  let index = 0;

  for (const match of line.matchAll(MARKUP)) {
    const at = match.index ?? 0;
    if (at > index) segments.push({ text: line.slice(index, at), strong: false, doc: null });
    if (match[1] !== undefined) {
      segments.push({ text: match[1], strong: true, doc: null });
    } else {
      segments.push({ text: match[2] ?? "", strong: false, doc: match[3] ?? null });
    }
    index = at + match[0].length;
  }

  if (index < line.length) segments.push({ text: line.slice(index), strong: false, doc: null });
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
