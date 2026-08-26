/**
 * ADR-053 Learning Center (#2135) — the markup a beat may carry.
 *
 * A beat is a spoken sentence, not a document, and it understands two
 * constructs: `**like this**` and `[like this](doc:page)`. That narrowness is the design rather than an
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
      { text: "A block is SciStudio's basic unit of data processing.", strong: false, doc: null },
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
      { text: "A block is a unit. ", strong: false, doc: null },
      { text: "Drag Load onto the canvas.", strong: true, doc: null },
      { text: " It goes anywhere.", strong: false, doc: null },
    ]);
  });

  it("emits no empty run when the emphasis opens the line", () => {
    /*
     * There is no plain text before the marker, and inventing a zero-length
     * run for it would put an empty element into the panel on every such beat
     * — harmless to look at and noise to assert against.
     */
    expect(beatSegments("**Press Run.** The workflow executes top to bottom.")).toEqual([
      { text: "Press Run.", strong: true, doc: null },
      { text: " The workflow executes top to bottom.", strong: false, doc: null },
    ]);
  });

  it("emits no empty run when the emphasis closes the line", () => {
    expect(beatSegments("Everything is ready. **Press Run.**")).toEqual([
      { text: "Everything is ready. ", strong: false, doc: null },
      { text: "Press Run.", strong: true, doc: null },
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
      { text: "Open ", strong: false, doc: null },
      { text: "Config", strong: true, doc: null },
      { text: ", then press ", strong: false, doc: null },
      { text: "Run", strong: true, doc: null },
      { text: ".", strong: false, doc: null },
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
      { text: "Match every file with *.csv in the folder.", strong: false, doc: null },
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
      { text: "This one matters: **be careful here", strong: false, doc: null },
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

describe("a link to a page of the user guide", () => {
  it("carries the page out of the sentence and leaves the words in it", () => {
    /*
     * #2083 — core tutorial 3's last beat has to hand the reader to the
     * provider installation guide, which lives on the other side of closing
     * the project. Naming the page in prose and leaving them to find it is
     * what this exists instead of.
     */
    expect(
      beatSegments("If you have not installed one, [the guide is here](doc:ai-assistant)."),
    ).toEqual([
      { text: "If you have not installed one, ", strong: false, doc: null },
      { text: "the guide is here", strong: false, doc: "ai-assistant" },
      { text: ".", strong: false, doc: null },
    ]);
  });

  it("counts only what the reader sees, so the typewriter does not stall on the markers", () => {
    const segments = beatSegments("Read [the guide](doc:ai-assistant) first.");
    expect(beatLength(segments)).toBe("Read the guide first.".length);
  });

  it("leaves a link to anywhere else as the characters the author typed", () => {
    /*
     * The target vocabulary is closed on purpose: a beat that could name any
     * URL is a beat that could send a reader anywhere. Anything but `doc:`
     * is not markup, and survives as text.
     */
    expect(beatSegments("See [the site](https://example.com).")).toEqual([
      { text: "See [the site](https://example.com).", strong: false, doc: null },
    ]);
  });
});
