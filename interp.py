"""Planes evaluator — values, provenance, effects."""
import hashlib
import json
import os
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

import world_ir
import world_source_map
from host import Host, HostError, PythonHost, TestHost
from lexer import *
from parser import BUILTIN_NAMES, find_discarded_writes, parse
from planes_num import Inexact, NotANumber, Number, number_from_text, root_of, sine_degrees
from planes_text import escape_string_literal


class _BuiltinName:
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name


# ================================================================ values

@dataclass
class Deriv:
    """One node in a derivation graph. Provenance lives here, not in types.

    The last three fields are R1's (checkpoint v28.0 §441): `generation` is
    a construction-order stamp every node gets; `released_count` and
    `fingerprint` are set only on a seal (kind="seal"), the node a
    retention window cuts a chain down to. A seal is otherwise an ordinary
    Deriv — empty inputs, a value, a label — so render/origins/why_tree/
    approximationsIn need no seal-specific case to walk one.
    """
    kind: str                                  # literal|name|op|call|field|effect|...
    label: str
    value: Any
    inputs: list = field(default_factory=list)
    origin: Optional[str] = None               # where this entered the program
    generation: int = 0
    released_count: Optional[int] = None
    fingerprint: Optional[str] = None


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
            "test for absence with `is nothing` — if the nothing is inside "
            "a compared list or record rather than the whole value (the "
            "path names which), test that inner value with `is nothing` "
            "directly rather than rewriting the whole comparison",
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
            "compare same-kind values — numbers with numbers, text with "
            "text, lists with lists (compared element by element), or "
            "records with records (compared field by field)",
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
        "compare it against something explicit rather than a bare value — "
        "e.g. `if count of items > 0:` for an if, `x > 0 and y` for an "
        "and/or operand, or `for each x in xs where x > 0:` for a where "
        "clause")


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
            "regenerate the record with a version of planes matching this "
            "interpreter's record format — if the record is newer than "
            "what this interpreter reads, upgrade planes instead of "
            "regenerating the record")
    return doc["records"]


def error_record(e):
    """A caught error, as an ordinary record — discriminated by shape
    (§74), never by type.

    ONE CONVENTION FOR AN ABSENT FIELD (C5, Ruling 3). `fix` (§158) and `path`
    (A.4) are both always present and both `nothing` when they do not apply.
    The record carried two conventions for one job until this build, and the
    deciding argument is not symmetry — it is that absence-as-meaning is a
    silent signal. A field not in the subject sets matched = False (`When`
    below), so `when e is { path }:` fell to the else branch for every error
    without a path, and an author could not tell that from failing to match an
    error record at all. Same shape as `[1] < [2]` answering `true`: a
    confident wrong turn where a refusal belongs.

    Planes already has an explicit way to say absent — `nothing`, with
    `is nothing` to test it. Using structural absence for the same job
    duplicates it and does it worse.

    A path that does apply is unchanged: the same steps, each a Planes number
    (list index) or the field name itself (already a string). An empty path is
    an empty list and not `nothing` — a top-level mismatch has a path, and it
    has no steps."""
    return {
        "tag": e.tag,
        "detail": e.detail,
        "fix": e.fix or None,
        "path": None if e.path is None else
        [Number.of(p) if isinstance(p, int) else p for p in e.path],
    }


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
    # The file this function was DEFINED in, as the loader's own key, or None
    # for a single-file program. `trace_line` uses it to report lines in the
    # source the caller handed over rather than in a module the reader is not
    # looking at. A field rather than an attribute set after construction:
    # this dataclass declares slots, so an ad-hoc attribute is silently lost.
    file: Optional[str] = None


@dataclass
class WorldEmission:
    """One `show` that produced a valid world-v1 envelope (Build 2, §3).

    Interpreter-level OBSERVATION, the same plane `self.trace` occupies —
    not a language feature, nothing a program can read, and appending one
    performs nothing. `raw` is the envelope in the native-host form
    `world_ir.parse_world_envelope` actually validated (Number already
    converted to int/float, Map/dict already converted to dict — see
    `to_host`); `normalized` and `warnings` are that call's own return
    value, kept rather than recomputed so a consumer never re-derives what
    the interpreter already knows to be true. `node` is the shown value's
    own Deriv, so a world record's provenance is exactly the provenance the
    program's own computation already built (§3 requirement 3) — nothing
    about emission constructs a second derivation for the same value.
    """
    raw: dict
    normalized: dict
    warnings: list
    node: Deriv
    source_line: int


def seal_refusal(generation, snapshot):
    """The fixed sentence a seal names (R1 §5) — true because Planes is
    deterministic and pure: history behind a seal is not lost, only
    compressed to a seed that a deterministic replay from `snapshot`
    recovers exactly. Byte-identical across implementations by construction
    — both build it from the same template with the same two values."""
    return (f"history before generation {generation} was released; "
            f"deterministic replay from snapshot {snapshot} recovers it "
            f"exactly.")


# ================================================================ interpreter

def real_http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "planes/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode()


class Interpreter:
    def __init__(self, http=None, fs=None, host=None, record=False, window=None,
                 trace=True):
        self.env = Env()
        self.funcs = {}
        self.foreigns = {}       # name -> Foreign declaration
        self.modules = set()
        # Every line the program produced, in order — and a SUPERSET of what
        # the host was asked to emit, which is the one thing to know before
        # reading it. `show` lands here AND goes to `host.show`; `why` lands
        # here ONLY, because a derivation query is not an effect and logs none.
        #
        #     show "a" ; why x   ->  output  ['a', '5 from 5']
        #                            host    ['a']
        #                            effects [('show', 'a')]
        #
        # So an embedder printing `output` while running on a host that also
        # prints doubles every `show`; one that prints neither loses every
        # `why`. planes.py hit the first of those — see its `CliHost`.
        self.output = []
        # One entry per line in `output`, in the same order and always the same
        # length: (derivation, source line) for the expression that produced
        # it. Interpreter-level OBSERVATION, like `effects` — not a language
        # feature, nothing a program can read, and it performs nothing: the
        # node is the one `eval` already built, kept rather than dropped.
        #
        # WHY IT IS HERE AND NOT IN `effects`. The effect log records that a
        # `show` happened and with what text; it has never carried where the
        # text came from. The record plane (§95-102) does carry it — Show hands
        # `v.node` to `maybe_record` below — but that plane is off unless
        # `record=True` and is forbidden from changing `output`, `effects` or
        # the surface, so a page cannot turn it on to ask a question. This is
        # the third thing, and it is the smallest one that answers "which
        # expression drew this line".
        #
        # Per run and replaced, never accumulated: a page constructs one
        # Interpreter per tick, so this is per frame by construction.
        self.trace = []
        # WHICH FILE A LINE IS IN. The trace's line has to name a line in the
        # source the CALLER handed over, or it is worse than nothing: a page
        # showing garden.planes and highlighting line 45 of draw.planes points
        # the reader at a file that is not on their screen. So each Function
        # remembers the file it was defined in, `current_file` tracks whose
        # body is running, and `call_sites` records where each active call was
        # WRITTEN. A `show` inside a helper then reports the innermost call
        # site written in the entry file — which for `circle of x, y, r` is
        # exactly the line the reader clicked on.
        #
        # A single-file program is unaffected: current_file and entry_file are
        # both None, so a `show` reports its own line, exactly as before.
        self.current_file = None
        self.entry_file = None
        self.call_sites = []
        self.effects = []            # ordered record of what the program did
        self.annotations = {}        # name -> latest `because` text, display-only

        # Horizon Phase 0 Build 2, Phase 1 (build prompt §3, spec §9.2): a
        # typed world envelope for every `show` of a value shaped like one,
        # riding BESIDE `effects`/`output` rather than replacing anything in
        # them — this list is the only thing Show adds to. Populated by
        # `_maybe_emit_world_envelope` below, which never touches `effects`,
        # `output`, or `trace`, so a program with no world content produces
        # an empty list here and is otherwise unaffected (§N+1 invariant 2).
        self.world_envelopes = []

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

        # The retention window (R1, checkpoint v28.0 §441). `window` is
        # host-supplied, in the memory math's own unit (a count of
        # Deriv nodes — REPORT_UPDATE_COST.md §5.4). None (the default)
        # means unbounded: `mk` and `_cut` below skip straight past every
        # window check, so an unbounded run allocates no seal and costs no
        # more than HEAD did — invariant 2 (§N+1) holds by construction,
        # not by a separate code path re-implementing HEAD's behaviour.
        self.window = window
        self._generation = 0
        self._pinned = {}           # id(Deriv) -> Deriv, kept alive by pin()

        # The tracing-off fast path (R3, checkpoint v30.0 §466-476). `trace`
        # defaults to True — HEAD behavior, exactly: every Deriv `mk` builds
        # is real, stamped, and (when a window is set) cut, precisely as
        # before this field existed. False is opt-in, for a host that wants
        # to run without paying the derivation-graph cost on every tick —
        # `mk` below is the one place that reads it (Ruling 2: the toggle
        # lives in mk, not threaded through every eval arm). `_untraced` is
        # ONE shared, never-mutated Deriv, returned by every `mk` call while
        # tracing is off — not a fresh object per call — so a tracing-off
        # run allocates no per-node Deriv graph at all (§N+3.4 measures
        # this). `Traced.value` still carries the real per-call value; only
        # the derivation graph is skipped. A `why` (any register) asked
        # about a value built this way finds `_untraced` and nothing else —
        # answering it is what `replay` (§5 below) is for.
        self.tracing = trace
        self._untraced = Deriv("untraced", "", None)

        # The record plane's effect log (R3, §7): the fast-path run's own
        # record of what each effect actually returned, so a later replay
        # can read an effect back instead of re-performing it. Piggybacked
        # on the EXISTING `record` toggle rather than a third flag — a
        # replay that needs this is required to have run the fast path with
        # `record=True` (stated as a dependency in REPORT_REPLAY.md), the
        # same way `self.records` already depends on it. Populated only for
        # the four host effects a program can trigger directly (show,
        # write, ask, read) — `call_foreign` is a claim against an
        # arbitrary host function, not one of the five required
        # capabilities, and is out of R3's replay scope (documented in the
        # report, not silently dropped).
        self.effect_log = []

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

    def log_effect(self, kind, target, result):
        """R3, §7: append this effect's ACTUAL result to `effect_log`, so a
        later replay can read it back rather than re-perform the effect.
        Gated on `self.record`, the same toggle `maybe_record` above
        already reads — a replay that needs this log requires the
        fast-path run to have set `record=True` (REPORT_REPLAY.md states
        the dependency). A no-op otherwise, so this can only ever add to
        `effect_log`, never change output/effects/records/the surface —
        the same inertness `maybe_record` itself keeps."""
        if not self.record:
            return
        self.effect_log.append((kind, target, result))

    # ---- the retention window (R1)

    def mk(self, kind, label, value, inputs=None, origin=None):
        """Build a Deriv, stamped with the next generation. Every Deriv in
        this file is built through here (not through the dataclass
        directly) so the stamp — and, when a window is set, the cut below —
        apply uniformly, with no operation-kind special case.

        R3 (§466-476): the first check, ahead of even the generation stamp
        — tracing off returns the one shared `_untraced` node and does
        nothing else, exactly as `window=None` already makes the window
        check below a no-op. No generation is spent and no Deriv is
        allocated, so a tracing-off run costs nothing this function did not
        already cost on HEAD before this build."""
        if not self.tracing:
            return self._untraced
        gen = self._generation
        self._generation += 1
        node = Deriv(kind, label, value, list(inputs) if inputs else [],
                     origin, generation=gen)
        if self.window is not None:
            self._cut(node)
        return node

    def mk_lit(self, v, label=None):
        return Traced(v, self.mk("literal", label if label is not None else fmt(v), v))

    def pin(self, traced_or_node):
        """Keep a specific derivation reachable past the window (§6).

        `self._pinned` holds a direct, strong reference to the node — an
        independent root the interpreter's own bookkeeping keeps alive,
        the same way a still-bound `env` variable keeps a value alive
        today, not a flag that changes how `_cut` treats every OTHER edge
        that happens to pass through it. That is what keeps a pin cheap
        and local: `_cut` is still free to seal the live chain's own edge
        to a pinned node — cutting one path to it does not lose it, since
        `self._pinned` is a second, independent path — so pinning one
        derivation never blocks the window from continuing to bound
        everything built after it. Pure bookkeeping otherwise — an id in a
        dict — so it can never change output, effects, or the static
        surface (v6.0's annotation-plane inertness, the discipline
        test_record.py's inertness gate checks for the record plane).
        Returns the pinned node.
        """
        node = traced_or_node.node if isinstance(traced_or_node, Traced) \
            else traced_or_node
        self._pinned[id(node)] = node
        return node

    def _cut(self, node):
        """Apply the window to `node`'s own reachable inputs, in place.

        Age is measured against `node.generation` — ONE fixed reference
        point for the whole call, not each intermediate ancestor's own
        generation. That distinction matters: a chain a `with`/`plus` loop
        builds links each new step to the one immediately before it, one
        generation apart, always — so checking an ancestor's age against
        its DIRECT parent's generation would never see more than 1 and
        would never cut anything. Checked against `node`'s own generation
        instead, an ancestor many steps behind the node actually being
        built reads as exactly that old, however many links away it is.

        A pinned input is left exactly as it is — not replaced, and its
        own inputs not descended into either, so its derivation stays
        whole from the moment it was pinned. Everything else old enough is
        replaced by a seal. Mutating an existing node's `inputs` here is
        safe: it changes only PROVENANCE, never the node's `value`, which
        is set once and never touched — so no output, effect, or static
        surface can differ because a cut happened (§N+1 invariant 2's twin
        for the windowed case).

        Iterative, not recursive: an unpinned linear chain — the shape a
        long-running `with`/`plus` loop actually builds — is a Deriv graph
        thousands of nodes deep, and a recursive walk over it would exceed
        Python's call-stack depth long before the window ever needed to
        cut anything. Discover the whole reachable subgraph once with an
        explicit stack, then rebuild each node's `inputs` deepest-first,
        so a parent's decision always sees its child's already-finished
        result. In practice this discovers at most one window's worth of
        nodes before hitting a leaf, a pin, or an already-placed seal —
        each of which stops discovery cold — which is what keeps the
        per-call cost bounded rather than growing with total history: the
        previous call already pushed a seal in place just past the window
        boundary.
        """
        if node.kind == "seal" or id(node) in self._pinned:
            return
        current = node.generation
        order = []
        stack = [node]
        seen = {id(node)}
        while stack:
            n = stack.pop()
            order.append(n)
            if n.kind == "seal" or id(n) in self._pinned:
                continue
            for inp in n.inputs:
                if id(inp) not in seen:
                    seen.add(id(inp))
                    stack.append(inp)
        for n in reversed(order):
            if n.kind == "seal" or id(n) in self._pinned:
                continue
            changed = False
            new_inputs = []
            for inp in n.inputs:
                if inp.kind == "seal" or id(inp) in self._pinned:
                    new_inputs.append(inp)
                elif current - inp.generation > self.window:
                    new_inputs.append(self._seal(inp))
                    changed = True
                else:
                    new_inputs.append(inp)
            if changed:
                n.inputs = new_inputs

    def _seal(self, root):
        """Replace `root`'s own chain with a seal: the value at the cut,
        the generation it cut at, how many steps it releases, and a
        fingerprint over a canonical, deterministic text of what is
        released.

        Two iterative passes, not a recursive walk (see `_protected`'s
        note): the first assigns every reachable node a stable index in
        first-discovery order (a stack, so both implementations visit in
        the identical order given the identical graph); the second emits
        one line per node — kind, label, value, origin, and its inputs'
        already-known indices — so the whole DAG, sharing included, is a
        flat, order-independent-to-write text. Same program, same
        traversal order in both langs, so the same text, and so the same
        fingerprint — extending the corpus's byte-identical-agreement
        discipline to the released subgraph, not only to output.

        NOT memoized across calls, deliberately: `id()` is a memory
        address, and Python is free to reuse one once its object is
        collected — which `root` becomes eligible for the moment nothing
        else references it, exactly the case a seal exists to create. A
        cache keyed on `id(root)` without holding `root` alive would, once
        that address was reassigned to an unrelated later node, hand back
        a stale seal for the wrong subgraph — found live in this build:
        window=5 over a 200-line chain produced a Python seal stuck at
        generation 19 while JavaScript's (correct; its ids never repeat)
        advanced to 595. Each call here walks only what is still
        reachable and not already behind an earlier seal, so the repeat
        cost this would have saved is small and only ever paid when the
        SAME node is independently discovered stale from more than one
        surviving path — the DAG-sharing case, not the common linear one.
        """
        order = {}
        seq = []
        stack = [root]
        while stack:
            n = stack.pop()
            if id(n) in order:
                continue
            order[id(n)] = len(order)
            seq.append(n)
            if n.kind != "seal":
                for inp in n.inputs:
                    if id(inp) not in order:
                        stack.append(inp)
        count = 0
        parts = []
        for n in seq:
            if n.kind == "seal":
                # A prior cut, absorbed rather than re-walked: its own
                # released_count folds in, and its fingerprint stands for
                # everything it already summarized.
                count += n.released_count
                parts.append(f"seal\x1f{n.generation}\x1f{n.fingerprint}")
                continue
            count += 1
            children = ",".join(str(order[id(i)]) for i in n.inputs)
            parts.append(
                f"{n.kind}\x1f{n.label}\x1f{fmt(n.value)}\x1f"
                f"{n.origin or ''}\x1f{children}")
        fingerprint = hashlib.sha256(
            "\n".join(parts).encode()).hexdigest()[:12]
        seal = Deriv("seal", seal_refusal(root.generation, fingerprint),
                     root.value, [], generation=root.generation,
                     released_count=count, fingerprint=fingerprint)
        # A host capability, requested and never performed directly — the
        # same rule maybe_record already follows for the clock and any
        # persistence (§99's "never performed by the interpreter
        # directly"). The default is a no-op; a host that wants durable
        # retention of the released subgraph can keep it.
        self.host.snapshot(fingerprint,
                           {"generation": root.generation,
                            "released_count": count})
        return seal

    # ---- driving

    def run(self, src, path=None):
        prog = parse(src)
        self.check_discarded_writes(prog)
        self.hoist(prog, self.env)
        for stmt in prog:
            if isinstance(stmt, Note):
                continue     # never dispatched -- see exec_stmt's Note case
            self.exec_stmt(stmt, self.env)
        return self.output

    def check_discarded_writes(self, prog):
        """A parse-time-computed, pre-execution refusal: `find_discarded_writes`
        (parser.py) is pure and cannot raise `PlanesError` itself without an
        import cycle, so the one call site that turns its answer into a
        program error lives here, on the class that already owns
        `PlanesError` — called before any statement runs, so the A-Q9 shape
        is refused before it can write its wrong answer, not caught after."""
        violations = find_discarded_writes(prog)
        if violations:
            name = violations[0]
            raise PlanesError(
                "discarded-write",
                f"'{name}' is bound with `let` inside a loop and reads the "
                f"outer '{name}', so every iteration's value is discarded "
                f"when that iteration ends",
                "drop `let` — a bare assignment rebinds the outer name, "
                "which is what accumulating across a loop needs")

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
        # The entry file, by the same absolute-path key the loop below
        # compares on. `trace_line` reports lines in THIS file and no other.
        self.entry_file = os.path.abspath(path)
        self.current_file = self.entry_file
        entry = []
        for p, src in graph:
            prog = parse(src, known)
            self.check_discarded_writes(prog)
            self.hoist(prog, self.env, renames.get(p, {}), os.path.abspath(p))
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

    def trace_line(self, stmt_line):
        """The line to record for an emitted output line, in the ENTRY source.

        A `show` written in the entry file reports its own line. One written
        in a module reports the innermost call site that WAS written in the
        entry file — the line the reader is looking at. Zero when neither
        exists, which only happens for a module's own top-level `show`.
        """
        if self.current_file == self.entry_file:
            return stmt_line
        for where, line in reversed(self.call_sites):
            if where == self.entry_file:
                return line
        return 0

    def _maybe_emit_world_envelope(self, traced, stmt_line):
        """Build 2, §3: beside `show`, never instead of it. Called only from
        the `Show` case below, AFTER every existing line there has already
        run — so a refusal here can only ever happen once the ordinary show
        (text/effects/trace/host/record/effect_log) has already completed
        exactly as it does today (§N+1 invariant 2).

        The gate is deliberately narrow: a shown value has to be a record
        carrying a `version` field AND at least one of the three critical
        facets (identity/situation/lineage) before this treats it as an
        intentional emission attempt at all. The exact version match is
        left to `world_ir.parse_world_envelope` itself rather than
        duplicated here — this gate only decides whether an attempt was
        made, `parse_world_envelope` is the one place that decides whether
        it succeeds, exactly as js/interp.mjs's mirror of this gate leaves
        it to `parseWorldEnvelope` (js/interp.mjs cannot import
        `world_ir.SUPPORTED_VERSION` directly without breaking its
        browser-loadability, so both gates are written the same
        presence-only way rather than one checking a value the other
        cannot reach). No program in this repo's corpus shows a top-level
        record shaped that way today (the one place `version` appears as a
        field is nested inside `identity`, never at the envelope's own top
        level), so the gate cannot change behavior for any existing
        program — it can only ever ADD a `WorldEmission` entry for a
        program that opts in by shape.

        Once gated in, the native form is built with `to_host` — the
        SAME existing Number/dict/list -> int/float/dict/list boundary
        `call_foreign` already crosses (`to_json`'s own `unwrap` for
        `show`'s canonical text form takes non-whole numbers to exact TEXT
        instead, which `world_ir`'s int/float field types would refuse; the
        foreign boundary's own float conversion is the one `_type_ok`
        expects) — and handed to `world_ir.parse_world_envelope`, the exact function
        Build 1's own parser exposes. A refusal there is a `WorldIRError`,
        not a `PlanesError`: it is a host-protocol-layer refusal, outside
        the language's own error surface (`errors_coverage.py`/
        `grammar_gen.py` never see a `WorldIRError` raise site), and it
        propagates uncaught — the same "never silently swallowed" choice
        `world_ir.py` itself makes for a malformed critical record.

        When an `affordance` facet is present, its `sourceMapTarget` is
        overwritten (never merely filled in when absent) with the real
        resolved path this `show` was written at — `world_source_map`'s
        extension of `trace_line`'s own entry-file line, formatted the one
        way `format_source_map_path` builds it. A program need only supply
        SOME placeholder string there (world-v1 requires the field present
        with non-empty text); the real path is what actually reaches the
        validator and what test_world_source_map.py resolves back to real
        source (§4).
        """
        value = traced.value
        if not isinstance(value, dict):
            return
        native = to_host(value)
        if "version" not in native:
            return
        if not any(facet in native for facet in ("identity", "situation", "lineage")):
            return
        if isinstance(native.get("affordance"), dict):
            resolved_line = self.trace_line(stmt_line)
            path = world_source_map.format_source_map_path(self.entry_file, resolved_line)
            if path is not None:
                native["affordance"]["sourceMapTarget"] = path
        normalized, warnings = world_ir.parse_world_envelope(native)
        self.world_envelopes.append(WorldEmission(
            raw=native, normalized=normalized, warnings=warnings,
            node=traced.node, source_line=self.trace_line(stmt_line)))

    def hoist(self, stmts, env, renames=None, file=None):
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
                fn.file = file
                # A rename replaces the exported name. Registering both would
                # put the colliding name back, which is the thing the rename
                # was written to fix. The defining file still reaches its own
                # functions by their original names through `fn.local`.
                exported = renames.get(s.name, s.name)
                self.funcs[exported] = fn
                fn.local = s.name
                self.hoist(s.body, env, renames, file)

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
            # Re-registered when the definition is REACHED, not only when it
            # was hoisted, so a definition in a nested scope closes over that
            # scope's env. `file` comes from whichever file is executing —
            # which for a top-level definition is the same file `hoist`
            # already recorded, and for a nested one is where it actually is.
            # Dropped, this quietly replaced every hoisted function with a
            # file-less copy and every trace line pointed at a call site
            # instead of at the `show` itself.
            self.funcs[stmt.name] = Function(stmt.name, stmt.params, stmt.body,
                                             env, file=self.current_file)
            return None

        if isinstance(stmt, Assign):
            val = self.eval(stmt.expr, env)
            named = Traced(val.value, self.mk("name", stmt.name, val.value, [val.node]))
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
            self.trace.append((v.node, self.trace_line(stmt.line)))
            self.host.show(text)
            self.effects.append(("show", text))
            self.maybe_record("show", text, self.host_anchor(), derivation=v.node)
            self.log_effect("show", text, None)
            self._maybe_emit_world_envelope(v, stmt.line)
            return v

        if isinstance(stmt, Why):
            v = self.eval(stmt.expr, env)
            because = self.annotations.get(stmt.expr.name) \
                if isinstance(stmt.expr, Var) else None
            self.output.append(explain(v, because))
            # `why` writes to `output` too, so it writes to `trace` too: the
            # two are the same length by construction, not by convention, and a
            # consumer indexing one with the other's index is never off by the
            # number of `why`s that happened to run.
            #
            # ZERO, and not the statement's own line, because a `Why` node does
            # not carry one. Giving it one is a change to the AST's SHAPE, and
            # the AST's shape is pinned by grammar/parser.planes — the
            # self-hosted parser this repository checks its own parser against
            # — so an AST field is a grammar change, which this build may not
            # make. Nothing is lost: the panel that reads this trace asks about
            # drawn marks, which are `show`s, and `why` prints its own
            # explanation already. js/interp.mjs records the identical zero.
            self.trace.append((v.node, 0))
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
                        val, self.mk("field", f".{name}", val, [subject.node])))
            result = None
            for s in (stmt.body if matched else stmt.els):
                if not isinstance(s, Note):
                    result = self.exec_stmt(s, env)
            fields = ", ".join(f for f, _ in stmt.pattern)
            label = f"when {{{fields}}} " + ("matched" if matched else "did not match")
            rv = result.value if result is not None else None
            rn = result.node if result is not None else self.mk("literal", "nothing", None)
            return Traced(rv, self.mk("op", label, rv, [subject.node, rn]))

        if isinstance(stmt, Fail):
            v = self.eval(stmt.message, env)
            # §158: text, or a record naming the message and, optionally, the
            # fix. `fail` is the one raise site whose message a program writes,
            # and until now it had nowhere to put the continuation clause every
            # other message in the language carries. No new syntax was needed —
            # `fail <expr> as <tag>` already read any expression, so a record
            # literal already parsed here in all three implementations; what
            # refused it was this guard.
            message, fix = v.value, None
            if isinstance(v.value, dict):
                message = v.value.get("message")
                fix = v.value.get("fix")
            if not isinstance(message, str):
                raise PlanesError(
                    "fail-message-not-text",
                    f"fail's message must be text, found {detail_value(message)}",
                    'use text of it, or a record: fail { message: "...", '
                    'fix: "..." } as tag')
            if fix is not None and not isinstance(fix, str):
                raise PlanesError(
                    "fail-message-not-text",
                    f"fail's fix must be text, found {detail_value(fix)}",
                    "use text for the fix, or leave the field out")
            # The `no_fix` marking is unconditional and stays exactly as it
            # was: it records that *the language* names no fix at this raise,
            # which is still true when the author names one. grammar_gen.py
            # reads it statically off this call site, so it could not be
            # conditional even if the reason had changed.
            raise PlanesError(
                stmt.tag, message, fix or "",
                no_fix="the message is the program's own, written at the "
                       "`fail`; naming a fix here would overwrite what the "
                       "author chose to say")

        return self.eval(stmt, env)

    # ---- expressions

    def eval(self, node, env):
        if isinstance(node, Num):
            return self.mk_lit(node.value)
        if isinstance(node, Str):
            label = f'"{escape_string_literal(node.value)}"'
            return Traced(node.value, self.mk("literal", label, node.value))
        if isinstance(node, Bool):
            return self.mk_lit(node.value)
        if isinstance(node, Nothing):
            return self.mk_lit(None)

        if isinstance(node, Var):
            if node.name in self.funcs and not env.has(node.name):
                return self.call(node.name, [], env, getattr(node, 'line', 0))
            return env.get(node.name)

        if isinstance(node, RecordLit):
            parts = [(k, self.eval(v, env)) for k, v in node.fields]
            val = {k: t.value for k, t in parts}
            return Traced(val, self.mk("record", "{record}", val,
                                     [t.node for _, t in parts]))

        if isinstance(node, ListLit):
            items = [self.eval(i, env) for i in node.items]
            vals = [i.value for i in items]
            return Traced(vals, self.mk("list", f"[{len(vals)} items]", vals,
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
            return Traced(new, self.mk("op", "with", new,
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
            return Traced(new, self.mk("op", "plus", new, [base.node, item.node]))

        if isinstance(node, Not):
            v = self.eval(node.expr, env)
            r = not condition(v.value)
            return Traced(r, self.mk("op", "not", r, [v.node]))

        if isinstance(node, IsNothing):
            v = self.eval(node.expr, env)
            r = v.value is None
            return Traced(r, self.mk("op", "is nothing", r, [v.node]))

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
            return Traced(val, self.mk("field", f".{node.name}", val, [obj.node]))

        if isinstance(node, Call):
            return self.call(node.name, node.args, env, node.line)

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
            return Traced(n, self.mk("op", f"round to {fmt(p.value)} places",
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
                    "check the directory exists and is writable — the "
                    "message above names the actual OS error when it's "
                    "something else, such as no space left on the device "
                    "or the destination already existing as a directory")
            self.effects.append(("write", dest.value, len(payload)))
            self.maybe_record("write", dest.value, self.host_anchor(),
                              derivation=dest.node)
            self.log_effect("write", dest.value, None)
            return Traced(None, self.mk("effect", f"write to {dest.value}", None,
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
                return Traced(False, self.mk("op", "and", False, [left.node]))
            right = self.eval(node.right, env)
            v = condition(right.value)
            return Traced(v, self.mk("op", "and", v, [left.node, right.node]))

        if node.op == "or":
            left = self.eval(node.left, env)
            if condition(left.value):
                return Traced(True, self.mk("op", "or", True, [left.node]))
            right = self.eval(node.right, env)
            v = condition(right.value)
            return Traced(v, self.mk("op", "or", v, [left.node, right.node]))

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
            return Traced(v, self.mk("op", f"first {int(n.value)} of", v, [src.node]))

        left = self.eval(node.left, env)
        right = self.eval(node.right, env)
        v = apply_op(node.op, left.value, right.value)
        return Traced(v, self.mk("op", node.op, v, [left.node, right.node]))

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
            except (HostError, OSError) as e:
                # C2 (A.1): the message is a literal here, so the catalogue can
                # read it. The host's own words ride along as the cause — they
                # say which url and why — but the sentence and the fix are the
                # language's.
                #
                # OSError, not just HostError: PythonHost.ask calls urlopen
                # directly and wraps nothing, and urllib.error.URLError (and
                # HTTPError) are OSError subclasses — the same widening
                # WriteTo's except already needed for a real filesystem.
                # TestHost is the only host that raises HostError itself.
                raise PlanesError(
                    "ask-failed", f"asking '{url}' failed: {e}",
                    "check the url is reachable and spelled right; a run "
                    "without the network needs a stubbed response")
            self.effects.append(("ask", url, len(body)))
            self.maybe_record("ask", url, self.host_anchor(), derivation=arg.node)
            self.log_effect("ask", url, body)
            try:
                parsed = from_foreign(self.host.parse_json(body))
            except Exception:
                parsed = body
            return Traced(parsed, self.mk("effect", f"ask {url}", parsed,
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
            except (HostError, OSError):
                # OSError, not just HostError: PythonHost.read calls open()
                # directly and wraps nothing, so a real missing file raised
                # FileNotFoundError here, uncaught — the same widening
                # WriteTo's except already needed for a real filesystem.
                # TestHost is the only host that raises HostError itself.
                raise PlanesError("no-such-file", path,
                                  "check the path, or write it first")
            self.effects.append(("read", path, len(body)))
            self.maybe_record("read", path, self.host_anchor(), derivation=arg.node)
            self.log_effect("read", path, body)
            return Traced(body, self.mk("effect", f"read {path}", body,
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
            return Traced(v, self.mk("op", "count of", v, [arg.node]))
        if node.name == "lower":
            require_text("lower", "lowercase", arg.value)
            v = arg.value.lower()
            return Traced(v, self.mk("op", "lower of", v, [arg.node]))
        if node.name == "upper":
            require_text("upper", "uppercase", arg.value)
            v = arg.value.upper()
            return Traced(v, self.mk("op", "upper of", v, [arg.node]))
        if node.name == "whole":
            if not is_num(arg.value):
                raise PlanesError(
                    "not-a-number",
                    f"cannot take the whole part of {detail_value(arg.value)}",
                    "whole of rounds a number to the nearest whole, half away from "
                    "zero; if this is text, "
                    "convert it first with number of — a boolean, a list, "
                    "a record, or nothing has no path to becoming a number")
            n = Number.of(arg.value).round_to(0)
            return Traced(n, self.mk("op", "whole of", n, [arg.node]))

        if node.name == "number":
            # The twelfth builtin (A-Q19): text to an exact number, closing the
            # round trip `write` opened and nothing closed — `write` emits a
            # number as JSON text so an exact value survives a tool that isn't
            # Planes, and `read` and `ask` hand text back, but nothing turned
            # that text back into a number until now.
            if not isinstance(arg.value, str):
                raise PlanesError(
                    "not-text",
                    f"cannot make a number from {detail_value(arg.value)}",
                    "number of takes text; a number does not need "
                    "converting, and nothing else has a path to one")
            try:
                n = number_from_text(arg.value)
            except NotANumber as e:
                if e.approximation:
                    raise PlanesError(
                        "not-a-number",
                        f"{detail_value(arg.value)} is an approximation of "
                        "a number, not a number",
                        "the ~ marks text that was rounded for display, so "
                        "the original value cannot be recovered from it — "
                        "carry the number itself instead of its text")
                raise PlanesError(
                    "not-a-number",
                    f"cannot make a number from {detail_value(arg.value)}",
                    "number of takes an optional leading -, digits, and at "
                    "most one . — no exponent notation, e.g. "
                    "number of \"12.5\"")
            return Traced(n, self.mk("op", "number of", n, [arg.node]))

        if node.name == "sine":
            # The eleventh builtin, and the operation that approximates at
            # EVERY argument, unlike `root` (checkpoint v21.0 §§251-253). Takes
            # DEGREES, consistent with the drawing protocol's `rotate`: degrees
            # are whole numbers and stay exact under this language's
            # arithmetic, where radians would arrive already approximated.
            if not isinstance(arg.value, Number):
                raise PlanesError(
                    "not-a-number",
                    f"cannot take the sine of {detail_value(arg.value)}",
                    "sine takes an angle in degrees as a number — e.g. "
                    "sine of 30; if this is text, convert it first with "
                    "number of")
            n = sine_degrees(arg.value)
            return Traced(n, self.mk("op", "sine of", n, [arg.node]))

        if node.name == "root":
            # The thirteenth builtin (square-root-spec.md, closing §253), and
            # the first whose exactness is decided by its ARGUMENT: `root of 9`
            # is exactly 3, `root of 2` is not. Deliberately unlike `sine`,
            # which approximates at every argument because its algorithm has no
            # exact path at any of them.
            if not isinstance(arg.value, Number):
                raise PlanesError(
                    "not-a-number",
                    f"cannot take the square root of {detail_value(arg.value)}",
                    "root takes a number — e.g. root of 9; if this is text, "
                    "convert it first with number of")
            if arg.value.q < 0:
                raise PlanesError(
                    "not-a-number",
                    f"cannot take the square root of {fmt(arg.value)}",
                    "root takes a number that is not negative — this language "
                    "has no imaginary number, so a negative radicand has no "
                    "value to return; test the sign before taking the root")
            n = root_of(arg.value)
            return Traced(n, self.mk("op", "root of", n, [arg.node]))

        if node.name == "text":
            v = fmt(arg.value)
            return Traced(v, self.mk("op", "text of", v, [arg.node]))
        if node.name == "normalize":
            require_text("normalize", "normalize", arg.value)
            v = unicodedata.normalize("NFC", arg.value)
            return Traced(v, self.mk("op", "normalize of", v, [arg.node]))
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
            return Traced(v, self.mk("op", "join of", v, [arg.node]))
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
            return Traced(v, self.mk("op", "rest of", v, [arg.node]))

        raise PlanesError(
            "unknown-builtin", f"no builtin is named '{node.name}'",
            "the thirteen builtins are fixed and the lexer recognises only those, "
            "so reaching this is a defect in the interpreter rather than in "
            "the program — worth reporting with the source")

    def run_or_fail_handler(self, node, error, env):
        """Bind `node.tag` to `error`, as a record, and run the handler.

        No child scope: an `or fail as` handler runs in the same env an
        `if`/`else` body does (exec_stmt's If case), so a name the handler
        assigns is visible afterward exactly the way an if-branch's is.
        """
        rec = error_record(error)
        bound = Traced(rec, self.mk("record", "{record}", rec, []))
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
            item_t = Traced(item, self.mk("item", node.var, item, [source.node]))
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
        return Traced(results, self.mk("comprehension", label, results,
                                     [source.node] + nodes[:3]))

    def call(self, name, args, env, line=0):
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
            inner.bind_local(p, Traced(a.value, self.mk("name", p, a.value, [a.node])))
        # Where this call was WRITTEN, and whose body is now running. Both are
        # restored on every exit path, including a `give` and a depth refusal,
        # so an early return can never leave the interpreter believing it is
        # somewhere it is not.
        self.call_sites.append((self.current_file, line))
        outer_file = self.current_file
        self.current_file = getattr(fn, "file", None)
        try:
            for s in fn.body:
                if not isinstance(s, Note):
                    self.exec_stmt(s, inner)
            return Traced(None, self.mk("call", iname, None,
                                      [a.node for a in arg_vals]))
        except _Give as g:
            return Traced(g.value.value,
                          self.mk("call", iname, g.value.value,
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
                "if recursing over a collection, replace it with one "
                "`for each` pass threading a state record forward — or a "
                "cons-list stack for nested structure; if recursing on a "
                "plain number with no collection involved, `for each` has "
                "nothing to iterate over, so restructure the computation "
                "to avoid unbounded recursion depth instead")
        finally:
            self.current_file = outer_file
            self.call_sites.pop()

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
        return Traced(value, self.mk("foreign", decl.name, value,
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
            "convert first — `text of n` to build text, or `number of t` "
            "to do arithmetic — but only for a text/number pairing; if "
            "either side is a list or record, neither conversion is "
            "meaningful: use `plus` to append to a list, `with` to update "
            "a record, or rewrite the expression")
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
                "`text of`, but only when it is a number, yes/no value, "
                "or nothing; if it is a list or record, `text of` gives "
                "an opaque placeholder, not its contents, so the search "
                "will not find what was probably intended")
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

def approximations_in(traced, seen=None, found=None):
    """Every distinct approximation entry reachable in this derivation.

    A comparison between two approximate values has TWO of them, and showing
    both is the whole reason the no-tolerance rule is defensible: the answer is
    plain, and the explanation says where each side stopped being exact. One
    epsilon nobody chose would replace both of these lines with silence.

    Iterative, not recursive (R3, checkpoint v30.0 §468) — the one walk
    `explain` reaches that used to recurse over the FULL derivation (not
    one layer: it has to check every node reachable from the root for an
    approximate number), so a long unwindowed chain — exactly the shape
    `replay` (§5) reconstructs — could exceed Python's recursion limit past
    roughly 450 steps. An explicit stack, construction order (so both
    languages still agree), matching `_cut`/`_seal`/`_why_next_stop`'s own
    iterative shape: a node is pushed once per reference but PROCESSED
    (and its approximation, if any, recorded) only once, the first time it
    is popped — `seen` gates at pop-time here exactly as the recursive
    form gated at call-entry, so dedup and result order are unchanged.
    """
    seen = set() if seen is None else seen
    found = [] if found is None else found
    stack = [traced]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        v = getattr(node, "value", None)
        if isinstance(v, Number) and v.approx is not None and v.approx not in found:
            found.append(v.approx)
        inputs = getattr(node, "inputs", ()) or ()
        for inp in reversed(inputs):
            stack.append(inp)
    return found


def explain(traced, because=None):
    """`why`'s one-line derivation. `because`, when given, is display
    text beside it — never an input the derivation graph carries."""
    n = traced.node
    inner = n.inputs[0] if n.kind == "name" and n.inputs else n
    text = f"{fmt(traced.value)} from {render(inner)}"
    if because:
        text += f'\n  because "{escape_string_literal(because)}"'
    for a in approximations_in(n):
        text += f"\n  approximate — {a.op}: {a.detail}"
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
    if k == "seal":
        # R1 §5: the seal's own label IS the fixed refusal sentence, so
        # this arm — like "list"/"record"/"effect" above — is just
        # "return node.label"; no seal-specific rendering logic exists.
        return node.label
    if k == "op":
        if node.label.endswith(" of") or node.label == "not":
            return f"{node.label} {render(node.inputs[0])}"
        return f" {node.label} ".join(render(i) for i in node.inputs)
    return fmt(node.value)


# ============================================================ readable deep walk (R2)
#
# `why_tree` is the deep walk `why` reaches on demand — `explain` above stays
# the one-layer default (§453's card register; that text is unchanged by
# this build). Three things changed here from HEAD: a run of consecutive,
# identical-in-shape reassignment/recursion hops folds into one labeled
# aggregate rather than printing every hop (§451); folding stops at a seal,
# which still renders as a leaf carrying its fixed refusal sentence (§452 —
# R1's own behavior, confirmed unchanged, not rebuilt); and the silent
# `depth > max_depth: "..."` line is gone (§455) — a walk that reaches its
# own requested depth simply stops, with an explicit note that more exists,
# never a bare ellipsis.
#
# The two "hop" helpers below compare SHAPE, not value: kind and label at
# every position, with the walk's own continuation abstracted to a
# placeholder so two hops that differ only in their numbers compare equal.
# That is what lets `total = total + n` run 600 times fold to one line
# while a step that switches from `+` to `*` does not.

_WHY_MIN_FOLD = 8      # a run shorter than this reads fine unfolded (F1's
                       # margin) — high enough that test_values.py's 3-step
                       # accumulation ("one derivation node per accumulation
                       # step") stays exactly as it prints today; folding
                       # earns its keep only once a chain runs well past
                       # what a single screen already shows comfortably.

_WHY_SEARCH_BUDGET = 4000  # a node visited-count cap, SHARED and
                           # cumulative across every search one
                           # `_why_find_run` call performs — not a fresh
                           # allowance per hop. A single very expensive hop
                           # (one whose own subtree is large) is exactly as
                           # capped as many cheap ones adding up, because
                           # both draw from the one budget. Most bound names
                           # never repeat at all (an ordinary one-off
                           # assignment, not a loop), and proving that
                           # exhaustively costs the size of everything still
                           # reachable from that point. Found live in this
                           # build: benchmarks/world_shape.planes (R1's own
                           # S=64 fixture) made an unbudgeted search run for
                           # minutes, and a budget reset per hop rather than
                           # shared across the whole call still did — a run
                           # whose OWN hops are each individually large, not
                           # only many small failed searches, needs the
                           # total bounded, not each part separately. A real
                           # repeat is always found within a handful of
                           # nodes, so the budget only ever gives up on a
                           # name that was never going to fold (or folds
                           # less far than the true extent) — always a safe
                           # under-fold, never a wrong count.


class _WhyBudget:
    """A shared, mutable operation counter threaded through every search
    one `_why_find_run` call performs. `take()` returns False once
    exhausted; every caller treats that identically to "no match here" —
    conservative, so a budget cutoff can only ever under-fold, never claim
    a run longer or shaped differently than what was actually verified."""
    __slots__ = ("left",)

    def __init__(self, n=_WHY_SEARCH_BUDGET):
        self.left = n

    def take(self):
        if self.left <= 0:
            return False
        self.left -= 1
        return True


def _why_next_stop(node, label, budget):
    """Iterative DFS, construction order (so both languages agree), for
    the next same-label 'name' node or seal reachable from `node`'s
    inputs. None at a natural leaf or once `budget` is exhausted.

    Iterative, not recursive — the same reason `_cut`/`_seal` above are
    (their own docstrings say why): a field reference inside a helper
    function is its own 'name' node whose own input traces back through
    every earlier call, so the path to a match can run hundreds of levels
    deep even for a chain a human would call short. Found live in this
    build: probe/parser/cursor_scales.planes (200 calls threading a
    record through `for each`, each field access one more link) exceeded
    Python's default recursion limit with the recursive form.

    Memoized (the `exhausted` set) for the same reason as before: a Deriv
    graph is a DAG, not a tree — a recursive call's own argument and
    return value commonly share a node — and unmemoized, this walk
    re-derives a shared node's "no match here" once per path to it. An
    explicit stack of (node, "exit") sentinels marks a node exhausted
    only once every one of its own descendants has been ruled out —
    post-order, the same shape `_seal`'s own two-pass walk uses."""
    exhausted = set()
    stack = [("enter", c) for c in reversed(node.inputs)]
    while stack:
        phase, n = stack.pop()
        if phase == "exit":
            exhausted.add(id(n))
            continue
        if id(n) in exhausted or not budget.take():
            continue
        if n.kind == "name" and n.label == label:
            return n
        if n.kind == "seal":
            return n
        stack.append(("exit", n))
        for c in reversed(n.inputs):
            stack.append(("enter", c))
    return None


def _why_hop_shape(head, stop_label, budget):
    """The structural signature of one hop, as a fixed-length SHA-256
    digest — `head`'s subtree with values erased, stopping (without
    descending) at the next same-label 'name' node or at a seal — so the
    signature describes exactly one step of a reassignment or recursion
    chain, never what lies beyond it. Budgeted and memoized the same way
    and for the same reasons as `_why_next_stop` above (DAG-sharing
    blowup, and recursion depth on a long path to a match) — `_why_find_run`
    calls this only after `_why_next_stop` has already located that same
    stopping point nearby, so in practice this walk is short; the shared
    budget is a backstop, not the common path.

    A DIGEST, not a nested structure: two shapes used to compare
    structurally, which walks every shared level natively — cheap for one
    comparison, but `_why_find_run`'s loop compares against `shape0` on
    every hop, and a hop whose own subtree is large paid that full
    recursive-compare cost EVERY time, not once. Found live in this
    build: benchmarks/world_shape.planes made this run for minutes with
    the budget correctly bounding CONSTRUCTION but not COMPARISON. A
    digest folds construction and comparison into the same accounting —
    building it costs what building the nested form did, and comparing
    two is then a fixed-length string check, not a walk. The same
    technique R1's own seal fingerprint already uses (`_seal`, above),
    applied here to a hop instead of a released subgraph.

    Iterative post-order, explicit (node, "exit") stack frames the same
    way `_why_next_stop` is now and `_seal` above already was: a child's
    digest must exist before its parent's can be computed, and LIFO
    ordering guarantees every child's "exit" pops before its parent's,
    the same invariant a recursive call's own return-before-caller-
    continues would have given for free — without paying for it in stack
    depth."""
    memo = {}

    def finish(n):
        children = ",".join(memo[id(c)] for c in n.inputs)
        return hashlib.sha256(
            f"{n.kind}\x1f{n.label}\x1f{children}".encode()).hexdigest()[:16]

    stack = [("enter", c) for c in reversed(head.inputs)]
    while stack:
        phase, n = stack.pop()
        key = id(n)
        if phase == "exit":
            memo[key] = finish(n)
            continue
        if key in memo:
            continue
        if not budget.take():
            memo[key] = "<budget>"
        elif n.kind == "name" and n.label == stop_label:
            memo[key] = "<next>"
        elif n.kind == "seal":
            memo[key] = "<seal>"
        else:
            stack.append(("exit", n))
            for c in reversed(n.inputs):
                stack.append(("enter", c))

    return finish(head)


def _why_find_run(head):
    """The maximal run of consecutive same-shape hops starting at `head`, a
    'name' node. `run` is `head` plus every following same-label 'name'
    node reached by an identically-shaped hop, in order (at least one
    element — itself). `tail` is what the run gives way to: a seal, a
    differently-shaped 'name' node, or None when the chain ends inside the
    run's own last node.

    One `_WhyBudget`, shared for the whole call: every hop this run
    confirms draws from the same allowance, so a run with many hops costs
    the same as a run with few large ones — the total is what is bounded,
    not each part separately. Checks `_why_next_stop` before ever computing
    a shape: the overwhelming majority of 'name' nodes in an ordinary
    program are a one-off assignment, not a loop, and never repeat at
    all — for those, the presence check alone already answers "no run
    here" without also paying for a shape walk of the same subtree."""
    budget = _WhyBudget()
    nxt = _why_next_stop(head, head.label, budget)
    if nxt is None or nxt.kind == "seal":
        return [head], nxt
    shape0 = _why_hop_shape(head, head.label, budget)
    run = [head]
    cur = head
    while True:
        if _why_hop_shape(cur, head.label, budget) != shape0:
            return run, nxt
        run.append(nxt)
        cur = nxt
        nxt = _why_next_stop(cur, head.label, budget)
        if nxt is None or nxt.kind == "seal":
            return run, nxt


def _why_build(traced, max_depth=14, because=None):
    """The one traversal every readable register renders from (§453): a
    card, a prompt view, and a machine export computed by separate walks
    could drift about which node they describe; one walk, shared by all
    three, cannot.

    Returns {"root": <node>, "because": because}, where a node is one of:
      {"type": "step", kind, label, value, origin, children: [node, ...]}
      {"type": "aggregate", label, count, tail: node or None}
      {"type": "seal", label, value}
      {"type": "repeat", kind, label, value}          -- DAG dedup (as HEAD)
      {"type": "frontier", kind, label, value, origin, more}  -- depth limit
    """
    seen = {}

    def walk(node, depth):
        if id(node) in seen and node.inputs:
            return {"type": "repeat", "kind": node.kind, "label": node.label,
                    "value": fmt(node.value)}
        seen[id(node)] = True

        if node.kind == "seal":
            return {"type": "seal", "label": node.label,
                    "value": fmt(node.value)}

        if node.kind == "name":
            run, tail = _why_find_run(node)
            if len(run) >= _WHY_MIN_FOLD:
                return {
                    "type": "step", "kind": node.kind, "label": node.label,
                    "value": fmt(node.value), "origin": node.origin,
                    "children": [{
                        "type": "aggregate", "label": node.label,
                        "count": len(run) - 1,
                        "tail": walk(tail, depth + 1) if tail is not None else None,
                    }],
                }

        if depth >= max_depth:
            return {"type": "frontier", "kind": node.kind, "label": node.label,
                    "value": fmt(node.value), "origin": node.origin,
                    "more": bool(node.inputs)}

        return {
            "type": "step", "kind": node.kind, "label": node.label,
            "value": fmt(node.value), "origin": node.origin,
            "children": [walk(c, depth + 1) for c in node.inputs],
        }

    return {"root": walk(traced.node, 0), "because": because}


def _why_render_prompt(built):
    """The prompt register: indented, walkable text — `why_tree`'s return
    shape, unchanged in form from HEAD, changed only in what fills it."""
    lines = []

    def origin_tail(node):
        return f"   <- entered at {node['origin']}" if node.get("origin") else ""

    def emit(node, depth):
        indent = "  " * depth
        t = node["type"]
        if t == "seal":
            lines.append(indent + f"{node['label']} = {node['value']}")
            return
        if t == "repeat":
            lines.append(indent +
                         f"{node['label']} = {node['value']}   (same as above)")
            return
        if t == "aggregate":
            step_word = "step" if node["count"] == 1 else "steps"
            lines.append(indent + f"{node['label']} advanced {node['count']} "
                                   f"more times ({step_word} identical in "
                                   "shape to the one above)")
            if node["tail"] is not None:
                emit(node["tail"], depth + 1)
            return
        if t == "frontier":
            lines.append(indent + f"{node['label']} = {node['value']}"
                                   f"{origin_tail(node)}")
            if node["more"]:
                lines.append("  " * (depth + 1) +
                             "(more derivation below this depth — call "
                             "again with a larger depth to expand)")
            return
        # "step"
        lines.append(indent + f"{node['label']} = {node['value']}"
                               f"{origin_tail(node)}")
        for c in node["children"]:
            emit(c, depth + 1)

    emit(built["root"], 0)
    if built["because"]:
        lines.insert(1, "  " +
                     f'because "{escape_string_literal(built["because"])}"')
    return "\n".join(lines)


def why_tree(traced, max_depth=14, because=None):
    """The deep walk's prompt register — `why`, walked explicitly and as
    far as `max_depth` allows (R2, checkpoint v29.0 §448-458). A run of
    identical-in-shape reassignment or recursion steps folds into one
    labeled aggregate (§451); a seal, R1's own leaf, still renders as its
    fixed refusal sentence and nothing folds past it (§452); nothing here
    ever elides silently — a walk that reaches its own depth limit says so,
    in words, rather than printing a bare "..." (§455).

    The graph is a DAG, not a tree: one source list feeds every item of a
    comprehension. Shared subgraphs are printed once and referred to after,
    so the output stays the size of the derivation, not of the data.

    `because`, when given, is display text for the root beside the
    derivation — never an input the graph itself carries.
    """
    return _why_render_prompt(_why_build(traced, max_depth, because))


def why_machine(traced, max_depth=14, because=None):
    """The machine register (§453): the same walk `why_tree` renders as
    text, returned as data instead — the step/aggregate/seal/frontier
    shapes `_why_build` documents, for an agent or tool to read
    structurally rather than parse back out of prose."""
    return _why_build(traced, max_depth, because)


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


# ================================================================ replay (R3)
#
# The fast path (tracing off, §3 above) builds no derivation graph. Any why
# — any of the three registers above, on a value it produced — answers by
# REPLAY: re-executing the same program from the start, tracing on, so the
# real Deriv graph an eager run would have built exists again. This is exact
# because Planes is deterministic and pure (§466): the same source, run
# against the same effect RESULTS in the same order, takes the identical
# path through `eval` and stamps the identical generations — byte-identical
# to an eager run of the same program, the gate test_replay.py checks (§6).
#
# Effects are read back, never re-performed (§7). `ReplayHost` is the
# mechanism: an ordinary second Host (the same seam TestHost already proves
# is real — no new host CAPABILITY, ruling 1) that answers `ask`/`read`/
# `write`/`show` from a recorded log instead of touching the world. A value
# whose effects were not recorded — the fast-path run did not set
# `record=True` — refuses rather than silently re-performing them (F7).

class ReplayHost(Host):
    """Answers the four effects a program can trigger directly from
    `effect_log` (an ordered `(kind, target, result)` list — `Interpreter.
    log_effect`'s own shape), instead of performing them. `clock` and
    `resolve` are refused outright: `record=False` during replay means
    `clock` is never reached (`maybe_record` short-circuits before it), and
    a `foreign` call is a claim against an arbitrary host function, outside
    R3's effect log (documented in REPORT_REPLAY.md, not silently
    supported by accident). `parse_json` is pure computation over already-
    recorded text, not a fresh effect, so it is real, not replayed.
    """

    name = "replay"

    def __init__(self, effect_log):
        self._log = list(effect_log)
        self._pos = 0

    def _next(self, kind, target):
        if self._pos >= len(self._log):
            raise HostError(
                f"replay refused: no recorded effect for {kind} '{target}' "
                "— the fast-path run must set record=True so effects are "
                "logged before a later replay can read them back instead "
                "of re-performing them")
        logged_kind, logged_target, result = self._log[self._pos]
        if logged_kind != kind or logged_target != target:
            raise HostError(
                f"replay refused: expected the recorded effect "
                f"{logged_kind} '{logged_target}' next but replay reached "
                f"{kind} '{target}' — effects must replay in the exact "
                "order they were recorded")
        self._pos += 1
        return result

    def ask(self, url):
        return self._next("ask", url)

    def read(self, path):
        return self._next("read", path)

    def write(self, path, text):
        self._next("write", path)

    def show(self, text):
        self._next("show", text)

    def clock(self):
        raise HostError(
            "replay refused: clock is not available during replay")

    def resolve(self, target):
        raise HostError(
            f"replay refused: foreign target '{target}' cannot be "
            "replayed — foreign effects are outside R3's effect log")

    def parse_json(self, text):
        return json.loads(text)


def replay(steps, subject, window=None, effect_log=None):
    """Reconstruct `subject`'s Deriv slice from a tracing-off run, by
    deterministic re-execution with tracing on (§5).

    `steps` is the same ordered list of source snippets the fast-path run
    executed (one `Interpreter.run` call per step — the shape
    `retention`/`whytree`'s own CLI configs already use for a scenario that
    grows over several calls); `window` is the fast path's own window, so a
    value already past it seals identically here — replay does not need to
    reconstruct sealed history in detail, only re-run far enough that its
    own `_cut` seals it again at the same generation (§5's "anchors at the
    seal's recorded generation", which falls out of re-execution rather
    than needing a separate mechanism, since generation stamping depends
    only on construction order and that order is unchanged). `effect_log`
    is the fast path's own `Interpreter.effect_log` (empty/`None` for a
    program with no effects); a `ReplayHost` built from it answers every
    effect the replay reaches by reading it back, in order, never by
    performing it — and refuses, by name, if the replay reaches an effect
    the log does not cover (§7/F7).

    Returns the replayed `Traced`, usable with `explain`/`why_tree`/
    `why_machine`/`origins` exactly as an eager run's value would be.
    """
    host = ReplayHost(effect_log or [])
    itp = Interpreter(host=host, window=window, trace=True, record=False)
    for step in steps:
        itp.run(step)
    return itp.env.get(subject)
