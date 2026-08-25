/**
 * ADR-053 Learning Center (#2136) — which face a beat is delivered with.
 *
 * The expression is authored per beat (FR-011f), so what is left on this side
 * is a lookup and its two failure modes: a beat the author said nothing about,
 * and a name this build does not have a drawing for.
 */

import { describe, expect, it } from "vitest";

import { DEFAULT_MIO_MOOD, MIO_MOOD_NAMES, avatarFor, moodAt, spriteFor } from "../mio";

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
    for (const mood of MIO_MOOD_NAMES) {
      expect(spriteFor(mood, "left")).not.toBe(spriteFor(mood, "right"));
      expect(avatarFor(mood, "left")).not.toBe(avatarFor(mood, "right"));
    }
  });
});
