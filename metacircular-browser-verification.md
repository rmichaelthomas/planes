# metacircular-browser — verification

Produced by `node --test js/test/meta_browser.test.mjs`, which the gate runs on every
invocation (`scripts/ci.sh`'s `js/test` step). **There is no `scripts/verify-*.mjs` for
this build** — the retirement rule gives a verification script two options when its
build merges, and Phase 1 of this sequence found that out the hard way, so the durable
form was written first and there is nothing to retire.

| group | assertion | result |
|---|---|---|
| A | A: lex — the page engine matches `node js/cli.mjs meta lex` | PASS |
| A | A: parse — the page engine matches `node js/cli.mjs meta parse` | PASS |
| A | A: run — the page engine matches `node js/cli.mjs meta run` | PASS |
| B | B: lex — direct and metacircular agree on all five programs | PASS |
| B | B: parse — direct and metacircular agree on all five programs | PASS |
| B | B: run — direct and metacircular agree on all five programs | PASS |
| — | the whole standalone corpus agrees, with only the documented exceptions | PASS |
| C | C: N programs issue one fetch per module, not N | PASS |
| C | C: the host resets between programs, so output does not bleed | PASS |
| D | D: stage load and per-program time are separate, and both are real | PASS |
| D | D: the ratio survives a coarsened clock, which a single-shot timing does not | PASS |
| E | E: interp.planes resolves its whole graph through the browser loader | PASS |
| E | E: `use file` and `use http` are builtin capability modules and fetch nothing | PASS |
| E | E: each stage loads only the graph it needs | PASS |
| — | the recursion ceiling is measurable both ways, and the second layer lowers it | PASS |
| F/A | F/A: comparing against the WRONG stage's Node output fails | PASS |
| F/B | F/B: a program whose two paths differ is reported as differing | PASS |
| F/C | F/C: a FRESH loader per program does refetch — so C's subject is real | PASS |
| F/D | F/D: the ratio is withheld when a side fails, rather than invented | PASS |
| F/E | F/E: a module that is genuinely absent fails the fetch, so E's loader is live | PASS |
| — | the 29-keyword core carries the metacircular stack in a browser too | PASS |
| — | STAGES names the file and entry function each stage is driven through | PASS |

**22/22 passing.**

Groups, per §N+3.2: **A** byte-identity with `node js/cli.mjs meta <stage>` · **B**
byte-identity direct vs metacircular · **C** stage reuse (one fetch per module, not per
program) · **D** the timing split, and that it survives a coarsened clock · **E** graph
resolution through the browser loader · **F** anti-vacuity, each group's subject broken
deliberately. The unlabelled rows are the corpus sweep, the recursion ceiling, the
core-restricted run, and the stage table itself.
