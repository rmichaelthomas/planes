# REPORT — The scanner counts itself, the ceiling becomes a measurement, and a checker nobody runs is retired

**Branch:** `fix/scanner-off-by-one-and-checker-retirement`
**Base:** `main` at `bf1068c`
**Commits:** three, one per phase.

| | | |
|---|---|---|
| **A** | `55b37bd` | A function definition is not a raise site |
| **B** | `d3f0052` | The shortfall matched on function as well as tag |
| **C** | `7386826` | A verification script graduates or is deleted |

**Gate:** green, exit 0. **56 files, 56 reporting, 1116 oks** (was 54 / 54 /
1092), 47 JS tests, 44.4 s wall, `mypy` 91 files. `--fast` green at 44 files,
44 reporting, 947 oks. Counts **32 / 10 / 7 / 7**. Reference catalogue **0 of
109**. Corpus 50 / 50 self-hosted. 348-shape three-implementation agreement:
**0 divergences**.

**No fix clause was ported.** That is the next build, and both numbers that
scope it moved here.

---

## §1 — The corrected arithmetic, against A.3

Every figure in the prompt's A.3 table held **exactly**, at baseline and after.
There is no second defect in the scanner.

| figure | at `bf1068c` | A.3 predicted | after A | |
|---|---|---|---|---|
| self-hosted raise sites | 113 | 111 | **111** | ✅ |
| names a fix | 6 | 5 | **5** | ✅ |
| deliberately names none | 35 | 35 | **35** | ✅ |
| should name one and does not | 72 | 71 | **71** | ✅ |
| split: has a twin | 44 | 44 | **44** | ✅ |
| split: no twin | 28 | 27 | **27** | ✅ |
| tag unreadable | 3 | 2 | **2** | ✅ |

The two lines the scanner was counting:

```
grammar/interp.planes:258   to error-of of tag, detail:            → SHORTFALL
grammar/interp.planes:261   to error-fix-of of tag, detail, fix:   → NAMES A FIX
```

Two errors in opposite directions, which is exactly why 113 and 72 looked
stable across two builds while each was one high.

**The guard is the general principle, not a list of two names.** A match
defines if everything before it on the line is exactly `to`. It deliberately
does not skip every line beginning `to `, because Planes allows a single inline
statement as a function body — `to f of x: give fail-of of (error-of of "y",
z), env` is a real raise site on a `to` line, and a blanket skip would have
traded an over-count for an under-count (failure mode 1). Both directions are
asserted in `test_error_messages.py`.

The two surviving tag-unreadable sites are `interp.planes:1978` and `:1990`,
both genuine dynamic-tag raises (`error-of of stmt.tag, ...`), exactly as A.3
predicted.

### The `ruff` / `mypy` preflight (A.4)

`scripts/ci.sh` invoked both bare, and this repo keeps them in `./.venv`. A
fresh shell died at **step nine** with `command not found` — after the whole
suite, the JS tests and every checker had already run. The gate now checks at
step one and **fails**, per A.4's ruling, rather than skipping: `node` is the
one thing this gate lets skip, and a green gate that silently type-checked
nothing is the same dishonesty about coverage the silent-suite guard exists to
prevent.

```
ci.sh: not on PATH: ruff mypy
  this repo keeps them in ./.venv, which is not activated in this shell.
  run the gate with:
      PATH="$PWD/.venv/bin:$PATH" scripts/ci.sh
  or activate it first:  source .venv/bin/activate
```

`--fast` does not run `mypy`, so it requires only `ruff`, and the suggested
command keeps the tier. Both directions are asserted in `test_gate.py`.

---

## §2 — The three-state split

```
  has a reference twin      44   by TAG       asserted at both sites
  has a probable twin        9   by FUNCTION  a naming convention nothing asserts
  no reference twin         18   survives both passes
                            --
                            71   unchanged
```

Totals unmoved across Phase B exactly as invariant 1 requires: **111** raise
sites, **71** shortfall, reference **0 of 109**.

The second key is the enclosing function, normalised across `_` and `-` —
`parser.py`'s `read_effect_word` against `grammar/parser.planes`'s
`read-effect-word`. The tag pass runs first because it is stronger evidence,
and a site both passes could match stays in the tag bucket; that ordering is
asserted rather than incidental.

**The two are not merged.** A function match is weaker evidence: the
correspondence is inferred from a naming convention nothing asserts. A matcher
that hides which key it used is worse than one that understates, because the
next build decides per site and has to see which evidence it is deciding on.

### Multiplicity, on both passes

| pass | sites | distinct keys | worst |
|---|---|---|---|
| by tag | 35 of 44 | 10 tags | `cannot-compare` → 5 entries |
| by function | 3 of 9 | 3 functions | `parse-rule` → 6 entries |

It bites harder on the second pass, and the reason is structural: a tag names
one kind of failure, a function may raise several.

---

## §3 — The seventeen lexer and parser sites

The population Phase B exists for. **Every one of them landed in "no twin"
under tag-matching alone** — that is C5's finding, and it is what a second key
had to answer.

| | file:line | enclosing function | tag |
|---|---|---|---|
| `fn` | `parser.planes:1324` | `parse-record-field` | `parse-error` |
| `fn` | `parser.planes:1391` | `parse-primary` | `parse-error` |
| `fn` | `parser.planes:1554` | `parse-with-field` | `parse-error` |
| `fn` | `parser.planes:2001` | `read-effect-word` | `parse-error` |
| `fn` | `parser.planes:2025` | `read-claim` | `parse-error` |
| `fn` | `parser.planes:2118` | `parse-rule` | `parse-error` |
| `fn` | `parser.planes:2157` | `parse-note-entry` | `parse-error` |
| `fn` | `parser.planes:2214` | `parse-when-pattern-entry` | `parse-error` |
| `fn` | `parser.planes:2295` | `finish-because` | `parse-error` |
| — | `parser.planes:70` | `digit-value` | `parse-error` |
| — | `parser.planes:511` | `canonical-of-node` | `unknown-node-kind` |
| — | `parser.planes:1086` | `expect-kind` | `parse-error` |
| — | `parser.planes:1093` | `expect-op` | `parse-error` |
| — | `parser.planes:2241` | `parse-when` | `parse-error` |
| — | `lexer.planes:291` | `flush-pending` | `unterminated-string` |
| — | `lexer.planes:295` | `flush-pending` | `unterminated-string` |
| — | `lexer.planes:412` | `step-string-escape` | `unrecognized-escape` |

**9 of 17 matched. 8 still need a clause written.**

The eight are informative about *how* the port diverged, which is why they are
named rather than counted. `lexer.planes`'s `flush-pending` and
`step-string-escape` correspond to `lexer.py`'s `tokenize` and
`_resolve_string_escapes` — the port restructured the lexer and the names went
with it. `expect-kind`/`expect-op` split the reference's single `expect`.
`digit-value` and `canonical-of-node` have no reference counterpart at all.

**No fuzzy matching was attempted.** A rename is a real absence of evidence,
not a near miss to be laundered — and B.3's whole point is that the confidence
of a match must be visible, not averaged away.

---

## §4 — The rewritten ceiling: what is still unmatchable

C5's note said what tag-matching could not see. Deleting it would have made the
output stop saying what it still cannot see (failure mode 5), so it is
**rewritten**, and the honest statement is that a ceiling has moved, not gone:

> 51 of the 109 catalogued reference errors carry no tag at all
> (PlanesSyntaxError, RuleConflict, PlanesAmbiguity, ModuleError,
> RuleNotSupported, and four PlanesError sites). The function pass reaches into
> that half and matched 9 of them. **What it cannot reach is a self-hosted
> function the port renamed, or one with no reference counterpart at all — and
> nothing distinguishes those two from each other here.** So 18 remains an
> upper bound on the authorship work, a tighter one than before and still not a
> measurement.

That last clause is the load-bearing one. `flush-pending` and `digit-value` are
both unmatched, and the first almost certainly has a reference clause to port
while the second almost certainly does not. **No key available here tells them
apart.** A third pass would need to match on message *shape* — comparing
`"line " + (text of t.line) + ": expected ..."` against `parser.py`'s
`f"line {tok.line}: expected ..."` — which is a different kind of evidence
again and would need its own ruling about how much text overlap counts.

---

## §5 — The size of the porting build

**This is the number this build exists to produce.**

| | sites | what the porting build does |
|---|---:|---|
| one-to-one twin, by tag | **9** | copy the clause; a lookup |
| one-to-one twin, by function | **6** | copy the clause; a lookup, weaker provenance |
| twin with multiplicity, by tag | **35** | choose among 2–5 catalogued clauses per site |
| twin with multiplicity, by function | **3** | choose among 2–6 per site |
| no twin | **18** | write a clause from nothing (an **upper bound**) |
| | **71** | |

So: **15 mechanical ports, 38 ports that need a per-site choice, and at most 18
clauses to author.** The 18 breaks down `interp.planes` 9, `parser.planes` 5,
`lexer.planes` 3, `json.planes` 1.

The shape of that work is not what "72 name no fix" suggested three builds ago,
and it is not what "44 to port, 28 to write" suggested one build ago. The
largest single body of work is neither porting nor authoring — it is **38
per-site decisions about which of several existing clauses a site means**, and
that is a reading task, not a writing one.

---

## §6 — The verification-script retirement, script by script

### The inventory (C.1) — seven, not four

C5 §5.4 named four `scripts/verify_*.py`. **There are seven.** Three live in
the repo root, outside that glob and outside the sentence that described them:

```
scripts/verify_batch_equivalence.py   verify_annotation.py
scripts/verify_fast_follow.py         verify_grammar_and_amber.py
scripts/verify_three_rulings.py       verify_values.py
scripts/verify_v9.py
```

Grepped across `scripts/ci.sh`, every `test_*.py` and every other script:
**none is referenced by anything that executes.** The expected answer, and not
the finding.

### Two were already broken on `main`

This is stronger evidence for the ruling than C5 had, which was one script
holding one stale assertion.

| script | state | |
|---|---|---|
| `verify_annotation.py` | **FAILS** | section E asserts the reserved-word ceiling *"stays at 30"*. It is 32, and has been for many builds. |
| `verify_grammar_and_amber.py` | **CRASHES** | shells out to `test_coverage.py` with a 120 s timeout it now exceeds. |
| `verify_values.py` | passes | |
| `scripts/verify_v9.py` | passes | |
| `scripts/verify_batch_equivalence.py` | passes | 481 / 481 |
| `scripts/verify_fast_follow.py` | passes | inverted at C5 §5.3 — it had been wrong for a build |
| `scripts/verify_three_rulings.py` | passes | written last build |

A third cost surfaced while running them: **two of these scripts mutate shared
repo state** (`grammar/vocabulary.json`, rewritten with `format: 999`) and are
outside `run_suites.py`'s `EXCLUSIVE` discipline entirely. Running two at once
corrupts the tree — it produced a spurious `GrammarDataError` divergence in the
batch-equivalence run mid-build. The gate's own suites cannot do that to each
other, because the runner knows which ones conflict.

### Graduate or delete (C.2)

**Graduated — the two claims with no counterpart anywhere in the suite:**

| claim | to | why it was durable |
|---|---|---|
| `run-batch` answers what `run` answers, 481 cases | **`test_batch_equivalence.py`** (new) | Every cross-implementation agreement this repo reports goes through the batch path. `test_builtin_guards._js_raw` existed *only* to serve this comparison — its docstring says so — and would have become dead code holding up a claim nothing checked. |
| used-vs-declared host surface, by grepping call sites | **`test_host.py`** | This is the check that found `to_json` dead at C4. |
| no host JSON capability reachable from `grammar/*.planes` | **`test_host.py`** | C1's result; a `.planes` call would silently undo it. |

The host one is **failure mode 4 caught in the act**.
`test_host.py::test_a_host_is_five_capabilities_a_resolver_and_a_json_reader`
explicitly *deferred* the used-vs-declared question to
`scripts/verify_fast_follow.py` in its own docstring. Deleting that script
without reading the docstring would have silently removed the seam invariant
while leaving a comment pointing at a file that no longer existed.

`test_batch_equivalence.py` takes **35 s** and carries **no cap**. A sample
would have been a quieter claim than the retired script made, and this build is
about not making quieter claims. It is its own file so `--fast` can skip it;
parallelism absorbs the rest, and the gate went from 41.3 s to 44.4 s.

**Deleted — all seven scripts.** Every remaining claim was checked against the
suite *before* deleting, not assumed:

| script | its claims | already covered by |
|---|---|---|
| `verify_annotation.py` | inertness, strip no-op, round-trip, marker, note/because raises, nesting | `test_annotation.py` — which sweeps **every** `.planes` file, where the script used a fixed list. Its `test_reserved_word_ceiling_unchanged` is the correct version of the row that has been failing in the script. |
| `verify_values.py` | `0.1+0.2`, `5 == "5"`, `is nothing`, `if 0:`, record literals, scoping, `truthy` unreachable | `test_values.py`, `test_numbers.py`, `test_planes.py`, `test_record.py` |
| `scripts/verify_v9.py` | text builtins, `cannot-combine`, nested compare path, recording OFF/ON byte-identical | `test_text.py`, `test_errors.py`, `test_record.py`, `test_builtin_guards.py` |
| `verify_grammar_and_amber.py` | grammar-as-data, `format 999` refusal, amber sites | `test_grammar_data.py`, `test_amber.py`, `test_names.py` |
| `scripts/verify_fast_follow.py` | the `path` convention, the seam, effect names, counts | graduated at C5 into `test_fail.py`; seam graduated here; `test_names.py` |
| `scripts/verify_three_rulings.py` | silent suites, JS enumeration, the split, the convention | graduated into `test_gate.py` and `test_error_messages.py` in **Phase A of this build** |
| `scripts/verify_batch_equivalence.py` | run/run-batch equivalence | graduated to `test_batch_equivalence.py` |

**Outputs.** Six `*-verification.md` files are cited by a `REPORT_*.md` and
stay. Two — `v9-verification.md` and `value-model-verification.md` — are cited
by nothing and go with their scripts. This matches a precedent the repo had
already set without stating it: `lexer-in-planes-verification.md` and
`parser-in-planes-verification.md` have outlived their producers for several
builds.

`annotation-verification.md` is kept **at its committed content**, which
records all-PASS. That is not a contradiction with the script now failing: the
"ceiling stays at 30" row was *true on the date the record was written*, and
the language grew to 32 deliberately afterwards. The record is accurate for its
date; the script is what went stale. That distinction is the whole argument for
the ruling.

### The rule, stated where the next build reads it (C.3)

In `scripts/ci.sh`, beside the gate:

> **A verification script graduates into a suite or is deleted when its build
> merges.** There is no third option, and there is no `scripts/verify_*.py`.

Not in `MANIFEST.md` — see §7's smaller findings; that file is itself a stale
record.

And `test_gate.py` asserts it: no `verify_*.py` may exist anywhere in the tree,
with a failure message that names the two options. Five instances of one
failure class have earned one self-checking assertion.

### The ok total, before and after (C.4)

| | files | reporting | oks |
|---|---:|---:|---:|
| baseline `bf1068c` | 54 | 54 | 1092 |
| after Phase A | 55 | 55 | **1103** (+11: `test_gate.py` ×10, scanner-definition ×1) |
| after Phase B | 55 | 55 | **1109** (+6: the three-state split) |
| after Phase C | 56 | 56 | **1116** (+7: 4 graduated, 3 for the rule itself) |

The graduation is wired up: the rise is stated and every graduated assertion
runs in the gate.

---

## §7 — What this build disproved about this prompt

Five. The prompt was written from two files read at `bf1068c` and said so.

### 7.1 — The category is seven, not four, and the prompt inherited the undercount

C5 §5.4 said "four committed `scripts/verify_*.py`", and this prompt's §1
Ruling 3 and §7 S1 both carried that number forward. The real figure is seven:
`verify_annotation.py`, `verify_grammar_and_amber.py` and `verify_values.py`
predate the `scripts/` directory and live in the repo root. C5's sentence was
true of the glob it named and false of the category it described, and this
prompt repeated the glob as though it were the category. C.1's "confirm the
count and check for any elsewhere in the tree" is the instruction that caught
it — the prompt guarded against exactly this and still stated the wrong number
in its own ruling.

### 7.2 — "One costs" was an undercount too: two of the seven were already broken

§1 Ruling 3 offers `verify_fast_follow.py`'s stale `path` assertion as *the*
evidence — one script, wrong for the length of one build. On `main` at
`bf1068c`, **`verify_annotation.py` fails and `verify_grammar_and_amber.py`
crashes**, and the first has been asserting a reserved-word ceiling of 30 since
the language passed 30. The ruling was better supported than the prompt knew.

### 7.3 — Deleting a verification script can silently delete a live invariant, and the prompt's own worked example is where it happens

C.2 nominates `verify_fast_follow.py` as the worked example and points at its
`path` assertion, "which is exactly why its going stale mattered". But that
assertion had *already* been graduated at C5. The claim in that script with no
home was a different one: **used-vs-declared host methods**, section C — and
`test_host.py`'s own docstring **defers to the deleted script for it**. A build
that followed C.2's example literally, reading only the row the prompt pointed
at, would have deleted the seam invariant and left a comment pointing at a file
that no longer existed. Failure mode 4 was real and was armed by the prompt's
own illustration.

### 7.4 — Graduating needs the runner to be re-entrant, which nothing anticipated

`test_gate.py` invokes `scripts/run_suites.py` as a subprocess to assert that a
silent suite fails. `run_suites.py` **clears `.ci-logs/` on entry**, so a nested
run deletes the logs of the run it is running inside, and the parent then fails
to read them back — a self-destroying gate. Fixed with `PLANES_LOGDIR`, and
`test_gate.py` is `EXCLUSIVE` besides. The prompt's §8.2 says "every check below
goes into a `test_*.py` and stays there" without noticing that moving a checker
*into* the runner changes what the runner has to tolerate.

### 7.5 — A.3's table was exactly right, which is itself worth recording

Invariant 7 says every count is a lower bound to verify, because four builds
found one low and C5 found two high. **All seven figures in A.3 held exactly**,
derived from reading `4eefb8b` and C5's report without running anything. That
is the first table in this arc's recent history that needed no correction —
and it is the one that was derived from reading the code rather than carried
forward from a previous report. Worth stating in the direction of what worked.

### Smaller things, recorded not fixed

* **`MANIFEST.md` is stale by an order of magnitude.** It says "55 files.
  Verified: … all 217 tests pass" and lists 10 implementation files and 7 test
  files. The repo has 56 suite files and 1116 oks. C.3 offered it as a home for
  the retirement rule; it is not a live document and the rule went to
  `scripts/ci.sh` instead. Whether to regenerate or retire it is a ruling.
* **Two verification scripts could corrupt the repo by running concurrently**,
  because they rewrite `grammar/vocabulary.json` and sit outside
  `run_suites.py`'s `EXCLUSIVE` list. Moot now that they are deleted, but it is
  a property any future out-of-band checker would have.
* **`scripts/` holds five `measure_*` and `run_*` scripts the gate also does
  not run.** They are instruments that report numbers, not checkers that
  assert, so the retirement rule does not reach them — and
  `scripts/parser_corpus_agreement.py`, which looks similar, is imported by
  three suites and is a library. Checked rather than assumed.

---

## §8 — Invariants

| # | | |
|---|---|---|
| 1 | totals pinned per phase; A moves them once to the A.3 table | **held** — B and C moved nothing; 111 / 71 asserted in the suite |
| 2 | `errors_coverage.py` reports and never fails | **held** — asserted for both modes |
| 3 | reference work list stays 0 of 109 | **held** |
| 4 | counts 32 / 10 / 7 / 7 after every phase | **held** |
| 5 | no assertion weakened; A *updates* six, C *moves* assertions | **held** — six pinned numbers updated with the reason stated; every moved assertion runs in the gate and the ok total rose to prove it |
| 6 | no fix clause ported | **held** — zero |
| 7 | every count a lower bound to verify | **held, and one was low**: the verification-script category was 4 in the prompt and 7 in the tree |

---

## §9 — Files

**Phase A** — `errors_coverage.py`, `scripts/ci.sh`, `scripts/run_suites.py`,
`test_error_messages.py`, `test_gate.py` (new).

**Phase B** — `errors_coverage.py`, `test_error_messages.py`.

**Phase C** — `scripts/ci.sh`, `test_gate.py`, `test_host.py`,
`test_builtin_guards.py`, `test_batch_equivalence.py` (new); deleted
`scripts/verify_batch_equivalence.py`, `scripts/verify_fast_follow.py`,
`scripts/verify_three_rulings.py`, `scripts/verify_v9.py`,
`verify_annotation.py`, `verify_grammar_and_amber.py`, `verify_values.py`,
`v9-verification.md`, `value-model-verification.md`.

No `grammar/*.planes` file changed, no `grammar/errors.json` regeneration was
needed (no message text moved), and no reserved word, builtin, effect kind or
host method was added or removed.
