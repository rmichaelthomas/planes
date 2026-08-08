# Tutor redesign verification — goal-driven, line-live typing (v35.0)

Build prompt: "Tutor Redesign: Goal-Driven, Line-Live Typing". Base state
`aca078f` (PR #97). Branch `feat/tutor-goal-live-typing`. Shell-only —
`tutor.html` was rewritten; the engine (`js/browser_main.mjs`,
`js/paint/why.mjs`, `js/paint/hit.mjs`, `js/scene_vocab.mjs`,
`paint/scene.planes`, and every other `js/paint/*.mjs` the page imports) is
byte-identical to its pre-build blob SHA, confirmed both before and after
this build (see §E below).

Verification method: served the repo root over `python3 -m http.server`,
drove the real page with `playwright-cli` in a headless Chrome session
(interactive typing, clicking, file upload/download, viewport resize,
`prefers-reduced-motion` emulation), and ran the repo's own test gate. Three
real defects were found this way and fixed before this table was written —
listed at the bottom, not folded into the pass rows as if they never
happened.

## §10.2.A — Goal-live loop, all seven lessons

| Lesson | Typed each correct line in order → paints + advances | Wrong line is a no-op | Lesson-specific mechanic | Result |
|---|---|---|---|---|
| 1 place a thing | ✅ sky→ground→sun, live in browser | ✅ (verified lesson 2's sky slot) | — | PASS |
| 2 across & down | ✅ sky→ground→bee, live in browser | — | — | PASS |
| 3 day → night | ✅ (structural: LESSONS items verified; exact-match kind identical to lessons 1/2, already exercised live) | — | — | PASS |
| 4 name it & why | ✅ sky→ground→sun→let…because→two-flowers, live in browser | ✅ a bare `let spot = 90` (no reason) left the goal on step 4, unchanged, live in browser | ✅ free-form reason (`"it makes the yard feel finished"`) accepted and carried verbatim into the why-card's because-sentence, live in browser; `js/test/tutor_redesign.test.mjs` additionally asserts an empty/missing reason and a wrong bound name/number are all rejected | PASS |
| 5 two, their own height | ✅ (structural + unit-tested: `testShapeBecause` exercised for both `spot`/90 and `shady`/44 pairs; test asserts lesson 5 carries **both** let…because pairs, not simplified to one) | ✅ (same matcher as lesson 4, unit-tested) | ✅ two independent named heights, each with its own free reason | PASS |
| 6 your own sky | ✅ full live run: `to sunset dream:` (learner's own words) → swatch-picker-written `custom-sky of …` body → `start` (frame) → `sunset dream` use-site → ground → sun → let…because → two-flowers, all live in browser | ✅ a wrong use-site name (`wrong name here`) rejected live; a name containing `of` rejected at the definition site (unit test) | ✅ learner-chosen name recorded at the definition site and required verbatim at the use site (the cue box itself updates to show her own chosen name back to her); swatch click completes the color line the same as typing would | PASS |
| 7 it's yours now | ✅ renders the complete finished garden immediately on load — **no typing gate** — confirmed live; free-form "keep growing it" editor below re-runs live on edit | n/a (no goal-live steps) | ✅ honest-card, save/reopen, seed, certificate all present and functional, confirmed live (see §invariant-preservation below) | PASS |

No lesson's content was dropped: `js/test/tutor_redesign.test.mjs`'s "no
lesson mechanic was dropped" test asserts lesson 4/5 keep shape-because,
lesson 6 keeps the full name-binding-def → shape-custom-sky → name-binding-use
chain plus `surfaces.swatches`, and lesson 7 keeps `surfaces.capstone` with
every one of its items pre-authored (`role: "frame"`) rather than forced
through a typing gate.

## §10.2.B — Per-element why

| Element | Click resolves to | Verified |
|---|---|---|
| sun (discrete mark) | `hitTest` → the mark's own trace entry | ✅ live: "where did sun come from?" — across 240 →, down 70 ↓, "this one has no reason yet" invite, from line 5, exactness note |
| ground (backdrop, `hitTest` returns -1 by design) | `backdropLineAt` → the region's recorded source line, using `hit.mjs`/`marks.mjs`'s own exported `invert`/`containsPoint`/`applyMatrix` — no hardcoded horizon constant | ✅ live: "where did ground come from?" — kind: wet grass, from line 4 |
| sky (backdrop) | same mechanism as ground | ✅ live: "where did sky come from?" — time: middle of the afternoon, from line 3 |
| flowers, with a because-annotated named height | mark → trace → `card()` → `annotationsInChain` | ✅ live: "where did two-flowers come from?" leads with **her own sentence** — "it makes the yard feel finished" — across 120, how-tall 90, from line 7 |
| clicking a garden element also highlights the corresponding line in the rendered stack | `highlightLine(sourceLine)` targets `.sl[data-line="n"]` | ✅ live, visible in every why-card screenshot above (amber-highlighted stack line) |
| asking performs nothing | `renderCardCore` never calls `runProgramGraph`/`analyseProgramGraph` | ✅ confirmed by direct source inspection (grep count: 0 engine calls inside `renderCardCore`) — the same structural guarantee the prior tutor shell relied on, unchanged |

## §10.2.C — One statement per line

`js/test/tutor_redesign.test.mjs`'s "one statement per line" test asserts no
`LESSONS[i].items[j].text` contains an embedded `\n` — every frame line and
every slot's canonical/committed text is exactly one physical line by
construction, since `lessonProgramText`/`onTypeInput` both join items with a
real `"\n"`, never string-concatenate two statements onto one rendered line.
Verified live throughout: every screenshot's stack, cue box, and worked
example show one Planes statement per rendered line, matching
`paint/scene.planes`'s own one-statement-per-line source shape.

## §10.2.D — Key

Verified live across lessons 1, 2, 4, 6, 7: the key shows only the current
lesson's vocabulary (e.g. lesson 6 shows no "skies — sky of …" group at all,
since lesson 6 never calls `sky of` — it defines and uses a custom sky
instead), no "unlock later" line anywhere, and every row renders as
word-over-caption (`<div class="word">` with a separate `.needs` line), never
as a copyable program line. `js/test/tutor_redesign.test.mjs` additionally
asserts `vocabForLesson` derives from `lessonProgramText` (the lesson's own
items) rather than a second hand-kept `vocab` field, and that no `LESSONS[i]`
carries one.

## §10.2.E — Invariants

- **Engine unmodified**: `git diff --stat main` touches exactly `tutor.html`
  and `js/test/tutor_redesign.test.mjs`. Blob SHAs for every engine file the
  build prompt named (`js/browser_main.mjs`, `js/paint/why.mjs`,
  `js/paint/hit.mjs`, `js/scene_vocab.mjs`, `paint/scene.planes`, and the
  rest of `js/paint/*.mjs`/`js/module_loader_browser.mjs`) are byte-identical
  to the values recorded before this build started.
- **sky/ground gained local why-card labels without touching
  `scene_vocab.mjs`**: `CARD_LABELS` (a `tutor.html`-local presentation map,
  the same pattern the prior shell already used for `custom-sky`) grew two
  entries; `PLACEABLES` in `js/scene_vocab.mjs` is untouched — asserted by
  test.
- **LESSONS.length is the only lesson count**: no hardcoded `7` drives
  lesson-nav rendering or clamping — asserted by test (`grep`-level check
  against the actual source, not just behavioral).
- **Test suite**: `node --test js/test/*.mjs` → 976/976 passing (30 in the
  rewritten `tutor_redesign.test.mjs`). `python3 scripts/run_suites.py` → 90
  suite files, 1533 oks, 0 failures. `scripts/check_js_tests.py`,
  `ruff check .`, `mypy .`, `audit_locked_vs_built.py`, `grammar_gen.py
  --check`, `scripts/protocol_gen.mjs --check`, `core_check.py` (both entry
  points), `scripts/check_derived_claims.py` — all clean.

## §10.3 — Visual self-check

Direction D reads as garden-material (frosted why-card, warm gradients on
the stage, clay-boxed cue distinct from grey frame furniture) rather than
editorial paper, confirmed across every lesson screenshot captured during
this build. The stream-draw-into-settle-pulse reveal fires on every
`paints`-bearing slot (verified live: sky/ground/sun/moon/firefly/bee/
flowers/custom-sky all triggered the wipe+pulse with no console errors
across dozens of typed lines). Under `prefers-reduced-motion: reduce`
(emulated via Playwright), a completed line was typed and the DOM was
inspected immediately afterward: zero `.reveal-wipe` and zero `.reveal-pulse`
elements were ever created — only the minimal `.reveal-fade` path runs. No
unresolved visual judgment call arose that needed the architect — the design
read matched the reference mockup's intent throughout.

## Preserved features (§2b), verified live

1. Lesson-advance save-first dialog — fires when the current lesson has
   authored (slot) content, offers "Save my garden, then continue / Start
   fresh / Stay here", never framed as loss. Confirmed on multiple lesson
   switches.
2. `beforeunload` guard — confirmed: a `goto` to a fresh URL while unsaved
   work existed blocked navigation until the dialog was dismissed.
3. Friendly error softening — confirmed structurally (same `friendlyError`
   function, unchanged softening rules) and confirmed live for the
   roll-back path: a pattern-matched line that the engine itself refused
   (attempted mid-build, before the multiline-defer fix below) surfaced a
   softened message with no raw tag, and did not advance.
4. SVG/PNG export — confirmed live: `Save SVG` produced a real
   `planes-tutor-garden-*.svg` download with genuine gradient/path content.
5. Garden-file save/reopen + seed ticket — confirmed live end to end: saved
   a `.planes` file, uploaded a hand-authored different garden (moon/firefly/
   night sky), and it repopulated the capstone's free-form editor and
   repainted correctly — "a completed program opens as complete."
6. "Asking performs nothing" via cached run state — confirmed structurally
   (§10.2.B above) and confirmed live (many successive why-card opens never
   altered the picture).
7. Click-to-line highlight — confirmed live in every why-card screenshot.
8. Ghost/key hide toggles (final lesson) — confirmed live: "hide hints"
   hides the lead/worked-example strip; "hide key" hides the vocabulary key;
   both reset to shown on lesson switch (by construction, in
   `performLessonSwitch`).

Also carried forward: the coordinate orientation tip (live across/down on
hover before a picture exists, handing off to the ask-hint after first
paint — confirmed live, renamed `hasRunThisLesson` → `hasPaintedThisLesson`
to match the no-Run-button model, same mechanism); the `DIRECTION_GLYPH`
single-source mapping; the empty-because invite card (confirmed live on the
sun's why-card); `COORDINATE_NOTE` in the key.

## Real defects found and fixed during this build

1. **Worked-example thumbnail only showed sky.** The mini canvas beside the
   worked-example code used the main stage's `DIMENSIONS` (`scale: 3`,
   implying a 1440×1080 backing store) while its actual HTML backing store
   was 480×360 — everything painted 3× too large and the ground/sun rects
   landed outside the visible canvas. Fixed with a dedicated
   `EXAMPLE_DIMENSIONS` (`scale: 1`) for the thumbnail only.
2. **Switching lessons left the previous lesson's picture on screen.**
   `performLessonSwitch` reset all JS state but never cleared the canvas —
   since frame lines don't trigger a paint, a fresh lesson showed the prior
   lesson's finished garden until the first slot completed. Fixed by
   clearing `lastLines`/`lastMarks`/etc. and calling `ctx.clearRect` on
   every lesson switch.
3. **The rail's rendered stack didn't clear on switching into the capstone
   lesson**, showing a stale, inconsistent mix of the previous lesson's
   committed lines alongside the new lesson's freshly-painted picture. Fixed
   by calling `renderStack()` immediately after the state reset in
   `performLessonSwitch`.
4. **A multiline definition's header alone was sent to the engine and
   correctly refused** (`let spot`-style: a `to <name>:` block header with
   no body is a genuine syntax error, not "runs and draws nothing yet").
   Found live while testing lesson 6's own-sky definition. Fixed by
   deferring the run+paint until the paired body line (`shape-custom-sky`)
   also completes — the two lines together are one atomic step, matching
   the build prompt's own "advance only when the whole definition is
   well-formed" language for the multiline match kind.

All four were caught by driving the real, served page in a real browser —
not by reading the code — and are fixed in the version this table describes.
