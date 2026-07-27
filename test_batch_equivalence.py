"""`run-batch` answers exactly what `run` answers, over every case.

GRADUATED FROM `scripts/verify_batch_equivalence.py` (C6 / Ruling 3). That
script asserted this and nothing ran it. It is the one assertion in the seven
retired verification scripts with no counterpart anywhere in the suite, and it
is load-bearing: `test_builtin_guards.py` sends its whole case list to the
JavaScript implementation through `run-batch`, so if the batch path answered
differently from the single-program path, every cross-implementation agreement
this repo reports would be validating a path no user takes.

`test_builtin_guards._js_raw` — one node process per case, the original
dispatch — exists ONLY to serve this comparison. Its docstring says so. With
the script gone and nothing graduated, it would have become dead code holding
up a claim nothing checked.

The two paths share `runOne` inside `js/cli.mjs`, which makes divergence
structurally unlikely. This asserts it anyway, because "unlikely by
construction" is how a test stops being run — and it is the whole reason the
retired script existed.

NO CAP. All 481 cases, both ways, ~35 s. That is the slowest single assertion
in the gate, which is why this is its own file and why `scripts/ci.sh --fast`
skips it: a sample would be a quieter claim than the one the retired script
made, and this build is about not making quieter claims. A difference here
means the batch protocol changed a result — do not adjust the comparison to
match it.
"""
import json
import sys

import test_builtin_guards as tbg


def test_run_batch_answers_what_run_answers_for_every_case():
    if tbg.NODE is None:
        return
    srcs = tbg.batch_sources()
    assert len(srcs) >= 481, f"the case list shrank: {len(srcs)}"

    batched = tbg.run_batch(srcs)
    assert set(batched) == set(srcs), "the batch did not answer every case"

    diffs = []
    for i, src in enumerate(srcs):
        r = tbg._js_raw(src)
        if r.returncode != 0:
            # The per-case path signals a crash by exiting non-zero; the batch
            # signals it in-band, so a crash compares as "both crashed".
            per, same = {"crash": r.stderr.strip()}, "crash" in batched[src]
        else:
            per = json.loads(r.stdout)
            bat = {k: v for k, v in batched[src].items() if k != "id"}
            same = per == bat
        if not same:
            diffs.append(f"--- case {i} ---\n{src}"
                         f"  run       = {per}\n  run-batch = {batched[src]}")
    assert not diffs, (f"{len(diffs)} case(s) differ between run and "
                       f"run-batch:\n" + "\n".join(diffs[:5]))


def test_the_per_case_path_is_still_reachable():
    """The comparison is only worth anything while both paths exist. A batch
    mode with no surviving per-case path could not be checked against
    anything."""
    if tbg.NODE is None:
        return
    r = tbg._js_raw("show text of (1 + 1)\n")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["output"] == ["2"], r.stdout


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_")]
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
