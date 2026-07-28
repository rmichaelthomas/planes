# Planes

**A general-purpose programming language that shows its work.**

Ask what a program can do to the outside world, and Planes computes the answer
without running it — every network call, file write and clock read, with its
destination. Ask where a value came from, and it traces back to the boundary it
entered through.

No other general-purpose language answers either question. Planes answers both,
and neither answer is trusted: three independent implementations must agree, and
one of them is written in Planes.

```
$ python3 planes.py -e 'x = 5; y = 3; z = x + y; why z'
8 from x (5) + y (3)

$ python3 shapes_cli.py hn.planes
effect surface of hn.planes

network:
  ask https://hacker-news.firebaseio.com/v0/item/{...}.json (computed)
  ask https://hacker-news.firebaseio.com/v0/topstories.json
file:
  write results.json
console:
  show found {...} (computed)
  show {...} (computed)
```

Not a single network call was made to produce that surface.

---

## Contents

| | |
|---|---|
| [Run it](#run-it) | the three implementations, and a browser |
| [Three implementations](#three-implementations) | what self-hosting buys, and what "they agree" means |
| [The vocabulary](#the-vocabulary) | 32 words, 11 builtins, 7 effect kinds |
| [The language](#the-language) | syntax, in one page |
| [Numbers are exact](#numbers-are-exact) | rationals, not floats |
| [Effect surface](#effect-surface) | what a program *can* do |
| [Why](#why) | where a value came from |
| [Rules](#rules) | governance as a plane over the surface |
| [Annotations](#annotations) | `because` and `note`, provably inert |
| [Errors name the fix](#errors-name-the-fix) | a commitment, counted |
| [Modules](#modules) | flat names, reported collisions |
| [Foreign functions](#foreign-functions) | the FFI, and why `doing` is a claim |
| [The host](#the-host) | seven methods, and nothing else |
| [Machine-readable surfaces](#machine-readable-surfaces) | the grammar as data |
| [Layout](#layout) | what is where |
| [The gate](#the-gate) | how it is checked |

---

## Run it

```bash
python3 planes.py ordinary.planes              # run a program
python3 planes.py money.planes --effects       # ...and log what it did
python3 planes.py hn.planes --why avg          # ...and explain a value

python3 shapes_cli.py hn.planes                # what it CAN do, without running
python3 shapes_cli.py hn.planes --json         # machine-readable
python3 shapes_cli.py --diff demo/v1.planes demo/v2.planes
python3 shapes_cli.py demo/rules/violation.planes --rules

node js/cli.mjs run ordinary.planes            # the JavaScript implementation
node js/cli.mjs meta run ordinary.planes       # ...running the SELF-HOSTED one
open index.html                                # run and analyse in a browser
open paint.html                                # ...or paint a program's `show` output onto a canvas

bash scripts/ci.sh                             # the gate
```

Both pages are also hosted, with no install: <https://rmichaelthomas.github.io/planes/> and
<https://rmichaelthomas.github.io/planes/paint.html>.

The gate needs `ruff` and `mypy`, which live in `./.venv`. It tells you so at
step one if they are missing.

---

## Three implementations

The same language, written three times. They are not ports of convenience —
they are the check.

| | written in | what it is |
|---|---|---|
| `interp.py` + `parser.py` + `lexer.py` | Python | the reference |
| `js/interp.mjs` + `js/parser.mjs` + `js/lexer.mjs` | JavaScript | a second host, independently written |
| `grammar/interp.planes` + `parser.planes` + `lexer.planes` + `json.planes` | **Planes** | the language, in itself |

The third one is the interesting one. `grammar/interp.planes` is a Planes
interpreter written in Planes; it runs on either of the other two.

```bash
$ node js/cli.mjs meta run ordinary.planes
```

That is Planes-in-Planes, running on JavaScript. No Python involved.

**What "they agree" means is measured, not asserted.** A sweep runs 348 value
shapes — every builtin and operator against every kind of value — through all
three and compares the tag, the detail text, and the fix clause of whatever
each refuses:

```
$ python3 planes.py -e 'x = "5" + 1'
error — cannot-combine: cannot combine "5" with 1 using +
  try: convert first — e.g. "total: " + text of n
```

All three produce that message, byte for byte. **0 divergences across 348
shapes.** Both the effect surface and the derivation graph are computed by the
JavaScript stack too, so neither guarantee depends on Python.

---

## The vocabulary

Closed, and asserted. The whole reserved surface is 43 names — 32 keywords plus
11 builtins — and both counts are pinned by the test suite, so adding a word is
a visible decision rather than a drift. For scale: Python has 35 keywords. The
small number here is not the vocabulary, it is [the host](#the-host) — seven
methods, which is what makes the effect surface computable at all.

**32 keywords** — only words the parser must see to know a statement's shape:

```
and  as    doing  each  else   fail  false  first
for  from  foreign give  if    in    let    not
nothing  of  or   places plus  round rule   show
to   true  use   when   where  why   with   write
```

**11 builtins** — ordinary functions, not keywords, called as `count of xs`:

```
ask  count  join  lower  normalize  read  rest  sine  text  upper  whole
```

`sine` takes **degrees** and is the only operation in the language that
returns an approximate value — see [Exact, and approximate](#exact-and-approximate).

**7 effect kinds** — the closed vocabulary a host can be asked for:

```
ask  clock  env  random  read  show  write
```

`clock`, `random` and `env` are *ambient*: they make a result depend on
something outside the program, so a function that reads the clock is not pure.

Everything else is an ordinary name. Builtins are shadowable, and the analyser
follows the shadow:

```
to word count of phrase:      # `count` used freely inside a name
  give 42

to read of source:            # shadows the builtin entirely
  give "no file is touched"
```

A shadowed `read` performs no file effect, and the surface says so. In a
language whose names read as prose, `count` and `text` and `read` are words
people reach for.

**Two call forms, deliberately different:**

- `f of x` binds tightly — `double of 5 + 1` is `(double of 5) + 1`
- `f x` takes the whole expression — `ask "https://" + text of n` is one call

Read them as "apply this to that one thing" versus "apply this to what
follows".

---

## The language

```
use http                          # declare a module before its effects work
use file

x = 5                             # binding; `let` optional
xs = [1, 2, 3]                    # lists
r = { name: "Ada", score: 450 }   # records
name = r.name                     # dot access
r2 = r with score: 500            # record update — a new record
ys = xs plus 4                    # list append — a new list

to add of a, b:                   # function definition
  give a + b                      # return

to fetch stories:                 # multi-word name, no arguments
  give first 30 of everything

r = add of 2, 3                   # call; `of` binds tightly
r = add(2, 3)                     # equivalent

ys = for each x in xs: x * 2                    # comprehension
zs = for each x in xs where x > 2: x            # with filter

if n > 50:                        # conditional
  show "big"
else:
  show "small"

when user is { role: "admin" }:   # match on a record's SHAPE
  give true
else:
  give false

when e is { path }:               # bind a field by name
  show text of (count of path)

count of xs                       # builtins
text of n
join of ["a", "b"]

body = ask "https://..."          # network round-trip, needs `use http`
  or fail as api-down             # rename any failure to a domain error

x = risky() or fail as e:         # ...or catch it, as an ordinary record
  show e.tag
  show e.detail
  show e.fix

fail "the order is empty" as empty-order          # raise one yourself
fail { message: "...", fix: "add a line" } as t   # ...naming the fix

write xs to "out.json"            # file write, needs `use file`

why total                         # derivation query
```

**A caught error is an ordinary record**, discriminated by shape rather than by
type: `{ tag, detail, fix, path }`. All four fields are always present, and
`nothing` when they do not apply — because a missing field is no match under
`when`, so an absent field would make `when e is { fix }:` silently skip every
error that names none.

---

## Numbers are exact

`0.1 + 0.2` is `0.3`. `1 / 3` is one third. `9007199254740993 * 2` is exact.

```
$ python3 planes.py money.planes
subtotal 59.97
tax      4.947525
total    64.917525
due      64.92
```

Numbers are exact rationals — not floats, not `Decimal`. The reason is `why`: a
derivation containing a silent rounding step answers a question about the
answer, not about the program. Floats round on almost every operation; Decimal
rounds on division. Exact rationals never round, so `why` reports arithmetic
that actually happened.

| | float | Planes |
|---|---|---|
| `0.1 + 0.2 == 0.3` | false | true |
| `round 2.675 to 2 places` | 2.67 | 2.68 |
| `1.1 * 3` | 3.3000000000000003 | 3.3 |
| `0.1 * 3` | 0.30000000000000004 | 0.3 |

**Approximation is visible.** A value with no finite decimal form prints with a
leading `~`: `1 / 3` shows as `~0.333333333333`. It is still exact internally —
`(1 / 3) * 3` is exactly `1` — the marker only says the *text* is an
approximation.

**Rounding is a named operation**, so it appears in the derivation:

```
due = 64.92
  round to 2 places = 64.92
    total = 64.917525
      + = 64.917525
        subtotal = 59.97
        tax = 4.947525
```

**Foreign numbers become exact at the boundary.** A JSON `0.1` is one tenth from
then on, so arithmetic on fetched data is as exact as on literals.

**The cost is bounded, not hidden.** Adding many fractions with unrelated
denominators grows the denominator. Summing 2000 distinct fractions takes about
10 ms; past the bound an operation is *refused* rather than silently rounded,
because a refusal is visible and a rounding is not.

---

## Effect surface

`shapes.py` computes what a program **can** do, without running it. The runtime
effect log records what one run **did**. The two must agree, and that agreement
is enforced as an oracle over every example program in the repo — which is the
one check that can catch an unsound analyser.

The upgrade diff is the case it exists for. It exits 1, so it works as a CI
gate:

```
$ python3 shapes_cli.py --diff demo/v1.planes demo/v2.planes
demo/v1.planes -> demo/v2.planes
NEW BOUNDARIES CROSSED: network
  + network: ask https://telemetry.example.com/collect?data=['debug', 'verbose']
  + network: ask https://telemetry.example.com/collect?data={...} (computed)
```

Two things worth knowing about how it works.

**Effects propagate through the call graph by fixed point**, not by a tree walk,
so a caller inherits everything its callees do, transitively, and mutual
recursion terminates.

**A library is not pure just because nothing runs at load time.** `effects` is
what running the file performs; `declared` is what any function in it can do if
called. Package queries read `declared` — otherwise a library whose only network
call sits one function deep would be indexed as harmless.

### Constant propagation

Effect targets resolve through variables, concatenation, and call arguments, so
the host stays visible instead of collapsing to `{...}`:

```
let base = "https://api.example.com"
let endpoint = base + "/users"
x = ask endpoint          →  ask https://api.example.com/users
```

Widening to unknown is always sound — it costs precision, never correctness.
Names assigned inside a branch or loop widen at the join, and recursive
functions are never specialised, because binding `n = 3` at a call to
`countdown of 3` would report `show 3` and miss 2, 1, 0.

---

## Why

Provenance is carried on values via a `Deriv` node, never in a type or a
signature. `apply_op` has no idea derivation exists — results are wrapped after
the fact. That is the architectural difference from label-propagation schemes:
nothing spreads into the signature of `+`.

```
why z            → 8 from x (5) + y (3)
why result       → 5 from add(2, 3) = a (2) + b (3)
why bumped       → 500 from s ({record}).score + 50
```

Full transitive tree, back to where each value entered the program:

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

`origins(value)` returns just the boundary crossings a value depends on. Both
`why` and `origins` are implemented in all three stacks, including the
self-hosted one.

---

## Rules

Governance is a plane over the effect surface, not a feature bolted into the
runtime. A rule names itself, names a subject, and forbids or permits an effect:

```
rule [readings-stay-local] anything may not ask to "https://metrics.internal/ingest"
```

Checked statically, against the computed surface, exiting 1 on a violation:

```
$ python3 shapes_cli.py demo/rules/violation.planes --rules
[readings-stay-local] violated at line 9.
  ask https://metrics.internal/ingest
  rule declared at line 1: anything may not ask to "https://metrics.internal/ingest"
```

Rules can permit as well as forbid, can name a narrower subject than
`anything`, and can supersede one another by name and fingerprint — so a
later rule that loosens an earlier one has to say which one, and the pair is
reported rather than resolved by declaration order. A rule that could never
fire is reported as vacuous rather than passing silently.

---

## Annotations

Two forms carry human reasons into the program without changing what it does:

```
cap = 200 because "board policy, ratified March"

note:
  from "GDPR Article 17"
  derives-from [refund-cap]
```

`because` attaches to a binding and surfaces in `why`:

```
$ python3 planes.py annotated.planes
200 from 200
  because "board policy, ratified March"
refund 150 approved: true
```

**Inertness is a guarantee, not a convention.** Stripping every annotation from
a program must not change its output, its effect log, or its computed surface —
and that is asserted over every `.planes` file in the repo, not over a sample.
`why` output is allowed to differ, because that is the point of writing one.

---

## Errors name the fix

A message that reports a mismatch without saying what to write instead leaves
its author — human or machine — with a true statement and no next move. So
every error names its fix, and that is counted rather than asserted:

```
$ python3 errors_coverage.py
  names a fix                  106 of 111  (95%)
  deliberately names none        5 of 111  (5%)
  should name one and does not   0 of 111  (0%)

  113 raise sites across interp.planes, parser.planes, lexer.planes, json.planes:
  names a fix                   73 of 113  (65%)
  deliberately names none       40 of 113  (35%)
  should name one and does not   0 of 113  (0%)
```

**Both work lists are zero** — the commitment is kept in the reference
implementation and in the self-hosted one.

The middle state is the load-bearing one. A site that names no fix must say
*why* at the raise site, in words: the parser's generic token gate knows which
token was due and not what the author meant, and `fail`'s own message belongs to
whoever wrote it, so the language must not attach its advice to a sentence it
did not write. A silence without a stated reason counts as a gap.

`errors_coverage.py` reports and never fails the build — an honest one-line
error should not be un-committable. The design record is
[`docs/error-messages.md`](docs/error-messages.md).

---

## Modules

`use http` and `use file` name builtin capability modules. `use config` names a
file, `config.planes`, resolved relative to the importer.

A package's effect surface includes the surface of everything it imports:

```
$ python3 shapes_cli.py demo/app/main.planes --no-follow
file:
  write out.json
unresolved calls: package
```

`main.planes` contains no network code — the `ask` is in `net.planes` and the
base URL in `config.planes`. Following imports finds it and resolves the exact
URL across all three files. Not following says so, rather than reporting a clean
surface it cannot vouch for.

**Names are flat across a module graph, and collisions are errors.** `api base`
is called as `api base`, not `config.api base`, because multi-word names already
read as prose. Flat names make a collision genuinely ambiguous, so it is
reported:

```
module error — two modules define the same name:
  'load record' is defined in cache.planes, loader.planes
  try: rename one of them — names are flat across modules,
       so 'load record' has to mean one thing
```

One of those reads a file and the other hits the network. Letting load order
decide would mean the same program behaved differently depending on the order of
its `use` lines, with nothing to read that explained why.

**A collision is fixed at the point of use**, because a consumer of two colliding
modules usually cannot edit either one:

```
use loader
use cache with load record as load cached

fresh = load record of "requests"     # loader's, over the network
old   = load cached of "requests"     # cache's, from a file
```

The rename *replaces* the exported name rather than adding an alias —
registering both would put the collision straight back.

---

## Foreign functions

A function implemented in the host declares what it does. Planes cannot see
inside the host, so it never guesses:

```
foreign sort of xs from "builtins.sorted" doing nothing
foreign now      from "time.time"         doing clock
foreign grab of u from "x.y"              doing ask, clock
```

**A declared effect can name where it goes**, either as a fixed destination or as
a parameter the caller supplies:

```
foreign send of x    from "m.post"    doing ask "https://api.example.com"
foreign fetch of url from "u.urlopen" doing ask url
```

The parameter form is the valuable one: at a call site with a known argument,
constant propagation resolves the real destination, so a host name survives a
foreign boundary — which is what makes the diff meaningful across FFI.

The `doing` clause is a **claim by whoever wrote the line**, not a fact the
analyser derived, and the surface says so:

```
ambient:
  clock time.time (declared, not verified)
```

**Omitting `doing` does not mean pure.** It means unknown, and the surface
reports the hole rather than hiding it:

```
foreign:
  unknown — m.f declares no effects
this surface is incomplete: a foreign function states no effects
```

That default is the whole safety property. Deriving effects from the host is
impossible in general — it would mean analysing CPython, then a C extension —
and the failure would be silent: an analyser that cannot see inside would report
"pure", publishing a guess as a fact.

---

## The host

Planes runs on a **host**: whatever actually performs an effect. A host is
**7 methods**, and that is the entire requirement the language places on a
machine.

| method | for |
|---|---|
| `ask` | a network round-trip |
| `read` | read a file |
| `write` | write a file |
| `show` | emit a line |
| `clock` | the time |
| `resolve` | find a foreign function |
| `parse_json` | parse JSON text |

It is small because the effect vocabulary is closed: a host cannot be asked for
more than the language can name. Every one of the seven has a live caller —
checked mechanically, so a method that stops being used becomes visible instead
of becoming dead surface a second host would have to implement for nothing.

```python
from host import TestHost
from interp import Interpreter

host = TestHost(responses={"https://x/y.json": '{"n": 1}'})
i = Interpreter(host=host)
i.run('use http\nr = ask "https://x/y.json"\nshow text of r.n')
```

A foreign target is **opaque to the language** — the parser stores it as a
string and the analyser never reads it — so `node:fs#readFile` and
`crate::mod::fn` parse and analyse today. Changing hosts needs no language
change, which is how the JavaScript implementation exists at all.

---

## Machine-readable surfaces

The language describes itself as data, generated from the implementation rather
than hand-kept, so a tool never has to parse prose to learn the vocabulary.

| file | what it holds |
|---|---|
| `grammar/vocabulary.json` | keywords, builtins, effect kinds, token classes |
| `grammar/errors.json` | every error site: tag, class, template, slots, fix |
| `grammar/rules.json` | every rule form the parser accepts |
| `grammar/core.json` | the subset a self-hosting implementation may use |

```json
{
  "id": "interp.cannot-compare.equal-4",
  "kind": "error",
  "class": "PlanesError",
  "tag": "cannot-compare",
  "source": "interp.py:119",
  "raised_in": "equal",
  "template": "records have different fields: {sorted(set(a) ^ set(b))}",
  "slots": ["sorted(set(a) ^ set(b))"],
  "fix": "compare records with the same fields"
}
```

`grammar_gen.py --check` fails the build if any of these drifts from the code it
describes. `shapes_cli.py --json` emits an effect surface in the same spirit.

---

## Layout

An orientation, not an inventory. For the complete list, ask the repo:
`git ls-files`.

| | |
|---|---|
| `lexer.py` `parser.py` `interp.py` | the reference implementation |
| `planes_num.py` `planes_text.py` | exact rationals; text as code points |
| `shapes.py` | the static effect analyser |
| `rules.py` | the rule plane, checked against a surface |
| `render.py` | the canonical printer — parse, render, reparse, agree |
| `modules.py` `host.py` | module graph; the host seam |
| `planes.py` `shapes_cli.py` | the two CLIs |
| `js/` | the JavaScript implementation, plus Node and browser hosts |
| `index.html` | run and analyse Planes in a browser, no build step |
| `paint.html` | run a Planes program and paint its `show` output onto a canvas |
| `grammar/*.planes` | **Planes, written in Planes** — lexer, parser, interpreter, JSON |
| `grammar/*.json` | the machine-readable surfaces above |
| `corpus/` | the canonical corpus — every construct, as programs |
| `demo/` | small programs for the diff, index, rules and module demos |
| `identity/` | the visual identity — marks, lockups, social card, all generated by `render_logo.py` |
| `scripts/ci.sh` | the gate |
| `docs/` | design records |
| `reports/` | one `REPORT_*.md` per build, including what each disproved |

---

## The gate

```bash
$ bash scripts/ci.sh
== suites: 56 files, 56 reporting, 1124 oks, 10 job(s), 45.6s wall ==
```

It runs the suites, the JavaScript tests, the locked-construct audit, the
grammar-data check, the core-subset check for every self-hosted file, the
coverage reports, `ruff` and `mypy`. `scripts/ci.sh --fast` skips the twelve slowest
suites for iteration and is **not** the gate — it skips the
cross-implementation agreement, which is the thing worth checking.

Two habits it enforces, both learned the hard way:

**A test file that reports no result fails the build.** Five times in this
repo's history something existed, passed, and was never executed — two suites
with no runner, 47 JavaScript tests nobody ran, and seven verification scripts
of which two had gone quietly wrong. A warning depends on somebody reading it.

**Every test-shaped file is counted against what the gate runs.** The check
reads the glob out of `ci.sh` rather than restating it, so the two cannot drift
apart silently.

---

## Status

Working, and checked. Nothing here is a specification — the implementation is
the specification, and `grammar/*.json` is its machine-readable projection. The
`reports/REPORT_*.md` files are the build record; each one ends with what that
build disproved about its own plan, which is usually the most useful part.

---

## License

[Apache License 2.0](LICENSE) — Copyright 2026 R. Michael Thomas.

`identity/render_logo.py` embeds the outlines of the word "Planes" set in
[Red Hat Display](https://github.com/google/fonts/tree/main/ofl/redhatdisplay),
© 2019 Red Hat, Inc., under the SIL Open Font License 1.1. No font file is
redistributed here. See [NOTICE](NOTICE).
