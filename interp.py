"""Planes evaluator — values, provenance, effects."""
import json
import os
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from host import HostError, PythonHost, TestHost
from lexer import *
from parser import BUILTIN_NAMES, parse
from planes_num import Inexact, Number
from planes_text import escape_string_literal


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


def equal(a, b, path=None):
    """Sameness, guarded. Cross-type comparison is an error, not `false`.

    A `false` from `5 == "5"` is true about the computation and useless
    about the mistake — and it enters a derivation as a fact. The number
    model refuses rather than rounds silently; equality refuses rather
    than answers.

    `path` accumulates the list-index/record-field steps from the root to
    a nested mismatch, so a mismatch buried inside a list of records names
    exactly where it is, not just what it is.
    """
    path = path if path is not None else []

    if a is None or b is None:
        raise PlanesError(
            "cannot-compare",
            "nothing cannot be compared with ==",
            "test for absence with `is nothing`",
            path=path)

    if is_num(a) and is_num(b):
        return Number.of(a) == Number.of(b)

    if isinstance(a, bool) != isinstance(b, bool):
        raise PlanesError(
            "cannot-compare",
            f"cannot compare {detail_value(a)} with {detail_value(b)}",
            "compare a yes/no value with a yes/no value",
            path=path)
    if isinstance(a, bool):
        return a is b

    if type(a) is not type(b):
        raise PlanesError(
            "cannot-compare",
            f"cannot compare {detail_value(a)} with {detail_value(b)}",
            "compare numbers with numbers, or text with text",
            path=path)

    if isinstance(a, str):
        return a == b

    if isinstance(a, list):
        if len(a) != len(b):
            return False
        for i, (x, y) in enumerate(zip(a, b)):
            if not equal(x, y, path + [i]):    # raises, with the path, on type mismatch
                return False
        return True

    if isinstance(a, dict):
        if set(a) != set(b):
            raise PlanesError(
                "cannot-compare",
                f"records have different fields: "
                f"{sorted(set(a) ^ set(b))}",
                "compare records with the same fields",
                path=path)
        return all(equal(a[k], b[k], path + [k]) for k in a)

    return a == b


def condition(v):
    """What `if` and `where` accept. A yes/no value, and nothing else."""
    if isinstance(v, bool):
        return v
    raise PlanesError(
        "not-a-yes-no",
        f"a condition needs a yes/no value, found {detail_value(v)}",
        "compare it: `if count of items > 0:`")


def require_text(name, verb, v):
    """The guard `lower`, `upper`, and `normalize` share (C2, A.6 family 2).

    Each of the three used to hand its argument to the host's own string
    conversion — `str()` here, `String()` in JavaScript — so `lower of [1, 2]`
    answered `'[1, 2]'` on one implementation and `'1,2'` on the other. Ten
    cases where both were confidently wrong in the same way, and the answer
    depended on which host ran the program.

    They refuse instead, naming `text of`. The chain was already consistent
    on this everywhere else — `+` does not coerce, ordering across types
    errors naming both operands, `join` refuses a non-text element — so an
    explicit conversion exists and implicit coercion bought nothing but the
    loss of a value's type. `verb` is separate from `name` so the sentence
    reads ("cannot lowercase") while the fix names the builtin ("lower of").
    """
    if not isinstance(v, str):
        raise PlanesError(
            "not-text", f"cannot {verb} {detail_value(v)}",
            f"{name} takes text; convert first — e.g. {name} of (text of n)")


def require_target(what, spelled, v):
    """The guard on an effect's target: a url, a path, a write destination.

    `ask`, `read`, and `write ... to` used to hand the value straight to the
    host, so a non-text target reached a host primitive and failed in the
    host's words — `open(5, "w")` opens file descriptor 5, and a TestHost
    keyed by path raised a bare `unhashable type` on a list. C2 refuses at
    the language boundary instead, where the message can name the fix.
    """
    if not isinstance(v, str):
        raise PlanesError(
            "not-text", f"{what} must be text, found {detail_value(v)}",
            f"wrap it with text of — `{spelled}`")


def detail_value(v):
    """How a value is written when it appears in an error detail.

    The rule, and it is the same in all three implementations: **write the
    value as the language would write it when writing it is bounded, and name
    its shape when it is not.**

    * text — as a quoted Planes literal, escaped. `fmt` renders text bare (it
      is what `show` prints), so `whole of "5"` used to report `cannot take the
      whole part of 5`, which reads as a number and is the one thing the
      message is about. The quotes are the whole fix: Planes has one string
      syntax, so a quoted value is unambiguously text.
    * number, boolean, nothing — the literal, which `fmt` already gives.
    * list, record — the *shape* (`[2 items]`, `{record}`), not the contents.
      Two reasons, and both are why this does not simply defer to the canonical
      form: an error detail must be bounded, and a canonical render of a
      10,000-item list or a record holding a credential puts unbounded — and
      possibly sensitive — data into text that goes to stderr and into logs.

    C2 applied this at two sites and reported the other four. This is the
    convergence: every site that puts a value into an error detail goes through
    here, `js/interp.mjs` has the same function, and
    `grammar/interp.planes`'s `detail-of-value` is the third. The self-hosted
    interpreter had been reusing `canonical-of-value` — its *test-oracle* form —
    for error details, which is where the divergence came from; that form is
    unchanged and still the oracle.
    """
    if isinstance(v, str):
        return f'"{escape_string_literal(v)}"'
    return fmt(v)


def param_list(params):
    """The ` of a, b` tail of a declaration, empty when it takes none. Used by
    the arity messages, which name the parameters rather than only counting
    them: a count leaves an author counting commas, and the declared names say
    which values are wanted and in what order."""
    return f" of {', '.join(params)}" if params else ""


def call_shape(name, params):
    """The call a declaration wants, each parameter standing in for its value:
    `f of a, b`, or a bare `f` for a function that takes nothing."""
    return f"{name} of {', '.join(params)}" if params else name


# ================================================================ errors

class PlanesError(Exception):
    """A program error, with the fix clause the language commits to naming.

    `no_fix` (C2) is the other half of that commitment: a reason, in words,
    why *this* site names none. Two shapes qualify and no others — a message
    the language did not write (`fail`'s own text, an `or fail` re-tag of a
    caught error), and a gate too generic to know what the author meant
    (`expect`). It is never rendered, so a message stays byte-identical
    across implementations; it exists so `grammar_gen.py` records the reason
    at the raise site and `errors_coverage.py` can tell a deliberate silence
    from a gap. Marked, never silent — an unexplained absence still counts
    against the commitment.
    """

    def __init__(self, tag, detail="", fix="", path=None, no_fix=None):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        self.path = path      # list-index/record-field steps to a comparison
                              # mismatch, or None when not applicable (§109)
        self.no_fix = no_fix
        msg = tag
        if detail:
            msg += f": {detail}"
        if fix:
            msg += f"\n  try: {fix}"
        super().__init__(msg)


class _Give(Exception):
    def __init__(self, value):
        self.value = value


# ================================================================ the record plane

# Bumped when the meaning of a field changes. A reader that does not
# recognise the version refuses the document rather than guess — the same
# contract shapes_cli.py's JSON output documents (FORMAT_VERSION there).
RECORD_FORMAT_VERSION = 1


@dataclass(frozen=True)
class Anchor:
    """Who owned the boundary a record crossed (§97).

    `kind` alone carries witnessed-vs-claimed — no separate boolean:
    "host" is a witnessed crossing (the host performed it and returned);
    "foreign-declaration" is a claim (declared by whoever wrote the
    `doing` clause, not verified by the analyser or the host).
    """
    kind: str
    identity: str


@dataclass(frozen=True)
class Record:
    """One boundary crossing, formalising the existing effect log (§95-96
    — not a new tracer). Four things: what crossed (kind/boundary/target/
    computed), who owned the boundary (anchor), when (one timestamp — the
    host call's return for a witness, the claim's recording for a claim),
    and which values flowed there (derivation, optional)."""
    kind: str
    boundary: str
    target: str
    computed: bool
    anchor: Anchor
    when: Any
    derivation: Optional[Any] = None
    format: int = RECORD_FORMAT_VERSION


def record_to_dict(r):
    """Per §105, text is code points; a `target` string serializes as its
    code-point sequence — a Python str already is one, so no extra
    encoding step is needed here."""
    return {
        "format": r.format,
        "kind": r.kind,
        "boundary": r.boundary,
        "target": r.target,
        "computed": r.computed,
        "anchor": {"kind": r.anchor.kind, "identity": r.anchor.identity},
        "when": r.when,
    }


def records_to_json(records):
    return {"format": RECORD_FORMAT_VERSION,
            "records": [record_to_dict(r) for r in records]}


def records_from_json(doc):
    """The refuse-don't-guess half of the contract: an unrecognised
    format version is rejected, not silently reinterpreted."""
    version = doc.get("format")
    if version != RECORD_FORMAT_VERSION:
        raise PlanesError(
            "unrecognized-record-format",
            f"record format {version!r} is not {RECORD_FORMAT_VERSION}",
            "regenerate the record with a matching version of planes")
    return doc["records"]


def error_record(e):
    """A caught error, as an ordinary record — discriminated by shape
    (§74), never by type. `path` (A.4) is present only when the error
    carries one; a path step is a Planes number (list index) or the field
    name itself (already a string)."""
    rec = {"tag": e.tag, "detail": e.detail}
    if e.path is not None:
        rec["path"] = [Number.of(p) if isinstance(p, int) else p for p in e.path]
    return rec


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
    def __init__(self, http=None, fs=None, host=None, record=False):
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

        # The record plane (§95-102). `record` toggles it; the toggle must
        # never change self.effects, self.output, or the static surface —
        # that is the whole of §99, and test_record.py's inertness gate is
        # the mechanical check. Recording itself is a host capability: the
        # clock and any persistence are requested from self.host, never
        # performed by the interpreter directly.
        self.record = record
        self.records = []

    @property
    def fs(self):
        """Files this run touched, when the host keeps them in memory."""
        return getattr(self.host, "files", {})

    # ---- the record plane

    def host_anchor(self):
        return Anchor("host", getattr(self.host, "name", "host"))

    def foreign_anchor(self, decl):
        return Anchor("foreign-declaration", decl.name)

    def maybe_record(self, kind, target, anchor, derivation=None, computed=False):
        """Request a record from the host; never perform one as an effect.

        A no-op when `record` is off — the caller always calls this at the
        same point in control flow either way, so the toggle can only ever
        add an entry to `self.records`, never change anything else.
        """
        if not self.record:
            return
        entry = Record(kind=kind, boundary=EFFECT_KINDS.get(kind, "foreign"),
                       target=target, computed=computed, anchor=anchor,
                       when=self.host.clock(), derivation=derivation)
        self.records.append(entry)
        self.host.record(entry)

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
            self.maybe_record("show", text, self.host_anchor(), derivation=v.node)
            return v

        if isinstance(stmt, Why):
            v = self.eval(stmt.expr, env)
            because = self.annotations.get(stmt.expr.name) \
                if isinstance(stmt.expr, Var) else None
            self.output.append(explain(v, because))
            return v

        if isinstance(stmt, If):
            c = self.eval(stmt.cond, env)
            # Block run inlined, not delegated to exec_block: on the recursion
            # spine (a function whose body is an `if`), a per-branch exec_block
            # frame is pure overhead against the ~140 ceiling (§42). Semantics
            # are exec_block's exactly — skip Note, return the last result.
            result = None
            for s in (stmt.then if condition(c.value) else stmt.els):
                if not isinstance(s, Note):
                    result = self.exec_stmt(s, env)
            return result

        if isinstance(stmt, When):
            # Shape dispatch (v5.0 §74), folded in from the former exec_when
            # method (its only caller). A self-hosted `eval` is a NESTED
            # when/else ladder, so every ladder level used to pay an
            # exec_stmt(When) frame AND an exec_when frame; folding halves the
            # per-arm cost — the compounding A.1 is about (§42). Semantics are
            # unchanged: a missing field is no match; a present field of the
            # wrong shape raises through the same guarded equal() `==` uses;
            # bindings land directly in env (the no-child-scope choice if/else
            # already makes); the matched (or else) block runs with Note
            # skipped and its last result carried out.
            subject = self.eval(stmt.subject, env)
            if not isinstance(subject.value, dict):
                raise PlanesError(
                    "not-a-record",
                    f"cannot match {detail_value(subject.value)} against a shape",
                    "when matches record shapes only")
            matched, bindings = True, []
            for fname, (kind, arg) in stmt.pattern:
                if fname not in subject.value:
                    matched = False
                    break
                field_val = subject.value[fname]
                if kind == "match":
                    want = self.eval(arg, env)
                    if not equal(field_val, want.value):
                        matched = False
                        break
                else:
                    bindings.append((fname, field_val))
            if matched:
                for name, val in bindings:
                    env.bind_local(name, Traced(
                        val, Deriv("field", f".{name}", val, [subject.node])))
            result = None
            for s in (stmt.body if matched else stmt.els):
                if not isinstance(s, Note):
                    result = self.exec_stmt(s, env)
            fields = ", ".join(f for f, _ in stmt.pattern)
            label = f"when {{{fields}}} " + ("matched" if matched else "did not match")
            rv = result.value if result is not None else None
            rn = result.node if result is not None else Deriv("literal", "nothing", None)
            return Traced(rv, Deriv("op", label, rv, [subject.node, rn]))

        if isinstance(stmt, Fail):
            v = self.eval(stmt.message, env)
            if not isinstance(v.value, str):
                raise PlanesError(
                    "fail-message-not-text",
                    f"fail's message must be text, found {detail_value(v.value)}",
                    "wrap it with text of")
            raise PlanesError(
                stmt.tag, v.value,
                no_fix="the message is the program's own, written at the "
                       "`fail`; naming a fix here would overwrite what the "
                       "author chose to say")

        return self.eval(stmt, env)

    # ---- expressions

    def eval(self, node, env):
        if isinstance(node, Num):
            return lit(node.value)
        if isinstance(node, Str):
            label = f'"{escape_string_literal(node.value)}"'
            return Traced(node.value, Deriv("literal", label, node.value))
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

        if isinstance(node, RecordUpdate):
            base = self.eval(node.base, env)
            if not isinstance(base.value, dict):
                raise PlanesError(
                    "not-a-record",
                    f"cannot update {detail_value(base.value)} with with",
                    "with updates a record; check the base is one")
            parts = [(k, self.eval(v, env)) for k, v in node.fields]
            new = {**base.value, **{k: t.value for k, t in parts}}
            return Traced(new, Deriv("op", "with", new,
                                     [base.node] + [t.node for _, t in parts]))

        if isinstance(node, ListPlus):
            base = self.eval(node.base, env)
            if not isinstance(base.value, list):
                raise PlanesError(
                    "not-a-list",
                    f"cannot append to {detail_value(base.value)} with plus",
                    "plus appends to a list; check the base is one")
            item = self.eval(node.item, env)
            new = base.value + [item.value]
            return Traced(new, Deriv("op", "plus", new, [base.node, item.node]))

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
                    f"cannot read .{node.name} from {detail_value(obj.value)}",
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
                                  f"cannot round {detail_value(v.value)}",
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
            require_target("a destination to write to",
                           "write value to (text of p)", dest.value)
            payload = to_json(value.value)
            try:
                self.host.write(dest.value, payload)
            except (HostError, OSError) as e:
                # A failed write used to leave the host's own OSError to escape
                # (C2, constraint 6). `read` and `ask` already converted; this
                # is the third boundary, converted in the same voice.
                raise PlanesError(
                    "write-failed", f"writing '{dest.value}' failed: {e}",
                    "check the directory exists and is writable")
            self.effects.append(("write", dest.value, len(payload)))
            self.maybe_record("write", dest.value, self.host_anchor(),
                              derivation=dest.node)
            return Traced(None, Deriv("effect", f"write to {dest.value}", None,
                                      [value.node], origin=f"file:{dest.value}"))

        if isinstance(node, OrFail):
            # The three raises below name no fix of their own, deliberately and
            # for one reason: they do not write a message. Each re-tags a
            # message somebody else wrote — a caught Planes error, or a host
            # exception a `foreign` call raised — under the author's `or fail
            # as` tag. Inventing a fix clause here would attach the language's
            # advice to a failure the language did not diagnose. `no_fix` says
            # so at the raise site, so the catalogue records a decision rather
            # than a gap. The caught error's own `fix` is carried forward
            # (C2): an error that named a fix must not stop naming it because
            # it crossed an `or fail`.
            # The reason is written out at each of the three, not hoisted into a
            # variable, for the same purpose parser.py's `expect` keeps two
            # literal raises: grammar_gen.py reads the catalogue off these call
            # sites, and a reason assembled elsewhere is a reason it cannot see.
            try:
                return self.eval(node.expr, env)
            except _Give:
                raise
            except PlanesError as e:
                if node.handler is not None:
                    return self.run_or_fail_handler(node, e, env)
                raise PlanesError(
                    node.tag, e.detail or e.tag, e.fix, path=e.path,
                    no_fix="re-tags a message this raise did not write; the "
                           "fix belongs to whoever raised it, and is carried "
                           "forward")
            except Exception as e:
                if node.handler is not None:
                    return self.run_or_fail_handler(
                        node,
                        PlanesError(
                            node.tag, str(e),
                            no_fix="re-tags a host exception this raise did "
                                   "not write; a host failure is not "
                                   "something the language can advise on"),
                        env)
                raise PlanesError(
                    node.tag, str(e),
                    no_fix="re-tags a host exception this raise did not "
                           "write; a host failure is not something the "
                           "language can advise on")

        if isinstance(node, ForEach):
            return self.eval_foreach(node, env)

        if isinstance(node, If):
            c = self.eval(node.cond, env)
            # inlined block run (§42), matching exec_stmt's If case above
            result = None
            for s in (node.then if condition(c.value) else node.els):
                if not isinstance(s, Note):
                    result = self.exec_stmt(s, env)
            return result

        # C2 (A.1): a literal, so the catalogue can read it. The four
        # interpreter-invariant guards in this file (this one, `unknown-builtin`,
        # and `unknown-operator` twice) are unreachable from any program the
        # parser accepts — every statement-only construct is refused there as
        # "expected a value". So they name a fix an author can actually act on:
        # report it, because reaching one means the two halves disagree.
        raise PlanesError(
            "cannot-evaluate",
            f"'{type(node).__name__}' has no value — it is a statement, not "
            f"an expression",
            "write it on its own line; reaching this from a program the parser "
            "accepted is a defect in the interpreter, not in the program, and "
            "worth reporting with the source that produced it")

    def eval_binop(self, node, env):
        if node.op == "and":
            left = self.eval(node.left, env)
            if not condition(left.value):
                return Traced(False, Deriv("op", "and", False, [left.node]))
            right = self.eval(node.right, env)
            v = condition(right.value)
            return Traced(v, Deriv("op", "and", v, [left.node, right.node]))

        if node.op == "or":
            left = self.eval(node.left, env)
            if condition(left.value):
                return Traced(True, Deriv("op", "or", True, [left.node]))
            right = self.eval(node.right, env)
            v = condition(right.value)
            return Traced(v, Deriv("op", "or", v, [left.node, right.node]))

        if node.op == "first":
            n = self.eval(node.left, env)
            src = self.eval(node.right, env)
            # C2 (constraint 6): both guards. Neither implementation had them —
            # a non-number count and a non-sequence source each reached a host
            # primitive, and `first 1 of 5` answered with a Python TypeError
            # here and a V8 one there.
            if not is_num(n.value):
                raise PlanesError(
                    "not-a-number",
                    f"the count in `first n of` must be a number, "
                    f"found {detail_value(n.value)}",
                    "write the count as a number — `first 3 of items`")
            if not isinstance(src.value, (str, list, tuple)):
                raise PlanesError(
                    "not-a-collection",
                    f"cannot take the first {detail_value(n.value)} of {detail_value(src.value)}",
                    "`first n of` takes a list or text; a record has no order "
                    "to take a prefix of")
            v = src.value[: int(n.value)]
            return Traced(v, Deriv("op", f"first {int(n.value)} of", v, [src.node]))

        left = self.eval(node.left, env)
        right = self.eval(node.right, env)
        v = apply_op(node.op, left.value, right.value)
        return Traced(v, Deriv("op", node.op, v, [left.node, right.node]))

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
            require_target("a url to ask", "ask (text of u)", url)
            try:
                body = self.host.ask(url)
            except HostError as e:
                # C2 (A.1): the message is a literal here, so the catalogue can
                # read it. The host's own words ride along as the cause — they
                # say which url and why — but the sentence and the fix are the
                # language's.
                raise PlanesError(
                    "ask-failed", f"asking '{url}' failed: {e}",
                    "check the url is reachable and spelled right; a run "
                    "without the network needs a stubbed response")
            self.effects.append(("ask", url, len(body)))
            self.maybe_record("ask", url, self.host_anchor(), derivation=arg.node)
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
            require_target("a path to read", "read (text of p)", path)
            try:
                body = self.host.read(path)
            except HostError:
                raise PlanesError("no-such-file", path,
                                  "check the path, or write it first")
            self.effects.append(("read", path, len(body)))
            self.maybe_record("read", path, self.host_anchor(), derivation=arg.node)
            return Traced(body, Deriv("effect", f"read {path}", body,
                                      [arg.node], origin=f"file:{path}"))

        if node.name == "count":
            # C2 (A.6, family 1): the guard. `len()` on a number, a boolean, or
            # nothing raised a bare Python TypeError — a host exception escaping
            # into a Planes program, which is the most complete failure of the
            # fix-clause commitment there is. js/interp.mjs already refused;
            # this now refuses in the same words.
            if not isinstance(arg.value, (str, list, tuple, dict)):
                raise PlanesError(
                    "not-a-collection", f"cannot count {detail_value(arg.value)}",
                    "count takes a list, a record, or text — check which of "
                    "those this value should be")
            v = Number.of(len(arg.value))
            return Traced(v, Deriv("op", "count of", v, [arg.node]))
        if node.name == "lower":
            require_text("lower", "lowercase", arg.value)
            v = arg.value.lower()
            return Traced(v, Deriv("op", "lower of", v, [arg.node]))
        if node.name == "upper":
            require_text("upper", "uppercase", arg.value)
            v = arg.value.upper()
            return Traced(v, Deriv("op", "upper of", v, [arg.node]))
        if node.name == "whole":
            if not is_num(arg.value):
                raise PlanesError(
                    "not-a-number",
                    f"cannot take the whole part of {detail_value(arg.value)}",
                    "whole of rounds a number toward zero; Planes has no "
                    "text-to-number builtin, so a number has to arrive as "
                    "one — from a literal, from arithmetic, or from a field "
                    "of something read as JSON")
            n = Number.of(arg.value).round_to(0)
            return Traced(n, Deriv("op", "whole of", n, [arg.node]))

        if node.name == "text":
            v = fmt(arg.value)
            return Traced(v, Deriv("op", "text of", v, [arg.node]))
        if node.name == "normalize":
            require_text("normalize", "normalize", arg.value)
            v = unicodedata.normalize("NFC", arg.value)
            return Traced(v, Deriv("op", "normalize of", v, [arg.node]))
        if node.name == "join":
            # Fold a list of text into one string in O(n) — the answer to the
            # O(n^2) repeated-`+` build the sweep measured (S2 §A.2). No
            # coercion: a non-text element is an error naming the fix, the same
            # refusal `+` makes (§12-era), not a silent stringify. An empty
            # list joins to the empty string, not an error.
            if not isinstance(arg.value, list):
                raise PlanesError(
                    "cannot-join",
                    f"cannot join {detail_value(arg.value)}",
                    "join takes a list of text; check the value is a list")
            for x in arg.value:
                if not isinstance(x, str):
                    raise PlanesError(
                        "cannot-join",
                        f"join needs a list of text, found {detail_value(x)}",
                        "convert each item first — e.g. text of n")
            v = "".join(arg.value)
            return Traced(v, Deriv("op", "join of", v, [arg.node]))
        if node.name == "rest":
            # The list without its first element (S2 §A.3). Lists only — a
            # string wants `first n of` (#11's declined `rest n of x` for text
            # stands). The rest of an empty list is an error, not a silent
            # empty list: a tail taken past the end is a bug at the call site,
            # and the empty result would hide it. `arg.node` rides in the
            # Deriv, so origins() traces the tail back to the source list.
            if isinstance(arg.value, str):
                raise PlanesError(
                    "not-a-list",
                    f"cannot take the rest of text {detail_value(arg.value)}",
                    "rest is for lists; for a text prefix use `first n of`")
            if not isinstance(arg.value, list):
                raise PlanesError(
                    "not-a-list",
                    f"cannot take the rest of {detail_value(arg.value)}",
                    "rest takes a list; check the value is a list")
            if not arg.value:
                raise PlanesError(
                    "empty-list",
                    "cannot take the rest of an empty list",
                    "check it is not empty first, e.g. `if count of xs > 0:`")
            v = arg.value[1:]
            return Traced(v, Deriv("op", "rest of", v, [arg.node]))

        raise PlanesError(
            "unknown-builtin", f"no builtin is named '{node.name}'",
            "the ten builtins are fixed and the lexer recognises only those, "
            "so reaching this is a defect in the interpreter rather than in "
            "the program — worth reporting with the source")

    def run_or_fail_handler(self, node, error, env):
        """Bind `node.tag` to `error`, as a record, and run the handler.

        No child scope: an `or fail as` handler runs in the same env an
        `if`/`else` body does (exec_stmt's If case), so a name the handler
        assigns is visible afterward exactly the way an if-branch's is.
        """
        rec = error_record(error)
        bound = Traced(rec, Deriv("record", "{record}", rec, []))
        env.bind_local(node.tag, bound)
        return self.exec_block(node.handler, env)

    def eval_foreach(self, node, env):
        source = self.eval(node.source, env)
        if not isinstance(source.value, (list, tuple, str)):
            raise PlanesError("not-a-collection",
                              f"cannot loop over {detail_value(source.value)}",
                              "for each needs a list, or a string to walk its code points")
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

        if name in self.funcs:
            fn, iname = self.funcs[name], name
        else:
            # A renamed function keeps working inside the file that defines
            # it: importers see the new name, the module sees its own.
            fn = next((f for f in self.funcs.values() if f.local == name), None)
            if fn is None:
                raise PlanesError("unknown-function",
                                  f"no function named '{name}'",
                                  f"define it: to {name}: ...")
            iname = fn.local or fn.name

        # invoke folded in (was its own method, called only from here): its
        # frame was pure overhead on the recursion spine (call -> invoke), and
        # exec_block(fn.body) was a second such frame. Both are inlined below
        # with semantics unchanged — arity check, a child scope binding each
        # parameter, the body run with Note skipped, _Give caught as the
        # return value, RecursionError narrowed to this body (§42).
        if len(args) != len(fn.params):
            word = "value" if len(fn.params) == 1 else "values"
            # C2: the fix names the parameters. The count alone leaves an author
            # counting commas; the declared names say which values are wanted
            # and in what order, and `call_shape` renders the call to write.
            raise PlanesError(
                "wrong-arity",
                f"'{iname}' takes {len(fn.params)} {word}, given {len(args)}",
                f"it is declared `to {iname}{param_list(fn.params)}`, so call "
                f"it as `{call_shape(iname, fn.params)}`")
        arg_vals = [a if isinstance(a, Traced) else self.eval(a, env)
                    for a in args]
        inner = Env(fn.env)
        for p, a in zip(fn.params, arg_vals):
            inner.bind_local(p, Traced(a.value, Deriv("name", p, a.value, [a.node])))
        try:
            for s in fn.body:
                if not isinstance(s, Note):
                    self.exec_stmt(s, inner)
            return Traced(None, Deriv("call", iname, None,
                                      [a.node for a in arg_vals]))
        except _Give as g:
            return Traced(g.value.value,
                          Deriv("call", iname, g.value.value,
                                [g.value.node] + [a.node for a in arg_vals]))
        except RecursionError:
            # Narrow on purpose: only around the recursive re-entry through
            # this function's own body, so a RecursionError raised inside a
            # host method for unrelated reasons is never mistaken for depth
            # exhaustion (unbound v3.0 §42 — the observable failure is
            # identical, and the cheaper implementation wins).
            raise PlanesError(
                "recursion-too-deep",
                f"'{iname}' recursed past the depth this interpreter can follow",
                "replace per-item recursion with one `for each` pass over "
                "the whole collection, threading a state record forward; "
                "for nested structure, track depth with a cons-list stack "
                "sized to nesting depth, not item count")

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
                f"given {len(args)}",
                f"it is declared `foreign {decl.name}"
                f"{param_list(decl.params)} from \"{decl.target}\"`, so call "
                f"it as `{call_shape(decl.name, decl.params)}`")

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
            dest_node = None
            if where is not None:
                if where[0] == "literal":
                    dest = where[1]
                elif where[0] == "param" and where[1] in decl.params:
                    i = decl.params.index(where[1])
                    if i < len(arg_vals):
                        dest = fmt(arg_vals[i].value)
                        dest_node = arg_vals[i].node
            self.effects.append((kind, dest))
            # A claim, anchored to the declaration — recorded here, before
            # the call, regardless of whether it goes on to raise (§97).
            # This is the one site that must never move: the append above
            # is correct for a claim precisely because it is pre-invoke,
            # and the record beside it inherits that same reasoning.
            self.maybe_record(kind, dest, self.foreign_anchor(decl),
                              derivation=dest_node)

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



def apply_op(op, a, b):
    if op == "+":
        if isinstance(a, str) and isinstance(b, str):
            return a + b
        if isinstance(a, list) and isinstance(b, list):
            return a + b
        if is_num(a) and is_num(b):
            return arith("+", a, b)
        raise PlanesError(
            "cannot-combine",
            f"cannot combine {detail_value(a)} with {detail_value(b)} using +",
            "convert first — e.g. \"total: \" + text of n")
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
    if op == "in": return membership(a, b)
    raise PlanesError(
        "unknown-operator", f"no operator is spelled '{op}'",
        "the parser builds only the operators the language defines, so "
        "reaching this is a defect in the interpreter rather than in the "
        "program — worth reporting with the source")


def is_num(v):
    return isinstance(v, (Number, int)) and not isinstance(v, bool)


def loose_equal(a, b):
    """The comparison membership uses: guarded equality's rules, without its
    refusals.

    `x in xs` asks whether an equal element is present, and a differently-typed
    element is an *answer* (no) rather than a mistake — unlike `==`, where a
    cross-type comparison is a bug worth naming. Python's `in` went through
    `Number.__eq__`, which refuses a boolean, so `true in [1, 2]` leaked
    planes_num's own `TypeError: a yes/no value is not a number` into the
    program. A port of `js/interp.mjs`'s `looseEqual`, arm for arm and in the
    same order.
    """
    if is_num(a) and is_num(b):
        return Number.of(a) == Number.of(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if a is None or b is None:
        return a is b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            loose_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(loose_equal(a[k], b[k]) for k in a)
    return False


def membership(a, b):
    """`a in b` — over a list, a record's field names, or text.

    Guarded on both operands (C2, constraint 6). `b` had no guard at all:
    `1 in 5` raised a Python TypeError here and answered `unknown-operator` in
    JavaScript, which named the wrong thing — `in` is an operator the language
    defines; what was wrong was the value on the right. And a text container
    had no guard on `a`: Python refused `1 in "ab"` with a TypeError while V8
    coerced the 1 to "1", so `1 in "a1b"` would have answered true on one host
    and raised on the other.
    """
    if isinstance(b, str):
        if not isinstance(a, str):
            raise PlanesError(
                "not-text", f"cannot look for {detail_value(a)} in text {detail_value(b)}",
                "`in` over text looks for text — wrap the left side with "
                "text of")
        return a in b
    if isinstance(b, dict):
        # A record's field names are text, so a candidate that is not text is
        # simply absent — not an error, and not the host's `unhashable type`
        # (which is what `[1] in { a: 1 }` used to raise). js/interp.mjs's
        # `b.has(a)` already answered false.
        return isinstance(a, str) and a in b
    if isinstance(b, (list, tuple)):
        return any(loose_equal(a, x) for x in b)
    raise PlanesError(
        "not-a-collection", f"cannot look inside {detail_value(b)}",
        "`in` looks inside a list, a record's field names, or text")


def arith(op, a, b):
    """Exact arithmetic. Non-numbers get an error that names the value."""
    for v in (a, b):
        if not is_num(v):
            raise PlanesError(
                "not-a-number",
                f"cannot use '{op}' on {detail_value(v)}",
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
    raise PlanesError(
        "unknown-operator", f"'{op}' is not an arithmetic operator",
        "arithmetic is + - * /; reaching this means apply_op routed an "
        "operator here that it does not itself arithmetic on, which is a "
        "defect in the interpreter rather than in the program")


def _order_kind(v):
    """What `<` can order: text with text, or a number with a number. Anything
    else is "other" and cannot be ordered at all."""
    if isinstance(v, str):
        return "str"
    return "num" if is_num(v) else "other"


def compare(op, a, b):
    """Ordering comparisons work on numbers and on text — and, now, on nothing
    else.

    The docstring said that before it was true. The guard was
    `type(a) is not type(b)`, which let a SAME-kind pair through to the host's
    own `<`: `[1] < [2]` answered `true` by way of Python's list comparison,
    `true < false` answered `false`, and a record pair and `nothing < nothing`
    each leaked a raw `TypeError`. Four accidents of the host, none of them the
    language, and the answer depended on which host ran the program.
    `js/interp.mjs` already refused all four — so this is Python catching up,
    the same direction A.6's family 1 went.
    """
    if _order_kind(a) != _order_kind(b) or _order_kind(a) == "other":
        raise PlanesError(
            "cannot-compare",
            f"cannot compare {detail_value(a)} with {detail_value(b)}",
            "compare numbers with numbers, or text with text")
    if is_num(a):
        a, b = Number.of(a), Number.of(b)
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
        text += f'\n  because "{escape_string_literal(because)}"'
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
            lines.append("  " * (depth + 1) +
                         f'because "{escape_string_literal(because)}"')
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
