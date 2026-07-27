#!/usr/bin/env python3
"""planes — run a .planes program.

  python3 planes.py program.planes
  python3 planes.py -e 'x = 5; y = 3; z = x + y; why z'
  python3 planes.py program.planes --effects   # print the effect surface
  python3 planes.py program.planes --why NAME  # print a full derivation tree
"""
import os
import sys

from host import PythonHost
from interp import Interpreter, PlanesError, origins, why_tree
from modules import ModuleError
from parser import PlanesSyntaxError


class CliHost(PythonHost):
    """The default host, with `show` silenced — because this CLI prints.

    `show` is a host capability: the interpreter records the line in
    `i.output` AND hands it to `host.show`, which is what makes a `show`
    reach stdout for an embedded caller. This CLI then printed `i.output`
    as well, so every `show` line appeared twice — including in
    `money.planes`, the example this README quotes.

    Printing `i.output` is the half that has to stay: a `why` statement
    inside a program body lands there too and is NOT a host effect, so
    dropping the loop would silence it. Silencing the echo instead keeps
    one emitter, keeps `show` and `why` interleaved in program order, and
    leaves `PythonHost` — the one an embedding caller gets — untouched.
    """

    def show(self, text):
        pass


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__.strip())
        return 2

    show_effects = "--effects" in args
    if show_effects:
        args.remove("--effects")

    why_name = None
    if "--why" in args:
        k = args.index("--why")
        why_name = args[k + 1]
        del args[k:k + 2]

    if args[0] == "-e":
        src = args[1].replace("; ", "\n").replace(";", "\n")
    else:
        path = args[0]
        if not os.path.exists(path):
            print(f"no such file: {path}", file=sys.stderr)
            return 1
        src = open(path).read()

    i = Interpreter(host=CliHost())
    try:
        if args[0] == "-e":
            lines = i.run(src)
        else:
            lines = i.run_file(args[0])
        for line in lines:
            print(line)
    except PlanesSyntaxError as e:
        print(f"syntax error — {e}", file=sys.stderr)
        return 1
    except ModuleError as e:
        print(f"module error — {e}", file=sys.stderr)
        return 1
    except PlanesError as e:
        print(f"error — {e}", file=sys.stderr)
        return 1

    if why_name:
        try:
            v = i.env.get(why_name)
        except PlanesError as e:
            print(f"error — {e}", file=sys.stderr)
            return 1
        print(f"\nwhy {why_name}:")
        print(why_tree(v))
        o = origins(v)
        if o:
            print("\nentered the program at:")
            for src_ in dict.fromkeys(o):
                print(f"  {src_}")

    if show_effects:
        print("\neffect surface:")
        if not i.effects:
            print("  (nothing — this run performed no effects; run "
                 "`shapes_cli.py <file>` for what the program can do on "
                 "any run)")
        for eff in i.effects:
            kind, target = eff[0], eff[1]
            print(f"  {kind:6} {target}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
