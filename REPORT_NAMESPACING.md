# Module Namespacing — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Closes the last gap before a package index.
**Mandate:** Module namespacing — the silent collision.
**Result:** Closed. 102/102 tests passing. One design decision made, one language bug found.

---

## 1. The Gap

Two files defining the same function name collided silently, last hoist wins:

```
$ python3 planes.py demo/clash/main.planes
hello from b
```

No warning. And **load order decided it** — swapping the two `use` lines
changed the program's behaviour with nothing to read that explained why.

---

## 2. The Design Decision

Three options: implicit merge (the broken status quo), qualified access
(`config.api base`), or flat names with collisions as errors.

**Flat names, collisions are errors.**

The reason is in the existing code. Planes already calls `api base` and
`fetch package` unqualified, and multi-word names read as prose:

```
let pkg = fetch package of "requests"
```

Qualifying that to `net.fetch package of "requests"` fights the grain of the
language badly — it puts a dot in the middle of a phrase. The multi-word
syntax is a commitment, and this is one of the things it commits to.

But flat names make a collision genuinely ambiguous. There is no correct
resolution, so the only honest answer is to refuse:

```
$ shapes_cli.py demo/clash/main.planes
module error — two modules define the same name:
  'load record' is defined in cache.planes, loader.planes
  try: rename one of them — names are flat across modules,
       so 'load record' has to mean one thing
```

In that demo one `load record` hits the network and the other reads a file.
**Before this change, the published effect surface would have silently
reported whichever module loaded last.** For a tool whose whole value is
telling you the truth about code you did not write, that is the worst
possible failure.

### What is not a collision

- **Diamond dependencies.** Two modules importing the same third module share
  one copy; `_seen` in `load_graph` already handled it. Tested.
- **The same name in unrelated programs.** Collision is per module graph, not
  global. Two applications may both define `run`. Tested.

### What is now guaranteed

`use` order cannot change behaviour. With collisions banned there is nothing
left for order to decide, and a test asserts both orderings produce identical
output.

---

## 3. A Language Bug Found

Building the namespacing tests surfaced a real defect: **reserved words in
function names failed silently.**

```
to first thing:
  give "1"
```

`first` is a keyword (`first 30 of`), so this tokenizes as `TO FIRST NAME`.
The name prescan only accepts `NAME`, stopped immediately, and returned
nothing — the function became invisible to every caller, with no error at
definition or call site.

This matters more than it looks. The reserved list has 29 entries and
includes common nouns: `count`, `text`, `first`, `read`, `show`, `write`,
`lower`, `upper`, `nothing`. In a language whose selling point is names that
read as prose, those are exactly the words people reach for.

Fixed with a diagnostic that names the word and lists all 29:

```
syntax error — line 1: 'first' is a reserved word and cannot start a
function name
  reserved: and, as, ask, count, each, else, fail, false, first, for,
  give, if, in, let, lower, not, nothing, of, or, read, show, text, to,
  true, upper, use, where, why, write
```

A second bug fell out of the fix: `write x to "path"` uses the same `TO`
token as a definition, so the prescan tried to read a function name out of a
write statement. Definitions are now only recognised at statement start.

**This is the multi-word syntax showing its cost twice in one session** —
once in the parser bootstrapping problem last session, once here. Worth
recording plainly: prose-like names are not free.

---

## 4. Where the Check Runs

Collision detection sits in `check_collisions`, called by both consumers:

- `Interpreter.run_file` — refuses to run an ambiguous program.
- `analyse_file` — refuses to publish a surface for one.

The analyser refusing is the important half. A surface computed over an
ambiguous call graph is a guess, and publishing a guess as a fact is worse
than publishing nothing.

---

## 5. What Is Not Built

- **Selective import.** `use lib` brings in everything. No way to take one
  function, and no way to rename on import — which is the obvious escape
  hatch for a collision you do not control.
- **Private functions.** Every function in a module is exported.
- **Versioning.** Two versions of a module in one graph is an unhandled case.
- **FFI.** Still Tier 0.
- **Numeric tower.** Unchanged, still the standing priority.

Selective import and rename-on-import are the natural next step, because the
current answer to a collision between two third-party modules is "rename one
of them," which a consumer cannot do.

---

## 6. Recommendation for the Next Session

**The numeric tower.** It has been the standing second priority for three
sessions and the reason has not changed: `why` on a money value that has
silently lost precision is worse than no `why` at all. Integers and floats
are currently Python's, and integer division, overflow, and money are
untouched.

It is also the last thing that is *research* rather than labour. Selective
import, private functions, and versioning are all well-understood; the
numeric model that lets a value carry provenance without precision loss is
the open question, and it sits on the critical path for Why in exactly the
domains — finance, actuarial, pricing — the destination targets.

---

## 7. Test Summary

```
test_planes.py    50/50   language, incl. reserved-word diagnostics
test_shapes.py    52/52   analyser, modules, namespacing, oracle,
                          constants, 9 adversarial cases
                  -------
                  102/102
```

Anti-drift greps still clean. A session about name resolution produced no
governance vocabulary.
