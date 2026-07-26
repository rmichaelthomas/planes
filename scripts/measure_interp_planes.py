#!/usr/bin/env python3
"""Measure grammar/interp.planes — the interpreter-in-Planes — at a baseline.

S3c (build 2) reasons about four numbers, and A.7's opening note forbids
carrying a report-basis figure a later build may have voided: every number is
established here and used from here.

  1. interpreted expression-nesting depth — how deep a `1 + (1 + (...))` the
     Planes `eval` follows before recursion-too-deep, and frames per level.
  2. interpreted function-call depth, frames per interpreted call, and the
     environment size at the deepest reachable call chain (the A.1 number:
     lexical scoping must hold this flat, dynamic scoping grows it).
  3. the full three-stage-pipeline nesting limit (parse-bound per A.6).
  4. interpreted statement nesting (build 2 only; blocks within blocks).

Method: drive grammar/interp.planes through interp.py exactly as the test
harness does, at increasing depth, watching for recursion-too-deep. The
environment size is read by wrapping the Planes-level `apply-function` (or, in
build 1, reading the deepest env length another way) — see each function.

Run:  .venv/bin/python3 scripts/measure_interp_planes.py
"""
import sys

sys.path.insert(0, ".")
from interp import Deriv, Interpreter, PlanesError, Traced  # noqa: E402


def _fresh():
    i = Interpreter()
    i.run_file("grammar/interp.planes")
    return i


def _traced(v):
    return Traced(v, Deriv("literal", "<host value>", v, []))


# ---------------------------------------------------------------- expr nesting

def nested_expr(n):
    s = "1"
    for _ in range(n):
        s = "1 + (" + s + ")"
    return s


def eval_ok(i, src):
    """True if grammar/interp.planes evaluates src without recursion-too-deep.

    Build the node with a raised Python limit so Python's own parser recursion
    does not mask the interpreted depth, then evaluate at the default limit so
    the number measured is the Planes eval depth, not Python's parse depth.
    """
    try:
        sys.setrecursionlimit(200000)
        node = i.call("node-of-source", [_traced(src)], i.env)
        sys.setrecursionlimit(1000)
        i.call("eval", [node, i.env.get("__empty")], i.env)
        return True
    except PlanesError as e:
        if e.tag == "recursion-too-deep":
            return False
        raise
    except RecursionError:
        return False
    finally:
        sys.setrecursionlimit(1000)


def measure_eval_depth():
    i = _fresh()
    i.run("__empty = []\n")
    lo, hi = 1, 2000
    while eval_ok(i, nested_expr(hi)):
        hi *= 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if eval_ok(i, nested_expr(mid)):
            lo = mid
        else:
            hi = mid
    return lo


# ---------------------------------------------------------------- pipeline

def pipeline_ok(i, src):
    try:
        i.call("evaluate-source", [_traced(src)], i.env)
        return True
    except PlanesError as e:
        if e.tag == "recursion-too-deep":
            return False
        raise
    except RecursionError:
        return False


def measure_pipeline_depth():
    i = _fresh()
    lo, hi = 1, 8
    while pipeline_ok(i, nested_expr(hi)):
        hi *= 2
        if hi > 4000:
            break
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if pipeline_ok(i, nested_expr(mid)):
            lo = mid
        else:
            hi = mid
    return lo


# ---------------------------------------------------------------- env size

def measure_env_at_depth():
    """Largest env length observed while evaluating a deep function-call chain.

    Wraps the Planes-level `apply-function` from outside, reading the length of
    the environment list argument each time a Planes function is applied. The
    A.1 number: whether the env grows with call depth.

    A chain of n functions each calling the next, applied at the depth the
    build reaches, is the deepest realistic call chain. Build 1 bodies are lone
    gives; build 2 uses a real recursive countdown.
    """
    i = _fresh()

    # A recursive countdown of user functions: f_k calls f_{k+1}.
    depth = 60
    defs = "".join(
        f"to f{k} of x: give f{k+1} of (x + 1)\n" for k in range(depth)
    ) + f"to f{depth} of x: give x\n"

    max_env = [0]
    orig = Interpreter.call

    def traced(self, name, args, env):
        # On each Planes-level `run-body`, read the length of the callee-env
        # argument (2nd positional: fn, callee-env, globals, call-env). Args are
        # still AST nodes here, so evaluate it — a plain Var lookup, side-effect-
        # free — and unwrap to the list of { name, value } bindings.
        if name == "run-body" and len(args) >= 2:
            try:
                a = args[1]
                ev = a if isinstance(a, Traced) else self.eval(a, env)
                lst = ev.value if isinstance(ev, Traced) else ev
                if isinstance(lst, list):
                    max_env[0] = max(max_env[0], len(lst))
            except Exception:
                pass
        return orig(self, name, args, env)

    Interpreter.call = traced
    try:
        i.call("evaluate-with", [_traced(defs), _traced("f0 of 0")], i.env)
    except PlanesError:
        pass
    finally:
        Interpreter.call = orig
    return max_env[0], depth


# ---------------------------------------------------------------- interpreted recursion (build 2)

COUNTDOWN = (
    "to cd of k:\n"
    "  if k <= 0:\n"
    "    give 0\n"
    "  give cd of (k - 1)\n"
    "done = cd of DEPTH\n"
)


def program_ok(i, src):
    try:
        state = i.call("execute-program", [_traced(src)], i.env).value
        if state["status"] == "fail":
            return state["error"]["tag"] != "recursion-too-deep"
        return True
    except PlanesError as e:
        if e.tag == "recursion-too-deep":
            return False
        raise
    except RecursionError:
        return False


def _bsearch(pred):
    lo, hi = 1, 8
    while pred(hi):
        hi *= 2
        if hi > 100000:
            break
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if pred(mid):
            lo = mid
        else:
            hi = mid
    return lo


def measure_recursion_depth():
    i = _fresh()
    return _bsearch(lambda n: program_ok(i, COUNTDOWN.replace("DEPTH", str(n))))


def measure_frames_per_interpreted_call():
    """Python frames the host spends per one interpreted function call: the
    stack-depth gap between consecutive Planes-level apply-function-node entries
    while an interpreted function recurses."""
    i = _fresh()
    depths = []
    orig = Interpreter.call

    def traced(self, name, args, env):
        if name == "apply-function-node":
            d = 0
            f = sys._getframe()
            while f is not None:
                d += 1
                f = f.f_back
            depths.append(d)
        return orig(self, name, args, env)

    Interpreter.call = traced
    try:
        i.call("execute-program", [_traced(COUNTDOWN.replace("DEPTH", "20"))], i.env)
    finally:
        Interpreter.call = orig
    diffs = [b - a for a, b in zip(depths, depths[1:]) if b > a]
    return diffs[len(diffs) // 2] if diffs else 0


def measure_statement_nesting():
    """How deep blocks nest within blocks before the ceiling: N nested ifs."""
    i = _fresh()

    def src(n):
        lines = ["marker = 0"]
        for d in range(n):
            lines.append("  " * d + "if true:")
        lines.append("  " * n + "marker = 1")
        return "\n".join(lines) + "\n"

    return _bsearch(lambda n: program_ok(i, src(n)))


def measure_env_at_recursion():
    """Max env length observed at any interpreted apply-function-node while a
    recursive function runs deep -- confirms A.1 holds under real control flow
    (params + the fixed function set, flat with depth)."""
    i = _fresh()
    max_env = [0]
    orig = Interpreter.call

    def traced(self, name, args, env):
        if name == "run-body" and len(args) >= 2:
            try:
                a = args[1]  # callee-env
                ev = a if isinstance(a, Traced) else self.eval(a, env)
                lst = ev.value if isinstance(ev, Traced) else ev
                if isinstance(lst, list):
                    max_env[0] = max(max_env[0], len(lst))
            except Exception:
                pass
        return orig(self, name, args, env)

    Interpreter.call = traced
    try:
        i.call("execute-program", [_traced(COUNTDOWN.replace("DEPTH", "120"))], i.env)
    except (PlanesError, RecursionError):
        pass
    finally:
        Interpreter.call = orig
    return max_env[0]


def main():
    print("# grammar/interp.planes — interpreted-depth measurements (S3c build 2)")
    print(f"# python {sys.version.split()[0]}, recursionlimit "
          f"{sys.getrecursionlimit()}")
    ed = measure_eval_depth()
    print(f"INTERPRETED_EVAL_NESTING_DEPTH   = {ed}")
    rd = measure_recursion_depth()
    fpc = measure_frames_per_interpreted_call()
    print(f"INTERPRETED_RECURSION_DEPTH      = {rd}   "
          f"(frames per interpreted call = {fpc})")
    sn = measure_statement_nesting()
    print(f"INTERPRETED_STATEMENT_NESTING    = {sn}")
    pd = measure_pipeline_depth()
    print(f"FULL_PIPELINE_NESTING_DEPTH      = {pd}")
    er = measure_env_at_recursion()
    print(f"MAX_ENV_LEN_AT_RECURSION_DEPTH   = {er}  (recursion depth 120)")
    try:
        env, depth = measure_env_at_depth()
        print(f"MAX_ENV_LEN_AT_CALL_CHAIN        = {env}  (chain depth {depth})")
    except PlanesError as e:
        print(f"MAX_ENV_LEN_AT_CALL_CHAIN        = blocked: {e.tag}")


if __name__ == "__main__":
    main()
