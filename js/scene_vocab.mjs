// js/scene_vocab.mjs — the single source of the tutor's teaching vocabulary
// (checkpoint v27.0 §420-421, build prompt §6.1). paint/scene.planes and
// tutor.html's read-only key both derive from the phrase lists below — the
// same "one source, read two ways" seam v18.0 named. scene.planes cannot
// import this file directly (a .planes module has no way to read JSON or
// .mjs), so its own `fail` message is a hand-written literal; what keeps the
// two from drifting is js/test/scene_rich.test.mjs, which runs every phrase
// below through the real scene.planes and asserts an unrecognised phrase's
// refusal names exactly this list — the same "one copy, read by the test"
// discipline garden.html's PENTATONIC table uses.
//
// The OKLCH numbers scene.planes actually paints with live only in
// scene.planes (§413's richness is the helper's business, not this module's)
// — the `color` here is a small, independent, ILLUSTRATIVE swatch for the
// key's reference dot, not a physics claim, exactly as mockup v7's own
// SKY_CHOICES/GROUND_CHOICES were independent of its stand-in renderer's
// SKY/GROUND objects. Colour values are explicitly NOT LOCKED (checkpoint
// v27.0, "WHAT IS NOT LOCKED").

// ---- the things a child can place, and their shape ------------------------
//
// Curated to what the taught curriculum (mockup v7's five-week arc) actually
// has her type — not an exhaustive dump of every callable in scene.planes.
// `flower`/`bee`/`firefly` (singular) remain real, working helpers (the
// paired ones are built out of them, §416), but no week's ghost text or key
// ever asks her to spell them, so they stay off this reference strip the
// same way an advanced builtin stays off a beginner's cheat sheet.
export const PLACEABLES = Object.freeze([
  Object.freeze({ name: "sun", shape: Object.freeze(["across", "down"]) }),
  Object.freeze({ name: "moon", shape: Object.freeze(["across", "down"]) }),
  Object.freeze({ name: "star", shape: Object.freeze(["across", "down"]) }),
  Object.freeze({ name: "two-bees", shape: Object.freeze(["across", "down"]) }),
  Object.freeze({ name: "two-fireflies", shape: Object.freeze(["across", "down"]) }),
  Object.freeze({ name: "two-flowers", shape: Object.freeze(["across", "how-tall"]) }),
]);

// ---- the fixed sets: sky and ground -----------------------------------
//
// Order matters: it is the order the key lists them in AND the order
// scene.planes's own refusal message lists them in (skyRefusalMessage/
// groundRefusalMessage below build that exact string).
export const SKY_PHRASES = Object.freeze([
  Object.freeze({ phrase: "early morning", color: "#f6dcc2" }),
  Object.freeze({ phrase: "middle of the afternoon", color: "#a9c6e8" }),
  Object.freeze({ phrase: "just before dark", color: "#6a4b78" }),
  Object.freeze({ phrase: "the middle of the night", color: "#1b2233" }),
]);

export const GROUND_PHRASES = Object.freeze([
  Object.freeze({ phrase: "wet grass", color: "#4f7a43" }),
  Object.freeze({ phrase: "dry grass", color: "#9aa05a" }),
  Object.freeze({ phrase: "dirt", color: "#6a4f38" }),
]);

// ---- naming and reasoning ------------------------------------------------

export const NAMING_WORDS = Object.freeze([
  Object.freeze({ name: "let", shape: Object.freeze(["name", "=", "number"]) }),
  Object.freeze({ name: "because", shape: Object.freeze(['"…"']) }),
]);

export const COORDINATE_NOTE =
  "Numbers are across and down from the top corner. Bigger down is lower.";

// ---- the exact refusal text scene.planes's `fail` lines carry -------------
//
// A test builds these and compares them, verbatim, against what running
// scene.planes with an unrecognised phrase actually raises — so a phrase
// added here with no matching edit in scene.planes fails the seam test
// loudly, rather than drifting silently the way two hand-kept lists would.
export function skyPhraseNames() {
  return SKY_PHRASES.map((p) => p.phrase);
}

export function groundPhraseNames() {
  return GROUND_PHRASES.map((p) => p.phrase);
}

export function skyRefusalMessage(feeling) {
  return (
    `"${feeling}" isn't a sky this program knows — try one of: ` +
    skyPhraseNames().join(", ")
  );
}

export function groundRefusalMessage(feeling) {
  return (
    `"${feeling}" isn't a ground this program knows — try one of: ` +
    groundPhraseNames().join(", ")
  );
}
