// js/paint/tick_scrubber.mjs — a tick scrubber: a range input plus optional
// back/forward steppers, wired to call back with whatever tick it lands on.
// It knows nothing about what a "day" means to the program driving it —
// that is entirely the caller's `max` and `onChange`. Shared so garden.html
// and tutor.html present the same control rather than two hand-wired ones.

export function createTickScrubber({ rangeEl, backEl, forwardEl, labelEl, max, onChange, labelText }) {
  const renderLabel = labelText || ((t) => String(t));

  rangeEl.min = "0";
  rangeEl.max = String(max);
  rangeEl.value = "0";
  if (labelEl) labelEl.textContent = renderLabel(0);

  // `fire`: false lets a caller set the displayed tick (e.g. on initial
  // load, or after changing `max`) without re-triggering a run of its own —
  // the caller runs the initial frame itself, once, rather than via this
  // side effect.
  function setTick(t, { fire = true } = {}) {
    const clamped = Math.max(0, Math.min(max, Math.round(t)));
    rangeEl.value = String(clamped);
    if (labelEl) labelEl.textContent = renderLabel(clamped);
    if (fire) onChange(clamped);
    return clamped;
  }

  function setMax(newMax) {
    max = newMax;
    rangeEl.max = String(max);
    setTick(Number(rangeEl.value), { fire: false });
  }

  rangeEl.addEventListener("input", () => setTick(Number(rangeEl.value)));
  if (backEl) backEl.addEventListener("click", () => setTick(Number(rangeEl.value) - 1));
  if (forwardEl) forwardEl.addEventListener("click", () => setTick(Number(rangeEl.value) + 1));

  return {
    setTick,
    setMax,
    getTick: () => Number(rangeEl.value),
  };
}
