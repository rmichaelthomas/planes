# The Garden — Page Specification

**For:** `garden.html`. **Reference implementations:** `mockups/tutor-garden-mockup.html` — why-card content and the note breakdown. Layout, palette and typography came from `the-living-garden.html`, a JavaScript mockup retired once this page existed; every value it carried is recorded below. Where this document and the surviving mockup disagree, the mockup wins — open it, and match it. This is the page-level twin of `garden-scene-spec.md`, and exists because that document's precedence rule was written about the program and the page went unspecified.

## §3.0 What this page is, and is not

This is the showcase of Planes: a living picture, a click that answers with a derivation, and a note whose ratio is exact — on one screen, legible to someone who has never heard of an effect surface. Machinery earns its place by serving that reader or it moves down the page. The current page fails this test the way the pre-spec garden failed the scene test: it leads with jargon, renders at postcard size, and dresses in `paint.html`'s clothes. Everything it *does* is right; everything it *shows first* is wrong.

## §3.1 One appearance

The page has exactly one appearance: paper. Delete `color-scheme: light dark` and the entire `@media (prefers-color-scheme: dark)` block. The identity tokens, as transcribed from the retired mockup:

```css
--paper:#F7F2E9; --graphite:#211D19; --line:#D6C9B4; --clay:#A65A2E;
--slate:#4A5B68; --amber:#F59E0B; --blue:#3B82F6; --teal:#14B8A6; --violet:#8B5CF6;
--ink-60:rgba(33,29,25,.62); --ink-40:rgba(33,29,25,.40);
```

`body` background is `--paper`, text `--graphite`. No hex color appears in the page that is not in this list, white, or `rgba` derived from a listed value. `#2d6cdf`, `#4a8a5c`, `#d8d8d8` and every other `paint.html` inheritance: gone.

## §3.2 Typography

Display: `"Red Hat Display"` 700/900, `letter-spacing:-.02em` on the h1. Body and UI: `"Martian Mono"` 400/500, 12–12.5px, `line-height:1.55`. Self-hosted via `@font-face` from `identity/fonts/` — this page's footer promises no network dependency beyond the static server, and a Google Fonts `<link>` would make that sentence false. Fallback stacks as in the mockup.

## §3.3 Header and branding

Left: the Planes mark — `identity/planes-small-on-light.svg`, rendered at **44px** via `<img>`, per the locked nav treatment. The mark is consumed from the `render_logo.py`-generated asset; it is never redrawn in CSS or inline HTML (standing term §89). Beside it, stacked: `the garden` as h1 (Red Hat Display 900, 25–26px) over the one-line sub in `--ink-60`: *click anything — the sun, a bee, a flower, the rain*.

Right: the clock, exactly as the mockup — time of day in Red Hat Display 700 ~17px, and beneath it in small mono the weather readout (`raining · day 2 of 3`). The clock moves here from wherever the controls put it; there is no second clock.

The five-sentence `paint/garden.planes` paragraph is deleted from the top of the page. Its true claims survive in the legend (§3.6) and footer (§3.11). Nobody meets the words "effect surface" before they meet the garden.

## §3.4 Controls

One bar under the header, mockup-styled buttons (1px `--line` borders, 3px radius, transparent background, mono 11–11.5px, `aria-pressed` states inverting to graphite-on-paper; the accent buttons border `--clay`):

- **▶ play / ❚❚ pause** — clay accent. **The page auto-plays on load at 1×** (the mockup runs on load; a showcase opens alive). Sound never auto-starts.
- **fast-forward** — toggle, wiring the existing loop speed between 1 and 16. The 1×/4×/16× triple is deleted; one toggle is the mockup's grammar.
- **♪ sound off / on** — clay accent, existing behavior: governs play-loop sound, constructs the AudioContext in the click.
- **seed** input (mono, 600 weight, white field, `--line` border) + **new seed** — new seed picks a random six-digit seed, as the mockup's `reseed` does.
- **Reset ⟲** — quiet, kept, at the end of the bar.

Deleted from the bar: the speed triple, Save SVG/PNG (demoted, §3.5), Reload modules (demoted, §3.11).

## §3.5 The canvas

Full column width, the dominant element on screen — `width:100%; height:auto`, `--line` border, 3px radius, `cursor:pointer`. The program's coordinate space stays **480×360 — `paint/garden.planes` is untouched.** The backing store scales: read `js/paint/export.mjs`, find the mechanism the PNG export already uses to render the same stream at 960 wide, and apply it to the on-screen canvas at 3× (1440×1080 backing pixels) with `DIMENSIONS` still describing program coordinates. Hit-testing and card positioning divide by the same factor. If the export mechanism cannot be reused for a live context, implement `ctx.scale(k,k)` before each paint with all mark and highlight coordinates in program space — but look for the existing mechanism first; building a second scaler beside a working one is the defect class §337 warns about, arriving from the other side.

Beneath the canvas, one slim row (`canvas-foot`): left, the tick scrubber — kept, restyled to the identity (slim range input, quiet ◀ ▶ steppers, `tick 130 · day 2` label in mono) — because dragging to a tick and getting the identical frame *is* the purity demonstration, and it stays within reach without leading the page. Right: **Save SVG ⤓** and **Save PNG ⤓** as quiet buttons with the existing behavior. Under the row, one hint line in `--ink-40`: *same seed, same garden — on any machine, forever*.

## §3.6 The legend

The mockup's strip, verbatim, in a bordered translucent panel under the canvas-foot:

> **one day** ≈ 100 seconds · **weather** drifts on its own noise · **bees** by day, **fireflies** by night · **flowers** open with the sun · every note is an exact ratio

Adjusted only if a claim is false of the real page (one day at 1× is 25 seconds at 4 ticks/s — say what is true; the legend never lies to match a mockup).

## §3.7 The effect surface, summarized

The visible surface pane is the first mockup's form: an eyebrow (*effect surface — computed, not run*) over at most three short lines — the purity claim in `--teal`, the approximation claim in `--clay`, and the chain in `--ink-40` — derived from what `js/paint/surface_pane.mjs` and the computed surface actually expose. Read the module first; render what the surface carries, not what this spec wishes it carried, and report in the PR what that turned out to be.

The full command listing survives, collapsed: a `<details>` inside the panel labeled *show the full surface*, containing the existing rendered listing. Computed-not-run is unchanged; only the default visibility changes. The jargon wall is now opt-in.

## §3.8 The why card — the centerpiece

A floating card over the canvas at the click point (paper background, 1px graphite border, 3px radius, shadow, max-width ~300px), with the **first mockup's content**, in this order:

1. **Heading** — Red Hat Display 700. If the trace exposes the enclosing definition's name for the clicked line (via `Function.file` / `call_sites` — read `js/paint/why.mjs` and the trace shape to check), the heading is the friendly form: *this plant · line 48*. If it does not, the heading stays the trimmed source line, as built. Implement whichever the data supports and state which in the PR; do not fabricate names the trace cannot justify.
2. **The derivation steps** — the mockup's connected-dot treatment: each step a dot on a hairline, value bold, source in `--ink-60`, `because` clauses in `--teal` with the left border. The step whose value feeds both the picture and the note gets the clay dot (`step.shared`). The existing "one step further" expansion renders as an additional step, not a separate row style.
3. **The origin step** — slate dot: *seed 481027 — you chose this. Nothing outside the program was touched.*
4. **Divider, then THE NOTE YOU JUST HEARD** — the clay-tinted box (`rgba(166,90,46,.07)` fill, `.28` border), present only when the click played a note: the frequency, *from base (220) × major sixth (5/3)* with the interval named from the ratio — unison 1/1, whole tone 9/8, major third 5/4, fifth 3/2, major sixth 5/3; an unlisted ratio displays as its ratio, unnamed — and beneath it the one sentence that is the entire pedagogical payload: *The same **g 0.9781** chose the height and the note. That is one node in the chain, read twice.* (Values live; the bold `g` in clay.)
5. **Divider, then the two badges** — clay: *approximate — the chain reaches `sine`*, with its note that approximate is not unpredictable and the garden is bit-identical everywhere; slate: *3/2 is exactly 3/2*, with its note that intervals never drift.
6. The closing line, kept from the built card: *asking performed nothing — the effect surface is unchanged.*

**Clicking a mark whose line emitted a note plays that note** — the first mockup's behavior. A click is a user gesture, so the audio player is constructed lazily on first such click; the ♪ toggle continues to govern only play-loop sound. Clicking pauses playback, as built. Card dismissal and source-line highlighting behavior are unchanged.

## §3.9 The source view

Kept — hovering a line lights its marks, the showcase's second-best trick — restyled as the first mockup's source panel: white, bordered, a head bar (`garden.planes` · line count, uppercase letterspaced `--ink-40`), the listing in mono 11px/1.85. Syntax tint if cheap using the four accent classes (`kw` clay, `bc` teal, `cm` ink-40, `lit` slate); skip it rather than adding a highlighting dependency. Hover/lit background moves from `#ffe9a8` to `rgba(245,158,11,.22)` — amber from the identity.

## §3.10 The output pane

Kept, small, under the source panel, mockup-styled. Errors in a red derived from `--clay` territory, not `#b00020`.

## §3.11 The footer

Compressed to the mockup's register — small `--ink-40` mono, max-width ~640px, four short items: the serving line (one sentence; the full explanation stays in the HTML comment, which is unchanged); the purity sentence; the saving sentence; and **reload modules** as a small text link — it exists to service the stale-module warning, and the warning text names it when it fires.

## §3.12 Acceptance

Open `garden.html` beside `tutor-garden-mockup.html`, same seed.

- [ ] Paper background, no dark mode in the file, no hex outside §3.1's list.
- [ ] Red Hat Display / Martian Mono render with the network tab showing no request leaving localhost.
- [ ] The real Planes mark at 44px in the header; no CSS-drawn mark anywhere.
- [ ] The canvas dominates the viewport at 1040px+ widths and is crisp (no 480px upscale blur).
- [ ] The page is alive on load; fast-forward is one toggle; no speed triple; no export buttons in the top bar.
- [ ] The first words a reader can see above the fold are the title, the sub, the controls and the garden — not `paint/garden.planes` and not `show draw align`.
- [ ] Clicking a flower plays its note and the card shows: derivation steps with the shared-g clay dot, the origin, THE NOTE YOU JUST HEARD with ratio and interval name, the shared-node sentence, both badges, the asking-performed-nothing line.
- [ ] The full surface listing exists but is collapsed by default; expanded, it matches the pre-build listing.
- [ ] Scrubbing to the same tick twice produces byte-identical PNGs at the new resolution.
- [ ] `paint/garden.planes` and `paint.html` have empty diffs.

---

## §3.13 Revisions after the visual gate

§3.0–§3.12 above are the build prompt's specification, verbatim. This section records what the first visual gate changed and why. Where the two disagree, this section is later and wins.

### The granularity finding, written down

**Per-mark granularity is available and it works.** The first build made every emitted mark answerable — 344 of them in a frame — and hit-testing, the trace lookup and the card all held up at that resolution. Clicking a single raindrop, one blade of grass or one branch segment returned a correct derivation. That capability is real and is worth keeping in mind for a future page that wants it.

It is also the wrong default. At full granularity a click on the sky returns `rect of 0, 0, canvas-width, sky-split, 0` and the reader learns nothing they were asking about. **Granularity is a capability, not a target.**

### §3.13.1 What is clickable

Six subjects, matching the set the retired mockup's own `why()` answered: **the sun or moon, a flower, a bee, a firefly, the rain, the tree**. Nothing else — not the sky, the hills, the ground, the grass, the clouds, the stars, and not a plant's stem or leaves.

A mark's subject is the enclosing `to <name>` of the line that drew it, read from the source. Within `draw-plant`, only the circles are the flower; the stem is not.

This also settles §3.8.1's heading question in the other direction. The heading is now the **subject** — *this flower* — because the enclosing definition is a fact about the program's text, not a name the page invented. The line number and definition stay underneath it.

### §3.13.2 What the card says

Rows are **named values**, not the drawing command's coordinates. `card().rows` gives one row per number in the emitted line, which reads `~186.931231836987 from .tip-x` — true, and useless to anyone not debugging the renderer.

The names shown are the ones the author annotated with `because` — the program saying "this matters, and here is why" — plus `g`, which always keeps a slot on a flower, since its height and its note both come from it. At most four. The expression beside each name is the **program's own text** for that binding, and is shown only when unambiguous: a name bound in more than one definition, outside the one that drew the mark, gets its value and no expression rather than a confident wrong one.

Dropped as too technical: the `one step further` expansion, and one row per raw coordinate.

### §3.13.3 The flower's note

A flower's note plays on every click, not only on the 25 ticks in 300 where a bee happens to land. This requires **restating the program's rule** (`whole of (g * 5)` into the five just ratios, at octave 1) in the page, because a page cannot call a program's functions.

The restatement is checked, not trusted: `js/test/garden_card.test.mjs` reads the table out of `garden.html` — there is no second copy — runs the real program across all 300 ticks, and asserts the page's rule reproduces the ratio and octave of every note the program actually emitted. It found a defect on its first run: **`whole of` rounds half away from zero, it does not truncate**, so a flower with `g` 0.708994 plays 5/3 where truncation says 3/2. (`interp.mjs`'s own error text for a bad `whole of` argument said "rounds a number toward zero", which is misleading; it was out of scope for that build and has since been corrected in all three implementations.)

### §3.13.4 The click itself

- **No page jump.** `scrollIntoView` walks every scrollable ancestor and threw the reader out of the picture; the source pane scrolls itself via `scrollTop`.
- **No outlines on the canvas.** Amber outlines belong to hovering a *source line* — the map read backwards. A click marks the line and leaves the picture alone.
- **Always dismissable.** A ✕ on the card, the Escape key, a click on empty sky, and a click anywhere off the picture. The card is no longer `pointer-events: none`; a card that cannot be closed is worse than one that cannot be clicked through.
- **A click still pauses.** The card's numbers are the values at one tick, so a card over a running scene would be stale before it finished rendering.
