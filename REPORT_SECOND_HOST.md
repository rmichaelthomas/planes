# REPORT — S4, The Second Host: Planes in JavaScript, and the Seam Crossed

**Branch:** `feat/second-host-js` · **Base:** `main` at PR #21's merge (`d938974`)
**Suite:** 849 → **902 passed** · **Counts:** 32 / 10 / 7 / 8 · **No Python source changed** (diff is `js/`, `test_js_*.py`, `index.html` only) · **Node:** v22.23.1

Route B was closed: Planes ran Planes. This build starts Route A — **a JavaScript
implementation of Planes, so that Planes runs without Python** — and, in doing so,
crosses the implementation-host seam for the first time in the repo's history.
`TestHost` could never test that claim: it subclasses `PythonHost` and shares
Python's runtime. This build does not.

**The deliverable is a Planes that runs in a browser tab** (`index.html`).

---

## What shipped, phase by phase, against §A

| Phase | Shipped | Against |
|---|---|---|
| 1 | `js/host.mjs` — the eight-method interface + the Node backend | A.4 |
| 2 | `js/planes_num.mjs` (exact rationals) + `js/planes_text.mjs`; the provenance decision | A.3, A.5 |
| 3 | `js/lexer.mjs` — 100% token agreement on every corpus file | A.3 |
| 4 | `js/parser.mjs` — AST agreement + the four amber sites | A.3 |
| 5 | `js/interp.mjs` (+ `modules.mjs`, `run_file.mjs`) — run agreement, effects, host.resolve | A.1, A.6 |
| 6 | `js/host_browser.mjs` (VFS) + `index.html` — the deliverable | A.4 |
| 7 | The metacircular conformance run — `*.planes` on the JS implementation | A.1 |
| 8 | Measurement and close | A.5, A.6 |

Layout mirrors the Python module names (A.2): `lexer.mjs`, `parser.mjs`,
`interp.mjs`, `host.mjs`, `modules.mjs`, `planes_num.mjs`, `planes_text.mjs`.
Plain ES modules, no TypeScript, **no build step, no bundler, no `package.json`**
— `.mjs` throughout so Node treats every file as ESM with zero configuration.

---

## A.0 — the three claims this prompt rested on, verified first

**Read `REPORT_INTERP_PLANES_3.md` and `CORE_SUBSET.md` at HEAD before Phase 1.**

1. **Port surface 28/32 keywords, 10/10 builtins, 7/7 effects, 8 host methods — CONFIRMED, with one refinement.** `core_check.py` on `main` reports 28/10/7 exactly. **"8 host methods" is soft:** `REPORT_INTERP_PLANES_3.md`'s own prose enumerates *nine* named items (`ask, read, write, show, clock, record, resolve, parse_json, to_json`) and collapses to 8 two different ways. `host.py`'s *mandatory* interface — the methods that `raise NotImplementedError` — is exactly eight: `ask / read / write / show / clock / resolve / parseJson / toJson`, with `record` an optional no-op. The JS interface is pinned at those eight + optional `record`, on both backends.
2. **Planes cannot parse JSON without a host — CONFIRMED, and free in JS.** `JSON.parse` / `JSON.stringify` supply the one irreducible host capability at no cost (A.4).
3. **Two corpus programs do not run under the self-hosted stack — CONFIRMED, and refined.** `foreign.planes` needs `host.resolve`; `probe/parser/cursor_scales.planes` exceeds interpreted recursion depth. **The refinement (see "What this build disproved"): `cursor_scales` is blocked only in the *self-hosted* stack (interp.planes-on-interp.py, depth 32) — not when run directly.** `js/interp.mjs` runs it directly, exactly as `interp.py` does; the interesting result is the *metacircular* depth (201 vs 32), not a direct-run rescue.

---

## The exact-rational representation, and what it cost

**The single largest correctness risk in the port (A.3).** JavaScript has no exact
rational type and `Number` is a float. `js/planes_num.mjs` represents a number as a
`Fraction` of two **`BigInt`s**, reduced, denominator positive — the subset of
`fractions.Fraction` Planes uses. `MAX_DENOMINATOR = 2n ** 4000n` unchanged;
arithmetic past the bound refuses (`Inexact`) rather than rounds.

**The load-bearing decision:** `Number.of(a foreign float)` routes through
`String(v)` — JavaScript's shortest round-trip decimal, the analogue of Python's
`Fraction(repr(v))` — **not** through the raw double. This keeps a JSON `0.1`
exactly one tenth and a JSON `1e23` exactly 10²³ (the nearest double to `1e23` is
not 10²³; `BigInt(1e23)` would have been wrong). Different textual formats of the
same shortest-round-trip decimal denote the same rational, so the parsed value
matches Python regardless of whether JS's `String` and Python's `repr` chose the
same notation.

**The cost:** `BigInt` arithmetic is slower than float, but exact. `test_js_num.py`
drives the same operations through both implementations and compares the rendered
text on every case a float gets wrong — `0.1 + 0.2 = 0.3`, `1 / 3 = ~0.333333333333`,
`round(2.675, 2) = 2.68` (not the float's 2.67), `round(2.5) = 3` (half away, not
banker's), a denominator past the bound refusing — plus a 228-fraction sweep. All
agree. **Exact rational arithmetic in JavaScript is not just possible but faithful;
§11's one halting condition never came close.**

Text is the second half: Planes text is a sequence of Unicode **code points**, JS
strings are UTF-16. `count of "😀"` is 1 (`[...s].length`), not 2; `first n of` a
string slices code points; `for each` walks them. `test_js_text.py` covers surrogate
pairs both ways.

---

## The Traced/Deriv decision, with numbers (A.5)

Provenance — `Traced(value, Deriv(...))` on every evaluated value — is what `why`
and `origins_of` are built on. A.5 required deciding it against measurement, not by
copying. **Measured in V8: a `Traced` + `Deriv` (with a 2-element `inputs` array) per
value costs ~32 ns** (167 ms for 5,000,000). That is a small fraction of any real
interpreter step — dispatch and environment lookup dwarf it — so a whole corpus
program pays microseconds of provenance overhead.

**Decision: port provenance, default on, no flag.** A.5's flag-it-off escape hatch is
required only *if* the cost is prohibitive; it is not. `why` and `origins_of` are
preserved. A Planes without `why` is not Planes.

---

## Agreement results, per stage

The oracle throughout is canonical-form agreement against the Python reference
(A.3), reusing the existing canonical forms — no fourth form invented. The JS side
emits, the Python test computes the same shape, the test compares strings.

| Stage | Result |
|---|---|
| **Host** (`test_js_host.py`, 15) | Each of the 8 methods pinned against `host.py`'s `PythonHost`. `toJson` byte-identical to `json.dumps(indent=2)`, ensure_ascii included. Both backends satisfy the same interface. |
| **Numbers** (`test_js_num.py`, 10) | Exact-rational agreement on every float-divergence case. |
| **Text** (`test_js_text.py`, 5) | Escapes + code-point semantics, surrogate pairs both ways. |
| **Lexer** (`test_js_lexer.py`, 6) | **58 / 58 `.planes` files, 100% token agreement** with `lexer.py`, plus three malformed-string messages byte-identical. |
| **Parser** (`test_js_parser.py`, 5) | **58 / 58 files, byte-identical canonical AST** with `parser.py` — including the ~1400-line interpreter (117 top-level nodes). **All four amber sites fire identically** on the synthetic fixtures with both readings named; the ported inline fire/near-miss scenarios agree on message. |
| **Interpreter** (`test_js_interp.py`, 8) | **Every one of the 58 corpus files runs to identical output and tag** — 33 standalone via `run`, 25 module graphs via `run-file`. The **seven effect kinds** agree on the whole effect log, the show output, and the files written, through a hermetic host on both sides. `why` and error tags/details match. |

The corpus fire rate for amber is zero, so corpus agreement cannot exercise the
disambiguation sites — the synthetic fixtures the Planes-parser build wrote do, and
the four fire identically (failure mode 8 avoided).

---

## Phase 7 — the metacircular conformance result, stated plainly

The strongest conformance test available: `grammar/lexer.planes`,
`grammar/parser.planes`, and `grammar/interp.planes` — a Planes implementation
written in Planes — run **on the JavaScript implementation**, and that stack
processes the corpus, checked against the **Python** implementation. A Planes
implementation written in Planes, running on a Planes implementation written in
JavaScript, checked against a Planes implementation written in Python.

**It finds nothing.**

- **Lexer stage: 58 / 58.** `lexer.planes`-on-JS tokenizes every corpus file
  identically to `lexer.py`.
- **Parser stage: 33 / 33 standalone files, zero real divergences.**
  `parser.planes`-on-JS parses to the same canonical AST as `parser.py`; the four
  amber fixtures refuse on both sides.
- **Interp stage: 32 / 33, one known gap.** `interp.planes`-on-JS runs every
  standalone program identically to `interp.py`. The one non-agreement is
  `foreign.planes`: `interp.planes` has **no dynamic `host.resolve`** (the second
  host's single non-effect method), so it refuses where `interp.py` resolves.
  **`js/interp.mjs` itself runs `foreign.planes`** — the gap is `interp.planes`'s,
  named, not the port's.

And the depth-blocked program runs: `cursor_scales.planes`, which hit
interpreted-recursion-32 on the CPython metacircular stack, runs through all three
layers on the deeper JS stack, matching `interp.py`'s direct run.

If it had found something it would be here. It found nothing; that is a strong
result and it should not be understated.

---

## Whether the eight-method seam held — the seam verdict

**This is the claim `ADDENDUM_SPRINT.md` §2 carried untested since the substrate
sprint: "a second host is eight methods, not a rewrite." This build is the first
crossing of that seam, and the answer is yes — it held.**

- **Exactly eight methods, no ninth.** Both backends (`NodeHost` over the real
  filesystem, `BrowserHost` over an in-memory VFS) implement `ask / read / write /
  show / clock / resolve / parseJson / toJson` and nothing more. `record` is an
  optional no-op on both, exactly as it is on `host.py`. No pressure from the port
  produced a ninth method (invariant 5 held without incident).
- **Neither backend needed anything outside the eight.** The only host-specific
  point is how `os.getcwd` resolves (`process.cwd()` under Node, a VFS root in the
  browser) — and that lives *inside* `resolve`, not as a new method.
- **The factoring proved right, with the A.0 nuance discharged.** The interface as
  written is eight methods; the report's prose "eight" collapsed the JSON pair into
  one "boundary." As *methods* they are two (`parseJson`, `toJson`), giving 5 effects
  + `resolve` + 2 JSON = 8. Both counts land at eight.
- **The seam is real, not decorative.** `TestHost` could never demonstrate this
  because it shares Python's runtime; the JS hosts share *nothing* with Python, and
  the whole corpus still runs. Crossing to a genuinely separate runtime cost exactly
  the eight methods the sprint predicted.

**One structural finding the seam claim did not anticipate** (see below): "two
implementations, one interface" also required *splitting the shared host module* so
it imports nothing node-specific — otherwise the browser cannot load the
interpreter at all.

---

## Recursion depth and performance, JS against CPython

Measured this phase, never carried.

| Measure | interp.py (CPython) | js/interp.mjs (V8) | Ratio |
|---|---|---|---|
| **Direct** Planes recursion ceiling | 328 | **1268** | 3.9× |
| **Metacircular** ceiling (a recursive program through `interp.planes`) | **32** | **201** | 6.3× |
| Corpus run, in-process (33 standalone files ×20) | 0.51 ms/run | **0.25 ms/run** | **2× faster** |

The metacircular 32 confirms `REPORT_INTERP_PLANES_3.md`'s figure exactly. On the
deeper V8 stack it is 201 — which is precisely why `cursor_scales` (needing depth
> 32) runs through the full metacircular stack on JS and did not on CPython. Per
A.6, the depth is the second host's to raise, and JavaScript's stack raises it ~6×
at the metacircular layer and ~4× directly, with no engineering-around — no
trampoline, no restructure, just a bigger stack. And the corpus interprets ~2×
faster on V8 than on CPython (in-process; Node's ~50 ms startup dominates one-shot
CLI use but not the interpretation itself).

## Runnable corpus count, JS against Python

**All 58 corpus files run identically** on `js/interp.mjs` and `interp.py` — 33
standalone (`run`) and 25 module graphs (`run-file`), output and terminal tag
matching on every one. The metacircular stack runs 32/33 standalone (the one
holdout is `foreign.planes`, the `interp.planes` `host.resolve` gap, which
`js/interp.mjs` closes).

---

## What porting `shapes.py`, `render.py`, and `rules.py` would cost (A.1)

Out of scope for this build (they are the analyser and its dependents — a second
port). The estimate, from their structure:

| Module | Lines | Port cost | New capability needed |
|---|---|---|---|
| `render.py` | 463 | Low–moderate. A straightforward AST→source pretty-printer; reuses the ported AST, `escapeStringLiteral`, and the same render/reparse agreement oracle. Depends on `rules.py` (violation markers). | none |
| `rules.py` | 595 | Moderate. The rule checker; agreement-testable on violations/conflicts. | **a hash** — `fingerprint` uses `hashlib.sha256`. `node:crypto` gives it free under Node; a browser needs Web Crypto (async, awkward) or a ~50-line pure SHA-256. The one genuinely new boundary capability, analogous to JSON for the interpreter. |
| `shapes.py` | 1246 | Moderate–high, the largest. The static effect analyser — a visitor computing the `Surface`. Reuses the ported AST, `parse`, `modules` resolution, and `escapeStringLiteral`; testable by analysing each corpus file and comparing the `Surface`. | none |

Total ~2300 lines, all agreement-testable by the technique that carried this build.
The only new host-ish capability is a **hash** (rules.py's fingerprint) — free in
Node, a small addition in the browser. Everything else reuses what is already
ported. Port order: `rules → render` (render depends on rules), `shapes`
independent.

---

## What this build disproved about this prompt

**Never empty** (§PROVENANCE). Three things:

1. **A.0's third claim was imprecise about `cursor_scales`.** The prompt, inheriting
   the summary, framed it as "one [corpus program] exceeding interpreted recursion
   depth" — as if the JS *implementation* would be the thing that must be made to run
   it. But `cursor_scales` is not blocked when an interpreter runs it *directly*:
   `interp.py` runs it (3 output lines), and so does `js/interp.mjs`, the moment it
   exists. The block is specifically the **self-hosted** `interp.planes` layer (depth
   32). So "the depth-blocked program must run under the JS implementation" was
   already true at Phase 5; the result worth reporting is the **metacircular** depth
   (201 vs 32), where the JS stack actually earns the win.

2. **"Eight host methods" was soft, and needed pinning.** The figure this prompt
   inherited was second-hand at two removes; the source report's own prose lists nine
   items and collapses to eight two different ways. The mandatory interface is exactly
   eight (`record` optional). Not a defect that changed the build — but a count stated
   as settled that was not, discharged by measuring the interface rather than trusting
   the prose.

3. **The seam claim missed a structural consequence.** "Two implementations, one
   interface" is true, but incomplete: a single host module that imports `node:fs`
   (for the Node backend) makes the *whole interpreter* unloadable in a browser,
   because the browser cannot resolve `node:fs` even if it is never called. The port
   forced a split — `host.mjs` browser-safe, `host_node.mjs` Node-only,
   `host_browser.mjs` for the VFS — and the same discipline on `modules.mjs` /
   `run_file.mjs` (Node-only, dynamically imported). The seam is eight methods *and* a
   module split the "not a rewrite" framing did not name.

---

## Route A, assessed — is Planes off Python?

**The language is off Python.** `lexer.mjs → parser.mjs → interp.mjs`, with a Node
backend and a browser backend, tokenizes, parses, and *runs* every one of the 58
corpus programs — expressions, statements, control flow, lexical scoping, recursion,
failure, all seven effect kinds, foreign resolution, and provenance — checked at
every stage by agreement with the Python reference, and by the metacircular run of
the Planes-in-Planes stack on top of it. A Planes program runs in a browser tab with
no Python, no server, and no build step.

**What remains:**

1. **The tooling port — `shapes.py`, `render.py`, `rules.py`** (~2300 lines, scoped
   above). The analyser, the renderer, and the rule checker. One new capability (a
   hash); everything else reuses what is ported. This is the analyser's turn at the
   same agreement technique, not new language.
2. **Nothing in the language.** `host.resolve` — the one thing `interp.planes` on
   CPython could not stand in for — is implemented by the JS host; `js/interp.mjs`
   runs `foreign.planes`. JSON, the irreducible interpreter-side host capability, is
   free in JS. Recursion depth, the second host's to raise, is raised ~6× at the
   metacircular layer with no engineering-around.

Route A is open and the language walks it. The second host was eight methods and a
module split — **not a rewrite** — and the seam, crossed for the first time, held.
