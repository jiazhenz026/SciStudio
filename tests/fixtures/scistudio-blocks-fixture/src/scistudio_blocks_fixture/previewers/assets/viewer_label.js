/**
 * A sibling of the fixture previewer's entry module.
 *
 * Exists so the ADR-054 compatibility shim (FR-042) is tested against a bundle
 * that is more than one file: an ADR-048 previewer imported its neighbours by
 * relative path, and a shim that wrapped only the entry module would leave a
 * real package with a mount that throws on its first import. The shim copies
 * the whole bundle into the panel directory it generates, and `viewer.js`
 * imports this to prove it.
 */
export const LABEL = "fixture panel";
