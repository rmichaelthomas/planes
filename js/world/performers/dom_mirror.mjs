// js/world/performers/dom_mirror.mjs — the semantic DOM performer
// (design doc §10.4, build prompt §2/§3).
//
// THE ACCESSIBILITY/SELECTION SCAFFOLD, NOT THE LENS. §7.1 says a
// selectable subject carries a stable semantic ID, a human-readable name,
// keyboard/pointer/touch/accessible-DOM focus behavior, and a source-map
// path. This file gives every subject the DOM node §7.1 requires — nothing
// more. It does not expose Touch actions (move, change state, ask the
// co-builder, undo — §7.2's action families), because those are Living
// Lens, and the Living Lens is Phase 3 (design doc §25). A subject here is
// focusable and screen-reader-labeled; it does nothing when activated,
// because there is nothing yet for it to do.
//
// One focusable node per subject, kept in a `role="list"` container so
// keyboard users can tab through subjects the same way they would a list of
// results. Each node's semantic ID, name, and source-map path are exposed
// both via `aria-label` (spoken on focus) and a visually-hidden `<dl>`
// (readable by a screen reader's virtual cursor, not just on focus) — data
// attributes alone would not satisfy this, since assistive tech does not
// read `data-*`.

const VISUALLY_HIDDEN_STYLE =
  "position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;" +
  "clip:rect(0,0,0,0);white-space:nowrap;border:0;";

export class DomMirror {
  constructor(container) {
    if (!container) throw new TypeError("DomMirror requires a container element");
    this.container = container;
    this.container.setAttribute("role", "list");
    if (!this.container.hasAttribute("aria-label")) {
      this.container.setAttribute("aria-label", "World subjects (accessibility mirror)");
    }
    this.nodes = new Map();
  }

  // envelope: the same full, current, normalized world-v1 envelope
  // pixi_performer.mjs receives — see worker.mjs/main.mjs for how it's kept
  // current from the worker's snapshot + delta stream.
  applyEnvelope(envelope) {
    const id = envelope.identity.id;
    let entry = this.nodes.get(id);
    if (!entry) entry = this._create(id);
    const name = envelope.identity.displayName ?? id;
    const sourceMapPath = envelope.affordance?.sourceMapTarget ?? "(none declared)";
    const state = envelope.behavior?.stateMachine ?? "";
    entry.root.setAttribute("aria-label", `${name} (${id})${state ? `, ${state}` : ""}`);
    entry.idField.textContent = id;
    entry.nameField.textContent = name;
    entry.sourceField.textContent = sourceMapPath;
    entry.stateField.textContent = state;
  }

  removeSubject(id) {
    const entry = this.nodes.get(id);
    if (!entry) return;
    this.container.removeChild(entry.root);
    this.nodes.delete(id);
  }

  focusSubject(id) {
    this.nodes.get(id)?.root.focus();
  }

  _create(id) {
    const doc = this.container.ownerDocument;
    const root = doc.createElement("div");
    root.setAttribute("role", "listitem");
    root.tabIndex = 0;
    root.className = "world-subject-mirror";
    root.dataset.subjectId = id;

    const dl = doc.createElement("dl");
    dl.setAttribute("style", VISUALLY_HIDDEN_STYLE);
    const idField = fieldRow(doc, dl, "Semantic ID");
    const nameField = fieldRow(doc, dl, "Name");
    const sourceField = fieldRow(doc, dl, "Source");
    const stateField = fieldRow(doc, dl, "State");
    root.appendChild(dl);

    this.container.appendChild(root);
    const entry = { root, idField, nameField, sourceField, stateField };
    this.nodes.set(id, entry);
    return entry;
  }

  // Plain-data diagnostic snapshot — for the verify script and frame bench,
  // matching pixi_performer.mjs's snapshot()/spriteCount() shape.
  snapshot() {
    return Object.fromEntries(
      [...this.nodes.entries()].map(([id, e]) => [
        id,
        {
          label: e.root.getAttribute("aria-label"),
          source: e.sourceField.textContent,
          focusable: e.root.tabIndex === 0,
        },
      ]),
    );
  }

  count() {
    return this.nodes.size;
  }
}

function fieldRow(doc, dl, label) {
  const dt = doc.createElement("dt");
  dt.textContent = label;
  const dd = doc.createElement("dd");
  dl.append(dt, dd);
  return dd;
}
