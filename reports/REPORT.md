# Planes Substrate Prototype — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. No design documents produced.
**Mandate:** Build the substrate. Park governance. Gate on `x = 5; y = 3; z = x + y; why z`.
**Result:** All three tasks complete. 45/45 tests passing. Runs against the live network.

---

## 1. What Was Built

A working programming language: 1,063 lines of implementation, 371 lines of tests.

| Component | File | Lines |
|---|---|---|
| Tokenizer + AST | `lexer.py` | 145 |
| Parser | `parser.py` | 356 |
| Evaluator + provenance | `interp.py` | 484 |
| CLI | `planes.py` | 78 |
| Tests | `test_planes.py` | 371 |

### Task 1 — The minimal core ✅

```
$ python3 planes.py -e 'x = 5; y = 3; z = x + y; why z'
8 from x (5) + y (3)
```

Parser, evaluator, and provenance tracker. The gate passes exactly as specified.

### Task 2 — Functions ✅

```
to add of a, b:
  give a + b

result = add of 2, 3
why result    →  5 from add(2, 3) = a (2) + b (3)
```

The call chain survives. Nested calls and recursion work (`fact of 5` → 120).

### Task 3 — Collections and the scraper ✅

Lists, records with dot access, comprehensions with `where`, conditionals,
`ask`/`write` effects, `or fail as` error renaming. Every line of the Python
HN scraper maps to Planes and the program runs.

---

## 2. Verified Behaviour

**The HN scraper runs.** Against a deterministic stub — 5 network asks, 3
prints, 1 file write, correct filtering:

```
found 2
Rust 2.0 released  (450)
Rewriting grep in Rust  (210)
```

**A real program runs against the live internet.** The sandbox blocks
`hacker-news.firebaseio.com`, so `pypi.planes` was written to the same shape
against an allowed host. Four live HTTPS calls, two comprehensions, a filter,
record access, string building, and a file write — all working:

```
found 3
Flask  (A simple framework for building complex web applications.)
Django  (A high-level Python web framework that encourages rapid development...)
numpy  (Fundamental package for array computing in Python)
```

**`why` crosses the network boundary.** This is the killer feature working
end-to-end. A value pulled from an API, field-accessed, then arithmetic'd,
traces back to the exact URL it entered from:

```
label = REQUESTS
  upper of = REQUESTS
    name = requests
      .name = requests
        info = {record}
          .info = {record}
            pkg = {record}
              ask https://pypi.org/pypi/requests/json = {record}
                  <- entered at network:https://pypi.org/pypi/requests/json
```

**Provenance is not a label system.** `apply_op` — the function that actually
adds two numbers — contains no reference to derivation. Results are wrapped
by the tracker after the operation returns. Nothing propagates into any
signature. This is the architectural difference from Jif and from taint
modes, and it is now demonstrated rather than asserted.

---

## 3. Findings From Implementation

Four things surfaced by writing code that would not have surfaced by design.

### 3.1 Naming is a derivation node — and it gives you two depths for free

`z = x + y` produces a `name` node wrapping the `op` node. That structure is
what makes `why d` on `d = c + 1` report `7 from c (6) + 1` rather than
flattening to `from a (2) * b (3) + 1`.

One hop by default, full tree on demand. This was not planned; it fell out of
the implementation and it is the right default. A user asking `why` usually
wants the immediate story, not the whole history.

### 3.2 The derivation graph is a DAG, not a tree

The first tree printer repeated the entire source list under every item of a
comprehension. Four items meant four copies. On a real dataset this is
unusable.

Fixed by node identity — shared subgraphs print once, then `(same as above)`.
**The consequence is architectural:** derivation output is the size of the
derivation, not the size of the data. A comprehension over ten thousand rows
has a derivation graph roughly the size of the source expression. This is the
first real evidence about whether `why` scales, and the answer is that it
scales with program structure rather than data volume.

### 3.3 `of` binds tighter than arithmetic

A test failure revealed an ambiguity nobody had noticed: `double of n + 1`
parses as `(double of n) + 1`, not `double of (n + 1)`.

The test encoded the wrong expectation; the implementation was right. Tight
binding is now locked and tested, because it is what makes `detail of id`
unambiguous inside a larger expression — exactly the construct the scraper
needs. **This is a syntax decision made by implementation, not by taste.**

### 3.4 `why` is a statement, not an expression

It prints; it does not return a value into the program. A program cannot
currently branch on its own provenance. This may be correct — it keeps
`why` out of the semantics of ordinary code — but it is an unmade decision,
flagged rather than resolved.

---

## 4. The Anti-Drift Check

Two tests exist purely to detect the failure mode that cost four prior
sessions.

`test_no_governance_vocabulary_in_source` greps the implementation for
`policy`, `precedence`, `govern`, `allow`, `deny`. If the substrate grows a
rule plane, the suite goes red.

`test_ordinary_program_needs_no_governance` runs a program with arithmetic,
a filtered comprehension, a conditional, and a file write, and asserts it
works with no governance vocabulary anywhere. `test_ordinary_program_is_traceable`
asserts `why` can trace it.

**Both pass.** The first code example this session was a price filter, not a
refund handler. That is the measurable difference from the prior chain.

---

## 5. The Hackathon Bar

> The HN scraper works, `why` works, and the errors are helpful.

**Scraper:** ✅ Runs. Same output shape as the Python reference.
**`why`:** ✅ Works through arithmetic, function calls, field access, comprehensions, and network boundaries.
**Errors:** ✅ Every error is a named tag with a detail and, where possible, a fix.

```
divided-by-zero: the right side of / was 0
  try: guard with `if divisor != 0:`

module-not-used: asking a url needs the http module
  try: add `use http` at the top

wrong-arity: 'add' takes 2 values, given 1
```

`or fail as api-down` renames any underlying failure to a domain error. When
the sandbox proxy returned a 403 mid-session, the scraper reported
`api-down: HTTP Error 403: Forbidden` rather than a Python traceback — the
error mechanism proved itself on an unplanned failure.

**Assessment:** the bar is met for a single-file program. Not yet met for
eight hours of work, which would need modules across files, more collection
operations (sort, group, sum), and a real string library. None of that is
research; all of it is labour.

---

## 6. Bugs Found and Fixed

1. **Multi-line comprehension headers** — `for each s in stories` /
   `where ...: s` across two lines failed to parse. Fixed by allowing an
   indented header continuation.
2. **Missing User-Agent** — `real_http` sent no UA, which many APIs reject
   outright. Fixed.
3. **DAG printed as tree** — see 3.2.
4. **Wrong test expectation on `of` precedence** — see 3.3.

---

## 7. What Is Not Built

Named honestly, not deferred silently.

- **Static analysis.** The effect surface is collected *at runtime*. Shapes
  needs it computed *without running the program*. The AST is there and the
  effect kinds are there; the analysis pass is not written. This is the
  single largest gap.
- **Modules across files.** `use http` toggles a builtin, it does not import.
- **FFI.** Nothing declares effects across a foreign boundary. Still Tier 0.
- **Numeric tower.** Integers and floats are Python's. Integer division,
  overflow, and money are untouched — and Why needs a number that can carry
  provenance without precision loss.
- **Sort, group, sum, string library.** Ordinary and absent.
- **`ask` as an effect kind.** Confirmed again: a request-with-response is
  not reducible to send-plus-receive, and it is the most-used effect in both
  example programs.

---

## 8. Recommendation for the Next Session

**Write the static effect analyser.** It is the only thing standing between
this prototype and the Shapes destination, it operates on an AST that already
exists, and it can be validated immediately: run the analyser over
`hn.planes` and `pypi.planes` and check its answer against the runtime effect
log those same programs produce. That is a self-checking build with a
ready-made test oracle — rare, and worth taking while it is available.

Second priority is the numeric tower, because `why` on a money value that has
silently lost precision is worse than no `why` at all.

---

## 9. Files Delivered

```
planes/
  README.md          usage and language reference
  lexer.py           tokenizer + AST
  parser.py          recursive-descent parser
  interp.py          evaluator, derivation graph, why, effect log
  planes.py          CLI: run, --effects, --why NAME
  test_planes.py     45 tests
  hn.planes          the HN scraper
  pypi.planes        live-runnable equivalent
  ordinary.planes    reference ordinary program
  run_hn.py          stub-driven scraper harness
```
