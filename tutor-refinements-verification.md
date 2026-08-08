# Tutor refinements verification — post-v35.0 architect review

Build prompt: "Build Prompt — Tutor Refinements (post-v35.0 merge)". Base
state `706cb53` (PR #98, the v35.0 goal-live redesign). `tutor.html` blob
`d92c506` at base, confirmed byte-identical before this build started.
Branch `feat/tutor-refinements`. Shell-only — the engine
(`js/browser_main.mjs`, `js/paint/why.mjs`, `js/paint/hit.mjs`,
`js/scene_vocab.mjs`, `paint/scene.planes`) is untouched, blob SHAs
confirmed identical to `main` below.

Verification method: served the repo root over `python3 -m http.server
8000`, drove the real page with `playwright-cli` in a headless Chrome
session at a 1440×900 viewport (typing, clicking, file download capture,
viewport resize down to 800px), and extended the repo's own test gate
(`js/test/tutor_redesign.test.mjs`, group H) with structural assertions
tied to the exact source lines this build changed. One real defect (a
fragile test string that matched the wrong occurrence of "keep growing it"
in the page's head comment) was found and fixed before this table was
written.

## §2 — Full-width stage

| Check | Result |
|---|---|
| `.wrap` raised to `max-width:1280px` | ✅ `js/test/tutor_redesign.test.mjs` "H §2" asserts the exact CSS line |
| Rail stays fixed at 340px, extra width flows to the stage (`1fr`) | ✅ asserted; confirmed live — stage canvas measured 916px wide at a 1440px viewport (was ≈700px under the old 1080px wrap) |
| Card position (`renderCardCore`) and coord-tip (`showCoordTipAt`) both re-derive `canvas.getBoundingClientRect()` on every call, not a cached value | ✅ asserted by test; confirmed live — clicked the sun at 1440px, the why-card rendered fully inside the widened stage bounds, no clipping |
| `@media (max-width:900px)` single-column collapse | ✅ confirmed live at 800×900 — rail drops below the stage, lesson tabs wrap |

## §3 — "Next lesson →" button

| Check | Result |
|---|---|
| Button ships `hidden` by default | ✅ asserted; confirmed live (absent before lesson 1 completes) |
| Appears on completion, lessons 1–6 | ✅ confirmed live: lesson 1 (sky→ground→sun) and lesson 6 (full own-sky chain) both revealed a clay "Next lesson →" button on their completion message |
| Gated on `LESSONS.length - 1`, not a literal | ✅ asserted by test (regex against the actual `finishLesson` source) |
| Hidden on the capstone (lesson 7) | ✅ confirmed live — `next-lesson.hidden === true` on load of `?lesson=6` |
| Click routes through `setLesson()`, honoring the (narrowed) save-first gate | ✅ confirmed live — clicking "Next lesson →" from a just-completed lesson 1 advanced silently to lesson 2 with the URL updating to `?lesson=1` and no dialog shown |

## §4 — Capstone rebalance

| Check | Result |
|---|---|
| "your garden is honest" demoted to a single-line strip above the grid, not a two-paragraph capcard | ✅ asserted (position + absence from the grid cells); confirmed live in the capstone screenshot — one sentence, teal check icon, full width |
| The honest claim itself still sourced from `updateHonestCard()`/`analyseProgramGraph` | ✅ unchanged code path — `#honest-text` id preserved, only its container moved |
| "keep growing it" expanded into a real send-off: affirmation + 3–5 concrete tries + one-line forward pointer | ✅ confirmed live — affirmation ties naming/saying-why/building-from-pieces to programming generally; four tries (`sky of "the middle of the night"` + `moon`/`firefly`, `two-flowers of 380, spot`, a custom sky via `to a quiet dusk:`, `two-bees of 150, 220`); one-line pointer to `./index.html`, no pitch language |
| Every suggested placeable/phrase is real, checkable `scene_vocab.mjs` vocabulary (not invented) | ✅ asserted by test directly against `PLACEABLES`/`SKY_PHRASES` — moon/firefly both need `[across, down]`, two-flowers/two-bees match their declared shapes |
| Share card (seed + save + open) unchanged in function | ✅ confirmed live — clicked "Save my garden file", captured a real `download` event: `planes-garden-20260808-120449.planes` |

## §5 — Public-facing cleanup

| Check | Result |
|---|---|
| No serving/build prose in the rendered footer | ✅ asserted (footer text scanned for `python3 -m http.server` and `Serving:`); confirmed live — footer now reads only "There's no Run button…" |
| Serving instructions preserved for developers, as an HTML comment | ✅ moved into a `<!-- -->` block immediately above `<footer>`; the pre-existing `<head>` comment block was already invisible and untouched |
| Second footer paragraph reworded to plain learner language | ✅ "Clicking anything in the picture asks about it — it never runs your program again" (was "reads the last line that painted it") |
| Both taglines replaced away from "draw something" | ✅ asserted (`grep` for the phrase returns nothing); header tag → "write a line, watch it grow, ask it why"; certificate signature → "write a line, ask it why" (mirrors the original's own header→cert abbreviation pattern) |
| `<meta name="description">` still leads with typing | ✅ verified unchanged — already led with "type one line of real Planes at a time" |

**AUTHOR-DRAFTED, FLAG FOR STRIKE:** both tagline strings above are drafted copy per the build prompt's own instruction — architect's final wording call.

## §6 — Lesson 6 clarity

| Check | Result |
|---|---|
| Cue shows a concrete example name (`to my morning glow:`), not the literal placeholder text | ✅ confirmed live — screenshot shows the cue box and goal copy both displaying the example |
| `cueTextFor`'s `name-binding-def` branch reads `step.example` | ✅ asserted by test |
| `cueTextForCanonical` (worked example / vocab derivation) untouched, still valid Planes | ✅ unchanged — still returns `step.text` ("to your sky name here:"), a syntactically valid identifier |
| Example costs nothing mechanically — an arbitrary own name still accepted | ✅ confirmed live end-to-end: typed `to a stormy dusk:` (not the example), it was accepted, committed to the stack, and the later use-site cue dynamically echoed back "a stormy dusk"; `testNameBindingDef` also unit-tested against both the example and a different name |
| Name → color presented as one connected two-step move | ✅ confirmed live — goal copy reads "Name your own sky, then give it a color — one move, two steps…" on step 1, "Now the second step: color the sky you just named…" on step 2 |

## §7 — Lesson 7 is a sandbox, not a lesson

### §7.6 — Completion copy must be true

| Check | Result |
|---|---|
| Lessons with slots keep "every line typed by you" | ✅ confirmed live on lesson 6 completion |
| Capstone gets a true message instead | ✅ confirmed live on `?lesson=6` load: "✓ This is the garden you grew across the lessons — now it's yours to change." |
| Branch keyed on presence of slot items, not a hardcoded lesson index | ✅ asserted by test (`hasSlots` computed from `items.some(role === "slot")`) |

**AUTHOR-DRAFTED, FLAG FOR STRIKE:** the capstone completion sentence above.

### §7.3 — Full vocabulary on the sandbox

| Check | Result |
|---|---|
| `renderKey` branches to the full imported lists for the capstone | ✅ asserted by test against the exact ternary |
| `fullVocab()` sources from `PLACEABLES`/`SKY_PHRASES`/`GROUND_PHRASES`/`NAMING_WORDS` — no second hand-kept list | ✅ asserted by test |
| Capstone key shows words absent from its own items (moon, firefly, all four sky phrases) | ✅ confirmed live: key listed sun/moon/star/bee/two-bees/firefly/two-fireflies/flower/two-flowers (9 placeables) and all four sky phrases ("early morning", "middle of the afternoon", "just before dark", "the middle of the night") — the capstone's own items only ever use sun/two-bees/two-flowers and one sky phrase |

### §7.7 — Reset button

| Check | Result |
|---|---|
| Reset control in `.freeplay-top` toggles, plainly labelled | ✅ "Reset garden" button confirmed live, sits alongside "hide hints"/"hide key" |
| Restores `LESSONS[currentLesson].items.map(it => it.text).join("\n")` | ✅ asserted by test; confirmed live — edited the freeplay editor (added `star of 400, 300`), clicked Reset, `#freeplay.value` came back byte-identical to the lesson's starting garden text |
| Re-runs/repaints after reset | ✅ confirmed live — `runFreeplay()` called, picture repainted without the added star |
| Light confirm before clobbering non-trivial edits | ✅ implemented — confirm only fires when the current text differs from the starting garden; a no-op reset (nothing to lose) skips the prompt |

### Framing

| Check | Result |
|---|---|
| Lesson 7's `say` copy reads as sandbox/graduation | ✅ rewritten to name the full toolkit and the Reset safety net explicitly, coherent with §7.3/§7.6 |

## §8 — Save de-escalation

| Check | Result |
|---|---|
| `hasUnsavedWork()` narrowed: non-capstone lessons always return `false` | ✅ asserted by test; confirmed live — completed lesson 1's sky slot only (partial slot progress), switched to lesson 2: no dialog, no download |
| Capstone: unsaved only when free-play text differs from its own starting garden | ✅ asserted by test; confirmed live in two directions — (a) capstone with an added `star of 400, 300` line: switching to lesson 1 showed the save-first dialog; (b) after Reset restored the starting text, switching to lesson 1 immediately, no dialog |
| Dialog copy matches its real (capstone-only) trigger | ✅ confirmed live — "Save your garden first? You've changed the garden in this sandbox…", buttons "Save my garden, then continue" / "Switch without saving" / "Stay here"; old "Start the next lesson?" / "Each lesson is its own garden" framing removed (asserted by test) |
| `beforeunload` still gated on the same narrowed `hasUnsavedWork()` | ✅ asserted by test — no separate/un-narrowed check left behind |
| File-saving (`saveGardenFile`) stays reachable only from the capstone (the dialog's "Save" option, or the capstone's own "Save my garden file" button) | ✅ confirmed live — capstone save button produced a real `.planes` download; the dialog's save button routes through the same `proceedLessonSwitch(true)` → `saveGardenFile()` call site, unchanged |
| Net: linear 1→2→…→7 sees zero downloads, zero dialogs | ✅ confirmed live end-to-end across lessons 1→2 (partial progress) and 6→7 (full completion via "Next lesson →") |

## §9 — Invariants

- **Engine unmodified**: `git diff --stat main` touches exactly `tutor.html`
  and `js/test/tutor_redesign.test.mjs`. `js/browser_main.mjs`,
  `js/paint/why.mjs`, `js/paint/hit.mjs`, `js/scene_vocab.mjs`, and
  `paint/scene.planes` are blob-identical to `main`.
- **One statement per line**: unaffected by this build — `lessonProgramText`
  still joins items with a real `"\n"` (pre-existing test, still passing);
  every screenshot's stack/cue/worked-example/capstone reads one Planes
  statement per line.
- **`LESSONS.length` is the only lesson count**: the new Next-lesson gate
  reads `currentLesson >= LESSONS.length - 1`, asserted by test — no
  hardcoded `7` was introduced.
- **Key derives from `scene_vocab.mjs`**: lessons 1–6 unchanged
  (`vocabForLesson`); the capstone's new full-vocab branch sources directly
  from the same imported `PLACEABLES`/`SKY_PHRASES`/`GROUND_PHRASES`/
  `NAMING_WORDS` — never a second hand-kept list — asserted by test.
- **Asking performs nothing**: `renderCardCore` unmodified; unaffected by
  this build's changes.
- **Every placed element remains interrogable**: the §5 backdrop-region path
  (`backdropLineAt`) is unmodified.
- **All v35.0-preserved features still function**: save-first dialog (now
  narrowed), `beforeunload` (now narrowed), friendly error softening, SVG/PNG
  export, garden save/reopen + seed, certificate + print (confirmed live —
  opened the certificate, seed `475598` matched the just-saved file's ticket,
  signature line shows the new "write a line, ask it why"), click-to-line
  highlight, coordinate orientation tip, empty-because invite, reveal motion.

## Test suite

- `node --test js/test/*.test.mjs` → **992/992 passing** (46 in
  `js/test/tutor_redesign.test.mjs`, up from 30 — the new "H" group covers
  all ten review items structurally).
- `.venv/bin/pytest test_gate.py` → **19/19 passing**, including the
  verify-script retirement rule (`test_no_verification_script_exists_for_
  the_gate_not_to_run`) — this build's assertions were graduated straight
  into `js/test/tutor_redesign.test.mjs` rather than shipped as a
  `scripts/verify-*.mjs` one-off, for the same reason
  `js/test/crossing_port.test.mjs`'s own header gives.
- `scripts/check_pages_surface.py` → 9 pages resolve cleanly, `tutor.html`
  among them.

## Real defect found and fixed during this build

1. **A test assertion matched the wrong occurrence of a shared phrase.**
   `js/test/tutor_redesign.test.mjs`'s "keep-growing card" test searched for
   the literal text `"keep growing it"`, which also appears in `tutor.html`'s
   own `<head>` comment block (predating this build) — the test read 1700
   characters of CSS instead of the capcard's actual content and failed.
   Fixed by anchoring the search to the capcard's own heading markup
   (`keep growing it</h3>`) instead of the bare phrase.

## AUTHOR-DRAFTED copy flagged for architect review

Per the build prompt's explicit instruction, the following is drafted
content, implemented as specified but not architect-locked:

1. Header tagline: "write a line, watch it grow, ask it why"
2. Certificate signature line: "write a line, ask it why"
3. Capstone completion message (no-slot lessons): "This is the garden you
   grew across the lessons — now it's yours to change."
4. The "keep growing it" primer's full copy — affirmation, the four
   concrete tries, and the one-line forward pointer to `index.html`
