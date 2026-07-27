# Planes — substrate prototype

A working parser, evaluator, and provenance tracker for Planes. No design
documents. Governance, rules, and precedence are parked.

## Run it

```
python3 planes.py -e 'x = 5; y = 3; z = x + y; why z'
# 8 from x (5) + y (3)

python3 planes.py ordinary.planes --effects --why avg
python3 planes.py pypi.planes --effects          # live network
python3 test_planes.py                            # 45 tests
```

## Names

29 reserved words, and only words the parser must see to know the shape of a
statement:

```
to give let use show write why
if else for each in where
and or not of as fail with
true false nothing
first round places
foreign from doing
```

Everything else is an ordinary name. `count`, `text`, `lower`, `upper`,
`whole`, `ask`, and `read` are **builtin functions**, not keywords — called
as `count of xs`, exactly like a user's own `detail of id`, and shadowable:

```
to word count of phrase:      # `count` used freely in a name
  give 42

to read of source:            # shadows the builtin entirely
  give "no file is touched"
```

A shadowed `read` performs no file effect, and the analyser says so. In a
language whose names read as prose, `count` and `text` and `read` are words
people reach for.

**Two call forms, deliberately different:**

- `f of x` binds tightly — `double of 5 + 1` is `(double of 5) + 1`
- `f x` takes the whole expression — `ask "https://" + text of n` is one call

Read them as "apply this to that one thing" versus "apply this to what
follows".

## The host

Planes runs on a **host**: whatever actually performs an effect. A host is
five capabilities — `ask`, `read`, `write`, `show`, `clock` — plus a
resolver for foreign names and a JSON codec. That is the entire requirement
the language places on a machine.

It is small because the effect vocabulary is closed: a host cannot be asked
for more than the language can name.

```python
from host import TestHost
from interp import Interpreter

host = TestHost(responses={"https://x/y.json": '{"n": 1}'})
i = Interpreter(host=host)
i.run('use http\nr = ask "https://x/y.json"\nshow text of r.n')
```

The default host is Python. A foreign target is **opaque to the language** —
the parser stores it as a string and the analyser never reads it — so
`node:fs#readFile` and `crate::mod::fn` parse and analyse today. Changing
hosts needs no language change.

## Foreign functions

A function implemented in the host declares what it does. Planes cannot see
inside the host, so it never guesses:

```
foreign sort of xs from "builtins.sorted" doing nothing
foreign now      from "time.time"         doing clock
foreign grab of u from "x.y"              doing ask, clock
```

**A declared effect can name where it goes**, either as a fixed destination
or as a parameter the caller supplies:

```
foreign send of x    from "m.post" doing ask "https://api.example.com"
foreign fetch of url from "u.urlopen" doing ask url
```

The parameter form is the valuable one: at a call site with a known
argument, constant propagation resolves the real destination, so a host name
survives a foreign boundary.

```
r = fetch of "https://pypi.org/pypi/requests/json"
→  ask https://pypi.org/pypi/requests/json (declared, not verified)
```

This is what makes the diff meaningful across FFI. Two versions with
identical Planes code and identical effect kinds, differing only in a
foreign declaration's destination:

```
$ shapes_cli.py --diff demo/fdiff/v1.planes demo/fdiff/v2.planes
NEW DESTINATIONS: https://collect.tracking.io/beacon
  + network: ask https://collect.tracking.io/beacon (declared, not verified)
  - network: ask https://api.example.com/events (declared, not verified)
```

Exit code 1, so a new destination fails a build the same as a new boundary.

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
impossible in general — it would mean analysing CPython, then a C extension
— and the failure would be silent: an analyser that cannot see inside would
report "pure", publishing a guess as a fact.

A foreign boundary is a place values enter the program, so `why` traces
through it:

```
spread = 37
  top = 41
    biggest = 41   <- entered at foreign:builtins.max
```

Effect kinds: `ask`, `read`, `write`, `show`, `clock`, `random`, `env`. The
last three are *ambient* — they make a result depend on something outside
the program, so a function that reads the clock is not pure.

## Numbers are exact

`0.1 + 0.2` is `0.3`. `1 / 3` is one third. `9007199254740993 * 2` is exact.

```
$ python3 planes.py money.planes
subtotal 59.97
tax      4.947525
total    64.917525
due      64.92
```

Numbers are exact rationals, not floats and not Decimal. The reason is Why:
a derivation containing a silent rounding step answers a question about the
answer, not about the program. Floats round on almost every operation;
Decimal rounds on division. Exact rationals never round, so `why` reports
arithmetic that actually happened.

Four cases where IEEE floats give a different answer:

| | float | Planes |
|---|---|---|
| `0.1 + 0.2 == 0.3` | false | true |
| `round 2.675 to 2 places` | 2.67 | 2.68 |
| `1.1 * 3` | 3.3000000000000003 | 3.3 |
| `0.1 * 3` | 0.30000000000000004 | 0.3 |

**Approximation is visible.** A value with no finite decimal form prints with
a leading `~`: `1 / 3` shows as `~0.333333333333`. It is still exact
internally — `(1 / 3) * 3` is exactly `1` — the marker only says the *text*
is an approximation.

**Rounding is a named operation**, so it appears in the derivation:

```
due = 64.92
  round to 2 places = 64.92
    total = 64.917525
      + = 64.917525
        subtotal = 59.97
        tax = 4.947525
```

**Foreign numbers become exact at the boundary.** A JSON `0.1` is one tenth
from then on, so arithmetic on fetched data is as exact as on literals.

**The cost is bounded, not hidden.** Adding many fractions with unrelated
denominators grows the denominator. Summing 2000 distinct fractions takes
about 10ms; past the bound an operation is *refused* rather than silently
rounded, because a refusal is visible and a rounding is not.

## Effect surface

`shapes.py` computes what a program **can** do, without running it. The
runtime effect log records what one run **did**; the two must agree, and
`test_shapes.py` enforces that as an oracle on every example program.

```
python3 shapes_cli.py hn.planes                    # the surface
python3 shapes_cli.py hn.planes --functions        # per-function
python3 shapes_cli.py hn.planes --json             # machine-readable
python3 shapes_cli.py hn.planes --check            # module declarations
python3 shapes_cli.py --diff demo/v1.planes demo/v2.planes
python3 shapes_cli.py --index demo/pkgs            # index a corpus
python3 shapes_cli.py --search network demo/pkgs   # search by behaviour
```

Surface of the HN scraper, computed without a single network call:

```
network:
  ask https://hacker-news.firebaseio.com/v0/item/{...}.json (computed)
  ask https://hacker-news.firebaseio.com/v0/topstories.json
file:
  write results.json
console:
  show found {...} (computed)
```

Upgrade diff — the case the effect surface exists for. Exits 1, so it works as a CI gate:

```
$ python3 shapes_cli.py --diff demo/v1.planes demo/v2.planes
NEW BOUNDARIES CROSSED: network
  + network: ask https://telemetry.example.com/collect?data={...} (computed)
```

Two things worth knowing about how it works:

**Effects propagate through the call graph by fixed point**, not by a tree
walk, so a caller inherits everything its callees do, transitively, and
mutual recursion terminates.

**A library is not pure just because nothing runs at load time.** `effects`
is what running the file performs; `declared` is what any function in it can
do if called. Package queries read `declared` — otherwise a library whose
only network call sits one function deep would be indexed as harmless.

### Constant propagation

Effect targets resolve through variables, concatenation, and call arguments,
so the host stays visible instead of collapsing to `{...}`:

```
let base = "https://api.example.com"
let endpoint = base + "/users"
x = ask endpoint          →  ask https://api.example.com/users
```

Widening to unknown is always sound — it costs precision, never
correctness. Names assigned inside a branch or loop widen at the join, and
recursive functions are never specialised, because binding `n = 3` at a call
to `countdown of 3` would report `show 3` and miss 2, 1, 0.

### Modules

`use http` and `use file` name builtin capability modules. `use config`
names a file, `config.planes`, resolved relative to the importer.

A package's effect surface includes the surface of everything it imports:

```
$ shapes_cli.py demo/app/main.planes
network:
  ask https://pypi.org/pypi/requests/json
  ...

$ shapes_cli.py demo/app/main.planes --no-follow
file:
  write out.json
unresolved calls: package
```

`main.planes` contains no network code — the `ask` is in `net.planes` and
the base URL in `config.planes`. Following imports finds it and resolves the
exact URL across all three files. Not following says so, rather than
reporting a clean surface it cannot vouch for.

**Names are flat across a module graph, and collisions are errors.**
`api base` is called as `api base`, not `config.api base`, because multi-word
names already read as prose. Flat names make a collision genuinely ambiguous,
so it is reported:

```
$ shapes_cli.py demo/clash/main.planes
module error — two modules define the same name:
  'load record' is defined in cache.planes, loader.planes
  try: rename one of them — names are flat across modules,
       so 'load record' has to mean one thing
```

One of those reads a file and the other hits the network. Letting load order
decide would mean the same program behaved differently depending on the order
of its `use` lines, with nothing to read that explained why.

**A collision is fixed at the point of use.** A consumer of two colliding
modules usually cannot edit either one, so the rename lives in their file:

```
use loader
use cache with load record as load cached

fresh = load record of "requests"     # loader's, over the network
old   = load cached of "requests"     # cache's, from a file
```

The rename *replaces* the exported name rather than adding an alias —
registering both would put the collision straight back. The defining module
still calls its own functions by their own names.

## Files

An orientation, not an inventory — it names what the load-bearing files are
for. For the complete list of what is in the repo, ask the repo: `git ls-files`.

| File | What it is |
|---|---|
| `lexer.py` | Indentation-sensitive tokenizer + AST node definitions |
| `parser.py` | Recursive-descent parser for the full surface syntax |
| `planes_num.py` | Exact rational numbers, rounding, rendering |
| `interp.py` | Evaluator, derivation graph, `why`, runtime effect log |
| `host.py` | The host seam — five capabilities and a foreign resolver |
| `modules.py` | Module resolution, dependency graph, cycle detection |
| `shapes.py` | Static effect analyser — the total surface, computed not run |
| `planes.py` | CLI: run a program |
| `shapes_cli.py` | CLI: surface, diff, index, search |
| `test_planes.py` | 50 tests — language |
| `test_shapes.py` | 52 tests — analyser: oracle, constants, modules, namespacing |
| `test_numbers.py` | 31 tests — exactness, rounding, boundaries, limits |
| `test_names.py` | 15 tests — every builtin name usable as a function name |
| `test_foreign.py` | 37 tests — FFI, declarations, targets, the unknown default |
| `test_host.py` | 14 tests — the host seam, swapping, target opacity |
| `test_coverage.py` | 7 tests — oracle reaches every node; suite touches nothing |
| `hn.planes` | The HN scraper, line-mapped to the Python reference |
| `pypi.planes` | Same program shape, runs live |
| `ordinary.planes` | Reference ordinary program — no governance vocabulary |
| `money.planes` | Invoice arithmetic — the case exact numbers exist for |
| `names.planes` | Former keywords used as ordinary names |
| `foreign.planes` | Real Python host functions, declared |
| `demo/v1,v2.planes` | Before/after pair for the upgrade diff |
| `demo/pkgs/*.planes` | Small corpus for index and search |
| `demo/app/*.planes` | Three-file program: main → net → config |
| `demo/clash/*.planes` | Two modules defining one name — a reported error |
| `demo/rename/*.planes` | The same pair, resolved with `with ... as ...` |
| `demo/fdiff/*.planes` | A foreign destination change — identical code, different host |

## The language, as implemented

```
use http                          # declare a module before its effects work
use file

x = 5                             # binding; `let` optional
xs = [1, 2, 3]                    # lists
name = record.field               # dot access on records

to add of a, b:                   # function definition
  give a + b                      # return

to fetch stories:                 # multi-word, zero-arg
  give first 30 of everything

r = add of 2, 3                   # call; `of` binds tightly
r = add(2, 3)                     # equivalent

ys = for each x in xs: x * 2                    # comprehension
zs = for each x in xs where x > 2: x            # with filter

if n > 50:                        # conditional
  show "big"
else:
  show "small"

count of xs                       # builtins: count, lower, upper, text, first
lower of s.title
text of n

body = ask "https://..."          # network round-trip, needs `use http`
  or fail as api-down             # rename any failure to a domain error

write xs to "out.json"            # file write, needs `use file`

why total                         # derivation query
```

## What `why` does

Provenance is carried on values via a `Deriv` node, never in a type or
signature. `apply_op` has no idea derivation exists — results are wrapped
after the fact. This is the architectural difference from Jif-style label
propagation: nothing spreads into the signature of `+`.

One-line summary:

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

`origins(value)` returns just the boundary crossings a value depends on.

## Effect surface

Every boundary crossing is logged in order as the program runs. `--effects`
prints it. This is the runtime effect log; the static half is `shapes.py`.
