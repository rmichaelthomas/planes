"""S6, Phase 4 — the standalone effect-surface CLI, checked against shapes_cli.py.

js/shapes_cli.mjs is a thin Node-only shell over the already-ported engine
(shapes.mjs / shapes_node.mjs): --index, --search, --diff, the last unported
surface that is neither runtime nor guarantee (A.5). No analysis logic lives in
the shell — every command reads only public Surface queries and diff.

Agreement: the same commands, same inputs, same output text and exit code as the
Python CLI. shapes_cli.py is the specification.
"""
import os
import shutil
import subprocess
import sys

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

COMMANDS = [
    ["--index", "demo/pkgs"],
    ["--index", "demo/pkgs/*.planes"],
    ["--index", "demo/rules"],
    ["--search", "network", "demo/pkgs"],
    ["--search", "file", "demo/pkgs"],
    ["--search", "console", "demo/pkgs"],
    ["--search", "network", "demo/rules"],   # no hits -> the "nothing touches" line
    # pure -> network (significant), network -> pure, and identical (no change)
    ["--diff", "demo/pkgs/mathlib.planes", "demo/pkgs/fetcher.planes"],
    ["--diff", "demo/pkgs/fetcher.planes", "demo/pkgs/mathlib.planes"],
    ["--diff", "demo/pkgs/sneaky.planes", "demo/pkgs/sneaky.planes"],
]


def _py(cmd):
    r = subprocess.run(["python3", "shapes_cli.py", *cmd], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout, r.returncode


def _js(cmd):
    r = subprocess.run([NODE, "js/shapes_cli.mjs", *cmd], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout, r.returncode


def test_cli_agrees_on_every_command():
    mismatches = []
    for cmd in COMMANDS:
        po, pc = _py(cmd)
        jo, jc = _js(cmd)
        if po != jo or pc != jc:
            mismatches.append(
                f"{' '.join(cmd)}:\n  exit py={pc} js={jc}\n"
                f"  --- py ---\n{po}\n  --- js ---\n{jo}")
    assert not mismatches, "CLI divergences:\n" + "\n".join(mismatches)


def test_index_output_is_a_real_table():
    """Not vacuously agreeing: --index actually produces the table."""
    out, code = _js(["--index", "demo/pkgs"])
    assert code == 0
    assert out.startswith("package")
    assert "sneaky" in out and "library" in out and "network" in out


def test_diff_exit_code_signals_a_new_boundary():
    """--diff exits 1 on a significant change (a new boundary), 0 otherwise —
    the CI-gate contract, agreeing with the Python CLI."""
    _, sig = _js(["--diff", "demo/pkgs/mathlib.planes", "demo/pkgs/fetcher.planes"])
    assert sig == 1
    _, same = _js(["--diff", "demo/pkgs/sneaky.planes", "demo/pkgs/sneaky.planes"])
    assert same == 0


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
        sys.exit(0)
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
