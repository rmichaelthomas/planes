# Error Message Audit — `~/fixaudit/answers.json` against the raise sites

Scope: score Codex's 60 answers against the actual raise sites in this repo.
No message text changed by this pass — it produces a report only.

## The files didn't line up positionally, and that had to be fixed before scoring

`~/fixaudit/messages.json` is `grammar/errors.json` (119 raw entries, current
HEAD) deduplicated by `(tag, template, fix)`, with every null-template entry
("message assembled elsewhere") pushed to the *end* of the list rather than
kept in source order — reproduced exactly, all 114 entries, by dedeuping
`grammar/errors.json` myself and diffing byte-for-byte against the supplied
file (0 mismatches, sites included).

`~/fixaudit/answers.json` has 60 entries, numbered 1–60. Naively, entry *N*
looks like it should be `messages.json`'s *N*th entry — and for entries 1–26
it is. From entry 27 on, the positional read is wrong. Three tags —
`no-such-file`, `bad-foreign-target`, `needs-rounding` — currently have a
null template (their message is assembled from a bare value, not a literal),
so today's generator sorts them to positions 105–107. But their **fix text**
still shows up mid-batch, verbatim, in three answers that have nothing to do
with position 105–107:

- answer 27 ("Correct the path or write the file before reading it.") is
  `msg-105`'s fix (`check the path, or write it first`) word-for-word.
- answer 46 ("Rewrite the foreign target in the form shown by the host
  hint...") is `msg-106`'s fix (`write it as {self.host.target_hint()}`)
  word-for-word.
- answer 55 ("Round the intermediate value, for example `round x to 6
  places`.") is `msg-107`'s fix word-for-word.

Reading the batch as **the first 60 raise sites in `interp.py`'s own source
order** (plus 4 `lexer.py`/`parser.py` grammar-loading sites at the tail) — the
order these three sites were in *before* they were refactored to assembled
messages — every one of the 60 answers matches its target's fix text
verbatim or near-verbatim. That is the mapping used below. The 54
`messages.json` entries this batch never covered (58–104, 108–114 in current
numbering — mostly parser/lexer syntax errors and `rules.py` messages) are
out of scope for this report, not silently skipped.

| answer # | true `messages.json` id | tag |
|---|---|---|
| 1–26 | msg-001 – msg-026 | (positional) |
| 27 | **msg-105** | no-such-file |
| 28–45 | msg-027 – msg-044 | (shifted −1) |
| 46 | **msg-106** | bad-foreign-target |
| 47–54 | msg-045 – msg-052 | (shifted −2) |
| 55 | **msg-107** | needs-rounding |
| 56–60 | msg-053 – msg-057 | (shifted −3) |

## Two raise sites this audit found are effectively unreachable in production

Not a scoring dimension in the rubric below, but load-bearing for reading it:
`ask` and `read` are the only two effect builtins whose host-error handling
doesn't actually catch what the real host raises.

`interp.py:1007` (`read`) and `interp.py:980` (`ask`) both do `except
HostError:` only. `PythonHost.read`/`PythonHost.ask` (`host.py:120,114`) call
`open()`/`urlopen()` directly and wrap nothing — `TestHost` is the only host
that actually raises `HostError` here. Verified directly against this repo's
`Interpreter`:

```
$ python3 -c "from interp import Interpreter; Interpreter().run(
    'use file\nlet x = read \"/tmp/does-not-exist-xyz.txt\"')"
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/does-not-exist-xyz.txt'

$ python3 -c "from interp import Interpreter; Interpreter().run(
    'use http\nlet x = ask \"http://does-not-exist.invalid/\"')"
URLError: <urlopen error [Errno 8] nodename nor servname provided, or not known>
```

Neither is a `PlanesError`. A real program that reads a missing file or asks
an unreachable URL never sees `no-such-file` or `ask-failed` at all — it
crashes with a raw Python traceback. `test_host.py` only ever exercises these
two tags through `TestHost`; `test_js_host.py:198`'s comment ("its HostError
surfaces as no-such-file at the interp layer") is simply wrong about
`PythonHost`, and the same test's own `except (FileNotFoundError, OSError)`
three lines below it is the tell. `write` (`interp.py:838`) does not have
this gap — it catches `(HostError, OSError)` and is reachable through the
real host (verified: writing to a nonexistent directory correctly raises
`write-failed`).

This affects entries 25 and 27 below (`edit_correct: partly` — the stated
fix is right for the one situation that can actually reach it, but that
situation is a test forgetting to stub a response/file, not the real-world
scenario the message describes).

## Per-answer table

`multi_intent` names distinct *programmer intents* that reach the same raise
site — not just different wrong-value types under one intent (e.g. "arg was
a number, a list, or nothing" under one `not-a-collection` guard is one
intent with three wrong inputs, not three intents).

| # | tag | site(s) | edit_correct | misdirects | multi_intent |
|---|---|---|---|---|---|
| 1 | cannot-compare | interp.py:81 | partly | **yes** | absence-check vs. `nothing` nested inside a compared list/record |
| 2 | cannot-compare | interp.py:91 | yes | no | type-confusion bug vs. treating a number as falsy/truthy |
| 3 | cannot-compare | interp.py:100, interp.py:1475 | partly | **yes** | `==` cross-type scalar mismatch vs. `==` list-vs-record mismatch vs. `<`/`>` ordering attempt on unorderable values |
| 4 | cannot-compare | interp.py:119 | yes | no | field-name typo vs. wanting a partial/subset comparison |
| 5 | not-a-yes-no | interp.py:134 | yes | **yes** (mild) | `if` truthiness assumption vs. `and`/`or`/`not` operand vs. `for each...where` clause |
| 6 | not-text | interp.py:157 | yes | no | no |
| 7 | not-text | interp.py:172 | yes | no | wrong-type write destination vs. url vs. read path |
| 8 | unrecognized-record-format | interp.py:322 | yes | **yes** (mild) | record is stale (older) vs. reader is stale (interpreter older than the record) |
| 9 | unknown-name | interp.py:372 | yes | no | no |
| 10 | discarded-write | interp.py:502 | yes | no | no |
| 11 | annotation-executed | interp.py:596 | yes | no | no (interpreter defect, not a program mistake) |
| 12 | not-a-record | interp.py:665 | yes | no | no |
| 13 | fail-message-not-text | interp.py:710 | yes | no | no |
| 14 | fail-message-not-text | interp.py:716 | yes | no | no |
| 15 | not-a-record | interp.py:766 | yes | no | no |
| 16 | not-a-list | interp.py:778 | yes | no | no |
| 17 | not-a-record | interp.py:802 | yes | no | no |
| 18 | not-a-number | interp.py:819 | yes | no | no |
| 19 | module-not-used | interp.py:830 | yes | no | no |
| 20 | write-failed | interp.py:842 | partly | **yes** (mild) | no (one intent — write a file — several unnamed OS-level causes) |
| 21 | cannot-evaluate | interp.py:912 | yes | no | no (interpreter defect) |
| 22 | not-a-number | interp.py:945 | yes | no | no |
| 23 | not-a-collection | interp.py:951 | yes | no | no |
| 24 | module-not-used | interp.py:973 | yes | no | no |
| 25 | ask-failed | interp.py:985 | partly | no* | test forgot to stub a response (the only reachable case) vs. a real unreachable/misspelled URL (never reaches this message — see above) |
| 26 | module-not-used | interp.py:1000 | yes | no | no |
| 27 | no-such-file | interp.py:1008 | partly | no* | `TestHost` missing-file simulation (the only reachable case) vs. a real missing file (never reaches this message — see above) |
| 28 | not-a-collection | interp.py:1022 | yes | no | no |
| 29 | not-a-number | interp.py:1038 | yes | no | numeric-looking text (fix: use `number of`) vs. fundamentally non-numeric type (fix: restructure) — both named correctly |
| 30 | not-text | interp.py:1054 | yes | no | already a number (no conversion needed) vs. non-text, non-number type — both named correctly |
| 31 | not-a-number | interp.py:1063 | yes | no | no |
| 32 | not-a-number | interp.py:1070 | yes | no | no |
| 33 | not-a-number | interp.py:1085 | yes | no | numeric-looking text vs. wrong type — fix names neither the sibling `whole`/`number` guards do (see note below) |
| 34 | cannot-join | interp.py:1106 | yes | no | no |
| 35 | cannot-join | interp.py:1112 | yes | no | no |
| 36 | not-a-list | interp.py:1126 | yes | no | no |
| 37 | not-a-list | interp.py:1131 | yes | no | no |
| 38 | empty-list | interp.py:1136 | yes | no | no |
| 39 | unknown-builtin | interp.py:1143 | yes | no | no (interpreter defect) |
| 40 | not-a-collection | interp.py:1164 | yes | no | no |
| 41 | wrong-arity | interp.py:1190 | yes | no | no |
| 42 | unknown-function | interp.py:1208 | yes | no | no |
| 43 | wrong-arity | interp.py:1224 | yes | no | no |
| 44 | recursion-too-deep | interp.py:1250 | partly | **yes** | recursion over a collection vs. plain numeric recursion (no collection exists to convert to `for each`) vs. nested/tree recursion |
| 45 | wrong-arity | interp.py:1269 | yes | no | no |
| 46 | bad-foreign-target | interp.py:1284 | yes | no | no |
| 47 | foreign-not-found | interp.py:1287 | yes | no | module not installed vs. module installed, name misspelled — both named |
| 48 | foreign-failed | interp.py:1319 | yes | no | any exception a host function can raise — open-ended, but the advice (handle it explicitly) is the only sound general answer |
| 49 | cannot-combine | interp.py:1339 | partly | **yes** | text+number string-building (fix works) vs. text/number arithmetic-from-text (fix works) vs. a list or record on either side (neither suggested conversion produces a meaningful result) |
| 50 | divided-by-zero | interp.py:1348 | yes | no | no |
| 51 | unknown-operator | interp.py:1358 | yes | no | no (interpreter defect) |
| 52 | not-text | interp.py:1410 | partly | **yes** (mild) | number/yes-no/nothing on the left (fix works) vs. a list or record on the left (`text of` gives an opaque placeholder, not content) |
| 53 | not-a-collection | interp.py:1423 | yes | no | no |
| 54 | not-a-number | interp.py:1432 | yes | no | no |
| 55 | needs-rounding | interp.py:1443 | yes | no | no |
| 56 | unknown-operator | interp.py:1446 | yes | no | no (interpreter defect) |
| 57 | grammar-data-missing | lexer.py:82, parser.py:47 | yes | no | no (installation defect, not a program mistake) |
| 58 | grammar-data-missing | lexer.py:90, parser.py:53 | yes | no | no |
| 59 | grammar-data-missing | lexer.py:96 | yes | **yes** (mild) | no (same stale-side ambiguity as #8) |
| 60 | grammar-data-missing | lexer.py:102 | yes | no | no |

\* Not scored `misdirects` because the *stated* fix is accurate for the one
situation that can reach it — the defect is that the situation the message
*describes* (a real missing file, a real unreachable URL) never reaches it
at all. See the reachability section above.

## Totals

- **edit_correct**: 52 yes / 8 partly / 0 no — partly at #1, #3, #20, #25,
  #27, #44, #49, #52.
- **misdirects**: 9 yes (#1, #3, #5, #8, #20, #44, #49, #52, #59) / 51 no.
- **multi_intent**: 17 yes (#1, #2, #3, #4, #5, #7, #8, #25, #27, #29, #30,
  #33, #44, #47, #48, #49, #52) / 43 no.
- Two reachability defects found (not a rubric dimension): `ask` and `read`
  swallow the real host's own exceptions instead of the ones their
  `except HostError` clause catches (#25, #27).

## Every `misdirects: yes` case, quoted in full

### #1 — `cannot-compare`, `interp.py:81`

> **fix as written:** "test for absence with `is nothing`"

This is the whole fix, unconditionally, for every site `equal()` raises this
from — including the two recursive calls at `interp.py:113` (list elements)
and `interp.py:125` (record fields), which carry a `path` naming exactly
which nested slot was `nothing`. `is nothing` can't be substituted for the
*outer* comparison when the mismatch is three levels deep in a list of
records — the outer values aren't `nothing`, one of their contents is.

**Corrected clause:** "test for absence with `is nothing` — if the
comparison is between two lists or records and only fails on a nested slot
(the error's `path` names it), test that inner value with `is nothing`
directly rather than rewriting the whole comparison."

### #3 — `cannot-compare`, `interp.py:100` (via `equal`) and `interp.py:1475` (via `compare`)

> **fix as written:** "compare numbers with numbers, or text with text"

Verified directly:

```
>>> Interpreter().run('show [1] == { a: 1 }')
cannot-compare: cannot compare [1 items] with {record}
  try: compare numbers with numbers, or text with text
>>> Interpreter().run('show [1,2] == [1,2]')
true   # same-type list/list is fine — the fix's premise that only numbers
         # and text are ever comparable is simply false for `==`
```

For the `equal()` site the fix omits two entire valid comparisons (list with
list, record with record) and gives no hint that the actual problem here is
a *list compared against a record*, nothing to do with numbers or text. For
the `compare()` site (`<`/`>`/`<=`/`>=`), the identical fix text is fully
accurate — only numbers and text can be ordered at all, confirmed:
`[1] < [2]` raises the same message even though both sides are lists of the
same type.

**Corrected clause (equal/`==`):** "compare same-kind values — numbers with
numbers, text with text, lists with lists (compared element-by-element), or
records with records (compared field-by-field)."
**Corrected clause (compare/`<` `>` `<=` `>=`):** unchanged — "compare
numbers with numbers, or text with text" is already correct here; lists,
records, yes/no values, and `nothing` can never be ordered, same-typed or
not.

### #5 — `not-a-yes-no`, `interp.py:134`

> **fix as written:** "compare it: `if count of items > 0:`"

`condition()` is called from five distinct call sites: `if` (twice, `exec_stmt`
and `eval`), `and`/`or` operands (`eval_binop`), `not` (`eval`'s `Not` case),
and `for each ... where` (`eval_foreach`). The illustrated fix is literally an
`if` statement; a `where`-clause or `and`/`or`-operand failure gets the same
text even though `if count of items > 0:` isn't the syntax in play there.

**Corrected clause:** "compare it against something explicit rather than a
bare value — e.g. `if count of items > 0:` for an `if`, `x > 0 and y` for an
`and`/`or` operand, or `for each x in xs where x > 0:` for a `where` clause."

### #8 — `unrecognized-record-format`, `interp.py:322`

> **fix as written:** "regenerate the record with a matching version of planes"

The check is `version != RECORD_FORMAT_VERSION` — symmetric. It reads as
"your record is stale," but a record from a *newer* planes than the reader
hits the identical message, and there "regenerate the record" is backwards
advice; the reader needs upgrading, not the record. (`RECORD_FORMAT_VERSION`
has only ever been `1`, so this is a currently-unreachable direction, not a
live one — worth naming since the guard is written to catch it either way.)

**Corrected clause:** "regenerate the record with a version of planes
matching this interpreter's record format — if the record is newer than
what this interpreter reads, upgrade planes instead of regenerating the
record."

### #20 — `write-failed`, `interp.py:842`

> **fix as written:** "check the directory exists and is writable"

The catch is `except (HostError, OSError) as e:` — any `OSError`, not just
`ENOENT`/`EACCES`. A full disk, or a destination that already exists as a
directory, hits this exact message and fix, and neither is a missing or
unwritable *directory*.

**Corrected clause:** "check the directory exists and is writable — `{e}`
in the message names the actual OS error if it's something else, such as no
space left on the device or the destination already existing as a
directory."

### #44 — `recursion-too-deep`, `interp.py:1250`

> **fix as written:** "replace per-item recursion with one `for each` pass
> over the whole collection, threading a state record forward; for nested
> structure, track depth with a cons-list stack sized to nesting depth, not
> item count"

Verified directly — plain numeric recursion with no collection anywhere in
the program hits this same message:

```
to countdown of n:
  if n <= 0:
    give 0
  else:
    give countdown of n - 1

show countdown of 5000
→ recursion-too-deep: 'countdown' recursed past the depth this interpreter can follow
```

There is no collection to run a `for each` pass over here, and Planes has no
builtin that manufactures one (`grammar/vocabulary.json`'s 12 builtins have
no range/sequence generator) — the fix's rewrite doesn't apply to this
entire class of recursive program.

**Corrected clause:** "if recursing over a collection, replace it with one
`for each` pass threading a state record forward (or a cons-list stack for
nested structure); if recursing on a plain number with no collection
involved, `for each` has nothing to iterate over — restructure the
computation to avoid unbounded recursion depth instead."

### #49 — `cannot-combine`, `interp.py:1339`

> **fix as written:** "convert first — text of n to build text, or number
> of t to do arithmetic"

Verified directly:

```
>>> Interpreter().run('show "Count: " + [1,2,3]')
cannot-combine: cannot combine "Count: " with [3 items] using +
  try: convert first — text of n to build text, or number of t to do arithmetic
>>> Interpreter().run('show [1,2] + 5')
cannot-combine: cannot combine [2 items] with 5 using +
  try: convert first — text of n to build text, or number of t to do arithmetic
```

`text of [1,2,3]` is the opaque placeholder `"[3 items]"`, not the list's
contents — following the fix on the first example produces
`"Count: [3 items]"`, which typechecks but is not what `+` was probably for.
On the second example, neither conversion applies at all: you cannot
`number of` a list, and `text of` a list produces a placeholder, not
something arithmetic can use — the actual fix is a different operator
entirely (`plus` to append, `with` to update a record).

**Corrected clause:** "convert first — `text of n` to build text, or
`number of t` to do arithmetic — but only for a text/number pairing; if
either side is a list or record, neither conversion is meaningful: use
`plus` to append to a list, `with` to update a record, or rewrite the
expression."

### #52 — `not-text`, `interp.py:1410`

> **fix as written:** "`in` over text looks for text — wrap the left side
> with text of"

Verified directly:

```
>>> Interpreter().run('show [1,2] in "some text with 2 items inside"')
not-text: cannot look for [2 items] in text "some text with 2 items inside"
  try: `in` over text looks for text — wrap the left side with text of
```

`text of [1,2]` is `"[2 items]"`, which is not a substring of the text being
searched even though the text plainly does describe "2 items" — the fix
produces valid, non-crashing code that answers `false` regardless of intent
whenever the left side is a list or record.

**Corrected clause:** "`in` over text looks for text — wrap the left side
with `text of`, but only when it's a number, yes/no value, or nothing; if
it's a list or record, `text of` gives an opaque placeholder
(`[N items]`/`{record}`), not its contents, so the search won't find what
was probably intended."

### #59 — `grammar-data-missing` (format version), `lexer.py:96`

> **fix as written:** "regenerate with a matching version of planes"

Same symmetric-check shape as #8: `version != GRAMMAR_FORMAT_VERSION` fires
identically whether the data file is older or newer than this interpreter
expects, and "regenerate" only reads correctly for the older case.

**Corrected clause:** "regenerate the grammar data with a version of planes
matching this interpreter — if the data is newer than what this interpreter
reads, upgrade planes instead of regenerating the data."

## Notes on entries scored clean that are still worth a second look

- **#25 / #27** (`ask-failed` / `no-such-file`): see the reachability
  section above — these are real, verified interpreter gaps, just not
  expressible as `misdirects` since the *stated* fix is right for the one
  situation (`TestHost`, unstubbed) that can actually reach it.
- **#33** (`sine`, `interp.py:1085`): the sibling guards for `whole`
  (`interp.py:1038`) and `number` (`interp.py:1054`) both explicitly branch
  their fix on "if this is text, convert with `number of` first"; `sine`'s
  guard (`not isinstance(arg.value, Number)`) can fire on text too, but its
  fix ("sine takes an angle in degrees as a number — e.g. sine of 30") never
  mentions the conversion route the other two do. Not scored as
  `misdirects` — the given fix isn't wrong, just less complete than its
  siblings — but worth flagging as an inconsistency, not a defect.
