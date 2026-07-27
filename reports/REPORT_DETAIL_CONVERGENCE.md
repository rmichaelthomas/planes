# REPORT — Error details converged across all three implementations

**Branch:** `fix/error-detail-convergence` · **Base:** `main` at `7d58e05` (C2's merge)

C2 closed the error catalogue's shortfall and reported four things it did not
fix. This closes three of them, on Rob's instruction: the four remaining `fmt`
sites, the divergence with `grammar/interp.planes`, and the catalogue's unstable
ids.

**The headline: all three implementations now agree on the tag *and* the detail
text of every type error, over 348 shapes — and seven more host exceptions were
escaping than C2's sweep could see.**

---

## 1. What was asked, and what was actually there

C2's finding 1 named four sites where `fmt` rendered a text value bare, so
`cannot combine 5 with 5 using +` could not tell `"5"` from `5`. Finding 2 noted
that `grammar/interp.planes` rendered the same details through
`canonical-of-value`, which quotes text, and that nothing asserted the
difference. Finding 3 noted that catalogue ids move when a tag gains a raise
site.

Measuring before fixing changed the shape of all three:

| | C2 reported | measured here |
|---|---|---|
| `fmt` sites naming no kind | 4 | **25** — every site that puts a value in a detail |
| self-hosted divergences | "differs" | **235 of 348**, in 31 distinct shapes |
| of those, *tag* divergences | not measured | **14** — real behaviour differences, not text |
| host exceptions still escaping | 0 (C2 swept them) | **7** — C2's sweep was one-sided |

The last row is the one that matters most. C2 swept `<value> <op> 1` — a value of
each kind against a number — and every builtin. It never swept a **pair** of
values, so nothing tried `{a:1} < {a:2}` or `[1] in {a:1}`.

---

## 2. The value-rendering rule, stated once and applied three times

One rule, in `interp.py`'s `detail_value`, `js/interp.mjs`'s `detailValue`, and
`grammar/interp.planes`'s `detail-of-value`:

> **Write the value as the language would write it when writing it is bounded,
> and name its shape when it is not.**

```
cannot combine "5" with 1 using +          text, as a quoted literal
cannot take the whole part of true         boolean, number, nothing: the literal
cannot round [2 items]                     a list: its shape
cannot read .a from {record}               a record: its shape
```

Applied at **every** site that puts a value into a detail, not the four C2
named — because a rule applied at 4 of 25 sites is not a rule. The count is
measured off the catalogue itself: 25 raise sites in the reference whose detail
renders a value, their counterparts in `js/interp.mjs`, and 26 `fail`/`error-of`
statements in `grammar/interp.planes`.

**Two decisions worth stating.**

*Quotes alone, not the word "text".* C2 wrote `text "5"`; this drops the prefix.
The quotes carry it — Planes has one string syntax — and `cannot combine "5"
with 1 using +` reads where `cannot combine text "5" with 1 using +` does not.
It is also what `grammar/interp.planes` already produced, so the convergence
moved toward the implementation that was right rather than away from it.

*A list and a record name their shape, not their contents.* This is why the
answer is not simply "use the canonical form", which was the obvious move and is
wrong twice over. An error detail has to be **bounded**: a canonical render puts
every element of a 10,000-item list into a message, and puts
`{ token: "hunter2" }` into text that goes to stderr and into whatever collects
stderr. Both are asserted by test — one on a 200-item list, one on a record
holding a credential.

The self-hosted side had been reusing `canonical-of-value` for error details.
That function's own comment says it is the **test-oracle** form: "both sides
render an evaluated value to this exact text and the test compares strings." An
oracle needs to distinguish every value; a message needs to stay short. Reusing
one for the other is where the divergence came from. It is untouched and still
the oracle; `detail-of-value` is the message form.

---

## 3. The 14 tag divergences — real behaviour, not wording

Each of these was a different *answer*, not a different sentence.

| shape | reference | self-hosted | resolution |
|---|---|---|---|
| `lower`/`upper`/`normalize` of a **number** (3) | `not-text` | **coerced** to `"5"` | the self-hosted side refuses too |
| `1 in 5` / `true` / `nothing` (3) | `not-a-collection` | `unknown-operator` | `not-a-collection` — `in` **is** an operator; the value was wrong |
| `"a" in { a: 1 }` (1) | `true` | refused | the self-hosted side gained the record arm |
| `1 in "ab"` (1) | `not-text`, naming the container | `cannot-combine`, not naming it | the reference's tag and sentence |
| `first <non-number> of` (6) | a parse refusal on both | — | harness artifact, not a divergence |

The first row is the sharpest. `text-form-of`'s own comment said it refused a
list, a record, a boolean, and nothing "rather than leaking a host repr" — which
is **A.6 family 2's reasoning, reached independently and a build earlier**. It
just stopped one kind short: a number still coerced. The self-hosted interpreter
had most of the ruling before the ruling existed.

The second row is the same defect C2 fixed in `js/interp.mjs`, still present in
the third implementation. A fix that lands in two of three implementations is a
divergence wearing a fix's clothes.

---

## 4. Seven more host exceptions, and two accidents

The pair sweep found five escapes and two wrong answers. **Every one was on the
Python side; `js/interp.mjs` was already right on all seven** — the same
one-sided shape as A.6's family 1.

| shape | before | now |
|---|---|---|
| `{a:1} < {a:2}` | `TypeError: '<' not supported between instances of 'dict' and 'dict'` | `cannot-compare` |
| `nothing < nothing` | `TypeError: '<' not supported between instances of 'NoneType'…` | `cannot-compare` |
| `[1] in {a:1}` | `TypeError: unhashable type: 'list'` | `false` |
| `{a:1} in {a:1}` | `TypeError: unhashable type: 'dict'` | `false` |
| `true in [1, 2]` | `TypeError: a yes/no value is not a number` | `false` |
| `[1] < [2]` | **`true`** | `cannot-compare` |
| `true < false` | **`false`** | `cannot-compare` |

The last two are not crashes, which makes them worse: the program got an answer,
and the answer came from Python's list and bool comparison rather than from
Planes. `compare`'s own docstring said *"Ordering comparisons work on numbers and
on text"* — the guard was `type(a) is not type(b)`, which enforces *matching*
kinds and not *orderable* ones, so a same-kind pair fell through to the host. The
docstring was right and the code did not implement it. It does now, in the form
`js/interp.mjs` already used.

`true in [1, 2]` leaking is its own small lesson: membership went through
guarded equality, which **refuses** a cross-type comparison by design, but `x in
xs` asks whether an equal element is present and a differently-typed element is
an *answer* (no), not a mistake. Python's `in` therefore surfaced planes_num's
own refusal. `loose_equal` is a port of the JavaScript `looseEqual`, arm for arm.

---

## 5. Catalogue ids (C2's finding 3)

**A fix was needed, and it is a real improvement rather than a guarantee.**

The disambiguator was a running count over a whole file, so adding one raise
site renumbered every later site sharing its tag: adding `first n of`'s count
guard moved `whole of` from `interp.not-a-number-3` to `-4`, and `for each`'s
guard from `interp.not-a-collection` to `-2`. An id meant one message before the
commit and a different one after.

Two changes:

1. **The enclosing function is now part of the id** — `interp.not-a-number.builtin`,
   `interp.unknown-operator.apply_op`. That is data the entry already carried
   (`raised_in`), so it promotes rather than invents, it reads better, and it is
   stable under the change that broke it.
2. **The remaining count follows source order.** `ast.walk` is breadth-first, so
   the suffix did not even follow the file — `expect`'s three raises came out in
   walk order. Entries are sorted by line before numbering, which also puts
   `errors.json` itself in source order.

What is honestly left: **58 of 114 ids still carry a count**, 38 of those because
their exception class has no tag at all (every `PlanesSyntaxError` in one
function collides — `parse_rule` has seven). Inserting a raise *above* one of
those still renumbers it. Nothing short of a hand-assigned key makes an id
permanent, and a hand-assigned key is what ruling D1 — *generated, not
hand-authored* — exists to refuse. The blast radius went from "every site with
this tag anywhere in the file" to "sites with this tag in this one function",
and that is the whole of the claim.

---

## 6. The limit this build found and did not close

**`grammar/interp.planes` cannot name a fix anywhere, and the reason is in the
language.**

A Planes program raises with `fail <message> as <tag>` — one slot for text — and
the error record a program catches with `or fail as e` carries `e.tag` and
`e.detail` and nothing else. `error-of of tag, detail` is a two-field record.
There is no third field, so the self-hosted interpreter says what went wrong and
never what to do about it.

So the three implementations agree on every tag and every detail, and **cannot**
agree on fix clauses: two have them and one has no way to. C2's report said the
self-hosted interpreter "is not measured" by the catalogue. The sharper statement
is that it *could not pass*: the highest-leverage machine-authorship affordance
in the language is structurally unavailable in the language's own
implementation of itself.

Closing it means a two-part `fail` and a third field on the error record — a
language addition, and this chain does not make those without a ruling. Reported,
not built. It is named in `docs/error-messages.md` too, because a learner reading
`grammar/interp.planes` should not conclude the commitment was forgotten there.

---

## 7. Verification

| item | result |
|---|---|
| `scripts/ci.sh` | **exit 0** — 996 oks across 52 suites (was 989), ruff clean, mypy 91 source files |
| all three implementations agree | **348 shapes, 0 divergences** on tag and detail — `test_all_three_implementations_agree_on_tag_and_detail` |
| no host exception escapes | **0** across the same 348, both the reference and the self-hosted stack |
| counts | 32 keywords / 10 builtins / 7 effect kinds / 8 host methods |
| the host seam | `host.py` and every `js/host*.mjs`: **empty diff** |
| `grammar/interp.planes` stays in the declared core | `core_check.py` — 28 keywords, 10 builtins, 7 effect kinds, unchanged |
| generated artifacts | `grammar_gen.py --check` clean on all three, JS node parity 32/32 |
| the catalogue's work list | still **0** of 109 errors |
| self-hosted suites | `test_interp_in_planes.py` 66/66, and every metacircular suite green |

## 8. Every file changed

Eight, plus this report.

| file | what |
|---|---|
| `interp.py` | `detail_value` replaces `kinded` and is applied at all 25 error-detail sites; `_order_kind` + `compare` rewritten to the orderable-kinds rule; `loose_equal` added; `membership` guards a record key and uses loose equality over a list |
| `js/interp.mjs` | `detailValue` at the counterpart sites, byte-identical messages |
| `grammar/interp.planes` | `detail-of-value` (new) at 26 error-detail sites; `require-text-of` replaces `text-form-of` and refuses a number; `require-target-of` (new) guards `ask`/`read`/`write`; `compare-values` + `order-kind-of` (new) replace `cmp-of`; `num-of` takes the operator; `member-of` gains the record arm and the corrected tag; `first n of` gains its count guard; the two `values-equal` boolean arms name both operands |
| `grammar_gen.py` | ids carry the enclosing function; entries sorted by source line before numbering; `_entry_line` helper |
| `grammar/errors.json` | regenerated — ids and order only, counts unchanged |
| `test_builtin_guards.py` | +5 tests: the three-way 348-shape sweep, the pair-wise host-exception sweep, the ordering rule, membership answering, and the bounded-detail assertions |
| `test_error_messages.py` | +2 tests pinning the id scheme and source ordering; two pinned ids updated |
| `docs/error-messages.md` | the value rule, the third implementation, and the fix-clause limit |

`REPORT_ERROR_CATALOGUE.md` is left as it was written. It is C2's session record,
and its findings 1–3 were accurate when made; this report is where they are
closed.

---

## 9. What this build disproved

**1. "Four sites" was 25, and the difference is the point.** C2 fixed two sites
and reported four, reasoning that changing the rest was "a detail-line change
across two implementations with its own agreement to establish". That was true
and it was also the wrong unit: the thing being fixed is a *rule about how a
value is written*, and a rule that holds at 2 of 25 sites is not a rule. The
agreement C2 deferred took one test to establish and found seven escaping host
exceptions on the way.

**2. C2's sweep was one-sided and said so in its own field names.** Its cases
were `<value> <op> 1` — every value kind against a number. `_other_cases()` even
names them `f"{kind} + 1"`. Nothing tried two non-numbers, so five host
exceptions and two host-supplied wrong answers sat inside the swept operators the
whole time. **A sweep is only as broad as its worst-covered axis, and 144 cases
looked exhaustive because the count was large.**

**3. The self-hosted interpreter had part of A.6's ruling before A.6.**
`text-form-of` refused a list, a record, a boolean, and nothing, and its comment
gave family 2's exact reasoning — "rather than leaking a host repr". It stopped
one kind short. C1 framed the divergences as "both implementations confidently
wrong"; there were three implementations, and the third was mostly right and
never consulted.

**4. Tag-only agreement is not agreement.** The self-hosted suites compare
`e.tag`, so 235 of 348 details could differ with every suite green. A tag is
deliberately shared across many messages — that is what makes it a good handle
for `or fail as e` and a bad one for asserting what a program tells a person.

**5. The instability in finding 3 was worse than finding 3 said.** It reported
that the count moves when a tag gains a raise site. It also did not follow source
order at all, because `ast.walk` is breadth-first — so the suffix was
unpredictable from reading the file even with no edits. The finding named the
symptom it had observed and missed the one it hadn't.
