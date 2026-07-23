"""Rule-plane checker — permits, exception resolution, fingerprinting.

Tests inception checkpoint §8's claim that a rule is the same question
Shapes and Why already answer, asked at compile time. shapes.py computes a
program's effect surface; this module only consumes it, through the public
`Surface` queries (`at`, `targets`, `touches`, `declared`, `kinds`,
`boundaries`). If this file ever needs to reach inside `Analyser`, `Consts`,
or `Effect` construction, that is a finding about §8 — report it, don't
route around it. `hashlib`, for fingerprinting (§5), is the one import this
file has ever needed — stdlib, not a `shapes` coupling.

Matching is static and structural (unbound v2.0 §34): no execution. A rule
is never triggered; it is only ever checked against a surface that was
already computed without running anything.
"""
import hashlib


class RuleNotSupported(Exception):
    """A rule this slice's checker cannot evaluate.

    Binding a named subject (anything other than the `anything` wildcard)
    to the effects it actually produced requires a static derivation
    graph, which this slice does not build — that machinery is the other,
    unsupported half of §8's claim. Reporting such a rule as clean would be
    the exact failure the two guarantees exist to prevent: a rule that
    never ran, presented as a rule that passed.
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
    - Two distinct rules are equally specific — same kind, same target —
      and neither narrows nor supersedes the other. If they share an
      assertion, that is the pre-existing ambiguity: nothing says which
      is authoritative. If they don't, that is v2.0 §32's "two rules
      demand opposite things" — one forbids exactly what the other
      permits, expressible for the first time now that a permitting
      assertion exists.
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
        text += f' to "{rule.target}"'
    return text


class Violation:
    """One forbid rule matched against one effect.

    Three shapes, told apart by `cleared_by` / `narrowed_by`:

    - A real violation: neither set.
    - A violation narrowed by a more specific sibling forbid rule that
      also matched: `narrowed_by` names it. Still a real violation — two
      forbid rules matching the same effect are not in conflict, and both
      are reported, but as related rather than as independent failures.
    - A prohibition a permit cleared: `cleared_by` names the permit.
      `is_violation` is False, and this must not count toward a caller's
      exit code — but it is still returned and rendered, so the exception
      is visible where a reader actually meets it (v2.0 §31's
      generated-marker reasoning, applied to output).
    """

    def __init__(self, rule, effect, uncertain=False, cleared_by=None,
                narrowed_by=None):
        self.rule = rule
        self.effect = effect
        # True when the effect's target is computed=True: the analyser
        # could not pin it down, so this is a possible match, not a
        # confirmed one. Conservative at the boundary (v2.0 §34) — widening
        # is sound, assuming a computed target is safe is not.
        self.uncertain = uncertain
        self.cleared_by = cleared_by
        self.narrowed_by = narrowed_by or []

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
        return "\n".join(lines)

    def __str__(self):
        return self.render()


def narrows(b, a):
    """Does rule `b` cover a strict subset of what rule `a` ranges over?

    (v2.0 §30.) A pure scope comparison — kind and target only, never
    assertion — so the same function resolves specificity between two
    forbids, two permits, or a permit and the forbid it excepts.
    Comparable only within the same kind. A rule naming a target narrows
    one that does not: `a` ranges over every target of a kind, `b` over
    one, so `b`'s scope is a subset of `a`'s. Two rules with the same
    target (including both unrestricted) are equally specific — neither
    narrows the other, even if their names differ.
    """
    if a.name == b.name:
        return False
    if a.kind != b.kind:
        return False
    return a.target is None and b.target is not None


def _target_matches(rule, effect):
    """Does this rule's target reach this effect?

    Returns (matched, uncertain). No target on the rule means every
    target of the kind — always a certain match. Otherwise: an exact
    string match is certain; an effect whose own target is computed=True
    (the analyser could not pin it down) is a possible match, not a
    confirmed one — conservative at the boundary (v2.0 §34): widening is
    sound, assuming a computed target is safe is not.
    """
    if rule.target is None:
        return True, False
    if effect.computed:
        return True, True
    return effect.target == rule.target, False


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
    on the clause (v2.0 §29) is checked here too, for either kind of
    supersedes: the named rule having changed since the override was
    written against it is exactly as much a problem whether the relation
    is a version bump or an exception.
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
        if r.supersedes_fingerprint is not None:
            actual = fingerprint(target_rule)
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

    Equally-specific (same target) counts as related here, even though
    `narrows` itself says no — that pair is not unrelated, it is a
    conflict, and `_check_conflicts` gives the precise diagnostic for it.
    Excluding it here would let this check's coarser "excepts no forbid
    rule" message fire first and hide the more accurate one.
    """
    forbids = [r for r in active if r.assertion == "forbid"]
    for p in active:
        if p.assertion != "permit":
            continue
        related = any(
            f.kind == p.kind and
            (p.supersedes == f.name or narrows(p, f) or p.target == f.target)
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
    """Equal-specificity conflicts among the active rules (v2.0 §32).

    Two distinct rules of the same kind and the same target (including
    both unrestricted), with neither narrowing nor explicitly superseding
    the other, are equally specific — nothing in the rule set says which
    one is authoritative:

    - Same assertion: the original ambiguity — two rules that agree, with
      no way to tell which is the intended, current one.
    - Opposite assertion: v2.0 §32's "two rules demand opposite things" —
      one forbids exactly what the other permits, and nothing says which
      wins.

    Related rules are not conflicts. `narrows` alone resolves the common
    nesting case (v2.0 §30 — a rule strictly more specific than another
    need not also declare `supersedes`); an explicit `supersedes`
    resolves an equal-specificity pair even when neither narrows the
    other, which is the only way two rules of identical target and kind
    can coexist.
    """
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.kind != b.kind or a.target != b.target:
                continue
            if narrows(a, b) or narrows(b, a):
                continue
            if a.supersedes == b.name or b.supersedes == a.name:
                continue

            where = f"'{a.kind}'" + (f' to "{a.target}"' if a.target else "")
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


def check(rules, surface):
    """Every violation of every rule, given a computed effect surface.

    A `forbid` rule matching an effect is a violation unless a related
    `permit` rule — one that supersedes or narrows it — also matches the
    same effect (§3, v2.0 §30–§32). A cleared match is still returned, so
    a reader can see the exception working, but its `is_violation` is
    False; a caller's exit-code decision must be based on
    `any(v.is_violation for v in result)`, never on whether the result is
    non-empty.

    Reads only the public queries on Surface. If this function needs to
    reach into the analyser's internals, that is a finding about
    inception checkpoint §8 — report it rather than working around it.
    """
    for rule in rules:
        if rule.subject != "anything":
            raise RuleNotSupported(
                f"rule [{rule.name}] (line {rule.line}): a subject other "
                f"than 'anything' is not yet supported — binding "
                f"'{rule.subject}' to the effects it actually produces "
                f"needs a static derivation graph this slice does not "
                f"build\n"
                f"  write the rule against 'anything' instead, or wait "
                f"for the derivation-reaching half of the rule plane")

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

            clearer = None
            for p in permits:
                if not (p.supersedes == rule.name or narrows(p, rule)):
                    continue
                p_matched, p_uncertain = _target_matches(p, effect)
                # A computed permit target clears nothing: widening is
                # safe for a prohibition (§34), but widening an EXCEPTION
                # is not — an uncertain match might not be the effect the
                # permit actually names.
                if p_matched and not p_uncertain:
                    clearer = p
                    break

            if clearer is not None:
                results.append(Violation(rule, effect, uncertain=uncertain,
                                         cleared_by=clearer))
                continue

            narrowers = [
                other for other in forbids
                if other is not rule and narrows(other, rule)
                and _target_matches(other, effect)[0]
            ]
            results.append(Violation(rule, effect, uncertain=uncertain,
                                     narrowed_by=narrowers))

    return results
