"""Rule-plane checker — permits, exception resolution, fingerprinting.

Tests inception checkpoint §8's claim that a rule is the same question
the analyser and Why already answer, asked at compile time. shapes.py computes a
program's effect surface; this module only consumes it, through the public
`Surface` queries (`at`, `targets`, `touches`, `declared`, `kinds`,
`boundaries`, and — since the static derivation graph build — `origins_of`,
the one query named-subject resolution needs). If this file ever needs to
reach inside `Analyser`, `Consts`, or `Effect` construction, that is a
finding about §8 — report it, don't route around it. `hashlib`, for
fingerprinting (§5), and `planes_text`, for the four-entry STRING escape
table a rule's `target` may now contain (fix/string-escapes-and-bootstrap)
and its own violation/conflict messages must re-escape when quoting it
back, are the only imports this file has ever needed — stdlib, or a leaf
utility with no project dependencies of its own, never a `shapes`
coupling.

Matching is static and structural (unbound v2.0 §34): no execution. A rule
is never triggered; it is only ever checked against a surface that was
already computed without running anything.
"""
import hashlib

from planes_text import escape_string_literal


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


class RuleConflict(Exception):
    """The rule set itself does not resolve — a compile error (v2.0 §32).

    Raised for several distinct authoring problems, all structural
    (checked before any effect is matched):

    - `supersedes` names a rule that does not exist, or a rule that
      supersedes itself.
    - A `supersedes` clause carries a fingerprint that no longer matches
      the rule it names — the named rule changed after the override was
      written against it (v2.0 §29).
    - A permit rule excepts no forbid rule — it neither supersedes nor
      narrows one of the same kind, so it has no force against anything.
    - Two distinct rules are equally specific — same kind, same covered
      set — and neither narrows nor supersedes the other. If they share
      an assertion, that is the pre-existing ambiguity: nothing says
      which is authoritative. If they don't, that is v2.0 §32's "two
      rules demand opposite things" — one forbids exactly what the other
      permits, expressible for the first time now that a permitting
      assertion exists.
    - A rule's target is URL-shaped and carries a query string or
      fragment (B2) — a rule target names an address, and only an
      effect's own query and fragment are ever ignored, never the
      rule's.
    """
    pass


def fingerprint(rule):
    """A stable, content-derived identity for a rule (v2.0 §29).

    Computed from what the rule means — subject, assertion, kind, target —
    never its name or line: a rename or a moved line changes neither the
    rule's meaning nor its fingerprint. `hashlib.sha256`, not `hash()`,
    because `hash()` is salted per process and would give a different
    answer on every run; the whole point is that the checker can recompute
    it later and compare. Truncated to six hex characters for legibility —
    the algorithm and the length are not load-bearing, only stability is.
    """
    canonical = "\x1f".join(
        [rule.subject, rule.assertion, rule.kind, rule.target or ""])
    return hashlib.sha256(canonical.encode()).hexdigest()[:6]


def condition(rule):
    """A rule's condition, exactly as written, for echoing into a message.

    A violation should be readable without opening the file to look up
    what the named rule actually says — the same reasoning behind "error
    messages must name the fix" (locked, unbound v1.1 §22 item 1). A
    permit rendered as "may not" would be a lie in the one place the
    reader is looking, so the assertion is read off the rule, not assumed.
    """
    verb = "may not" if rule.assertion == "forbid" else "may"
    text = f"{rule.subject} {verb} {rule.kind}"
    if rule.target is not None:
        text += f' to "{escape_string_literal(rule.target)}"'
    return text


class Violation:
    """One forbid rule matched against one effect — or, for the vacuous
    shape below, matched against nothing at all.

    Five shapes, told apart by `cleared_by` / `narrowed_by` / `vacuous` /
    `contradicts_rule`:

    - A real violation: none set.
    - A violation narrowed by a more specific sibling forbid rule that
      also matched: `narrowed_by` names it. Still a real violation — two
      forbid rules matching the same effect are not in conflict, and both
      are reported, but as related rather than as independent failures.
    - A prohibition a permit cleared: `cleared_by` names the permit.
      `is_violation` is False, and this must not count toward a caller's
      exit code — but it is still returned and rendered, so the exception
      is visible where a reader actually meets it (v2.0 §31's
      generated-marker reasoning, applied to output).
    - A named-subject rule whose subject resolved but never matched a
      single effect (P-Q19): `vacuous=True`, `effect=None` — there is no
      effect, that is the point. `is_violation` is False for the same
      reason `cleared_by` makes it False: this is not a violation, it is a
      fact about the check the reader needs, not a failure of the program.
    - A contradiction (B3, Track 0 #5): both rules of a declared
      `contradicts` pair matched at least one effect in this surface.
      `self.rule`/`self.effect` are the declaring rule and the effect it
      matched; `contradicts_rule`/`contradicts_effect` are the named
      rule's own match. `is_violation` is True — an authored
      incompatibility both sides actually reach is a real problem with the
      program, exit code 1 like a genuine violation, not an inert fact
      like `vacuous`.
    """

    def __init__(self, rule, effect, uncertain=False, cleared_by=None,
                narrowed_by=None, origins=None, vacuous=False,
                contradicts_rule=None, contradicts_effect=None):
        self.rule = rule
        self.effect = effect
        # True when the effect's target is computed=True: the analyser
        # could not pin it down, so this is a possible match, not a
        # confirmed one. Conservative at the boundary (v2.0 §34) — widening
        # is sound, assuming a computed target is safe is not.
        self.uncertain = uncertain
        self.cleared_by = cleared_by
        self.narrowed_by = narrowed_by or []
        # Every name/file this effect's target derives from (Surface.
        # origins_of) — rendered as a derivation line when non-empty (§24).
        self.origins = origins or []
        self.vacuous = vacuous
        # Which of §2's three situations produced this vacuous entry — set
        # by check() after construction, not a constructor argument, since
        # only the vacuous shape needs it. 1 = no effect of the rule's kind
        # at all; 2 = effects of the kind exist but none derive from the
        # subject; 3 = the subject derives an effect of the kind, but the
        # rule's target excludes every one.
        self.vacuous_situation = None
        # The other rule of a declared `contradicts` pair, and the effect
        # IT matched — set only for the contradiction shape (B3).
        self.contradicts_rule = contradicts_rule
        self.contradicts_effect = contradicts_effect

    @property
    def is_violation(self):
        if self.contradicts_rule is not None:
            return True
        return self.cleared_by is None and not self.vacuous

    def render(self):
        if self.contradicts_rule is not None:
            return self._render_contradiction()

        if self.vacuous:
            return self._render_vacuous()

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
                f'computed value may or may not be '
                f'"{escape_string_literal(self.rule.target)}"')
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

    def _render_contradiction(self):
        """B3 (Track 0 #5): both rules of a declared `contradicts` pair
        matched at least one effect in this surface. `self.rule` is the
        rule that wrote the `contradicts` clause and `self.effect` is the
        effect it matched; `contradicts_rule`/`contradicts_effect` are the
        named rule's own match. Names both rules, one effect each matched,
        and the declaring rule's `because` if it has one — never the named
        rule's, since the declaration belongs to the rule that wrote the
        clause."""
        a, b = self.rule, self.contradicts_rule
        ea, eb = self.effect, self.contradicts_effect
        line = (f"[{a.name}] contradicts [{b.name}]: both apply to this "
                f"program — [{a.name}] at line {ea.site} ({ea}), "
                f"[{b.name}] at line {eb.site} ({eb})")
        if a.annotation is None:
            return line
        return line + f'\n  [{a.name}] because "{a.annotation.text}"'

    def as_json(self):
        """Every field `render()` reads, as data rather than prose (H1).

        A `--json --rules` consumer gets the rule name, the rule's own
        kind/target/assertion/`because`, the specific effect (kind, boundary,
        target, line) it matched or None for the vacuous shape, and the
        supersedes/permit outcome (`cleared_by`) or narrowing sibling
        (`narrowed_by`) — every structural fact `render()`'s prose is built
        from. `message` is `render()`'s own text, included verbatim beside
        the fields so a host can print exactly what text mode prints without
        re-deriving it (js/rules.mjs's Violation.asJson and Rules.swift's
        Violation.asJSON must agree with this field for field).

        `contradiction` (B3) is None except for the contradiction shape,
        where it names both rules of the declared pair and one effect
        each matched — self-contained, so a consumer reading only this key
        gets both sides without also reading the top-level `rule`/`effect`.

        `origins` dedupes the same way `render()`'s derivation line does —
        by the formatted "name (file)" string, not by the raw pair — so the
        structured list and the rendered line never disagree about what
        counts as one origin.
        """
        rule = self.rule
        effect = self.effect
        seen = {}
        for n, f in self.origins:
            key = f"{n} ({f})" if f else n
            seen.setdefault(key, (n, f))
        origins = [{"name": n, "file": f} for _, (n, f) in sorted(seen.items())]
        return {
            "rule": rule.name,
            "rule_line": rule.line,
            "assertion": rule.assertion,
            "kind": rule.kind,
            "target": rule.target,
            "condition": condition(rule),
            "because": rule.annotation.text if rule.annotation is not None else None,
            "is_violation": self.is_violation,
            "vacuous": self.vacuous,
            "vacuous_situation": self.vacuous_situation,
            "uncertain": self.uncertain,
            "effect": None if effect is None else {
                "kind": effect.kind,
                "boundary": effect.boundary,
                "target": effect.target,
                "line": effect.site,
            },
            "cleared_by": None if self.cleared_by is None else {
                "rule": self.cleared_by.name,
                "line": self.cleared_by.line,
            },
            "narrowed_by": [{"rule": r.name, "line": r.line}
                           for r in self.narrowed_by],
            "contradiction": None if self.contradicts_rule is None else {
                "rule": rule.name,
                "effect": None if effect is None else {
                    "kind": effect.kind,
                    "boundary": effect.boundary,
                    "target": effect.target,
                    "line": effect.site,
                },
                "with_rule": self.contradicts_rule.name,
                "with_effect": {
                    "kind": self.contradicts_effect.kind,
                    "boundary": self.contradicts_effect.boundary,
                    "target": self.contradicts_effect.target,
                    "line": self.contradicts_effect.site,
                },
            },
            "origins": origins,
            "message": self.render(),
        }

    def _render_vacuous(self):
        """§2's three situations, one message each — never the word
        "violated": this is not one (§3.1)."""
        rule = self.rule
        situation = self.vacuous_situation

        if situation == 1:
            header = (f"[{rule.name}] (line {rule.line}) checked nothing "
                      f"— subject '{rule.subject}' resolves in this file, "
                      f"but the program performs no '{rule.kind}' effect "
                      f"at all")
            reason = "the rule is inert against this program as written"
            fix = ("check the program still performs the effect you "
                  "expect, or remove the rule if it no longer applies")
        elif situation == 3:
            header = (f"[{rule.name}] (line {rule.line}) checked nothing "
                      f"— subject '{rule.subject}' derives a "
                      f"'{rule.kind}' effect, but the rule's target "
                      f"excludes every one")
            reason = (f"'{rule.subject}' reaches this effect kind, but "
                      f'never at "{escape_string_literal(rule.target)}"')
            fix = (f"check the target matches where '{rule.subject}' "
                  f"actually goes, or remove the target to check every "
                  f"'{rule.kind}' effect '{rule.subject}' reaches")
        else:
            header = (f"[{rule.name}] (line {rule.line}) checked nothing "
                      f"— subject '{rule.subject}' resolves in this file, "
                      f"but no '{rule.kind}' effect derives from it")
            reason = (f"the program performs '{rule.kind}', but to a "
                      f"target that does not derive from '{rule.subject}'")
            fix = ("check the subject names the value you meant, or "
                  "write the rule against 'anything'")

        return "\n".join([header, f"  {reason}", f"  {fix}"])

    def __str__(self):
        return self.render()


class RuleResults(list):
    """`check()`'s return value — every `Violation`, plus what it resolved.

    A `list` subclass so every existing caller — `if not results`,
    iteration, `any(v.is_violation for v in results)`, `len()`, indexing —
    keeps working exactly as before; `check()`'s return type does not
    change.

    `resolved_subjects` is the readback a caller needs to report how many
    named subjects were resolved without re-deriving that count from its
    own input and assuming it agrees with what `check()` actually did
    (P-Q20, unearned-assertion audit item 2). It accumulates inside
    `check()` only after `_resolve_subject` returns without raising —
    surviving resolution is what puts a name in the list, and that
    ordering is the mechanism, not a comment promising it.
    """
    def __init__(self, items=(), resolved_subjects=()):
        super().__init__(items)
        self.resolved_subjects = list(resolved_subjects)


def _ascii_lower(text):
    """Fold only ASCII A-Z to a-z; every other character is left exactly
    as written (B2 follow-up). Scheme and host are DNS-shaped, and DNS
    case-insensitivity is ASCII-only — a full Unicode lower (`str.lower`)
    can map a character context-dependently (a final Greek sigma `Σ`
    becomes `ς` under some case-folding rules, `σ` under
    others), and there is no guarantee another host's Unicode tables
    agree with this one's on the exact mapping. That would silently
    break the byte-for-byte agreement the three hosts promise. Used only
    where B2 asks for case-insensitive comparison (scheme, host); a
    rule's path stays case-sensitive and untouched by this function.
    js/rules.mjs's and Rules.swift's identically-named function must
    agree with this one.
    """
    return "".join(
        chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in text)


def _is_scheme(text):
    """Is `text` a legal URL scheme (`ALPHA *( ALPHA / DIGIT / "+" / "-" /
    "." )`, RFC 3986 §3.1) — the one piece of a `scheme://host/path`
    target ASCII-only by construction, so this is a plain ASCII check,
    never a code-point one.
    """
    if not text:
        return False
    first = _ascii_lower(text[0])
    if not ("a" <= first <= "z"):
        return False
    for ch in text[1:]:
        lower = _ascii_lower(ch)
        if ("a" <= lower <= "z") or ("0" <= ch <= "9") or ch in "+-.":
            continue
        return False
    return True


def _parse_url_target(target):
    """Split `target` into (scheme, host, path, query, fragment) if it has
    the shape `scheme://host[:port][/path][?query][#fragment]` (B2); `None`
    otherwise — a file path, a `queue:send`-style name, or console text,
    none of which are addresses this matches by host and path (B2 keeps
    those on today's exact-string matching, unchanged).

    `query` and `fragment` carry their leading `?`/`#` when present, else
    `None`. No percent-decoding, no Unicode normalisation, no default-port
    folding: every piece is exactly the substring as written (B2). Compared
    by `js/rules.mjs`'s and `Rules.swift`'s identically-named function,
    which must agree with this one.
    """
    sep = target.find("://")
    if sep <= 0 or not _is_scheme(target[:sep]):
        return None
    scheme = target[:sep]
    rest = target[sep + 3:]
    host_end = len(rest)
    for i, ch in enumerate(rest):
        if ch in "/?#":
            host_end = i
            break
    host = rest[:host_end]
    tail = rest[host_end:]
    if tail[:1] in ("?", "#"):
        path, remainder = "", tail
    else:
        path_end = len(tail)
        for i, ch in enumerate(tail):
            if ch in "?#":
                path_end = i
                break
        path, remainder = tail[:path_end], tail[path_end:]
    if remainder[:1] == "#":
        query, fragment = None, remainder
    elif remainder[:1] == "?":
        hash_at = remainder.find("#")
        query, fragment = (remainder, None) if hash_at < 0 else (
            remainder[:hash_at], remainder[hash_at:])
    else:
        query, fragment = None, None
    return scheme, host, path, query, fragment


def _path_covers(rule_path, effect_path):
    """Does `rule_path` cover `effect_path` at a "/" boundary (B2)?

    An empty path or "/" in the rule covers every path on the host.
    Otherwise `rule_path` must be a prefix of `effect_path`, and either
    they're equal, `rule_path` itself already ends in "/" (a rule path
    ending in "/" covers everything under it, including a path that adds
    more path straight after the slash), or the next character of
    `effect_path` past the prefix is "/". Compared case-sensitively,
    exactly as written — no percent-decoding, no Unicode normalisation.
    """
    if rule_path in ("", "/"):
        return True
    if effect_path == rule_path:
        return True
    if not effect_path.startswith(rule_path):
        return False
    if rule_path.endswith("/"):
        return True
    return effect_path[len(rule_path):len(rule_path) + 1] == "/"


def _url_covers(rule_target, effect_target):
    """Does the URL-shaped `rule_target` cover the URL-shaped
    `effect_target` (B2)? Same scheme and host, compared case-
    insensitively; port is part of the host and compared exactly as
    written — no default-port folding, so `https://x` and `https://x:443`
    differ. The effect's own query and fragment are ignored entirely —
    only its path is compared, against the rule's path, by `_path_covers`.
    """
    r_scheme, r_host, r_path, _, _ = _parse_url_target(rule_target)
    e_scheme, e_host, e_path, _, _ = _parse_url_target(effect_target)
    if _ascii_lower(r_scheme) != _ascii_lower(e_scheme):
        return False
    if _ascii_lower(r_host) != _ascii_lower(e_host):
        return False
    return _path_covers(r_path, e_path)


def _scope_covers(wide, narrow):
    """Does every address `narrow` (a target string, or `None`) ranges
    over also fall inside `wide`'s range (B2)? `None` is the top of the
    lattice — every target of the kind. Identical strings are always the
    same scope. A URL-shaped pair compares by `_url_covers`; anything
    else — a target that isn't URL-shaped, or a URL paired with a
    non-URL — only ever covers its own exact string, exactly as before
    B2.
    """
    if wide is None:
        return True
    if narrow is None:
        return False
    if wide == narrow:
        return True
    if _parse_url_target(wide) is None or _parse_url_target(narrow) is None:
        return False
    return _url_covers(wide, narrow)


def _same_scope(a, b):
    """Do `a` and `b` (two rule targets, or `None`) range over exactly
    the same addresses (B2)? Equal by mutual coverage rather than by
    `==`, so `"https://x"` and `"https://x/"` — two spellings of "every
    path on x" — are the same scope even though the strings differ.
    """
    return _scope_covers(a, b) and _scope_covers(b, a)


def narrows(b, a):
    """Does rule `b` cover a strict subset of what rule `a` ranges over?

    (v2.0 §30; re-proven for host/path covering at B2.) A pure scope
    comparison — kind and target only, never assertion — so the same
    function resolves specificity between two forbids, two permits, or a
    permit and the forbid it excepts. Comparable only within the same
    kind. `b` narrows `a` when `a`'s covered set contains `b`'s and the
    two aren't the same scope (B2's `_scope_covers`) — the pre-B2 case
    (`a` has no target, `b` does) is one instance of this; a rule whose
    covered address set is strictly inside another's target now is too
    (`rule [ok] ... to "https://x/public"` narrows `rule [deny] ... to
    "https://x"`). Two rules of the same scope (including both
    unrestricted, or two spellings of the same address family) are
    equally specific — neither narrows the other, even if their names or
    exact target strings differ.
    """
    if a.name == b.name:
        return False
    if a.kind != b.kind:
        return False
    return _scope_covers(a.target, b.target) and not _scope_covers(b.target, a.target)


def _target_matches(rule, effect):
    """Does this rule's target reach this effect?

    Returns (matched, uncertain). No target on the rule means every
    target of the kind — always a certain match. Otherwise, for an
    effect whose own target is computed=True (the analyser could not pin
    it down): a possible match, not a confirmed one — conservative at
    the boundary (v2.0 §34): widening is sound, assuming a computed
    target is safe is not — unless its known chunks rule the rule's
    target out, which is a certain non-match (v37.0 §513, B2's
    `_pattern_excludes` below). For a literal effect target: when both
    it and the rule's target are URL-shaped (`scheme://host/path`), the
    rule's target must *cover* the effect's — the same address, or
    anything under it (B2) — with the effect's own query and fragment
    ignored; otherwise (a file path, a `queue:send`-style name, console
    text — either target not URL-shaped) an exact string match, exactly
    as before B2.
    """
    if rule.target is None:
        return True, False
    if effect.computed:
        if _pattern_excludes(rule.target, effect.target):
            return False, False
        return True, True
    if (_parse_url_target(rule.target) is not None
            and _parse_url_target(effect.target) is not None):
        return _url_covers(rule.target, effect.target), False
    return effect.target == rule.target, False


HOLE = "{...}"
NO_DESTINATION = " (destination not stated)"


def _pattern_excludes(rule_target, effect_target):
    """Can this computed target provably never be covered by the rule's
    target (B2; originally "never equal", v37.0 §513)?

    A computed target is not an unknown one (v37.0 §511): shapes.py keeps
    every statically known chunk and marks only the unknown spans `{...}`,
    and those chunks are facts. When the rule's target isn't URL-shaped,
    covering is exact-string equality, unchanged since v37.0:
    `_exact_pattern_excludes` below. When it is, B2 re-proves the guard for
    host/path covering in `_url_pattern_excludes`.

    Only ever removes matches that could not occur (v37.0 §514): anything
    this cannot rule out stays a possible match. A pattern that is nothing
    but holes excludes nothing, and neither does a computed target that is
    not a pattern at all — a foreign function with no stated destination
    (`<host function> (destination not stated)`), which names where the
    claim came from, not where the request goes. js/rules.mjs's
    patternExcludes and Rules.swift's patternExcludes must agree with this.
    """
    if HOLE not in effect_target or effect_target.endswith(NO_DESTINATION):
        return False
    rule_url = _parse_url_target(rule_target)
    if rule_url is None:
        return _exact_pattern_excludes(rule_target, effect_target)
    r_scheme, r_host, r_path, _, _ = rule_url
    return _url_pattern_excludes(r_scheme, r_host, r_path, effect_target)


def _exact_pattern_excludes(rule_target, effect_target):
    """The v37.0 §513 algorithm, unchanged: can this pattern never equal
    `rule_target` as a flat string? Its known chunks must appear in it in
    order — the first anchored to the start, the last to the end, unless
    the pattern opens or closes with a hole — with a hole free to stand
    for any text, including none. Still what governs a rule target B2
    leaves on exact matching (not URL-shaped: a file path, a
    `queue:send`-style name, console text).
    """
    chunks = effect_target.split(HOLE)
    first, middle, last = chunks[0], chunks[1:-1], chunks[-1]
    if len(first) + len(last) > len(rule_target):
        return True
    if not rule_target.startswith(first) or not rule_target.endswith(last):
        return True
    pos, end = len(first), len(rule_target) - len(last)
    for chunk in middle:
        at = rule_target.find(chunk, pos, end)
        if at < 0:
            return True
        pos = at + len(chunk)
    return False


def _url_pattern_excludes(r_scheme, r_host, r_path, effect_target):
    """B2's re-proof of the v37.0 §513 guard for a URL-shaped rule target:
    can this computed target's KNOWN prefix — the literal text before its
    first hole, which is a true, certain prefix of whatever the hole goes
    on to produce (v37.0 §511) — prove no completion could ever be covered
    by the rule?

    Reasons from that one chunk only. It's the one piece of the pattern
    guaranteed to survive regardless of what any hole produces, so a proof
    built from it alone is sound: it can only prove exclusions that are
    real. A later chunk could in principle prove more, but skipping it
    only means staying uncertain more often — the conservative side of the
    guarantee ("when in doubt, don't exclude").

    Scheme and host are compared case-insensitively (B2's `_url_covers`);
    a hole overlapping the scheme, or extending past what the known chunk
    resolves of the host, leaves that piece unproven rather than assumed
    to fail — an unresolved host must still match on the substring that IS
    known: `https://api.{...}/` can't cover `https://x/`, because the
    host's known prefix `api.` is longer than, and a mismatch against,
    `x`, no matter what the hole fills in after it.
    """
    first = effect_target.split(HOLE, 1)[0]
    sep = first.find("://")
    if sep <= 0 or not _is_scheme(first[:sep]):
        return False
    if _ascii_lower(first[:sep]) != _ascii_lower(r_scheme):
        return True

    remainder = first[sep + 3:]
    term = len(remainder)
    for i, ch in enumerate(remainder):
        if ch in "/?#":
            term = i
            break
    if term == len(remainder):
        # The host itself isn't fully known here -- only a prefix of it
        # is, from this chunk. Whatever it resolves to will still start
        # with this prefix, so a rule host that does NOT start with it
        # can never be that host.
        return not _ascii_lower(r_host).startswith(_ascii_lower(remainder))

    e_host, rest = remainder[:term], remainder[term:]
    if _ascii_lower(e_host) != _ascii_lower(r_host):
        return True

    if rest[:1] in ("?", "#"):
        # The path is fully known here, from certain text -- and empty.
        return r_path not in ("", "/")

    known_path = rest
    if r_path in ("", "/"):
        return False
    lr = len(r_path)
    if len(known_path) < lr:
        return known_path != r_path[:len(known_path)]
    if known_path[:lr] != r_path:
        return True
    if len(known_path) == lr:
        return False
    return known_path[lr] != "/"


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


def _check_target_is_an_address(rule):
    """B2: a rule target names an address, not a request.

    The matcher ignores an EFFECT's own query string and fragment (B2 §3)
    — but a query or fragment written into the RULE's own target is an
    authoring mistake, not something to silently drop, so a URL-shaped
    target carrying one is refused before any matching runs. Checked for
    every declared rule, forbid or permit, superseded or not.
    """
    if rule.target is None:
        return
    parsed = _parse_url_target(rule.target)
    if parsed is None:
        return
    _, _, _, query, fragment = parsed
    if query is None and fragment is None:
        return
    raise RuleConflict(
        f"rule [{rule.name}] (line {rule.line}): target "
        f"\"{escape_string_literal(rule.target)}\" has a query string or "
        f"fragment — a rule target names an address, and only an "
        f"effect's own query and fragment are ever ignored, never the "
        f"rule's\n"
        f"  drop everything from the \"?\" or \"#\" onward")


def _resolve_active(rules):
    """Rules still in force after `supersedes` is applied.

    Two different things share the `supersedes` clause, told apart by
    whether the two rules share an assertion:

    - Same assertion (forbid supersedes forbid, or permit supersedes
      permit) is version replacement (v2.0 §31): the superseded rule is
      dropped entirely, before matching or conflict detection ever sees
      it — an edit is an event, not a silent substitution.
    - Opposite assertion (permit supersedes forbid) is the exception
      mechanism (§3): the forbid rule is NOT dropped — it still applies
      to every effect the permit doesn't cover — so it stays active, and
      per-effect clearing happens later in `check()`.

    Either way, naming an unknown rule, or a rule that supersedes itself,
    is a compile error: an external registry was refused, so the rule set
    itself is the only source of truth, and a dangling reference in it is
    an authoring mistake, not something to silently ignore. A fingerprint
    on the clause (v2.0 §29) is required — not merely checked when present
    (B3, Track 0 #3): the parser cannot know the other rule's fingerprint,
    so a `supersedes` clause naming no fingerprint at all is refused here,
    where the named rule is actually in hand to compute one from. Whether
    present or freshly required, the named rule having changed since the
    override was written against it is exactly as much a problem whether
    the relation is a version bump or an exception.

    `contradicts` (B3, Track 0 #5) is resolved in the same pass, with the
    same error class: naming an unknown rule, naming itself, or the same
    pair being declared from both sides. Checked against `by_name` — every
    named rule, whether or not it later gets dropped below — since these
    are facts about the clause as written, not about which rules survive
    supersedes.
    """
    by_name = {}
    for r in rules:
        if r.name in by_name:
            other = by_name[r.name]
            raise RuleConflict(
                f"two rules are both named [{r.name}] (line {other.line} "
                f"and line {r.line}) — a rule name must be unique\n"
                f"  rename one of them")
        by_name[r.name] = r

    dropped = set()
    for r in rules:
        if r.supersedes is None:
            continue
        if r.supersedes == r.name:
            raise RuleConflict(
                f"rule [{r.name}] (line {r.line}) supersedes itself\n"
                f"  supersedes should name an earlier, different rule")
        if r.supersedes not in by_name:
            raise RuleConflict(
                f"rule [{r.name}] (line {r.line}) supersedes "
                f"[{r.supersedes}], which is not a rule in this file\n"
                f"  check the name, or remove the supersedes clause")

        target_rule = by_name[r.supersedes]
        actual = fingerprint(target_rule)
        if r.supersedes_fingerprint is None:
            raise RuleConflict(
                f"rule [{r.name}] (line {r.line}) supersedes "
                f"[{r.supersedes}] (line {target_rule.line}) without its "
                f"fingerprint\n"
                f"  write supersedes [{r.supersedes}] @{actual}")
        if actual != r.supersedes_fingerprint:
            raise RuleConflict(
                f"rule [{r.name}] (line {r.line}) supersedes "
                f"[{r.supersedes}] (line {target_rule.line}) as of "
                f"@{r.supersedes_fingerprint}, but [{r.supersedes}] "
                f"is now @{actual} — it changed after [{r.name}] was "
                f"written to override it\n"
                f"  confirm the override still means what it meant, "
                f"then update the fingerprint to @{actual}")

        if target_rule.assertion == r.assertion:
            dropped.add(r.supersedes)

    contradicted_pairs = {}
    for r in rules:
        if r.contradicts is None:
            continue
        if r.contradicts == r.name:
            raise RuleConflict(
                f"rule [{r.name}] (line {r.line}) contradicts itself\n"
                f"  contradicts should name a different rule")
        if r.contradicts not in by_name:
            raise RuleConflict(
                f"rule [{r.name}] (line {r.line}) contradicts "
                f"[{r.contradicts}], which is not a rule in this file\n"
                f"  check the name, or remove the contradicts clause")

        pair = frozenset((r.name, r.contradicts))
        if pair in contradicted_pairs:
            first = contradicted_pairs[pair]
            raise RuleConflict(
                f"rule [{r.name}] (line {r.line}) contradicts "
                f"[{r.contradicts}], but [{first.name}] (line "
                f"{first.line}) already contradicts [{first.contradicts}] "
                f"— the pair only needs declaring once\n"
                f"  remove the contradicts clause from one of them")
        contradicted_pairs[pair] = r

    return [r for r in rules if r.name not in dropped]


def _check_permits_are_related(active):
    """A permit only has force against a prohibition it excepts (§3).

    A `may` rule grants nothing on its own — every effect is permitted by
    default, since Planes is a general-purpose language, not a sandbox.
    A permit that neither supersedes nor narrows any active forbid rule
    of its kind, nor is even equally specific to one, is an authoring
    error: silently ignoring it would report a program clean against a
    rule the author believed was doing something — the same failure
    `RuleNotSupported` exists to prevent for named subjects.

    Equally-specific (same covered set — B2's `_same_scope`, subsuming the
    pre-B2 same-target case) counts as related here, even though `narrows`
    itself says no — that pair is not unrelated, it is a conflict, and
    `_check_conflicts` gives the precise diagnostic for it. Excluding it
    here would let this check's coarser "excepts no forbid rule" message
    fire first and hide the more accurate one.
    """
    forbids = [r for r in active if r.assertion == "forbid"]
    for p in active:
        if p.assertion != "permit":
            continue
        related = any(
            f.kind == p.kind and
            (p.supersedes == f.name or narrows(p, f)
             or _same_scope(p.target, f.target))
            for f in forbids)
        if not related:
            raise RuleConflict(
                f"rule [{p.name}] (line {p.line}) permits '{p.kind}' but "
                f"excepts no forbid rule — a permit only has force "
                f"against a prohibition it supersedes or narrows\n"
                f"  add 'supersedes [name-of-the-forbid-rule]' to "
                f"[{p.name}], or give it a target that narrows one of "
                f"the forbid rules over '{p.kind}'")


def _check_conflicts(active):
    """Equal-specificity conflicts among the active rules (v2.0 §32; B2's
    `_same_scope` in place of `==` on the target).

    Two distinct rules of the same kind and the same covered set
    (including both unrestricted, or two spellings of the same address
    family — B2, e.g. `"https://x"` and `"https://x/"`), with neither
    narrowing nor explicitly superseding the other, are equally specific
    — nothing in the rule set says which one is authoritative:

    - Same assertion: the original ambiguity — two rules that agree, with
      no way to tell which is the intended, current one.
    - Opposite assertion: v2.0 §32's "two rules demand opposite things" —
      one forbids exactly what the other permits, and nothing says which
      wins.

    Related rules are not conflicts. `narrows` alone resolves the common
    nesting case (v2.0 §30 — a rule strictly more specific than another
    need not also declare `supersedes`; B2 extends this to a rule whose
    covered address set is strictly inside another's, e.g. a `/public`
    permit under a host-wide forbid); an explicit `supersedes` resolves
    an equal-specificity pair even when neither narrows the other, which
    is the only way two rules of the same scope and kind can coexist.

    Two URL-shaped targets on the same scheme and host can never overlap
    without one covering the other or the two being the same scope — a
    "/" boundary prefix relation is laminar, never partial — so B2 needs
    no additional overlap-without-narrowing case here beyond widening
    what "equally specific" means.
    """
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.kind != b.kind or not _same_scope(a.target, b.target):
                continue
            if narrows(a, b) or narrows(b, a):
                continue
            if a.supersedes == b.name or b.supersedes == a.name:
                continue

            where = f"'{a.kind}'" + (
                f' to "{escape_string_literal(a.target)}"' if a.target else "")
            if a.assertion != b.assertion:
                forbid, permit = (
                    (a, b) if a.assertion == "forbid" else (b, a))
                raise RuleConflict(
                    f"rule [{forbid.name}] (line {forbid.line}) and rule "
                    f"[{permit.name}] (line {permit.line}) demand "
                    f"opposite things over {where} — one forbids it, the "
                    f"other permits it, and neither narrows nor "
                    f"supersedes the other\n"
                    f"  add 'supersedes [{forbid.name}]' to "
                    f"[{permit.name}] to make the exception explicit, or "
                    f"give one of them a target the other lacks")
            raise RuleConflict(
                f"rule [{a.name}] (line {a.line}) and rule [{b.name}] "
                f"(line {b.line}) are equally specific over {where} — "
                f"neither narrows nor supersedes the other\n"
                f"  add 'supersedes [{a.name}]' to [{b.name}] (or the "
                f"reverse), or give one of them a target the other lacks")


def _rule_applies(rule, surface, declaring_file):
    """Does this rule's condition match at least one effect in the
    surface (B3, Track 0 #5)? A rule *applies* when it matches, whether
    as a forbid rule that would be violated or cleared, or as a permit
    rule that matched an effect; a rule matching nothing (vacuous) does
    not apply.

    For a forbid rule this is the same widen-on-uncertainty rule the
    vacuous check uses: an effect whose target is computed and not ruled
    out still counts, because widening a prohibition is sound (v2.0 §34).
    For a permit rule, the same uncertainty must NOT count — the
    conservatism flips at the permit boundary (v2.0 §34b): an uncertain
    match might not be the effect the permit actually names, so reporting
    the permit as "applying" on it would be unsound the same way clearing
    a violation on it would be.

    Returns (applies, first_matching_effect_or_None) — the first effect by
    `surface.declared`'s existing ordering, for a caller that needs one to
    name in a message.
    """
    for effect in surface.declared:
        if effect.kind != rule.kind:
            continue
        matched, uncertain = _target_matches(rule, effect)
        if not matched:
            continue
        if rule.assertion == "permit" and uncertain:
            continue
        if not _subject_matches(rule, effect, surface, declaring_file):
            continue
        return True, effect
    return False, None


def _check_contradictions(active, surface, declaring_file):
    """Contradiction violations (B3, Track 0 #5): every declared
    `contradicts` pair where both rules apply to this surface.

    Iterates `active` in its existing order, so this is deterministic and
    identical across hosts given the same source. `_resolve_active`
    already refused declaring the same pair from both sides, so at most
    one of the two rules carries the `contradicts` clause and no pair is
    ever reported twice. A pair naming a rule `_resolve_active` dropped
    (superseded away, same-assertion version replacement) can never fire:
    a dropped rule is not in `active` and so cannot apply.
    """
    by_name = {r.name: r for r in active}
    results = []
    for r in active:
        if r.contradicts is None:
            continue
        other = by_name.get(r.contradicts)
        if other is None:
            continue
        applies, effect = _rule_applies(r, surface, declaring_file)
        if not applies:
            continue
        other_applies, other_effect = _rule_applies(
            other, surface, declaring_file)
        if not other_applies:
            continue
        results.append(Violation(r, effect, contradicts_rule=other,
                                 contradicts_effect=other_effect))
    return results


def check(rules, surface, declaring_file=None):
    """Every violation of every rule, given a computed effect surface.

    A `forbid` rule matching an effect is a violation unless a related
    `permit` rule — one that supersedes or narrows it — also matches the
    same effect (§3, v2.0 §30–§32). A cleared match is still returned, so
    a reader can see the exception working, but its `is_violation` is
    False; a caller's exit-code decision must be based on
    `any(v.is_violation for v in result)`, never on whether the result is
    non-empty.

    `declaring_file` scopes named-subject resolution (P-Q18): defaults to
    None, which matches every node's file when the surface came from
    `analyse(src)` with no path (every node's file is None too) — so every
    existing single-file caller keeps working unchanged. `shapes_cli.py`
    passes the entry file's path. A caller that passes a real
    `declaring_file` against a surface built with no `file=` gets a silent
    total mismatch — every node's file is None, so nothing ever resolves
    in the given file. Match the two deliberately, as `shapes_cli.py` does.

    A named-subject `forbid` rule whose subject resolves (P-Q18) but never
    matches a single effect is reported as a fourth, vacuous `Violation`
    shape rather than silently as "no violations" (P-Q19) — a rule that
    never did any work must not look like a rule that passed.

    A fifth shape, the contradiction (B3, Track 0 #5), is appended after
    every forbid rule's own violations: for each declared `contradicts`
    pair among the active rules, one `Violation` when both rules apply to
    this surface. `is_violation` is True for it, same as a real violation.

    Reads only the public queries on Surface. If this function needs to
    reach into the analyser's internals, that is a finding about
    inception checkpoint §8 — report it rather than working around it.

    Cost note: `_resolve_subject` and the per-effect `_subject_matches`
    calls below both walk `surface.origins_of()` per named-subject rule —
    O(rules × effects × nodes), duplicates undeduplicated by design.
    Irrelevant at the node counts P-Q10 measured; would first matter on a
    program with many named-subject rules over a very large effect surface.

    Returns a `RuleResults` (a `list` subclass) rather than a bare list:
    `resolved_subjects` records every subject that survived
    `_resolve_subject`, in order, for a caller to read back rather than
    re-derive (P-Q20).
    """
    for rule in rules:
        _check_target_is_an_address(rule)

    resolved_subjects = []
    for rule in rules:
        if rule.subject != "anything":
            _resolve_subject(rule, surface, declaring_file)
            resolved_subjects.append(rule.subject)

    active = _resolve_active(rules)
    _check_permits_are_related(active)
    _check_conflicts(active)

    forbids = [r for r in active if r.assertion == "forbid"]
    permits = [r for r in active if r.assertion == "permit"]

    results = []
    for rule in forbids:
        # Three counters distinguish §2's three vacuous situations without
        # a second pass over surface.declared: how many effects share this
        # rule's kind at all, and how many of those derive from the
        # subject (regardless of target). matched_any tracks whether any
        # effect passed both gates — the pre-existing violation condition,
        # unchanged.
        n_kind = 0
        n_kind_subject = 0
        matched_any = False
        for effect in surface.declared:
            if effect.kind != rule.kind:
                continue
            n_kind += 1
            matched, uncertain = _target_matches(rule, effect)
            subject_ok = _subject_matches(rule, effect, surface, declaring_file)
            if subject_ok:
                n_kind_subject += 1
            if not matched or not subject_ok:
                continue
            matched_any = True

            clearer = None
            for p in permits:
                if not (p.supersedes == rule.name or narrows(p, rule)):
                    continue
                p_matched, p_uncertain = _target_matches(p, effect)
                # A computed permit target clears nothing: widening is
                # safe for a prohibition (§34), but widening an EXCEPTION
                # is not — an uncertain match might not be the effect the
                # permit actually names.
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

        if rule.subject != "anything" and not matched_any:
            vacuous = Violation(rule, None, vacuous=True)
            if n_kind == 0:
                vacuous.vacuous_situation = 1
            elif n_kind_subject == 0:
                vacuous.vacuous_situation = 2
            else:
                vacuous.vacuous_situation = 3
            results.append(vacuous)

    results.extend(_check_contradictions(active, surface, declaring_file))

    return RuleResults(results, resolved_subjects=resolved_subjects)
