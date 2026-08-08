"""world_runtime.py — the Python persistent-invocation driver (Build 2, §5).

Spec §12 items 1-6, in order:

  1-2. hash and load the module graph once, hoist once     -- `run_file`,
       called exactly once in `WorldRuntime.__init__` (never again).
  3.   instantiate a persistent interpreter                 -- one
       `Interpreter`, held as `self.itp` for the runtime's whole life.
  4.   call a named world-init function once                -- `init()`.
  5.   call a named advance function per fixed-step batch    -- `advance()`,
       any number of times.
  6.   keep immutable Planes world values in memory rather than
       serializing them through JSON each tick                -- `self.world`
       is the `Traced` `advance`/`init` returned, held directly; nothing
       here calls `json.dumps`/`json.loads` on it, ever.

The calling convention this build fixes (documented, not a language
keyword, per the build prompt's explicit "do not invent a language
keyword"): a program loaded through `WorldRuntime` must define

    to world-init:                      # 0 params, gives the initial world record
    to advance of world, tick, events:  # 3 params, gives the next world record

Horizon Phase 2 Build 1 (the input-event seam) extends the two-param
`advance` convention to three: `events` is a Planes value — a list of
typed event records, e.g. `[{ kind: "nudge" }]` — never a new language
keyword, exactly like `world`/`tick` before it. A caller that passes
nothing gets an empty list, which reproduces the old self-driving
behavior byte-for-byte (see `advance()` below).

`replay()` (interp.py, R3 §466-476) already establishes the shape this
reuses: one `Interpreter`, several `run`-shaped calls against it in
sequence, `self.env`/`self.funcs` persisting across every one of them.
`WorldRuntime` is the same pattern with `run_file` for the one load and
`call` for every tick, instead of `run` called once per step.
"""
import world_ir
from interp import Interpreter, from_foreign, to_host
from planes_num import Number

WORLD_INIT = "world-init"
ADVANCE = "advance"


class WorldRuntimeError(Exception):
    """Raised when a loaded program does not honor the calling convention
    (missing `world-init`/`advance`) or when `advance` is called before
    `init`. Distinct from `PlanesError` (a program's own runtime error,
    which propagates unchanged) and from `world_ir.WorldIRError` (a
    returned value that fails world-v1 validation, which also propagates
    unchanged) — this is the driver's own contract, not the language's or
    the protocol's."""


class WorldRuntime:
    """Loads a world program once; advances a live world value per tick.

    `window`/`trace` pass straight through to the one `Interpreter` this
    holds — the R1 retention window and the R3 tracing-off fast path are
    exactly what make calling `advance` many times against one interpreter
    affordable (build prompt §5 requirement 5); this class does not
    reimplement either, it only supplies the persistent call site that
    lets a host actually use them across ticks instead of per run.
    """

    def __init__(self, path, host=None, window=None, trace=True):
        self.itp = Interpreter(host=host, window=window, trace=trace, record=False)
        # The one and only load: run_file hashes, parses, hoists the whole
        # module graph in dependency order and executes the entry file's
        # top-level statements (build prompt §5 requirement 1). Nothing
        # below this line ever calls run_file/load_graph/hoist again.
        self.itp.run_file(path)
        if WORLD_INIT not in self.itp.funcs:
            raise WorldRuntimeError(
                f"'{path}' defines no '{WORLD_INIT}' function — "
                f"a world program must declare `to {WORLD_INIT}:`")
        if ADVANCE not in self.itp.funcs:
            raise WorldRuntimeError(
                f"'{path}' defines no '{ADVANCE}' function — "
                f"a world program must declare "
                f"`to {ADVANCE} of world, tick, events:`")
        advance_params = self.itp.funcs[ADVANCE].params
        if len(advance_params) != 3:
            raise WorldRuntimeError(
                f"'{path}' declares '{ADVANCE}' with {len(advance_params)} "
                f"parameter(s), not 3 — a world program must declare "
                f"`to {ADVANCE} of world, tick, events:`")
        self.world = None
        self.tick = 0

    def init(self):
        """Call `world-init` once, producing the tick-0 world value.

        Returns the `Traced` value, exactly as `advance` does — a caller
        that wants the plain world-v1 envelope reads `.envelope` after
        calling this, not this method's own return value.
        """
        self.world = self.itp.call(WORLD_INIT, [], self.itp.env, 0)
        self.tick = 0
        return self.world

    def advance(self, events=None):
        """Call `advance` once more, producing the next world value.

        `self.world` is REPLACED with the new `Traced`, never mutated in
        place — the value model's own record-update semantics (`with`
        always builds a new dict) already guarantee the interpreter never
        writes through an old reference, so the immutability build prompt
        §5 requirement 3 asks for holds by construction, not by a check
        this method performs. A caller holding the PREVIOUS tick's
        `Traced`/`.value` from an earlier `init()`/`advance()` return
        still has exactly what it had.

        `events` is a plain host list of typed event records (e.g.
        `[{"kind": "nudge"}]`), converted through `from_foreign` — the
        same host-to-Planes boundary conversion `call_foreign` already
        uses for a foreign call's return value — and handed to the
        interpreter's own `mk_lit`, exactly as `tick` is on the line
        below. `events=None` (the default) becomes an empty list, so a
        caller that passes nothing reproduces the prior two-param
        self-driving behavior byte-for-byte (build prompt invariant 1).
        """
        if self.world is None:
            raise WorldRuntimeError(
                f"advance() called before init() — call init() once to run "
                f"'{WORLD_INIT}' before any 'advance' batch")
        tick_traced = self.itp.mk_lit(Number.of(self.tick))
        events_traced = self.itp.mk_lit(from_foreign([] if events is None else events),
                                        label="events")
        self.world = self.itp.call(
            ADVANCE, [self.world, tick_traced, events_traced], self.itp.env, 0)
        self.tick += 1
        return self.world

    @property
    def envelope(self):
        """The current world value's world-v1 envelope (build prompt §5
        acceptance (a): "a valid emittable envelope"). Reuses Build 1's own
        `to_host`/`parse_world_envelope` pair — the exact machinery Phase 1
        emission calls from `show` — rather than a second conversion path,
        since `advance`'s return value is data the driver reads directly,
        not something the demo program necessarily also `show`s.

        Raises `world_ir.WorldIRError` if the current world value is not a
        valid world-v1 envelope — never returns a partial or unchecked
        result.
        """
        if self.world is None:
            raise WorldRuntimeError("no current world value — call init() first")
        native = to_host(self.world.value)
        normalized, warnings = world_ir.parse_world_envelope(native)
        return normalized, warnings
