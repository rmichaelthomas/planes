# The Planes Drawing Protocol

**Version 2**

A Planes program cannot draw. It can emit text. This document defines a text
format that a program emits and a renderer consumes, so that one program can be
drawn by many renderers without the program knowing which — or knowing that
anything is listening at all.

The program's effect surface is `console` for every renderer, because emitting
these lines is emitting text and nothing else.

---

## 1. The stream

A renderer consumes a sequence of lines, in order. Each line is either a
**command** or **prose**.

A command begins with the word `draw`, followed by a verb, followed by that
verb's arguments, separated by one or more spaces.

```
draw circle 200 100 40
```

Any line not beginning with `draw` is prose. The renderer does not interpret it
and passes it to whatever text surface it has. Prose may contain any words at
all, including verb names.

```
show "draw circle 200 100 40"     a command
show "close the file"             prose
show "end"                        prose
```

The prefix exists so that these two categories cannot collide. Without it, a
program printing the word `end` would silently close a path.

### 1.1 The version declaration

```
draw protocol 2
```

A stream may declare the protocol version it is written against. If present, the
declaration **must appear before the first drawing command**. A renderer cannot
refuse a picture it has already begun drawing.

- If absent, the version is 1.
- A second declaration in one stream, or one appearing after a drawing command,
  is an error.
- A renderer that does not implement the declared version **refuses the entire
  stream** and reports why. It does not draw the commands it recognises and
  discard the rest. A half-drawn picture with no error is the failure this
  declaration exists to prevent.

`protocol` is recognised in version 1 specifically so that a version-1 renderer
can refuse a version-2 stream. It is not a drawing command and changes nothing
about the picture.

This renderer implements versions 1 and 2. A stream that declares version 1 (or
declares nothing, which is version 1 per the rule above) may use any verb from
§6.1 through §6.5. A verb introduced in version 2 (§6.6's `gradient`, `shadow`,
`blend`, `clip`, `unclip`, plus §6.1's `alpha` and `dash`) used in such a stream
is an error — `verb-not-in-version` — naming `draw protocol 2` as the fix. This
is not a silently-ignored line and not a silent upgrade: a v1 stream's meaning
does not change out from under it just because the renderer also happens to
understand v2.

The one exception is the optional rotation argument on `ellipse` and `rect`
(§6.2, §9.2): it widens an *existing* v1 verb's arity rather than introducing a
new verb, and is accepted regardless of the stream's declared version.

---

## 2. The refusal contract

A line beginning with `draw` **is** a command. It is never reinterpreted as
prose.

The following are errors, reported with the offending line:

- an unrecognised verb
- the wrong number of arguments for a verb
- an argument that is not a valid number where a number is required
- a word argument outside its permitted set
- `vertex`, `curve` or `close` outside a `shape` … `end` block
- `end` without a preceding `shape`
- `pop` without a matching `push`
- a `shape` block still open at the end of the stream
- a `push` still unmatched at the end of the stream
- `unclip` without a matching `clip`
- a `clip` still unmatched at the end of the stream
- a version-2 verb used in a stream that declares version 1, or declares
  nothing

A renderer reports the error rather than drawing a partial picture in silence.

This is the one place where the "unrecognised text becomes prose" rule is
switched off, and it is deliberate: a mistyped command that becomes a caption
gives the author nothing to work with.

---

## 3. Coordinates and numbers

- Coordinates are in pixels.
- The origin is the top-left corner. `x` increases to the right, `y` increases
  downward.
- The drawing area's dimensions are the renderer's business, not the protocol's.
  A program that wants to know them is given them as a value, not by asking.

A number is an optional `-`, then digits, optionally a `.` and more digits. No
exponent notation.

A number may carry a leading `~`. This is how Planes renders a rational whose
decimal expansion does not terminate. The renderer **accepts and discards** the
`~`; it is never part of the value.

```
draw circle ~66.666 100 40
```

---

## 4. Colour

Colour is **OKLCH**, always, everywhere in this protocol. There is no second
colour model and no alternative spelling.

| Channel | Range | Meaning |
|---|---|---|
| L | 0 – 1 | perceived lightness; 0 is black, 1 is white |
| C | 0 – ~0.37 | chroma, or how saturated; 0 is grey |
| H | 0 – 360 | hue, in degrees around a circle |
| A | 0 – 1 | alpha; 0 is fully transparent |

### 4.1 Why not RGB

Hue is degrees on a circle, so colour harmony is addition:

| Add to the hue | Gives |
|---|---|
| 25 | analogous |
| 120 | triadic |
| 180 | complementary |
| 150 and 210 | split complementary |
| 45 | tetradic |

```
let base = 210
draw stroke 0.6 0.15 base 1
draw stroke 0.6 0.15 (base + 120) 1
draw stroke 0.6 0.15 (base + 240) 1
```

Three colours that belong together, computed rather than looked up, and
traceable through `why` like any other derivation. No arithmetic on RGB triples
produces this.

Degrees are whole numbers and stay exact under this language's arithmetic, for
the same reason `rotate` takes degrees rather than radians.

Hue wraps at 360, so hue arithmetic is modulo arithmetic. `base - 30` must
resolve to a point on the circle, which is why the shared `mod` is floored — the
result takes the sign of the divisor.

### 4.2 Stated limit: out-of-gamut colours clamp silently

OKLCH can name colours that a screen cannot show — high chroma at very high or
very low lightness. Conversion clamps each output channel to its representable
range.

**Two distinct requests can therefore produce identical pixels, with no
indication that anything was lost.** This is a real limit of the colour space
meeting a real limit of displays. It is stated here rather than discovered.

This applies per computed stop of a `gradient` (§6.6) exactly as it applies to
`stroke`, `fill` and `background`: a gradient can request a run of colours that
sweeps outside the display's gamut partway between its two endpoints, and the
clamp is silent there too.

---

## 5. Initial state

At the start of every stream, a renderer resets to:

| | |
|---|---|
| stroke | `0 0 0 1` (opaque black) |
| fill | `0 0 0 0` (transparent — shapes are outlines by default) |
| width | 1 |
| cap | `butt` |
| corner | `miter` |
| size | renderer's default text size |
| align | `left` |
| transform | identity |
| path | none open |
| blend | `normal` |
| alpha | `1` (fully opaque — no dimming) |
| dash | `0 0` (solid) |
| shadow | none |
| clip | none |

Nothing persists between streams except what the program restates. A Planes
program holds no state; the page may. The renderer's state is per-stream and
begins from this table every time.

---

## 6. The verbs

Thirty-three. Every one renders natively in both an immediate-mode raster
context and in SVG, with no translation layer on either side.

### 6.1 Colour and line

| Verb | Arguments | |
|---|---|---|
| `stroke` | L C H A | outline colour |
| `fill` | L C H A | interior colour |
| `width` | w | line thickness in pixels |
| `cap` | `butt` \| `round` \| `square` | how a line's ends are drawn |
| `corner` | `miter` \| `round` \| `bevel` | how corners are drawn |
| `alpha` | a | a per-mark opacity multiplier, `0` to `1` |
| `dash` | on off | dash length, then gap length, in pixels; `0 0` is solid |

`alpha` multiplies onto whatever a mark's own fill/stroke alpha already is —
it is not a group fade. Two marks drawn under the same `alpha` and overlapping
each other are two independently-dimmed marks, not one dimmed group; a program
that wants marks to fade together as a unit draws them with the transform
stack (§6.4), not with `alpha`.

`dash` is line-drawing state, exactly like `width`/`cap`/`corner`: it applies
to every stroked outline — shapes, paths, and lines alike — until changed.

### 6.2 Shapes

| Verb | Arguments |
|---|---|
| `line` | x1 y1 x2 y2 |
| `rect` | x y w h [deg] |
| `circle` | x y r |
| `ellipse` | x y rx ry [deg] |
| `arc` | x y r start end |
| `triangle` | x1 y1 x2 y2 x3 y3 |

`r` and `rx`/`ry` are **radii**, not diameters.

Each shape is filled with the current fill, then outlined with the current
stroke. With the default transparent fill, a shape is an outline.

`rect` and `ellipse` each take one further, **optional** argument: a rotation
in degrees, defaulting to `0` when omitted. Positive degrees rotate clockwise
as pictured, the same sense §7's `rotate` uses. The rotation is about the
mark's own centre — the only choice both a raster context and SVG can honour
with no further argument:

- `ellipse x y rx ry [deg]` — about `(x, y)`, the ellipse's own centre.
- `rect x y w h [deg]` — about `(x + w/2, y + h/2)`, the rectangle's own
  centre.

A rotated `rect` or `ellipse` is not gated by the stream's declared protocol
version (§1.1) — it widens an existing v1 verb's arity rather than adding a
new one.

### 6.3 Paths

| Verb | Arguments | |
|---|---|---|
| `shape` | — | begin a path |
| `vertex` | x y | a straight segment to this point |
| `curve` | cx1 cy1 cx2 cy2 x y | a cubic curve to this point, via two control points |
| `close` | — | connect back to the first point |
| `end` | — | finish the path: fill, then stroke |

Paths are what make the vocabulary open-ended rather than a fixed menu. Any
outline is expressible.

```
draw shape
draw vertex 100 100
draw vertex 160 140
draw vertex 120 200
draw close
draw end
```

Paths do not nest. A `shape` while one is open is an error.

The reason a polygon is several lines rather than one is structural: every
command has a fixed argument count, which is what lets a renderer validate a
line rather than guess at it. A variable-length command would give that up.

### 6.4 Transforms

| Verb | Arguments | |
|---|---|---|
| `push` | — | save the current transform |
| `pop` | — | restore the last saved transform |
| `translate` | x y | move the origin |
| `rotate` | degrees | rotate about the current origin |
| `scale` | sx sy | scale about the current origin; negatives flip |

Transforms are renderer state, which the renderer is allowed to hold.

**This is how a Planes program rotates without trigonometry.** The program emits
`draw rotate 30`; the renderer computes the rotation. The same structural move
as colour conversion: the transcendental arithmetic happens on the renderer's
side of the line.

`push` and `pop` are what make recursive shapes tractable — draw a branch, save,
rotate, recurse, restore.

### 6.5 Text and canvas

| Verb | Arguments | |
|---|---|---|
| `label` | x y *rest of line* | draw text |
| `size` | n | text size in pixels |
| `align` | `left` \| `center` \| `right` | horizontal alignment relative to x |
| `background` | L C H | fill the whole drawing area |
| `clear` | — | reset the drawing area to the current background |

`label` takes everything after the y coordinate as its text, including spaces
and including words that are verbs. It cannot be confused with prose because it
carries the `draw` prefix.

```
draw label 8 16 score: 42
```

The verb is `label` rather than `text`, and `corner` rather than `join`, because
`text` and `join` are Planes builtins. A helper function of either name would
shadow the builtin across a whole module graph. The protocol and its Planes
helper library use the same words, so a collision in one renames both.

### 6.6 Paint and compositing

| Verb | Arguments | |
|---|---|---|
| `gradient` | `linear` x1 y1 x2 y2 L1 C1 H1 A1 L2 C2 H2 A2, or `radial` x y r L1 C1 H1 A1 L2 C2 H2 A2 | sets the current fill to a gradient between two OKLCH colours |
| `shadow` | dx dy blur L C H | a shadow cast by every mark drawn while it is set |
| `blend` | `normal` \| `add` | how a mark composites with what is already drawn |
| `clip` | — | opens a masking region, defined by the next completed shape or path |
| `unclip` | — | releases the region `clip` opened |

**`gradient`.** The word decides how many numbers follow it: `linear` takes
four geometry numbers (two endpoints) then eight stop numbers; `radial` takes
three (a centre and a radius) then eight. Both eight-number runs are two whole
OKLCH colours, `L1 C1 H1 A1 L2 C2 H2 A2` — the gradient's two endpoints. A
gradient **sets the current fill**, exactly the way `fill` does; a `gradient`
call replaces whatever fill was set before it, and a later plain `fill`
replaces the gradient right back. There is no gradient **stroke** in this
version (§9).

Colour interpolates between the two endpoints in OKLCH itself, not in the
output colour space: lightness, chroma and alpha vary linearly between the two
requested values, and hue takes the **shorter arc** around the circle — from
350 to 10 sweeps forward 20 degrees through 0, never backward 340. This is the
same floored-`mod` sense §4.1's hue arithmetic already uses. §4.2's gamut clamp
applies to every point along the gradient exactly as it applies to a flat
colour.

**`shadow`.** Six numbers: an offset (`dx dy`), a blur radius, and an OKLCH
colour with no alpha channel of its own — a shadow's opacity comes from the
current `alpha` state (§6.1), not a seventh argument, so `alpha` dims a
shadowed mark and its shadow together. `dx 0, dy 0` is a glow: there is no
separate verb for it. **A mark casts exactly one shadow**, however many times
its own outline is painted (a shape that is both filled and stroked is one
mark, not two) — a renderer whose medium would otherwise cast one shadow per
paint operation composites the mark once before casting the shadow over it.

**`blend`.** One word, from a set that stays closed at exactly two. `normal`
is how every mark has always composited; `add` brightens wherever two marks
overlap, the way overlapping light does. Every other blend mode a raster
context or SVG can name differs between the two in ways that would make them
disagree about what a picture means (§8) — an open mode list is how a shared
walk stops being normative, so this one stays closed.

**`clip`/`unclip`.** `clip` opens a masking region. It does not itself carry
geometry: the very next completed shape (§6.2) or path (§6.3) after it defines
the region, by its own outline — and is still painted normally, exactly as it
would have been without the `clip`, since a shape is never outside its own
boundary. Every mark drawn after that, until the matching `unclip`, is
constrained to the region. `clip`/`unclip` may nest; each `clip` needs its own
`unclip`, tracked independently of `push`/`pop` (§6.4) — a `clip` opened inside
a `push`/`pop` pair and never explicitly `unclip`'d is still open after the
matching `pop`.

---

## 7. The arc convention, pinned

Two renderers will disagree about arcs unless this is exact.

- Angles are in **degrees**.
- **0 degrees points along positive x** — to the right.
- Angles **increase clockwise as the picture appears**, consistent with `y`
  increasing downward.
- An arc is drawn from `start` to `end` in the direction of increasing angle.
- If `end` is less than or equal to `start`, add 360 to `end` until it exceeds
  `start`. A full circle is therefore `start` and `end` differing by 360.
- An arc is a curve, not a wedge: it is not closed back to its centre. To draw a
  wedge, use a path.

`rotate` uses the same sense: positive degrees rotate clockwise as the picture
appears. `rect`'s and `ellipse`'s optional rotation argument (§6.2) uses it
too.

---

## 8. Renderer conformance

A renderer implements a whole version or refuses it. There is no partial
conformance and no verb-by-verb negotiation, because a program that cannot know
what is listening cannot adapt to a renderer's gaps.

A renderer states, in its own documentation, which versions it implements.

A renderer whose medium cannot express a verb — a pen plotter cannot fill —
states that as a documented limitation of that renderer. It does not silently
skip commands.

### 8.1 Still-image renderers

A renderer producing a file rather than a live surface captures **one stream**.
For a program that draws once, that is the whole picture. For a program that
redraws continuously, it is the frame that was captured — a snapshot, not an
animation.

This is worth saying plainly to whoever uses such a renderer: *saving gives you
what is on screen now.*

---

## 9. Known limits of version 2

- **Out-of-gamut colours clamp silently** (§4.2), now including every computed
  point along a gradient.
- **No cursor.** `line` takes four coordinates. Earlier drafts carried a
  `move`/`line` pair; a stateful cursor was dropped because it made line the
  only shape whose meaning depended on a preceding command.
- **No gradient stroke.** `gradient` (§6.6) sets a fill only. A stroke is
  always a flat OKLCH colour in this version.
- **`blend`'s mode set is closed at two, and stays closed.** `normal` and
  `add` are the only two modes this version has, and no third is expected —
  every other blend mode a raster context and SVG can each name diverges
  between the two badly enough to make them disagree about what a picture
  means, which is exactly what a shared protocol exists to prevent (§8).
- **No image drawing.** Expressible in both target formats, and deliberately
  left for a later version: it brings asset loading and a fetch boundary that
  is a larger question than a verb table entry.
- **No variadic polylines.** §6.3's reasoning stands: fixed arity is what lets
  a renderer validate a line rather than guess at it, and a variable-length
  command would give that up. A path already expresses any polyline; `line`
  stays four numbers.
- **No animation in the format.** Motion is a program redrawing; the protocol
  describes one picture at a time.

---

## 10. Relationship to p5.js

p5 is the most established beginner drawing vocabulary, and a learner outgrowing
Planes is likely to land there. This protocol deliberately does **not** reuse
p5's names, because the words overlap while the meanings do not — and a word
that transfers with a different meaning is worse than a word that does not
transfer at all. A learner who carries `circle` across and gets a shape half the
intended size has no error to read.

The on-ramp is this table instead.

| This protocol | p5 | Difference |
|---|---|---|
| `circle x y r` | `circle(x, y, d)` | p5 takes a **diameter** |
| `ellipse x y rx ry` | `ellipse(x, y, w, h)` | p5 takes full width and height |
| `line x1 y1 x2 y2` | `line(x1, y1, x2, y2)` | same |
| `rect x y w h` | `rect(x, y, w, h)` | same |
| `triangle …` | `triangle(…)` | same |
| `arc x y r s e` | `arc(x, y, w, h, s, e)` | p5 takes width/height and **radians** |
| `stroke L C H A` | `stroke(r, g, b, a)` | p5 is RGB, 0–255 by default |
| `fill L C H A` | `fill(r, g, b, a)` | p5 is RGB; p5 also has `noFill()` |
| `width n` | `strokeWeight(n)` | same idea |
| `cap` / `corner` | `strokeCap()` / `strokeJoin()` | same idea |
| `label x y text` | `text(str, x, y)` | argument order differs |
| `size n` | `textSize(n)` | same idea |
| `align` | `textAlign()` | same idea |
| `shape` / `vertex` / `close` / `end` | `beginShape()` / `vertex()` / `endShape(CLOSE)` | same idea |
| `curve …` | `bezierVertex(…)` | same idea |
| `push` / `pop` | `push()` / `pop()` | p5 also saves colour state; this saves transform only |
| `translate` / `rotate` / `scale` | same names | p5's `rotate` takes **radians** |
| `background L C H` | `background(r, g, b)` | p5 is RGB |
| `clear` | `clear()` | same idea |
| `gradient` | none built in | p5 has no gradient primitive; a sketch builds one by hand against a raw `drawingContext` |
| `alpha` | none built in | p5 dims via colour alpha only; this is a separate multiplier |

*(p5 details here are general knowledge and are not verified against a p5
release. The table is an orientation aid, not a compatibility claim.)*

---

## 11. Writing this from Planes

Emitting these lines by hand is string assembly:

```
show "draw circle " + text of x + " " + text of y + " " + text of r
```

The companion library `draw.planes` wraps every verb once so that programs do
not:

```
use draw
circle of 200, 100, 40
```

The library holds **one helper per verb in this document, and nothing else**.
The specification and the library are the same thing written twice, and that
correspondence is mechanically checkable.

---

## 12. What version 3 is expected to carry

Recorded so it is not re-derived, and not as a commitment.

- **Image drawing** (§9) — asset loading and a fetch boundary, deliberately
  left out of this version.
- Whatever a third independent implementation reaches for and does not find.

`blend`'s mode set and the absence of a gradient stroke (§9) are stated limits,
not gaps waiting on demand — nothing above lists them as expected, because
nothing about them is expected to change.

The version declaration in §1.1 exists so that this change, when it comes, is a
refusal rather than a silently wrong picture.

---

*Version 2. This document defines the format; a renderer implements it; a
program emits it and knows about none of them.*
