import { parseAtlas } from "../paint/a_crossing.mjs";
import { card } from "../paint/why.mjs";

const TABS = new Set(["revision", "atlas", "why", "source", "surface"]);

export function createArchiveController({ loadSource = async () => null, loadSurface = async () => null } = {}) {
  const state = {
    tab: "revision",
    source: null,
    surface: null,
    revision: "The crossing is preparing.",
    landings: [],
    events: [],
    seed: null,
    result: null,
    subjects: [],
    selected: null,
  };
  let sourcePromise = null;
  let surfacePromise = null;

  return {
    state,
    async open(tab = "revision") {
      if (!TABS.has(tab)) throw new RangeError(`unknown archive tab: ${tab}`);
      state.tab = tab;
      if (tab === "source" && state.source === null) {
        sourcePromise ??= Promise.resolve(loadSource()).then((value) => { state.source = value; return value; });
        await sourcePromise;
      }
      if (tab === "surface" && state.surface === null) {
        surfacePromise ??= Promise.resolve(loadSurface()).then((value) => { state.surface = value; return value; });
        await surfacePromise;
      }
      return state;
    },
    update({ result, subjects = [], events = [], seed = null, selected = null } = {}) {
      state.result = result ?? state.result;
      state.subjects = subjects;
      state.events = events.map((event) => ({ ...event }));
      state.seed = seed;
      state.selected = selected;
      state.revision = result?.state?.revision ?? state.revision;
      state.landings = result ? parseAtlas(result.lines).filter(({ kind }) => kind === "landing") : state.landings;
      return state;
    },
  };
}

const escapeText = (value) => String(value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

export function createCrossingArchive({ root, loadSource, loadSurface, restoreFocus = () => {} } = {}) {
  if (!root) throw new TypeError("createCrossingArchive requires a dialog root");
  const controller = createArchiveController({ loadSource, loadSurface });
  let sourceRendered = false;

  const renderTabs = () => {
    root.querySelectorAll("[data-tab]").forEach((button) => button.setAttribute("aria-selected", String(button.dataset.tab === controller.state.tab)));
    root.querySelectorAll("[data-view]").forEach((view) => view.classList.toggle("active", view.dataset.view === controller.state.tab));
  };

  const renderRevision = () => {
    const { state } = controller;
    root.querySelector("#archive-revision").textContent = state.revision;
    root.querySelector("#archive-revision-title").textContent = state.result?.state?.phase === "arrived" ? "The landing receives the line" : state.result?.state?.phase === "crossing" ? "The cord takes the water" : "The condition in view";
    root.querySelector("#archive-standing").textContent = `The ninety-minute standard stands. ${state.result?.state?.need ?? "Care"} remains the active Passage condition.`;
    root.querySelector("#archive-run").textContent = `Seed ${state.seed ?? "—"} · ${state.events.length} ordered input${state.events.length === 1 ? "" : "s"} · local simulation`;
    root.querySelector("#archive-replay").innerHTML = `<li>Horizon watch · seed ${escapeText(state.seed ?? "—")}</li>` + state.events.map((event, index) => `<li>${String(index + 1).padStart(2, "0")} · ${escapeText(event.kind)} / ${escapeText(event.choice ?? event.subject)}</li>`).join("");
  };

  const renderWhy = () => {
    const { state } = controller;
    const subject = state.subjects.find(({ id }) => id === state.selected);
    const title = root.querySelector("#archive-why-title");
    const body = root.querySelector("#archive-why");
    if (!subject || !state.result) {
      title.textContent = "Select something in the world";
      body.innerHTML = "<p>Every active object can lead back to the Planes value and source line that placed it here.</p>";
      return;
    }
    const details = card(subject.node, { annotations: state.result.annotations, title: subject.id.replaceAll("-", " "), line: subject.sourceLine });
    const because = details.because[0]?.text;
    title.textContent = subject.id.replaceAll("-", " ");
    body.innerHTML = `<div class="archive-grid"><div class="archive-card"><h4>Planes origin</h4><p>${escapeText(details.origin.text)}</p><p>Source line ${subject.sourceLine}</p></div><div class="archive-card"><h4>Because</h4><p>${escapeText(because || "This visible subject is derived from the current Planes state and inputs.")}</p></div></div>`;
  };

  const renderSource = () => {
    if (sourceRendered || controller.state.source === null) return;
    const lines = String(controller.state.source).split("\n");
    const hot = controller.state.subjects.find(({ id }) => id === controller.state.selected)?.sourceLine;
    root.querySelector("#archive-source-slot").innerHTML = `<pre class="archive-code">${lines.map((line, index) => `${index + 1 === hot ? "▶" : " "}${String(index + 1).padStart(3, "0")}  ${escapeText(line)}`).join("\n")}</pre>`;
    sourceRendered = true;
  };

  const render = () => { renderTabs(); renderRevision(); renderWhy(); renderSource(); };

  root.querySelector(".archive-tabs").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) return;
    await controller.open(button.dataset.tab);
    render();
  });
  root.querySelector("#close-archive").addEventListener("click", () => root.close());
  root.addEventListener("click", (event) => { if (event.target === root) root.close(); });
  root.addEventListener("close", restoreFocus);

  return {
    async open(tab = "revision", selection = null) {
      if (selection) controller.state.selected = selection;
      await controller.open(tab);
      render();
      if (!root.open) root.showModal();
      root.querySelector(`[data-tab="${tab}"]`)?.focus();
    },
    close() { if (root.open) root.close(); },
    update(value) { controller.update(value); if (root.open) render(); },
    state: controller.state,
    destroy() { if (root.open) root.close(); },
  };
}
