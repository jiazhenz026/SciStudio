/**
 * ADR-053 Learning Center (#2136) — which face a beat is delivered with.
 *
 * The expression is authored per beat (FR-011f), so what is left on this side
 * is a lookup and its two failure modes: a beat the author said nothing about,
 * and a name this build does not have a drawing for.
 */

import { describe, expect, it } from "vitest";

import {
  DEFAULT_MIO_MOOD,
  MIO_MARGINS,
  MIO_MOOD_NAMES,
  avatarFor,
  facingInset,
  moodAt,
  spriteFor,
} from "../mio";

describe("the expression a beat is delivered with", () => {
  it("takes the one the author wrote on that beat", () => {
    expect(moodAt(["idle", "explain", "curious"], 1)).toBe("explain");
    expect(moodAt(["idle", "explain", "curious"], 2)).toBe("curious");
  });

  it("rests when the beat named nothing", () => {
    // The backend's default, restated here because the wire field is optional.
    expect(moodAt(undefined, 0)).toBe(DEFAULT_MIO_MOOD);
    expect(moodAt([], 0)).toBe(DEFAULT_MIO_MOOD);
    expect(moodAt(["explain"], 3)).toBe(DEFAULT_MIO_MOOD);
  });

  it("rests rather than throwing on a name it has no drawing for", () => {
    /*
     * A backend a version ahead could name a seventh expression. A face is not
     * worth a blank tutorial, so an unknown one falls back the way an absent
     * one does.
     */
    expect(moodAt(["smug"], 0)).toBe(DEFAULT_MIO_MOOD);
  });

  it("has a sprite and an avatar for every name, on both sides", () => {
    /*
     * The vocabulary is the sprite set — `test_the_expression_vocabulary_is_
     * the_sprite_set` holds the other half of this, on the backend, where the
     * same six names are the manifest's.
     */
    for (const mood of MIO_MOOD_NAMES) {
      for (const side of ["left", "right"] as const) {
        expect(spriteFor(mood, side)).toBeTruthy();
        expect(avatarFor(mood, side)).toBeTruthy();
      }
    }
    expect(MIO_MOOD_NAMES).toContain(DEFAULT_MIO_MOOD);
  });

  it("gives the two sides different files, so she faces her own dialogue", () => {
    for (const mood of MIO_MOOD_NAMES.filter((name) => name !== "curious")) {
      expect(spriteFor(mood, "left")).not.toBe(spriteFor(mood, "right"));
      expect(avatarFor(mood, "left")).not.toBe(avatarFor(mood, "right"));
    }
  });

  it("shows `curious` in its own orientation on both sides, question mark included", () => {
    /*
     * The exception, pinned rather than left to be re-derived. Reflection is a
     * fact about pixels: the pose survives it and the purple `?` beside her
     * head does not, and a backwards question mark is the one thing in the
     * frame a reader is certain to read. Facing her dialogue is worth less than
     * that, so this mood is served un-mirrored on either side.
     *
     * Written as an equality rather than a filename so it keeps holding if the
     * art is ever recut: what matters is that one file serves both sides.
     */
    expect(spriteFor("curious", "left")).toBe(spriteFor("curious", "right"));
    expect(avatarFor("curious", "left")).toBe(avatarFor("curious", "right"));
  });

  it("measures her gap from whichever side of her the panel is on", () => {
    /*
     * A mirrored mood meets its panel with the same band on either side —
     * reflection carries it across — so the inset does not move. `curious` is
     * not mirrored, so on the left the panel meets her other side, and reading
     * the mirrored number there would put the gap out by the difference
     * between her two margins.
     */
    expect(facingInset("idle", "left")).toBe(facingInset("idle", "right"));
    expect(facingInset("curious", "right")).toBe(MIO_MARGINS.curious.left);
    expect(facingInset("curious", "left")).toBe(MIO_MARGINS.curious.right);
    expect(MIO_MARGINS.curious.left).not.toBe(MIO_MARGINS.curious.right);
  });
});
