# The Garden — Scene Specification

**For:** `paint/garden.planes`
**Reference implementation:** `the-living-garden.html` — a JavaScript mockup, retired once the page it specified existed. Every number below was extracted from it, which is why this document is now the authority rather than a transcription of one: the mockup is gone, and where it once won a disagreement, these numbers do.

---

## 0. What this program is, and is not

**This is not a demonstration of protocol v2.** It is a picture. A verb that does not serve the picture does not appear.

The current `paint/garden.planes` fails this test. Its effect surface shows three distinct `dash` patterns, two literal `alpha` values, both `blend` modes and a `clip` — that is a conformance exercise wearing a garden costume. Delete it and start from this document.

Expected verb usage in a correct implementation:

| Verb | Times it should appear | Where |
|---|---|---|
| `gradient` | 3 | sky, ground, vignette |
| `shadow` | ~5 | sun/moon glow, flower centres, fireflies, wet-ground sheen. **Not on everything.** |
| `blend add` | 1 region | fireflies at night, and the sun/moon glow |
| `alpha` | as needed | clouds, stars, rain — always computed, never a magic literal toggled twice |
| `dash` | **0** | nothing in this scene is dashed |
| `clip` | **0** | nothing in this scene is masked |
| `ellipse` rotation | ~60 | every leaf, every petal |

If `dash` or `clip` appear in the output, the program is wrong regardless of how it looks.

---

## 1. Canvas and the two inputs

Drawing area 1720 × 900. Ground line at **y = 0.815 × height** = 733.5.

The whole picture is a pure function of `day` and `seed`. No value carries across ticks. `day` advances continuously; `phase` is `day mod 1`, where **phase 0 is midnight** and phase 0.5 is noon.

Derived once per frame, used everywhere:

| Value | Definition |
|---|---|
| `phase` | `day mod 1` |
| `sunEl` | `sine of ((phase − 0.25) × 360)` — ranges −1 to 1, peaks at noon |
| `light` | `sunEl + 0.18`, divided by 0.72, clamped to 0…1 |
| `night` | `1 − light` |
| `wet` | `fbm of (day × 1.6 + 3.5)`, × 1.55, − 0.62, floored at 0 → roughly 0…0.55 |
| `wind` | `0.35 + fbm of (day × 4) × 1.1` |
| `grow` | `0.34 + day × 0.16`, capped at 1 |

**Noise.** `hash of (i, seed)` is an integer hash returning 0…1. `noise of (x, seed)` blends `hash of (floor x)` and `hash of (floor x + 1)` with a cosine smoothstep: `(1 − cosine of (frac × 180)) / 2`. `fbm` is three octaves: `noise(x) × 0.6 + noise(x × 2.3) × 0.27 + noise(x × 5.1) × 0.13`.

The cosine is why this program's numbers are approximate, and that is intentional — it is what makes the effect surface say so.

---

## 2. Layer order — draw in exactly this sequence

Everything overlaps correctly only in this order. This is the single most important section.

1. Sky gradient
2. Stars — night only
3. Sun or moon, with glow
4. Clouds
5. Far hills — three parallax layers
6. Ground
7. Tree
8. Plants, each with leaves and a flower
9. Rain — only when wet
10. Bees (day) **or** fireflies (night)
11. Foreground grass
12. Vignette

---

## 3. Sky

A vertical gradient from the top of the canvas to the ground line. The protocol's `gradient` is two-stop, so use **two stacked gradients** — top→middle over the upper 55%, middle→low over the remainder — rather than one.

Palette keyframes, interpolated by `phase`. OKLCH values are starting estimates; tune against the mockup's RGB.

| phase | top (L C H) | middle | low | |
|---|---|---|---|---|
| 0.00 | 0.18 0.06 265 | 0.24 0.06 265 | 0.28 0.05 262 | midnight |
| 0.17 | 0.28 0.09 285 | 0.44 0.10 330 | 0.62 0.11 25 | first light |
| 0.24 | 0.52 0.09 250 | 0.68 0.13 40 | 0.84 0.08 68 | dawn |
| 0.34 | 0.62 0.09 245 | 0.78 0.06 240 | 0.90 0.02 235 | morning |
| 0.50 | 0.60 0.10 245 | 0.75 0.07 238 | 0.88 0.03 232 | noon |
| 0.68 | 0.62 0.08 250 | 0.70 0.10 45 | 0.82 0.09 62 | late |
| 0.77 | 0.36 0.08 285 | 0.58 0.14 30 | 0.74 0.12 52 | dusk |
| 0.86 | 0.22 0.06 268 | 0.28 0.06 266 | 0.32 0.05 264 | night falls |

Interpolate L and C linearly and **H on the shorter arc**.

---

## 4. Stars

150 of them, positions fixed by `hash of (i, 7)` — they do not drift. `x = hash(i) × width`, `y = hash(i + 900) × groundY × 0.78`, radius `0.7 + hash(i + 50) × 1.5`.

Alpha is `night × twinkle × 0.85` where `twinkle = 0.55 + 0.45 × sine of (day × 612 + phase_i × 57)`. Skip the whole layer when `night < 0.05`.

---

## 5. Sun and moon

One body, on an arc. Sun when `phase` is 0.25 to 0.75; moon otherwise.

Let `p` be the progress across the sky: `(phase − 0.25) × 2` for the sun, `((phase + 0.25) mod 1) × 2` for the moon.

- `x = p × width × 1.06 − width × 0.03`
- `y = groundY − sine of (p × 180) × groundY × 0.78`

Draw it as **two marks**, not one:

1. The glow — `blend add`, `shadow 0 0 <blur> <colour>` with blur 52 for the sun and 30 for the moon, drawing a circle of radius 110 (sun) or 66 (moon) at low alpha. Sun glow `0.92 0.10 75`, alpha `0.30 + light × 0.35`. Moon glow `0.88 0.04 250`, alpha 0.30.
2. The disc — `blend normal`, no shadow, radius 36 (sun) or 25 (moon), nearly opaque. Sun `0.97 0.05 85`, moon `0.94 0.02 260`.

---

## 6. Clouds

Seven. Each is five overlapping ellipses, so the silhouette is lumpy rather than oval.

For cloud `i`: drift `x = ((noise of (i × 2.1 + day × 0.24) × 1.4 + day × 0.11 × (0.5 + i × 0.12)) mod 1.35 − 0.18) × width`. Vertical `y = groundY × 0.13 + noise of (i × 7.7) × groundY × 0.36`. Scale `s = 0.55 + noise of (i × 3.3) × 0.9`.

The five puffs, for `b` from 0 to 4: offset `(b − 2) × 46 × s` horizontally, `sine of (b × 109 + i × 57) × 13 × s` vertically, radii `(58 − |b − 2| × 11) × s` by `(30 − |b − 2| × 5) × s`.

Colour: lightness `0.35 + light × 0.65`, darkened toward `0.45` as `wet` rises. Alpha `0.30 + min(1, wet × 1.7) × 0.34`. Soften with `shadow 0 0 16` in the cloud's own colour — this is the blur the mockup gets from a filter.

---

## 7. Far hills

Three layers, back to front, `L` from 0 to 2. Each is a `shape` with a `vertex` every 26 pixels across the width, then down to the bottom corners and `close`.

`y = groundY − 70 − L × 34 − fbm of (x × 0.0016 + L × 9 + day × 0.0096) × (110 − L × 22)`

Colour darkens with distance and lightens with `light`: base lightness `0.10 + light × 0.20`, scaled by `1 − depth × 0.28` where `depth = L / 2`. Hue 145, chroma 0.04. Alpha `0.55 + L × 0.18`.

---

## 8. Ground

A gradient from the ground line to the bottom. Top stop: lightness `(0.22 − wetK × 0.06) × (0.5 + light × 0.7)` where `wetK = min(1, wet × 2.4)`, hue 120, chroma 0.05. Bottom stop: lightness 0.08, hue 130, chroma 0.03.

When `wetK > 0.1`, add a sheen — `blend add`, a wide low rect just below the ground line at `0.75 0.05 230`, alpha `wetK × 0.12`, with `shadow 0 0 20` in the same colour.

---

## 9. The tree

At `x = 0.135 × width`, rooted at the ground line. One function calling itself twice, seven levels deep.

Root call: angle straight up, length 118, width 17.

Each branch: draw a line from its start to `start + (cos angle, sin angle) × length`, then recurse twice —
- angle `− (0.30 + hash × 0.34)` radians, length × `(0.70 + hash × 0.12)`, width × 0.68
- angle `+ (0.30 + hash₂ × 0.34)` radians, length × `(0.70 + hash₂ × 0.12)`, width × 0.68

Stop at depth 7 or length below 7.

Sway: add `sine of (day × 60 + depth × 32) × depth² × 0.32 × wind` to the branch's x, at 35% strength at the start point and full strength at the end, so the trunk barely moves and the tips move most.

Bark: lightness `0.10 + light × 0.28`, hue 60, chroma 0.03.

**Leaves only at depth 5 and deeper** — an ellipse at the branch tip, radii 13 × 9, rotated by the branch's own index. Hue moves from 96 toward 32 as `day` advances (`96 − min(1, day × 0.13) × 64`), lightness `0.16 + light × 0.30`, chroma `0.10 + light × 0.06`, alpha 0.92.

The current build's tree reads as grey sticks with green dots because the leaves are too few, too small, and not clustered at the tips. Depth 5+ is roughly 96 leaves.

---

## 10. Plants

Twelve, `i` from 0 to 11. `x = 150 + i × ((width − 260) / 11)`.

- `g = noise of (i × 0.73 + day × 0.5, seed)` — this one number drives everything about the plant
- `height = (70 + g × 250) × grow`
- `lean = sine of (day × 66 + i × 97) × (6 + wind × 13) × (height / 260)`

**Stem** — a `shape` with one `curve` from `(x, groundY)` to `(x + lean, groundY − height)`, control points at `(x + lean × 0.6, groundY − height × 0.55)` doubled. Width `5 + g × 5`, round cap. Hue `132 − g × 26`, lightness `0.13 + (0.20 + light × 0.62) × 0.30`, chroma `0.09 + g × 0.05`.

**Leaves** — `2 + floor(g × 4)` of them, alternating sides. For leaf `l` of `lv`: fraction `q = 0.3 + (l / lv) × 0.6` up the stem, at `(x + lean × q, groundY − height × q)`. Side `+1` or `−1` alternating. Length `16 + g × 24`.

Draw as a **rotated ellipse**: centre `(leafX + side × length × 0.55, leafY)`, radii `length` by `length × 0.33`, rotation `side × (−24 − g × 13)` degrees. This is what the rotation argument is for; do not use `push`/`rotate`/`pop`.

**Flower** at the stem tip `(x + lean, groundY − height)`. Petal count `5 + floor(g × 3)`. Hue `(28 + g × 300) mod 360`.

For petal `k`: angle `(k / petals) × 360 + day × 69` degrees. Radius `rr = (5 + g × 13) × (0.30 + light × 0.85)` — **this is the opening**, and it is `light` that opens it. Ellipse centred at `(fx + cos(angle) × rr × 0.95, fy + sin(angle) × rr × 0.95)`, radii `rr × 0.72` by `rr × 0.44`, **rotated by the petal's own angle**.

Centre: a circle of radius `4 + g × 5`, hue 48, lightness `0.52 + light × 0.26`.

When `light > 0.55`, add a glow — `blend add`, `shadow 0 0 10` in the flower's hue, a circle of radius `20 + g × 16`, alpha `(light − 0.55) × 0.34`. Then `blend normal`.

---

## 11. Rain

Only when `wet > 0.06`. `floor(wet × 640)` short strokes, width 1.4, colour `0.85 0.03 240`, alpha `0.10 + wet × 0.34`.

Stroke `i` runs from `(x, y)` to `(x − 5, y + 19)`, where x and y are hash-scattered and offset by `day` so it falls.

---

## 12. Bees and fireflies

**Bees when `light > 0.30`.** Four. Bee `i` targets plant number `floor(noise of (i × 4.4 + day × 0.6) × 12)` and is drawn **at** a position that is a pure function of day — interpolate toward the target using a fraction derived from `day`, never by accumulating. Body: an ellipse 6.5 × 4.6, hue 85, lightness 0.85. A darker stripe ellipse 2.4 × 4.4 offset 2 right. Wing: an arc above, at low alpha.

**Fireflies when `light ≤ 0.30`.** Fourteen. `x = noise of (i × 2.7 + day × 1.56) × width`, `y = groundY − 60 − noise of (i × 5.3 + day × 1.32) × 300`.

Blink: `b = max(0, sine of (day × 192 + i × 132))` cubed.

`blend add`, `shadow 0 0 7` in `0.90 0.16 130`, a circle of radius 11 at alpha `b × 0.5`, then a bright core circle radius 2.3 at alpha `0.35 + b × 0.6`. Then `blend normal`.

**The fireflies are the only place in the scene that needs `blend add` on many overlapping marks.** That is what makes them look right.

---

## 13. Foreground grass

130 blades across the bottom. Blade `i` at `x = hash of (i, seed + 500) × width`, height `18 + hash of (i + 90) × 40`. A `shape` with a `curve` from `(x, height)` up to `(x + sway, canvasHeight − h)`, where `sway = sine of (day × 108 + i × 57) × 5 × wind`. Width 2.2. Dark: lightness `0.06 + light × 0.14`, hue 140, chroma 0.05.

---

## 14. Vignette

A radial `gradient` centred at `(width / 2, groundY × 0.6)`, transparent at radius `height × 0.28`, reaching alpha `0.30 + night × 0.22` black at radius `height × 0.92`. Drawn last, over everything.

---

## 15. Acceptance

Open `garden.html` at the given day and compare against the numbers below. (This step once read "open the mockup beside it"; the mockup has been retired, so the specification is what the picture is checked against.)

- [ ] Layer order matches §2 exactly.
- [ ] At day 0.5 the sky is blue, the sun is high, flowers are open, bees are out.
- [ ] At day 0.0 the sky is deep indigo, stars are visible, the moon is up, flowers are closed, fireflies are out and **brighten where they overlap**.
- [ ] Dawn and dusk pass through warm oranges, not straight from blue to black.
- [ ] The tree reads as a tree with foliage, not sticks with dots.
- [ ] Plants read as plants with tilted leaves and open flowers, not green blobs.
- [ ] Clouds are lumpy and soft-edged, not grey ovals.
- [ ] Nothing in the picture is dashed. Nothing is clipped.
- [ ] `shadow` appears on glows and the wet sheen only — the picture is mostly crisp.
- [ ] Scrubbing to the same day twice produces byte-identical PNGs.
