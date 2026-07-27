# Constant Propagation and Cross-File Modules — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Continues the Shapes analyser.
**Mandate:** Constant propagation for effect targets, then cross-file modules.
**Result:** Both built. 92/92 tests passing. **Two unsoundness bugs found and fixed** — both by probing, not by the test suite.

---

## 1. Constant Propagation

Effect targets now resolve through variables, concatenation, and call
arguments. Before, anything not a bare literal collapsed to `{...}` and the
host was lost:

```
let base = "https://api.example.com"
let endpoint = base + "/users"
x = ask endpoint

before:  ask {...} (computed)
after:   ask https://api.example.com/users
```

The mechanism is a scoped constant environment (`Consts`) tracking only what
is knowable without running anything: literals and concatenations of them.
Everything else widens to `UNKNOWN`. **Widening is always sound** — it costs
precision in the target description, never correctness of the effect set.

Call sites also specialise: `get of "https://api.example.com/x"` reports that
URL rather than the generic `{...}` its fixed-point surface carries.

---

## 2. Two Unsoundness Bugs

Both found by writing a probe that deliberately tried to break the analyser.
Neither was caught by the 28 tests that existed at the start of the session.

### 2.1 Specialisation was unsound under recursion — CAUGHT BY THE ORACLE

```
to countdown of n:
  show text of n
  if n > 0:
    give countdown of (n - 1)

countdown of 3
```

Specialisation bound `n = 3` and read the target off one pass, reporting
`show 3`. The program shows 3, then 2, then 1, then 0. The oracle caught it
immediately: *"runtime performed show on '2', not covered by static surface
['show 3'] — ANALYSER IS UNSOUND"*.

Fixed by never specialising a function that can reach itself through any
chain of calls (`is_recursive`, a reachability search over the call graph,
cached). Recursive callees keep their generic surface. The same guard
applies to constant folding of return values.

**This is the oracle earning its place.** A precision optimisation silently
became a correctness bug, and the runtime cross-check caught it on the first
run after the change.

### 2.2 A variable rebound in a branch kept its old value — CAUGHT BY PROBING

```
let u = "https://example.com/default.json"
if 1 > 0:
  let u = "https://example.com/other.json"
x = ask u
```

The `if` walk used a child scope, so the rebinding was discarded at the join.
The analyser reported `default.json`; the program asked `other.json`.

**This is the worst possible failure mode for Shapes**: not a missing effect,
but a *confidently wrong target*. A user reading the surface would see a URL
the program never contacts, and not see the one it does.

Fixed by widening every name assigned inside a branch or loop body to
`UNKNOWN` at the join. Which branch ran is a runtime fact; the surface must
not pretend otherwise.

Both cases are now permanent tests.

---

## 3. Cross-File Modules

`use http` and `use file` name builtin capability modules — reserved words
that unlock effects. `use config` names a file, `config.planes`, resolved
relative to the importer.

One keyword for both deliberately: from the caller's side `use` answers a
single question — what does this program depend on — and the analyser needs
both kinds in one dependency graph.

**A package's effect surface includes the surface of everything it imports.**
The demo is a three-file program where `main.planes` contains no network code
at all:

```
main.planes    → use net, use file        (calls fetch package)
net.planes     → use http, use config     (the ask lives here)
config.planes  → pure                     (the base URL lives here)
```

```
$ shapes_cli.py demo/app/main.planes
network:
  ask https://pypi.org/pypi/requests/json
file:
  write out.json
```

Constant propagation reached across all three files to resolve the exact URL.
The runtime confirms it: `('ask', 'https://pypi.org/pypi/requests/json', ...)`.

And the single-file view is honest about its limits:

```
$ shapes_cli.py demo/app/main.planes --no-follow
file:
  write out.json
unresolved calls: package
```

Without following imports it does not claim a clean network surface — it says
there are calls it cannot resolve.

### Module machinery

- `load_graph` returns files in dependency order, imports before importers.
- Cycles raise a named error with the cycle path, rather than hanging.
- A missing module names the fix.
- `run_file` hoists every file's definitions but **only executes the entry
  file's top-level statements** — importing a module must not run it.

---

## 4. A Parser Consequence of Modules

Multi-word function names could not be called across files. `api base` is two
NAME tokens; only a name table tells the parser it is one call, and the
prescan only saw the current file.

This creates a bootstrapping problem: the parser needs names from the
dependency graph, but discovering the graph required parsing. Resolved by
reading `use` statements at the **token** level (`uses_in`), so the graph is
discoverable before the parser knows enough to read any file. Names are then
collected graph-wide and passed into `parse(src, known)`.

**This is a real design consequence of multi-word names**, not an
implementation detail. It would not exist in a language with parenthesised
calls, and it is worth knowing that the syntax choice has this cost.

---

## 5. What Improved in Real Output

| Program | Before | After |
|---|---|---|
| variable-built URL | `ask {...}` | `ask https://api.example.com/users` |
| `get of "https://…"` | `ask {...}` | exact URL |
| three-file app | not analysable | exact URL, across three files |
| genuine unknowns | `{...}` | still `{...}`, correctly |

`fetcher.planes` in the corpus still reports `ask {...}` — it is a library
whose URL comes from its caller, so that is the honest answer.

---

## 6. What Is Not Built

- **Records and lists as constants.** Only strings and numbers propagate.
- **Per-call-site effect attribution.** The surface says the program asks two
  URLs, not which call site produces which.
- **Module namespacing.** Two files defining the same function name collide
  silently; last hoist wins. Needs a real decision before package indexing.
- **FFI.** Still Tier 0, still invisible to the analyser.
- **Numeric tower.** Unchanged and still the standing second priority.

---

## 7. Recommendation for the Next Session

**Module namespacing**, because it is now the only thing between this and a
real package index, and because the collision is currently silent — the worst
kind of gap in a system whose whole value is telling you the truth about
code you did not write.

Then the numeric tower, unchanged in priority and rationale from the last two
sessions: `why` on a money value that has silently lost precision is worse
than no `why` at all.

---

## 8. Test Summary

```
test_planes.py    47/47   language
test_shapes.py    45/45   analyser: oracle, libraries, constants,
                          modules, diffing, 9 adversarial cases
                  -----
                  92/92
```

Anti-drift greps still clean across `lexer.py`, `parser.py`, `interp.py`,
and `shapes.py`. A session about module resolution and constant folding
produced no governance vocabulary.
