#!/usr/bin/env python3
"""The ladder, Python implementation — and, with --self-hosted, a reduced-
iteration run through the self-hosted interpreter (grammar/interp.planes),
for the record only.

Decomposes the cost of one interpreted Planes-level call by subtraction: each
rung is a tiny program that adds ONE thing to an otherwise-identical call,
run inside a loop, timed as a whole, with an empty-loop control subtracted to
isolate what that one rung adds. It changes nothing it measures: every rung
and the control run through the ordinary `Interpreter().run(src)` entry
point exactly as any program does; nothing here reaches into the
interpreter's own methods (contrast scripts/measure_frames_per_call.py,
which wraps Interpreter.call from outside to observe stack depth — this
script only times a black-box `run`).

WHY A NESTED `for each` LOOP, NOT RECURSION. Planes recursion has a ceiling
around ~140-200 levels deep (measure_frames_per_call.py measures it
directly) -- far short of the hundreds of thousands of iterations a 200ms
floor needs at sub-microsecond per-call costs. `for each` (interp.py's
eval_foreach) iterates with a native Python `for` loop, not a Planes-level
call, so it never touches that ceiling. A single flat list of that many
elements would also mean a source-text literal of several megabytes --
parsed every trial, which would swamp the very thing being measured. Nesting
two `for each` loops over the SAME modest list (length L, N = L*L total
iterations) keeps the source text small while N scales quadratically with L.
The nesting's own overhead (one extra Env per level) is identical between a
rung and its control, so it cancels in the subtraction exactly like the loop
overhead does.

Timer: time.perf_counter_ns() -- monotonic, nanosecond resolution.

Per rung: calibrate L so ONE run takes >= 200ms, run one further untimed
warm-up pass sized to max(10% of N, 1000) iterations, then run 7 timed
trials at the calibrated L. The empty-loop control is measured the SAME way,
AT THE SAME L as the rung it will be subtracted from (not independently
calibrated to its own 200ms floor) -- see reports/REPORT_CALL_COST.md Sec 1
for why that is the correct comparison. Median and minimum are reported
across the 7 trials, not the mean.

Run:  .venv/bin/python3 scripts/measure_call_cost.py [--json] [--self-hosted]
"""
import json
import platform
import sys
import time

sys.path.insert(0, ".")
from host import TestHost  # noqa: E402
from interp import Interpreter, PlanesError  # noqa: E402

TRIALS = 7
TARGET_NS = 200_000_000  # 200ms floor, per Sec 4.2 of the build prompt
MAX_L = 4000
MAX_CALIBRATION_STEPS = 25

# Reduced-iteration self-hosted pass: grammar/interp.planes running under
# interp.py, driving each rung's source through its own `execute-program` --
# the same pattern scripts/run_corpus_through_planes.py uses. Metacircular
# execution pays the interpreter's own cost twice over, so this is timed at
# a small fixed L and reported separately, clearly marked not comparable.
SELF_HOSTED_L = 4  # N = 16, tiny on purpose -- "for the record only"
SELF_HOSTED_TRIALS = 3

RUNGS = [
    {
        "name": "control",
        "label": "empty loop (no call)",
        "preamble": "",
        "call_expr": None,
    },
    {
        "name": "rung1_noop",
        "label": "rung 1 -- noop, no args, empty body: dispatch + environment allocation",
        "preamble": "to noop:\n  give nothing\n",
        "call_expr": "noop",
    },
    {
        "name": "rung2_ident",
        "label": "rung 2 -- ident of x: give x: + parameter binding",
        "preamble": "to ident of x:\n  give x\n",
        "call_expr": "ident of 1",
    },
    {
        "name": "rung3_add1",
        "label": "rung 3 -- add1 of x: give x + 1: + one rational op and its derivation record",
        "preamble": "to add1 of x:\n  give x + 1\n",
        "call_expr": "add1 of 1",
    },
    {
        "name": "rung4_add3",
        "label": "rung 4 -- add3 of x: give x + 1 + 1 + 1: marginal cost of "
                 "two more arithmetic ops, no extra call",
        "preamble": "to add3 of x:\n  give x + 1 + 1 + 1\n",
        "call_expr": "add3 of 1",
    },
    {
        "name": "rung5_txt",
        "label": "rung 5 -- txt of x: give text of x: a derived value with no gcd",
        "preamble": "to txt of x:\n  give text of x\n",
        "call_expr": "txt of 1",
    },
    {
        "name": "rung6_circle",
        "label": "rung 6 -- c of x, y, r: the draw.planes circle helper's body exactly",
        "preamble": (
            'to c of x, y, r:\n'
            '  show "draw circle " + text of x + " " + text of y + " " + text of r\n'
        ),
        "call_expr": "c of 1, 2, 3",
    },
    {
        "name": "rung7_depth1",
        "label": "rung 7a -- assignment to an outer-scope name, recursion depth 1",
        "preamble": (
            "outer = 0\n"
            "to recur of n:\n"
            "  if n <= 0:\n"
            "    outer = n\n"
            "    give 0\n"
            "  else:\n"
            "    give recur of (n - 1)\n"
        ),
        "call_expr": "recur of 1",
    },
    {
        "name": "rung7_depth8",
        "label": "rung 7b -- assignment to an outer-scope name, recursion depth 8",
        "preamble": (
            "outer = 0\n"
            "to recur of n:\n"
            "  if n <= 0:\n"
            "    outer = n\n"
            "    give 0\n"
            "  else:\n"
            "    give recur of (n - 1)\n"
        ),
        "call_expr": "recur of 8",
    },
]


def build_list(n):
    return "[" + ", ".join(str(i) for i in range(n)) + "]"


def build_src(rung, length):
    list_lit = build_list(length)
    call_expr = rung["call_expr"]
    body = f"let ignored = {call_expr}" if call_expr else "let ignored = j"
    loop = f"for each i in base:\n  for each j in base:\n    {body}\n"
    return f"{rung['preamble']}let base = {list_lit}\n{loop}"


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n % 2:
        return s[(n - 1) // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def run_once(src, label):
    # TestHost, not the default PythonHost: PythonHost.show() calls print(),
    # and rung 6 calls `show` once per iteration -- real stdout I/O per call
    # would swamp the very cost being measured. TestHost's show() only
    # appends to an in-memory list (host.py), matching js/host_browser.mjs's
    # BrowserHost used by the JS ladder's runProgram.
    t0 = time.perf_counter_ns()
    try:
        Interpreter(host=TestHost()).run(src)
    except PlanesError as e:
        raise RuntimeError(f"{label}: {e.tag}: {e}") from e
    t1 = time.perf_counter_ns()
    return t1 - t0


def calibrate(rung):
    length = 10
    elapsed_ns = 0
    for _ in range(MAX_CALIBRATION_STEPS):
        src = build_src(rung, length)
        elapsed_ns = run_once(src, rung["name"])
        if elapsed_ns >= TARGET_NS or length >= MAX_L:
            return length, elapsed_ns
        scale = (TARGET_NS / max(elapsed_ns, 1)) ** 0.5
        length = min(MAX_L, max(length + 1, int(length * scale * 1.15) + 1))
    return length, elapsed_ns


def measure(rung, length):
    n = length * length
    warmup_n = max(1000, -(-n // 10))  # ceil(0.1 * n)
    warmup_length = max(1, int(warmup_n ** 0.5 - 1e-9) + 1)
    warmup_src = build_src(rung, warmup_length)
    run_once(warmup_src, rung["name"])  # discarded -- warm-up only

    src = build_src(rung, length)
    trials_ns = [run_once(src, rung["name"]) for _ in range(TRIALS)]
    return {
        "L": length,
        "N": n,
        "warmupL": warmup_length,
        "warmupNActual": warmup_length * warmup_length,
        "trialsNs": trials_ns,
        "medianNs": median(trials_ns),
        "minNs": min(trials_ns),
    }


def run_native_ladder():
    control_rung = RUNGS[0]
    target_rungs = RUNGS[1:]
    results = {}
    for rung in target_rungs:
        length, _ = calibrate(rung)
        rung_result = measure(rung, length)
        control_result = measure(control_rung, length)
        marginal_median_ns = rung_result["medianNs"] - control_result["medianNs"]
        marginal_min_ns = rung_result["minNs"] - control_result["minNs"]
        results[rung["name"]] = {
            "label": rung["label"],
            "L": length,
            "N": rung_result["N"],
            "warmupNActual": rung_result["warmupNActual"],
            "rungTrialsNs": rung_result["trialsNs"],
            "controlTrialsNs": control_result["trialsNs"],
            "rungMedianNs": rung_result["medianNs"],
            "rungMinNs": rung_result["minNs"],
            "controlMedianNs": control_result["medianNs"],
            "controlMinNs": control_result["minNs"],
            "marginalMedianNsPerCall": marginal_median_ns / rung_result["N"],
            "marginalMinNsPerCall": marginal_min_ns / rung_result["N"],
        }

    def med(name):
        return results[name]["marginalMedianNsPerCall"]

    def mn(name):
        return results[name]["marginalMinNsPerCall"]

    derived = {
        "arithmeticMarginalMedianNsPerOp": (med("rung4_add3") - med("rung3_add1")) / 2,
        "arithmeticMarginalMinNsPerOp": (mn("rung4_add3") - mn("rung3_add1")) / 2,
        "derivedValueVsRationalOpMedianNs": med("rung5_txt") - med("rung3_add1"),
        "derivedValueVsRationalOpMinNs": mn("rung5_txt") - mn("rung3_add1"),
        "depth8VsDepth1MedianNs": med("rung7_depth8") - med("rung7_depth1"),
        "depth8VsDepth1MinNs": mn("rung7_depth8") - mn("rung7_depth1"),
    }
    return results, derived


def run_self_hosted_ladder():
    """Each rung's source run through grammar/interp.planes (itself run by
    interp.py) via `execute-program`, at SELF_HOSTED_L -- metacircular, so
    every cost below is paid twice over. Not compared numerically against
    the native figures above; reported for the record only."""
    shared = Interpreter(host=TestHost())
    shared.run_file("grammar/interp.planes")

    def t(value):
        from interp import Deriv, Traced
        return Traced(value, Deriv("literal", "<host value>", value, []))

    def run_self_hosted_once(src, label):
        t0 = time.perf_counter_ns()
        state = shared.call("execute-program", [t(src)], shared.env).value
        t1 = time.perf_counter_ns()
        if state["status"] == "fail":
            raise RuntimeError(f"self-hosted {label}: {state['error']['tag']}")
        return t1 - t0

    control_rung = RUNGS[0]
    target_rungs = RUNGS[1:]
    results = {}
    for rung in target_rungs:
        rung_src = build_src(rung, SELF_HOSTED_L)
        control_src = build_src(control_rung, SELF_HOSTED_L)
        n = SELF_HOSTED_L * SELF_HOSTED_L
        rung_trials = [
            run_self_hosted_once(rung_src, rung["name"]) for _ in range(SELF_HOSTED_TRIALS)
        ]
        control_trials = [
            run_self_hosted_once(control_src, "control") for _ in range(SELF_HOSTED_TRIALS)
        ]
        marginal_median = median(rung_trials) - median(control_trials)
        results[rung["name"]] = {
            "label": rung["label"],
            "L": SELF_HOSTED_L,
            "N": n,
            "rungTrialsNs": rung_trials,
            "controlTrialsNs": control_trials,
            "marginalMedianNsPerCall": marginal_median / n,
        }
    return results


def main():
    json_mode = "--json" in sys.argv
    self_hosted = "--self-hosted" in sys.argv

    machine = {
        "implementation": "python",
        "pythonVersion": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "cpu": platform.processor() or platform.machine(),
    }

    results, derived = run_native_ladder()
    output = {
        "machine": machine,
        "trials": TRIALS,
        "targetMs": TARGET_NS / 1e6,
        "results": results,
        "derived": derived,
    }

    if self_hosted:
        output["selfHosted"] = {
            "note": "metacircular (interp.py running grammar/interp.planes); "
                    "reduced iteration counts; not comparable to the native figures",
            "L": SELF_HOSTED_L,
            "trials": SELF_HOSTED_TRIALS,
            "results": run_self_hosted_ladder(),
        }

    if json_mode:
        print(json.dumps(output))
        return

    print("# The ladder -- Python")
    print(f"PYTHON_VERSION={machine['pythonVersion']}")
    print(f"PLATFORM={machine['platform']}")
    print(f"CPU={machine['cpu']}")
    print(f"TRIALS={TRIALS}")
    print(f"TARGET_MS={TARGET_NS / 1e6}")
    for rung in RUNGS[1:]:
        r = results[rung["name"]]
        print(f"--- {rung['name']} ---")
        print(f"LABEL={r['label']}")
        print(f"L={r['L']} N={r['N']} WARMUP_N={r['warmupNActual']}")
        print(f"RUNG_TRIALS_NS={','.join(str(x) for x in r['rungTrialsNs'])}")
        print(f"CONTROL_TRIALS_NS={','.join(str(x) for x in r['controlTrialsNs'])}")
        print(f"MARGINAL_MEDIAN_NS_PER_CALL={r['marginalMedianNsPerCall']:.2f}")
        print(f"MARGINAL_MIN_NS_PER_CALL={r['marginalMinNsPerCall']:.2f}")
    print("--- derived ---")
    for k, v in derived.items():
        print(f"{k}={v:.2f}")

    if self_hosted:
        print("--- self-hosted (for the record only; NOT comparable) ---")
        for rung in RUNGS[1:]:
            r = output["selfHosted"]["results"][rung["name"]]
            print(f"SELF_HOSTED {rung['name']}: L={r['L']} N={r['N']} "
                  f"MARGINAL_MEDIAN_NS_PER_CALL={r['marginalMedianNsPerCall']:.2f}")


if __name__ == "__main__":
    main()
