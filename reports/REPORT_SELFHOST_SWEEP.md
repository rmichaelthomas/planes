# REPORT_SELFHOST_SWEEP.md

The self-hosting sweep in one pass: every remaining gap between the language
and the interpreter that must be written in it, measured at once. No
production code shipped — the diff is `probe/selfhost/`, `PROBE_SELFHOST.md`,
`CORE_SUBSET.md`, and this report.

---

## 1. The §129 prediction table — refutations first

A refuted prediction removes work from the next build and is the higher-value
output. The prompt names the subject matter of four of §129's six predicted
gaps (gaps 2–5, mapped to Phases 1–4); the other two it references by number
only (see §9, "what this build disproved about this prompt"). Reconstructed
rows are flagged.

### Refuted / refined (lead with these)

| # | §129 prediction (as given) | Verdict | Evidence |
|---|---|---|---|
| 3 | field enumeration / generic traversal is a **gap** (Phase 2) | **REFUTED** | Field enumeration is genuinely absent, but that is not a gap — `when…is` shape dispatch is the *correct* substitute, at 32 arms (= the AST node count, the case count `render.py` already maintains). #13's exhaustive-dispatch discipline makes explicit per-kind dispatch a **feature**, not a deficiency. The gap, if any, is a compile-time exhaustiveness check over `when` ladders — a different thing than enumeration. |
| 2 | environment lookup is the **hardest** gap (Phase 1) | **REFINED** | The cost figure is confirmed (1.30 ms/lookup at 500 entries) but "hardest" is refuted. Rebinding — the feared cost ("an interpreter rebinds constantly") — is ~4 µs and flat; the real cost is the scan, and it is **bounded and survivable with a scoped environment** (§42 adequate to N≈50–200 entries). Harder gaps exist: the join absence (Phase 3) and the recursion ceiling. |
| 5 | fixed-point iteration is missing / underestimated (Phase 4) | **REFINED** | A monotone fixed point **is expressible today**, via recursion (proven: transitive closure converges to 5). So "cannot express fixpoints" is refuted. What remains true: recursion caps it at ~140 rounds, so the gap is real only for *large* fixpoints — a bounded, not a total, absence. |

### Confirmed

| # | §129 prediction (as given) | Verdict | Evidence |
|---|---|---|---|
| 4 | incremental string building is **O(n²)** (Phase 3) | **CONFIRMED** (and extended) | Repeated `+` is O(n²), measured (×3.6 time for ×2 size at scale; 400 KB → 1.25 s). There is **no join**. Extended finding: the list-of-fragments workaround is *also* O(n²) because `plus` in a loop copies the growing list — so both incremental string- and list-building are quadratic. The concrete language answer is a **join**. |
| 1 | *(not stated in prompt — reconstructed: the recursion ceiling)* | **CONFIRMED**, and under-weighted | Measured exactly: succeeds at depth 140, fails at 141. Treated by the prompt as carried background, but for a recursive-descent `eval` written in Planes it **compounds** — usable interpreted-program depth is a fraction of 140 — making it arguably the deepest gap of all. |
| 6 | *(not stated in prompt — reconstructed: `rest of xs`, §130)* | **CONFIRMED needed, OUT OF SCOPE** | List-tail access is ruled at §130 and lands in the next build; not implemented here (Invariant 2 — builtins stay at 8). Phases 1–5 assumed nothing that requires it. |

---

## 2. The `interp.py` reading (§0 step 5)

1154 lines. A **tree-walking evaluator with hand-written `isinstance`
dispatch** — `exec_stmt` (~12 statement kinds) and `eval` (~20 expression
kinds), plus string dispatch in `eval_binop` and `builtin`; 35 `isinstance`
sites, no visitor. **Every value is a `Traced(value, Deriv)`** (provenance
travels with the value). **The environment is a mutable Python `dict` chain**.
**User functions are already inert data** — `Function(name, params, body,
env)`.

**What it does that Planes has no obvious way to express** (three items, not
"a great deal"):

1. **Non-local control flow via host exceptions** — `give` is a `_Give`
   exception; error propagation and `or fail` ride `PlanesError`. Planes must
   thread a status/result record instead.
2. **A mutable, in-place environment** — `Env.set` mutates. Planes must use the
   immutable association idiom (Phase 1).
3. **`isinstance` dispatch over ~20 node classes** — Planes must use `when…is`
   (Phase 2).

Host libraries (`urllib`, `json`, `unicodedata`) are the `foreign`/host
boundary by design, not a gap. The number model is native, not a gap.

---

## 3. Phase 1 verdict (with numbers, and the N)

Association-idiom lookup is linear in entries: **10 → 0.032 ms, 50 → 0.134 ms,
200 → 0.518 ms, 500 → 1.303 ms** per lookup. Nested frames add nothing beyond
total entries walked. Rebinding (`plus`/`with`) is **~4 µs, flat** — the scan,
not the rebind, is the cost. **§42 is adequate up to N ≈ 50 entries**
(sub-second even at thousands of refs) and **stops covering it by N ≈ 200**
(≈1 s at 2000 refs) **through 500** (3–10 s). The answer §42 defers is a design
constraint — *keep scopes small* — not a new construct.

## 4. Phase 2 answer

**Field enumeration is not a gap; hand-dispatch is the correct Planes answer.**
Records are not iterable, no builtin enumerates fields, computed field access
is forbidden by design — and `when…is` dispatch substitutes at 32 arms, the
same case count the Python walkers maintain. #13's discipline makes explicit
dispatch a feature. The residual gap is a mechanical exhaustiveness check over
`when` ladders, not enumeration.

## 5. Phase 3 verdict, and whether a join exists

**There is no join** — every `.join` in the tree is Python's. Incremental `+`
is O(n²) (400 KB → 1.25 s), and the fragment-list workaround is quadratic too.
§42 covers it to ~tens of KB (a lexer-sized render is single-digit ms), visible
by ~100 KB, a wall by ~400 KB. **A join is the concrete language answer.**

## 6. Phase 4 finding and costed candidates

A fixed point **is expressible today via recursion**, bounded by the ~140-round
ceiling; `shapes.planes` would need nothing new for the round (a `for each`
over functions), only for the outer repeat-until-stable. Candidates, **costed
not chosen**: `repeat…until` (new keyword, breaks the 32-ceiling, needs state
threading, escapes the ceiling); `for each n times`/range (needs a range or
`times` keyword; only a safe approximation with a known bound); a fixpoint
builtin (9th builtin — forbidden this build — and needs first-class functions,
which don't exist). They escape the ceiling; they do not *enable* the fixpoint,
which recursion already does.

## 7. Phase 5 answer on function representation

**Functions are not first-class** (cannot be stored in a record, passed, or
called indirectly), but **the inert-data representation works end to end**: a
closure as `{ param, body, env }`, applied by interpretation, survives storage
in a record (→ 15) and carries distinct captures (→ 105, 23). This is how
`interp.py` already represents functions. **`interp.planes` needs no new
construct for functions.**

## 8. The core subset — pointer and summary

See **`CORE_SUBSET.md`**. Mechanically inventoried, the two largest Planes
programs (1682 lines) use **22 of 32 keywords, 3 of 8 builtins, 0 of 7 effect
kinds**; Phases 1–5 add one borderline (`with`). **§127's prediction — that the
`note:`/`because:` planes, the record plane, `rule`, and `foreign` are not
core — is CONFIRMED.** The core is about **half** the named language and
**none** of its effects: a second host can run `interp.planes` without
implementing a single effect kind, `foreign`, the record plane, `rule`, the
annotation planes, or `why`. The surprise is not what is in the core but how
much of the language sits outside it.

---

## 9. What this build disproved about this prompt (never empty)

1. **The six-prediction premise is only two-thirds supplied.** The prompt
   asserts "§129's six predictions" and §10.1 demands all six be marked, but it
   states the subject matter of only four (gaps 2–5). Gaps 1 and 6 are
   referenced by number and never written down, and §129 itself was never read
   in this chain (the prompt's own provenance says so). The six-row table
   **cannot be completed from the materials this build was given** — §1's last
   two rows are reconstructions, flagged as such. This is a real defect in the
   prompt, surfaced rather than papered over.
2. **"Phase 1 is the predicted hardest" is wrong.** Its cost is bounded and
   survivable; the join absence and the recursion ceiling are harder. The
   prompt mis-ranked difficulty.
3. **The prompt's Phase-2 lean toward field enumeration is refuted.**
   Hand-dispatch is correct, not a gap to be closed by enumeration.
4. **The largest-known-unknown did *not* materialize.** The prompt warned: "if
   the answer [to how much of interp.py has no natural Planes expression] is 'a
   great deal', this prompt's Phase 6 core derivation is the wrong shape."
   The answer is **not** a great deal — it reduces to three clean items, each
   with a known Planes idiom. **Phase 6's core derivation is the right shape**;
   the feared outcome is disproved.
5. **The recursion ceiling is not background.** The prompt carries ~140 as a
   settled fact and scopes it to Phase 4. Measured and reasoned about, it is
   **existential for a recursive interpreter** and belongs at the top of the
   language build, not the margin.

---

## 10. S2 — the consolidated language build, scoped

With the inventory complete, this is the deliverable the whole sweep exists to
produce: **every remaining language item, ruled or awaiting ruling, in one
list.** This build implemented none of them.

| item | status | source | note |
|---|---|---|---|
| `rest of xs` (list-tail access) | **RULED (§130)** — next build | prior ruling | Would make builtins 9; explicitly out of scope here. |
| a **join** (fold a fragment list in one O(n) pass) | **AWAITING RULING** | Phase 3 | The concrete answer to O(n²) string building; a 9th builtin, so it interacts with `rest of xs` on the builtin count. |
| **repeat-until / bounded-iteration / fixpoint** construct | **AWAITING RULING** | Phase 4 | Three candidates costed; architect chooses. Needed to exceed the ~140-round ceiling for large fixpoints. |
| the **recursion ceiling** (~140, compounding) | **AWAITING RULING** | §0 / Phase 4 | The deepest issue. Options: raise the limit, trampoline/CPS the interpreter, or accept a depth-bounded `interp.planes`. |
| **`with` in the core** | **AWAITING RULING** | CORE_SUBSET.md §4 | Include for interpreter ergonomics, or hold the core to fresh-record construction (the grammar programs use `with` zero times). |
| **non-local control flow** (`give` / error propagation without host exceptions) | **AWAITING RULING** | §0 reading | Bless the state-record-threading idiom as the canonical self-hosted return/error pattern. |
| **exhaustiveness check over `when` ladders** | **AWAITING RULING** | Phase 2 | To give #13's no-safe-fallback guarantee mechanically for self-hosted dispatch. |
| multi-line record/list literal inside a function body | **AWAITING TRIAGE** (discovered bug) | Phase 5 | Parses at top level, breaks inside an indented body; affects writing `interp.planes`. |
| the **core subset** itself | **AWAITING RULING** | CORE_SUBSET.md | A proposal. Once ruled, the conformance checker (sketched, not built) can be built. |

The through-line: the sweep found **no total blocker** to self-hosting. Every
gap is either bounded (Phases 1, 4), design-answerable without a construct
(Phases 2, 5), a single missing builtin (Phase 3's join), or a decision the
architect can now make with numbers in hand. The one that most deserves a ruling
before `interp.planes` is written is the recursion ceiling, because it is the
one that scales *against* a recursive interpreter rather than with the size of
any single program.
