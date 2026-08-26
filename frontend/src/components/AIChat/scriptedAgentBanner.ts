/**
 * ADR-053 FR-061a (#2083) — the scripted agent's start-up banner.
 *
 * A mark and two lines, the shape every agent CLI opens with. The first pass
 * set the name in block capitals with a sampled portrait of Mio beside it, and
 * it was ugly twice over: at any width a terminal can spare, her sprite has no
 * tonal structure left to sample — pale hair against pale skin — so the
 * portrait came out as noise, and forty columns of block capitals made a title
 * card rather than a prompt.
 *
 * **The mark is an abstract logo, and the name is plain text.** Neither tries
 * to draw anything. Mio has a portrait already — she is on screen a few inches
 * to the left, drawn properly at a size that can carry a face — and a second,
 * worse likeness beside it would only invite the comparison. Type set in
 * blocks is a picture of type, and reads worse than type.
 *
 * **No frame.** A CLI draws its border to the width of the terminal it is in.
 * This banner goes into a panel the reader can drag narrower at any moment,
 * and a fixed-width box that wraps is worse than no box — so the mark and the
 * text stand on their own and stay legible at any width.
 *
 * **It scrolls.** The banner is written into the terminal buffer when the tab
 * opens, so it is what a reader sees before they have asked anything and it
 * leaves on its own once the conversation is long enough to push it off. A
 * pinned header would keep taking that room from the conversation for the rest
 * of the session, which is not what a CLI does with its own name.
 */

/** Amber for the mark, a brighter tone for the name, dim for the disclaimer. */
const MARK = "\x1b[38;5;215m";
const NAME = "\x1b[1m\x1b[38;5;223m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";

/**
 * The mark: a solid block with two eyes in it.
 *
 * `▀` is a cell filled on its top half only, so the empty bottom half of that
 * cell is the eye — one cell wide, half a cell tall, sitting on the mark's
 * vertical midline with a filled column between the pair. Everything else is
 * `█`. Nothing here is a bracket: the half-block brackets the first version
 * used were the same colour as the fill they were supposed to frame, so on
 * screen they merged into it and only made the mark wider.
 *
 * Two rows because that is how many the two lines of text beside it need. A
 * mark taller than its own caption reads as a picture that happens to have
 * writing next to it.
 */
export const AGENT_MARK: readonly [string, string] = ["█▀█▀█", "█████"];

/** The name, and the one thing a reader has to know before they read a word. */
export const AGENT_NAME = "SciStudio Mio Agent";
export const AGENT_NOTE =
  "A recorded session — it spends none of your tokens, and takes no typing.";

/** The banner as a terminal-ready string, colours included. */
export function scriptedAgentBanner(): string {
  const top = `  ${MARK}${AGENT_MARK[0]}${RESET}   ${NAME}${AGENT_NAME}${RESET}`;
  const bottom = `  ${MARK}${AGENT_MARK[1]}${RESET}   ${DIM}${AGENT_NOTE}${RESET}`;
  return `\r\n${top}\r\n${bottom}\r\n\r\n`;
}
