#!/usr/bin/env python3
"""A.1's blocking check: `run-batch` answers exactly what `run` answers.

Batching the cross-implementation comparisons is a dispatch change — one node
process for 348 cases instead of 348 processes. It is only that if every case
reports the same thing through both paths, so this runs the whole case list
through both and compares case by case.

The two paths share `runOne` inside `js/cli.mjs`, which makes divergence
structurally unlikely; this asserts it anyway, because "unlikely by
construction" is how a test stops being run.

If a single case differs, this exits 1 and prints both answers. Do not adjust
the comparison to match — a difference here means the batch protocol changed a
result, which is failure mode 2.

Usage: python3 scripts/verify_batch_equivalence.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_builtin_guards as tbg  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="check only the first N cases (a smoke run)")
    args = ap.parse_args()

    if tbg.NODE is None:
        print("node not on PATH — nothing to compare")
        return 0

    srcs = tbg.batch_sources()
    if args.limit:
        srcs = srcs[:args.limit]
    print(f"cases: {len(srcs)}")

    batched = tbg.run_batch(srcs)

    diffs = []
    for i, src in enumerate(srcs):
        r = tbg._js_raw(src)
        if r.returncode != 0:
            # The per-case path signals a crash by exiting non-zero; the batch
            # signals it in-band, so a crash compares as "both crashed".
            per = {"crash": r.stderr.strip()}
            same = "crash" in batched[src]
        else:
            per = json.loads(r.stdout)
            bat = {k: v for k, v in batched[src].items() if k != "id"}
            same = per == bat
        if not same:
            diffs.append((i, src, per, batched[src]))
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(srcs)} compared")

    if diffs:
        print(f"\nFAIL: {len(diffs)} case(s) differ between run and run-batch")
        for i, src, per, bat in diffs[:10]:
            print(f"\n--- case {i} ---\n{src}"
                  f"  run       = {per}\n  run-batch = {bat}")
        return 1

    print(f"\nPASS: {len(srcs)}/{len(srcs)} cases identical "
          f"through `run` and `run-batch`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
