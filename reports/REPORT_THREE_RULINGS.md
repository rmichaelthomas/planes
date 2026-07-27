# REPORT — One convention for the error record, a split shortfall, and a gate that counts what exists

**Branch:** `fix/record-convention-shortfall-split-and-silent-suites`
**Base:** `main` at `f87d626`
**Commits:** four, one per phase plus the verification script.

| | | |
|---|---|---|
| **A** | `38086e9` | A suite that reports nothing fails the gate |
| **B** | `66c924d` | The self-hosted shortfall split into port and write |
| **C** | `77afa92` | The error record keeps one convention for an absent field |
| **§8.2** | `c7d69b8` | The three rulings verified without a human |

**Gate:** green, exit 0. 54 files, 54 reporting, **1092 oks** (was 1085), 47 JS
tests, 47.8 s wall. `--fast` green at 43 files, 43 reporting, 925 oks.
`ruff` clean, `mypy` clean over 96 files. Counts **32 / 10 / 7 / 7** — reserved
words, builtins, effect kinds, host methods — all unmoved. Corpus 50 / 50
through the self-hosted stack. The 348-shape three-implementation agreement on
tag and detail: **0 divergences.**

**Catalogue:** reference **0 of 109**, self-hosted **72 of 113**, both unmoved,
and the 72 now arrives as **44 to port, 28 to write**.

**Verification:** `scripts/verify_three_rulings.py`, 35 checks, all pass;
`three-rulings-verification.md` is its output. Inputs from Rob: none, as §8.3
said. C4's `scripts/verify_fast_follow.py` also still passes — see §5.3, which
is the only reason anybody found out that it had stopped.

---

## §1 — Does `grammar/interp.planes` carry `path` at all?

C.1's first question. **No — it never had one, and that absence was itself the
divergence.**

`make-error-value` built a three-field record:

```
to make-error-value of err:
  give make-record of [{ key: "tag", ... }, { key: "detail", ... }, { key: "fix", ... }]
```

and the comment above it said so plainly: *"The path field A.4 carries on some
errors is a derivation concern left to a later build; tag and detail are what a
handler reads."* The reason is real — `values-equal` raises `cannot-compare`
without accumulating any steps, so there is no path in that interpreter to put
anywhere.

C.1 anticipated this case and drew the wrong conclusion from it: *"If so, this
is a two-implementation change and the third needs only a confirming
assertion."* It is not. Under Ruling 3 the absence of the field **is** the
divergence, and it is observable from an ordinary program:

```
when e is { path }:   →  bind on interp.py and js/interp.mjs
                      →  no match on grammar/interp.planes
```

That is a difference in what a program does depending on which implementation
ran it — precisely what invariant 1 exists to prevent. So this was a
three-implementation change. `make-error-value` now carries four fields, with
`path` honestly `nothing` on every error it raises. **The field converges; the
steps do not**, and computing real steps remains the derivation concern that
comment always described. All three now answer `["bound: nothing"]`.

---

## §2 — The `{ path }` / `.path` grep, including where nothing changed

C.4 asked for the grep across every `.planes` tree plus every suite, and for
the finding to be reported *including* where nothing needed changing. It is
re-run mechanically by section C of the verification script rather than
remembered, over **109 `.planes` files**: `grammar/` (5), `corpus/` (50),
`demo/` (23), `probe/` (23), repo root (8).

| what was searched for | hits | verdict |
|---|---|---|
| `{ path }` as a shape pattern, any `.planes` tree | **0** | nothing to change |
| `.path` field access, any `.planes` tree | 1 | **not an error record** |
| `path:` as a record key, any `.planes` tree | 3 | **not an error record** |
| `{ path }` / `err.path` in the Python suites | 2 files | both updated, §3 |
| `path` in `js/test/*.mjs` | 0 (2 comment hits: "code path") | nothing to change |
| `render.py` branching on the key's presence | 0 | nothing to change |
| `why_tree` branching on the key's presence | 0 | nothing to change |

The one `.path` hit is `grammar/interp.planes:1807`, `if f.path == path:` —
that is `lookup-file` walking the *file* records the effect boundary threads
(`{ path, body }`), which share a field name with the error record and nothing
else. The three `path:` hits are the same file records plus a function
parameter and a comment about the parser's "as_expr path".

**So the expectation held: no program anywhere used `{ path }` as a presence
test, and no program's behaviour changed.** C.4 was right that the expectation
is not the finding, and running it turned the expectation into a measurement.
`path` is young and set only on comparison mismatches, which is exactly why
this convention could still be changed cheaply — and why it was worth doing
before anything came to depend on the old one.

The two suite files that did touch it:

* **`test_fail.py::test_the_path_field_keeps_the_opposite_convention`** —
  rewritten, not deleted, per C.3. It read `["no path field"]`; it now reads
  `["bound: nothing"]` and is renamed
  `test_the_path_field_keeps_the_same_convention_as_fix`. A second assertion
  was added beside it pinning that a path which *does* apply still carries the
  same steps (`{a: [1, "2"]} == {a: [1, 2]}` → the field name `"a"` then list
  index `1`).
* **`test_errors.py::test_error_without_path_has_no_path_field`** — the prompt
  did not know about this one. Its assertion (`err.path is nothing` → `"true"`)
  is *unchanged and still true*, because dot access on a missing key already
  gave `nothing`; only its name and docstring described the old convention. It
  is renamed and given a second, **stronger** assertion that reads
  `error_record` directly — `is nothing` cannot tell present-and-nothing from
  absent, and that distinction is the whole of Ruling 3.

Invariant 4, stated rather than assumed: **one assertion is inverted and none
is weakened.** Inverting a pinned assertion to match a ruling is the ruling
landing; weakening one is a test that stops looking. The inverted assertion
still fails if `path` stops binding, and it is still the only place in the
suite that has ever looked at the question.

---

## §3 — The split, its multiplicity, and how big the porting build is

```
  has a reference twin          44   the clause exists — porting it is mechanical
  no reference twin             28   needs a clause written
                                --
                                72   unchanged; per-file 54 / 14 / 3 / 1
```

Totals preserved exactly as invariant 6 requires: **72 of 113** self-hosted,
**0 of 109** reference, per-file breakdown `interp.planes` 54, `parser.planes`
14, `lexer.planes` 3, `json.planes` 1. The split produced a number and ported
nothing.

### Multiplicity — 35 sites, 10 tags

Of the 44 with a twin, **35 carry a tag that maps to more than one catalogued
reference entry**, across ten tags:

| tag | entries | tag | entries |
|---|---|---|---|
| `cannot-compare` | 5 | `not-a-number` | 4 |
| `not-a-collection` | 4 | `module-not-used` | 3 |
| `not-a-list` | 3 | `not-a-record` | 3 |
| `not-text` | 3 | `wrong-arity` | 3 |
| `cannot-join` | 2 | `unknown-operator` | 2 |

Reported, not resolved. A tag is shared across messages by design
(`REPORT_DETAIL_CONVERGENCE.md` §4 item 4), so a tag match is evidence that *a*
clause exists to port and **not** proof it is the right clause for that site.
Nine of the 44 have a one-to-one twin and can be ported by lookup; the other 35
need a human or a careful machine to pick which of 2–5 catalogued clauses this
site means.

### What that implies about the size of the porting build

**Not 72 sites of authorship. Roughly nine mechanical ports, 35 ports that need
a per-site choice, and at most 28 clauses to write from nothing — and the 28 is
an over-count, for a reason the prompt's method cannot see.**

### A ceiling, not a measurement — 51 of 109

**Half the reference catalogue has no tag to match on.** Only `PlanesError` and
`GrammarDataError` carry one at all, and four `PlanesError` sites do not carry
one either:

| untagged | | untagged | |
|---|---|---|---|
| `PlanesSyntaxError` | 29 | `PlanesAmbiguity` | 6 |
| `RuleConflict` | 7 | `PlanesError` | 4 |
| `ModuleError` | 3 | `RuleNotSupported` | 2 |

**51 of 109.** A self-hosted `fail "line 3: ..." as parse-error` therefore
cannot match the reference's syntax message *however close the two are*,
because that catalogue entry has no tag to be found by.

That is where all seventeen `parser.planes` + `lexer.planes` sites land — 13
`parse-error`, 2 `unterminated-string`, 1 `unrecognized-escape`, 1
`unknown-node-kind`. The reference answers most of them already, and names a
fix while doing it. So **28 is an upper bound on the authorship work, not a
measurement of it**, and the checker says so at the point where the number is
read rather than only here.

### Tag unreadable at the site — 3

Three shortfall sites name their tag dynamically and so cannot be matched
either way. They fall to `no reference twin` because *nothing checked*, never
because anything was ruled out, and they are listed on their own so the
distortion stays visible:

```
interp.planes:258   to error-of of tag, detail:
interp.planes:1978  give fail-of of (error-of of stmt.tag, m.value.value), m.env
interp.planes:1990  give fail-of of (error-of of stmt.tag, message-value.value), m.env
```

The first of those is not a raise site at all. See §5.1.

---

## §4 — Phase A: what the gate now counts

**The Python half.** `scripts/run_suites.py` returns non-zero when a suite file
reports no result, and names the files. The message is still informative — "the
gate failed" without the list is worse than the warning it replaces — and it
names the fix, because that is the house rule for every other error in this
repo:

```
SILENT: 1 suite file(s) reported no result: test_zz_c5_silent_probe.py
  each ran nothing the gate can count — give it a `__main__` runner that
  prints 'N/M passing'
```

`--fast`, `--only` and `--skip` are safe by construction and were left that
way: `names` is the *selected* set, so a deliberately skipped suite is never
opened, never counted, and can never appear. Asserted, not assumed —
`--only test_fail.py --only <silent probe> --skip <silent probe>` exits 0, and
the full `--fast` tier is green at 43 files, 43 reporting.

Detection stays "a line ending in ` passing`". That is a convention rather than
a contract and it was deliberately not tightened: a suite that changes its
output format *should* fail loudly and be fixed, which is the intended
behaviour and not a limitation to paper over.

**The JavaScript half**, which is the gap the warning left open and the
mechanism nothing had ever looked at. `scripts/check_js_tests.py` enumerates
every test-shaped `.mjs` anywhere under `js/` and asserts each one is inside
what `ci.sh` hands to `node --test`.

* **The convention was confirmed, not assumed**, as A.2 asked: all seven files
  in `js/test/` share `*.test.mjs`, and the checker says so in its output
  (`all 7 share one convention`). It also matches on directory — anything under
  a `test/` or `tests/` component, under any name — so a file hidden by a
  *naming* convention is caught too, and it reports separately if the two rules
  ever disagree.
* **It reads the glob out of `ci.sh` rather than restating it.** A checker that
  hard-coded `js/test/*.mjs` would agree with a `ci.sh` narrowed to something
  else, which is the same silent-drift failure one level up.
* It is pure Python, so it runs whether or not `node` is on `PATH` — the one
  configuration where the old arrangement was silent twice over.

Both acceptance probes hold by construction: a stray `.mjs` in `js/test/sub/`
and one beside the test directory each fail the gate and are named. The
verification script also asserts something the acceptance criteria did not: that
`ci.sh` runs both checks under `timed` and not `timed_soft`. A non-zero return
only fails the gate if the step is a hard one, and two steps in that file
deliberately are not.

---

## §5 — What this build disproved about this prompt

Five, and the prompt was right to expect them: three rulings written from four
files read at `f87d626` is a thin basis, and it said so.

### 5.1 — A pinned total is one high, in both directions, and it is the checker's own bug

Invariant 7 says every count is a lower bound to verify, because *four
consecutive builds have found one low*. This one found one **high**.

`errors_coverage.py`'s self-hosted scanner matches `(?<!-)\berror-of of ` and
`\berror-fix-of of ` anywhere on a non-comment line. Two of the lines it matches
are the **definitions of those helpers**, not raise sites:

```
interp.planes:258   to error-of of tag, detail:            → counted as SHORTFALL
interp.planes:261   to error-fix-of of tag, detail, fix:   → counted as NAMES A FIX
```
(`:257` / `:260` at `f87d626`; Phase C's comment above them added a line.)

So `113` is 111, `72` is 71, and `6` is 5. The two errors are in opposite
directions, which is why the totals have looked stable across two builds.

**Not fixed here.** Invariant 6 pins the totals across Phase B and B.2 says the
phase produces a number; a build that changes on its own initiative the number
it was told to preserve is the drift §8.3 warns about. It is reported with
evidence, and the fix is one line. It also matters to the *next* build directly:
without it, the porting work list contains a function definition.

### 5.2 — Tag-matching cannot partition the shortfall, because half the catalogue has no tag

B.1 says "Split that bucket in two" and "Match on the **tag**". The method was
followed exactly, and it cannot do what the phrasing implies, because **51 of
the 109 catalogued reference errors carry no tag at all** — only `PlanesError`
and `GrammarDataError` carry one, and four `PlanesError` sites do not. Every
`parser.planes` and `lexer.planes` site — all seventeen — is classified *needs a
clause written* when the reference already answers it, through a
`PlanesSyntaxError` that mostly names a fix and has no tag to be found by.

B.1 was careful about the *other* direction (a tag match is not proof of the
right clause) and had no guard for this one. The consequence is asymmetric: the
`44` is honest with a caveat, the `28` is an upper bound. Reported inside the
checker's own output, where the number is read.

### 5.3 — The stale assertion was not in `render.py` or `why_tree`; it was in a committed checker nothing runs

C.4 named `render.py` and `why_tree` as the things to check for branching on the
key's presence. Neither does. The thing that actually held an assertion about
the old convention was **`scripts/verify_fast_follow.py:205`**, C4's own
verification script, which asserted `["no path field"]` — and it would have been
wrong on `main` from the moment Phase C landed.

It was found by grepping for the *prose* ("opposite convention"), not by the
code grep C.4 specified. It has been inverted, widened to check all three
implementations rather than one, and re-run; `fast-follow-verification.md` is
regenerated in the same commit.

### 5.4 — And that is an instance of Ruling 1, one level up, in the dimension Phase A did not look at

Ruling 1's stated principle is that *"a suite file that reports no result is the
gate misstating its own coverage"*. Four committed verification scripts —
`scripts/verify_v9.py`, `verify_batch_equivalence.py`, `verify_fast_follow.py`,
and now `verify_three_rulings.py` — are executed by **nothing**: not `ci.sh`,
not any `test_*.py`, not any other script. Grepped, not assumed.

That is the same failure class in a third mechanism. §5.3 is what it costs: a
committed checker asserted something false for the length of a build and
nothing would have said so. Phase A closed the Python-suite and JS-test
mechanisms and did not touch this one, because the prompt did not name it.

Not fixed here: these scripts run whole suites and would multiply the gate's
cost several times over, and deciding what a gate should pay is a ruling, not a
build detail. Recorded as the fifth instance of a class now at five.

### 5.5 — The third implementation needed more than a confirming assertion

C.1's contingency — *"if so, this is a two-implementation change and the third
needs only a confirming assertion"* — is wrong for the reason §1 gives: the
absence of the field is the divergence, not an exemption from it. Had it been
followed, this build would have shipped a convention that two of three
implementations keep, and Phase C's own acceptance criterion ("all three
implementations agree") would have been satisfied on tag and detail while the
record shape diverged underneath it.

### Smaller things, recorded not fixed

* **`ruff` and `mypy` are not on the default `PATH` in this environment**; they
  live in the repo's `.venv`. `scripts/ci.sh` calls them bare, so a fresh shell
  gets `ruff: command not found` and the gate dies at step nine with `set -e` —
  after everything expensive has already run. A one-line `command -v` guard
  with a stated message would turn that into a diagnosis. Not touched: it is
  environment, not the build.
* **`test_errors.py`'s `path` assertions are on the exception object**, not the
  record (`e.path == [1, 1]`). They are unaffected by Ruling 3 and stayed
  unaffected — the convention is about what `error_record` hands a *program*.
* An **empty path stays an empty list**, not `nothing`. A top-level mismatch
  (`5 == "5"`) has a path and it has no steps, and collapsing that to `nothing`
  would have been a second silent signal replacing the one this build removed.

---

## §6 — Invariants

| # | | |
|---|---|---|
| 1 | A behaviour change lands in all three implementations in the same commit | **held** — `77afa92` carries `interp.py`, `js/interp.mjs` and `grammar/interp.planes` |
| 2 | A message change and its regenerated artifact land in the same commit | **held** — `grammar/errors.json` is in `77afa92`; every change in it is an `interp.py:<line>` reference, no message text moved |
| 3 | `errors_coverage.py` reports and never fails | **held** — asserted twice, and Ruling 1 was kept off it deliberately |
| 4 | No test assertion is weakened | **held** — one inverted, stated explicitly in §2; one renamed and strengthened |
| 5 | Counts 32 / 10 / 7 / 7 after every phase | **held** — reserved words, builtins, effect kinds, host methods |
| 6 | Totals preserved across Phase B | **held** — 72 of 113, 0 of 109, 54 / 14 / 3 / 1 |
| 7 | Every count is a lower bound to verify | **broken by the repo, not by the build** — see §5.1: two of them are one high |

---

## §7 — Files

**Phase A** — `scripts/run_suites.py`, `scripts/ci.sh`,
`scripts/check_js_tests.py` (new).

**Phase B** — `errors_coverage.py`, `test_error_messages.py` (six new
assertions pinning the split's arithmetic).

**Phase C** — `interp.py`, `js/interp.mjs`, `grammar/interp.planes`,
`grammar/errors.json` (regenerated), `test_fail.py`, `test_errors.py`,
`scripts/verify_fast_follow.py`, `fast-follow-verification.md`.

**§8.2** — `scripts/verify_three_rulings.py` (new),
`three-rulings-verification.md` (new).

No grammar file other than `grammar/interp.planes` changed; no corpus, demo or
probe program changed; no reserved word, builtin, effect kind or host method
was added or removed.
