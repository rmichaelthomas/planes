#!/usr/bin/env python3
"""shapes — compute a Planes program's effect surface without running it.

  python3 shapes_cli.py program.planes              # the surface
  python3 shapes_cli.py program.planes --functions  # per-function breakdown
  python3 shapes_cli.py program.planes --json       # machine-readable
  python3 shapes_cli.py program.planes --check      # module declarations
  python3 shapes_cli.py program.planes --no-follow   # this file only
  python3 shapes_cli.py program.planes --rules        # check its rules
  python3 shapes_cli.py program.planes --fingerprints # print rule fingerprints
  python3 shapes_cli.py --diff old.planes new.planes
  python3 shapes_cli.py --index demo/pkgs           # index a corpus
  python3 shapes_cli.py --search network demo/pkgs  # search by behaviour

The point of --json is that this is a fact an agent can act on before
installing anything. --diff exits 1 when a new boundary is crossed, and
--rules exits 1 on any violation, so both drop into CI as a gate.
"""
import json
import sys
import os

from shapes import analyse_file, diff
from parser import parse, PlanesSyntaxError
from lexer import Rule
from modules import ModuleError
from rules import check as check_rules, RuleNotSupported, RuleConflict, fingerprint


# Bumped when the meaning of a field changes. A consumer that does not
# recognise the version should refuse the document rather than guess.
FORMAT_VERSION = 1


def as_json(surface, path):
    """The machine-readable surface.

    `effects` reports the DECLARED surface — everything this file offers,
    including what its functions do when called. Reporting only top-level
    effects would say a library does nothing, which is the failure this
    whole system exists to prevent, and it said exactly that until this was
    fixed: `sneaky.planes` emitted `"effects": []` beside
    `"boundaries": ["network"]`.
    """
    return {
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
        for p in paths:
            try:
                s = analyse_file(p)
            except PlanesSyntaxError:
                continue
            if s.touches(boundary):
                hits += 1
                name = os.path.basename(p).replace(".planes", "")
                for e in s.at(boundary):
                    print(f"{name:16} {e}")
        if not hits:
            print(f"nothing touches {boundary}")
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
        if not found:
            print(f"no rules in {os.path.basename(path)}")
            return 0

        if "--fingerprints" in args:
            for r in found:
                print(f"[{r.name}] @{fingerprint(r)}")
            return 0

        try:
            results = check_rules(found, surface)
        except (RuleNotSupported, RuleConflict) as e:
            print(f"rule check error — {e}", file=sys.stderr)
            return 1
        if not results:
            word = "rule" if len(found) == 1 else "rules"
            print(f"{len(found)} {word} checked, no violations")
            return 0
        for v in results:
            print(v.render())
            print()
        # A cleared prohibition is returned (so the exception is visible)
        # but must not fail the build — only a genuine violation does.
        return 1 if any(v.is_violation for v in results) else 0

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
                for e in es:
                    print(f"  {name:16} {e.boundary:8} {e}")
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
        for e in undeclared:
            mod = "http" if e.boundary == "network" else e.boundary
            print(f"  performs {e.kind} without `use {mod}`")
        return 1 if undeclared else 0

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
