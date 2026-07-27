# The composition defect closed, and the CLI ported

**Build:** S6, the composition defect and the CLI. **Branch:** `fix/render-composition-and-cli`, based on `main` at PR #23's merge (`cca9a2f`).
**Spec:** the render finding in `REPORT_ANALYSER_JS.md`; `render.py` and the grammar's node kinds as the source.

The analyser port (S5) found a defect in the thing it was porting: `render` produces source that does not reparse. It was reported, not fixed, because a port may not edit its own specification. This build fixes it in both implementations — and the fix turned out to be far larger than the reported instance. It also ports the last surface that is neither runtime nor guarantee: the standalone CLI.

Counts stay **32 / 10 / 7 / 8**. Only `render.py` changed among non-test Python source; no `grammar/*.planes` changed.

---

## A.0 — the mechanism, confirmed and broader than described

**The mechanism is as described, and the class is much broader.** The report named a multi-argument call used as a record-field value whose argument commas collide with the record's field separators, at `grammar/interp.planes:717`. Reproducing it (Phase 1, committed before any fix) confirmed the collision mechanism and corrected the details:

- The actual source is `grammar/interp.planes:1152`: `{ ..., status: (normal-of of nothing, outer), kept: false, ... }`. The multi-arg call is **parenthesised in the source**; `render` **strips** those protective parens, and the bare commas then collide with the following field.
- **Two** corpus files fail the render round-trip, not one: `grammar/interp.planes` **and** `grammar/parser.planes` (S5 reported only the former).
- Even a **one-argument** call breaks: `name of (a), k2` reads `k2` as a second bare-primary argument (`of` takes a bare primary, not only a parenthesised one).
- The greedy tail is not unique to calls: a **RecordUpdate**'s `with` field list (`base with a: 1, b: 2`) extends on a following `name: expr` the same way.

So `724 :717` was approximate, the site was parenthesised-in-source not bare, and the footprint was two files and two expression kinds. The comma-collision mechanism itself held.

---

## The fix, and the positions enumerated from the grammar (A.1)

No grammar change, no new separator, no amber site — the parser is correct; the renderer emitted text whose meaning differed from the AST. The fix is parenthesisation, applied identically in `render.py` (the only Python source changed) and `render.mjs`.

Phase 2 fixed the four defects that block corpus round-trip:

| # | defect | position | fix |
|---|---|---|---|
| 1 | greedy comma tail (call `of` list, record-update `with` list) | record-field value, list element | `_comma_element` wraps by tail kind × separator kind |
| 2 | `first N of L` — bare Var count swallowed as `k of parts`; sub-unary list split | both operands | wrap both operands as closed primaries |
| 3 | `X.name` on a greedy-tail base — `(call).kind` binds `.kind` to the last arg | field base | `_field_base` wraps a `_COMPOUND`-or-greedy base |
| 4 | `or fail as tag:` handler block dropped entirely | statement-level or-fail | render the head, then the handler block |

Phase 3's generator then showed these four were instances of **one systematic gap** (below), fixed by completing the parenthesisation model. The positions, enumerated from the grammar rather than a fixed list:

- **Operand positions** — read at less than full precedence, via `render_operand`: BinOp sides, `Not`/`is nothing`/`plus` operands, `round` arguments, field base. `_COMPOUND` (the set wrapped here) was `{BinOp, Not, IsNothing}`; it is now `{BinOp, Not, IsNothing, ListPlus, OrFail, RecordUpdate, ForEach}` — the low-precedence kinds it had been missing.
- **Trailing-delimiter positions** — read up to a keyword or `:`: for-each source and `where`, `if`/`when` subject, `write` value and destination, `fail` message, or-fail inner. A new `_delimited` helper wraps only the **`OPEN_TRAILING`** kinds `{OrFail, RecordUpdate, ForEach}` here — deliberately **not** the full `_COMPOUND`, so `if x > 0:` does not gain needless parens.
- **Comma-list positions** — record-literal fields, record-update fields, list items, and `when`-match values — via `_comma_element`, wrapping greedy tails per separator kind.

`render` now round-trips the **whole corpus** — 34/34 standalone-parseable files, `grammar/interp.planes` and `grammar/parser.planes` for the first time — byte-identically between the two implementations.

---

## Every canonical-text change, with its reason (A.2)

The render change alters canonical output only for files containing the affected constructs. No test pins the exact rendered text of those constructs except two, both updated deliberately:

1. **`test_render_composition.py`** — Phase 1 pinned the *broken* behaviour (so the suite stayed green — invariant 7). Phase 2 **flipped** each assertion to the fixed behaviour: `test_call_in_record_round_trips` (was `..._currently_fails_to_reparse`), `test_every_corpus_file_now_round_trips` (was `test_the_two_corpus_files_that_fail...`), plus a distilled case per defect.
2. **`test_js_render.py`** — S5's `test_js_reproduces_render_py_roundtrip_limitation_on_interp` asserted interp.planes *fails* reparse on both implementations. The limitation is fixed, so it is **replaced** by `test_the_two_grammar_files_now_round_trip_on_both_implementations` (its opposite), and the module docstring updated to record the change.

Every other render-related test (`test_render.py`'s round-trips, the marker tests, `test_fail.py`, `test_record.py`, `test_annotation.py`) is `ast_equal`-based or uses non-greedy constructs, and passed unchanged — parenthesisation preserves the AST, and Python↔JS byte-identity is preserved because both sides apply the identical rule.

---

## Composition coverage: 680 pairs, and it found the class (A.3)

The generator nests **every** expression kind inside **every** kind that can contain one — the matrix derived from the grammar (`_INNER` = every kind `render_expr` emits; `_CONTAINER` = every grammar position that reads a sub-expression). Each case is built as **source and parsed first**, so only parser-reachable ASTs are tested; it is deterministic and its cases are named (`container <- inner`). It runs on both implementations and cross-implementation — byte-identical render plus a both-sides round-trip **is** the cross-implementation round-trip (Python render == JS render, and each reparses to the AST it was rendered from).

**It found a second defect, and then 38 more.** Beyond the four Phase 2 fixed, the generator surfaced **39 additional failing compositions**, all one root cause: the renderer's parenthesisation model was systematically incomplete — `_COMPOUND` held only three of the seven low-precedence kinds, and several positions bypassed `render_operand` entirely. This is the strongest possible justification for the phase: the defect was never one bug or four, but a structural gap that per-node-kind coverage cannot see, because every individual kind *is* handled — the bug lives in valid compositions of handled kinds.

After completing the model: **680 pairs, 680 reachable, 0 failures**, on both implementations and cross-implementation.

Two things the corpus round-trip never caught, and only the generator did: `BinOp` was tested with op `+` but never op `first`, and no field-access-on-a-call appeared in the round-trip set — per-kind coverage passed both clean.

---

## What composition coverage would cost for `interp` and `shapes` (A.4 — reported, not built)

Both dispatch exhaustively over AST kinds and would benefit from the same generalisation. The cost is **lower** than it was for render, and their agreement corpora already cover **more** incidentally — for a structural reason:

- **Incidental coverage is already better.** render's defects hid specifically because `render.py`'s own round-trip test set (`*.planes` + `demo/**`) *excluded* the two files exercising them (`grammar/interp.planes`, `grammar/parser.planes`). `interp` and `shapes` agreement is checked on the **whole** corpus, those two files included — so every composition that appears in a real corpus file is already covered for them. The residual gap is only *synthetic* compositions absent from every corpus file (e.g. `(for each i in xs: i) + 1`).
- **`shapes` — low-moderate cost.** Reuse the 680-pair source matrix; the oracle is structural agreement (JS `as_json` + derivation vs Python), and the analyser is total, so no case can throw. A `shapes-batch` command analogous to `render-batch` would run it in one process. Estimated: a day, no new capability.
- **`interp` — moderate cost.** Reuse the matrix, but each composition must be made a **runnable, value-producing** program (defined functions, no unstubbed effects) so the oracle can compare output/value/tag on both runtimes. The harness to make each composition runnable is the real cost, not the run.

Neither is built here (A.4). Recommendation: `shapes` composition coverage is cheap enough to fold into a future build; `interp`'s is worth it only if a composition-specific evaluation defect is ever suspected.

---

## The CLI (A.5)

`js/shapes_cli.mjs` — `--index`, `--search`, `--diff` — is a thin Node-only shell. Every line of analysis is already in the engine: `--index` reads `is_library`/`is_pure`/`boundaries`, `--search` reads `touches`/`at` and `Effect`'s text form, `--diff` reads `diff`/`SurfaceDiff`. **Nothing the engine lacked** — no command was a finding. It agrees with the Python CLI on output text **and** exit code across 10 cases (including the empty-search "nothing touches" line and `--diff`'s significant/not-significant 1/0 exit — the CI-gate contract). Node-only, and verified unreachable from the browser bundle (invariant 6: the browser graph is 13 modules, `shapes_cli.mjs` absent, 0 `node:` imports reachable).

---

## The metacircular check, re-run

Canonical output changed, so both metacircular checks were re-run and still find nothing: `shapes.js` over the three grammar stages agrees with `shapes.py` (`interp.planes` still all seven kinds on both), and the Planes lexer/parser/interpreter running on `js/interp.mjs` still process the corpus identically to the Python reference. The render change touches neither analysis nor evaluation, and the parser/lexer canonical AST/token forms are render-independent, so all prior agreement holds.

---

## What this build disproved about this prompt

Never empty. Five things:

1. **The fix's scope was an order of magnitude larger than framed.** A.1 framed the fix as parenthesising "any multi-argument call." The defect was a *class* of five families (call comma-tail, record-update comma-tail, the `first` operator, field base, and the low-precedence operand/delimiter positions), one root cause: an incomplete parenthesisation model. "Multi-argument call" was one visible instance of a systematic renderer gap — which is exactly the disproof A.3 was built to produce.
2. **A.0's locating details were approximate.** The site is `interp.planes:1152`, not `:717`; the call is *parenthesised in source* (render strips it), not bare; the footprint is *two* files, not one; and a *one*-argument call breaks too. The comma-collision mechanism held; the specifics did not.
3. **Invariant 1 forbids what A.2 and A.3 require.** "Only `render.py` changes on the Python side. No other `.py`" literally prohibits the canonical-text test updates A.2 mandates and the composition test A.3 mandates. Resolved toward evident intent (§9 mode 9): only `render.py` changes among *non-test* Python source; test files are added and updated as the rulings require.
4. **Phase 1 contradicts invariant 7.** "Commit the failing test" (Phase 1) versus "`scripts/ci.sh` clean at every commit" (invariant 7) cannot both hold for a red test. Resolved by committing a *passing* test that pins the current broken behaviour, then flipping it in Phase 2 — the reproduction is still committed before the fix.
5. **"Finding a second defect" undersold the outcome.** A.3 said a second defect would justify the phase. The generator found **thirty-nine** more, all one root cause — the phase was justified many times over, and the "class not instance" framing was vindicated literally.

---

## What remains, and whether any of it is runtime or guarantee

**Nothing runtime or guarantee remains.** The language (lexer, parser, interpreter) shipped in S4; the guarantee (analyser, renderer, rule checker) in S5; and this build closed the last correctness gap in the renderer and ported the CLI. `render` now round-trips the entire corpus, both implementations agree byte-for-byte, and the composition class is closed by an exhaustive generator.

What is left is **Python-side language-maintenance tooling** — `grammar_gen.py` (regenerates the grammar tables), `core_check.py` (audits `interp.planes` against the declared core), `audit_locked_vs_built.py`, and `scripts/*.py`. These are about *maintaining* the language, not *running* it or *answering its questions*. None is runtime; none is guarantee. Planes is complete on the JavaScript target for everything a user does with it — run a program, see what it touches, see where a value came from, render it back, check its rules, and diff its surface — with no Python anywhere.
