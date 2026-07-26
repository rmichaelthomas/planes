# The analyser ported — the guarantee, without Python

**Build:** S5, the analyser ported. **Branch:** `feat/analyser-js`, based on `main` at PR #22's merge (`a0e8b47`).
**Spec:** `shapes.py`, `render.py`, `rules.py` as the specification; `REPORT_SECOND_HOST.md` at HEAD.

Planes already ran without Python. It did not yet *answer the two questions it exists to answer* without Python — what does this program touch, and where did a value come from. This build ports the analyser (`shapes.py`), the renderer (`render.py`), and the rule checker (`rules.py`) to JavaScript, and puts the effect surface in the browser. It is the same agreement technique applied a fifth time, against a fifth artifact. It is not new language.

Every count below was re-established at the §0 baseline: counts **32 / 10 / 7 / 8**, `ruff` clean, `mypy` clean (73 files), `scripts/ci.sh` green.

---

## What shipped, phase by phase

| Phase | Module | Agreement | Result |
|---|---|---|---|
| 1 | `js/sha256.mjs` | `test_js_hash.py` 6/6 | SHA-256 byte-identical to `hashlib` |
| 2 | `js/shapes.mjs` (+`shapes_node.mjs`) | `test_js_shapes.py` 7/7, `test_js_shapes_derivation.py` 2/2 | the analyser agrees, corpus + inline + derivation |
| 3 | `js/render.mjs` | `test_js_render.py` 8/8 | canonical source byte-for-byte, every kind, cross-impl both ways |
| 4 | `js/rules.mjs` | `test_js_rules.py` 7/7 | pass/fail + message text + fingerprints + markers |
| 5 | `index.html` + `js/browser_main.mjs` | `js/test/browser.test.mjs` 8/8 | the effect surface, in a browser, nothing executed |
| 6 | metacircular | `test_js_metacircular_shapes.py` 3/3 | all-seven surface on `interp.planes`, from both analysers |

New JS source: `sha256.mjs`, `shapes.mjs`, `shapes_node.mjs`, `render.mjs`, `rules.mjs` — **2,263 lines**. New tests: **33** Python agreement functions across 6 files, **21** JS unit tests across 4 files, plus 3 browser-surface tests. No `.py` file and no `grammar/*.planes` file changed — the diff is `js/`, new `test_js_*.py`, and `index.html`.

---

## The hash (A.2)

**Algorithm:** `rules.py`'s `fingerprint()` is `hashlib.sha256(canonical.encode()).hexdigest()[:6]`, where `canonical = "\x1f".join([subject, assertion, kind, target or ""])`. So the requirement is SHA-256 over UTF-8 bytes, byte-identical to `hashlib`, truncated to six hex. (The prompt's PROVENANCE noted the algorithm "is not established" — §0 established it: SHA-256.)

**Implementation:** `js/sha256.mjs`, **~130 lines**, the FIPS 180-4 algorithm itself — synchronous, importing nothing Node-only (`TextEncoder` is a global), so it is browser-safe. **Not** WebCrypto: `crypto.subtle.digest` is async, and making it the fingerprint path would colour `async` up through `rules.js` and every caller that checks a rule (A.2). A synchronous pure-JS hash colours nothing.

**Byte-identity evidence:** verified against `hashlib` across the empty string (anchored to the known digest `e3b0c442…`), ASCII, multi-byte UTF-8 (`café`, `日本語`, `😀`, ZWJ sequences), inputs spanning the 64-byte block boundary (lengths 50–69, and multi-byte chars straddling byte 64), and the actual rule-fingerprint canonical strings. Full 64-character digests agree, so the six-hex truncation agrees.

---

## Effect-surface agreement, per file — the central result (A.1, A.3)

`shapes.js` ships first and was verified before `render.js` or `rules.js` began (A.1). The oracle reuses the existing published surface form — `shapes_cli.as_json` — not a fourth invented form (A.3).

- **Whole corpus, following imports:** the published surface (`as_json(analyse_file(f, follow))`) is identical between the two analysers for **52 of the 66** `.planes` files — every file that analyses standalone; the remainder are the intentionally ambiguous `probe/amber` fixtures and multi-file-only fragments that don't parse standalone (covered by the parser/module suites). This exercises the multi-file constant-propagation and rename paths (`demo/app/`, `demo/_ren*`).
- **The hn scraper**, called out: network + file, surface identical.
- **34 inline programs** mirroring `test_shapes.py`: specialisation, widening at branch/loop/when joins, recursion never specialised, libraries, computed targets that keep the host, foreign declarations (declared, undeclared, doing-nothing), and the ten adversarial effect-smuggling attempts.
- **Per-function breakdown** agrees across the corpus and inline.
- **Derivation graph:** `origins_of` and the full derivation tree agree on 40 file=null programs — the static analogue of `why`.
- **Totality (A.1 ruling 1):** the analyser never raises on a parseable program, including partially-resolvable ones (calls to undefined functions, undeclared foreigns) — asserted on the JS side, agreeing with Python.

### Where widening was hard to reproduce, and how it was resolved

`shapes.py` compares `Effect`s by value through a frozen dataclass hashed into `set`s, with `derivation` excluded from equality. JavaScript `Set` is reference-identity, so a faithful port needed an explicit value-identity set (`EffectSet`): keyed by `(kind, boundary, target, computed, site, claimed)`, **first-wins on collision** so the *earlier* derivation survives — exactly as Python `set` union keeps the existing element. This is the one place the port's correctness turned on a subtlety of the source language's semantics rather than its logic: get first-wins wrong and the effect kinds still agree, but a derivation (and therefore an `origins_of` / rule "derived from" line) can diverge. Ordering never reaches output — every surface field is sorted by `(boundary, kind, target)` — and I confirmed the Python surface is deterministic across `PYTHONHASHSEED` values, so the sort fully determines output. **A.1 ruling 2 holds:** the JS analyser is neither more nor less precise than Python's — widening is reproduced exactly, not improved.

No type information was introduced (A.1 ruling 3): `shapes.js` computes the guarantee by dispatching on AST node kind and folding constants, never consulting a value type — the strongest evidence for the language's no-types decision, carried into a second implementation.

---

## `render.js` — every kind, cross-implementation, and a `render.py` finding (A.4, A.6)

`render.py`'s output is canonical text, so agreement is **byte-for-byte across 34 standalone-parseable files** (including `grammar/interp.planes`, the largest program in the repo). It gets `render.py`'s own treatment: a real case for **every AST node kind** (30 kinds via snippets; coverage checked against every dataclass Python's lexer defines), no safe fallback (an unhandled kind raises, naming it — `renderExpr` on the dead `Builtin`, `renderStmt` on `Because`), a round-trip per kind, **plus cross-implementation round-trips both directions** (Python render → JS reparse, and JS render → Python reparse) over every file `render.py` guarantees a round-trip for.

**FINDING in `render.py`, reported not fixed (A.6):** `render.py` renders a **multi-argument call used as a record-field value** in a form it cannot itself reparse. In `grammar/interp.planes` (around the rendered line 717), `give { …, status: normal-of of (nothing), (outer), kept: false, … }` renders the call `normal-of of (nothing), (outer)` unparenthesised, so its argument-list commas collide with the record's field separators; the reparse fails with `expected }, found ':'`. `render.py`'s own round-trip test set (`*.planes` + `demo/**`) contains no file using that construct, so its tests never caught it — precisely the class of latent bug A.4 warns about. The JS renderer reproduces `render.py` **byte-for-byte**, so its round-trip fails on exactly that one file and no other. This is asserted directly (`test_js_reproduces_render_py_roundtrip_limitation_on_interp`): agreement on the limitation is faithfulness, and the fix belongs in `render.py`, out of scope here.

Cross-implementation round-tripping found nothing a same-side round-trip missed *except* by confirming the above: the byte-identical render means both implementations produce the same non-reparseable text, and both fail the reparse identically.

---

## `rules.js` — agreement, and no message diverged (A.2, A.3)

Every scenario in `test_rules.py` was driven through both `check()` implementations and the full result compared — each violation's render text, `is_violation`, and `vacuous` flag; the resolved subjects; the exit category; and the `RuleConflict` / `RuleNotSupported` message on refusal: clean, violation, target match/miss, computed/uncertain, quote re-escaping, named-subject resolve/unresolvable, derivation lines, narrowed-by siblings, `supersedes` (drop / unknown / resolve), equal- and opposite-specificity conflicts, permits (supersede-clear, narrow-clear, broad-still-applies, different-target, unrelated, global), and all three vacuous situations. Plus the four rule-bearing corpus files through the `shapes_cli --rules` path, fingerprint byte-identity, and the render+rules integration — generated markers rendered byte-for-byte.

**No message diverged.** Errors-that-name-the-fix is a language-level commitment, and the JS checker meets it character-for-character.

`rules.js` did **not** need to split (A.7): A.2's synchronous hash keeps fingerprinting off the filesystem, so the module imports only `sha256.mjs` and `planes_text.mjs` — no `node:` import, browser-safe as written.

---

## Phase 6 — the all-seven surface, from both analysers

Running `shapes.js` over the three grammar stages and comparing to `shapes.py`:

- `grammar/lexer.planes` — **pure** on both (a lexer transforms text to tokens).
- `grammar/parser.planes` — **pure** on both (a parser transforms tokens to an AST).
- `grammar/interp.planes` — **all seven kinds** on both: `ask, clock, env, random, read, show, write`.

The full published surface is identical for all three. The prediction under test — made in this chain *before* `interp.planes` existed, that a Planes interpreter's static effect surface is all seven kinds, always: sound, maximally imprecise, correct rather than a failure — is now **discharged by a second independent analyser**. Two analysers agreeing on the all-seven surface is stronger evidence than one; a disagreement would have meant one was wrong. There was none.

---

## Analyser performance, JS against Python

Pure analysis time (grammar loaded, files read, warm; 34 standalone-parseable programs × 20 iterations):

| | per analysis | total |
|---|---|---|
| CPython `shapes.py` | 5.17 ms | 3,515 ms |
| V8 `shapes.mjs` | 1.17 ms | 793 ms |

**The JS analyser is ~4.4× faster.** (For reference, S4 measured the JS *interpreter* ~2× faster; the analyser's tighter numeric work widens the gap.) It is also not slower than Python — which §10 explicitly allowed it to be.

---

## Is the guarantee available without Python?

**Yes.** A browser with no Python anywhere can now:

- say **what a program touches** — its total effect surface, which boundaries and which destinations — computed by `js/shapes.mjs`, which never executes a line (the "Surface ⊚" button in `index.html`);
- say **where a value came from** — the `why` block names the origins each target derives from, straight off the derivation graph.

The page's sample makes the point sharp: a `fetch` function reaches the network, but nothing calls it at the top level, so *running* the program performs no network send (asserted) — while the *surface* still sees the reach, because a library that hides a network call behind a function is exactly what the analyser refuses to call pure. The guarantee, and not just the language, is off Python.

---

## Defects found in `shapes.py` / `render.py` / `rules.py` — reported, not fixed (A.6)

1. **`render.py`** does not round-trip a multi-argument call used as a record-field value (`grammar/interp.planes` ~line 717): the call's arg-list commas collide with the record's field separators, and `render.py` cannot reparse its own output. Its round-trip test set never exercises the construct. **Reported; not fixed** (`render.py` is read-only). The JS port reproduces it exactly.

No defect was found in `shapes.py` or `rules.py`: both ported to full agreement without a single divergence to explain.

---

## What this build disproved about this prompt

Never empty. Four things:

1. **The phase order contradicts the dependency.** The prompt lists `render.js` as Phase 3 and `rules.js` as Phase 4, but `render.py` imports `from rules import check` at module top — render *depends on* rules. `render.mjs` cannot exist without `rules.mjs`, so `rules.mjs` had to land in Phase 3 as render's dependency. The real constraint (§9 failure mode 8: the hash precedes rules) still holds — Phase 1's hash precedes it. Resolved toward §A's evident intent (§9 mode 9): the phase order governs *verification order* (rules agreement is Phase 4), not the order code can exist.

2. **A.4's per-node-kind coverage is necessary but not sufficient.** A.4 frames render's risk as a *safe fallback hiding an unrenderable node kind* — the two kinds that were silently unrenderable in `render.py`. But the latent `render.py` bug this build surfaced is not a missing kind: every node kind *is* handled. It is an unparenthesised multi-argument call *as a record-field value* — a valid combination of handled kinds that no per-kind round-trip would catch. Per-kind coverage would have passed this bug clean; only a real program using the construct (or a construct-combination fuzzer) finds it.

3. **A.7 named the wrong module as the likely split.** A.7 predicted `rules.js` as "the likely candidate" to split, if fingerprinting reached the filesystem. It didn't: A.2's synchronous hash kept fingerprinting pure, so `rules.js` needed no split. The module that *did* have to split was `shapes.js` — `analyseFile` follows imports across files and needs `node:fs`, so it moved to the Node-only `shapes_node.mjs` while the browser-loadable `analyse(src)` stayed in `shapes.mjs`. The split A.7 anticipated was averted; a different one was required.

4. **A.2's premise was inference; it is now established.** The prompt's PROVENANCE flagged that `rules.py` uses `hashlib` was inferred from an older commit and "which algorithm is not established." §0 established it: SHA-256, `hexdigest()[:6]`. The premise held.

---

## What remains

With the analyser, renderer, and rule checker ported, **the language and its guarantee are both off Python.** What is left is not the runtime and not the guarantee:

- **CLI conveniences.** `shapes_cli.py`'s `--index`, `--search`, and `--diff` (corpus indexing and upgrade-diffing) are not ported as a standalone `shapes_cli.mjs`. Their engine *is* ported — `asJson`, `check`, `render`, and `diff`/`SurfaceDiff` all live in `js/shapes.mjs` and the CLI — so a thin `.mjs` front door is the only missing piece, perhaps ~150 lines, and needs no new capability.
- **Python-side development tooling.** `grammar_gen.py`, `core_check.py`, `audit_locked_vs_built.py`, and `scripts/*.py` are about *maintaining* the language (regenerating the grammar, auditing the locked core), not *running* it or answering its questions. None is needed for the guarantee, and porting them would be a tooling exercise, not a language or guarantee one.

Neither blocks the claim this build set out to make. The browser tab has the language and now the guarantee: paste a program, see what it would touch and where its values came from, with no Python anywhere.
