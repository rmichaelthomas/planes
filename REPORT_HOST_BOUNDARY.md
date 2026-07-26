# The self-hosted host boundary completed — JSON in Planes, and the seam tested

**Build:** C1, `feat/selfhosted-host-boundary`
**Base:** `17b3d89` (S8, "The second guarantee, self-hosted")
**Scope:** the five gaps `REPORT_WHY_SELF_HOSTED.md` §8 named under *Runtime*

---

## The headline: does the self-hosted path still need the host's JSON capability?

**No.**

`grammar/json.planes` reads and writes JSON in the language — 539 lines, 48
functions, **zero declared effects**. The capability that was called *the one
irreducible host capability* turns out to be a pure program, and one that needs
nothing the language did not already have. Counts are unchanged: **32 keywords,
10 builtins, 7 effect kinds, 8 host methods.**

The claim it disproves was made twice in this chain, and the reason it survived
is visible in its own wording: *Planes has no JSON parser and no runtime type
probe, so interp.planes cannot re-wrap a host-parsed value into its tagged
model.* That was written before `grammar/parser.planes` existed and never
revisited after it did — and parsing Planes is a considerably harder job than
parsing JSON. Once the parser existed the claim was owed a re-test, and it does
not survive one.

What the self-hosted path now does without reaching past the language:

| | before C1 | after C1 |
|---|---|---|
| `ask`, inert | the response table held a pre-parsed tagged value; nothing was parsed | the table holds the **raw body**, and `interp.planes` parses it itself, falling back to the text on a refusal exactly as the reference falls back when `json.loads` raises |
| `write`, inert | the destination was logged and nothing was serialised | the bytes are computed by `json.planes` and stored, **byte-identical to `to_json`** |
| `write` of a record | fell back to canonical *Planes* text | serialised as JSON |

The host's `parse_json` / `to_json` **stay** — the reference implementation calls
them, and this build changed no `.py` or `.mjs` interpreter source. The question
was never whether the host has the capability; it was whether the self-hosted
path is still bound by it. It is not.

**What is still host-bound is not JSON.** Three real-mode behaviours remain, and
they are one gap wearing three hats: in real mode `interp.planes` performs an
effect by executing the corresponding *Planes* construct, and the outer host
parses or encodes on the way past. It is handed host-**parsed** values where it
now only needs host **bytes**. See §A.4 and §"What the stack still cannot do".

---

## Was "no runtime type probe" a real second gap?

**It was never separate — and shape matching is not what answers it.**

A type probe is needed only to re-wrap a value *somebody else* parsed: given an
opaque host value, decide whether it is a number, a list, a record. A parser that
reads the text itself learns each value's type **from the syntax** — a `{` opens
a record, a `"` opens a text, a digit opens a number. The probe is not worked
around in `json.planes`; it is not needed there.

So the two halves of the stated gap were one fact stated twice: the type probe
was required *because* the host did the parsing.

The probe's absence is real, and it is what §A.4 turns on — but for a different
job. Measured, not asserted (`test_interp_effects_in_planes.py`, C1 section):

* `count of` a record gives the **field count**, so a record is not wholly
  opaque;
* nothing yields the **field names** — `for each` over a record is
  `not-a-collection`, `join of` a record is refused, and reading a field needs a
  name known when the source was written;
* a probe by trial (catching the raise with `or fail`) separates a *number* from
  the rest and leaves **list, text, and record indistinguishable**.

That is why an arbitrary foreign's result cannot be tagged, and equally why a
JSON object built from text can be: in the second case the keys arrive as data.

---

## Exact numbers: what it took to match the reference

**It took nothing extra, and the residual runs in Planes's favour.**

The reference converts in two steps: `json.loads` gives a Python `int` (exact) or
`float` (binary), and `from_foreign` turns that into an exact number — for a
float, via `Fraction(repr(v))`, *the shortest decimal that round-trips it*, which
is why a JSON `0.1` becomes one tenth rather than `0.1000000000000000055`.

`json.planes` reads the decimal text directly. Because the reference's conversion
goes through the shortest round-tripping decimal, the two agree on **every JSON
number whose decimal form round-trips a float64** — up to 17 significant digits,
which is every number JSON is ordinarily written with and every number in the
corpus. Asserted across `0.1`, `0.2`, `0.30000000000000004`, `1e3`, `1E3`,
`1e+3`, `1e-3`, `2.5e2`, `-2.5e-2`, `1e17`, `1e-17`, `-0`, `9007199254740993`,
and `12345678901234567890`.

Past that boundary they diverge, one-directionally, and Planes is the exact side:

| input | `json.planes` | reference |
|---|---|---|
| `1.0000000000000000001` | `1.0000000000000000001` | `1` |
| `3.141592653589793238462643383279` | `3.141592653589793238462643383279` | `3.141592653589793` |

**Reproducing the loss was considered and rejected.** Matching the reference past
17 digits would mean emulating float64 shortest-repr rounding in Planes — a large
program whose entire purpose is to throw away digits — and it would contradict
the language's own reader, which takes a source `0.1` as one tenth "not the
nearest float" (`planes_num.py`, `Number.parse`). The Planes JSON reader is now
consistent with the Planes source reader, which is the more defensible place to
be. It is asserted as a named divergence so it cannot change silently.

Two details that removed the risk rather than managing it:

* **No float is ever written.** `to_json`'s `unwrap` sends a whole number out as
  an integer and anything else out as its exact *text*, so the writer needs no
  float formatting at all — `1/3` lands in a file as `"~0.333333333333"` on both
  sides.
* **Exponents cost no depth.** `10^(the number those digits spell)` is folded
  over the exponent's own text — reading one more digit takes `10^k` to
  `(10^k)^10 * 10^d` — so there is no range loop (Planes iterates collections,
  not ranges) and no recursion.

---

## Was inert write-then-read a fill?

**Yes, and by the narrowest margin of any fill this chain has measured.**

The prediction was that the io record already threads state of this kind. It
does, three ways: `log` accumulates, `output` accumulates, and `randoms` is
*consumed* head-first through the same `with`. Adding the files table to that set
required:

| | |
|---|---|
| functions changed | 1 (`do-write`) |
| lines of body added | 3 |
| signature changes | 0 |
| new threading | none — the same `with-io` the site already called |
| other sites touched | 0 |
| depth cost | 0 (all six figures identical, §"Depth") |

One design point was not free, and it is the kind a fill can hide: a rewrite of
the same path **prepends**, because `lookup-file` takes the first match.
Appending would have had a later `read` serve the *older* body — a silently wrong
value, from a three-line change.

Hermetic either way: the table is per-run, starts from supplied data, and an
inert write to an absolute path in a fresh temp directory leaves that directory
empty (asserted, not assumed).

---

## A.4 — `foreign-needs-host`: **a documented limit of the self-hosted stack**

A.4's **second outcome**. Nothing was closed, nothing was added, and the argument
is measured rather than asserted so a future session does not rediscover it.

Real mode resolving an *arbitrary* foreign needs two things. The second holds
even if the first were granted.

**1. Dynamic resolution is ungrammatical, not unimplemented.**

```
target = "builtins.sorted"
foreign f of xs from target doing nothing
```

is a **syntax error** — `line 2: expected string, found 'target'`. The grammar
requires a literal. That is precisely what keeps the static analyser able to name
every host function a program can reach, which is the property `origins_of` and
the effect surface both rest on. The language did not omit dynamic lookup; it
refuses it in the parser.

**2. The result cannot be tagged.** Even given the target, an arbitrary foreign's
return value cannot enter `interp.planes`'s tagged model, for the reasons
measured in §"no runtime type probe" above: a record's field names are
unreachable, and `count of` is the only type discriminator available.

**3. A static target table does not rescue it.** `js/host.mjs`'s `sharedTargets`
is exactly that shape, and `interp.planes` already carries three host-specific
target literals (`time.time`, `random.random`, `os.getcwd`). A fourth, fifth and
sixth would get a *usable value back* — measured: `foreign f-sorted of xs from
"builtins.sorted"` returns a list of three items. It still cannot be tagged,
because a `doing nothing` declaration carries **no return type**. The ambient
three work only because their *effect kind* supplies the type: `clock` and
`random` are numbers, `env` is text. Closing `foreign.planes` this way would mean
the interpreter hardcoding the return types of four specific Python functions —
host knowledge inside the language's own interpreter, which is the thing the
eight-method seam exists to prevent.

So `interp.planes` refusing with `foreign-needs-host` is **correct behaviour**,
not a gap left open: it declines to guess a value it cannot construct.

### The ninth-method candidate, reported and unbuilt

It is **not** "dynamic resolve". The three remaining real-mode gaps are one gap:

| gap | what interp.planes is handed | what it needs |
|---|---|---|
| arbitrary foreign | nothing (it cannot call it) | the result, as bytes |
| `ask` | the body already parsed by the outer host | the body, as bytes |
| `write` of a record | a `write` that re-encodes whatever it is given | to hand over bytes |

Before C1, bytes would not have been enough — there was no parser. Now they are.
So the candidate is a **serialised boundary**, one method wide:

```
call_foreign_json(target, args_json) -> json text
```

The host resolves the target (it already has `resolve`) and returns the result as
JSON text, which `json.planes` tags with no probe. It adds **no language
surface**: the *program's* declared target is still a literal, so the analyser's
static view of what a program reads is unchanged, and the ruling that keeps
`origins_of` sound is not touched. The same shape closes real-mode `ask` (a raw
body) and real-mode raw `write`.

**Is it necessary or merely convenient?** Necessary for the self-hosted stack to
reach parity with the reference in *real* mode; convenient for everything else,
because inert mode already reaches parity and is where every agreement result in
this repo is measured. That is a seam decision, not a build one, so it is written
down and not built.

One observation, not a proposal: the seam could stay at **eight by substitution**
rather than growing to nine. `parse_json` and `to_json` are needed by the
*reference implementation*, not by the language — the self-hosted path no longer
calls either. A host interface of `ask / read / write / show / clock / resolve` +
a raw-bytes pair is also eight. This build does not propose removing anything;
the reference uses those two methods and they stay.

---

## Corpus runnable count

Measured with one instrument across both trees —
`scripts/run_corpus_selfhosted.py`, new because no existing harness measured
this. `run_corpus_through_planes.py` drives *real* mode and marks every
`use`-bearing program N/A, so it never saw the sixteen corpus programs that touch
the world: the half the host boundary is about.

| | count | short |
|---|---|---|
| baseline `17b3d89`, default configuration | **48 / 50** | `cache-store` (`no-such-file`), `fastest-responses` (`not-a-collection`) |
| baseline `17b3d89`, foreign stub supplied | **49 / 50** | `cache-store` |
| **after C1** | **50 / 50** | — |

**It is 50 of 50.** Nothing is short.

The 48→49 row is a finding in its own right: half of A.3's ruling was already
built. The inert configuration **already had** a foreign-results table
(`io.foreigns`, scanned by `lookup-by-name`), and a supplied result already
worked. Only the missing-entry behaviour was wrong, and it was wrong in the way
this language exists to prevent — returning `nothing` and letting the program
carry on, so `fastest-responses` failed `not-a-collection` three expressions
downstream of the real problem. It now fails at the under-specified site, naming
which foreign lacked a result, its target, and the table entry that supplies one.

The other harnesses moved as expected and nothing regressed:

* corpus `why`-agreement (`test_why_in_planes.py`): **43/50 → 44/50**, 130 → 132
  derivations compared. The remaining five skips are programs `interp.py` itself
  does not complete under a `TestHost` (four unstubbed `ask`s, one deliberate
  `not-a-yes-no`), which the self-hosted stack matches failure-for-failure —
  `run_corpus_selfhosted.py` counts them RUNNABLE for exactly that reason.
* `run_corpus_through_planes.py` (real mode): **60 / 62** unchanged, with the
  same two BLOCKED — `foreign.planes` (§A.4) and
  `probe/parser/cursor_scales.planes` (interpreted-recursion depth, and it runs
  on the deeper JS metacircular stack).

---

## Depth

A recursive-descent JSON parser three levels of interpretation down was the named
risk. It was avoided by construction rather than measured after the fact: the
**reader is a fold with an explicit container stack**, so nesting costs a stack
entry rather than an interpreter frame. The **writer** recurses once per level,
as `interp.planes`'s own `canonical-of-value` already does.

`scripts/measure_interp_planes.py`, before and after — **all six identical:**

| figure | baseline | after C1 |
|---|---|---|
| interpreted eval nesting | 139 | **139** |
| interpreted recursion depth | 32 (35 frames/call) | **32 (35)** |
| interpreted statement nesting | 33 | **33** |
| full pipeline nesting | 23 | **23** |
| max env at recursion depth | 4 (depth 120) | **4 (120)** |
| max env at call chain | 63 (chain 60) | **63 (60)** |

New figures for the JSON program itself:

| | |
|---|---|
| reader nesting, called from the host | **≥ 400** (no ceiling found; 400 asserted) |
| reader nesting, through an interpreted `ask` | **≥ 300** (no ceiling found) |
| writer nesting, called from the host | **75** |
| writer nesting, through an interpreted `write` | **22** — *and this is not the writer's ceiling* |

The last row is the interesting one. A program whose literal is nested 22 deep
fails at 23 **with no `write` in it at all** (measured): the binding constraint is
the interpreted program's own expression nesting, which was 22 before C1 and is
22 after. The writer adds **zero**. The 75 is its own ceiling with a full stack
available, reported as a number rather than worked around.

---

## What the self-hosted stack still cannot do

Each classified, as §6 asks.

### Documented limits

1. **Real mode cannot resolve an arbitrary foreign** (`foreign-needs-host`).
   §A.4 in full. Refusing is correct behaviour; closing it needs a ninth host
   method, proposed above and not built. *Not a defect.*
2. **Real-mode `ask` returns the response's text form.** The outer host parses
   the body before `interp.planes` sees it, so the raw text is gone and the
   parsed value carries no tag this model can read. Same gap as 1, same remedy.
   Inert mode — where every agreement result is measured — returns a parsed
   record. *Not a defect.*
3. **Real-mode `write` of a record is one JSON layer too deep.** The payload is
   now the reference's **exact bytes** (asserted: `json.loads(ours) == theirs`),
   wrapped once more because the outer host's `write` JSON-encodes whatever it is
   handed and no effect in the language writes text raw. Same gap, same remedy.
   Inert mode is byte-identical. *Not a defect, and strictly closer than the
   canonical-Planes-text it replaced.*
4. **JSON's `\r`, `\b`, `\f` and `\uXXXX` escapes are refused.** A Planes string
   literal carries four escapes (`\"` `\\` `\n` `\t`) and there is no
   code-point conversion — `chr of n` was **declined** when the string escapes
   were settled, on the grounds that a magic conversion builtin reintroduces the
   opacity a closed vocabulary exists to avoid (the same ruling
   `parser.planes` cites for parsing a number by hand). The refusal names why, on
   both implementations, byte-identically. *A documented limit of the language,
   surfacing in a program — not a defect in the program.*
5. **Non-ASCII is written as itself, not `\uXXXX`** — the same absence, the other
   direction. The output is valid JSON that the reference reads back to the same
   value; it is not byte-identical to `ensure_ascii=True`. Asserted both ways:
   Planes → reference round-trips an astral-plane character; reference → Planes
   refuses the surrogate-pair escape. *Documented limit.*
6. **Past 17 significant digits the two readers diverge**, with Planes exact.
   §"Exact numbers". *Documented limit, and the favourable direction.*
7. **`probe/parser/cursor_scales.planes` exceeds interpreted recursion depth (32)
   on the CPython metacircular stack.** Pre-existing, unchanged, and it runs on
   the deeper JS stack. *Documented limit.*

### Defects — found, reported, not fixed

8. **Thirteen `interp.py` ↔ `js/interp.mjs` divergences in the text-coercing
   builtins.** Found while measuring whether a type probe by trial could rescue
   §A.4, by sweeping `count / join / rest / normalize / lower / upper / whole /
   text` across `5`, `"ab"`, `[1, 2]`, `{ a: 1 }`, `true`, `nothing` — 48 cases,
   13 disagreeing. Two families:

   | | `interp.py` | `js/interp.mjs` |
   |---|---|---|
   | `count of 5` / `true` / `nothing` | raw Python **`TypeError: object of type 'Number' has no len()`** — a host exception escaping with no tag and no fix | `PlanesError` **`not-a-collection`** |
   | `lower` / `upper` / `normalize` of `[1, 2]` | `'[1, 2]'` | `'1,2'` |
   | … of `{ a: 1 }` | `"{'a': 1}"` | `'[object Map]'` |
   | … of `nothing` | `'None'` / `'NONE'` / `'none'` | `'null'` / `'NULL'` |
   | `normalize of true` | `'True'` | `'true'` |

   The first family is a clear one-sided defect: the JavaScript behaviour is
   right, a Python traceback escapes where a Planes error belongs, and the fix is
   one line. The second family is ten cases where **both** implementations are
   confidently wrong in the same way — each leaks its own host language's
   stringification into the language — so neither can be called the
   specification, and the right answer (refuse? coerce? whose form?) is a
   language ruling, not a mechanical fix.

   **Not fixed here.** Fixing the first family alone while leaving the second is
   arbitrary, and the second needs a ruling this build has no mandate to make.
   Reproduction is one line per case: `show text of (<builtin> of <value>)`, run
   through `interp.py` and `node js/cli.mjs run`. This is the largest open
   defect the self-hosted stack sits on top of, and it is worth a build of its
   own.

### Unfinished work

9. **Module resolution in the self-hosted stack.** `use` records the module name
   for the file/http checks and does not resolve a `.planes` file, so the 42
   multi-file programs outside `corpus/` remain N/A in the real-mode harness.
   Out of scope here and unchanged.
10. **The 12-entry error-catalogue shortfall** and the nine messages assembled
    away from their raise site. Unchanged; reported every CI run.

---

## Every file this build changed

Ten, plus this report.

| file | new? | what changed |
|---|---|---|
| `grammar/json.planes` | **new** | the JSON reader and writer, 539 lines, 48 functions, zero effects. No `use` of its own |
| `grammar/interp.planes` | | `use json`; `do-ask` parses the raw body; `lookup-response` reads `body`; `do-write` stores the serialised bytes in the files table; `unwrap-value`'s record arm serialises; `foreign-supplied-or-nothing` → `foreign-supplied-or-fail`, which fails naming the stub |
| `js/cli.mjs` | | a `meta json` stage beside the existing `lex` / `parse` / `run`, so the same Planes program is checked on the JavaScript host |
| `scripts/ci.sh` | | holds `grammar/json.planes` to the same declared core as `interp.planes` |
| `scripts/run_corpus_selfhosted.py` | **new** | the corpus-through-the-self-hosted-stack measurement, and the per-program inert configuration |
| `test_json_in_planes.py` | **new** | 17 tests: reading, refusing, writing, Unicode, depth — every case against the reference rather than a hand-written expectation |
| `test_js_json.py` | **new** | 3 tests: the same Planes program on both hosts, and the round trip against the reference, over the repo's own JSON files plus written fixtures |
| `test_interp_effects_in_planes.py` | | 17 tests added (ask parsing, write-then-read, hermeticity, the missing-stub failure, the 50/50 corpus count, the §A.4 investigation); the `__main__` runner it never had; `pytest.mark.parametrize` → a plain loop, which merged four cases into one function — 27 functions before, 44 after |
| `test_why_in_planes.py` | | response stubs carry `body` |
| `test_js_render.py` | | `grammar/json.planes` added to the cross-implementation round-trip set |

**No `.py` or `.mjs` interpreter, analyser, lexer, parser, renderer, or host
source changed.** `grammar/lexer.planes` and `grammar/parser.planes` are
untouched. The whole of this build's behaviour change lands in Planes.

---

## Verification

| check | result |
|---|---|
| `scripts/ci.sh` | **green, exit 0** — 953 oks across 52 suites (baseline 889 / 49), `ruff` clean, `mypy` 90 files (baseline 87) |
| counts | **32 / 10 / 7 / 8**, unchanged |
| error catalogue | **97 entries — 70 name a fix, 6 delegate, 9 unreadable, 12 do not.** Identical to the baseline: the new `no-foreign-result` message is a Planes `fail`, and the catalogue is generated by walking `.py` sources. Its fix clause is asserted by test instead |
| render round-trip of the new stage file | `grammar/json.planes` round-trips on both implementations and renders byte-identically between them — added to the same check `interp.planes` and `parser.planes` sit in, because it is the largest Planes program written since the composition defect was closed |
| `grammar/lexer.planes`, `grammar/parser.planes` | unchanged (`git diff` empty) |
| `core_check.py` | `interp.planes` conforms; `grammar/json.planes` conforms (20 keywords, 4 builtins, 0 effect kinds) |
| `grammar_gen.py --check` | exits 0 — no generated artifact hand-edited |
| JSON round trip vs the reference | **46 documents read and compared** against `parse_json` + `from_foreign`, plus 3 asserted individually (the two past-17-digit cases and a repeated field); **27 refusals** asserted (21 malformed, 6 unspellable-escape); **14 values written byte-identical** to `to_json`; both round-trip directions over all 14. Nesting, escapes, exact numbers, empty containers, and astral-plane Unicode each covered, with the two Unicode outcomes asserted rather than assumed |
| the same program on both hosts | 14 fixtures, byte-identical text and byte-identical refusal messages |
| inert write-then-read | working, hermetic, `cache-store` agreeing byte for byte |
| a foreign with no stub | fails `no-foreign-result`, message asserted to name the foreign, its target, and the entry that supplies one; `fastest-responses` agreeing |
| A.4 | reported as outcome 2, with the argument pinned by four tests |
| corpus, self-hosted | **50 / 50** (baseline 48) |
| depth | all six figures identical to baseline |
| metacircular | re-run, still finds nothing; `interp.planes` on the JS host runs the corpus like `interp.py`, with `foreign.planes` the one named non-agreement, as before |

### The one gate item that does not pass

§10 asks for "JSON round-tripping against the reference across … astral-plane
Unicode". **Byte-identical round-tripping of non-ASCII does not pass, and cannot
be made to pass without a language addition.** `json.dumps(ensure_ascii=True)`
writes `😀` as `😀`; Planes has no code-point escape and cannot read
that back or write it. What does pass, and is asserted: Planes writes the
character itself, the reference reads that output back to the same value, and the
reverse direction refuses with a message naming exactly why. Stating this plainly
is more useful than a green tick over a hedge — and the boundary is a
previously-settled ruling (`chr of n`, declined), not a discovery.

---

## What this build disproved about this prompt

Never empty, and this time there are five.

**1. §7 abandoning enumeration worked.** Four consecutive builds shipped a
constraint that forbade something a ruling needed, most recently by listing the
files that could change and closing the list. §7 constrains behaviour and counts
instead, and **nothing in it obstructed anything.** This build touched a file no
enumeration would have predicted (`js/cli.mjs`), created three (a grammar stage,
a script, two test suites), and needed no exception. The pattern that produced
four contradictions is fixed by not doing it.

**2. A.3's first half was already built.** "The inert configuration gains a
foreign-results table" — it had one. `io.foreigns` existed, was scanned by
`lookup-by-name`, and a supplied result already worked; a test in the repo
already exercised it. Only the missing-entry behaviour was wrong. Measured:
48/50 with the default configuration, **49/50 with the stub supplied**, on the
baseline tree. Half a ruling's worth of work was already done, and §0 step 7's
"confirm each fails for the reason the report states" caught it — the *reason*
was right and the *remedy* was half-built.

**3. §9's stop condition 1 contradicts A.1.** §9 makes it a stop condition that
"a JSON parser in Planes requires a language addition"; A.1 says that if it turns
out to need one, "that is the finding — report it and add nothing." A complete
JSON parser *does* need one: four of JSON's eight string escapes have no Planes
spelling. Under §9 this build stops; under A.1 it reports and continues.
Resolved toward §A's evident intent (test the claim, add no surface) per §8's
failure mode 8 — and the result is the stronger one, because the boundary is now
an exact, tested line rather than an unattempted question.

**4. "Two corpus programs are unreachable" was true of a measurement nothing in
the repo made.** §8's figure is right, but no harness computed it:
`run_corpus_through_planes.py` marks every `use`-bearing program N/A and
`test_why_in_planes.py` reports skips for four different reasons at once. The
48-of-50 the prompt quotes had to be reconstructed by reading a skip list. The
instrument came after the number, which is the wrong order, and
`scripts/run_corpus_selfhosted.py` now exists so the next build reads a number
instead of reconstructing one.

**5. A whole test suite was dead in the gate, and the prompt's §10 could not have
caught it.** `test_interp_effects_in_planes.py` — the *primary* suite for
everything in §A.1 through §A.3 — had no `__main__` runner, and `scripts/ci.sh`
runs each suite as `python3 test_*.py`. The gate imported the module and ran none
of its 30 tests. Every §10 item that says "asserted by test" was, for this file,
asserted by a test nobody ran. It has the runner now, and the suite reports 44
passing — 27 of them tests that existed at the baseline and had never been run by
the gate.
