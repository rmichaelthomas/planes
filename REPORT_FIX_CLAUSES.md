# REPORT — The fix clause, kept in all three implementations

**Branch:** `feat/fix-clauses-manifest-and-the-mark`
**Base:** `main` at `bd7a7b5`

| | | |
|---|---|---|
| **1** | `16db116` | Every self-hosted error names its fix |
| **2** | `f60e9a4` | Retire MANIFEST.md |
| **3** | `1e94c6e` | The animated mark is generated, not hand-written |
| | `2715ddc` | The scanner tells `fix:` from `no-fix:` — a defect in Phase 1, §5.5 |

**Gate:** green, exit 0. **56 files, 56 reporting, 1114 oks**, 47 JS tests,
44.7 s wall, `mypy` 91 files, `ruff` clean. Counts **32 / 10 / 7 / 7**. Corpus
**50 / 50** self-hosted. `core_check` clean on all four `grammar/*.planes`.
348 shapes, **0 divergences on tag, detail and fix**.

**The commitment:**

| | before | after |
|---|---|---|
| reference (`interp.py` etc.) | 0 of 109 | **0 of 109** |
| self-hosted (`grammar/*.planes`) | 71 of 111 | **0 of 111** |

`errors name the fix` has stood since `unbound` v1.1 §22. It is now kept in all
three implementations.

---

## §1 — How the 71 actually split, against 15 / 38 / 18

C5 and C6 sized this by matching **sites** and produced *15 mechanical ports,
38 per-site reading decisions, 18 to author*. The prompt's §2.1 called that the
wrong instrument and named the right one. It was right, and the split came out
differently in a specific way.

| | sites | |
|---|---:|---|
| **named by the three-way sweep** | **25** | the sweep reported the divergence and printed both sides; nothing to decide |
| **the rest of `interp.planes`, from the catalogue** | **28** | the sweep does not exercise them; matched by tag *and detail template* against `grammar/errors.json` |
| **already carried a clause the scanner could not see** | **4** | 3 in `lexer.planes`, 1 in `parser.planes` — not missing, invisible |
| **written by hand** | **11** | 10 in `parser.planes`, 1 in `json.planes` |
| **marked a deliberate silence** | **3** | the parser's generic token gate |
| | **71** | |

Extending the sweep to compare `fix` reported **299 of 348 shapes divergent
across 24 distinct clauses**, and named both sides of every one. Porting those
closed 25 sites directly and, because the reference clause for a shape is the
clause for its whole family, closed the rest of `interp.planes` with it.

**What the 38 got wrong is not the count but the difficulty.** There genuinely
were per-site decisions in the 28 — `cannot-compare` alone has three different
reference clauses for three different branches of `equal()`, and picking the
right one per site is a judgment. But with the *detail template* in hand
alongside the tag, the judgment is a lookup: the detail says which branch it
is. C6's matcher keyed on tag and function and could not see the detail, which
is why it reported an unresolvable ambiguity that resolves on sight.

**And the 18 was three different things.** Four of them were never missing —
`lexer.planes` and one `parser.planes` site already named their fix inline on a
continuation line, exactly as the reference's syntax errors do, and the scanner
could not read that shape. Three more are deliberate silences. Eleven were real
authorship.

### Three shapes the scanner could not see, and none of them was a clause

The count could not have reached zero by writing clauses alone:

1. **`reraise` dropped the fix.** The adapter that turns a self-hosted fail
   status back into a host exception carried tag and detail and not the clause,
   so an error that named a fix stopped naming one the moment it crossed the
   value-returning boundary. `failure-of` builds §158's record form and the fix
   rides across with the detail. Without this the sweep could not have *seen* a
   self-hosted clause at all.
2. **A fix named through `fail`'s record form.** That is the only way a `fail`
   site can name one, and the scanner predated §158.
3. **A fix on a continuation line.** Every syntax error names its fix that way,
   because both implementations render one string and the two are asserted
   byte-identical. `classify()` has read exactly that shape on the *reference*
   side since C2; the self-hosted half had never learned it, including through
   the one helper the lexer composes its message in.

---

## §2 — The deliberate silences, and the reason each states

40 of 111. A pass, not a shortfall — §2.2's ruling, and no clause was invented
to drive a number down.

| shape | n | the reason it states |
|---|---:|---|
| bare-name re-raise — `fail d as tag` | **35** | the message belongs to whoever wrote it. 28 in `interp.planes` (22 of them `reraise`'s tag table), 7 in `parser.planes`'s amber and ambiguity re-raises. The language must not attach its advice to a sentence it did not write. |
| `error-no-fix-of` | **2** | `exec-fail` and `exec-fail-record`: *"the message is the program's own — `fail` names it, and the language must not attach its advice to a sentence it did not write."* The reference states the same reason at the same site. |
| `fail`'s record form with `no-fix:` | **3** | `expect-kind`, `expect-op`, `parse-when`: *"this is the generic token gate, reached from every form in the grammar; it knows which token was due and not what the author meant by writing another, so a call site that can say more passes its own clause and a call site that cannot says nothing rather than guessing."* Taken verbatim in substance from `parser.py`'s `no_fix` on its own twin. |

`error-no-fix-of` is the self-hosted counterpart of the reference's `no_fix=`.
Its `reason` is a literal at the raise site, is never rendered, and never
reaches the record a program reads — so the error record stays the four fields
C5 fixed it at. `fail`'s `no-fix:` field is ignored by all three interpreters
for the same reason, so the rendered message is unchanged.

---

## §3 — Phase 2: MANIFEST.md

Read before deleting. It held a file inventory — name, byte count, sha256 —
and a note about extracting `planes.tar.gz`, an archive not in the repo. **No
design statement, no rationale, no orientation a reader would lose**, so
nothing was folded into `README.md`; that is stated rather than assumed.

`README.md`'s own `## Files` table already does the orienting half — it says
what each load-bearing file is *for*, which a checksum table never did. One
sentence added there says so and points at `git ls-files`. No generator was
built.

It claimed 55 files and 217 tests against a repo with 56 suite files and 1114
oks. Nothing outside the historical `REPORT_*.md` referenced it.

---

## §4 — Phase 3: the mark

`render_logo.py` emits the animated icon from the same `PLANES` and `VIEWS` the
six SVGs come from. The six SVGs and the identity sheet **regenerate
byte-identical** to the ones handed over, which is the before/after check that
the generator is authoritative and this change moved nothing else; re-running
is idempotent.

**The duplication had already drifted**, which is the argument for the ruling
rather than against it. Three differences, all corrections toward the data the
static marks already use:

* the oblique plane was `rotateX(45deg) rotateY(45deg)`, which is **not** the
  basis `record` declares — that transform puts its local x at
  (0.71, 0.5, −0.5) where the data says (0.7071, 0, −0.7071). It is now a
  `matrix3d` change of basis from `u`, `v` and `u × v`, to four places, because
  two would round a direction cosine to a fifth of a degree of skew;
* the grid was 8.5 cells to the SVGs' six (`DIVISIONS`);
* the axis length and origin dot were near, not equal, to `AXIS / HALF` and
  `origin_r`.

The motion is not derived and was not touched: the 24 s linear spin, the −18°
tilt, the 800 px perspective are design decisions already made.

`OUT_DIR` defaults to the script's own directory so a bare run regenerates in
place; `PLANES_OUT` still overrides. `identity/` is excluded from `ruff`,
`mypy` and `coverage` by ruling.

---

## §5 — What this build disproved about this prompt

Recorded, with no recommendation attached, per §0.

### 5.1 — `identity/` is not invisible to the suites, and §4.1 said it would be

> *"the `.planes` globs are `grammar/`, `corpus/**`, `demo/`, `probe/` and the
> repo root, so a new top-level directory should be invisible to all of them"*

It is not. **Six suites glob `**/*.planes` recursively from the repo root**
(`test_js_interp`, `test_js_lexer`, `test_js_metacircular`, `test_js_parser`,
`test_js_shapes`, and `scripts/run_corpus_through_planes`), and `test_host.py`
walks the entire tree for `.py`, `.mjs` and `.planes`. `identity/` is reached by
all seven.

It is invisible in *effect* — because it holds no `.planes` file and no host
call — and not by construction. §4.1's own instruction to "verify rather than
assume" is what caught it. `test_host.py`'s walk now skips `identity/`
outright, and `test_gate.py` asserts the two facts the recursive globs depend
on, so invariant 7 holds by check rather than by luck.

### 5.2 — §2.1's correction was right, and understated its own reason

The prompt says the sweep matches behaviours where the catalogue matched sites,
and that behaviour is the thing that has to agree. True. But the sweep could
not have seen a single self-hosted fix clause before this build, because
`reraise` discarded it at the adapter boundary. The instrument was in the repo;
what it measured was not yet reaching it. Had the sweep been extended without
that fix, it would have reported all 348 shapes as agreeing on an empty clause
and named nothing.

### 5.3 — "expect step 2 to absorb most of the 38" was right for the wrong reason

Step 2 absorbed all of `interp.planes`, which is more than the 38. But the
sweep did not do it alone: it named 25 sites directly, and the other 28 were
closed by reading the catalogue's *detail templates*, which C6's matcher never
had. The absorbing instrument was the detail text, not the sweep as such — and
the detail text was in `grammar/errors.json` throughout the two builds that
called this work undecidable.

### 5.4 — The residue was smaller than 18 and not all of it was authorship

§2.1 predicted a residue "mostly `parser.planes` and `lexer.planes`". It was 18
sites, and only 11 were writing. Four already carried their clause and the
scanner could not read it — a measurement gap presented as a work item, which
is the same class of error C6 found in the definition-line miscount. Three were
deliberate silences whose reason the reference had already written down at the
matching site.

### 5.5 — This build shipped a defect in its own measurement and caught it in the report

Phase 1's scanner change tested `\bfix:` to recognise §158's record form. `\b`
matches inside `no-fix:` — the hyphen is a non-word character — so the three
generic-token-gate sites Phase 1 had just marked as deliberate silences were
counted as naming a fix. The work list read 0 either way, which is why the gate
stayed green and why it took *measuring the silences for §2 of this report* to
find it. Fixed in `2715ddc`; the split moved 74/37 to **71/40**.

The general lesson is the narrow one: a total that is correct does not mean the
buckets under it are, and a report that only restates the total will not find
out.

### Smaller things, recorded

* **`README.md` is stale** in the same way `MANIFEST.md` was: it opens "29
  reserved words" (32), "45 tests" (1114 oks), "No design documents", and its
  `## Files` table names test counts from many builds ago. The gate is green
  and no program is wrong, so it is recorded here and not touched.
* **`pyproject.toml`'s coverage `omit` listed `verify_*.py`**, which C6 deleted
  one build ago. Replaced with `identity/*` while editing the same block.
* **C5 and C6's split machinery now describes an empty set.** It is kept, not
  deleted: a new self-hosted raise site arriving without a clause lands back on
  the work list and it partitions it again. Its twelve pinned assertions are
  replaced by eight asserting the endpoint, and 0 of 111 is the stricter claim
  than 71 and its partition.
* **`grammar/errors.json` needed no regeneration.** `grammar_gen --check` is
  clean, so no reference-side message moved — the prediction in §2.3 held.

---

## §6 — Invariants

| # | | |
|---|---|---|
| 1 | counts 32 / 10 / 7 / 7 after every phase | **held** |
| 2 | reference catalogue 0 of 109 | **held** |
| 3 | 348 shapes, 0 divergences on tag, detail and fix | **held** |
| 4 | `errors_coverage.py` reports and never fails | **held** |
| 5 | no assertion weakened; extensions allowed | **held** — the sweep gained a field; C5/C6's split assertions were replaced by the stricter endpoint, and that replacement is named in §5's smaller things rather than left to be noticed |
| 6 | no new open question, no successor build, no next steps | **held** |
| 7 | `identity/` outside the gate, nothing in it a gate dependency | **held** — and checked rather than assumed, see §5.1 |

---

## §7 — Files

**Phase 1** — `grammar/interp.planes`, `grammar/parser.planes`,
`grammar/lexer.planes`, `grammar/json.planes`, `errors_coverage.py`,
`test_builtin_guards.py`, `test_error_messages.py`.

**Phase 2** — `README.md`; deleted `MANIFEST.md`.

**Phase 3** — `identity/` (new: `render_logo.py`, six SVGs, the identity sheet,
the generated animated mark), `pyproject.toml`, `test_gate.py`, `test_host.py`.

No reserved word, builtin, effect kind or host method was added or removed. No
reference-side message changed.
