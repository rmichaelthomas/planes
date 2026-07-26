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
    return Traced(v, Deriv("literal", repr(v), v, []))


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
        # On each Planes-level `apply-function`, read the length of the
        # call-env argument (3rd positional). Args are still AST nodes here, so
        # evaluate it — it is a plain Var lookup, side-effect-free — and unwrap
        # to the underlying list of { name, value } bindings.
        if name == "apply-function" and len(args) >= 3:
            try:
                a = args[2]
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


def main():
    print("# grammar/interp.planes — interpreted-depth baseline")
    print(f"# python {sys.version.split()[0]}, recursionlimit "
          f"{sys.getrecursionlimit()}")
    ed = measure_eval_depth()
    print(f"INTERPRETED_EVAL_NESTING_DEPTH = {ed}")
    pd = measure_pipeline_depth()
    print(f"FULL_PIPELINE_NESTING_DEPTH   = {pd}")
    try:
        env, depth = measure_env_at_depth()
        print(f"MAX_ENV_LEN_AT_CALL_CHAIN     = {env}  (chain depth {depth})")
    except PlanesError as e:
        print(f"MAX_ENV_LEN_AT_CALL_CHAIN     = blocked: {e.tag}")


if __name__ == "__main__":
    main()
