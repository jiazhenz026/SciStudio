/**
 * ADR-053 Learning Center (#2136) — the tutorial's character, and which face she wears.
 *
 * The expression is **derived, never transmitted**. Everything below is read
 * off state the session already carries: whether the step's condition holds,
 * whether it has one at all, whether the session or the last trigger failed,
 * and how far through the step's beats the reader has read. Nothing new crosses
 * the API for it, and no manifest has to declare a mood — which also means the
 * six levels get this without any of their text being touched.
 *
 * **Two sprite sets, not one flipped at render time.** The art is drawn facing
 * screen-left. Standing at the left of a dialogue box, that turns her away from
 * the text she is speaking, so she has to face the other way there — and the
 * mirrored copy is a real file rather than a CSS transform. Baking it keeps the
 * asset the browser paints identical to the asset in the library, and leaves
 * room for either side to be replaced later with art actually drawn for it
 * instead of reflected into it.
 *
 * **`curious` is never mirrored.** Reflection is a fact about pixels, not about
 * drawing: her pose survives it, but the purple question mark floating beside
 * her head does not, and a backwards `?` is the one thing in the frame a reader
 * is guaranteed to read. She keeps her own orientation in that expression on
 * both sides, which costs her facing her dialogue and saves the glyph. Any
 * expression that grows a letterform later belongs in `NEVER_MIRRORED` with it.
 *
 * Keyed by **which side she stands on**, not by which way she faces, because
 * that is what the caller knows: `placeDialogue` decides a side, and this maps
 * it. A set named for the facing would make every call site do the inversion.
 *
 * Within a set the sprites share one canvas, one scale and one eye anchor, so
 * swapping expressions moves nothing but the face.
 */

import avatarMirroredAngry from "../../assets/mio/avatar-mirrored/angry.webp";
import avatarMirroredError from "../../assets/mio/avatar-mirrored/error.webp";
import avatarMirroredExplain from "../../assets/mio/avatar-mirrored/explain.webp";
import avatarMirroredFocus from "../../assets/mio/avatar-mirrored/focus.webp";
import avatarMirroredIdle from "../../assets/mio/avatar-mirrored/idle.webp";
import avatarMirroredSuccess from "../../assets/mio/avatar-mirrored/success.webp";
import avatarAngry from "../../assets/mio/avatar/angry.webp";
import avatarCurious from "../../assets/mio/avatar/curious.webp";
import avatarError from "../../assets/mio/avatar/error.webp";
import avatarExplain from "../../assets/mio/avatar/explain.webp";
import avatarFocus from "../../assets/mio/avatar/focus.webp";
import avatarIdle from "../../assets/mio/avatar/idle.webp";
import avatarSuccess from "../../assets/mio/avatar/success.webp";
import mirroredAngry from "../../assets/mio/mirrored/angry.webp";
import mirroredError from "../../assets/mio/mirrored/error.webp";
import mirroredExplain from "../../assets/mio/mirrored/explain.webp";
import mirroredFocus from "../../assets/mio/mirrored/focus.webp";
import mirroredIdle from "../../assets/mio/mirrored/idle.webp";
import mirroredSuccess from "../../assets/mio/mirrored/success.webp";
import angry from "../../assets/mio/angry.webp";
import curious from "../../assets/mio/curious.webp";
import error from "../../assets/mio/error.webp";
import explain from "../../assets/mio/explain.webp";
import focus from "../../assets/mio/focus.webp";
import idle from "../../assets/mio/idle.webp";
import success from "../../assets/mio/success.webp";

import type { DialogueSide } from "./placeDialogue";

/** The tutorial's speaker. Named here so no component spells it. */
export const MIO_NAME = "Mio";

export const MIO_MOOD_NAMES = [
  "idle",
  "explain",
  "curious",
  "focus",
  "success",
  "error",
  "angry",
] as const;

export type MioMood = (typeof MIO_MOOD_NAMES)[number];

/**
 * Expressions whose art is shown in its own orientation on both sides.
 *
 * One member today. The module docstring has the reason; this is the single
 * place the fact is written down, so the sprite maps, the avatar maps and the
 * layout inset cannot disagree about it.
 */
const NEVER_MIRRORED: ReadonlySet<MioMood> = new Set<MioMood>(["curious"]);

/** Drawn facing screen-left: the set for a character standing on the right. */
const FACING_LEFT: Record<MioMood, string> = {
  idle,
  explain,
  curious,
  focus,
  success,
  error,
  angry,
};

/** The mirrored files: the set for a character standing on the left. */
const FACING_RIGHT: Record<MioMood, string> = {
  idle: mirroredIdle,
  explain: mirroredExplain,
  // Her own orientation, on this side too: see NEVER_MIRRORED.
  curious,
  focus: mirroredFocus,
  success: mirroredSuccess,
  error: mirroredError,
  angry: mirroredAngry,
};

export const MIO_SPRITES: Record<DialogueSide, Record<MioMood, string>> = {
  left: FACING_RIGHT,
  right: FACING_LEFT,
};

/** The sprite she wears for *mood*, standing on *side* and facing her dialogue. */
export function spriteFor(mood: MioMood, side: DialogueSide): string {
  return MIO_SPRITES[side][mood];
}

/**
 * The same six faces, cropped square for the compact form.
 *
 * One crop box serves all six, which is a dividend of the aligned set: with the
 * eye in the same place in every sprite, a box that frames one frames them all.
 * Shipped with the background still transparent so the surface rounds it and
 * chooses its own backing, rather than baking a circle no layout can undo.
 */
const AVATAR_FACING_LEFT: Record<MioMood, string> = {
  idle: avatarIdle,
  explain: avatarExplain,
  curious: avatarCurious,
  focus: avatarFocus,
  success: avatarSuccess,
  error: avatarError,
  angry: avatarAngry,
};

const AVATAR_FACING_RIGHT: Record<MioMood, string> = {
  idle: avatarMirroredIdle,
  explain: avatarMirroredExplain,
  // The crop keeps the question mark, so the crop keeps the rule.
  curious: avatarCurious,
  focus: avatarMirroredFocus,
  success: avatarMirroredSuccess,
  error: avatarMirroredError,
  angry: avatarMirroredAngry,
};

export const MIO_AVATARS: Record<DialogueSide, Record<MioMood, string>> = {
  left: AVATAR_FACING_RIGHT,
  right: AVATAR_FACING_LEFT,
};

/** The avatar for *mood*, sitting on *side* of its line and facing it. */
export function avatarFor(mood: MioMood, side: DialogueSide): string {
  return MIO_AVATARS[side][mood];
}

/**
 * The one face the compact form wears, whatever the beat declares.
 *
 * The chat line is a small floating thing that appears next to a control the
 * reader is being asked to look at; it is there to point, not to perform. An
 * expression changing inside a 36px circle beside the thing they are meant to
 * be looking at competes with it and reads as noise. The standing form keeps
 * the full range, because there she is what is being looked at.
 *
 * Facing right, since the avatar sits to the left of its own line.
 */
export const MIO_COMPACT_AVATAR = MIO_AVATARS.left.idle;

/** The sprite canvas, in its own pixels. The surface scales it; the ratio is fixed. */
export const MIO_CANVAS = { width: 576, height: 494 } as const;

/**
 * Transparent margin between each edge of the canvas and her silhouette, in
 * canvas pixels, measured on the art as drawn.
 *
 * The aligned set fixes her *eye* in the canvas, not her outline: an arm raised
 * in one pose and folded in another reach different distances, so the empty
 * band beside her is not the same width twice. A panel placed a fixed distance
 * from the image edge would therefore sit against her cheek in one expression
 * and well clear of it in the next -- the gap would move every time her face
 * changed, which is the one moment it is being looked at. Subtracting the band
 * makes the gap the reader sees the gap the layout asked for.
 *
 * Both edges are recorded rather than only the facing one. For a mirrored mood
 * the two coincide -- reflection swaps the bands along with the pose, so the
 * band against the panel is `left` on either side -- but `curious` is not
 * mirrored, and on the left she meets her panel with the other side of her
 * body. `facingInset` is what resolves which.
 *
 * Measured from the library, not guessed. Regenerate with `_source/realign.py`
 * in the asset library if the art is ever recut or rescaled.
 */
export const MIO_MARGINS: Record<MioMood, { readonly left: number; readonly right: number }> = {
  idle: { left: 100, right: 106 },
  explain: { left: 102, right: 51 },
  curious: { left: 108, right: 119 },
  focus: { left: 53, right: 96 },
  success: { left: 88, right: 105 },
  error: { left: 100, right: 128 },
  angry: { left: 106, right: 88 },
};

/**
 * The empty band between her silhouette and the panel, for *mood* on *side*.
 *
 * The panel sits on the side she faces. Mirrored, that is always the `left`
 * band of the art as drawn -- reflection carries it to whichever edge now faces
 * the panel. Un-mirrored on the left she is turned away from her own dialogue,
 * so the band the panel actually meets is `right`.
 */
export function facingInset(mood: MioMood, side: DialogueSide): number {
  const margins = MIO_MARGINS[mood];
  return side === "left" && NEVER_MIRRORED.has(mood) ? margins.right : margins.left;
}

/** What a beat that names no expression is delivered with. Matches the backend. */
export const DEFAULT_MIO_MOOD: MioMood = "idle";

/**
 * The expression for the beat at *index*, or the default.
 *
 * The expression is **authored, never derived** (FR-011f). It used to be read
 * off the step's state — mid-beat meant explaining, an unmet condition meant
 * asking — and the result was a face that changed on the runtime's schedule
 * rather than on the writing's. Which line she smiles on is a writing decision
 * and the manifest carries it, as a prefix on the line itself.
 *
 * Unknown names fall back rather than throw, for the reason the wire type is
 * optional: a face is not worth a blank tutorial.
 */
export function moodAt(moods: readonly string[] | undefined, index: number): MioMood {
  const named = moods?.[index];
  return named !== undefined && (MIO_MOOD_NAMES as readonly string[]).includes(named)
    ? (named as MioMood)
    : DEFAULT_MIO_MOOD;
}
