"""Planes evaluator — values, provenance, effects."""
import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from host import HostError, PythonHost, TestHost
from lexer import *
from parser import BUILTIN_NAMES, parse
from planes_num import Inexact, Number


class _BuiltinName:
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name


# ================================================================ values

@dataclass
class Deriv:
    """One node in a derivation graph. Provenance lives here, not in types."""
    kind: str                                  # literal|name|op|call|field|effect|...
    label: str
    value: Any
    inputs: list = field(default_factory=list)
    origin: Optional[str] = None               # where this entered the program


@dataclass
class Traced:
    value: Any
    node: Deriv

    def __repr__(self):
        return repr(self.value)


def lit(v, label=None):
    return Traced(v, Deriv("literal", label if label is not None else fmt(v), v))


def fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "nothing"
    if isinstance(v, Number):
        return v.text()
    if isinstance(v, (int, float)):
        return Number.of(v).text()
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return f"[{len(v)} items]"
    if isinstance(v, dict):
        return "{record}"
    return str(v)


def equal(a, b):
    """Sameness, guarded. Cross-type comparison is an error, not `false`.

    A `false` from `5 == "5"` is true about the computation and useless
    about the mistake — and it enters a derivation as a fact. The number
    model refuses rather than rounds silently; equality refuses rather
    than answers.
    """
    if a is None or b is None:
        raise PlanesError(
            "cannot-compare",
            "nothing cannot be compared with ==",
            "test for absence with `is nothing`")

    if is_num(a) and is_num(b):
        return Number.of(a) == Number.of(b)

    if isinstance(a, bool) != isinstance(b, bool):
        raise PlanesError(
            "cannot-compare",
            f"cannot compare {fmt(a)} with {fmt(b)}",
            "compare a yes/no value with a yes/no value")
    if isinstance(a, bool):
        return a is b

    if type(a) is not type(b):
        raise PlanesError(
            "cannot-compare",
            f"cannot compare {fmt(a)} with {fmt(b)}",
            "compare numbers with numbers, or text with text")

    if isinstance(a, str):
        return a == b

    if isinstance(a, list):
        if len(a) != len(b):
            return False
        for x, y in zip(a, b):
            if not equal(x, y):     # raises, with the position, on type mismatch
                return False
        return True

    if isinstance(a, dict):
        if set(a) != set(b):
            raise PlanesError(
                "cannot-compare",
                f"records have different fields: "
                f"{sorted(set(a) ^ set(b))}",
                "compare records with the same fields")
        return all(equal(a[k], b[k]) for k in a)

    return a == b


def condition(v):
    """What `if` and `where` accept. A yes/no value, and nothing else."""
    if isinstance(v, bool):
        return v
    raise PlanesError(
        "not-a-yes-no",
        f"a condition needs a yes/no value, found {fmt(v)}",
        "compare it: `if count of items > 0:`")


# ================================================================ errors

class PlanesError(Exception):
    def __init__(self, tag, detail="", fix=""):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        msg = tag
        if detail:
            msg += f": {detail}"
        if fix:
            msg += f"\n  try: {fix}"
        super().__init__(msg)


class _Give(Exception):
    def __init__(self, value):
        self.value = value


# ================================================================ env

class Env:
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def get(self, name):
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.get(name)
        raise PlanesError("unknown-name", f"no name '{name}' here",
                          f"define it first: let {name} = ...")

    def set(self, name, val):
        """Rebind where the name lives; bind locally if it is new."""
        scope = self
        while scope is not None:
            if name in scope.vars:
                scope.vars[name] = val
                return
            scope = scope.parent
        self.vars[name] = val

    def bind_local(self, name, val):
        """Always a new binding in this scope. What `let` means."""
        self.vars[name] = val

    def has(self, name):
        return name in self.vars or (self.parent is not None and self.parent.has(name))


@dataclass
class Function:
    name: str
    params: list
    body: list
    env: Env
    local: str = ""      # the name the defining file knows it by


# ================================================================ interpreter

def real_http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "planes/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode()


class Interpreter:
    def __init__(self, http=None, fs=None, host=None):
        self.env = Env()
        self.funcs = {}
        self.foreigns = {}       # name -> Foreign declaration
        self.modules = set()
        self.output = []
        self.effects = []            # ordered record of what the program did
        self.annotations = {}        # name -> latest `because` text, display-only

        # Every effect goes through a host. `http=` and `fs=` are the older,
        # narrower way to say the same thing and still work; they build a
        # TestHost. See host.py for what a host has to provide, and
        # REPORT_HOST.md for why that surface is as small as it is.
        if host is not None:
            self.host = host
        elif http is not None or fs is not None:
            self.host = TestHost(responses=http, files=fs)
        else:
            self.host = PythonHost()

    @property
    def fs(self):
        """Files this run touched, when the host keeps them in memory."""
        return getattr(self.host, "files", {})

    # ---- driving

    def run(self, src, path=None):
        prog = parse(src)
        self.hoist(prog, self.env)
        for stmt in prog:
            if isinstance(stmt, Note):
                continue     # never dispatched -- see exec_stmt's Note case
            self.exec_stmt(stmt, self.env)
        return self.output

    def run_file(self, path):
        """Run a file plus everything it uses.

        Imported files are loaded in dependency order and their definitions
        hoisted into the same scope. Only the entry file's top-level
        statements execute — importing a module must not run it.
        """
        from modules import check_collisions, load_graph, names_in_graph, rename_map
        graph = load_graph(path)
        check_collisions(graph)
        known = names_in_graph(graph)
        renames = rename_map(graph)
        entry = []
        for p, src in graph:
            prog = parse(src, known)
            self.hoist(prog, self.env, renames.get(p, {}))
            if os.path.abspath(p) == os.path.abspath(path):
                entry = prog
            else:
                for stmt in prog:
                    if isinstance(stmt, Use):
                        self.exec_stmt(stmt, self.env)
        for stmt in entry:
            if isinstance(stmt, Note):
                continue
            self.exec_stmt(stmt, self.env)
        return self.output

    def hoist(self, stmts, env, renames=None):
        """Register function definitions before executing anything.

        Source order controls execution, not visibility: a program may call a
        function defined further down the file. Without this the static
        analyser and the interpreter disagree about what a program can do,
        and the analyser would be the one telling the truth.
        """
        renames = renames or {}
        for s in stmts:
            if isinstance(s, Foreign):
                self.foreigns[renames.get(s.name, s.name)] = s
                continue
            if isinstance(s, FuncDef):
                fn = Function(s.name, s.params, s.body, env)
                # A rename replaces the exported name. Registering both would
                # put the colliding name back, which is the thing the rename
                # was written to fix. The defining file still reaches its own
                # functions by their original names through `fn.local`.
                exported = renames.get(s.name, s.name)
                self.funcs[exported] = fn
                fn.local = s.name
                self.hoist(s.body, env, renames)

    def exec_block(self, stmts, env):
        result = None
        for s in stmts:
            if isinstance(s, Note):
                continue
            result = self.exec_stmt(s, env)
        return result

    def exec_stmt(self, stmt, env):
        if isinstance(stmt, Use):
            self.modules.add(stmt.module)
            return None

        if isinstance(stmt, Foreign):
            self.foreigns[stmt.name] = stmt
            return None

        if isinstance(stmt, Rule):
            # A rule is a constraint the checker reads, never an action
            # the program takes (unbound v2.0 §33's refusal of `trigger`,
            # enforced here). Nothing about a rule's presence may change
            # what a program does.
            return None

        if isinstance(stmt, Note):
            # A normal run never reaches this: run(), run_file(), and
            # exec_block() all skip Note before ever calling exec_stmt.
            # This case is the structural half of that guarantee, not the
            # mechanism — a promise kept by structure, not by every
            # present and future statement-list loop remembering to
            # filter (unbound v1.0 §4 item 3, §218). If this ever fires,
            # a call site stopped filtering; that is a bug in Planes, not
            # in the program that wrote a `note:` block.
            raise PlanesError(
                "annotation-executed",
                "an annotation reached the evaluator",
                "this is a bug in Planes, not in your program — please report it")

        if isinstance(stmt, FuncDef):
            self.funcs[stmt.name] = Function(stmt.name, stmt.params, stmt.body, env)
            return None

        if isinstance(stmt, Assign):
            val = self.eval(stmt.expr, env)
            named = Traced(val.value, Deriv("name", stmt.name, val.value, [val.node]))
            if stmt.is_let:
                env.bind_local(stmt.name, named)
            else:
                env.set(stmt.name, named)
            # `because` is a rationale for `why` to show beside the
            # derivation, never an input to it — the Deriv graph above
            # never sees stmt.annotation, only stmt.expr.
            if stmt.annotation is not None:
                self.annotations[stmt.name] = stmt.annotation.text
            else:
                self.annotations.pop(stmt.name, None)
            return named

        if isinstance(stmt, Give):
            raise _Give(self.eval(stmt.expr, env))

        if isinstance(stmt, Show):
            v = self.eval(stmt.expr, env)
            text = fmt(v.value)
            self.output.append(text)
            self.host.show(text)
            self.effects.append(("show", text))
            return v

        if isinstance(stmt, Why):
            v = self.eval(stmt.expr, env)
            because = self.annotations.get(stmt.expr.name) \
                if isinstance(stmt.expr, Var) else None
            self.output.append(explain(v, because))
            return v

        if isinstance(stmt, If):
            c = self.eval(stmt.cond, env)
            return self.exec_block(stmt.then if condition(c.value) else stmt.els, env)

        return self.eval(stmt, env)

    # ---- expressions

    def eval(self, node, env):
        if isinstance(node, Num):
            return lit(node.value)
        if isinstance(node, Str):
            return Traced(node.value, Deriv("literal", f'"{node.value}"', node.value))
        if isinstance(node, Bool):
            return lit(node.value)
        if isinstance(node, Nothing):
            return lit(None)

        if isinstance(node, Var):
            if node.name in self.funcs and not env.has(node.name):
                return self.call(node.name, [], env)
            return env.get(node.name)

        if isinstance(node, RecordLit):
            parts = [(k, self.eval(v, env)) for k, v in node.fields]
            val = {k: t.value for k, t in parts}
            return Traced(val, Deriv("record", "{record}", val,
                                     [t.node for _, t in parts]))

        if isinstance(node, ListLit):
            items = [self.eval(i, env) for i in node.items]
            vals = [i.value for i in items]
            return Traced(vals, Deriv("list", f"[{len(vals)} items]", vals,
                                      [i.node for i in items]))

        if isinstance(node, Not):
            v = self.eval(node.expr, env)
            r = not condition(v.value)
            return Traced(r, Deriv("op", "not", r, [v.node]))

        if isinstance(node, IsNothing):
            v = self.eval(node.expr, env)
            r = v.value is None
            return Traced(r, Deriv("op", "is nothing", r, [v.node]))

        if isinstance(node, BinOp):
            return self.eval_binop(node, env)

        if isinstance(node, Field):
            obj = self.eval(node.obj, env)
            if not isinstance(obj.value, dict):
                raise PlanesError(
                    "not-a-record",
                    f"cannot read .{node.name} from {fmt(obj.value)}",
                    "check the value is a record before using dot access")
            val = obj.value.get(node.name)
            return Traced(val, Deriv("field", f".{node.name}", val, [obj.node]))

        if isinstance(node, Call):
            return self.call(node.name, node.args, env)

        if isinstance(node, Builtin):
            return self.eval_builtin(node, env)

        if isinstance(node, Round):
            v = self.eval(node.value, env)
            p = self.eval(node.places, env)
            if not is_num(v.value):
                raise PlanesError("not-a-number",
                                  f"cannot round {fmt(v.value)}",
                                  "round only works on numbers")
            n = Number.of(v.value).round_to(Number.of(p.value).as_int())
            return Traced(n, Deriv("op", f"round to {fmt(p.value)} places",
                                   n, [v.node]))

        if isinstance(node, WriteTo):
            value = self.eval(node.value, env)
            dest = self.eval(node.dest, env)
            if "file" not in self.modules:
                raise PlanesError("module-not-used",
                                  "writing a file needs the file module",
                                  "add `use file` at the top")
            payload = to_json(value.value)
            self.host.write(dest.value, payload)
            self.effects.append(("write", dest.value, len(payload)))
            return Traced(None, Deriv("effect", f"write to {dest.value}", None,
                                      [value.node], origin=f"file:{dest.value}"))

        if isinstance(node, OrFail):
            try:
                return self.eval(node.expr, env)
            except _Give:
                raise
            except PlanesError as e:
                raise PlanesError(node.tag, e.detail or e.tag)
            except Exception as e:
                raise PlanesError(node.tag, str(e))

        if isinstance(node, ForEach):
            return self.eval_foreach(node, env)

        if isinstance(node, If):
            c = self.eval(node.cond, env)
            return self.exec_block(node.then if condition(c.value) else node.els, env)

        raise PlanesError("cannot-evaluate", type(node).__name__)

    def eval_binop(self, node, env):
        if node.op == "and":
            l = self.eval(node.left, env)
            if not condition(l.value):
                return Traced(False, Deriv("op", "and", False, [l.node]))
            r = self.eval(node.right, env)
            v = condition(r.value)
            return Traced(v, Deriv("op", "and", v, [l.node, r.node]))

        if node.op == "or":
            l = self.eval(node.left, env)
            if condition(l.value):
                return Traced(True, Deriv("op", "or", True, [l.node]))
            r = self.eval(node.right, env)
            v = condition(r.value)
            return Traced(v, Deriv("op", "or", v, [l.node, r.node]))

        if node.op == "first":
            n = self.eval(node.left, env)
            src = self.eval(node.right, env)
            v = list(src.value)[: int(n.value)]
            return Traced(v, Deriv("op", f"first {int(n.value)} of", v, [src.node]))

        l = self.eval(node.left, env)
        r = self.eval(node.right, env)
        v = apply_op(node.op, l.value, r.value)
        return Traced(v, Deriv("op", node.op, v, [l.node, r.node]))

    def eval_builtin(self, node, env):
        return self.builtin(node.name, self.eval(node.arg, env))

    def builtin(self, name, arg):
        """The built-in functions. Ordinary calls, not keywords."""
        node = _BuiltinName(name)

        if node.name == "ask":
            if "http" not in self.modules:
                raise PlanesError("module-not-used",
                                  "asking a url needs the http module",
                                  "add `use http` at the top")
            url = arg.value
            try:
                body = self.host.ask(url)
            except HostError as e:
                raise PlanesError("ask-failed", str(e))
            self.effects.append(("ask", url, len(body)))
            try:
                parsed = from_foreign(self.host.parse_json(body))
            except Exception:
                parsed = body
            return Traced(parsed, Deriv("effect", f"ask {url}", parsed,
                                        [arg.node], origin=f"network:{url}"))

        if node.name == "read":
            if "file" not in self.modules:
                raise PlanesError("module-not-used",
                                  "reading a file needs the file module",
                                  "add `use file` at the top")
            path = arg.value
            try:
                body = self.host.read(path)
            except HostError:
                raise PlanesError("no-such-file", path,
                                  "check the path, or write it first")
            self.effects.append(("read", path, len(body)))
            return Traced(body, Deriv("effect", f"read {path}", body,
                                      [arg.node], origin=f"file:{path}"))

        if node.name == "count":
            v = Number.of(len(arg.value))
            return Traced(v, Deriv("op", "count of", v, [arg.node]))
        if node.name == "lower":
            v = str(arg.value).lower()
            return Traced(v, Deriv("op", "lower of", v, [arg.node]))
        if node.name == "upper":
            v = str(arg.value).upper()
            return Traced(v, Deriv("op", "upper of", v, [arg.node]))
        if node.name == "whole":
            if not is_num(arg.value):
                raise PlanesError("not-a-number",
                                  f"cannot take the whole part of {fmt(arg.value)}")
            n = Number.of(arg.value).round_to(0)
            return Traced(n, Deriv("op", "whole of", n, [arg.node]))

        if node.name == "text":
            v = fmt(arg.value)
            return Traced(v, Deriv("op", "text of", v, [arg.node]))

        raise PlanesError("unknown-builtin", node.name)

    def eval_foreach(self, node, env):
        source = self.eval(node.source, env)
        if not isinstance(source.value, (list, tuple)):
            raise PlanesError("not-a-collection",
                              f"cannot loop over {fmt(source.value)}",
                              "for each needs a list")
        results, nodes = [], []
        for idx, item in enumerate(source.value):
            inner = Env(env)
            item_t = Traced(item, Deriv("item", node.var, item, [source.node]))
            inner.bind_local(node.var, item_t)
            if node.where is not None:
                if not condition(self.eval(node.where, inner).value):
                    continue
            r = self.eval(node.body[0], inner) if node.is_expr \
                else self.exec_block(node.body, inner)
            if r is not None:
                results.append(r.value)
                nodes.append(r.node)
        label = f"for each {node.var}" + (" where ..." if node.where else "")
        return Traced(results, Deriv("comprehension", label, results,
                                     [source.node] + nodes[:3]))

    def call(self, name, args, env):
        # A user's own definition wins over a builtin of the same name.
        # Builtins are ordinary functions, so shadowing one is fine and is
        # the escape hatch if a name is wanted for something else.
        if name not in self.funcs and name in BUILTIN_NAMES:
            if len(args) != 1:
                raise PlanesError(
                    "wrong-arity",
                    f"'{name}' takes 1 value, given {len(args)}",
                    f"write it as `{name} of x`")
            arg = args[0] if isinstance(args[0], Traced) \
                else self.eval(args[0], env)
            return self.builtin(name, arg)

        if name in self.foreigns and name not in self.funcs:
            return self.call_foreign(self.foreigns[name], args, env)

        if name not in self.funcs:
            # A renamed function keeps working inside the file that defines
            # it: importers see the new name, the module sees its own.
            for fn in self.funcs.values():
                if fn.local == name:
                    return self.invoke(fn, args, env)
            raise PlanesError("unknown-function", f"no function named '{name}'",
                              f"define it: to {name}: ...")
        return self.invoke(self.funcs[name], args, env, name)

    def call_foreign(self, decl, args, env):
        """Call a host function.

        Values are converted on the way out and back, so a host float
        returns as an exact number and a Planes number arrives as something
        the host understands. The declared effects are logged before the
        call — a declaration is a claim, and the log records that the claim
        was acted on, not that it was verified.
        """
        if len(args) != len(decl.params):
            word = "value" if len(decl.params) == 1 else "values"
            raise PlanesError(
                "wrong-arity",
                f"'{decl.name}' takes {len(decl.params)} {word}, "
                f"given {len(args)}")

        arg_vals = [a if isinstance(a, Traced) else self.eval(a, env)
                    for a in args]

        try:
            fn = self.host.resolve(decl.target)
        except HostError as e:
            if "bad target" in str(e):
                raise PlanesError(
                    "bad-foreign-target", decl.target,
                    f"write it as {self.host.target_hint()}")
            raise PlanesError(
                "foreign-not-found",
                f"cannot find '{decl.target}' in the host",
                "check the module is installed and the name is right")

        for kind, where in decl.effects:
            # Log where the effect actually went, resolving a parameter
            # against this call's arguments. The runtime knows the real
            # value, so its log is the ground truth the static surface is
            # checked against.
            dest = decl.target
            if where is not None:
                if where[0] == "literal":
                    dest = where[1]
                elif where[0] == "param" and where[1] in decl.params:
                    i = decl.params.index(where[1])
                    if i < len(arg_vals):
                        dest = fmt(arg_vals[i].value)
            self.effects.append((kind, dest))

        try:
            raw = fn(*[to_host(a.value) for a in arg_vals])
        except Exception as e:
            raise PlanesError(
                "foreign-failed",
                f"'{decl.name}' raised {type(e).__name__}: {e}",
                "wrap the call with `or fail as ...` to name the failure")

        value = from_foreign(raw)
        return Traced(value, Deriv("foreign", decl.name, value,
                                   [a.node for a in arg_vals],
                                   origin=f"foreign:{decl.target}"))

    def invoke(self, fn, args, env, name=None):
        name = name or fn.local or fn.name
        if len(args) != len(fn.params):
            word = "value" if len(fn.params) == 1 else "values"
            raise PlanesError(
                "wrong-arity",
                f"'{name}' takes {len(fn.params)} {word}, given {len(args)}")
        arg_vals = [a if isinstance(a, Traced) else self.eval(a, env) for a in args]
        inner = Env(fn.env)
        for p, a in zip(fn.params, arg_vals):
            inner.bind_local(p, Traced(a.value, Deriv("name", p, a.value, [a.node])))
        try:
            self.exec_block(fn.body, inner)
            return Traced(None, Deriv("call", name, None,
                                      [a.node for a in arg_vals]))
        except _Give as g:
            return Traced(g.value.value,
                          Deriv("call", name, g.value.value,
                                [g.value.node] + [a.node for a in arg_vals]))


def apply_op(op, a, b):
    if op == "+":
        if isinstance(a, str) or isinstance(b, str):
            return fmt(a) + fmt(b)
        if isinstance(a, list) and isinstance(b, list):
            return a + b
        return arith("+", a, b)
    if op == "-": return arith("-", a, b)
    if op == "*": return arith("*", a, b)
    if op == "/":
        if is_num(b) and Number.of(b) == 0:
            raise PlanesError("divided-by-zero", "the right side of / was 0",
                              "guard with `if divisor != 0:`")
        return arith("/", a, b)
    if op == "<":  return compare(op, a, b)
    if op == ">":  return compare(op, a, b)
    if op == "<=": return compare(op, a, b)
    if op == ">=": return compare(op, a, b)
    if op == "==": return equal(a, b)
    if op == "!=": return not equal(a, b)
    if op == "in": return a in b
    raise PlanesError("unknown-operator", op)


def is_num(v):
    return isinstance(v, (Number, int)) and not isinstance(v, bool)


def arith(op, a, b):
    """Exact arithmetic. Non-numbers get an error that names the value."""
    for v in (a, b):
        if not is_num(v):
            raise PlanesError(
                "not-a-number",
                f"cannot use '{op}' on {fmt(v)}",
                "check the value is a number before doing arithmetic")
    x, y = Number.of(a), Number.of(b)
    try:
        if op == "+": return x + y
        if op == "-": return x - y
        if op == "*": return x * y
        if op == "/": return x / y
    except Inexact as e:
        raise PlanesError(
            "needs-rounding", str(e),
            "round an intermediate value, e.g. `round x to 6 places`")
    raise PlanesError("unknown-operator", op)


def compare(op, a, b):
    """Ordering comparisons work on numbers and on text."""
    if is_num(a) and is_num(b):
        a, b = Number.of(a), Number.of(b)
    elif type(a) is not type(b):
        raise PlanesError(
            "cannot-compare",
            f"cannot compare {fmt(a)} with {fmt(b)}",
            "compare numbers with numbers, or text with text")
    if op == "<":  return a < b
    if op == ">":  return a > b
    if op == "<=": return a <= b
    return a >= b


def to_json(v):
    def unwrap(x):
        if isinstance(x, Traced):
            return unwrap(x.value)
        if isinstance(x, list):
            return [unwrap(i) for i in x]
        if isinstance(x, dict):
            return {k: unwrap(val) for k, val in x.items()}
        if isinstance(x, Number):
            # Whole numbers stay whole; others go out as text so an exact
            # value is not silently rounded on the way to a file.
            return x.as_int() if x.is_whole() else x.text()
        return x
    return json.dumps(unwrap(v), indent=2)


def to_host(x):
    """Convert a Planes value for the host.

    Exact numbers become int where whole, float otherwise. The float is a
    real loss of precision and it happens only here, at a boundary the
    program asked to cross by writing `foreign`.
    """
    if isinstance(x, Number):
        return x.as_int() if x.is_whole() else float(x)
    if isinstance(x, list):
        return [to_host(i) for i in x]
    if isinstance(x, dict):
        return {k: to_host(v) for k, v in x.items()}
    return x


def from_foreign(x):
    """Convert data arriving from outside into Planes values.

    JSON numbers are floats. Converting at the boundary means a value that
    entered as 0.1 is one tenth from then on, so arithmetic on foreign data
    is as exact as arithmetic on literals.
    """
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return Number.of(x)
    if isinstance(x, list):
        return [from_foreign(i) for i in x]
    if isinstance(x, dict):
        return {k: from_foreign(v) for k, v in x.items()}
    return x


# ================================================================ why

def explain(traced, because=None):
    """`why`'s one-line derivation. `because`, when given, is display
    text beside it — never an input the derivation graph carries."""
    n = traced.node
    inner = n.inputs[0] if n.kind == "name" and n.inputs else n
    text = f"{fmt(traced.value)} from {render(inner)}"
    if because:
        text += f'\n  because "{because}"'
    return text


def render(node):
    k = node.kind
    if k == "literal":
        return node.label
    if k in ("name", "item"):
        return f"{node.label} ({fmt(node.value)})"
    if k == "field":
        base = render(node.inputs[0]) if node.inputs else "?"
        return f"{base}{node.label}"
    if k == "call":
        body = node.inputs[0] if node.inputs else None
        args = node.inputs[1:]
        arglist = ", ".join(render(a) for a in args)
        head = f"{node.label}({arglist})" if arglist else node.label
        return f"{head} = {render(body)}" if body else head
    if k == "effect":
        return node.label
    if k == "comprehension":
        src = render(node.inputs[0]) if node.inputs else "?"
        return f"{node.label} over {src}"
    if k == "list":
        return node.label
    if k == "record":
        return node.label
    if k == "op":
        if node.label.endswith(" of") or node.label == "not":
            return f"{node.label} {render(node.inputs[0])}"
        return f" {node.label} ".join(render(i) for i in node.inputs)
    return fmt(node.value)


def why_tree(traced, max_depth=14, because=None):
    """Full transitive derivation, back to where each value entered.

    The graph is a DAG, not a tree: one source list feeds every item of a
    comprehension. Shared subgraphs are printed once and referred to after,
    so the output stays the size of the derivation, not of the data.

    `because`, when given, is display text for the root beside the
    derivation — never an input the graph itself carries.
    """
    lines = []
    seen = {}

    def walk(n, depth):
        if depth > max_depth:
            lines.append("  " * depth + "...")
            return
        tail = f"   <- entered at {n.origin}" if n.origin else ""
        if id(n) in seen and n.inputs:
            lines.append("  " * depth +
                         f"{n.label} = {fmt(n.value)}   (same as above)")
            return
        seen[id(n)] = True
        lines.append("  " * depth + f"{n.label} = {fmt(n.value)}{tail}")
        if depth == 0 and because:
            lines.append("  " * (depth + 1) + f'because "{because}"')
        for i in n.inputs:
            walk(i, depth + 1)

    walk(traced.node, 0)
    return "\n".join(lines)


def origins(traced):
    """Every boundary crossing this value depends on."""
    found = []

    def walk(n):
        if n.origin:
            found.append(n.origin)
        for i in n.inputs:
            walk(i)

    walk(traced.node)
    return found
