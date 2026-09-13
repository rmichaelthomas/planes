"""The standalone effect-surface CLI, checked against shapes_cli.py.

The Swift counterpart of test_js_shapes_cli.py. js runs its port as its own entry
point, js/shapes_cli.mjs; the Swift host has one agreement CLI, so the same
shell is its `shapes-cli` subcommand (swift/Sources/PlanesCLI/EffectSurfaceToolCommand.
swift): --index, --search, --diff. No analysis logic lives in the shell — every
command reads only public Surface queries and diff.

Agreement: the same commands, same inputs, same output text and exit code as the
Python CLI. shapes_cli.py is the specification.

The last test has no JavaScript counterpart: a directory of files whose names
are non-ASCII (one differing from another only by normalisation), hidden, or
carry ".planes" twice, indexed and searched through `*`, `?` and `[...]` globs —
where the column padding counts code points and the listing sorts by them.
"""
import os
import subprocess
import sys
import tempfile

from swift_host import REPO, SWIFT, command

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


def _py(cmd, cwd=REPO):
    r = subprocess.run([sys.executable, os.path.join(REPO, "shapes_cli.py"), *cmd], cwd=cwd,
                       capture_output=True, text=True)
    return r.stdout, r.returncode


def _swift(cmd, cwd=REPO):
    r = subprocess.run(command("shapes-cli", *cmd), cwd=cwd, capture_output=True, text=True)
    return r.stdout, r.returncode


def test_cli_agrees_on_every_command():
    mismatches = []
    for cmd in COMMANDS:
        po, pc = _py(cmd)
        so, sc = _swift(cmd)
        if po != so or pc != sc:
            mismatches.append(
                f"{' '.join(cmd)}:\n  exit py={pc} swift={sc}\n"
                f"  --- py ---\n{po}\n  --- swift ---\n{so}")
    assert not mismatches, "CLI divergences:\n" + "\n".join(mismatches)


def test_index_output_is_a_real_table():
    """Not vacuously agreeing: --index actually produces the table."""
    out, code = _swift(["--index", "demo/pkgs"])
    assert code == 0
    assert out.startswith("package")
    assert "sneaky" in out and "library" in out and "network" in out


def test_diff_exit_code_signals_a_new_boundary():
    """--diff exits 1 on a significant change (a new boundary), 0 otherwise —
    the CI-gate contract, agreeing with the Python CLI."""
    _, sig = _swift(["--diff", "demo/pkgs/mathlib.planes", "demo/pkgs/fetcher.planes"])
    assert sig == 1
    _, same = _swift(["--diff", "demo/pkgs/sneaky.planes", "demo/pkgs/sneaky.planes"])
    assert same == 0


# Two directories, because APFS will not hold two names that differ only by
# normalisation side by side: each keeps the form it was created with.
FILES = {
    "pkgs": {
        "caf\u00e9.planes": 'use http\nto get:\n  give ask "https://caf\u00e9.example"\n',
        "\U0001f600.planes": 'use file\nwrite [1] to "\U0001f600.json"\n',
        "\uff41.planes": "x = 1\n",
        "a.planes.planes": 'show "\u00e9"\n',
        ".hidden.planes": 'use http\nx = ask "https://hidden"\n',
        "zz-a-long-package-name-past-sixteen.planes": 'use http\nx = ask "https://z/\u0301"\n',
    },
    "pkgs2": {
        "cafe\u0301.planes": 'use http\nx = ask "https://cafe\u0301.example"\n',
        "\u00e9t\u00e9.planes": 'use http\nx = ask "https://\u00e9t\u00e9"\n',
    },
}


def test_non_ascii_file_names_agree():
    with tempfile.TemporaryDirectory() as d:
        for sub, files in FILES.items():
            os.makedirs(os.path.join(d, sub))
            for name, src in files.items():
                with open(os.path.join(d, sub, name), "w", encoding="utf-8", newline="") as fh:
                    fh.write(src)
        commands = [
            ["--index", "pkgs", "pkgs2"],
            ["--index", "pkgs/*.planes", "pkgs2/caf?\u0301.planes", "pkgs/[a-c]*.planes",
             "pkgs/[!c]*"],
            ["--index", "pkgs/.*.planes"],
            ["--search", "network", "pkgs", "pkgs2"],
            ["--search", "file", "pkgs/*"],
            ["--search", "ambient", "pkgs"],
            ["--diff", "pkgs/caf\u00e9.planes", "pkgs2/cafe\u0301.planes"],
            ["--diff", "pkgs/\uff41.planes", "pkgs/\U0001f600.planes"],
        ]
        mismatches = []
        for cmd in commands:
            po, pc = _py(cmd, cwd=d)
            so, sc = _swift(cmd, cwd=d)
            if po != so or pc != sc:
                mismatches.append(f"{cmd!r}:\n  exit py={pc} swift={sc}\n"
                                  f"  --- py ---\n{po}\n  --- swift ---\n{so}")
        assert not mismatches, "CLI divergences:\n" + "\n".join(mismatches)
        out, _ = _py(["--index", "pkgs", "pkgs2"], cwd=d)
        assert "\ncaf\u00e9" + " " * 13 + "library" in out, out
        assert "\ncafe\u0301" + " " * 12 + "program" in out, out
        assert "hidden" not in out, out


if __name__ == "__main__":
    if SWIFT is None:
        print("  SKIP  swift not on PATH")
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
