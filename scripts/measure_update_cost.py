#!/usr/bin/env python3
"""The update-cost ladder, Python implementation.

Decomposes the cost of one functional update (`with`, record update; `plus`,
list append — v5.0 §72) by subtraction, in the same discipline
scripts/measure_call_cost.py uses for calls: each rung is a tiny program that
adds ONE thing to an otherwise-identical loop body, run inside a nested
`for each`, timed as a whole, with a control subtracted to isolate what that
one rung adds. It changes nothing it measures: every rung and the control run
through the ordinary `Interpreter(host=TestHost()).run(src)` entry point;
nothing here reaches into the interpreter's own methods.

Two arms:

  THE with ARM. For each record width W in WITH_WIDTHS, a control (touches
  the base record, no update) and three rungs: rung 1 (`r with f0: 1`, one
  field written, one copy), rung 2 (`r with f0: 1 with f1: 2`, a SECOND
  chained `with` -- a second copy), rung 3 (`r with f0: 1, f1: 2`, two
  fields written in ONE `with` -- one copy, two field writes). Rung 3 minus
  rung 1 isolates the marginal cost of a field write with the copy held
  constant; rung 2 minus rung 3 isolates the cost of the second copy.

  THE plus ARM. For each list length L in PLUS_LENGTHS, a control (reads the
  base list, appends nothing) and one rung (`xs plus i`, one append at
  length L).

Plus a CUMULATIVE measurement: build a list to length CUMULATIVE_L by
CUMULATIVE_L repeated `plus` reassignments in a single program run (not N
independent trials of one append each -- one run, L sequential appends,
timed as a whole), reporting total wall time and the implied O(L^2)
constant, with an extrapolation to EXTRAPOLATE_TO events stated as an
extrapolation.

WHY A NESTED `for each` LOOP, NOT RECURSION -- identical reasoning to
scripts/measure_call_cost.py (its docstring is the canonical statement):
Planes recursion has a ceiling far short of the iteration counts a 200ms
floor needs; `for each` iterates with a native Python `for`, never touching
that ceiling; nesting two loops over the SAME modest list (length L_iter,
N = L_iter*L_iter total iterations) keeps source text small while N scales
quadratically. `L_iter` here is the LOOP iteration-count parameter,
distinct from W (record width) and L (list length under test) -- it is
calibrated per rung exactly as scripts/measure_call_cost.py calibrates its
own L.

Timer: time.perf_counter_ns() -- monotonic, nanosecond resolution, matching
scripts/measure_call_cost.py and NOT any coarser wall-clock source.

Per rung: calibrate L_iter so ONE run takes >= 200ms, run one further
untimed warm-up pass sized to max(10% of N, 1000) iterations, then run 7
timed trials at the calibrated L_iter. The control is measured the SAME
way, AT THE SAME L_iter as the rung it will be subtracted from -- see
reports/REPORT_CALL_COST.md §1 and reports/REPORT_UPDATE_COST.md §4 for why
that is the correct comparison. Median and minimum are reported across the
7 trials, not the mean.

Run:  .venv/bin/python3 scripts/measure_update_cost.py [--json]
"""
import json
import os
import platform
import sys
import time

sys.path.insert(0, ".")
from host import TestHost  # noqa: E402
from interp import Interpreter, PlanesError  # noqa: E402
from parser import parse  # noqa: E402

TRIALS = 7
TARGET_NS = 200_000_000  # 200ms floor, matching measure_call_cost.py
MAX_L = 4000
MAX_CALIBRATION_STEPS = 25

WITH_WIDTHS = [4, 8, 16, 32, 64, 128]
PLUS_LENGTHS = [64, 256, 1024, 4096, 16384]

CUMULATIVE_BASE = 128           # 128*128 = 16384 sequential `plus` appends
CUMULATIVE_L = CUMULATIVE_BASE * CUMULATIVE_BASE
EXTRAPOLATE_TO = 100_000

WITH_RUNG_NAMES = ["rung1_single", "rung2_chained", "rung3_multi"]
WITH_RUNG_LABELS = {
    "rung1_single": "rung 1 -- let r2 = r with f0: 1: one field written, one copy",
    "rung2_chained": "rung 2 -- let r2 = r with f0: 1 with f1: 2: a second chained "
                      "`with` -- rung 2 minus rung 3 isolates the second copy",
    "rung3_multi": "rung 3 -- let r2 = r with f0: 1, f1: 2: two fields in one "
                   "RecordUpdate -- rung 3 minus rung 1 isolates one field write",
}

PLUS_RUNG_NAME = "rung1_append"
PLUS_RUNG_LABEL = "rung 1 -- let xs2 = xs plus i: one append at length L"


def build_list(n):
    return "[" + ", ".join(str(i) for i in range(n)) + "]"


def build_record(width):
    fields = ", ".join(f"f{i}: {i}" for i in range(width))
    return "{ " + fields + " }"


def build_with_src(rung_name, width, iter_l):
    """`rung_name` is None for the control (touches `r`, no update)."""
    record = build_record(width)
    body_exprs = {
        None: "r",
        "rung1_single": "r with f0: 1",
        "rung2_chained": "r with f0: 1 with f1: 2",
        "rung3_multi": "r with f0: 1, f1: 2",
    }
    body = f"let ignored = {body_exprs[rung_name]}"
    loop = f"for each i in base:\n  for each j in base:\n    {body}\n"
    return f"let r = {record}\nlet base = {build_list(iter_l)}\n{loop}"


def build_plus_src(rung_name, length, iter_l):
    """`rung_name` is None for the control (reads `xs`, appends nothing)."""
    base_list = build_list(length)
    body_exprs = {
        None: "xs",
        PLUS_RUNG_NAME: "xs plus i",
    }
    body = f"let ignored = {body_exprs[rung_name]}"
    loop = f"for each i in base:\n  for each j in base:\n    {body}\n"
    return f"let xs = {base_list}\nlet base = {build_list(iter_l)}\n{loop}"


def build_cumulative_src():
    base_list = build_list(CUMULATIVE_BASE)
    return (
        f"let base = {base_list}\n"
        "xs = []\n"
        "for each i in base:\n"
        "  for each j in base:\n"
        "    xs = xs plus j\n"
        "show \"LEN=\" + text of (count of xs)\n"
    )


WORLD_T = 32  # matches benchmarks/world_shape.planes exactly
WORLD_SUBJECT_COUNTS = [16, 64, 256]
WORLD_FACET_W = 4
WORLD_SUBJECT_W = 7
WORLD_WORLD_W = 3

# Everything in benchmarks/world_shape.planes except the `subject-count` /
# `subject-ids` lines, which this generates per S. Kept byte-for-byte
# identical to the shipped file's function definitions so the two cannot
# silently drift; test_update_cost.py checks build_world_src(64) against the
# file on disk.
# Built from concatenated fragments (not one triple-quoted block) so no
# physical Python line exceeds ruff's 100-column limit -- adjacent string
# literals concatenate to the exact same value, so this changes nothing
# about the resulting Planes source text.
_WORLD_PRELUDE = (
    "to make-subject of i:\n"
    "  give {\n"
    '    identity: { id: i, kind: "subject", canonical: true, version: 1 },\n'
    '    situation: { place: "passage", x: i, y: 0, active: true },\n'
    '    relation: { contains: [], connects-to: [], near: [], belongs-to: "world" },\n'
    '    behavior: { pattern: "patrol", state: "idle", ticks-in-state: 0, '
    'deterministic: true },\n'
    '    expression: { asset: "subject-mesh", layer: 1, animation: "idle", '
    'material: "default" },\n'
    '    affordance: { actions: [], preconditions: [], authority: "system", '
    'fallback: "none" },\n'
    '    lineage: { source: "world-shape-benchmark", author: "system", '
    'agreement: "none", immutable: false }\n'
    "  }\n"
    "\n"
    "to toggle-state of s:\n"
    '  if s == "active":\n'
    '    give "idle"\n'
    "  else:\n"
    '    give "active"\n'
    "\n"
    "to advance-subject of subj, tick-num:\n"
    "  let situation = subj.situation\n"
    "  let new-situation = situation with x: situation.x + 1, y: situation.y + 1\n"
    "  let behavior = subj.behavior\n"
    "  let new-behavior = behavior with state: (toggle-state of behavior.state), "
    "ticks-in-state: behavior.ticks-in-state + 1\n"
    "  give subj with situation: new-situation, behavior: new-behavior\n"
    "\n"
    "to advance-world of world, tick-num:\n"
    "  let new-subjects = for each subj in world.subjects: advance-subject of "
    "subj, tick-num\n"
    '  let evt = { sequence: tick-num, kind: "tick-advance", subject-count: '
    "count of new-subjects }\n"
    "  let new-events = world.events plus evt\n"
    "  give world with subjects: new-subjects, events: new-events, tick: tick-num\n"
)


def build_world_src(s):
    return build_world_src_for(s, WORLD_T)


def build_world_src_for(s, t):
    """Phase 3 (build prompt §6) reuses this at t != WORLD_T to checkpoint
    the derivation graph at a chosen tick count -- otherwise identical to
    build_world_src."""
    ids = build_list(s)
    ticks = build_list(t)
    return (
        _WORLD_PRELUDE
        + f'let subject-count = {s} because "S — the subject count this canonical '
        'instance measures; the sweep script generates the same shape at S in 16, 64, 256"\n'
        + f"let subject-ids = {ids}\n"
        + f"let ticks = {ticks}\n"
        "\nlet initial-subjects = for each i in subject-ids: make-subject of i\n"
        "let initial-world = { subjects: initial-subjects, events: [], tick: 0 }\n"
        "\ncurrent-world = initial-world\n"
        "for each t in ticks:\n"
        "  current-world = advance-world of current-world, t\n"
        '\nshow "FINAL-TICK=" + text of current-world.tick\n'
        'show "SUBJECT-COUNT=" + text of subject-count\n'
        'show "EVENTS-LENGTH=" + text of (count of current-world.events)\n'
        'show "FACET-FIELD-COUNT=4"\n'
        'show "SUBJECT-FIELD-COUNT=7"\n'
        'show "WORLD-FIELD-COUNT=3"\n'
    )


def parse_once(src):
    t0 = time.perf_counter_ns()
    parse(src)
    t1 = time.perf_counter_ns()
    return t1 - t0


def calibrate_repeats(src, timer_fn):
    sample = max(1, timer_fn(src))
    k = max(1, -(-TARGET_NS // sample))  # ceil
    return min(k, 5000)


def measure_repeated(src, timer_fn, k):
    warmup_k = max(1, -(-k // 10))
    for _ in range(warmup_k):
        timer_fn(src)  # discarded
    trial_totals = []
    for _ in range(TRIALS):
        total = 0
        for _ in range(k):
            total += timer_fn(src)
        trial_totals.append(total)
    return {
        "k": k,
        "trialTotalsNs": trial_totals,
        "medianNsPerRun": median(trial_totals) / k,
        "minNsPerRun": min(trial_totals) / k,
    }


def interpolate(x0, y0, x1, y1, x):
    if x1 == x0:
        return y0
    return y0 + (x - x0) / (x1 - x0) * (y1 - y0)


def run_world_phase(with_results, with_per_width, with_derived, plus_derived):
    """Phase 2 (build prompt §5): the same primitive, in the shape Horizon
    will actually produce. (a) parse+load and (c) the remainder are
    measured DIRECTLY, by timing benchmarks/world_shape.planes's own
    program (generated per S) through the ordinary `run`/`parse` entry
    points. (b) with/plus copy cost is DERIVED from the with/plus arms
    already measured above -- never measured a second time inside this
    program's own timing, per §5(b) -- applied to the actual widths (facet=4,
    tested directly; subject=7, interpolated between the tested W=4/W=8
    points; world=3, extrapolated below W=4 from the fitted line) and the
    actual events-list length trajectory this program produces (0..WORLD_T-1,
    averaged)."""
    # facet_update_ns: situation/behavior each write 2 fields in one `with`
    # on a 4-field record -- exactly rung 3's shape at the tested W=4 point.
    facet_update_ns = with_results["4"]["rungs"]["rung3_multi"]["marginalMedianNsPerCall"]
    rung3_at_8 = with_results["8"]["rungs"]["rung3_multi"]["marginalMedianNsPerCall"]
    # subject_update_ns: the same 2-field-write shape on a 7-field record --
    # interpolated between the tested W=4 and W=8 rung-3 points.
    subject_update_ns = interpolate(4, facet_update_ns, 8, rung3_at_8, WORLD_SUBJECT_W)
    # world_update_ns: 3 fields written on a 3-field record (a full
    # rewrite) -- the fitted 1-field-write model extrapolated to W=3, plus
    # two more field-write increments (costPerUpdate's rung-1 shape writes
    # only one field; the world `with` writes three).
    cost_per_update_at_3 = (with_derived["costPerUpdateNsIntercept"]
                             + with_derived["costPerUpdateNsPerFieldSlope"] * WORLD_WORLD_W)
    facet_field_write_ns = with_per_width[str(WORLD_FACET_W)]["fieldWriteMarginalMedianNs"]
    world_update_ns = cost_per_update_at_3 + 2 * facet_field_write_ns

    avg_events_length = (WORLD_T - 1) / 2
    plus_cost_ns = (plus_derived["nsIntercept"]
                     + plus_derived["nsPerElementSlope"] * avg_events_length)

    world_timer = lambda s: run_once(s, "world-trial")  # noqa: E731

    results = {}
    for s in WORLD_SUBJECT_COUNTS:
        src = build_world_src(s)
        k = calibrate_repeats(src, world_timer)
        total = measure_repeated(src, world_timer, k)
        parse_total = measure_repeated(src, parse_once, k)

        total_ns_per_run_median = total["medianNsPerRun"]
        parse_ns_per_run_median = parse_total["medianNsPerRun"]
        exec_ns_per_run_median = total_ns_per_run_median - parse_ns_per_run_median

        a_parse_per_tick = parse_ns_per_run_median / WORLD_T
        exec_per_tick = exec_ns_per_run_median / WORLD_T
        b_copy_per_tick = (s * (2 * facet_update_ns + subject_update_ns)
                            + world_update_ns + plus_cost_ns)
        c_remainder_per_tick = exec_per_tick - b_copy_per_tick

        results[str(s)] = {
            "S": s,
            "T": WORLD_T,
            "k": k,
            "totalNsPerRunMedian": total_ns_per_run_median,
            "totalNsPerRunMin": total["minNsPerRun"],
            "parseNsPerRunMedian": parse_ns_per_run_median,
            "parseNsPerRunMin": parse_total["minNsPerRun"],
            "aParseNsPerTick": a_parse_per_tick,
            "bCopyNsPerTick": b_copy_per_tick,
            "cRemainderNsPerTick": c_remainder_per_tick,
            "totalNsPerTick": total_ns_per_run_median / WORLD_T,
            "facetUpdateNs": facet_update_ns,
            "subjectUpdateNs": subject_update_ns,
            "worldUpdateNs": world_update_ns,
            "plusCostNsAtAvgLength": plus_cost_ns,
            "avgEventsLength": avg_events_length,
        }
    return results


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n % 2:
        return s[(n - 1) // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def run_once(src, label):
    t0 = time.perf_counter_ns()
    try:
        Interpreter(host=TestHost()).run(src)
    except PlanesError as e:
        raise RuntimeError(f"{label}: {e.tag}: {e}") from e
    t1 = time.perf_counter_ns()
    return t1 - t0


def calibrate(build_src_fn):
    length = 10
    elapsed_ns = 0
    for _ in range(MAX_CALIBRATION_STEPS):
        src = build_src_fn(length)
        elapsed_ns = run_once(src, "calibrate")
        if elapsed_ns >= TARGET_NS or length >= MAX_L:
            return length, elapsed_ns
        scale = (TARGET_NS / max(elapsed_ns, 1)) ** 0.5
        length = min(MAX_L, max(length + 1, int(length * scale * 1.15) + 1))
    return length, elapsed_ns


def measure(build_src_fn, length):
    n = length * length
    warmup_n = max(1000, -(-n // 10))  # ceil(0.1 * n)
    warmup_length = max(1, int(warmup_n ** 0.5 - 1e-9) + 1)
    run_once(build_src_fn(warmup_length), "warmup")  # discarded

    src = build_src_fn(length)
    trials_ns = [run_once(src, "trial") for _ in range(TRIALS)]
    return {
        "L": length,
        "N": n,
        "trialsNs": trials_ns,
        "medianNs": median(trials_ns),
        "minNs": min(trials_ns),
    }


def linear_fit(xs, ys):
    """Least-squares slope/intercept of ys against xs -- used to state the
    fitted ns/field (with arm) and ns/element (plus arm) slope, per
    Criterion C (build prompt §1): with cost is expected to scale linearly
    in record field count, plus cost linearly in list length."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den else 0.0
    intercept = mean_y - slope * mean_x
    return slope, intercept


def run_with_arm():
    results = {}
    for width in WITH_WIDTHS:
        control_fn = lambda il, w=width: build_with_src(None, w, il)  # noqa: E731
        iter_l, _ = calibrate(control_fn)
        # Calibrate against rung3 (the most expensive rung at this width) so
        # every rung at this width is measured at the SAME iter_l -- required
        # for the marginal-over-control subtraction to hold N constant.
        rung3_fn = lambda il, w=width: build_with_src("rung3_multi", w, il)  # noqa: E731
        iter_l_rung, _ = calibrate(rung3_fn)
        iter_l = min(iter_l, iter_l_rung)

        control_result = measure(control_fn, iter_l)
        width_result = {"L": iter_l, "N": control_result["N"],
                         "controlMedianNs": control_result["medianNs"],
                         "controlMinNs": control_result["minNs"],
                         "controlTrialsNs": control_result["trialsNs"],
                         "rungs": {}}
        for rung_name in WITH_RUNG_NAMES:
            rung_fn = lambda il, w=width, r=rung_name: build_with_src(r, w, il)  # noqa: E731
            rung_result = measure(rung_fn, iter_l)
            marginal_median = rung_result["medianNs"] - control_result["medianNs"]
            marginal_min = rung_result["minNs"] - control_result["minNs"]
            width_result["rungs"][rung_name] = {
                "label": WITH_RUNG_LABELS[rung_name],
                "rungMedianNs": rung_result["medianNs"],
                "rungMinNs": rung_result["minNs"],
                "rungTrialsNs": rung_result["trialsNs"],
                "marginalMedianNsPerCall": marginal_median / rung_result["N"],
                "marginalMinNsPerCall": marginal_min / rung_result["N"],
            }
        results[str(width)] = width_result

    def med(width, rung):
        return results[str(width)]["rungs"][rung]["marginalMedianNsPerCall"]

    def mn(width, rung):
        return results[str(width)]["rungs"][rung]["marginalMinNsPerCall"]

    per_width = {}
    for width in WITH_WIDTHS:
        per_width[str(width)] = {
            "fieldWriteMarginalMedianNs": med(width, "rung3_multi") - med(width, "rung1_single"),
            "fieldWriteMarginalMinNs": mn(width, "rung3_multi") - mn(width, "rung1_single"),
            "secondCopyMarginalMedianNs": med(width, "rung2_chained") - med(width, "rung3_multi"),
            "secondCopyMarginalMinNs": mn(width, "rung2_chained") - mn(width, "rung3_multi"),
            "costPerUpdateMedianNs": med(width, "rung1_single"),
            "costPerUpdateMinNs": mn(width, "rung1_single"),
        }

    isolated_copy_xs = WITH_WIDTHS
    isolated_copy_ys = [per_width[str(w)]["secondCopyMarginalMedianNs"] for w in WITH_WIDTHS]
    isolated_slope, isolated_intercept = linear_fit(isolated_copy_xs, isolated_copy_ys)

    update_ys = [per_width[str(w)]["costPerUpdateMedianNs"] for w in WITH_WIDTHS]
    update_slope, update_intercept = linear_fit(isolated_copy_xs, update_ys)

    derived = {
        "isolatedCopyNsPerFieldSlope": isolated_slope,
        "isolatedCopyNsIntercept": isolated_intercept,
        "costPerUpdateNsPerFieldSlope": update_slope,
        "costPerUpdateNsIntercept": update_intercept,
    }
    return results, per_width, derived


def run_plus_arm():
    results = {}
    for length in PLUS_LENGTHS:
        control_fn = lambda il, n=length: build_plus_src(None, n, il)  # noqa: E731
        rung_fn = lambda il, n=length: build_plus_src(PLUS_RUNG_NAME, n, il)  # noqa: E731
        iter_l_control, _ = calibrate(control_fn)
        iter_l_rung, _ = calibrate(rung_fn)
        iter_l = min(iter_l_control, iter_l_rung)

        control_result = measure(control_fn, iter_l)
        rung_result = measure(rung_fn, iter_l)
        marginal_median = rung_result["medianNs"] - control_result["medianNs"]
        marginal_min = rung_result["minNs"] - control_result["minNs"]
        results[str(length)] = {
            "label": PLUS_RUNG_LABEL,
            "L": iter_l,
            "N": rung_result["N"],
            "controlMedianNs": control_result["medianNs"],
            "controlMinNs": control_result["minNs"],
            "controlTrialsNs": control_result["trialsNs"],
            "rungMedianNs": rung_result["medianNs"],
            "rungMinNs": rung_result["minNs"],
            "rungTrialsNs": rung_result["trialsNs"],
            "marginalMedianNsPerCall": marginal_median / rung_result["N"],
            "marginalMinNsPerCall": marginal_min / rung_result["N"],
        }

    xs = PLUS_LENGTHS
    ys = [results[str(pl)]["marginalMedianNsPerCall"] for pl in PLUS_LENGTHS]
    slope, intercept = linear_fit(xs, ys)
    derived = {"nsPerElementSlope": slope, "nsIntercept": intercept}
    return results, derived


def run_cumulative():
    src = build_cumulative_src()
    run_once(src, "cumulative-warmup")  # discarded
    trials_ns = [run_once(src, "cumulative-trial") for _ in range(TRIALS)]
    total_median = median(trials_ns)
    total_min = min(trials_ns)
    # L*(L-1)/2 total element-copies across the whole grow-to-L run (the
    # i-th append copies i existing elements): O(L^2)/2, so k = total / (L*(L-1)/2)
    # is the implied per-copied-element constant.
    pairs = CUMULATIVE_L * (CUMULATIVE_L - 1) / 2
    k_median = total_median / pairs
    k_min = total_min / pairs
    extrapolated_median_ns = k_median * EXTRAPOLATE_TO * (EXTRAPOLATE_TO - 1) / 2
    extrapolated_min_ns = k_min * EXTRAPOLATE_TO * (EXTRAPOLATE_TO - 1) / 2
    return {
        "L": CUMULATIVE_L,
        "trialsNs": trials_ns,
        "totalMedianNs": total_median,
        "totalMinNs": total_min,
        "impliedNsPerCopiedElementMedian": k_median,
        "impliedNsPerCopiedElementMin": k_min,
        "extrapolateToEvents": EXTRAPOLATE_TO,
        "extrapolatedTotalMedianNs": extrapolated_median_ns,
        "extrapolatedTotalMinNs": extrapolated_min_ns,
        "note": "extrapolation from the fitted O(L^2) constant; not measured directly",
    }


RETENTION_S = 64
RETENTION_CHECKPOINTS = [1, 100, 300, 600]
RETENTION_SOAK_SECONDS = 30 * 60
RETENTION_TICKS_PER_SECOND = 60


def count_reachable_derivs(root):
    """BFS over Deriv.inputs from `root` (a Deriv, not a Traced), counting
    UNIQUE reachable nodes by object identity. Reads only public fields
    (`.inputs`) -- never calls an interpreter method (build prompt §3's
    permitted exception for the retention arm)."""
    seen = set()
    stack = [root]
    while stack:
        node = stack.pop()
        node_id = id(node)
        if node_id in seen:
            continue
        seen.add(node_id)
        for inp in node.inputs:
            if id(inp) not in seen:
                stack.append(inp)
    return len(seen)


def run_retention_phase():
    """Phase 3 (build prompt §6): reachable Deriv count and process RSS at
    tick 1/100/300/600 for world_shape's shape at S=64. Four independent
    full runs (0..checkpoint-1 ticks each) through the ordinary `run` entry
    point -- deterministic and pure, so this gives the SAME final world
    value a single continuous 600-tick run would at each checkpoint, without
    needing to pause mid-run. Checkpoints run low to high in one process so
    `ru_maxrss` (a high-water mark, never decreasing) is read in an order
    where each new checkpoint does strictly more work than the last."""
    import gc
    import resource

    results = {}
    for checkpoint in RETENTION_CHECKPOINTS:
        src = build_world_src_for(RETENTION_S, checkpoint)
        interp = Interpreter(host=TestHost())
        interp.run(src)
        traced_world = interp.env.get("current-world")
        deriv_count = count_reachable_derivs(traced_world.node)
        gc.collect()
        ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports KB.
        rss_bytes = ru_maxrss if sys.platform == "darwin" else ru_maxrss * 1024
        results[str(checkpoint)] = {
            "checkpointTick": checkpoint,
            "S": RETENTION_S,
            "reachableDerivCount": deriv_count,
            "rssBytes": rss_bytes,
        }
        del interp, traced_world
        gc.collect()

    # rss_bytes is `ru_maxrss`, a process-wide HIGH-WATER MARK -- and this
    # phase runs last, after the with/plus/cumulative/world phases have
    # already pushed that mark up with their own (unrelated) allocations. The
    # ABSOLUTE reading is therefore not "memory this retention run used"; the
    # GROWTH relative to the tick=1 checkpoint is, since every checkpoint
    # after it does strictly more retention work on top of the same
    # already-contaminated baseline. Slope and extrapolation are fitted on
    # that growth, not on the raw absolute bytes.
    ticks = [results[str(c)]["checkpointTick"] for c in RETENTION_CHECKPOINTS]
    derivs = [results[str(c)]["reachableDerivCount"] for c in RETENTION_CHECKPOINTS]
    rss = [results[str(c)]["rssBytes"] for c in RETENTION_CHECKPOINTS]
    rss_baseline = rss[0]
    rss_growth = [v - rss_baseline for v in rss]
    deriv_slope, deriv_intercept = linear_fit(ticks, derivs)
    rss_slope, rss_intercept = linear_fit(ticks, rss_growth)

    soak_ticks = RETENTION_SOAK_SECONDS * RETENTION_TICKS_PER_SECOND
    extrapolated_bytes = rss_intercept + rss_slope * soak_ticks
    extrapolated_derivs = deriv_intercept + deriv_slope * soak_ticks

    return {
        "S": RETENTION_S,
        "checkpoints": RETENTION_CHECKPOINTS,
        "results": results,
        "rssBaselineBytes": rss_baseline,
        "rssGrowthBytes": rss_growth,
        "derivCountPerTickSlope": deriv_slope,
        "rssGrowthBytesPerTickSlope": rss_slope,
        "soakSeconds": RETENTION_SOAK_SECONDS,
        "soakTicksPerSecond": RETENTION_TICKS_PER_SECOND,
        "soakTicks": soak_ticks,
        "extrapolatedRssGrowthBytes": extrapolated_bytes,
        "extrapolatedDerivCount": extrapolated_derivs,
        "note": "rss is a process-wide high-water mark contaminated by earlier "
                "phases in this run; growth is measured relative to the tick=1 "
                "checkpoint, not in absolute bytes. Extrapolation is from a "
                "4-point linear fit over ticks 1..600; not measured directly.",
    }


def run_retention_subprocess():
    """Runs this script's own --retention-only mode as a fresh subprocess, so
    the RSS reading reflects only the retention phase's footprint, not
    whatever the with/plus/cumulative/world phases already pushed the
    process's high-water mark to."""
    import subprocess

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--retention-only", "--json"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)["retention"]


def main():
    if "--retention-only" in sys.argv:
        print(json.dumps({"retention": run_retention_phase()}))
        return

    json_mode = "--json" in sys.argv

    machine = {
        "implementation": "python",
        "pythonVersion": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "cpu": platform.processor() or platform.machine(),
    }

    with_results, with_per_width, with_derived = run_with_arm()
    plus_results, plus_derived = run_plus_arm()
    cumulative = run_cumulative()
    world_results = run_world_phase(with_results, with_per_width, with_derived, plus_derived)
    # `ru_maxrss` is a process-wide HIGH-WATER MARK. Measured in this same
    # process, the with/plus/cumulative/world phases above (W=128 records,
    # L=16384 lists, S=256 subjects) already push it past anything 600 ticks
    # of a 64-subject retention run needs, so an in-process reading is
    # useless -- it was observed to read flat zero growth end to end. A
    # subprocess isolates retention's own footprint.
    retention = run_retention_subprocess()

    output = {
        "machine": machine,
        "trials": TRIALS,
        "targetMs": TARGET_NS / 1e6,
        "with": {
            "widths": WITH_WIDTHS,
            "rungNames": WITH_RUNG_NAMES,
            "results": with_results,
            "perWidth": with_per_width,
            "derived": with_derived,
        },
        "plus": {
            "lengths": PLUS_LENGTHS,
            "rungName": PLUS_RUNG_NAME,
            "results": plus_results,
            "derived": plus_derived,
        },
        "cumulative": cumulative,
        "world": {
            "subjectCounts": WORLD_SUBJECT_COUNTS,
            "ticks": WORLD_T,
            "facetW": WORLD_FACET_W,
            "subjectW": WORLD_SUBJECT_W,
            "worldW": WORLD_WORLD_W,
            "results": world_results,
        },
        "retention": retention,
    }

    if json_mode:
        print(json.dumps(output))
        return

    print("# The update-cost ladder -- Python")
    print(f"PYTHON_VERSION={machine['pythonVersion']}")
    print(f"PLATFORM={machine['platform']}")
    print(f"CPU={machine['cpu']}")
    print(f"TRIALS={TRIALS}")
    print(f"TARGET_MS={TARGET_NS / 1e6}")
    print("--- with arm ---")
    for width in WITH_WIDTHS:
        w = with_results[str(width)]
        print(f"W={width} L={w['L']} N={w['N']} "
              f"CONTROL_MEDIAN_NS={w['controlMedianNs']:.1f}")
        for rung_name in WITH_RUNG_NAMES:
            r = w["rungs"][rung_name]
            print(f"  {rung_name}: MARGINAL_MEDIAN_NS_PER_CALL="
                  f"{r['marginalMedianNsPerCall']:.2f} "
                  f"MARGINAL_MIN_NS_PER_CALL={r['marginalMinNsPerCall']:.2f}")
        pw = with_per_width[str(width)]
        print(f"  fieldWriteMarginalMedianNs={pw['fieldWriteMarginalMedianNs']:.2f} "
              f"secondCopyMarginalMedianNs={pw['secondCopyMarginalMedianNs']:.2f}")
    print(f"isolatedCopyNsPerFieldSlope={with_derived['isolatedCopyNsPerFieldSlope']:.3f}")
    print(f"costPerUpdateNsPerFieldSlope={with_derived['costPerUpdateNsPerFieldSlope']:.3f}")
    print("--- plus arm ---")
    for length in PLUS_LENGTHS:
        p = plus_results[str(length)]
        print(f"L={length} iterL={p['L']} N={p['N']} "
              f"MARGINAL_MEDIAN_NS_PER_CALL={p['marginalMedianNsPerCall']:.2f} "
              f"MARGINAL_MIN_NS_PER_CALL={p['marginalMinNsPerCall']:.2f}")
    print(f"nsPerElementSlope={plus_derived['nsPerElementSlope']:.4f}")
    print("--- cumulative ---")
    print(f"L={cumulative['L']} TOTAL_MEDIAN_NS={cumulative['totalMedianNs']:.0f} "
          f"TOTAL_MIN_NS={cumulative['totalMinNs']:.0f}")
    print(f"impliedNsPerCopiedElementMedian={cumulative['impliedNsPerCopiedElementMedian']:.4f}")
    print(f"EXTRAPOLATED to {EXTRAPOLATE_TO}: "
          f"{cumulative['extrapolatedTotalMedianNs'] / 1e6:.1f}ms (median-derived, EXTRAPOLATION)")
    print("--- world (benchmarks/world_shape.planes shape) ---")
    for s in WORLD_SUBJECT_COUNTS:
        w = world_results[str(s)]
        print(f"S={s} T={w['T']} k={w['k']} "
              f"TOTAL_NS_PER_TICK={w['totalNsPerTick']:.0f} "
              f"a_parse={w['aParseNsPerTick']:.0f} "
              f"b_copy={w['bCopyNsPerTick']:.0f} "
              f"c_remainder={w['cRemainderNsPerTick']:.0f}")
    print("--- retention (S=64, derivation graph reachable from `current-world`) ---")
    for c in RETENTION_CHECKPOINTS:
        r = retention["results"][str(c)]
        print(f"TICK={c} REACHABLE_DERIVS={r['reachableDerivCount']} "
              f"RSS_BYTES={r['rssBytes']}")
    print(f"derivCountSlopePerTick={retention['derivCountPerTickSlope']:.2f}")
    print(f"rssGrowthBytesSlopePerTick={retention['rssGrowthBytesPerTickSlope']:.1f}")
    print(f"EXTRAPOLATED {retention['soakSeconds']/60:.0f}min soak @ "
          f"{retention['soakTicksPerSecond']}tick/s = {retention['soakTicks']} ticks: "
          f"{retention['extrapolatedRssGrowthBytes']/1e6:.1f}MB RSS growth, "
          f"{retention['extrapolatedDerivCount']:.0f} derivs (EXTRAPOLATION)")


if __name__ == "__main__":
    main()
