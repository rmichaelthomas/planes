"""Rule-plane checker — effect-only slice.

Tests inception checkpoint §8's claim that a rule is the same question
Shapes and Why already answer, asked at compile time. shapes.py computes a
program's effect surface; this module only consumes it, through the public
`Surface` queries (`at`, `targets`, `touches`, `declared`, `kinds`,
`boundaries`). If this file ever needs to reach inside `Analyser`, `Consts`,
or `Effect` construction, that is a finding about §8 — report it, don't
route around it.

Matching is static and structural (unbound v2.0 §34): no execution. A rule
is never triggered; it is only ever checked against a surface that was
already computed without running anything.
"""


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

    Raised for two distinct authoring problems, both structural (checked
    before any effect is matched):

    - `supersedes` names a rule that does not exist, or a rule that
      supersedes itself.
    - Two distinct rules are equally specific — same kind, same target —
      and neither narrows nor supersedes the other, so there is no
      principled way to say which one is authoritative.

    v2.0 §32's own framing is "two rules that demand opposite things",
    which presumes a permitting assertion this slice's grammar does not
    have (§2 built `may not` only). What is implemented here is the
    narrower, well-defined case reachable from that grammar: equal
    specificity with no narrows/supersedes relation. See REPORT_RULES.md
    for why the fuller reading was not attempted.
    """
    pass


class Violation:
    """One rule broken by one effect in the computed surface."""

    def __init__(self, rule, effect, uncertain=False):
        self.rule = rule
        self.effect = effect
        # True when the effect's target is computed=True: the analyser
        # could not pin it down, so this is a possible match, not a
        # confirmed one. Conservative at the boundary (v2.0 §34) — widening
        # is sound, assuming a computed target is safe is not.
        self.uncertain = uncertain

    def render(self):
        lines = [f"[{self.rule.name}] violated at line {self.effect.site}."]
        lines.append(f"  {self.effect}")
        if self.uncertain:
            lines.append(
                "  target could not be pinned down statically — this "
                f"computed value may or may not be \"{self.rule.target}\"")
        lines.append(f"  rule declared at line {self.rule.line}")
        return "\n".join(lines)

    def __str__(self):
        return self.render()


def narrows(b, a):
    """Does rule `b` cover a strict subset of what rule `a` forbids?

    (v2.0 §30.) Comparable only within the same kind — specificity across
    kinds is not defined. A rule naming a target narrows one that does
    not: `a` forbids every target of a kind, `b` forbids one, so `b`'s
    forbidden set is a subset of `a`'s. Two rules with the same target
    (including both unrestricted) are equally specific — neither narrows
    the other, even if their names differ.
    """
    if a.name == b.name:
        return False
    if a.kind != b.kind:
        return False
    return a.target is None and b.target is not None


def _resolve_active(rules):
    """Rules still in force after `supersedes` is applied (v2.0 §31).

    A rule that names another in its `supersedes` clause replaces it; the
    superseded rule is dropped before matching or conflict detection ever
    sees it. Naming an unknown rule, or a rule superseding itself, is a
    compile error — an external registry was refused, so the only source
    of truth is the rule set itself, and a dangling reference in it is an
    authoring mistake, not something to silently ignore.
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

    superseded = set()
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
        superseded.add(r.supersedes)

    return [r for r in rules if r.name not in superseded]


def _check_conflicts(active):
    """Equal-specificity conflicts among the active rules (v2.0 §32).

    Two distinct rules of the same kind and the same target (including
    both unrestricted) are equally specific: neither is a refinement of
    the other, and nothing in the rule set says which one is
    authoritative. That does not compile.
    """
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.kind != b.kind or a.target != b.target:
                continue
            if narrows(a, b) or narrows(b, a):
                continue
            where = f"'{a.kind}'" + (f' to "{a.target}"' if a.target else "")
            raise RuleConflict(
                f"rule [{a.name}] (line {a.line}) and rule [{b.name}] "
                f"(line {b.line}) are equally specific over {where} — "
                f"neither narrows nor supersedes the other\n"
                f"  add 'supersedes [{a.name}]' to [{b.name}] (or the "
                f"reverse), or give one of them a target the other lacks")


def check(rules, surface):
    """Every violation of every rule, given a computed effect surface.

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
    _check_conflicts(active)

    violations = []
    for rule in active:
        for effect in surface.declared:
            if effect.kind != rule.kind:
                continue
            if rule.target is None:
                violations.append(Violation(rule, effect))
            elif effect.computed:
                violations.append(Violation(rule, effect, uncertain=True))
            elif effect.target == rule.target:
                violations.append(Violation(rule, effect))

    return violations
