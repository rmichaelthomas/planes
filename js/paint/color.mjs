// js/paint/color.mjs — OKLCH to sRGB, pure arithmetic (planes-drawing-
// protocol-v1.md §4, normative).
//
// This is the ONLY definition of the conversion in the repo. Both renderers
// import it: painter.mjs turns the result into a canvas `rgba(...)` string,
// svg.mjs into a presentation attribute plus a separate opacity. Two
// renderers that each converted colour their own way would agree on every
// test anyone thought to write and disagree on the first colour nobody did.
//
// No CSS `oklch()` string and no dependency, so this runs identically in
// every browser and is testable headless. Structure: OKLCH -> OKLab -> LMS
// cubed -> linear sRGB matrix -> gamma. Out-of-gamut colours clamp silently,
// per channel (specification §4.2) — clamping the LINEAR value before the
// gamma curve is what makes that well-defined, since a negative linear
// channel has no real gamma-corrected value.

function oklchToLinearSrgb(L, C, H) {
  const hRad = (H * Math.PI) / 180;
  const a = C * Math.cos(hRad);
  const b = C * Math.sin(hRad);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;

  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;

  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

function linearToGamma(c) {
  const clamped = Math.max(0, Math.min(1, c));
  return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
}

// OKLCH -> sRGB, each output channel 0-1.
export function oklchToRgb(L, C, H) {
  const [rl, gl, bl] = oklchToLinearSrgb(L, C, H);
  return [linearToGamma(rl), linearToGamma(gl), linearToGamma(bl)];
}

const to255 = (n) => Math.round(n * 255);

// `rgb(r, g, b)` — the opaque form, for `background`, which the protocol
// gives no alpha channel.
export function rgbString(L, C, H) {
  const [r, g, b] = oklchToRgb(L, C, H);
  return `rgb(${to255(r)}, ${to255(g)}, ${to255(b)})`;
}

// `rgba(r, g, b, a)` — canvas carries alpha inside the colour string.
export function rgbaString([L, C, H, A]) {
  const [r, g, b] = oklchToRgb(L, C, H);
  return `rgba(${to255(r)}, ${to255(g)}, ${to255(b)}, ${A})`;
}

// `#rrggbb` — SVG carries alpha in a separate `*-opacity` attribute, so the
// colour itself has no alpha to express. Same three channels, same rounding.
export function rgbHex(L, C, H) {
  const [r, g, b] = oklchToRgb(L, C, H);
  const hex = (n) => to255(n).toString(16).padStart(2, "0");
  return `#${hex(r)}${hex(g)}${hex(b)}`;
}
