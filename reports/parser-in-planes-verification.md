# parser-in-planes-verification.md

**Build:** feat/parser-finished (S3a), Phase 4
**Method:** `scripts/parser_corpus_agreement.py` — for every corpus file,
`parser.py`'s real `parse()` and `grammar/parser.planes`'s
`canonical-of-program-source` are each run, and their canonical AST text
forms (test_parser_in_planes.py's harness, proven agreeing on a hand-built
fixture in Phase 1) are compared. **PASS** means the two canonical forms
are byte-identical. Nothing is changed by running this script; it only
measures.

The canonical form was completed to be **fully structural** in this build:
every AST node kind expands field by field on both sides. Before, a node
kind absent from the harness's `AST_NODE_TYPES` was rendered by Python's
`str(node)` — its dataclass repr — when it appeared as a field value, which
another implementation cannot reproduce (Python's repr even switches quote
style around an embedded apostrophe). With `RecordUpdate`, `OrFail`,
`When`, `Rule`, `Foreign`, `WriteTo`, `Why`, `Fail`, `Note`, and `Because`
added, and the tuple-valued fields (`When.pattern` matchers, `Foreign.effects`
targets) rendered structurally, agreement is now a property of the two ASTs
and not of Python's repr.

## Result: 31 PASS, 0 PARTIAL, 0 FAIL, out of 31 — **full agreement**

Every corpus file's AST from `grammar/parser.planes` is byte-identical to
`parser.py`'s. The progression across S3a's phases:

| After phase | PASS / 31 | What it added |
|---|---|---|
| Baseline (b2e5973) | 4 | — |
| Phase 1 (cursor on `rest of xs`) | 4 | cursor no longer construction-bound; `status_threading.planes` moved off the `unreverse` ceiling |
| Phase 2 (`known_funcs` + amber) | 11 | juxtaposition and multi-word calls resolve; the four amber sites |
| Phase 4 (remaining statement forms) | 31 | `write`, `foreign`, `rule`, `note`, `when`, `why`, `fail`, the `because`/`with`/`or fail` trailers, for-each-as-expression, and the bare-expression-statement fallthrough |

**`demo/app/net.planes`** is the one file that cannot be parsed standalone:
it calls `api base`, a multi-word function defined in its sibling
`config.planes`, and without the name table both parsers read `api base`
as a syntax error at the same point (`parser.py`: `expected ), found 'base'`;
`parser.planes`: `expected ')', found 'base'` — the identical stop, not a
disagreement). The harness resolves this by scanning the file's `use`d
sibling modules for their defined names and passing that cross-file `known`
mapping — the same table the module system supplies — identically to both
parsers (`cross_file_known` in the agreement script; `parse(src, known)` on
the Python side, `canonical-of-program-source-with-known` on the Planes
side). Given the same module context, the two agree on the full AST.

## Every Phase 4 disagreement, classified

Each file that failed before Phase 4 was classified before it was fixed. No
disagreement turned out to be a genuine difference in what the two
implementations consider the same AST — every one was a construct
`grammar/parser.planes` did not yet parse (a language-surface gap, closable
with existing keywords, no new keyword/builtin/effect/host), or the
cross-file `known` methodology point above. None was a bug in the shared
canonical form's meaning.

| Construct that was missing | Files it blocked | Resolution |
|---|---|---|
| `write … to …` (`WriteTo`) | `money`, `ordinary`, `cachelib`, `v1`, `v2`, `hn`, `pypi`, `rules/*` | ported `parse_write` + trailing `or fail` |
| for-each-as-expression | `gate`, `ordinary`, `hn` | `parse_foreach` as_expr path in `parse-primary` |
| `because` trailer | `annotated`, `gate`, `money`, `hn`, `rules/exception` | `parse_because`, attaching a `Because` via `with` |
| keyword-as-field-name (`{ first: … }`) | `gate` | `is-field-name-kind` in record/pattern fields |
| bare-expression statement | `clash/main`, `rename/main`, `v1`, `v2`, `main` calls | `parse_statement` fallthrough to `parse_expr` |
| `foreign` declaration | `foreign`, `fdiff/v1`, `fdiff/v2` | `parse_foreign` + `read_claim` + effect filtering |
| `rule` statement | `annotated`, `rules/clean`, `rules/violation`, `rules/exception` | `parse_rule` (may/may not, `to`, `supersedes`, `@fp`) |
| `note:` block | `annotated`, `rules/exception` | `parse_note` + `parse_note_entry` |
| `when` dispatch | `status_threading` | `parse_when` + pattern (match / bind) entries |
| `with` (RecordUpdate), `or fail` (OrFail) | `rename/main`, `hn`, `pypi`, `status_threading` | `trailing_with` / `trailing_or_fail` in `parse_expr` |

## Self-parsing — the second bootstrap assertion

`grammar/parser.planes` was run over its own source and over
`grammar/lexer.planes` and `grammar/vocabulary.planes`, each checked against
`parser.py` (with the same cross-file `known`).

- **`grammar/lexer.planes` — AGREES.** A 564-line, 156 046-character
  canonical form, byte-identical between the two parsers. A Planes parser
  parsing the Planes lexer.
- **`grammar/vocabulary.planes` — AGREES.**
- **`grammar/parser.planes` — AGREES.** A 748 255-character canonical form,
  byte-identical. A Planes parser parsing the Planes parser — the second
  closed bootstrap assertion in this domain, after lexer self-tokenization.
  Getting here required flattening this file's own deepest dispatch chains
  (`canonical-of-node`, `parse-statement`, `parse-primary`, `digit-value`)
  from nested `when`/`else` ladders into flat `if … give` sequences: the
  nested form was deep enough that *parsing it* exceeded the recursion
  ceiling (ruling A.6 — a recursion-too-deep is a design bug in the code,
  fixed, not a ceiling to raise), and one further bug surfaced only here — a
  parenthesised expression used `parse-or`, not `parse-expr`, so `(x with …)`
  inside parentheses did not parse. Both were fixed; corpus agreement stayed
  at 31/31 throughout, and the flat dispatch also drops the per-dispatch
  frames the nested form spent at run time.
