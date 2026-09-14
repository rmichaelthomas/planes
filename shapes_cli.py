#!/usr/bin/env python3
"""shapes — compute a Planes program's effect surface without running it.

  python3 shapes_cli.py program.planes              # the surface
  python3 shapes_cli.py program.planes --functions  # per-function breakdown
  python3 shapes_cli.py program.planes --json       # machine-readable
  python3 shapes_cli.py program.planes --check      # module declarations
  python3 shapes_cli.py program.planes --no-follow   # this file only
  python3 shapes_cli.py program.planes --rules        # check its rules
  python3 shapes_cli.py program.planes --fingerprints # print rule fingerprints
  python3 shapes_cli.py program.planes --derivation-stats  # P-Q10 node/depth measurement
  python3 shapes_cli.py program.planes --render       # canonical source, with rule markers
  python3 shapes_cli.py --diff old.planes new.planes
  python3 shapes_cli.py --index demo/pkgs           # index a corpus
  python3 shapes_cli.py --search network demo/pkgs  # search by behaviour

The point of --json is that this is a fact an agent can act on before
installing anything. --diff exits 1 when a new boundary is crossed. --rules
exits 1 on a genuine violation, 2 when every genuine violation is absent but
a named-subject rule resolved and matched nothing (it checked nothing —
P-Q19), 0 otherwise; both drop into CI as a gate. `--json --rules` together
add a "rules" field to the JSON document (H1) — the same violations, in the
same order, that --rules alone prints as text, as structured fields plus the
rendered message string, so a --json consumer no longer has to run --rules
separately or parse its prose to see what it found. The exit code is
unchanged either way.
"""
import json
import os
import sys

from lexer import Rule
from modules import ModuleError
from parser import PlanesSyntaxError, parse
from render import render
from rules import RuleConflict, RuleNotSupported, fingerprint
from rules import check as check_rules
from shapes import analyse, analyse_file, diff

# Bumped when the meaning of a field changes. A consumer that does not
# recognise the version should refuse the document rather than guess.
#
# 2 (B1, Sprint B): `send` joined the effect vocabulary and `ask` narrowed
# to fetch-only (Track 0 #7-#11) -- the MEANING of an existing "ask" value
# changed (a value that was "an ask, could be a fetch or a send" is now
# certainly a fetch), which is exactly what this field exists to flag. See
# docs/surface-format-v2.md's "Changes from format 1".
FORMAT_VERSION = 2


def as_json(surface, path, rules=None):
    """The machine-readable surface.

    `effects` reports the DECLARED surface — everything this file offers,
    including what its functions do when called. Reporting only top-level
    effects would say a library does nothing, which is the failure this
    whole system exists to prevent, and it said exactly that until this was
    fixed: `sneaky.planes` emitted `"effects": []` beside
    `"boundaries": ["network"]`.

    `rules`, when given, is `rules_json(found, results)` (H1) — appended as
    an additional "rules" field, never touching any field above it. Every
    existing two-argument caller keeps getting the exact document it always
    did; `rules=None` (the default) omits the key entirely rather than
    writing it as `null`, so a consumer that never asked for --rules sees no
    trace that the field exists.
    """
    doc = {
        "format": FORMAT_VERSION,
        "program": os.path.basename(path),
        "kind": ("library" if surface.is_library()
                 else "pure" if surface.is_pure() else "program"),
        "pure": surface.is_pure(),
        "complete": not surface.has_unknowns() and not surface.unresolved,
        "boundaries": surface.boundaries(),
        "kinds": surface.kinds(),
        "effects": [
            {
                "kind": e.kind,
                "boundary": e.boundary,
                "target": e.target,
                "computed": e.computed,
                "declared": e.claimed,
            }
            for e in surface.declared
        ],
        "runs_on_load": [
            {"kind": e.kind, "boundary": e.boundary, "target": e.target}
            for e in surface.effects
        ],
        "modules_declared": sorted(surface.modules),
        "modules_unused": surface.declared_but_unused(),
        "effects_undeclared": [
            {"kind": e.kind, "target": e.target}
            for e in surface.used_but_undeclared()
        ],
        "unresolved_calls": sorted(set(surface.unresolved)),
        # The third question, in the machine-readable report too: does this
        # program produce approximate values, and by what route.
        "approximate": [list(p) for p in surface.approximate],
    }
    if rules is not None:
        doc["rules"] = rules
    return doc


def rules_json(found, results):
    """--rules's results, structured for --json (H1).

    `checked` and `resolved_subjects` are the same readback the text
    summary line reports (P-Q20: read from `results.resolved_subjects`,
    never re-derived by assuming every named subject in `found` survived).
    `violations` is every `Violation.as_json()`, in the exact order
    `check()` returned them — the same order text mode prints them in, so a
    --json consumer sees an identical sequence to a --rules reader.
    """
    return {
        "checked": len(found),
        "resolved_subjects": list(results.resolved_subjects),
        "violations": [v.as_json() for v in results],
    }


def derivation_stats(surface):
    """Max/mean node count per effect, and max graph depth — P-Q10.

    Measures whether derivation survives arithmetic without Jif-style label
    creep. The creep bounds already in shapes.py (is_recursive, the depth
    caps in const_call/specialise, assigned_in's join widening) are what
    keep this bounded; this only measures the result, it does not enforce
    anything new.
    """
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


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__.strip())
        return 2

    if args[0] == "--index":
        import glob
        paths = []
        for pat in args[1:] or ["*.planes"]:
            paths.extend(sorted(glob.glob(os.path.join(pat, "*.planes")
                                          if os.path.isdir(pat) else pat)))
        if not paths:
            print("no .planes files found", file=sys.stderr)
            return 1
        rows = []
        for p in paths:
            try:
                rows.append((p, analyse_file(p)))
            except PlanesSyntaxError as e:
                print(f"{p}: syntax error — {e}", file=sys.stderr)
        print(f"{'package':16} {'kind':9} boundaries")
        print("-" * 52)
        for p, s in rows:
            name = os.path.basename(p).replace(".planes", "")
            kind = ("library" if s.is_library()
                    else "pure" if s.is_pure() else "program")
            print(f"{name:16} {kind:9} {', '.join(s.boundaries()) or '-'}")
        return 0

    if args[0] == "--search":
        import glob
        if len(args) < 2:
            print("--search needs a boundary "
                  "(network, file, console)", file=sys.stderr)
            return 2
        boundary = args[1]
        paths = []
        for pat in args[2:] or ["*.planes"]:
            paths.extend(sorted(glob.glob(os.path.join(pat, "*.planes")
                                          if os.path.isdir(pat) else pat)))
        hits = 0
        skipped = 0
        for p in paths:
            try:
                s = analyse_file(p)
            except PlanesSyntaxError as e:
                # Reported, not silently dropped (matches --index's
                # handling of the same failure mode): "nothing touches
                # X" below must not claim more than what was actually
                # searched — a skipped file's real answer is unknown, not
                # "no" (unearned-assertion sweep finding).
                print(f"{p}: syntax error — {e}", file=sys.stderr)
                skipped += 1
                continue
            if s.touches(boundary):
                hits += 1
                name = os.path.basename(p).replace(".planes", "")
                for eff in s.at(boundary):
                    print(f"{name:16} {eff}")
        if not hits:
            note = (f" ({skipped} file(s) could not be parsed and were "
                    f"not searched)" if skipped else "")
            print(f"nothing touches {boundary} among the files searched{note}")
        return 0

    if args[0] == "--diff":
        if len(args) < 3:
            print("--diff needs two files", file=sys.stderr)
            return 2
        before, after = analyse_file(args[1]), analyse_file(args[2])
        d = diff(before, after)
        print(f"{args[1]} -> {args[2]}")
        print(d.render())
        # Fail the build on a new boundary OR a new destination.
        return 1 if d.is_significant() else 0

    path = args[0]
    if not os.path.exists(path):
        print(f"no such file: {path}", file=sys.stderr)
        return 1

    follow = "--no-follow" not in args
    try:
        surface = analyse_file(path, follow=follow)
    except PlanesSyntaxError as e:
        print(f"syntax error — {e}", file=sys.stderr)
        return 1
    except ModuleError as e:
        print(f"module error — {e}", file=sys.stderr)
        return 1

    if "--derivation-stats" in args:
        stats = derivation_stats(surface)
        print(f"derivation stats for {os.path.basename(path)}")
        print(f"  effects with a derivation: {stats['effects_with_derivation']}")
        print(f"  max nodes per effect:      {stats['max_nodes']}")
        print(f"  mean nodes per effect:     {stats['mean_nodes']}")
        print(f"  max graph depth:           {stats['max_depth']}")
        return 0

    if "--render" in args:
        # Its own parse and surface, single-file and unfollowed, so a
        # rule's subject resolves the same way render()'s internal
        # `check(rules, surface, declaring_file=None)` expects: every
        # node's file is None on both sides (rules.py's own documented
        # default-matching rule).
        try:
            src = open(path).read()
            prog = parse(src)
        except PlanesSyntaxError as e:
            print(f"syntax error — {e}", file=sys.stderr)
            return 1
        found = [s for s in prog if isinstance(s, Rule)]
        try:
            text = (render(prog, rules=found, surface=analyse(src))
                    if found else render(prog))
        except (RuleNotSupported, RuleConflict) as e:
            print(f"rule check error — {e}", file=sys.stderr)
            return 1
        print(text, end="")
        return 0

    if "--rules" in args or "--fingerprints" in args:
        # Rules are collected from this file's own top-level statements,
        # the same file the surface above was computed for — parsing it a
        # second time is simplest and keeps this checker decoupled from
        # the multi-file graph in modules.py.
        try:
            prog = parse(open(path).read())
        except PlanesSyntaxError as e:
            print(f"syntax error — {e}", file=sys.stderr)
            return 1
        found = [s for s in prog if isinstance(s, Rule)]

        if "--fingerprints" in args:
            if not found:
                print(f"no rules found in {os.path.basename(path)}")
                return 0
            for r in found:
                print(f"[{r.name}] @{fingerprint(r)}")
            return 0

        # H1: with --json also given, the result is the JSON document with
        # a "rules" field, not the text below — an empty `found` still goes
        # through check_rules() (which reports 0 checked, no violations)
        # rather than the "no rules found" text short-circuit, since a
        # --json consumer wants a document, not a sentence.
        as_json_output = "--json" in args
        if not found and not as_json_output:
            print(f"no rules found in {os.path.basename(path)}")
            return 0

        try:
            results = check_rules(found, surface,
                                  declaring_file=os.path.abspath(path))
        except (RuleNotSupported, RuleConflict) as e:
            print(f"rule check error — {e}", file=sys.stderr)
            return 1

        if as_json_output:
            print(json.dumps(
                as_json(surface, path, rules=rules_json(found, results)),
                indent=2))
        elif not results:
            word = "rule" if len(found) == 1 else "rules"
            summary = f"{len(found)} {word} checked"
            # Read back from check()'s own record of what it resolved
            # (RuleResults.resolved_subjects), not re-derived from `found`
            # by assuming _resolve_subject would have raised otherwise
            # (P-Q20) — the claim comes from what check() did, not from
            # this module's guess about it.
            resolved = results.resolved_subjects
            if resolved:
                n = len(resolved)
                subj_word = "subject" if n == 1 else "subjects"
                summary += f" ({n} named {subj_word} resolved)"
            print(f"{summary}, no violations")
        else:
            for v in results:
                print(v.render())
                print()

        # A cleared prohibition, or a vacuous named-subject rule, is
        # reported (so the reader sees it) but is not a genuine violation —
        # only a genuine violation exits 1. A vacuous rule (P-Q19) still
        # exits non-zero: a rule that checked nothing should fail its CI
        # gate, distinctly from a real violation, so a caller can tell
        # "this broke" from "this rule no longer applies to anything." Same
        # exit-code logic whether the result above printed as JSON or text.
        if any(v.is_violation for v in results):
            return 1
        if any(v.vacuous for v in results):
            return 2
        return 0

    if "--json" in args:
        print(json.dumps(as_json(surface, path), indent=2))
        return 0

    print(f"effect surface of {os.path.basename(path)}")
    print()
    print(surface.render())

    if "--functions" in args:
        print()
        print("per function:")
        for name in sorted(surface.functions):
            es = surface.functions[name]
            if es:
                for eff in es:
                    print(f"  {name:16} {eff.boundary:8} {eff}")
            else:
                print(f"  {name:16} pure")

    if "--check" in args:
        print()
        unused = surface.declared_but_unused()
        undeclared = surface.used_but_undeclared()
        if not unused and not undeclared:
            print("module declarations match the effect surface")
        for m in unused:
            print(f"  declared but unused: use {m}")
        for eff in undeclared:
            mod = "http" if eff.boundary == "network" else eff.boundary
            print(f"  performs {eff.kind} without `use {mod}`")
        return 1 if undeclared else 0

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
