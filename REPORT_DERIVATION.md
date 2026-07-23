# Session Report — The Static Derivation Graph, Named Subjects, and the Second Guarantee

Resolves P-Q16 (primary), P-Q10 (by measurement), P-Q18 (decided at the top
of the build prompt, carried through implementation unchanged). Extends
Checkpoint v2.0.

---

## §8's claim: survived

`rules.py`'s import block, quoted in full:

```python
"""Rule-plane checker — permits, exception resolution, fingerprinting.

Tests inception checkpoint §8's claim that a rule is the same question
Shapes and Why already answer, asked at compile time. shapes.py computes a
program's effect surface; this module only consumes it, through the public
`Surface` queries (`at`, `targets`, `touches`, `declared`, `kinds`,
`boundaries`, and — since the static derivation graph build — `origins_of`,
the one query named-subject resolution needs). If this file ever needs to
reach inside `Analyser`, `Consts`, or `Effect` construction, that is a
finding about §8 — report it, don't route around it. `hashlib`, for
fingerprinting (§5), is the one import this file has ever needed — stdlib,
not a `shapes` coupling.

Matching is static and structural (unbound v2.0 §34): no execution. A rule
is never triggered; it is only ever checked against a surface that was
already computed without running anything.
"""
import hashlib
```

`ast.parse(open("rules.py").read())` walked and its import statements
collected gives exactly `{"hashlib"}` — asserted directly now
(`test_rules_module_imports_only_hashlib`), not just reviewed by eye. The
file gained exactly one new public query it calls: `Surface.origins_of`.
`Surface.derivation_of` exists (built-prompt §3.4 asked for both), but
`rules.py` never calls it — `origins_of` alone supplies everything named-
subject resolution and the §24 derivation line need.

## P-Q10: the numbers

`python3 shapes_cli.py <file> --derivation-stats`:

| | `hn.planes` | `money.planes` |
|---|---|---|
| effects with a derivation | 5 | 5 |
| max nodes per effect | 8 | 13 |
| mean nodes per effect | 4.6 | 6.6 |
| max graph depth | 5 | 8 |

Both bounded and small. `money.planes` runs more arithmetic per effect
(`unit * qty`, `subtotal * rate`, `subtotal + tax`, `round total to 2
places`) and correspondingly has a deeper graph, but depth 8 over ~13 nodes
is nowhere near creep — it is the literal shape of five chained `let`s. No
suppression heuristic was added, and none was needed: **P-Q10 resolves
empirically. Derivation survives arithmetic without becoming Jif-style
label creep**, on both programs measured.

Two structural reasons the numbers stay small, both pre-existing bounds
this build did not touch and one design choice this build made
deliberately for exactly this purpose:

- `is_recursive()`, the `self.depth > 6` cap in `const_call`, and the
  `self.depth > 4` cap in `specialise` already prevent unbounded inlining
  across calls.
- `assigned_in()`'s join-widening collapses a branch/loop-rebound name to a
  single `"unknown"` node rather than a node per branch.
- **New in this build:** `const_call`'s `"call"`-kind node's `inputs` are
  the *argument* nodes only, not the callee's internal derivation chain
  (§3.3 below). A chain of nested pure-function calls therefore grows the
  graph linearly in call depth, not multiplicatively in call depth ×
  callee-body size.

## The `const_value()` decision

**Rejected — no wrapper added.** Grepped every call site of `.const(`,
`.pattern(`, `.describe(`, and `.claim_target(` across the repository
before writing any code:

```
shapes.py:439,447,454,468,492,580,604,610,638,800,803,804,814,822,843,
          876,894,921,924,938,942,944,945
```

All internal call sites — verified with `grep -n` both before writing any
code (to make the decision) and after (to confirm every site was actually
updated, listed above at post-edit line numbers). No external caller
exists in `rules.py`, `shapes_cli.py`, any test file, or `modules.py`. Every
call site was updated in place to consume `(value, StaticDeriv)` (and, for
`describe()`, `(text, computed, StaticDeriv)`) tuples directly. No
`const_value()` compatibility wrapper was written, because nothing needed
one — adding it anyway would have been an unused abstraction.

## Existing test changed — argued

`test_named_subject_raises_rather_than_passing_silently` (`test_rules.py`)
asserted `"not yet supported" in str(e)`. That phrase described the old
blanket refusal: *any* subject other than `anything` raised, unconditionally,
because no derivation graph existed to check one against. That claim is now
false — a derivation graph exists and most named subjects resolve. The test
now asserts `"does not resolve" in str(e)` instead: the specific program in
that test (no variable named `readings` exists anywhere in it) still cannot
report clean, for the reason that now actually applies (the subject was not
found), rather than the reason that used to apply (subjects were categorically
unsupported). **The guarantee the test protects — a named-subject rule must
never report clean because the graph could not reach it — is unchanged.**
Only the message, and the specific failure branch that produces it, changed.

## Decisions this build made that the prompt did not specify

Four, named explicitly per the build prompt's own instruction, for accept or
reject:

1. **File-context threading via `self.current_file`/`self.func_file`, not a
   `file` parameter threaded through every constant-evaluation method.**
   `Analyser` gained `self.current_file` (pushed/popped around
   `specialise()` and `const_call()` exactly like the existing
   `self.depth` guard) instead of adding a `file` argument to `const()`,
   `pattern()`, `describe()`, `const_builtin()`, `claim_target()`, and
   `walk()`. This kept the diff to the handful of places that actually
   cross a function boundary, rather than touching every call site of
   every one of those methods. **Recommend: lock.** The alternative
   (parameter-threading) would have been a much larger, more error-prone
   diff for the same result, and `self.depth`'s push/pop pattern already
   established this style as idiomatic for this file.

2. **`const()`'s `Var` branch always wraps in a fresh `"name"` node,
   including when the value it wraps is itself unknown.** Read literally,
   the build prompt's "Var → kind=name, input is the stored node" doesn't
   distinguish a known-value read from a widened one. This build applies it
   uniformly: every read of an identifier gets a `"name"`-kind node labeled
   with that identifier, regardless of what's underneath. Consequence: a
   variable's name survives being read even after its value widened to
   `UNKNOWN` at a branch/loop join (the wrap happens unconditionally on
   read, not conditionally on knownness). This is what makes
   `origins_of` useful for rule-subject resolution even across widened
   values — a rule naming a subject whose value can't be pinned down can
   still be *checked* (conservatively, mirroring how a computed target is
   already a possible match rather than a skipped one). **Recommend:
   lock.** It is the load-bearing reason decision 4 below is a real
   simplification rather than a silent capability loss.

3. **`pattern()`'s fallback branch reuses the node `const()` already built,
   instead of manufacturing a fresh disconnected `StaticDeriv("unknown",
   "{...}")`.** The original (pre-node) code discarded everything on the
   unknown path because it only tracked a placeholder string. Once nodes
   exist, discarding the node `const()` already computed — which may
   itself be a `"name"` node wrapping an `"unknown"` one — throws away
   exactly the chain `origins_of` needs. This is a deliberate deviation
   from a surface reading of "keep every statically known chunk, mark the
   rest," made because the literal reading would make derivation tracing
   vacuous on every value that widens through a `pattern()` call (which is
   most of them — anything computed). **Recommend: lock.**

4. **`RuleNotSupported`'s four bullets (§3.5 of the build prompt) collapsed
   to three in this implementation.** Because of decision 2, a subject name
   that was rebound-and-widened at a join is *still* discoverable by label
   through `origins_of` — only the `"unknown"` node underneath signals the
   widening, not the absence of the `"name"` wrapper. This means the build
   prompt's third bullet ("resolves to nothing") and fourth bullet
   ("derivation widened to unknown") are not separately reachable states
   given this design: if the label isn't found at all, that's bullet 3; a
   genuinely present name is always resolvable to a file via `origins_of`,
   whether or not its value was widened. `_resolve_subject` therefore
   implements three outcomes — resolved in the declaring file, resolved
   only in another file (P-Q18), or not resolved at all — collapsing the
   prompt's third and fourth into one message
   ("does not resolve to anything in the traced effect surface"). **Flagging
   for explicit accept/reject rather than treating as obviously correct:**
   an alternative design where join-widening drops the name label entirely
   (storing a bare `"unknown"` node with no name at the point of rebinding,
   rather than letting the read-time wrap re-attach it) would make bullet 4
   reachable as originally specified, at the cost of losing the
   conservative-match behavior decision 2 buys. This build chose the
   conservative-match behavior; the four-bullet distinction was the
   tradeoff.

## Test counts

| | before this build | after |
|---|---|---|
| `test_shapes.py` | 63/63 | 72/72 |
| `test_rules.py` | 47/47 | 53/53 |
| `test_planes.py` (untouched — session gate) | 50/50 | 50/50 |
| `test_coverage.py`, `test_foreign.py`, `test_host.py`, `test_names.py`, `test_numbers.py` (untouched) | 104/104 | 104/104 |

No new test suite was created; both extensions (`test_shapes.py`,
`test_rules.py`) only. The standing session gate
(`test_ordinary_program_needs_no_governance`,
`test_ordinary_program_is_traceable` in `test_planes.py`) was not modified
and passes.

## Order of work followed

Steps 1–4 of the build prompt's §6 (StaticDeriv/Consts, const()/pattern()
returning nodes, Effect.derivation, Surface queries) were implemented as one
branch — steps 1 and 2 specifically were combined into a single commit
rather than two, because `Consts` cannot usefully store nodes until
`const()` produces them and vice versa; splitting them would have left an
intermediate commit that doesn't run. Step 5 (`--derivation-stats`, the
P-Q10 measurement) was a reporting gate, done before touching `rules.py`.
Steps 6–7 (narrowed `RuleNotSupported` with P-Q18 scoping, the §24
derivation line) were the second branch.

## Commits

```
3d63305 shapes: retain a static derivation graph instead of discarding it
00e60af shapes: expose derivation_of/origins_of on Surface
eb755b3 shapes_cli: add --derivation-stats for the P-Q10 measurement
5829132 rules: resolve named subjects against the static derivation graph (P-Q18)
```
