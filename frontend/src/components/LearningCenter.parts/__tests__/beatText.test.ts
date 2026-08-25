/**
 * ADR-053 Learning Center (#2135) — the one piece of markup a beat may carry.
 *
 * A beat is a spoken sentence, not a document, and `**like this**` is the only
 * construct it understands. That narrowness is the design rather than an
 * unfinished parser, so the cases worth pinning are the ones where a fuller
 * Markdown renderer would have done something and this deliberately does not:
 * a lone asterisk in the middle of a sentence, and a `**` the author never
 * closed. Both have to survive as the characters the author typed. A parser
 * that treated either as the start of a span would swallow the rest of the
 * line into bold, and the reader would lose the instruction the emphasis
 * exists to set apart.
 *
 * `beatLength` is tested beside the splitting because the typewriter counts in
 * it. Counting the raw line instead would stall the reveal for two ticks on
 * every pair of markers and land the emphasis a beat behind the words it is on.
 */

import { describe, expect, it } from "vitest";

import { beatLength, beatSegments } from "../beatText";

describe("splitting a beat into its runs", () => {
  it("hands back an ordinary sentence as a single plain run", () => {
    expect(beatSegments("A block is SciStudio's basic unit of data processing.")).toEqual([
      { text: "A block is SciStudio's basic unit of data processing.", strong: false },
    ]);
  });

  it("separates an emphasized instruction from the explanation around it", () => {
    /*
     * The shape nearly every authored beat takes: a sentence of explanation,
     * then the half the reader has to act on. Three runs in the order they
     * were written, so a reader coming back to the panel finds the thing to do
     * without re-reading the line.
     */
    expect(
      beatSegments("A block is a unit. **Drag Load onto the canvas.** It goes anywhere."),
    ).toEqual([
      { text: "A block is a unit. ", strong: false },
      { text: "Drag Load onto the canvas.", strong: true },
      { text: " It goes anywhere.", strong: false },
    ]);
  });

  it("emits no empty run when the emphasis opens the line", () => {
    /*
     * There is no plain text before the marker, and inventing a zero-length
     * run for it would put an empty element into the panel on every such beat
     * — harmless to look at and noise to assert against.
     */
    expect(beatSegments("**Press Run.** The workflow executes top to bottom.")).toEqual([
      { text: "Press Run.", strong: true },
      { text: " The workflow executes top to bottom.", strong: false },
    ]);
  });

  it("emits no empty run when the emphasis closes the line", () => {
    expect(beatSegments("Everything is ready. **Press Run.**")).toEqual([
      { text: "Everything is ready. ", strong: false },
      { text: "Press Run.", strong: true },
    ]);
  });

  it("keeps two emphasized runs apart instead of joining them into one", () => {
    /*
     * A beat naming two controls emphasizes both. The text between them is
     * plain and stays plain: a parser that ran from the first opening marker
     * to the last closing one would bold the connective as well, which reads
     * as one instruction where the author wrote two.
     */
    expect(beatSegments("Open **Config**, then press **Run**.")).toEqual([
      { text: "Open ", strong: false },
      { text: "Config", strong: true },
      { text: ", then press ", strong: false },
      { text: "Run", strong: true },
      { text: ".", strong: false },
    ]);
  });

  it("leaves a lone asterisk exactly where the author put it", () => {
    /*
     * An asterisk is a character a tutorial sentence may legitimately contain
     * — a footnote mark, a glob, a multiplication sign. Treating it as the
     * opening of a span would emphasize everything after it, and the author
     * would have no way to say they meant the character.
     */
    expect(beatSegments("Match every file with *.csv in the folder.")).toEqual([
      { text: "Match every file with *.csv in the folder.", strong: false },
    ]);
  });

  it("leaves an unclosed emphasis as the characters that were typed", () => {
    /*
     * A typo in tutorial copy should cost the author a stray pair of asterisks
     * on screen, which is visible and fixable, rather than a line that renders
     * bold from the mistake to the end of the beat — the failure mode where
     * the emphasis stops meaning anything and nobody can see why.
     */
    expect(beatSegments("This one matters: **be careful here")).toEqual([
      { text: "This one matters: **be careful here", strong: false },
    ]);
  });

  it("has nothing to say about an empty beat", () => {
    // A step with no text still renders the panel, so this is a real input and
    // not a defensive branch: an empty line is an empty line area.
    expect(beatSegments("")).toEqual([]);
  });
});

describe("counting the characters the reader will see", () => {
  it("counts the words and not the markers", () => {
    /*
     * The number the typewriter reveals in. The raw line is four characters
     * longer than what lands on screen, and revealing by raw index would pause
     * twice on nothing in the middle of the sentence.
     */
    const line = "A block is a unit. **Drag Load onto the canvas.**";
    expect(beatLength(beatSegments(line))).toBe(line.length - 4);
  });

  it("counts every character of a line that carries no markup", () => {
    const line = "The workflow executes top to bottom.";
    expect(beatLength(beatSegments(line))).toBe(line.length);
  });

  it("counts nothing for a beat with nothing in it", () => {
    expect(beatLength(beatSegments(""))).toBe(0);
  });
});
