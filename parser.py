"""Planes parser — turns tokens into AST."""
import json
import os

from lexer import *
from lexer import _VOCAB, GrammarDataError
from planes_num import Number

# Builtins are ordinary functions, not keywords. The parser only needs their
# names so a bare `count of xs` is read as a call rather than a variable; it
# does not need to know what they do. A user may define a function with the
# same name, and theirs is the one that runs. Source of truth is
# grammar/vocabulary.json, loaded by lexer.py as _VOCAB.
BUILTIN_NAMES = {b["name"] for b in _VOCAB["builtins"]}


class PlanesAmbiguity(PlanesSyntaxError):
    """Two or more readings of the same source, and nothing says which.

    Not a malformed program — a program the name table cannot resolve.
    The remedy is different (rename or parenthesise, not fix a typo), so
    the class is distinct even though the base is shared: every existing
    `except PlanesSyntaxError` still catches it. Parse-time only — this
    never interacts with `or fail as`, which is a runtime mechanism.
    """
    pass


_AMBER_TEMPLATES = None


def _load_amber_templates():
    """grammar/messages/amber.json — amber's refusal text, as data (§69.5
    ruling D5). No amber message text lives inline in this file."""
    global _AMBER_TEMPLATES
    if _AMBER_TEMPLATES is not None:
        return _AMBER_TEMPLATES
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "grammar", "messages", "amber.json")
    fix = "reinstall planes, or regenerate with python3 grammar_gen.py"
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        raise GrammarDataError(
            "grammar-data-missing", f"{path} could not be read ({e.strerror or e})", fix) from e
    except json.JSONDecodeError as e:
        raise GrammarDataError(
            "grammar-data-missing", f"{path} is not valid JSON ({e})", fix) from e
    _AMBER_TEMPLATES = {t["id"]: t for t in doc["templates"]}
    return _AMBER_TEMPLATES


def render_amber(template_id, line, readings, **slots):
    """Render one of amber's refusal messages from grammar/messages/amber.json.

    `readings` is a list of (source, gloss) pairs, one per candidate
    reading — lettered A, B, C, ... in order. `slots` fills every other
    `{...}` placeholder the template uses.
    """
    t = _load_amber_templates()[template_id]
    lines = [t["headline"].format(line=line, **slots), ""]
    for i, (source, gloss) in enumerate(readings):
        letter = chr(ord("A") + i)
        lines.append(t["readings"].format(letter=letter, source=source, gloss=gloss))
    lines.append("")
    lines.append(t["reason"].format(line=line, **slots))
    lines.append(t["fix"].format(line=line, **slots))
    return "\n".join(lines)


class Parser:
    known_funcs: dict = {}

    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    # ---- token helpers

    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def at(self, kind, value=None):
        t = self.peek()
        return t.kind == kind and (value is None or t.value == value)

    def accept(self, kind, value=None):
        return self.next() if self.at(kind, value) else None

    def expect(self, kind, value=None):
        t = self.accept(kind, value)
        if t is None:
            g = self.peek()
            raise PlanesSyntaxError(
                f"line {g.line}: expected {value or kind.lower()}, "
                f"found '{g.value or 'end of line'}'")
        return t

    def skip_blank(self):
        while self.accept("EOL") or self.accept("OP", ";"):
            pass

    def skip_bracket_ws(self):
        """Blank tokens inside `[...]` / `{...}`.

        The tokenizer tracks indentation per physical line, oblivious to
        bracket nesting — a literal spanning indented lines picks up BEGIN
        and END tokens that mean nothing here (brackets already carry the
        structure). Consume them along with EOL/`;` so a literal can wrap
        across lines the way a person writing one down would."""
        while self.accept("EOL") or self.accept("OP", ";") \
                or self.accept("BEGIN") or self.accept("END"):
            pass

    # ---- structure

    def parse_program(self):
        stmts = []
        self.skip_blank()
        while not self.at("EOF"):
            if self.accept("END"):
                self.skip_blank()
                continue
            stmts.append(self.parse_statement())
            self.skip_blank()
        return stmts

    def parse_block(self):
        """Indented block after ':' — or a single inline statement."""
        if self.accept("EOL"):
            self.expect("BEGIN")
            stmts = []
            self.skip_blank()
            while not self.at("END") and not self.at("EOF"):
                stmts.append(self.parse_statement())
                self.skip_blank()
            self.accept("END")
            return stmts
        return [self.parse_statement()]

    # ---- statements

    def parse_statement(self):
        if self.accept("USE"):
            module = self.expect("NAME").value
            renames = []
            with_tok = self.accept("WITH")
            while with_tok:
                # `use cache with load record as load cached`
                # Names are multi-word, so read consecutive NAME tokens on
                # both sides of `as`. `as` and `with` are reserved words, so
                # neither can be part of either name. Only `old` is checked
                # for amber (§69.5 site 4): it is a lookup against the used
                # module's exported names, so a shorter exported prefix is
                # a real second reading. `new` is not a lookup — it is the
                # alias being introduced right here — and names_in_graph
                # already registers it as a known name for the rest of this
                # file, so checking it the same way would flag every rename
                # whose alias happens to start with the name it replaces.
                old = self.read_multiword_name()
                self.check_rename_name_ambiguity(old, with_tok)
                self.expect("AS")
                new = self.read_multiword_name()
                renames.append((old, new))
                with_tok = self.accept("WITH")
            return Use(module, tuple(renames))

        if self.at("FOREIGN"):
            return self.parse_foreign()

        if self.at("RULE"):
            return self.parse_because(self.parse_rule())

        if self.at("NAME", "note") and self.peek(1).kind == "OP" and self.peek(1).value == ":":
            return self.parse_note()

        if self.at("TO") and self.peek(1).kind == "NAME":
            return self.parse_funcdef()

        if self.accept("GIVE"):
            return Give(self.parse_expr())

        show_tok = self.accept("SHOW")
        if show_tok:
            return Show(self.parse_expr(), show_tok.line)

        if self.accept("WHY"):
            return Why(self.parse_expr())

        write_tok = self.accept("WRITE")
        if write_tok:
            value = self.parse_or()
            self.expect("TO")
            dest = self.parse_or()
            return self.trailing_or_fail(WriteTo(value, dest, write_tok.line))

        if self.accept("IF"):
            cond = self.parse_expr()
            self.expect("OP", ":")
            then = self.parse_block()
            els = []
            save = self.i
            self.skip_blank()
            if self.accept("ELSE"):
                self.expect("OP", ":")
                els = self.parse_block()
            else:
                self.i = save
            return If(cond, then, els)

        if self.accept("WHEN"):
            return self.parse_when()

        if self.at("FOR"):
            return self.parse_foreach(as_expr=False)

        if self.accept("LET"):
            name = self.expect("NAME").value
            self.expect("OP", "=")
            return self.parse_because(Assign(name, self.parse_expr(), is_let=True))

        if self.at("NAME") and self.peek(1).kind == "OP" and self.peek(1).value == "=":
            name = self.next().value
            self.next()
            return self.parse_because(Assign(name, self.parse_expr()))

        return self.parse_expr()

    def parse_foreign(self):
        """`foreign sort of xs from "builtins.sorted" doing nothing`

        The `doing` clause is a claim, not a derived fact. Omitting it means
        unknown, not pure — a foreign function whose effects nobody stated
        must not disappear from the surface.
        """
        foreign_tok = self.expect("FOREIGN")
        parts = [self.expect("NAME").value]
        while self.at("NAME"):
            parts.append(self.next().value)
        name = " ".join(parts)
        params = []
        if self.accept("OF"):
            params.append(self.expect("NAME").value)
            while self.accept("OP", ","):
                params.append(self.expect("NAME").value)
        self.expect("FROM")
        target = self.expect("STRING").value[1:-1]
        effects, declared = (), False
        if self.accept("DOING"):
            declared = True
            claims = [self.read_claim(params)]
            while self.accept("OP", ","):
                claims.append(self.read_claim(params))
            effects = tuple(c for c in claims if c[0] != "nothing")
        return Foreign(name, params, target, effects, declared, foreign_tok.line)

    def read_claim(self, params):
        """One entry in a `doing` clause: an effect kind and, optionally,
        where it goes.

            doing ask "https://api.example.com"    a fixed destination
            doing ask url                          whatever the caller passes
            doing ask                              not stated

        The middle form is the valuable one: naming a parameter means a call
        site with a known argument resolves to the real destination, so an
        effect surface can name a host across a foreign boundary.
        """
        kind = self.read_effect_word()
        if kind == "nothing":
            return ("nothing", None)
        if self.at("STRING"):
            return (kind, ("literal", self.next().value[1:-1]))
        if self.at("NAME") and self.peek().value in params:
            return (kind, ("param", self.next().value))
        if self.at("NAME"):
            g = self.peek()
            raise PlanesSyntaxError(
                f"line {g.line}: '{g.value}' is not a parameter of this "
                f"function, so it cannot be where '{kind}' goes\n"
                f"  parameters: {', '.join(params) or 'none'}")
        return (kind, None)

    def read_effect_word(self, after="'doing'"):
        """An effect name, after `doing` in a foreign claim or after `may
        not` in a rule.

        Effect names double as ordinary words, so most arrive as NAME. A few
        (`read`, `write`, `show`, `ask`) may be builtins or reserved words;
        accept whatever token carries the text.
        """
        t = self.peek()
        if t.kind in ("NAME", "NOTHING", "SHOW", "WRITE"):
            self.next()
            return t.value or "nothing"
        raise PlanesSyntaxError(
            f"line {t.line}: expected an effect name after {after}, "
            f"found '{t.value or 'end of line'}'")

    def parse_rule(self):
        """`rule [name] subject may not kind` (forbid) or
        `rule [name] subject may kind` (permit), each optionally with
        `to "target"` and a `supersedes [other-name]` clause, which may
        itself carry a fingerprint (`@xxxxxx`) of the rule it overrides.

        A rule is a constraint the checker reads, never an action the
        program takes (unbound v2.0 §33) — nothing here executes anything.
        """
        rule_tok = self.expect("RULE")

        if not self.at("OP", "["):
            g = self.peek()
            raise PlanesSyntaxError(
                f"line {g.line}: a rule needs a bracketed name, "
                f"found '{g.value or 'end of line'}'\n"
                f"  try: rule [name-here] subject may not effect-kind")
        self.next()
        if not self.at("NAME"):
            g = self.peek()
            raise PlanesSyntaxError(
                f"line {g.line}: a rule's bracketed name must be a word, "
                f"found '{g.value or 'end of line'}'\n"
                f"  try: rule [name-here] subject may not effect-kind")
        name = self.next().value
        self.expect("OP", "]")

        subject = self.expect("NAME").value

        if not self.at("NAME", "may"):
            g = self.peek()
            raise PlanesSyntaxError(
                f"line {g.line}: expected 'may not' or 'may' after a "
                f"rule's subject, found '{g.value or 'end of line'}'\n"
                f"  try: rule [{name}] {subject} may not effect-kind  "
                f"(forbid)\n"
                f"    or: rule [{name}] {subject} may effect-kind  "
                f"(permit)")
        self.next()
        # `not` present -> forbid; absent -> permit. Neither `may` nor
        # `not` is reserved for this — `not` was already NOT from logical
        # negation, and `may` is read positionally, right here, only.
        assertion = "forbid" if self.accept("NOT") else "permit"
        verb = "may not" if assertion == "forbid" else "may"
        form = f"rule [{name}] {subject} {verb} effect-kind"

        kind_tok = self.peek()
        kind = self.read_effect_word(after=f"'{verb}'")
        if kind not in EFFECT_KINDS:
            raise PlanesSyntaxError(
                f"line {kind_tok.line}: '{kind}' is not an effect kind a "
                f"rule can name\n"
                f"  valid kinds: {', '.join(sorted(EFFECT_KINDS))}")

        target = None
        if self.accept("TO"):
            target = self.expect("STRING").value[1:-1]

        supersedes = None
        supersedes_fingerprint = None
        if self.at("NAME", "supersedes"):
            self.next()
            if not self.at("OP", "["):
                g = self.peek()
                raise PlanesSyntaxError(
                    f"line {g.line}: 'supersedes' needs a bracketed rule "
                    f"name, found '{g.value or 'end of line'}'\n"
                    f"  try: {form} supersedes [other-rule-name]")
            self.next()
            if not self.at("NAME"):
                g = self.peek()
                raise PlanesSyntaxError(
                    f"line {g.line}: 'supersedes' needs a bracketed rule "
                    f"name, found '{g.value or 'end of line'}'\n"
                    f"  try: {form} supersedes [other-rule-name]")
            supersedes = self.next().value
            self.expect("OP", "]")

            if self.at("FINGERPRINT"):
                supersedes_fingerprint = self.next().value[1:]
            elif self.at("OP", "@"):
                at_tok = self.next()
                bad = self.peek()
                raise PlanesSyntaxError(
                    f"line {at_tok.line}: a fingerprint must be exactly "
                    f"six hex characters after '@', found "
                    f"'{bad.value or 'end of line'}'\n"
                    f"  try: {form} supersedes [{supersedes}] @abcdef "
                    f"— or omit it for an unverified override")

        return Rule(name, subject, kind, target, rule_tok.line, supersedes,
                   assertion, supersedes_fingerprint)

    def parse_funcdef(self):
        self.expect("TO")
        parts = [self.expect("NAME").value]
        while self.at("NAME"):
            parts.append(self.next().value)
        name = " ".join(parts)
        params = []
        if self.accept("OF"):
            params.append(self.expect("NAME").value)
            while self.accept("OP", ","):
                params.append(self.expect("NAME").value)
        self.expect("OP", ":")
        return FuncDef(name, params, self.parse_block())

    def parse_foreach(self, as_expr):
        self.expect("FOR")
        self.expect("EACH")
        var = self.expect("NAME").value
        self.expect("IN")
        source = self.parse_or()
        # header may wrap: `for each s in stories` \n `  where ...: s`
        wrapped = False
        if self.at("EOL") and self.peek(1).kind == "BEGIN" \
                and self.peek(2).kind in ("WHERE", "OP"):
            self.next()
            self.next()
            wrapped = True
        where = None
        if self.accept("WHERE"):
            where = self.parse_or()
        self.expect("OP", ":")
        if wrapped:
            body = [self.parse_expr()]
            self.skip_blank()
            self.accept("END")
            return ForEach(var, source, where, body, is_expr=True)
        if as_expr:
            if self.accept("EOL"):
                self.expect("BEGIN")
                body = [self.parse_expr()]
                self.skip_blank()
                self.accept("END")
            else:
                body = [self.parse_expr()]
            return ForEach(var, source, where, body, is_expr=True)
        return ForEach(var, source, where, self.parse_block(), is_expr=False)

    def trailing_or_fail(self, node):
        """`or fail as tag` — same line, or indented continuation.

        `as tag` may be followed by `:` and a block (indented, or a single
        inline statement, same as `if`/`to`/`for each`) — the handler that
        runs on failure, with `tag` bound to the error record. Without it,
        the tag only renames the re-raised failure, as before.
        """
        save = self.i
        if self.at("OR") and self.peek(1).kind == "FAIL":
            self.next()
            self.next()
            self.expect("AS")
            tag = self.expect("NAME").value
            handler = None
            if self.at("OP", ":"):
                self.next()
                handler = self.parse_block()
            return OrFail(node, tag, handler)
        if self.at("EOL") and self.peek(1).kind == "BEGIN" \
                and self.peek(2).kind == "OR" and self.peek(3).kind == "FAIL":
            self.next()
            self.next()
            self.next()
            self.next()
            self.expect("AS")
            tag = self.expect("NAME").value
            handler = None
            if self.at("OP", ":"):
                self.next()
                handler = self.parse_block()
            self.skip_blank()
            self.accept("END")
            return OrFail(node, tag, handler)
        self.i = save
        return node

    def parse_because(self, attach):
        """A trailing `because "..."` on an Assign or Rule — same line, or
        an indented continuation (matching `trailing_or_fail`'s wrapped
        form). `because` is read positionally, right here, only — like
        `may` and `is` — so it stays free as an ordinary name everywhere
        else (test_names.py's reserved-word ceiling).
        """
        save = self.i
        if self.at("NAME", "because"):
            self.next()
            return self.finish_because(attach)
        if self.at("EOL") and self.peek(1).kind == "BEGIN" \
                and self.peek(2).kind == "NAME" and self.peek(2).value == "because":
            self.next()
            self.next()
            self.next()
            node = self.finish_because(attach)
            self.skip_blank()
            self.accept("END")
            return node
        self.i = save
        return attach

    def finish_because(self, attach):
        g = self.peek()
        if not self.at("STRING"):
            raise PlanesSyntaxError(
                f"line {g.line}: 'because' needs a quoted reason\n"
                f'  try: cap = 200 because "the reason"')
        text = self.next().value[1:-1]
        attach.annotation = Because(text, g.line)
        return attach

    def parse_note(self):
        """`note:` followed by an indented block of `from "..."` and
        `derives-from [rule-name]` entries — or a single inline entry.
        Never executes; the interpreter raises if one reaches it.
        """
        note_tok = self.next()   # 'note'
        self.expect("OP", ":")
        entries = []
        if self.accept("EOL"):
            self.expect("BEGIN")
            self.skip_blank()
            while not self.at("END") and not self.at("EOF"):
                entries.append(self.parse_note_entry())
                self.skip_blank()
            self.accept("END")
        else:
            entries.append(self.parse_note_entry())
        return Note(entries, note_tok.line)

    def parse_note_entry(self):
        if self.at("FROM"):
            self.next()
            if not self.at("STRING"):
                g = self.peek()
                raise PlanesSyntaxError(
                    f"line {g.line}: 'from' in a note needs a quoted source\n"
                    f'  try: from "the source"')
            return ("from", self.next().value[1:-1])
        if self.at("NAME", "derives-from"):
            self.next()
            if not self.at("OP", "["):
                g = self.peek()
                raise PlanesSyntaxError(
                    f"line {g.line}: 'derives-from' needs a bracketed rule "
                    f"name, found '{g.value or 'end of line'}'\n"
                    f"  try: derives-from [rule-name]")
            self.next()
            if not self.at("NAME"):
                g = self.peek()
                raise PlanesSyntaxError(
                    f"line {g.line}: 'derives-from' needs a bracketed rule "
                    f"name, found '{g.value or 'end of line'}'\n"
                    f"  try: derives-from [rule-name]")
            name = self.next().value
            self.expect("OP", "]")
            return ("derives-from", name)
        g = self.peek()
        raise PlanesSyntaxError(
            f"line {g.line}: unrecognised entry in a note, "
            f"found '{g.value or 'end of line'}'\n"
            f'  try: from "source"  or  derives-from [rule-name]')

    # ---- expressions

    def parse_expr(self):
        return self.trailing_or_fail(self.trailing_with(self.parse_or()))

    # Field names a with-clause or when-pattern entry may use — the same
    # keyword-as-field-name exception parse_record_field grants, since
    # both are naming a record field, not opening a new construct. Source
    # of truth is grammar/vocabulary.json's field_name_token_kinds.
    FIELD_NAME_KINDS = tuple(_VOCAB["field_name_token_kinds"])

    def at_field_start(self, ahead=0):
        t = self.peek(ahead)
        nxt = self.peek(ahead + 1)
        return (t.kind in self.FIELD_NAME_KINDS
                and nxt.kind == "OP" and nxt.value == ":")

    def trailing_with(self, node):
        """`<expr> with name: expr, name: expr, ...` — record update
        (v5.0 §72), never braced (that is RecordLit). Distinct from the
        module-rename `with` (`use x with a as b`), which parse_statement's
        Use branch parses entirely on its own and never reaches here.
        Chains: `p with a: 1 with b: 2` is two nested RecordUpdate nodes,
        left to right — "compose like any other expression" (§72).
        """
        while self.at("WITH") and self.at_field_start(1):
            self.next()
            fields = [self.parse_with_field()]
            while self.accept("OP", ","):
                if not self.at_field_start(0):
                    self.i -= 1     # this comma belongs to an outer
                                    # context (a call's argument list, a
                                    # list literal, ...), not another field
                    break
                fields.append(self.parse_with_field())
            node = RecordUpdate(node, fields)
        return node

    def parse_with_field(self):
        """`name: expr` inside a with-clause. Not parse_record_field: that
        one reads its value through parse_expr, which would re-enter
        trailing_with and let a *following* with-clause attach to this
        field's value instead of to the RecordUpdate as a whole —
        `p with a: 1 with b: 2` must chain onto `p with a: 1`, not parse
        as `p with a: (1 with b: 2)`. Everything parse_expr does except
        the with-chain itself, since that part is precisely what must not
        recurse here.
        """
        self.skip_bracket_ws()
        t = self.peek()
        if t.kind in self.FIELD_NAME_KINDS:
            key = self.next().value
        else:
            raise PlanesSyntaxError(
                f"line {t.line}: expected a field name, "
                f"found '{t.value or 'end of line'}'\n"
                f"  try: with name: value")
        self.expect("OP", ":")
        return (key, self.trailing_or_fail(self.parse_or()))

    def parse_or(self):
        left = self.parse_and()
        while self.at("OR") and self.peek(1).kind != "FAIL":
            self.next()
            left = BinOp("or", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.accept("AND"):
            left = BinOp("and", left, self.parse_not())
        return left

    def parse_not(self):
        if self.accept("NOT"):
            return Not(self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_plus()
        while (self.at("OP") and self.peek().value in
               ("<", ">", "<=", ">=", "==", "!=")) or self.at("IN") \
                or (self.at("NAME", "is") and self.peek(1).kind == "NOTHING"):
            # `is` is read positionally, right here, only — like `may` in
            # parse_rule — so a program that never writes `is nothing`
            # still has `is` free as an ordinary name (test_names.py's
            # reserved-word ceiling). Requiring NOTHING to follow (rather
            # than accepting bare `is` unconditionally) is what lets
            # `when subject is { ... }` use the same word positionally,
            # one level up in parse_when, without this loop swallowing it
            # first and demanding a NOTHING that was never coming.
            if self.accept("NAME", "is"):
                self.expect("NOTHING")
                left = IsNothing(left)
                continue
            if self.accept("IN"):
                left = BinOp("in", left, self.parse_plus())
            else:
                left = BinOp(self.next().value, left, self.parse_plus())
        return left

    def parse_plus(self):
        """`base plus item` (v5.0 §72) — a named binary connective, bound
        below arithmetic so `xs plus a + b` reads as `xs plus (a + b)`."""
        left = self.parse_additive()
        while self.at("PLUS"):
            self.next()
            left = ListPlus(left, self.parse_additive())
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.at("OP") and self.peek().value in ("+", "-"):
            left = BinOp(self.next().value, left, self.parse_multiplicative())
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.at("OP") and self.peek().value in ("*", "/"):
            left = BinOp(self.next().value, left, self.parse_unary())
        return left

    def parse_unary(self):
        if self.at("OP", "-"):
            self.next()
            return BinOp("-", Num(0), self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_primary()
        while self.at("OP", ".") and (self.peek(1).kind == "NAME"
                                       or self.peek(1).value in KEYWORDS):
            # A field name is not a position where a reserved word can be
            # structural — records nest arbitrarily (v2.0 §35) and a field
            # may be named `first`, `to`, or any other ordinary word that
            # happens to double as a keyword elsewhere.
            self.next()
            node = Field(node, self.next().value)
        if self.at("OP", "["):
            # Planes has no index or slice syntax. Without this check,
            # `s[1]` does not raise at all: parse_primary returns Var("s")
            # for the name, the statement ends there, and the leftover
            # `[1]` tokens are read as an unrelated second statement — a
            # list literal, evaluated and silently discarded. `c = s[1]`
            # then binds `c` to the whole string, not a character, with
            # nothing to say so (found by direct AST inspection,
            # PROBE_LEXER.md §2). This does not add indexing; it turns a
            # silent misparse into a syntax error naming what exists
            # instead (`first n of x`).
            g = self.peek()
            raise PlanesSyntaxError(
                f"line {g.line}: '[' has no meaning here — Planes has no "
                f"index or slice syntax\n"
                f"  try: first n of x — takes the first n code points or "
                f"items; there is no way to take one position or a range")
        return node

    def read_multiword_name(self):
        """Read a multi-word name: every consecutive NAME token, stopping
        at the first non-NAME.

        Names are several NAME tokens, so a clause like `load record as
        load cached` needs a rule for where one name ends. This works only
        because both of this method's callers' terminators (`as`, `with`)
        are reserved words and therefore never arrive as NAME — there is
        no lookahead for a specific stop word here, despite what an
        earlier version of this docstring (and an unused `*stops`
        parameter) implied.
        """
        parts = []
        while self.at("NAME"):
            parts.append(self.next().value)
        if not parts:
            g = self.peek()
            raise PlanesSyntaxError(
                f"line {g.line}: expected a name, "
                f"found '{g.value or 'end of line'}'")
        return " ".join(parts)

    def check_rename_name_ambiguity(self, name, tok):
        """Amber site 4 (§69.5). `name` (the `old` half of a rename — a
        lookup against the used module's exported names, via parse()'s
        `known`) was just consumed whole by read_multiword_name, with no
        table consulted. Check every prefix of it against known_funcs —
        two or more matching prefixes means the greedy full consumption
        was not the only viable reading.
        """
        parts = name.split(" ")
        hits = [k for k in range(1, len(parts) + 1)
                if " ".join(parts[:k]) in Parser.known_funcs]
        if len(hits) < 2:
            return
        readings = []
        for k in hits:
            prefix = " ".join(parts[:k])
            rest = " ".join(parts[k:])
            gloss = (f"`{prefix}` alone" if not rest
                     else f"`{prefix}`, leaving `{rest}` unaccounted for")
            readings.append((prefix if not rest else f"{prefix} | {rest}", gloss))
        msg = render_amber("amber.rename_clause", tok.line, readings, source=name)
        raise PlanesAmbiguity(msg)

    # ---- amber (§69.5): message construction helpers, never consuming

    def _peek_text(self, start, end):
        """Token values from offset `start` (inclusive) to `end`
        (exclusive), space-joined — a best-effort source reconstruction
        for an amber message, not a claim about original spacing."""
        return " ".join(self.peek(k).value or self.peek(k).kind for k in range(start, end))

    def _peek_trailer(self, offset, limit=4):
        """Up to `limit` tokens starting at `offset`, for an amber
        message. Stops at a statement boundary so the trailer reads as a
        fragment, not a runaway scan."""
        end = offset
        for i in range(limit):
            tok = self.peek(offset + i)
            if tok.kind in ("EOL", "EOF", "END", "BEGIN"):
                break
            end = offset + i + 1
            if tok.kind == "OP" and tok.value in (":", ";"):
                break
        return self._peek_text(offset, end)

    def _matching_close_paren_offset(self, open_offset):
        """Offset of the token just after the `)` matching the `(` at
        `open_offset`. Never consumes — paren_is_arglist does the same
        scan for its own decision; this is the read-only twin used only
        to build an amber message."""
        depth, k = 0, open_offset
        while True:
            tok = self.peek(k)
            if tok.kind == "OP" and tok.value == "(":
                depth += 1
            elif tok.kind == "OP" and tok.value == ")":
                depth -= 1
                if depth == 0:
                    return k + 1
            k += 1

    def raise_amber_multiword(self, t, name, bare_hit, ext_hits):
        readings = []
        labels = []
        if bare_hit:
            trailer = self._peek_trailer(0)
            source = name if not trailer else f"{name}  then  {trailer}"
            readings.append((source, f"the value `{name}`, then whatever parses next on its own"))
            labels.append(f"`{name}`")
        for k, probe in ext_hits:
            trailer = self._peek_trailer(k)
            source = probe if not trailer else f"{probe}  {trailer}"
            readings.append((source, f"one call to `{probe}`"))
            labels.append(f"`{probe}`")
        names_txt = labels[0] if len(labels) == 1 else \
            ", ".join(labels[:-1]) + f", and {labels[-1]}" if len(labels) > 2 else \
            f"{labels[0]} and {labels[1]}"
        suggestion = f"({ext_hits[-1][1]})" if ext_hits else f"({name})"
        msg = render_amber("amber.multiword", t.line, readings,
                           names=names_txt, suggestion=suggestion)
        raise PlanesAmbiguity(msg)

    def raise_amber_juxtaposition(self, t, head, next_name):
        readings = [
            (f"{head} ({next_name})",
             f"one call to `{head}`, passing the result of calling `{next_name}`"),
            (f"{head}  then  {next_name}",
             f"`{head}` with no argument, then a separate call to `{next_name}`"),
        ]
        msg = render_amber("amber.juxtaposition", t.line, readings, head=head, next=next_name)
        raise PlanesAmbiguity(msg)

    def raise_amber_juxtaposition_unknown(self, t, subject):
        readings = [
            (f"{subject}(...)",
             f"if `{subject}` takes an argument here, one call using what follows"),
            (f"{subject}  then  ...",
             f"if `{subject}` takes no argument here, a separate statement follows"),
        ]
        msg = render_amber("amber.juxtaposition.unknown_arity", t.line, readings, subject=subject)
        raise PlanesAmbiguity(msg)

    def check_juxtaposition_ambiguity(self, name, t):
        """Amber site 2 (§69.5). `name` is a known function directly
        followed by a bare NAME, with nothing else in the token stream
        deciding whether that NAME is the argument or the start of the
        next statement. Returns whether the following NAME should be
        consumed as the argument; raises when both readings fit."""
        arity = Parser.known_funcs.get(name)
        if arity is None:
            self.raise_amber_juxtaposition_unknown(t, name)
        if arity == 0:
            return False
        next_name = self.peek().value
        if next_name not in Parser.known_funcs:
            return True
        next_arity = Parser.known_funcs.get(next_name)
        if next_arity is None:
            self.raise_amber_juxtaposition_unknown(t, next_name)
        if next_arity == 0:
            self.raise_amber_juxtaposition(t, name, next_name)
        return True

    def check_paren_arglist_ambiguity(self, name, t):
        """Amber site 3 (§69.5). paren_is_arglist already decided an
        operator after the close paren means the parens were a
        sub-expression, not an argument list — a lookahead rule, not a
        name-table decision. Arity is what turns it into one: called with
        `self` positioned at the `(`, right after paren_is_arglist
        returned False for it."""
        arity = Parser.known_funcs.get(name)
        close = self._matching_close_paren_offset(0)
        paren_src = self._peek_text(1, close - 1)
        rest_src = self._peek_trailer(close)
        if arity is None:
            readings = [
                (f"{name}({paren_src})",
                 f"if `{name}` takes one argument here, this call alone"),
                (f"{name}({paren_src}) {rest_src}".strip(),
                 "if not, the whole expression including what follows"),
            ]
            msg = render_amber("amber.paren_arglist.unknown_arity", t.line, readings, head=name)
            raise PlanesAmbiguity(msg)
        if arity != 1:
            return
        readings = [
            (f"{name}({paren_src}) {rest_src}".strip(),
             f"one call to `{name}`, argument = everything up to and including `{rest_src}`"),
            (f"({name}({paren_src})) {rest_src}".strip(),
             f"one call to `{name}`, argument = `{paren_src}` alone; "
             f"`{rest_src}` applies to the call's result, not inside it"),
        ]
        msg = render_amber("amber.paren_arglist", t.line, readings,
                           head=name, paren_expr=paren_src)
        raise PlanesAmbiguity(msg)

    def paren_is_arglist(self):
        """Looking at `(`: is this an argument list, or a parenthesised
        argument that continues into a larger expression?

        Scan to the matching close paren. If an arithmetic or comparison
        operator follows it, the parens were a sub-expression.
        """
        depth, k = 0, 0
        while True:
            t = self.peek(k)
            if t.kind == "EOF":
                return True
            if t.kind == "OP" and t.value == "(":
                depth += 1
            elif t.kind == "OP" and t.value == ")":
                depth -= 1
                if depth == 0:
                    nxt = self.peek(k + 1)
                    if nxt.kind == "OP" and nxt.value in (
                            "+", "-", "*", "/", "<", ">",
                            "<=", ">=", "==", "!="):
                        return False
                    return True
            k += 1

    def parse_record_field(self):
        """`name: expr`. The key is a bare word, never an expression."""
        self.skip_bracket_ws()
        t = self.peek()
        if t.kind == "NAME":
            key = self.next().value
        elif t.kind in self.FIELD_NAME_KINDS:
            # A field name is not a position where a keyword can be
            # structural. `{ to: "x", from: "y" }` must work.
            key = self.next().value
        else:
            raise PlanesSyntaxError(
                f"line {t.line}: expected a field name, "
                f"found '{t.value or 'end of line'}'\n"
                f"  try: {{ name: value }}")
        self.expect("OP", ":")
        return (key, self.parse_expr())

    def parse_when(self):
        """`when subject is { field: expr, bindname, ... }: body
        [else: els]` (v5.0 §74). `WHEN` is already consumed by the caller.
        A chained dispatch ladder (`when ... else: when ... else: ...`)
        needs no dedicated grammar — the else block is an ordinary block,
        and a `When` is an ordinary statement, so nesting one inside the
        other falls out of parse_block for free, the same way `if / else:
        if` already forms an if-elif-else chain in this language."""
        subject = self.parse_expr()
        self.expect("NAME", "is")
        self.expect("OP", "{")
        pattern = []
        self.skip_bracket_ws()
        if not self.at("OP", "}"):
            pattern.append(self.parse_when_pattern_entry())
            while self.accept("OP", ","):
                self.skip_bracket_ws()
                if self.at("OP", "}"):
                    break
                pattern.append(self.parse_when_pattern_entry())
        self.skip_bracket_ws()
        self.expect("OP", "}")
        self.expect("OP", ":")
        body = self.parse_block()
        els = []
        save = self.i
        self.skip_blank()
        if self.accept("ELSE"):
            self.expect("OP", ":")
            els = self.parse_block()
        else:
            self.i = save
        return When(subject, pattern, body, els)

    def parse_when_pattern_entry(self):
        """`name: expr` (a match constraint) or a bare `name` (a binding).
        Same field-name recognition as parse_record_field — a pattern
        entry names a field, so a keyword like `to` or `from` must work
        here exactly as it does in a record literal."""
        self.skip_bracket_ws()
        t = self.peek()
        if t.kind == "NAME" or t.kind in self.FIELD_NAME_KINDS:
            name = self.next().value
        else:
            raise PlanesSyntaxError(
                f"line {t.line}: expected a field name, "
                f"found '{t.value or 'end of line'}'\n"
                f"  try: {{ name: value }}  or  {{ name }}")
        if self.at("OP", ":"):
            self.next()
            return (name, ("match", self.parse_expr()))
        return (name, ("bind", name))

    def parse_primary(self):
        t = self.peek()

        if t.kind == "FIRST":
            self.next()
            n = self.parse_unary()
            self.expect("OF")
            return BinOp("first", n, self.parse_unary())

        if t.kind == "ROUND":
            # `round total to 2 places` — rounding is an operation with a
            # name, so it appears in the derivation like anything else.
            self.next()
            value = self.parse_unary()
            self.expect("TO")
            places = self.parse_unary()
            self.accept("PLACES")
            return Round(value, places)

        if t.kind == "FOR":
            return self.parse_foreach(as_expr=True)

        if t.kind == "NUMBER":
            self.next()
            # Literals are exact: `0.1` is one tenth, not the nearest float.
            return Num(Number.parse(t.value))

        if t.kind == "STRING":
            self.next()
            return Str(t.value[1:-1])

        if t.kind == "TRUE":
            self.next()
            return Bool(True)
        if t.kind == "FALSE":
            self.next()
            return Bool(False)
        if t.kind == "NOTHING":
            self.next()
            return Nothing()

        if t.kind == "OP" and t.value == "{":
            self.next()
            fields = []
            self.skip_bracket_ws()
            if not self.at("OP", "}"):
                fields.append(self.parse_record_field())
                while self.accept("OP", ","):
                    self.skip_bracket_ws()
                    if self.at("OP", "}"):
                        break          # trailing comma
                    fields.append(self.parse_record_field())
            self.skip_bracket_ws()
            self.expect("OP", "}")
            seen = set()
            for k, _ in fields:
                if k in seen:
                    raise PlanesSyntaxError(
                        f"line {t.line}: field '{k}' appears twice in this record")
                seen.add(k)
            return RecordLit(fields)

        if t.kind == "OP" and t.value == "[":
            self.next()
            items = []
            self.skip_bracket_ws()
            if not self.at("OP", "]"):
                items.append(self.parse_expr())
                while self.accept("OP", ","):
                    self.skip_bracket_ws()
                    if self.at("OP", "]"):
                        break          # trailing comma
                    items.append(self.parse_expr())
            self.skip_bracket_ws()
            self.expect("OP", "]")
            return ListLit(items)

        if t.kind == "OP" and t.value == "(":
            self.next()
            e = self.parse_expr()
            self.expect("OP", ")")
            return e

        if t.kind == "NAME":
            self.next()
            name = t.value
            if self.accept("OF"):
                args = [self.parse_unary()]
                while self.accept("OP", ","):
                    args.append(self.parse_unary())
                return Call(name, args, t.line)
            if self.at("OP", "("):
                # `add(2, 3)` is an argument list. But `ask (api base) + "/"`
                # is one argument that merely starts with a parenthesis, and
                # the two look identical up to the closing paren. Decide by
                # what follows it: an operator means the parens were part of
                # a larger expression, not the whole argument list.
                if not self.paren_is_arglist():
                    self.check_paren_arglist_ambiguity(name, t)
                    return Call(name, [self.parse_additive()], t.line)
                self.next()
                args = []
                if not self.at("OP", ")"):
                    args.append(self.parse_expr())
                    while self.accept("OP", ","):
                        args.append(self.parse_expr())
                self.expect("OP", ")")
                return Call(name, args, t.line)
            # multi-word name, longest match against known functions.
            # Handles both `fetch stories` and `phone home of settings`.
            # Amber site 1 (§69.5): collect EVERY k (including k=0, the
            # bare name itself) whose joined text is a known function —
            # two or more means the parser will not silently prefer the
            # longest.
            if self.at("NAME"):
                ext_hits = []
                probe = name
                k = 0
                while self.peek(k).kind == "NAME":
                    probe += " " + self.peek(k).value
                    k += 1
                    if probe in Parser.known_funcs:
                        ext_hits.append((k, probe))
                bare_hit = name in Parser.known_funcs
                if (1 if bare_hit else 0) + len(ext_hits) >= 2:
                    self.raise_amber_multiword(t, name, bare_hit, ext_hits)
                if ext_hits:
                    j, best = ext_hits[0]
                    for _ in range(j):
                        self.next()
                    if self.accept("OF"):
                        args = [self.parse_unary()]
                        while self.accept("OP", ","):
                            args.append(self.parse_unary())
                        return Call(best, args, t.line)
                    return Call(best, [], t.line)
            if name in Parser.known_funcs:
                # A known function may take one argument by juxtaposition:
                # `ask "https://" + text of id` and `ask url` both read as
                # one call on the whole following expression. This differs
                # deliberately from `of`, which binds tightly so
                # `detail of id + 1` is `(detail of id) + 1`.
                # Juxtaposition reads as "apply this to what follows";
                # `of` reads as "apply this to that one thing".
                takes_arg = (self.at("STRING") or self.at("NUMBER")
                             or self.at("OP", "(") or self.at("OP", "["))
                if not takes_arg and self.at("NAME"):
                    # A bare name only counts as an argument when it is not
                    # itself the start of a call — otherwise `main` followed
                    # by a statement would absorb it. Amber site 2 (§69.5):
                    # when both readings have a shape that fits, the parser
                    # refuses instead of guessing which one was meant.
                    takes_arg = self.check_juxtaposition_ambiguity(name, t)
                if takes_arg:
                    return Call(name, [self.parse_additive()], t.line)
                return Call(name, [], t.line)
            return Var(name)

        raise PlanesSyntaxError(
            f"line {t.line}: expected a value, found '{t.value or 'end of line'}'")


def _param_arity(tokens, j):
    """Count comma-separated NAME parameters starting at index `j`, which
    points at the token right after `of`. Zero when there is no parameter
    there at all (a bare `of` never occurs; this only fires when `of`
    itself was absent, handled by the caller)."""
    if tokens[j].kind != "NAME":
        return 0
    count = 1
    j += 1
    while tokens[j].kind == "OP" and tokens[j].value == "," and tokens[j + 1].kind == "NAME":
        count += 1
        j += 2
    return count


def prescan_funcs(tokens):
    """Function names and arities, read before the real parse.

    A multi-word call is several NAME tokens; only a name table can tell the
    parser they are one call. So names have to be collected first. Arity is
    the number of comma-separated parameters after `of` — 0 when there is no
    `of` clause at all (`to main:`). Returns {name: arity}.
    """
    names = {}
    for i, t in enumerate(tokens):
        if t.kind == "FOREIGN":
            # A foreign declaration names a callable, same as `to`.
            j, parts = i + 1, []
            while tokens[j].kind == "NAME":
                parts.append(tokens[j].value)
                j += 1
            if parts:
                arity = _param_arity(tokens, j + 1) if tokens[j].kind == "OF" else 0
                names[" ".join(parts)] = arity
            continue
        if t.kind != "TO":
            continue
        # `to` also appears inside `write x to "path"`. A definition is the
        # one that starts a statement.
        if i > 0 and tokens[i - 1].kind not in ("EOL", "BEGIN", "END"):
            continue
        j, parts = i + 1, []
        while tokens[j].kind == "NAME":
            parts.append(tokens[j].value)
            j += 1
        if not parts:
            raise PlanesSyntaxError(
                f"line {tokens[i + 1].line}: "
                f"'{tokens[i + 1].value}' is a reserved word and cannot "
                f"start a function name\n"
                f"  reserved: {', '.join(sorted(KEYWORDS))}")
        # A reserved word mid-name is the same problem, one token later:
        # `to first thing` reads as the builtin `first`, not a name.
        if tokens[j].kind not in ("OF", "OP", "EOL", "EOF"):
            raise PlanesSyntaxError(
                f"line {tokens[j].line}: "
                f"'{tokens[j].value}' is a reserved word and cannot "
                f"appear in the function name "
                f"'{' '.join(parts)} {tokens[j].value}'\n"
                f"  reserved: {', '.join(sorted(KEYWORDS))}")
        arity = _param_arity(tokens, j + 1) if tokens[j].kind == "OF" else 0
        names[" ".join(parts)] = arity
    return names


def parse(src, known=None):
    """Parse a program.

    `known` supplies function names defined elsewhere — either a mapping of
    name to arity, or a bare set/iterable of names, in which case arity is
    `None` (unknown) for each. Multi-word names must be known before a call
    site can be parsed — `api base` is two NAME tokens, and only a name
    table can say it is one call. Without this a file could not call a
    multi-word function from a module it uses.

    When the same name appears more than once, this file's own definitions
    win over `known` (another file in the graph), which wins over a
    builtin of the same name — matching how shadowing already works at
    runtime (interp.py resolves a user function before a builtin). `None`
    (unknown arity) is never treated as a match or a non-match by anything
    that reads it later; it is reported.
    """
    toks = tokenize(src)
    if known is None:
        known_map = {}
    elif isinstance(known, dict):
        known_map = known
    else:
        known_map = {name: None for name in known}
    builtins_map = {b["name"]: b.get("arity", 1) for b in _VOCAB["builtins"]}
    merged = dict(builtins_map)
    merged.update(known_map)
    merged.update(prescan_funcs(toks))
    Parser.known_funcs = merged
    return Parser(toks).parse_program()


def scan_names(src):
    """Function names defined in a source file, without a full parse."""
    return prescan_funcs(tokenize(src))
