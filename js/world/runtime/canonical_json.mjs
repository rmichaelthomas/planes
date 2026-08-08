// js/world/runtime/canonical_json.mjs — a deterministic, whitespace-free,
// sorted-key text form of a plain JSON-shaped value.
//
// Mirrors world_event_log.mjs's own canonicalEventString (and its Python
// sibling in world_event_log.py's _canonical_event_string) exactly, for
// the same reason: two independently-serialized copies of an identical
// logical value must produce an identical string — and therefore an
// identical hash — regardless of the two languages' own differing
// object/dict key-insertion-order conventions. Pulled out to its own leaf
// module (zero dependencies) so both worker.mjs (the "save" message
// handler) and crossing_persistence.mjs (replay/verify) can import it
// without either importing the other.
export function canonicalJSON(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJSON).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJSON(value[k])}`).join(",")}}`;
}
