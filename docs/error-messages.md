# What an error message is, in Planes

This is the design record for the error catalogue — the account P-Q14 has owed
since `grammar/errors.json` shipped without one at #9. It is written for
someone learning the language, not for a tool consuming the artifact. If you
want the artifact, it is `grammar/errors.json` and it is generated; if you want
the count, run `python3 errors_coverage.py`. This is the *why*.

---

## 1. What a message owes you

Planes commits to one thing about its errors, and it has since `unbound` v1.1
§22: **an error names the fix.** Not "an error is clear". Not "an error is
polite". It names, in the message, what to write instead.

The commitment exists because of who reads these messages. Planes is built to
be written by machines as much as by people, and a machine given a true
statement and no next move is stuck in a way a person is not — a person can
guess, look things up, ask someone. So the message has to carry the next move
itself.

Two messages taught this the hard way. Both came from writing the canonical
corpus (#25) — real programs, written by hand, hitting real refusals:

```
x = { k: f of a, k2: 9 }   ->  line 1: expected }, found ':'
let rule = 1               ->  line 1: expected name, found 'rule'
```

Both are **true**. Neither helps. The first one is worse than unhelpful: the
parser is right and its report is a red herring. `f of a, k2: 9` is a
multi-argument call — the call swallowed the rest of the list, so by the time
the parser reached `:` it had long since gone wrong, and `expected }` describes
the symptom at a place the author never wrote anything strange. The second is
about the reserved surface: `rule` is one of the 32 keywords, and no amount of
staring at `let rule = 1` reveals that unless you already know the list.

What they got:

```
line 1: expected }, found ':'
  a record is `{ name: value, ... }`; a call or `with` used as a field value takes the rest of the list, so parenthesise it: `{ k: (f of a, b), k2: 9 }`

line 1: 'rule' is a keyword, so it cannot be used as a name
  keyword names are reserved like builtins; pick another name
```

Note what changed. Neither *detail line* moved much. What arrived was a second
line that carries information the first line does not have — the shape of a
record, the existence of a reserved list. That is the test a fix clause has to
pass, and it is the only real test:

> **A fix clause must carry information the error does not.** "Expected a
> number, found text — provide a number" passes a mechanical check and helps
> nobody. It is the error, said twice.

Some worked examples of the difference:

| the error | a clause that restates | the clause that helps |
|---|---|---|
| `cannot count 5` | *count needs a collection* | `count takes a list, a record, or text — check which of those this value should be` |
| `cannot take the whole part of "5"` | *whole of needs a number* | `whole of rounds a number to the nearest whole, half away from zero; if this is text, convert it first with number of — a boolean, a list, a record, or nothing has no path to becoming a number` |
| `'add' takes 2 values, given 1` | *pass 2 values* | `it is declared \`to add of a, b\`, so call it as \`add of a, b\`` |
| `field 'a' appears twice in this record` | *remove the duplicate* | `keep one of the two; to change a field's value later, build a new record from this one — \`r with a: value\`` |

The right-hand column names the three kinds count accepts, the *absence* of a
conversion builtin, the declared parameter names, and the `with` form. None of
those are in the error. All four are the next move.

### The second lesson: a message is part of the language

The other body of evidence is thirteen cases where the two implementations
disagreed about what to say (found in C1, closed in C2). `lower of [1, 2]`
answered `'[1, 2]'` when the program ran on the Python reference and `'1,2'`
when it ran on the JavaScript host. `count of 5` raised a Python `TypeError`
on one and a Planes `not-a-collection` on the other.

There turned out to be a third implementation to disagree with. `grammar/
interp.planes` — Planes interpreting Planes — was rendering its details through
`canonical-of-value`, its own *test-oracle* form, so it differed from both
others on nearly every detail while its test suite stayed green: those suites
compared error **tags**, and a tag is deliberately shared across many messages.
All three now agree on tag and detail across 348 shapes, and that agreement is
asserted rather than assumed. The lesson is the same one, one turn sharper: if
what a message *says* is part of the language, then a test that only checks the
tag is not checking the language.

That is the sharpest available illustration of the principle: **a message is
part of the language, not an artifact of whichever host ran the program.** The
same program has to say the same thing. In ten of the thirteen cases the answer
was not merely inconsistent but wrong on both sides — each implementation was
handing a Planes value to its own host's string conversion, so the answer
depended on CPython's `str()` versus V8's `String()`. Neither could be called
the specification.

The ruling that closed them is the one the rest of the language already
followed: **refuse, and name the explicit conversion.** `+` does not coerce.
Ordering across types errors and names both operands. `join` refuses a non-text
element. `text of` exists. Implicit coercion bought nothing and cost the
property that a value's type is never silently changed — and it made the answer
depend on the host, which is worse than either option.

---

## 2. The shape

A message has at most three parts — a tag, a detail line, and a fix clause —
and only the first line is mandatory.

```
<what went wrong, on one line>
  <the fix clause, on its own line, indented two spaces>
```

For a runtime error the first line is `tag: detail`, where the tag is the short
hyphenated name a program can catch:

```
not-a-collection: cannot count 5
  try: count takes a list, a record, or text — check which of those this value should be
```

For a parse error the first line begins with the source line number, because
there is no program state to name yet:

```
line 1: field 'a' appears twice in this record
  keep one of the two; to change a field's value later, build a new record from this one — `r with a: value`
```

Three things about this shape are load-bearing:

**The tag is a name, not a sentence.** `not-a-collection`, `wrong-arity`,
`divided-by-zero`. It is what `or fail as e` binds and what `e.tag` reads, so it
is part of the program's interface and not just prose. Two errors that are the
same kind of wrong share a tag even when their details differ.

**The detail line stays one line.** Everything after the first newline is the
fix. That is not a style preference — it is how the catalogue tells one from
the other without parsing English.

**The fix clause is a field, not a sentence buried in the detail.** Three lexer
messages used to name their fix in prose after a `--`, mid-sentence. The
information was there and a reader could find it; a tool could not, and the
catalogue counted them as naming nothing. They now say the same thing on a
continuation line. Nothing was added — it moved.

### How a value is written in a detail

One rule, and all three implementations follow it: **write the value as the
language would write it when writing it is bounded, and name its shape when it
is not.**

```
cannot combine "5" with 1 using +          text, as a quoted literal
cannot take the whole part of true         a boolean, a number, nothing: the literal
cannot round [2 items]                     a list: its shape
cannot read .a from {record}               a record: its shape
```

Text gets quotes because the plain display form does not have them — it is what
`show` prints — so `whole of "5"` used to report `cannot take the whole part of
5`, which reads as a number and is the one thing the message is about. Planes
has one string syntax, so the quotes settle it.

A list and a record get their *shape*, not their contents, and this is the part
worth knowing: an error detail has to be **bounded**. A message that rendered a
10,000-item list in full would be unreadable, and one that rendered
`{ token: "hunter2" }` in full would put a credential into stderr and into
whatever collects stderr. So a detail names how many and what kind, and if you
need the contents, `why` on the name will show you where the value came from.

Where a message crosses an `or fail`, the fix clause travels with it. An error
that named a fix does not stop naming one because the author renamed it.

---

## 3. When a message deliberately names none

Some messages should not name a fix, and pretending otherwise would make them
worse. Five sites in the reference are marked as deliberate silences, each
carrying a written reason at the raise site itself. There are exactly two
shapes, and both are about **whose message it is**.

**The message is not the language's.** `fail "the invoice is empty" as
no-lines` raises the author's own text. The language has no idea what the fix
is — the author does, and they either wrote it or chose not to. Appending advice
here would overwrite what the author chose to say. The same holds for the three
places `or fail as e` re-tags something: a caught Planes error, or a host
exception a `foreign` call raised. Those messages belong to whoever raised them,
and the language forwards them (with their fix clause) rather than
editorialising.

**The gate is too generic to know.** The parser has one place that checks
"is the next token the one I expected" — `expect` — and every form in the
grammar goes through it. It knows a `}` was due and a `:` arrived. It cannot
know what the author *meant*, because the answer depends entirely on which form
called it. So the sites that can say more pass a fix clause in (the record
close passes the greedy-tail diagnosis), and the generic path says nothing
rather than guessing.

Compare this with the four *interpreter invariants* — `cannot-evaluate`,
`unknown-builtin`, and `unknown-operator` twice — which are unreachable from any
program the parser accepts. Those are not deliberate silences. They name a fix,
and the fix is *report it*:

```
unknown-builtin: no builtin is named 'frobnicate'
  try: the ten builtins are fixed and the lexer recognises only those, so reaching this is a defect in the interpreter rather than in the program — worth reporting with the source
```

Telling you the failure is not your fault is a next move. Marking these as
"no fix" would withhold exactly the thing you need to know.

### One place the commitment is not available at all

`grammar/interp.planes` — Planes interpreting Planes — cannot name a fix
anywhere, and the reason is in the language rather than in the file. A program
raises with `fail <message> as <tag>`, which has one slot for text, and the
error record a program catches with `or fail as e` carries `e.tag` and
`e.detail` and nothing else. There is no third field to put a fix clause in, so
the self-hosted interpreter says what went wrong and never what to do about it.

The three implementations agree on every tag and every detail — that is
asserted, over 348 shapes. They cannot agree on fix clauses, because two of them
have them and one has no way to.

Closing it means either a two-part `fail` and a third field on the error record —
a language addition, and this chain does not make those without a ruling — or
accepting that a Planes-written interpreter answers the first question and not
the second. Naming it is not the same as closing it, and it is named here
because a learner reading `grammar/interp.planes` should not conclude the
commitment was forgotten there.

A deliberate silence is **marked**, never merely absent. The reason is a
literal at the raise site, read into the catalogue the same way the message is,
and printed in the report next to the site. That distinction is what keeps the
measurement honest as it approaches its floor: without it, "12 messages name no
fix" and "12 messages have decided not to" are the same number, and only one of
them is work.

---

## 4. Three planes that write to you, and whether they share a voice

Planes emits text to a person from three places. They are not the same kind of
thing, and the difference is worth knowing before you read one.

**Errors** — the catalogue's subject. A program stopped. Something is wrong
*now*, and you have to change something to get past it.

**Amber's refusals** — the parser found more than one reading of your source
and will not choose. Nothing is wrong with what you wrote in the sense that a
typo is wrong; it is *ambiguous*, and the remedy is to say which you meant:

```
line 5: two readings are possible here, and nothing says which

  reading A:  total  then  items
              the value `total`, then whatever parses next on its own
  reading B:  total items
              one call to `total items`

both `total` and `total items` are defined, so the parser will not choose between them
try: parenthesise the one you mean -- `(total items)` -- or rename one of the functions so only one reading is possible
```

**The rule plane's reports** — a `rule` you declared was checked against the
program's static effect surface. This is not a refusal at all; it is a finding,
and there are three outcomes: violated, excepted, or checked nothing.

```
[no-audit-writes] violated at line 4.
  write audit.log
  rule declared at line 2: anything may not write to "audit.log"
```

A rule with a named subject adds a `derived from:` line naming the values the
effect's target came from, and a rule narrowed by another adds a
`narrowed here by` line. Evidence, all of it — no fix clause anywhere.

**Do they share a voice?** They share a *shape*, and they should — and they
already do, without anyone having designed it that way:

| | headline | evidence | fix clause |
|---|---|---|---|
| error | one line: tag or line number | — | `\n  ` continuation |
| amber refusal | one line, names the line | the lettered readings | `try: ...` last |
| vacuous-rule report | one line, names the rule | the reason | last line |
| violation report | one line, names the rule | effect, declaration, derivation | **none** |

One line that says what happened, indented material that shows the evidence,
and the fix last. Converging on that from three independently written planes is
a sign it is the right shape, and new text should follow it.

What they should **not** share is the *stance*, and the violation report shows
why. It names no fix — and that is correct, because there isn't one the language
can give. A violated rule means two things you wrote disagree: the rule and the
program. Which one is wrong is a judgement only you can make. So the report
spends its space on **evidence** instead — which effect, declared where, derived
from what — and stops. That is the shape of a message whose job is to inform a
decision rather than unblock a step.

The rule of thumb:

> If the reader is stuck, name the fix. If the reader has a decision to make,
> show the evidence and get out of the way.

Errors and amber refusals are the first kind. Rule violations are the second.
Vacuous-rule reports sit in between and lean toward the first, which is why
they carry a fix clause: a rule that checked nothing is almost always a mistake
in the rule, and the report says so.

This is also why the catalogue measures errors and merely *lists* the rule-plane
reports. Holding a violation report to the fix-clause commitment would be
holding it to a commitment about a different kind of text. (For four builds it
was held to exactly that, and passed — which inflated the count by four and is
the reason the inclusion rule is now written down.)

---

## 5. What this is not

**The catalogue is not documentation.** It is an inventory of every place the
implementation refuses, generated from the raise sites. Reading it end to end
tells you what can go wrong; it does not tell you how the language works, and
it is not organised for a reader — it is organised by source file and line.

**The catalogue is not a tutorial.** Nothing in it teaches you Planes. A fix
clause assumes you already know what a record is; it just reminds you of the
syntax at the moment you got it wrong.

Both of those are owed, separately, and neither is this. What this document is,
and all it is: the account of what a message in this language is for, what
shape it takes, and why some of them stop short on purpose.

**The catalogue is also not a gate.** `errors_coverage.py` reports and never
fails. A message with no fix clause is work to schedule, not a build to break —
and the first person to add an honest one-line error should not have to write
prose before they can commit. The number that matters is the one that is a work
list, and its target is zero.

---

## Where to look

| you want | look at |
|---|---|
| every catalogued site | `grammar/errors.json` (generated — do not hand-edit) |
| how a value is written in a detail | `detail_value` in `interp.py`, `detailValue` in `js/interp.mjs`, `detail-of-value` in `grammar/interp.planes` |
| whether the three agree | `test_builtin_guards.py`, the three-way sweep |
| the current count, in three states | `python3 errors_coverage.py` |
| what makes an entry an error | the inclusion rule at the top of `grammar_gen.py` |
| amber's refusal text | `grammar/messages/amber.json` (data, not inline prose) |
| the rule plane's reports | `rules.py`'s `Violation.render` |
| the two messages that started this | `test_error_messages.py`, sections 1 and 2 |
| the thirteen host divergences | `test_builtin_guards.py` |
