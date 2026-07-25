# CORE_SUBSET.md — the port surface for self-hosting

**Status: a proposal, not a ruling.** It goes to the architect. Checkpoint
v10.0 §127's obligation is to derive the core — the subset of Planes that
`interp.planes` will be written in, and therefore the subset a second host
must implement to run it — *from evidence, not taste*. Every member below
names a program that cannot be written without it. Every non-member names the
evidence that it went unused.

The evidence base is the two largest Planes programs in existence,
`grammar/lexer.planes` (564 lines, 52 functions) and `grammar/parser.planes`
(1118 lines, 98 functions), inventoried mechanically by
`probe/selfhost/phase6_inventory.py` (tokenized with the language's own
`lexer.tokenize`, not eyeballed — transcript at
`probe/selfhost/transcripts/phase6_inventory.txt`), plus what Phases 1–5 of
`PROBE_SELFHOST.md` show `interp.planes` needs beyond what the lexer and
parser needed.

---

## 1. The proposed core

Each member lists a justifying program: one that cannot be written without it.
Counts are combined token occurrences across the two grammar programs.

### 1.1 Constructs (syntax)

| Member | Used | Justifying program — cannot be written without it |
|---|---|---|
| function def `to NAME of p: … give` | to 150, give 304 | `grammar/parser.planes` — recursive descent is functions calling functions |
| function call `NAME of args` (`of`) | of 577 | every program; `of` is the single most-used word in the language |
| assignment `NAME = expr` | pervasive | every function body binds intermediate results |
| `if / else` | if 126, else 166 | `grammar/lexer.planes` per-character classification |
| shape dispatch `when subj is { … } / else` | when 44, is 46 | `grammar/parser.planes` node dispatch; **`interp.planes`'s `eval` (Phase 2)** — the *only* substitute for the absent `isinstance` |
| bounded iteration `for each x in xs [where c]` | for/each 18, in 19, where 3 | the association-idiom env lookup (Phase 1); every token/list walk |
| record literal `{ f: v, … }` | 270 `{` | tokens, AST nodes, and closures-as-data (Phase 5) are all records |
| list literal `[ … ]` + `plus` | `[` 26, plus 38 | the token stream; the association-list environment (Phase 1) |
| field access `.name` | pervasive | `token.kind`, `node.left`, `entry.value` — every record read |
| operators `+ - * / < > <= >= == != in` | in 19, arith/compare pervasive | position arithmetic in the lexer; every comparison in dispatch |
| boolean `and / or / not` | and 28, or 51, not 3 | compound guards in `parse_*` |
| literals: number, string, `true`/`false`, `nothing` | true 17, false 25, nothing 6 | everywhere; `nothing` is the "no result" of a failed scan |
| recursion (self-call via `to`/`give`) | — | `grammar/parser.planes`; **`interp.planes`'s `eval`, and the fixpoint (Phase 4)** |
| error handling `or fail as tag: …` | fail 10, as 10 | `grammar/parser.planes` error recovery; the interpreter's own guarded evaluation |
| module use `use NAME` (+ `from`) | use 2, from 2 | `grammar/lexer.planes` reads its tables via `use vocabulary` |

### 1.2 Builtins

| Member | Used | Justifying program |
|---|---|---|
| `text of` | 116 | `grammar/parser.planes` renders each AST node to canonical text |
| `count of` | 13 | list/string lengths; the fixpoint's convergence test (Phase 4) is `count of grown == count of reached` |

`upper of` appears **once** (parser.planes) — by §127 obligation 4 ("a
construct appearing once for convenience is not core"), it is a convenience,
not core. Listed here as a borderline the architect should rule on.

### 1.3 The one addition Phases 1–5 make beyond the lexer/parser core

| Member | Status | Justifying program |
|---|---|---|
| record update `with` | **borderline — see §4** | measured for rebinding at env scale (Phase 1); but the two grammar programs use it **zero** times, threading state by constructing fresh record literals instead |

Everything else Phases 1–5 require — records, recursion, `for each`, the
association idiom, `when…is`, closures-as-data — is already in §1.1. Phase 5's
central result is that `interp.planes` needs **no new construct** to represent
user functions: an inert `{ param, body, env }` record applied by
interpretation is built entirely from members already in the core
(`probe/selfhost/phase5_closures_as_data.planes` proves it end to end).

---

## 2. Not core — with the evidence

`probe/selfhost/phase6_inventory.py` found these **unused** across all 1682
lines of the two grammar programs (or used only as documentation):

| Non-member | Evidence | §127 predicted? |
|---|---|---|
| `let` | 0 keyword uses — plain `=` suffices everywhere | — |
| `show`, `write` | 0 uses — the grammar programs are pure functions; **effects are the host's job, not the interpreter's** | — |
| `why` | 0 uses — provenance query is a tool, not a language primitive |
| `round`, `places` | 0 uses | — |
| `foreign`, `doing` | 0 uses — the grammar programs are pure Planes | **yes** |
| `rule` | 0 uses | **yes** |
| `note:` / `because:` | `note:` appears 2× — both are file-header docstrings, identical behaviour with or without them; `because` 0× | **yes** |
| the record plane (§95–102 boundary-crossing Record/Anchor/`maybe_record`) | a runtime `record=` toggle, never a syntax token — nothing to reproduce in a v1 interpreter | **yes** |
| builtins `lower`, `whole`, `ask`, `read`, `normalize` | 0–0 uses | — |
| all 7 effect kinds (`ask read write show clock random env`) | 0 uses — no effect crosses a boundary in either program | — |
| positional `may`, `supersedes`, `derives-from` | 0 uses | — |

**§127's prediction is CONFIRMED, not refuted.** The four items it named —
the `note:`/`because:` planes, the record plane, `rule`, and `foreign` — are
each either unused or used only as documentation. Nothing in the inventory
forces any of them into the core.

One caution on wording: §127's "record plane" is the **provenance-recording
subsystem** (§95–102: `Record`, `Anchor`, `maybe_record`, the `record=`
toggle), which is correctly not core. It must not be confused with **record
literals** `{ … }`, which are the single most-used data construct (270
occurrences) and are unambiguously core. The prediction is about the former.

---

## 3. How much smaller is the core than the language

The full surface is **32 keywords / 8 builtins / 7 effect kinds** (+ 6
positional words) = 53 named elements.

The proposed core is roughly **~18 keywords / 2 builtins / 0 effect kinds**,
plus records, lists, operators, and literals — on the order of **half** the
named surface, and **none** of the effect surface. A second host that
implements the core can run `interp.planes`; it need implement no effect kind,
no `foreign` boundary, no record plane, no `rule`/`note`/`because`
annotations, and no `why` provenance to do so. Effects re-enter only at the
host beneath `interp.planes`, exactly where they enter beneath `interp.py`
today.

---

## 4. The open question for the architect: `with`

`with` is the one place evidence and Phases 1–5 disagree.

- **Phases 1 measured it** as a rebinding primitive and found it cheap (~4 µs,
  flat to 500 fields — `probe/selfhost/transcripts/phase1_env_lookup.txt`).
- **The two largest programs never use it.** `grammar/lexer.planes` threads
  its lexer state forward by writing a fresh record literal at every step
  (`give { out: state.out plus tok, pending: { kind: "none" }, line: state.line }`),
  never `state with out: …`.

So `with` is not *forced* by any program that exists. It is forced only if
`interp.planes` chooses record-update over fresh-record-construction for
threading the environment forward — and the association-idiom environment is a
**list**, rebuilt with `plus`, not a record updated with `with`. On current
evidence `with` may be a convenience the core can omit. **The architect should
rule**: include `with` for interpreter ergonomics, or hold the core to what
the grammar programs proved and let `interp.planes` construct fresh records.

---

## 5. Sketch of the core-conformance checker (sketch only — not built)

Modelled on `audit_locked_vs_built.py`, which confirms every *locked* construct
has code evidence. The core checker inverts that: it confirms `interp.planes`
uses *nothing outside* the ruled core.

```
# core_check.py  (SKETCH — do not build in this probe)
CORE = load("grammar/core.json")        # the ruled core, once §1 is a ruling
toks = lexer.tokenize(open("interp.planes").read())
violations = []
for t in toks:
    if t.kind is a keyword-token and t.value not in CORE.keywords:
        violations.append((t.line, "keyword", t.value))
    if t.kind == "NAME" and t.value in ALL_BUILTINS and t.value not in CORE.builtins:
        violations.append((t.line, "builtin", t.value))
    if t.kind == "NAME" and t.value in EFFECT_KINDS:
        violations.append((t.line, "effect-kind", t.value))
exit(1 if violations else 0)   # print each: interp.planes:LINE uses non-core X
```

It reuses the language's own `lexer.tokenize` (so the checker and the language
never disagree about what a token is), reads the core from a single JSON source
of truth (as `grammar/vocabulary.json` is the source of truth for the full
surface), and fails closed. Building it is out of scope for this probe by §6
step 6; it waits on §1 becoming a ruling.

---

## 6. One-paragraph summary

The core is about half the named language and none of its effects. Everything
`grammar/lexer.planes` and `grammar/parser.planes` needed across 1682 lines is
a compact set — functions, records, lists, `if`, `when…is`, `for each`,
recursion, `or fail`, `text`/`count`, and the operators — and Phases 1–5 add
essentially nothing to it except a single borderline (`with`). §127's four
predicted non-core items are all confirmed unused. The surprising part is not
what is in the core but how much of the language sits outside it: every effect
kind, the entire record (provenance) plane, `foreign`, `rule`, the annotation
planes, `why`, and five of eight builtins are absent from the two largest real
programs and unneeded by the interpreter that must run on them.
