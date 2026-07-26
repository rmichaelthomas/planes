# REPORT — the fix field, the seam counted honestly, and an effect vocabulary that stays closed

C4, on `feat/fix-field-seam-and-effect-refusal`, base `b173190`.
Four phases, four commits, one PR.

| | before | after |
|---|---:|---:|
| `scripts/ci.sh` wall | ≈ 491 s | **47–50 s** |
| suite files / reporting | 54 / **52** | 54 / **54** |
| oks | 996 | **1085** |
| `node` spawns per gate | 3602 | 1274 |
| reserved words | 32 | 32 |
| builtins | 10 | 10 |
| effect kinds | 7 | 7 |
| host methods, **declared** | 8 | **7** |
| host methods, **used** | 7 | **7** |
| reference error work list | 0 of 109 | **0 of 109** |
| self-hosted fix-clause shortfall | not measurable | **73 of 114** |

`scripts/verify_fast_follow.py`: **31 of 31 checks pass**, full run (not
`--quick`). Table in `fast-follow-verification.md`.

---

## §1 — Phase C's call-site table, and the arithmetic

C.1's grep, run over every `.py`, `.mjs` and `.planes` in the repo, separating
calls on a **host object** from module-level functions of the same name and
from `json.dumps` / `JSON.stringify` directly. Tests of a method are excluded:
they are what let a dead method look alive.

| method | declared | production call sites |
|---|---|---|
| `ask` | yes | `interp.py:936`, `js/interp.mjs:753` |
| `read` | yes | `interp.py:963`, `js/interp.mjs:782` |
| `write` | yes | `interp.py:794`, `js/interp.mjs:628` |
| `show` | yes | `interp.py:585`, `js/interp.mjs:415` |
| `clock` | yes | `interp.py:453`, `js/interp.mjs:327` |
| `resolve` | yes | `interp.py:1194`, `js/interp.mjs:992` |
| `parse_json` | yes | `interp.py:949`, `js/interp.mjs:768` |
| **`to_json`** | **yes** | **none** |
| `record` | optional | `interp.py:455`, `js/interp.mjs:332` |

`host.to_json`'s only call site anywhere was `js/cli.mjs`'s `host to_json`
probe — a subcommand that exists so `test_js_host.py` can test the method.
`test_host.py` checked the surface with `hasattr(Host, name)`, a declaration
check, which cannot distinguish a live method from a dead one.

**The arithmetic. Before: declared 8, used 7. After: declared 7, used 7.**

So the P-Q17 question — *does the seam grow to nine, or substitute at eight?* —
had a third answer neither branch anticipated: **it was seven all along.**
Removing a dead method is subtraction, not substitution, so C1's proposed
`call_foreign_json` boundary is **not spent** and remains available as a ruling
for the architect. The "eight methods, not a rewrite" claim is **restated at
seven**, and seven is now the *used* count, not merely the declared one.

### Why it was dead, which is the more interesting half

`host.to_json` was `json.dumps(value, indent=2)` — it takes an already-plain
value. The one site in the language that serialises is the `write` effect, and
`interp.py`'s `WriteTo` calls a **module-level** `to_json` that first unwraps
the value model (`Traced` → raw, `Number` → int-or-text) and *then* calls
`json.dumps(..., indent=2)`.

The host method could not have served that site even if something had reached
for it: it did not know the value model. It was not a live method that fell out
of use — it was declared in a shape that could never do its job.

`parse_json` is the mirror image and stays: one live caller, `interp.py`'s
`ask` builtin, `from_foreign(self.host.parse_json(body))`, unchanged.

### What moved with it

The two byte-identity checks (`json.dumps(v, indent=2)`, and non-ASCII
escaping matching `ensure_ascii`) lived on the dead wrapper. They are now
pointed at `pyJsonDumps` — the serialiser `js/interp.mjs`'s module-level
`toJson` actually hands its unwrapped value to on the write path — through a
new `node js/cli.mjs json-dumps` probe. **The assertions are unchanged; they
now check code that runs.** Removing dead code must not take live coverage
with it.

`grammar/interp.planes`'s own header comment claimed `interp.py` "calls them at
exactly two sites — an `ask`'s response and a `write`'s payload." It called
the pair at **one**. That comment is corrected in place; overstating the seam
by one site is part of why the dead method survived three builds.

---

## §2 — Phase B's self-hosted catalogue shortfall

`REPORT_DETAIL_CONVERGENCE.md` §6 recorded that `grammar/interp.planes`
"cannot name a fix anywhere" and was outside the fix-clause commitment as
measured. That was correct: there was no slot. §158 opened one
(`error-fix-of`), so the self-hosted files are inside the commitment for the
first time and `errors_coverage.py` counts them:

| state | count |
|---|---:|
| names a fix | 6 of 114 (5%) |
| deliberately names none | 35 of 114 (31%) |
| **should name one and does not** | **73 of 114 (64%)** |

By file: `interp.planes` 54, `parser.planes` 15, `lexer.planes` 3,
`json.planes` 1.

**Reported, not merged, and not driven to zero.** The reference's work list
stays at 0 of 109 and merging would hide that. Closing the self-hosted 73 is a
body of message-writing work with its own ruling; a non-zero work list is the
honest output of the build that made it measurable. `errors_coverage.py` still
exits 0 by construction (invariant 4).

The classification is structural, read off the source the way `grammar_gen.py`
reads Python raise sites: `error-fix-of` names one; `error-of` names none;
`fail <bare-name> as tag` re-raises a message written elsewhere and is
*deliberate* for the same stated reason `or fail`'s re-tag is; `fail "..." as
tag` wrote its own message with nowhere to put a fix and is shortfall.

---

## §3 — Gate timing

Full tables in `gate-timing-pre.md` and `gate-timing-post.md`.
**Machine: Darwin 25.5.0, arm64, 10 cores.** Both files state it.

| | before | after |
|---|---:|---:|
| whole gate | ≈ 491 s | 47–50 s |
| suites, parallel (10 jobs) | — | 44.4 s |
| suites, serial (`PLANES_JOBS=1`) | 488.7 s | 193.9 s |
| `scripts/ci.sh --fast` | — | 10.0 s |

Three changes, by what each returned:

1. **294.8 s** — the suite stopped running itself twice (§4 finding 1).
2. **149.5 s** — the suites run in parallel (193.9 s serial → 44.4 s at 10 jobs).
3. **44.9 s** — `run-batch`: `test_builtin_guards.py` 47.5 s → 2.6 s.

`scripts/verify_batch_equivalence.py`: **481 / 481 cases identical** through
`run` and `run-batch`. The two share `runOne` inside `js/cli.mjs`, so
divergence is structurally unlikely; it is asserted anyway.

The `--fast` tier's eleven suites are the top 80.2% of serial time, named in
`scripts/ci.sh` with each one's measured cost. It is not the gate and says so.

---

## §4 — The hermeticity audit

Grepped every suite for fixed paths under the system temp directory, for
writes outside a `TemporaryDirectory`, and for anything mutating a repo file.
Reported here including where nothing needed changing.

**Three genuine parallel hazards, all handled by declaring the suite exclusive
— it runs alone, before the parallel batch:**

| suite | what it mutates | why it races |
|---|---|---|
| `test_grammar_data.py` | `grammar/vocabulary.json`, in place — first corrupt JSON, then `format: 999`, restored in a `finally` | any suite importing `lexer` or `parser` inside that window loads a corrupt grammar |
| `test_shapes.py` | creates `demo/cycle/`, `demo/broken/` with `.planes` files | eight suites walk `demo/` and would pick them up mid-flight |
| `test_rules.py` | creates `demo/_deriv_subject/` with `.planes` files | same |

**Found and needing no change:**

* `test_builtin_guards.py`'s `<tmp>/c2-no-such-dir/f.json` — the fixed shared
  path the prompt flagged. It only asserts the directory is *absent* and never
  creates it, so concurrency cannot make it flaky. Left alone.
* `test_assertions.py`'s `os.chdir` — process-global, but each suite is its own
  process and it is restored in a `finally`. Not a cross-suite hazard.
* Every other `open(..., "w")` in a suite is inside a `TemporaryDirectory`.

`.ci-logs/` is in `.gitignore`.

---

## §5 — What this build disproved about this prompt

Never empty, and this one is no exception. **Six**, including two of the
prompt's own four corrections.

**1. The gate's hotspot was not either hypothesis, and is 50.9% of it on its
own.** Both named hypotheses were confirmed, and neither was the answer.
`test_coverage.py::test_the_suite_does_not_touch_the_real_world` re-runs
**every other suite** as a subprocess to check for filesystem leaks — so the
gate executed the whole test suite **twice**. That one test is **248.9 s of
488.7 s** and **1801 of 3602 `node` spawns**. It is larger than every
JavaScript agreement suite combined, and no prior report in this repo names
it. The prompt's §3 hypotheses looked at `test_builtin_guards.py` because that
is where a reading happened to look — exactly as §A.0 warned about itself.

**2. The 528 spawn count was low by 6.8×.** The prompt named it a lower bound
and it is one: repo-wide the figure is **3602**. (`test_builtin_guards.py`'s
own 528 is exactly right — and it is 481 *distinct* programs, so the batch
dedups 47.) This is the fourth consecutive build in this chain to find a count
in its own prompt low by roughly an order of magnitude.

**3. `996 oks across 52 suites` was not a clean bill of health — 68 tests were
never running.** 54 `test_*.py` files exist; 52 printed a result.
`test_core_check.py` (6 tests) and `test_interp_statements_in_planes.py` (62
tests) had **no `__main__` runner**, so `python3 <file>` imported the module,
ran nothing, and exited 0. All 68 pass — verified before anything was changed
— so this was 68 uncounted passes, not hidden failures. This is
`REPORT_HOST_BOUNDARY.md` §5's failure, live again at `b173190`. The prompt
treats 996/52 as the invariant to preserve; it was the number to interrogate.

**3b. And a third instance, in a place nothing had ever looked.**
`js/test/*.mjs` — **47 `node:test` tests** — were run by *nothing*: not
`scripts/ci.sh`, not any `test_js_*.py`, not any script. Found while removing
a dead host method whose remaining coverage lived there. Now in the gate.
Three instances of the same failure class in one build says the class is
structural, not incidental: **the gate counted what it ran, and nothing
counted what existed.** `scripts/run_suites.py` now warns when a suite file
reports no result.

**4. Correction 2's ruling was right, and its reasoning understated the
independence.** B, C and D are indeed mutually independent — but §161's
original rationale fails harder than Correction 2 says. It is not only that
`PlanesSyntaxError` has no `fix` field; Phase D ends up **removing** a message
rather than adding one, so there was never a clause needing a field to move
into.

**5. Correction 3 was right and is now demonstrable, not just arguable.** The
two conventions sit in one record and behave oppositely, asserted directly:
`when e is { fix }` binds on **every** error (`nothing` where none), and
`when e is { path }` does **not match** an error without a path. Reported as a
finding for the architect, not changed here.

**6. §158 and the prompt name a spelling the language does not have.**
`when e is { fix: f }:` is specified in §B.2 and in failure mode 4 as the
shape-matching read to assert. In Planes that is a **match** — it compares the
`fix` field against the value of a name `f` — and raises
`unknown-name: no name 'f' here`. The binding form is the bare
`when e is { fix }:` (`parser.py:1130`). The assertion the prompt wanted is
real and passes; the spelling in the prompt does not.

**And one the prompt got exactly right, worth recording because three of these
are corrections:** Correction 1 is confirmed in **all three** parsers, not
just `parser.py`. `fail { message: ..., fix: ... } as tag` already produced a
`Fail` node with a `RecordLit` message in `parser.py`, `js/parser.mjs` and
`grammar/parser.planes` before any change. No grammar moved, no reserved word
was spent, and the cost-of-a-word report §158 asks for as a fallback is not
owed.

### Smaller findings, recorded not fixed

* **The self-hosted parser had no fix clauses at all on this message.**
  `grammar/parser.planes`'s `read-effect-word` refused in one line where
  `parser.py` and `js/parser.mjs` gave a `valid kinds:` continuation. Nothing
  asserted it, because the self-hosted parser suites compare ASTs and error
  *tags*, not text. Closed for this message; **the other ~21 `fail` sites in
  `grammar/parser.planes` are still shorter than their reference twins** and
  are part of the 73 in §2.
* **Planes has exactly four escapes** (`\"` `\\` `\n` `\t`), so an em-dash in a
  self-hosted message is written as itself, not `—`. Discovered by the
  lexer refusing, in its own words, which is the refusal working.
* **`test_core_check.py` uses pytest's `tmp_path` fixture**, so the runner
  added for it supplies one rather than skipping those two tests — a runner
  that silently skipped a fixture case would reproduce finding 3 one level
  down.

---

## §6 — Invariants

| # | invariant | held |
|---|---|---|
| 1 | a message change and its regenerated artifact in one commit | yes — `grammar_gen.py --check` green at every commit |
| 2 | a behaviour change in all three implementations in one commit | yes — B and D each touch `interp.py`/`parser.py`, `js/*.mjs`, `grammar/*.planes` |
| 3 | counts stated after every phase | yes — only C moved one, deliberately, 8 → 7 |
| 4 | `errors_coverage.py` reports, never fails | yes — still `return 0` by construction |
| 5 | no test assertion weakened | yes — see below |
| 6 | no host exception escapes into a Planes program | yes — 348 shapes, three implementations, still zero |
| 7 | the language surface closed except where §158 opens it | yes — 32 / 10 / 7 unchanged; `fail`'s record form uses grammar that already existed |
| 8 | a count from the prompt is a lower bound to verify | yes — 528→3602, 52→54, 996→1085, 109 confirmed |

**On invariant 5.** Three assertions changed, none weakened:

* `test_fail.py`'s `"text of" in e.fix` — the message now names both accepted
  forms, and the assertion **gained** `"fail { message:" in e.fix`. The fix
  clause deliberately keeps "text of it" so the original assertion still holds.
* `test_host.py` / `test_js_host.py` / `js/test/host.test.mjs` — eight → seven,
  plus new assertions that `to_json` has **not** come back.
* The two JSON byte-identity tests moved from the dead wrapper to the live
  serialiser. Same cases, same comparison, better target.

`test_coverage.py`'s leak assertion is byte-for-byte the same claim; only the
*source of the observation* changed, and the new source watches the gate's real
run rather than a second synthetic one. An incomplete record fails loudly; a
`--fast` record downgrades to a printed "partial" note and never reads as full.

---

## §7 — Files

**Created:** `scripts/run_suites.py`, `scripts/verify_batch_equivalence.py`,
`scripts/verify_fast_follow.py`, `gate-timing-pre.md`, `gate-timing-post.md`,
`fast-follow-verification.md`, `REPORT_FAST_FOLLOW.md`.

**Modified:** `scripts/ci.sh`, `js/cli.mjs`, `interp.py`, `js/interp.mjs`,
`grammar/interp.planes`, `parser.py`, `js/parser.mjs`,
`grammar/parser.planes`, `host.py`, `js/host.mjs`, `js/host_node.mjs`,
`js/host_browser.mjs`, `errors_coverage.py`, `grammar/errors.json`,
`grammar/rules.json`, `grammar/vocabulary.planes`, `.gitignore`, and the
suites `test_builtin_guards.py`, `test_coverage.py`, `test_core_check.py`,
`test_interp_statements_in_planes.py`, `test_fail.py`, `test_foreign.py`,
`test_host.py`, `test_js_host.py`, `js/test/host.test.mjs`.

**Out of scope and untouched, as specified:** module resolution in the
self-hosted stack; `foreign-needs-host` (refusing is correct behaviour); the
JSON escape and non-ASCII limits; `why_tree`'s dedup; the absence of a suffix
operation. The list is what was in front of this build, not a closed
enumeration (v13.1 §154).
