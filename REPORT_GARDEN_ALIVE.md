# A garden that lives

The garden was specified once as one paragraph at the end of a build about
drawing verbs, and it was built the way it was specified: as a footnote. This
build gives it a play loop, weather, rain, sound, and a way to ask any visible
thing where it came from — and, along the way, measures why the previous
version could not have had a play loop at all.

---

## What the measurement found, before anything was built

`scripts/measure-density.mjs` times one tick end to end — prelude, parse,
run — at four densities on both implementations, and reports the largest
command count that stays under a 60ms frame. It is a measurement, nothing in
`ci.sh` runs it, and it never fails a build.

| draw commands | `js/interp.mjs` | `interp.py` |
|---:|---:|---:|
| 51 | 13.7 ms | 36.6 ms |
| 201 | 14.3 ms | 123.1 ms |
| 501 | 35.6 ms | 320.2 ms |
| 1001 | 68.0 ms | 647.4 ms |

**SCENE_BUDGET = 877** — the JavaScript number, because the garden is drawn by
a browser and `interp.py` has no canvas. The Python column is here because the
program has to stay *runnable* there, which is a correctness fact and not a
frame budget.

Then the same instrument was pointed at the garden that already existed:

> **3,635 to 4,226 commands. 393 to 598 milliseconds a tick.**

Five times the budget, ten times the frame. That is the whole explanation for
"no play loop — the day scrubber replaces both": the scene could not be played
because it could not be computed fast enough, and nobody had measured it. The
rewritten scene spends **750 to 868 commands and 28 to 34 milliseconds**, at
full density, with no count reduced to make it fit.

Two things got it there, and neither was drawing less:

- **`spread` was written with `mod`, and `mod` is a doubling recursion** —
  about thirty Planes frames a call, five hundred calls a frame, 110ms a tick
  on its own. Rewritten over `whole of`, one exact big-integer divmod, it costs
  nothing measurable. `paint/math.planes`'s new `part` and `floor` are written
  the same way and are now constant-time *and* correct for negatives.
- **The hash was quadratic, and a quadratic modulo a power of two is not
  uniform.** `fbm` came out with a range of 0.47 where it should have had 1.0,
  and it never rained once in three days. The cubic — scattered first, because
  its own constant term dominates for small n — is uniform, and the weather
  works.

`benchmarks/density.md` carries the numbers and one further finding: the
command count is the wrong unit. The probe spends 0.07ms a command and the
garden 0.04, because a probe mark is two commands of arithmetic and a garden
mark is often one command carrying six. A build that changes the scene should
re-measure the milliseconds rather than trust the conversion.

---

## Phase 5a: which branch, and the evidence

**The runtime effect log does NOT carry the derivation.** `interp.py`'s `Show`
appends `("show", text)` to `self.effects` — text only, no node. The derivation
*is* passed to `maybe_record(...)`, but that is the record plane: a no-op
unless `record=True`, and explicitly forbidden from changing `self.effects`,
`self.output` or the static surface, so a page cannot turn it on to ask a
question.

Branch taken: **`trace` beside `output`**, in both implementations. One entry
per emitted line, in the same order and always the same length, carrying the
`Deriv` of the shown expression and its source line. It performs nothing — the
node is the one `eval` already built, kept rather than dropped —
and `test_js_interp.py` pins that the effect log is byte-identical either way.

### The part that was not in the plan

A `show` inside `draw.planes` is on line 45 **of draw.planes**, and a page
showing `garden.planes` that highlights line 45 points the reader at a file
that is not on their screen. So the interpreter now knows which file a function
was defined in (`Function.file`), which file is executing (`current_file`), and
where each active call was *written* (`call_sites`). A `show` in a module
reports the innermost call site written in the entry file — for
`circle of body-x, body-y, disc-r`, exactly the line that was clicked. Both
implementations carry it; `test_js_interp.py` compares the canonical traces of
every `.planes` file in the repository and they agree entry for entry.

Finding, en route: `exec_stmt`'s `FuncDef` case re-registers a function when
the definition is *reached*, replacing the hoisted one. Without carrying the
file across that second registration, every hoisted function was silently
replaced by a file-less copy and every trace line pointed at a call site
instead of at the `show` itself. Present in both implementations, fixed in
both.

---

## The cloud-blur gap, for a later protocol version

The mockup's clouds use `filter: blur()`, which softens **a shape's own edge**.
The drawing protocol's `shadow` blurs **a copy behind** a shape. There is no
verb that softens a mark's edge, so the clouds here read as hard shapes with a
halo. No blur verb was added. Recorded for v3 alongside image drawing.

A second, smaller one found the same way: `gradient radial` has no inner-radius
argument, so the vignette's transparent-to-dark ramp runs the full radius
instead of starting partway out. Softer than the mockup's, and the closest the
verb reaches.

---

## Two protocols now, one generator

`planes-sound-protocol-v1.md` is the drawing protocol's architecture applied to
a second medium, deliberately: a prefix that cannot collide with prose, a
version declaration that must precede the first sounding command, a refusal
contract, a fixed-arity verb table, one shared normative walk, and **two
players** — Web Audio (`js/sound/audio.mjs`) and a `.wav` writer
(`js/sound/wav.mjs`) — because with one player, semantics leak into it and the
shared walk stops being normative.

**Pitch is a ratio.** `sound note 3 2 1 0.5 0.4` is a perfect fifth above the
base, one octave up, starting half a second into the tick, lasting four tenths.
Just intonation is expressible exactly in this language and equal temperament
is not; a protocol carrying a frequency would force every program to round
before it spoke, and the rounding would be the first thing a `why` chain
reached. The base is pinned at 220 Hz so two players cannot disagree.

`scripts/protocol_gen.mjs` generates `sound/protocol.json` and
`sound/errors.json` alongside `protocol/`'s, from one descriptor table rather
than a second generator — the scanner, extractors and arity prober are about
the *shape* both protocol modules were written in, not about drawing.
`protocol/*.json` is byte-identical apart from line numbers that moved when
`stream.mjs` gained its line index.

### Two words moved, and both moved in the specification too

`lasts`, not `for`: `for` is reserved in Planes and a parameter cannot be named
it. `silence`, not `clear`: `clear` is already a **drawing** verb, and a
program emitting both protocols — the entire point of the two prefixes —
imports both libraries into one module graph, where two helpers of one name is
a collision the loader refuses. `planes-drawing-protocol-v2.md` §6.5 already
states the rule for `label` and `corner`; this is its second application.

Writing the second player found two things the first would have hidden:
`silence` has to clear the schedule inside the walk rather than inside a
player, and a note's wave and gain are the state at the moment it was
**emitted**, not at the end of the stream.

---

## Where this build did not do as it was told, and why

Three places. All three are the build prompt meeting a standing rule of this
repository, and in all three the standing rule won.

**1. No `scripts/verify-garden.mjs`.** The prompt asks for one, committed. This
repository forbids one in either language and gates on its absence
(`test_gate.py`, and the retirement rule at length in `scripts/ci.sh`): a
build's verification script graduates into a suite or is deleted when the build
merges. The last build to ignore that shipped a `scripts/verify-*.mjs` that
reported BLOCKING FAILURE on green main for two builds because nothing ran it.
Every one of §12's checks is in **`js/test/garden_gate.test.mjs`**, which
`node --test` runs on every gate, with the letters kept so the correspondence
is checkable.

**2. Gate H is asserted, not byte-compared.** `grammar/errors.json` is a
*projection* of the Python source and records `file.py:line` for every error it
catalogues. Adding a field and a comment to `interp.py` moved a hundred of
those line numbers without touching a single tag, template or fix — so
`git diff --stat main -- grammar/` is not empty, and a byte-identity check
would have failed a build that changed nothing about the language. The suite
asserts the thing that matters instead, and is stronger where it counts: no
other file under `grammar/` moved at all, every changed line inside
`errors.json` is a source location and nothing else, and the entry count and
tag set match `main` exactly. A new tag, a changed message or a lost fix clause
all still fail.

**3. `why` has no source line in the trace, and records 0.** A `Why` node does
not carry one. Giving it one is a change to the AST's **shape**, and the AST's
shape is pinned by `grammar/parser.planes` — the self-hosted parser this
repository checks its own parser against — so an AST field is a grammar change.
Adding it turned `test_corpus.py`, `test_parser_in_planes.py` and
`test_js_metacircular.py` red, which is the self-hosted stack doing exactly
what it exists to do. Reverted. Nothing is lost: the panel asks about drawn
marks, which are `show`s, and `why` prints its own explanation already.

And one place the corpus lost coverage, honestly:

**`clip`, `unclip` and `dash` are back on the coverage allowlist.** The garden
was the only program that drew them, and it drew them because the corpus needed
the coverage rather than because the picture did — a masked region and a dashed
outline in a scene with neither a window nor a dotted line in it. Gate G
forbids all three and blocks on their absence, which settles it in the
picture's favour: a corpus that keeps a verb alive by planting it somewhere it
does not belong is measuring itself, not the protocol. All three are still
exercised directly, in both sinks, by `js/test/protocol_v2.test.mjs`; what is
missing is a real program that reaches for them, and the allowlist is the
honest place to say so.

---

## Named findings, reported and not fixed

- **`whole of` rounds to nearest, half away from zero, and its own refusal
  message says it "rounds a number toward zero".** `whole of 2.5` is 3 and
  `whole of -3.7` is -4; truncation would give 2 and -3. The message lives in
  `interp.py` and its twin and nothing in this build has business editing
  either. `paint/math.planes` states the real behaviour where it depends on it.
- **A hyphenated near-miss is a command with no verb, in both protocols.**
  `sound-ish` and `draw-ish` both reach their parser as commands, because both
  test the prefix with `\b` and `\b` sits between a letter and a hyphen. Both
  specifications say "a command begins with the WORD". Matched deliberately
  rather than diverged from — fixing it in one protocol and not the other would
  be worse than the quirk, and fixing it in both changes what an existing
  drawing stream means. Pinned by a test so it cannot drift silently.
- **`marks.mjs`, `hit.mjs` and `wav.mjs` joined `GEOMETRY_ONLY`.**
  `test_exactness.py` forbids host trigonometry, with four renderer-side files
  named one by one so a fifth cannot join quietly. These three are the same
  category arrived at from the other side: `painter.mjs` needs no trigonometry
  because a canvas has `rotate`, and these have no context to delegate to. Each
  is named with its reason.
- **`garden.html`'s source pane was never editable in the sense it
  advertised.** It said "editable — click a day/seed control to re-run with
  edits applied"; nothing read the textarea back, and only "Reload modules"
  re-fetched the file. It is now a read-only, line-addressable view, which is
  also what hovering a line to light up its marks needs.

---

## The gate

Automated, on merged-clean `main` plus this branch:

- `scripts/ci.sh` green end to end.
- **60 Python suites, 60 reporting, 1,219 oks** (1,191 before).
- **651 JavaScript tests, 0 failures** (398 before).
- `ruff` clean; `mypy` clean over 96 source files.
- `grammar_gen.py --check` and `protocol_gen.mjs --check` (all four
  projections) up to date.
- Counts unchanged: **32 keywords, 12 builtins, 7 effect kinds.**
- `paint.html`, `turtle.planes`, `bloom.planes` and `snake.planes` untouched;
  the committed pre-v2 baselines still render byte-identically once the new
  `data-line` annotation is stripped from both sides.

Visual, served over `python3 -m http.server 8000`, all nine steps:

1. A garden is visible on load. **PASS**
2. Play moves it: 1× advances 11 ticks in 3 seconds (4/s, as designed); 16×
   advances 252 ticks in 4 seconds, a full day in about 1.6s. **PASS**
3. Sun rises, the sky warms through dawn, flowers open, bees appear; at dusk it
   reverses, stars come out, fireflies replace the bees and brighten where they
   overlap. **PASS**
4. Rain: the readout goes `drizzle → raining → clear` across the three days,
   the sky greys and the ground darkens. **PASS**
5. Sound on, then play: **29 notes in six seconds while playing, 0 while
   scrubbing.** Frequencies 733.3, 660, 550, 110 — exactly 220 × 2 × 5/3, 3/2,
   5/4 and 220 × 2⁻¹. **PASS**
6. Clicking a flower names its line, its coordinates and radius with the step
   each came from, three `because` clauses including *"tall enough to catch the
   light, short enough to stay in frame"*, one step further, its note (1/1, 110
   Hz), the origin — *"the seed — you chose this. Nothing outside the program
   was touched."* — the badge *"approximate, and identical on every machine"*,
   and the line that asking performed nothing. The effect surface beside the
   canvas is byte-identical before and after. **PASS**
7. Hovering the petal line outlines every petal of every flower. **PASS**
8. Save SVG and Save PNG both write files; the SVG's `stdDeviation="15"` on a
   480-wide document and the canvas export's 30 on a 960-wide one are the same
   shadow relative to the picture. **PASS**
9. `paint.html` unchanged and still renders turtle identically. **PASS**

And the one that matters most, through the real Save PNG button rather than a
test harness — scrub to 60, away to 5, back to 60:

```
f5c4ff052da71f7c2fa55da83737cf183c0681df8c13c50b8e1814988b9f4bb6  a60.png
f5c4ff052da71f7c2fa55da83737cf183c0681df8c13c50b8e1814988b9f4bb6  b60.png
```

---

*`feat/tutor-ask-why` was never created — its Phases 1–3 are §7 here and its
Phase 4 landed in `garden.html`. There is no branch to delete.*
