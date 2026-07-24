"""Planes static effect analyser.

Computes a program's total effect surface without running it.

The runtime effect log in interp.py records what a program *did* on one
particular run. This computes what a program *can do* on any run. The two
must agree: every effect that occurs at runtime must appear in the static
surface. That is the oracle, and test_shapes.py enforces it.

The hard part is not finding `ask` in the AST. It is that a function's
effects include the effects of everything it calls, transitively, and calls
can be mutually recursive. So this is a fixed-point computation over the
call graph, not a tree walk.
"""
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from lexer import *
from parser import BUILTIN_NAMES, parse

# ================================================================ effect kinds

# EFFECT_KINDS — the closed vocabulary, grouped by boundary — now lives in
# lexer.py, because the parser also needs it (to validate a rule's effect
# kind) and cannot import this module without a cycle. `from lexer import *`
# below brings it into this namespace unchanged; `from shapes import
# EFFECT_KINDS` elsewhere in the codebase still works.
#
# `clock` and `random` are effects because they make a function's result
# depend on something outside the program. A function that reads the clock
# is not pure, and a package index that called it pure would be wrong in a
# way that matters — it is the difference between a value that can be
# reproduced from its derivation and one that cannot.

BOUNDARIES = ("network", "file", "console", "ambient", "foreign")

# What a foreign declaration may claim. `nothing` claims purity.
DECLARABLE = set(EFFECT_KINDS) | {"nothing"}


@dataclass(frozen=True)
class Effect:
    """One thing a program can do at a boundary.

    `target` is the static description of where — a literal when the program
    names one, or a pattern when it is computed. Patterns matter: a package
    that asks a computed URL is a different fact from one that asks a fixed
    endpoint, and Shapes has to be able to say which.
    """
    kind: str
    boundary: str
    target: str
    computed: bool = False      # target is built at runtime, not a literal
    site: int = 0               # source line
    claimed: bool = False       # asserted by a foreign declaration, not derived
    # Excluded from hash/equality: the fixed point compares effect sets for
    # growth, and two structurally identical effects reached by different
    # paths must remain one effect or it may not terminate.
    derivation: Optional[Any] = field(default=None, compare=False)

    def __str__(self):
        if self.kind == "unknown":
            return f"unknown — {self.target} declares no effects"
        t = self.target
        if self.computed and not t.endswith(")"):
            t += " (computed)"
        if self.claimed:
            t += " (declared, not verified)"
        return f"{self.kind} {t}"


@dataclass
class Surface:
    """A program's total effect surface.

    Two different questions, and conflating them is unsound:

    `effects` — what running this file performs, following calls from the
    top level. Right question for an application.

    `declared` — everything any function in this file can do if called.
    Right question for a library, where the top level is empty and the
    effects live behind functions the consumer calls. A library that
    reported `pure` because nothing runs at import time would be a lie of
    exactly the kind Shapes exists to prevent.
    """
    effects: list = field(default_factory=list)
    functions: dict = field(default_factory=dict)   # name -> set of Effect
    modules: set = field(default_factory=set)
    unresolved: list = field(default_factory=list)  # calls to unknown functions
    foreign: list = field(default_factory=list)     # effects of every foreign
                                                    # declaration, called or not

    # ---- the declared surface

    @property
    def declared(self):
        """Every effect any function here can perform, plus top-level ones.

        Includes foreign declarations even when nothing in this file calls
        them: a library that re-exports a clock function is not pure, and
        saying otherwise would be the same lie as calling a library pure
        because nothing runs at load time.

        A generic foreign entry is dropped when a call site already resolved
        the same effect to a real destination — keeping both would show the
        reader `{...}` beside the answer it stands in for.
        """
        out = list(self.effects)
        for es in self.functions.values():
            out.extend(es)
        resolved = {(e.kind, e.boundary) for e in out if not e.computed}
        for e in self.foreign:
            if e.computed and (e.kind, e.boundary) in resolved:
                continue
            out.append(e)
        seen, uniq = set(), []
        for e in out:
            k = (e.kind, e.target, e.computed)
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        return sorted(uniq, key=lambda e: (e.boundary, e.kind, e.target))

    def is_library(self):
        """No top-level effects, but functions or foreigns that have them."""
        return not self.effects and (any(self.functions.values())
                                     or bool(self.foreign))

    # ---- queries Shapes needs to answer
    #
    # These read the declared surface, because "does this package touch the
    # network" must be true of a library whose network call is one function
    # deep. Use `effects` directly for the narrower run-this-file question.

    def kinds(self):
        return sorted({e.kind for e in self.declared})

    def boundaries(self):
        return sorted({e.boundary for e in self.declared})

    def touches(self, boundary):
        return any(e.boundary == boundary for e in self.declared)

    def at(self, boundary):
        return [e for e in self.declared if e.boundary == boundary]

    def is_pure(self):
        return not self.declared

    def has_unknowns(self):
        """True if any foreign function declined to state its effects."""
        return any(e.kind == "unknown" for e in self.declared)

    def claims(self):
        """Effects asserted by a foreign declaration rather than derived."""
        return [e for e in self.declared if e.claimed]

    def targets(self, kind=None):
        return sorted({e.target for e in self.declared
                       if kind is None or e.kind == kind})

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

    def declared_but_unused(self):
        """Modules brought in with `use` that nothing actually needs."""
        needed = {EFFECT_KINDS[e.kind] for e in self.declared
                  if e.kind in EFFECT_KINDS}
        mods = set()
        for b in needed:
            mods.add("http" if b == "network" else b)
        return sorted(self.modules - mods)

    def used_but_undeclared(self):
        """Effects the program performs without the matching `use`."""
        missing = []
        for e in self.declared:
            mod = "http" if e.boundary == "network" else e.boundary
            if e.boundary in ("network", "file") and mod not in self.modules:
                missing.append(e)
        return missing

    def render(self):
        lines = []
        if self.is_pure():
            return "pure — this program touches nothing outside itself"
        if self.is_library():
            lines.append("(library — nothing runs at load; these are what "
                         "its functions can do)")
        for b in BOUNDARIES:
            at = self.at(b)
            if not at:
                continue
            lines.append(f"{b}:")
            seen = set()
            for e in at:
                key = (e.kind, e.target, e.computed)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"  {e}")
        if self.unresolved:
            lines.append(f"unresolved calls: {', '.join(sorted(set(self.unresolved)))}")
        if self.has_unknowns():
            lines.append("this surface is incomplete: a foreign function "
                         "states no effects")
        return "\n".join(lines)


# ================================================================ constants

class Unknown:
    """A value the analyser cannot pin down statically."""
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "{...}"


UNKNOWN = Unknown()


@dataclass(frozen=True)
class StaticDeriv:
    """One node in the static derivation graph. Mirrors interp.Deriv's shape
    deliberately — same field names, same meanings — so a reader who knows
    one knows the other, and the runtime and static graphs can eventually
    be compared.

    Frozen and tuple-typed because Effect is frozen and hashed into sets; a
    mutable `inputs` list would break Effect's hashability, which the fixed
    point depends on.
    """
    kind: str                    # literal|name|op|call|param|foreign|unknown
    label: str
    inputs: tuple = ()
    origin: Optional[str] = None # where this entered the program
    file: Optional[str] = None   # declaring file, for P-Q18 scoping


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


# ================================================================ analyser

class Analyser:
    def __init__(self):
        self.funcs = {}          # name -> FuncDef
        self.modules = set()
        self.unresolved = []
        self.depth = 0           # guards recursive constant evaluation
        self._rec_cache = {}     # name -> can it reach itself?
        self.local = {}          # original name -> exported name, for renames
        self.foreigns = {}       # name -> Foreign declaration
        self.func_file = {}      # name -> file path that declared it
        self.foreign_file = {}   # name -> file path that declared it
        self.entry_file = None   # the file the surface is being computed for
        self.current_file = None # file whose source is currently being walked

    # ---- entry point

    def analyse(self, src):
        prog = parse(src)
        self.collect_declarations(prog, file=self.entry_file)
        return self.analyse_prog(prog)

    def analyse_prog(self, prog):
        """Run the fixed point over already-collected declarations.

        Split out from `analyse` so a multi-file program can gather
        declarations from every file first, then compute one surface. A
        package's effect surface includes the surface of everything it uses.
        """
        # Fixed point over the call graph. A function's effect set grows
        # until it stops growing; recursion terminates because sets only
        # grow and the vocabulary is finite. Parameters are UNKNOWN here —
        # this is the generic surface, true for any call site.
        fn_effects = {name: set() for name in self.funcs}
        changed = True
        rounds = 0
        while changed:
            changed = False
            rounds += 1
            if rounds > 200:            # cannot happen; guard anyway
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

        # Top-level statements, now that function effects are known. Call
        # sites here may sharpen a callee's targets via specialisation.
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
                # Register under the exported name only. Also registering
                # the original would put the colliding name straight back
                # into the shared table — the thing the rename fixes.
                # Calls inside the defining file are resolved separately
                # via `self.local`.
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

    # ---- the walk

    def walk(self, node, fn_effects, consts):
        """Effects reachable from this node. Never executes anything."""
        if node is None:
            return set()

        out = set()

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
            # `ask` and `read` are ordinary builtin functions now, not keyword
            # nodes. They still produce effects, and a user function of the
            # same name shadows them — so a builtin only counts as an effect
            # when nothing else defines that name.
            if node.name in EFFECT_KINDS and node.name not in self.funcs:
                arg = node.args[0] if node.args else None
                target, computed, deriv = self.describe(arg, consts)
                out.add(Effect(node.name, EFFECT_KINDS[node.name],
                               target, computed, site=node.line, derivation=deriv))
                return out
            target = self.local.get(node.name, node.name)
            if target in self.foreigns:
                out |= self.foreign_effects(
                    self.foreigns[target], node.args, consts)
                return out
            if target in fn_effects:
                out |= self.specialise(
                    Call(target, node.args), fn_effects, consts)
            elif target not in self.funcs and target not in BUILTIN_NAMES:
                self.unresolved.append(node.name)
            return out

        if isinstance(node, Var):
            # A bare name may be a zero-arg call the parser left as Var.
            if node.name in fn_effects:
                return set(fn_effects[node.name])
            return set()

        if isinstance(node, Assign):
            out |= self.walk(node.expr, fn_effects, consts)
            value, node_ = self.const(node.expr, consts)
            consts.set(node.name, value, node_)
            return out

        if isinstance(node, (Give, Why)):
            return self.walk(node.expr, fn_effects, consts)

        if isinstance(node, BinOp):
            return (self.walk(node.left, fn_effects, consts)
                    | self.walk(node.right, fn_effects, consts))

        if isinstance(node, Not):
            return self.walk(node.expr, fn_effects, consts)

        if isinstance(node, Round):
            return (self.walk(node.value, fn_effects, consts)
                    | self.walk(node.places, fn_effects, consts))

        if isinstance(node, Field):
            return self.walk(node.obj, fn_effects, consts)

        if isinstance(node, ListLit):
            for i in node.items:
                out |= self.walk(i, fn_effects, consts)
            return out

        if isinstance(node, OrFail):
            return self.walk(node.expr, fn_effects, consts)

        if isinstance(node, ForEach):
            out |= self.walk(node.source, fn_effects, consts)
            inner = consts.child()
            inner.set(node.var, UNKNOWN,        # loop variable is never constant
                     StaticDeriv("unknown", node.var, file=self.current_file))
            out |= self.walk(node.where, fn_effects, inner)
            for s in node.body:
                out |= self.walk(s, fn_effects, inner)
            # Same join reasoning as `if`: whether the body ran at all, and
            # how many times, are runtime facts.
            for name in self.assigned_in(node.body):
                consts.set(name, UNKNOWN,
                          StaticDeriv("unknown", name, file=self.current_file))
            return out

        if isinstance(node, If):
            # Both branches. A static surface is what the program CAN do,
            # so an effect in an untaken branch still belongs in the surface.
            out |= self.walk(node.cond, fn_effects, consts)
            for s in node.then + node.els:
                out |= self.walk(s, fn_effects, consts.child())
            # At the join, any name a branch assigned is no longer knowable:
            # which branch ran is a runtime fact. Widening here is what keeps
            # the surface sound — without it, `if ...: let u = other` would
            # leave `u` reporting its pre-branch value.
            for name in self.assigned_in(node.then + node.els):
                consts.set(name, UNKNOWN,
                          StaticDeriv("unknown", name, file=self.current_file))
            return out

        if isinstance(node, FuncDef):
            return set()        # handled in the fixed point, not inline

        return set()

    def foreign_effects(self, decl, args=None, consts=None):
        """What a foreign declaration contributes to the surface.

        A declaration is a claim by whoever wrote it, not something the
        analyser derived — Planes cannot see inside the host. So the effects
        are reported as declared, and marked as such.

        An UNDECLARED foreign function does not contribute nothing. It
        contributes `unknown`, because defaulting to pure would publish a
        guess as a fact — the same failure as reporting a library pure
        because nothing runs at load time.

        When a declaration says its destination is a parameter, and the call
        site passes something the analyser knows, the real destination is
        reported. That is how a host name survives a foreign boundary.
        """
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

    def claim_target(self, decl, where, args, consts):
        """Where a declared effect goes, as specifically as can be known."""
        if where is None:
            # No destination stated. Naming the host function is honest —
            # it is what the reader has — but it is not a destination.
            return (f"{decl.target} (destination not stated)", True,
                    StaticDeriv("foreign", decl.target, file=self.current_file,
                               origin=f"foreign:{decl.target}"))
        kind, value = where
        if kind == "literal":
            return (value, False,
                    StaticDeriv("literal", f'"{value}"', file=self.current_file))
        # A parameter. Resolve it from the call site if there is one.
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

    def specialise(self, node, fn_effects, consts):
        """Re-analyse a callee with its arguments' known values bound.

        `get of "https://api.example.com/x"` should report that URL, not
        `{...}`. The generic effect set computed by the fixed point is the
        fallback and remains the soundness guarantee: specialisation may only
        sharpen a target description, never remove an effect.

        Recursive callees are NEVER specialised. `countdown of 3` shows 3,
        then 2, then 1 — binding n=3 and reading the target off one pass
        reports `show 3` and misses the rest. That is unsound, so any
        function that can reach itself keeps its generic surface.
        """
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

        # Keep every generic effect whose target the specialised pass did not
        # sharpen. Never drop an effect kind that the generic pass found.
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

    def is_recursive(self, name):
        """Can this function reach itself through any chain of calls?"""
        if name in self._rec_cache:
            return self._rec_cache[name]
        seen, stack = set(), [name]
        found = False
        while stack:
            cur = stack.pop()
            fn = self.funcs.get(cur)
            if fn is None:
                continue
            for callee in self.calls_in(fn.body):
                if callee == name:
                    found = True
                    stack = []
                    break
                if callee not in seen:
                    seen.add(callee)
                    stack.append(callee)
        self._rec_cache[name] = found
        return found

    def assigned_in(self, stmts):
        """Every name assigned anywhere inside these statements.

        Used at branch and loop joins: a name a branch may have rebound is
        not statically knowable afterwards.
        """
        out = set()

        def scan(n):
            if n is None:
                return
            if isinstance(n, Assign):
                out.add(n.name)
                scan(n.expr)
            elif isinstance(n, If):
                for s in n.then + n.els:
                    scan(s)
            elif isinstance(n, ForEach):
                for s in n.body:
                    scan(s)
            elif isinstance(n, FuncDef):
                for s in n.body:
                    scan(s)

        for s in stmts:
            scan(s)
        return out

    def calls_in(self, stmts):
        """Every function name called anywhere inside these statements."""
        out = set()

        def scan(n):
            if n is None:
                return
            if isinstance(n, Call):
                out.add(n.name)
                for a in n.args:
                    scan(a)
            elif isinstance(n, Var):
                if n.name in self.funcs:
                    out.add(n.name)
            elif isinstance(n, (Give, Why, Show, Not)):
                scan(n.expr)
            elif isinstance(n, Assign):
                scan(n.expr)
            elif isinstance(n, BinOp):
                scan(n.left)
                scan(n.right)
            elif isinstance(n, Field):
                scan(n.obj)
            elif isinstance(n, Builtin):
                scan(n.arg)
            elif isinstance(n, OrFail):
                scan(n.expr)
            elif isinstance(n, WriteTo):
                scan(n.value)
                scan(n.dest)
            elif isinstance(n, ListLit):
                for i in n.items:
                    scan(i)
            elif isinstance(n, ForEach):
                scan(n.source)
                scan(n.where)
                for s in n.body:
                    scan(s)
            elif isinstance(n, If):
                scan(n.cond)
                for s in n.then + n.els:
                    scan(s)
            elif isinstance(n, FuncDef):
                for s in n.body:
                    scan(s)

        for s in stmts:
            scan(s)
        return out

    # ---- constant evaluation

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
            left, left_n = self.const(node.left, consts)
            right, right_n = self.const(node.right, consts)
            if left is UNKNOWN or right is UNKNOWN:
                return UNKNOWN, StaticDeriv("unknown", "+", inputs=(left_n, right_n),
                                            file=self.current_file)
            v = (self.as_text(left) + self.as_text(right)
                 if (isinstance(left, str) or isinstance(right, str)) else left + right)
            return v, StaticDeriv("op", "+", inputs=(left_n, right_n),
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

    def const_call(self, node, consts):
        """Evaluate a call statically when its body is a single `give`.

        Bounded by depth: this is constant folding, not an interpreter, and
        it must never loop on recursion. The resulting "call" node's inputs
        are the argument nodes only — the callee's internal derivation
        chain is not inlined, so nested calls do not grow the graph
        multiplicatively (P-Q10).
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

    @staticmethod
    def as_text(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    # ---- target description

    def describe(self, node, consts):
        """Static description of an effect's target, paired with its node.

        A fully known value gives the exact target. A partly known one keeps
        its literal parts so the host and shape stay visible:
        `"https://api/" + text of id + ".json"` becomes
        `https://api/{...}.json`.
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


def analyse(src, file=None):
    a = Analyser()
    a.entry_file = file
    return a.analyse(src)


def analyse_file(path, follow=True):
    """Analyse a file plus everything it uses.

    `follow=False` gives the single-file surface. The default follows
    imports, because a package that hides its network call in a helper file
    is exactly the case Shapes has to see through.
    """
    if not follow:
        return analyse(open(path).read(), file=path)

    from modules import check_collisions, load_graph, names_in_graph, rename_map
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


# ================================================================ diffing

@dataclass
class SurfaceDiff:
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    new_boundaries: list = field(default_factory=list)
    dropped_boundaries: list = field(default_factory=list)

    def is_empty(self):
        return not (self.added or self.removed)

    def new_destinations(self):
        """Destinations reached now that were not reached before.

        A new host inside a boundary the program already touched is the
        case targets exist for: identical code, identical effect kinds, a
        different place the data goes.
        """
        before = {e.target for e in self.removed}
        return [e for e in self.added
                if e.target not in before and not e.computed]

    def is_significant(self):
        """Worth failing a build over: a new boundary, or a new destination."""
        return bool(self.new_boundaries or self.new_destinations())

    def render(self):
        if self.is_empty():
            return "no change to the effect surface"
        lines = []
        if self.new_boundaries:
            lines.append("NEW BOUNDARIES CROSSED: "
                         + ", ".join(self.new_boundaries))
        fresh = self.new_destinations()
        if fresh and not self.new_boundaries:
            lines.append("NEW DESTINATIONS: "
                         + ", ".join(sorted({e.target for e in fresh})))
        for e in self.added:
            lines.append(f"  + {e.boundary}: {e}")
        for e in self.removed:
            lines.append(f"  - {e.boundary}: {e}")
        if self.dropped_boundaries:
            lines.append("no longer touches: "
                         + ", ".join(self.dropped_boundaries))
        return "\n".join(lines)


def diff(before: Surface, after: Surface) -> SurfaceDiff:
    """What changed between two versions of a program.

    This is the upgrade-diff use case: tell me this package now performs
    network sends it did not before — including a library whose new
    network call lives in a function nothing calls at load time. `added`/
    `removed` compare `.declared`, not `.effects`, so `is_empty()` (and the
    "no change" render() takes when it's true) agrees with
    `new_boundaries`/`dropped_boundaries`, which were already computed from
    `.declared` via `.boundaries()`. Comparing `.effects` here (audit
    finding, unearned-assertion sweep) let `is_empty()` say "no change"
    for a library that gained a whole new boundary in an uncalled
    function — exactly the "reported pure because nothing runs at load"
    lie this project exists to prevent, reproduced inside its own diff
    tool.
    """
    b = {(e.kind, e.target, e.computed): e for e in before.declared}
    a = {(e.kind, e.target, e.computed): e for e in after.declared}
    added = [a[k] for k in a if k not in b]
    removed = [b[k] for k in b if k not in a]
    return SurfaceDiff(
        added=sorted(added, key=lambda e: (e.boundary, e.kind, e.target)),
        removed=sorted(removed, key=lambda e: (e.boundary, e.kind, e.target)),
        new_boundaries=sorted(set(after.boundaries()) - set(before.boundaries())),
        dropped_boundaries=sorted(set(before.boundaries()) - set(after.boundaries())),
    )
