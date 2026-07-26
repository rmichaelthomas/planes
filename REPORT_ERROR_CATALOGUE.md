# REPORT — The catalogue completed, and P-Q14's design record

**Branch:** `feat/error-catalogue` · **Base:** `main` at `f6cf7cd` (C1's merge)

`errors name the fix` has been a language-level commitment since `unbound` v1.1
§22 and was counted for the first time in S8. This build closes the shortfall,
gives the measurement a floor, states the rule for what it measures, closes the
thirteen host divergences C1 found, and produces the design record P-Q14 has
owed since the artifact shipped mechanically at #9.

---

## 1. The headline: three-state counts, before and after

**The work-list number is 0.** That is the number A.3 asks for and the only one
that is a work list.

| | baseline `f6cf7cd` | after |
|---|---|---|
| catalogued message sites | 97 | **114** |
| — errors (measured) | 92 | **109** |
| — rule-plane reports (listed) | 5 | **5** |
| **names a fix** | 72 | **104** |
| **deliberately names none** | 0 | **5** |
| **should name one and does not** | **20** | **0** |
| unreadable at the raise site (a figure, not a state) | 9 | 4 |
| of the passes, delegating to `amber.json` | 6 | 6 |

Every figure above is measured, not remembered: the baseline column is computed
by re-classifying `git show f6cf7cd:grammar/errors.json` through the new
classifier, and the "after" column is `python3 errors_coverage.py`.

**The baseline is not S8's published table**, and the difference matters. S8
reported four buckets over all 97 entries — 70 names a fix / 6 delegates /
9 unreadable / 12 NAMES NO FIX — and this build's §0 confirmed those numbers
exactly, so the prompt's figures were *not* stale this time. But under the
inclusion rule §4 states:

* **four rule-plane report lines were being counted as passes.** They are not
  errors. Removing them takes 70 → 66, and with the 6 delegating sites folded
  into "names a fix" (three states, not four) the baseline pass count is 72.
* **the work list at baseline was 20, not 12** — 11 genuine shortfall plus the
  9 unreadable, because an unknown is never a pass and now has to land in one
  of the three states rather than sitting in a bucket of its own.

So the shortfall S8 published as 12% was, measured honestly, **20 of 92**.

The error population grew from 92 to 109. Seventeen of the eighteen new entries
are accounted for below; one entry "disappeared" and did not — see §8, finding 3.

---

## 2. Where each of the nine unreadable entries landed

A.1's ruling: restructure the raise site so the message is a literal, do not
teach the generator to chase variables. **Five could be. Four could not, for one
reason: they do not write a message.**

| site | id | destination | still unreadable? |
|---|---|---|---|
| `interp.py:1033` | `unknown-operator-1` | **names a fix** | no |
| `interp.py:1058` | `unknown-operator-2` | **names a fix** | no |
| `interp.py:693` | `cannot-evaluate` | **names a fix** | no |
| `interp.py:831` | `unknown-builtin` | **names a fix** | no |
| `interp.py:739` | `ask-failed` | **names a fix** | no |
| `interp.py:554` | `planeserror-site-1` (`fail`) | **deliberately names none** | yes |
| `interp.py:674` | `planeserror-site-2` (`or fail`, caught Planes error) | **deliberately names none** | yes |
| `interp.py:679` | `planeserror-site-3` (`or fail`, host exception) | **deliberately names none** | yes |
| `interp.py:678` | `planeserror-site-4` (`or fail` handler, host exception) | **deliberately names none** | yes |

Five to "names a fix", four to "deliberately names none". **None to done by
default** — which is what Phase 1 asked to be reported.

The four that stayed unreadable are unreadable *because* they forward text
somebody else wrote: `fail "..." as tag` raises the author's own message, and the
three `or fail` paths re-tag a caught Planes error or a host exception under the
author's tag. A literal message is impossible there and inventing a fix clause
would attach the language's advice to a failure the language did not diagnose. So
they carry a `no_fix` reason instead — read as a literal at the raise site,
exactly the way a message is (see §5).

**One thing changed while reading them.** `or fail`'s re-raise of a caught
`PlanesError` was dropping the caught error's `fix`: an error that named a fix
stopped naming one the moment an author wrapped it in `or fail as e`. It now
carries `e.fix` forward, in both implementations.

---

## 3. Every fix clause written, with what the error is and what to do

A.2 item 4 warns that a clause restating the error is worse than none. The test
each of these has to pass: **does the clause carry information the error does
not?** The third column names that information.

### The twelve, by category

**Category 1 — three lexer string-literal messages made structural.** These
already named their fix, inline in prose after a `--`. Nothing was added; the
clause moved to a continuation line so a catalogue and a tool can see it. Changed
in all three implementations — `lexer.py`, `js/lexer.mjs`, and the self-hosted
`grammar/lexer.planes`.

| error | fix clause | new information |
|---|---|---|
| `unrecognized escape '\q' in a string literal` | `the four recognized escapes are \" \\ \n \t -- for any other character, write the character itself` | the four; and that there is no code-point escape to reach for |
| `unterminated string literal -- no closing quote found before the end of the line` | `add the closing quote; a Planes string cannot span multiple lines, so a long one has to be joined with + across lines` | how to write a long string at all |
| `unterminated string literal -- a backslash right before the closing quote escapes that quote (\")` | `the four recognized escapes are \" \\ \n \t -- write \\ for a literal trailing backslash` | the exact two characters to type |

**Category 2 — the rules-report line left the catalogue's measurement.** See §4.

**Category 3 — `expect`'s own no-fix path is kept and marked.** See §5.

**Category 4 — the remainder.**

| error | fix clause | new information |
|---|---|---|
| `'add' takes 2 values, given 1` | `it is declared \`to add of a, b\`, so call it as \`add of a, b\`` | the parameter **names** and their order, and the call to write — a count leaves an author counting commas |
| `'sorted' takes 1 value, given 2` (foreign) | `it is declared \`foreign sorted of xs from "builtins.sorted"\`, so call it as \`sorted of xs\`` | the declaration, which for a foreign may be far from the call |
| `cannot take the whole part of text "5"` | `whole of rounds a number toward zero; Planes has no text-to-number builtin, so a number has to arrive as one — from a literal, from arithmetic, or from a field of something read as JSON` | that **no conversion exists** — the thing an author would otherwise search for |
| `expected an effect name after 'doing', found '5'` | `valid kinds: ask, clock, env, random, read, show, write — and 'nothing' after 'doing', for a foreign that performs none` | the whole closed vocabulary, and where `nothing` is allowed (not the same place) |
| `expected a value, found 'show'` | `a value starts with a number, a quoted string, true, false, nothing, a name, \`not\`, a list, a record, or a parenthesised expression — a statement word like \`show\` or \`write\` cannot stand in for one` | what can begin an expression, and why a statement word cannot |
| `expected a name, found '5'` | `a name here is one or more plain words — the old or the new spelling in a \`use ... with <old> as <new>\` rename; a quoted string, a number, or a punctuation mark cannot stand for one` | *which form you are in*. `read_multiword_name` is reached from exactly one place, so the clause names it rather than describing names in general |
| `field 'a' appears twice in this record` | `keep one of the two; to change a field's value later, build a new record from this one — \`r with a: value\`` | `with` — what an author writing the field twice was probably reaching for |

### The five restructured invariants and `ask-failed`

| error | fix clause | new information |
|---|---|---|
| `no operator is spelled '{op}'` | `the parser builds only the operators the language defines, so reaching this is a defect in the interpreter rather than in the program — worth reporting with the source` | that it is **not the author's fault** |
| `'{op}' is not an arithmetic operator` | `arithmetic is + - * /; reaching this means apply_op routed an operator here that it does not itself arithmetic on, which is a defect in the interpreter rather than in the program` | same, plus where the routing went wrong |
| `'Show' has no value — it is a statement, not an expression` | `write it on its own line; reaching this from a program the parser accepted is a defect in the interpreter, not in the program, and worth reporting with the source that produced it` | both the ordinary fix and the fallback |
| `no builtin is named 'frobnicate'` | `the ten builtins are fixed and the lexer recognises only those, so reaching this is a defect in the interpreter rather than in the program — worth reporting with the source` | that the set is closed |
| `asking 'x' failed: <host cause>` | `check the url is reachable and spelled right; a run without the network needs a stubbed response` | that an offline run is possible at all |

**Why these four invariants name a fix rather than being marked deliberate.**
They are unreachable from any program the parser accepts — every statement-only
construct is refused there as *expected a value*, verified directly. It would
have been easy to mark them "no fix, unreachable" and move on. But there *is* a
next move — report it — and telling an author the defect is not theirs is
exactly the thing they need. Marking them silent would withhold it. Asserted by
test.

### The eight new guards (§6) each name a fix too

`count of` a non-collection, `lower`/`upper`/`normalize` of a non-string, a
non-text `ask`/`read`/`write` target, `first n of`'s count and source, `in`'s two
operands, and a failed write. Every one is in the table in §6, and
`test_every_runtime_message_this_build_changed_names_a_fix` asserts the clause is
present on all fifteen runtime messages this build wrote or rewrote.

---

## 4. The generator's inclusion rule, stated

A.2 item 2 asked for the rule to be explicit rather than incidental. It now
lives at the top of `grammar_gen.py`, next to the class list it governs:

> An entry is an **error** iff it constructs one of the error classes the
> reference implementation defines. All seven are listed, and the listing is the
> rule — including a class is a decision with a reason, and so is leaving one
> out.
>
> An entry is a **report** iff it is text a plane renders for a person without
> raising anything: `rules.py`'s `Violation.render` and `_render_vacuous`. The
> catalogue inventories both, because both are text a person reads. The
> fix-clause commitment is measured over errors only — an error stops a program
> and leaves its author needing a next move; a report does not.

The seven: `PlanesError`, `PlanesSyntaxError`, `PlanesAmbiguity`,
`RuleConflict`, `RuleNotSupported`, `ModuleError`, `GrammarDataError`.

Three exception classes are deliberately outside it, each for a reason a reader
can check:

| class | why not an error of the language |
|---|---|
| `HostError` (`host.py`) | the machine failing, not the program being wrong. Every one is converted to a `PlanesError` before it can cross into a program — which is what constraint 6 asserts and `test_builtin_guards.py` checks by sweep |
| `Inexact` (`planes_num.py`) | the same: caught in `arith()` and re-raised as `needs-rounding`, so no program sees it |
| `_Give` (`interp.py`) | control flow for `give`, not a failure at all |

**Stating the rule found more than it settled.** `ModuleError` and
`GrammarDataError` had been outside the catalogue for no stated reason —
`planes.py` prints a `ModuleError` to the same stderr as everything else. That
is **nine raise sites the commitment was never measured over**, and four of them
held their fix clause in a local variable where the catalogue could not see it:

```python
fix = "reinstall planes, or regenerate with python3 grammar_gen.py"
...
raise GrammarDataError("grammar-data-missing", f"{path} is not valid JSON ({e})", fix)
```

Exactly A.1's pattern, at sites A.1 could not have named because they were not
in the catalogue to be counted. All nine now name a fix, with the clause written
out at each raise — the same discipline `parser.py`'s `expect` already kept, and
for the same reason.

The 5 rule-plane reports are listed in the report output and excluded from the
measurement. `RuleConflict` and `RuleNotSupported` stay *in*: those are
malformed **rules**, refused by raising, and an author is stuck on one.

---

## 5. The floor: deliberate silences, marked

Once deliberate no-fix entries exist, a raw percentage is misleading — so the
measurement distinguishes *has decided to name none* from *should name one and
does not*. Five sites are marked, each carrying its reason as a literal at the
raise site. There are exactly two shapes, and both are about **whose message it
is**.

| site | reason (as recorded in the catalogue) |
|---|---|
| `interp.py` `fail` | the message is the program's own, written at the `fail`; naming a fix here would overwrite what the author chose to say |
| `interp.py` `or fail`, caught Planes error | re-tags a message this raise did not write; the fix belongs to whoever raised it, and is carried forward |
| `interp.py` `or fail`, host exception ×2 | re-tags a host exception this raise did not write; a host failure is not something the language can advise on |
| `parser.py` `expect`, bare path | this is the generic token gate, reached from every form in the grammar; it knows which token was due and not what the author meant by writing another, so a call site that can say more passes `fix=` and a call site that cannot says nothing rather than guessing |

**The mechanism, and why it is not a hand-kept list.** `PlanesError` and
`PlanesSyntaxError` gained a `no_fix=` argument. It is never rendered, so every
message stays byte-identical across implementations; `grammar_gen.py` reads it
as a literal exactly as it reads the message. A reason held in a variable does
not count, by the same rule that governs a fix clause. The JavaScript
implementation carries the same argument at the same sites — nothing there reads
it, but a site marked deliberate in one implementation is marked in both.

A silence with no stated reason is **still shortfall**. That is asserted:
`classify()` checks `no_fix` last, so a stray annotation cannot hide a real fix
clause, and an unreadable entry with no reason lands in the work list.

---

## 6. The thirteen divergences, each closed — and the sweep past them

§0 step 7 confirmed all thirteen still diverged at this build's baseline, and
confirmed C1's characterisation of both families exactly. **The prompt's
second-hand description was accurate.**

### Family 1 — three cases

`count of` a number, a boolean, or nothing raised a bare Python `TypeError:
object of type 'Number' has no len()`. Now `not-a-collection` on both, with the
fix clause neither side had:

```
not-a-collection: cannot count 5
  try: count takes a list, a record, or text — check which of those this value should be
```

### Family 2 — ten cases

`lower`, `upper`, and `normalize` handed their argument to the host's own string
conversion. Now they refuse, naming `text of`:

```
not-text: cannot lowercase [2 items]
  try: lower takes text; convert first — e.g. lower of (text of n)
```

**A.6's ruling is made and not softened.** No corpus program relied on the
coercion — asserted directly by
`test_no_corpus_program_relied_on_the_coercion`, not read off a CI log. So there
is no finding about the corpus to report.

### The sibling sweep (Phase 3 item 3)

Thirteen was where the JSON work happened to look. The sweep is every builtin —
**all ten**, not the eight C1 exercised — against every value kind, plus every
other operation that reaches a host primitive, because **constraint 6 is not
limited to builtins**. 144 cases. It found five more families:

| what | before | now |
|---|---|---|
| `ask` a non-text url | py: `no stubbed response for 5` via `ask-failed`, or a bare `TypeError: unhashable type: 'list'`; js: **crashed node** | `not-text: a url to ask must be text, found 5` |
| `read` a non-text path | py: bare `TypeError`; js: `no-such-file` | `not-text: a path to read must be text, found [1 items]` |
| `write ... to` a non-text destination | py: `open(5, "w")` **opens file descriptor 5**; js: crashed node | `not-text: a destination to write to must be text, found {record}` |
| `first n of` a non-sequence, or a non-number count | host exception on **both** | `not-a-collection` / `not-a-number`, both naming the fix |
| `in` a non-collection, or a number in text | py: bare `TypeError`; js: `unknown-operator`, which named the wrong thing — `in` **is** an operator | `not-a-collection` / `not-text` |

A failed `write` also left the host's own `OSError` to escape; it is now
`write-failed`, converted at the same boundary `read` and `ask` already used.

### The sweep result, after

```
BUILTINS — all ten (60 cases):     diverging: 0    host exceptions: 0
OTHER OPERATIONS (84 cases):        diverging: 0    host exceptions: 0
```

And the fifteen runtime messages this build wrote or rewrote are **byte-identical
in both implementations**, asserted on the rendered text rather than the tag —
which required `js/cli.mjs run` to report the message alongside the tag, since a
tag is deliberately shared across many different messages.

---

## 7. What the design record settled about the three planes

`docs/error-messages.md`, written for a learner. Every message it shows is the
exact rendered text, verified by running the program that produces it.

On the voice question A.4 asks to establish: **they share a shape and should;
they do not share a stance and should not.**

| | headline | evidence | fix clause |
|---|---|---|---|
| error | one line: tag or line number | — | `\n  ` continuation |
| amber refusal | one line, names the line | the lettered readings | `try: ...` last |
| vacuous-rule report | one line, names the rule | the reason | last line |
| **violation report** | one line, names the rule | effect, declaration, derivation | **none** |

Three independently written planes converged on *one line saying what happened,
indented material showing the evidence, the fix last*. That convergence is the
argument for keeping the shape, and new text should follow it.

The stance is where they part, and the violation report shows why it must. It
names no fix — correctly, because a violated rule means two things the author
wrote disagree, and which one is wrong is a judgement only they can make. So it
spends its space on evidence instead. The rule the record states:

> If the reader is stuck, name the fix. If the reader has a decision to make,
> show the evidence and get out of the way.

Errors and amber refusals are the first kind. Rule violations are the second.
Vacuous-rule reports sit between and lean to the first — which is why they carry
a fix clause, and why holding a *violation* report to the same commitment was a
category error the catalogue made for four builds and passed.

The record also states what the catalogue is not: not documentation, not a
tutorial, not a gate. Both of the first two are owed separately.

**This closes P-Q14's design record.**

---

## 8. Findings — reported, not fixed

1. **`fmt` renders text without quotes, so several error details are ambiguous
   about the value's kind.** `whole of "5"` reported `cannot take the whole part
   of 5`, which reads as a number and is the one thing the message is about.
   Fixed at the **two** sites where a text value is a realistic wrong input and
   this build's own clause depended on it (`whole of`, and `first n of`'s count),
   via a `kinded()` helper that names text as text — the convention `rest of
   text "..."` and `in text "..."` already used. **Left at four:** `+`
   (`cannot combine 5 with 5 using +` when one side is text `"5"`), `round`,
   ordering comparison, and `arith`. All four are pre-existing, all four are
   realistic, and changing them is a detail-line change across two
   implementations with its own agreement to establish.

2. **The self-hosted interpreter already disagrees with the reference about
   this.** `grammar/interp.planes` renders those same details through
   `canonical-of-value`, which **quotes** text — so the Planes-written
   interpreter says `cannot combine "5" with 5 using +` where the reference says
   `cannot combine 5 with 5 using +`. The self-hosted suites compare error
   **tags**, not detail text, so this has never been asserted either way. The
   self-hosted answer is the better one. Converging the three implementations is
   a build of its own, and finding 1 is its first step.

3. **Catalogue ids are not stable when a tag gains a raise site.** The
   disambiguating suffix is assigned by source order, so adding the `first n of`
   count guard renamed `whole of`'s entry from `interp.not-a-number-3` to
   `-4`, and the pre-existing `for each` guard from `interp.not-a-collection` to
   `-2`. Nothing was lost — the tally script reports one entry "disappearing"
   for exactly this reason — but an id is not a durable handle, and two tests in
   this build pin ids that could move under the same rule.

4. **`foreign f of x from "m.f" doing frobnicate` parses.** `read_effect_word`
   accepts any `NAME`, and the `kind not in EFFECT_KINDS` check exists only on
   the rule path. So an unknown effect kind is refused in a `rule` and accepted
   in a `foreign`. Discovered while looking for a trigger for that message's new
   fix clause. Not a message defect, so not this build's.

---

## 9. Every file this build changed

Sixteen, plus this report.

| file | what |
|---|---|
| `interp.py` | `no_fix` on `PlanesError`; `require_text`, `require_target`, `membership`, `kinded`, `param_list`, `call_shape`; guards on `count`, the three text builtins, `ask`, `read`, `write`, `first n of`, `in`; fix clauses on both arity messages and `whole of`; five invariant messages made literal; `or fail` carries `e.fix` forward; four deliberate silences marked |
| `lexer.py` | `no_fix` on `PlanesSyntaxError`; three string-literal messages made structural; four `GrammarDataError` fix clauses inlined at their raise sites |
| `parser.py` | `expect`'s bare path marked deliberate; fix clauses on the effect-name, expected-a-value, expected-a-name, and duplicate-field messages; two `GrammarDataError` fix clauses inlined |
| `grammar/lexer.planes` | the same three string-literal messages, in the self-hosted lexer |
| `js/interp.mjs` | every `interp.py` change above, byte-identical in message text |
| `js/lexer.mjs` | `noFix` on `PlanesSyntaxError`; the three string-literal messages |
| `js/parser.mjs` | the four parser messages; `expect`'s deliberate marking |
| `js/cli.mjs` | `run` reports the rendered `message` alongside the tag, so runtime text identity is testable |
| `grammar_gen.py` | the inclusion rule and `ERROR_CLASSES` (five → seven); per-class argument layout; `kind` on every entry; `no_fix` read as a literal |
| `errors_coverage.py` | three states with a floor; the errors/reports split; `is_unreadable` as a figure; the report states the rule |
| `grammar/errors.json` | regenerated (97 → 114 entries, 87 distinct tags) |
| `grammar/rules.json` | regenerated (line-number shifts only) |
| `scripts/ci.sh` | the errors-coverage step's comment describes three states |
| `test_error_messages.py` | 10 → 28 tests: the three states, the inclusion rule, the deliberate markings, and one test per fix clause written |
| `test_builtin_guards.py` | **new**, 18 tests: the 144-case sweep, both families, the five sibling families, the fifteen runtime messages byte-identical, and the corpus assertion |
| `docs/error-messages.md` | **new** — P-Q14's design record |

Not changed, deliberately: `host.py` and every `js/host*.mjs` — the seam stays at
**eight** methods (A.7), verified by an empty diff. No `grammar/*.planes` other
than `lexer.planes`. No hand-edit of a generated artifact.

**Three commits, not six.** Phases 1–4 land as one because constraint 8 requires
CI clean at every commit, and the message work and the regenerated catalogue
cannot be separated without a red intermediate state: `grammar_gen.py --check`
fails the moment a message changes without regeneration. Phases 5 and 6 are their
own commits.

---

## 10. Verification

Every gate item, machine-checked.

| item | result |
|---|---|
| `scripts/ci.sh` green | **exit 0** — 989 oks across 52 suites, ruff clean, mypy 91 source files |
| counts 32 / 10 / 7 / 8 | `reserved words 32/32`, `builtins 10/10`, `effect kinds 7/7`; host surface diff empty |
| the unreadable bucket at zero | 9 → 0 as a *bucket*; 4 remain unreadable **as a figure** and each is a marked deliberate silence, never a pass. Every destination reported in §2 |
| every message change identical in both implementations | 15 runtime messages compared on rendered text; 3 lexer and 4 parser messages compared through `js/cli.mjs ast`; asserted by test |
| three-state counts reported, work-list number stated | 104 / 5 / **0** of 109 — printed by `errors_coverage.py` on every CI run |
| deliberate no-fix entries marked and distinguishable | 5, each with its reason in the catalogue and in the report output; `test_every_deliberate_silence_states_its_reason` |
| the inclusion rule stated explicitly | `grammar_gen.py`'s `ERROR_CLASSES` with its exclusions; `test_the_inclusion_rule_is_stated_and_the_reports_are_not_measured` asserts all seven are in and `HostError`/`Inexact`/`_Give` are out |
| no host exception reaching a Planes program | 144 swept cases, **0** — builtins and beyond |
| all thirteen divergences agreeing, plus siblings | **0 divergences** across the whole sweep; the five sibling families each closed and tested |
| the design record present, for a learner, closing P-Q14 | `docs/error-messages.md`, 301 lines |
| metacircular re-run; prior results holding | `test_js_metacircular.py` 4/4, `test_js_metacircular_shapes.py` 3/3, `grammar_gen.py --check` exit 0 on all three artifacts + JS node parity (32 nodes both sides) |
| the check reports and never fails | `errors_coverage.py` returns 0 by construction; `test_the_catalogue_check_reports_and_never_fails` |

**Is the fix-clause commitment now met?** **Yes, for the reference
implementation's catalogued errors** — every one of the 109 either names a fix or
states, at its raise site, why it names none. Two things it does *not* yet mean:

* **the self-hosted interpreter is not measured.** `grammar/interp.planes`
  raises through `fail ... as tag`, which the catalogue does not scan, so a
  Planes-written implementation's messages are outside the commitment as
  measured. Finding 2 shows they already differ from the reference's.
* **the fix clauses are not judged, only present.** §3 exists so they can be
  judged. A clause that carries new information can still be the wrong
  information, and only use will tell.

---

## 11. What this build disproved about this prompt

Never empty. Five items.

**1. §7's abandonment of enumeration held — and the enumeration that survived
elsewhere is what broke.** Five consecutive prompts shipped a constraint tighter
than the intent it served, most recently by enumerating scope. §7 dropped the
file whitelist and nothing went wrong: the build touched sixteen files, three of
them ones a whitelist would plausibly have omitted (`js/cli.mjs`, `scripts/ci.sh`,
and the self-hosted `grammar/lexer.planes`). **But
the pattern reappeared one level down, inside the code.** `grammar_gen.py`'s
`TARGET_EXCEPTIONS` was a five-element enumeration standing in for the concept
"an error class of this language", and it silently excluded two classes with nine
raise sites. §7 abandoned enumeration in the prompt; A.2 item 2 made this build
abandon it in the generator. The contradiction was not in the prompt this time —
it was in the artifact the prompt was measuring.

**2. A.2's category 2 is wrong about a number, and the error is inherited from
S8's own report.** A.2 says *"Two rules-report lines are informational rather
than errors."* There is **one** in the shortfall. The prompt's PROVENANCE says
§5 of `REPORT_WHY_SELF_HOSTED.md` was read directly and in full, and it was —
S8's sentence is *"three parser token expectations ... and two rules-report
lines"*, and the catalogue actually holds **four** parser token expectations and
**one** rules-report line. The two errors cancel, which is why the total of nine
looked right for four builds. Resolved toward §A's evident intent, which was
better than its arithmetic: the informational lines do not belong in an error
measurement, and applying that reasoning removed **five** rules-report entries,
four of which were being counted as *passes*. The correction that mattered was
the opposite sign from the one the prompt described.

**3. A.3's premise — "once deliberate no-fix entries exist, a raw percentage is
misleading" — is right, and understates it.** A raw percentage was misleading
*before* any deliberate entry existed, because the denominator was wrong: four
report lines were passing a commitment about errors. The floor A.3 asks for fixes
the numerator; the inclusion rule A.2 asks for fixes the denominator; and only
the second one changed the published figure.

**4. A.1's instrument does not fit four of the nine sites, and the ruling is
still right.** A.1 says restructure the raise site so the message is a literal.
Four sites cannot: they forward a message they did not write. The prompt's
framing — *"the readability of a message is a property of how it is written, not
of how hard a tool looks"* — turns out to have a sharper form the prompt did not
state: **readability is a property of whether the message is written there at
all.** That distinction is what made the marking mechanism obvious, and it is the
same distinction §5's two shapes rest on.

**5. Phase 3 item 3's sweep instruction was too narrow, by its own logic.** It
says *"check every builtin for the same two shapes"*. Constraint 6 says *"no host
exception escapes into a Planes program"*, unqualified. Sweeping only the ten
builtins would have left `first n of` crashing both implementations, `in` naming
the wrong thing, and `write [1] to 5` opening file descriptor 5 — three defects
worse than several of the thirteen the build was chartered to fix. The sweep was
extended to every operation that reaches a host primitive because the constraint
demanded it and the phase text did not. **Failure mode 7b ("only the thirteen
fixed") was correctly anticipated; the boundary it drew around the fix was not.**
