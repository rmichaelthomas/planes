// js/paint/surface_pane.mjs — the computed effect surface pane: given a
// program's source and (optionally) the module loader that already resolved
// its graph, renders what analyseProgramGraph finds into a target element.
// Nothing is run to produce this — the same "computed, not declared, and
// never hidden" discipline paint.html's own surface pane has always
// followed (js/browser_main.mjs's analyseProgramGraph/surfaceReport).

import { analyseProgramGraph, surfaceReport } from "../browser_main.mjs";

export async function renderSurface(targetEl, src, { loader } = {}) {
  const { surface, error } = await analyseProgramGraph(src, { loader });
  if (error) {
    targetEl.textContent = `✗ ${error.tag}: ${error.message}`;
    return { error };
  }
  targetEl.textContent = surfaceReport(surface);
  return { surface };
}
