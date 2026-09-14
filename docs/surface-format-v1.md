# The effect-surface format, version 1

This is the specification for `shapes_cli.py --json` (and its JS and Swift
counterparts) — the document a downstream project should read instead of
copying the shape by hand. Five projects currently reimplement it in their own
code (Undertow, Cutter, Omniglot, Koncord's `HostEffect`, 5xFive), and one has
already drifted: Cutter added `process` and `tool` effect kinds that Planes
does not have. **A copy that adds a kind is no longer Planes' vocabulary.**
The vocabulary in §3 is closed, and only this repository can grow it.

This document is written directly from the code that produces the format —
`as_json`/`rules_json` in `shapes_cli.py`, `Violation.as_json` in `rules.py`,
and their JS (`js/cli.mjs`, `js/rules.mjs`) and Swift
(`swift/Sources/Planes/EffectSurface.swift`, `.../Rules.swift`) counterparts —
not from memory of what it should look like. A machine-checked companion,
`grammar/protocols/surface-v1.json`, is a JSON Schema for exactly what is
described here; `test_surface_format.py` runs all three hosts over a spread
of real programs and validates every one of them against it, and separately
checks that the kind table in §3 has not drifted from
`grammar/vocabulary.json`.

How to produce this document yourself:

```
python3 shapes_cli.py program.planes --json               # format 1
python3 shapes_cli.py program.planes --json --rules        # format 1 + rules

node js/cli.mjs shapes program.planes                       # the JS oracle
node js/cli.mjs shapes program.planes --rules

swift run planes-swift shapes program.planes                # the Swift oracle
swift run planes-swift shapes program.planes --rules
```

`shapes_cli.py` is the specification; the JS and Swift commands above are the
agreement oracles the test suites already hold to it (`test_js_shapes.py`,
`test_swift_shapes.py`, `test_js_rules.py`, `test_swift_rules.py`). All three
must produce byte-identical JSON for the same input, key order included,
which is why every table below states an exact key order rather than "an
object with these fields."

---

## 1. What this format is for

`shapes.py` computes what a Planes program **can do** without running it —
its *effect surface*. `--json` is that fact in a form a program can act on
before installing anything: does this package touch the network, and where;
is it actually pure; does it perform something it never declared. `--rules`
(H1, folded into `--json` as of PR #119) adds whether the program's own
declared rules pass, as structured fields alongside the same rendered text
`--rules` alone prints.

Two things this format is emphatically **not**:

- **Not a runtime trace.** Nothing in this document was observed by running
  the program. `effects`/`kinds`/`boundaries` are every effect any function
  in the file could perform if called (`Surface.declared`); `runs_on_load`
  is narrower — only what running the file's top level actually does
  (`Surface.effects`). A library reports an empty `runs_on_load` and a
  populated `effects`; reporting only `runs_on_load` would say a library
  that hides a network call behind a function does nothing, which is the
  exact failure this whole system exists to prevent.
- **Not a verified claim about a `foreign` boundary.** Planes cannot see
  inside a host function. Every effect a `foreign` declaration states is
  reported as **declared, not verified** (the `declared` field, §2.3) —
  asserted by whoever wrote the declaration, never derived. See §4.

## 2. Top-level document

Every key below appears in this exact order (Python `dict` insertion order,
preserved by every host's JSON serialiser) whenever it is present. `rules` is
the only key that is ever absent — see §2.2.

| key | type | meaning |
|---|---|---|
| `format` | integer, always `1` today | the format version (§6) |
| `program` | string | the file's base name (`os.path.basename`), not a path |
| `kind` | string enum: `"library"` \| `"pure"` \| `"program"` | see §2.1 |
| `pure` | boolean | `Surface.is_pure()` — no declared effects at all |
| `complete` | boolean | see §4.4 |
| `boundaries` | array of strings, alphabetically sorted, deduped | every boundary in `effects` (§3) |
| `kinds` | array of strings, alphabetically sorted, deduped | every kind in `effects` (§3) |
| `effects` | array of objects (§2.3) | the **declared** surface, sorted |
| `runs_on_load` | array of objects (§2.4) | the **top-level-only** surface, sorted |
| `modules_declared` | array of strings, alphabetically sorted | every `use`d module name |
| `modules_unused` | array of strings, alphabetically sorted | `use`d but never needed (§4.5) |
| `effects_undeclared` | array of objects (§2.5) | performed without the matching `use` (§4.5) |
| `unresolved_calls` | array of strings, alphabetically sorted, deduped | calls to a name the analyser could not resolve |
| `approximate` | array of arrays of strings | call routes that reach `sine`/`root` (§4.3) |
| `rules` | object (§2.2), **optional** | present only with `--json --rules` together |

### 2.1 `kind`

- `"library"` — no top-level effects, but at least one function (or a
  `foreign` declaration) has one (`Surface.is_library()`). `pure` is always
  `false` here — a library that reported `pure` because nothing runs at
  import time is precisely the lie this analyser exists to catch.
- `"pure"` — `Surface.is_pure()`: nothing in the file, called or not, has
  any effect. `pure` is `true`.
- `"program"` — anything else: at least one top-level effect. `pure` is
  `false`.

### 2.2 `rules` (H1, PR #119)

Present **only** when `--rules` is given alongside `--json`; a plain
`--json` document never has this key at all — not `null`, absent — so a
consumer that never asked for rule checking sees no trace the field exists.
Its three keys, in this order:

| key | type | meaning |
|---|---|---|
| `checked` | integer | `len(found)` — how many top-level `rule` statements the file has, whether or not any resolved |
| `resolved_subjects` | array of strings | every named subject (`rule [x] subject may …`) that resolved without raising, in rule order — read back from what `check()` actually did, never re-derived |
| `violations` | array of objects (§2.6) | every `Violation`, in the exact order `check()` returned them: grouped by forbid rule in the order the rules were declared (after `supersedes` resolution), and within a rule, in the same `(boundary, kind, target)` order as `effects` |

`checked` is `0` and `violations` is `[]` for a file with no rules at all —
`--json --rules` still returns a `rules` object in that case, it does not
fall back to a `--json`-only document (unlike bare `--rules` in text mode,
which prints `"no rules found"` instead).

The document's exit code is unaffected by `--json`: `1` if any violation has
`is_violation: true`, `2` if none do but at least one is `vacuous: true`
(a named-subject rule that resolved but matched nothing — P-Q19), else `0`.

### 2.3 One entry in `effects`

```
{ "kind": "ask", "boundary": "network", "target": "https://…", "computed": false, "declared": true }
```

| key | type | meaning |
|---|---|---|
| `kind` | string | one of the seven vocabulary kinds (§3), or the sentinel `"unknown"` (§3.1) |
| `boundary` | string | the kind's boundary, or `"foreign"` for `"unknown"` |
| `target` | string | where — a literal, a `{...}` pattern (§4.1), or a `(destination not stated)` label (§4.2) |
| `computed` | boolean | `true` when `target` was built at runtime rather than written as a literal |
| `declared` | boolean | `true` when this effect came from a `foreign … doing …` claim rather than being derived — "declared, not verified" (§4) |

Sorted by `(boundary, kind, target)`, ascending, code-point order. This is
`Surface.declared`: every effect any function in the file can perform if
called, plus every top-level one, plus every `foreign` declaration's claim
(even one nothing in the file calls — a re-exported clock function makes a
library impure whether or not its consumer calls it). Deduplicated by
`(kind, target, computed)` — a generic `foreign` entry is dropped when a
call site already resolved the same `(kind, boundary)` to a real,
non-computed destination, so the reader is not shown `{...}` beside the
literal answer it stands in for.

### 2.4 One entry in `runs_on_load`

```
{ "kind": "clock", "boundary": "ambient", "target": "time.time (destination not stated)" }
```

Only `kind`, `boundary`, `target` — no `computed`, no `declared`. This is
`Surface.effects`: what actually runs when the file's top level executes,
following calls but not entering functions never invoked from the top
level. Sorted by `(boundary, kind, target, site)` — the same primary key as
`effects`, with the source line as an explicit tie-breaker so two effects
reaching the same destination from different lines sort deterministically
regardless of set/hash iteration order. Empty for a pure library, `[]`.

### 2.5 One entry in `effects_undeclared`

```
{ "kind": "ask", "target": "https://…" }
```

Only `kind` and `target` — no `boundary`, no `computed`, no `declared`.
`Surface.used_but_undeclared()`: effects at the `network` or `file` boundary
(the only two boundaries a `use` statement governs — see §4.5) that the
program performs without the matching `use http` / `use file`. Preserves
`effects`' `(boundary, kind, target)` order, filtered.

### 2.6 One entry in `rules.violations`

One `Violation.as_json()` (`rules.py`), sixteen keys in this order — one per
forbid rule matched against one effect, against nothing at all (the vacuous
shape), or one declared `contradicts` pair where both rules apply (the
contradiction shape, B3):

| key | type | meaning |
|---|---|---|
| `rule` | string | the rule's name — the forbid rule for the first four shapes, or the rule that wrote the `contradicts` clause for the contradiction shape |
| `rule_line` | integer | the line the rule is declared on |
| `assertion` | string enum: `"forbid"` \| `"permit"` | `"forbid"` for the first four shapes — only a forbid rule ever produces one of those. For the contradiction shape this is `rule`'s own assertion, which may be `"permit"`: `contradicts` can be declared on either kind of rule |
| `kind` | string, one of the seven vocabulary kinds (never `"unknown"` — the parser rejects any other word here at parse time) | the rule's own effect kind |
| `target` | string or `null` | the rule's declared target, or `null` when the rule names none (matches every target of its kind) |
| `condition` | string | the rule's condition rendered as source (`rules.condition()`) |
| `because` | string or `null` | the rule's `because` annotation text, or `null` if it has none |
| `is_violation` | boolean | `false` for a cleared (`cleared_by` set) or vacuous match; `true` for a real violation and for a contradiction — see below |
| `vacuous` | boolean | `true` for the fourth shape: a named-subject rule that resolved but matched no effect at all |
| `vacuous_situation` | integer (`1`, `2`, or `3`) or `null` | which of the three vacuous cases (§4.6), `null` unless `vacuous` is `true` |
| `uncertain` | boolean | `true` when the match is against a computed target that could not be ruled out, not confirmed |
| `effect` | object or `null` (§2.7) | the specific effect matched, `null` for the vacuous shape; for the contradiction shape, the effect `rule` itself matched |
| `cleared_by` | object or `null` (§2.8) | the permit rule that excepted this match, or `null` |
| `narrowed_by` | array of objects (§2.8) | sibling forbid rules with a narrower scope that also matched — reported as related, not independent |
| `contradiction` | object or `null` (§2.10) | `null` except for the contradiction shape, where it names both rules of the declared pair and one effect each matched |
| `origins` | array of objects (§2.9) | every name/file the effect's target provably derives from, alphabetically sorted and deduplicated |
| `message` | string | `render()`'s own text, verbatim — so a host can print exactly what `--rules` prints without re-deriving it |

A violation is genuine — should fail a build — exactly when
`is_violation` is `true`. `cleared_by` non-`null` and `vacuous` are the two
reasons it can be `false` for the first four shapes; both are still reported
(so the reader sees the exception or the inert rule working), just not
counted. A contradiction (`contradiction` non-`null`) is always genuine:
`is_violation` is `true`, the same as a real violation, and it counts toward
a caller's exit code the same way.

### 2.7 `effect` (inside a violation)

```
{ "kind": "ask", "boundary": "network", "target": "https://…", "line": 9 }
```

`kind` and `boundary` are drawn from the same closed set as a rule's own
`kind` (§2.6) — never `"unknown"`/`"foreign"`, since a rule can only be
written against one of the seven vocabulary kinds. `line` is the effect's
source line.

### 2.8 `cleared_by` and one entry in `narrowed_by`

Both shapes are `{ "rule": "<name>", "line": <int> }` — the identity of
another rule, nothing else. `cleared_by` is the permit that excepted this
match (`supersedes` or narrower scope); `narrowed_by` lists every sibling
forbid rule with a narrower scope that also matched the same effect.

### 2.9 One entry in `origins`

```
{ "name": "payload", "file": "/path/to/file.planes" }
```

`file` is `null` when the name has no associated file (an `analyse(src)`
call with no path, matching every node's `file` being `None`). Deduplicated
and sorted by the same `"name (file)"` string `render()`'s derivation line
uses, so the structured list and the rendered line never disagree about
what counts as one origin.

### 2.10 `contradiction` (B3, Track 0 #5)

An authored `contradicts [other-name]` clause declares that two rules must
never both apply. A rule *applies* to a checked surface when its condition
matches at least one effect there — whether as a forbid rule that would be
violated or cleared, or as a permit rule that matched an effect; a rule
matching nothing does not apply. When both rules of a declared pair apply,
the checker reports the contradiction as a `Violation` in its own right,
distinct from the four shapes above and distinct from the structural
conflict detection `RuleConflict` performs at compile time (v2.0 §32):
`contradicts` is an authored declaration that reaches pairs no structural
check can see — different kinds, different targets, incompatible in intent
rather than in shape.

```
{
  "rule": "no-sends",
  "effect": { "kind": "ask", "boundary": "network", "target": "https://x.example.com", "line": 11 },
  "with_rule": "no-writes",
  "with_effect": { "kind": "write", "boundary": "file", "target": "out.txt", "line": 10 }
}
```

`rule` and `effect` name the rule that wrote the `contradicts` clause and
the effect it matched — the same values the violation's own top-level
`rule`/`effect` keys carry, repeated here so a consumer reading only this
key gets both sides of the pair without also reading the top-level fields.
`with_rule` and `with_effect` (§2.7's shape, never `null`) name the rule
`contradicts` pointed at and the effect *that* rule matched. Only one rule
of a declared pair ever carries the `contradicts` clause — the checker
refuses declaring the same pair from both sides — so a contradiction is
never reported twice for one pair, and `null` here means every other
shape.

## 3. The effect-kind vocabulary

Closed at **seven kinds**, defined once in `grammar/vocabulary.json`'s
`effect_kinds` array and imported into `shapes.py` as `EFFECT_KINDS`
(`lexer.py`) so the parser can validate a rule's kind at parse time against
the same list. `test_surface_format.py::test_doc_kind_table_matches_vocabulary_json`
checks that the table below has not drifted from it.

| kind | boundary | meaning |
|---|---|---|
| `ask` | `network` | request-with-response |
| `clock` | `ambient` | the current time |
| `env` | `ambient` | environment variables, process arguments |
| `random` | `ambient` | entropy |
| `read` | `file` | reading a file |
| `show` | `console` | writing to the console |
| `write` | `file` | writing a file |

`clock` and `random` are effects because they make a result depend on
something outside the program; a package index that called a clock-reading
function pure would be wrong in a way that matters — it could not be
reproduced from its own derivation.

Four boundaries govern these seven kinds: `network` (only `ask`), `file`
(`read`, `write`), `console` (`show`), `ambient` (`clock`, `random`, `env`).
Only `network` and `file` have a matching `use` module (`http`, `file` —
`modules.py`'s `BUILTIN_MODULES`); `modules_unused`/`effects_undeclared`
(§4.5) only ever mention those two boundaries.

**Say plainly what this means for a downstream copy: the vocabulary is
these seven words, no more.** Cutter's `process` and `tool` kinds are not
Planes effect kinds; a `--json` document from this repository will never
emit them, and a fork that adds them is describing something else, not a
drifted copy of this format.

### 3.1 `"unknown"` — not an eighth kind

An **undeclared** `foreign` function (`foreign f from "lib.f"`, no `doing`
clause at all) contributes one effect whose `kind` is the literal string
`"unknown"` and whose `boundary` is `"foreign"` — never a guess of purity.
Omitting the `doing` clause means *unknown*, not *pure*: defaulting to pure
would publish a guess as a fact, which is the same failure this whole
analyser exists to prevent for a declared-but-hidden effect. Generated live:

```
$ cat undeclared.planes
foreign mystery from "lib.mystery"
x = mystery

$ python3 shapes_cli.py undeclared.planes --json
{
  "format": 1, "program": "undeclared.planes", "kind": "program",
  "pure": false, "complete": false,
  "boundaries": ["foreign"], "kinds": ["unknown"],
  "effects": [{"kind": "unknown", "boundary": "foreign",
               "target": "lib.mystery", "computed": true, "declared": true}],
  "runs_on_load": [{"kind": "unknown", "boundary": "foreign",
                     "target": "lib.mystery"}],
  "modules_declared": [], "modules_unused": [], "effects_undeclared": [],
  "unresolved_calls": [], "approximate": []
}
```

`"unknown"`/`"foreign"` can appear in `kinds`/`boundaries`/`effects`/
`runs_on_load`, and this is also why `complete` is `false` here (§4.4). It
never appears inside a rule or a rule's matched `effect` (§2.6, §2.7) —
a rule can only be written against one of the seven kinds in §3, so nothing
it matches can be `"unknown"` either. It never appears in
`effects_undeclared` either, since that list is restricted to the
`network`/`file` boundaries and `"foreign"` is neither.

## 4. Conventions

### 4.1 The `{...}` hole

A `target` that is built at runtime rather than written as a string literal
is reported as a **pattern**: every statically-known literal chunk is kept
verbatim, and each unknown span is replaced with the literal three
characters `{...}`. `computed` is `true` whenever any part of the target
came from something other than a literal — including when the whole thing
is one bare `{...}` because nothing about it could be pinned down.

```
https://registry.internal.example.com/v1/packages/{...}
```

is `"https://registry.internal.example.com/v1/packages/"` (a literal
prefix, known statically) concatenated with a parameter the analyser could
not resolve to a constant. `{...}` is a hole standing for *any* text,
including none — a pattern that opens or closes with a hole is not anchored
on that end (`rules.py`'s `_pattern_excludes`, which uses exactly this
convention to decide whether a rule's target can *never* be reached by a
computed one). This is the same `{...}` a rule-matching implementation must
recognise — `js/rules.mjs`'s `patternExcludes` and `Rules.swift`'s
`patternExcludes` must agree with `shapes.py`'s `_pattern_excludes` on it.

For a rule target that parses as `scheme://host[:port][/path]`, a rule
covers that address **and everything under it** (B2), not only the exact
address: `_pattern_excludes` was re-proven for that weaker condition, so a
computed target is excluded only when its known chunks prove no completion
could ever be *covered* by the rule — not merely that it could never *equal*
the rule's target outright. A target that isn't URL-shaped (a file path, a
`queue:send`-style name, console text) still matches exactly, as every rule
target did before B2.

### 4.2 `(destination not stated)`

A `foreign` declaration whose `doing` claim names an effect but never says
*where* (no literal, no parameter) reports its target as the host function's
own name plus the literal suffix `" (destination not stated)"` —
`"time.time (destination not stated)"` in the worked example below. This
is baked into the `target` string itself (unlike the human-readable
`" (computed)"` and `" (declared, not verified)"` suffixes below, which
exist only in the **text** rendering, never in the JSON `target` value —
those two facts are carried instead by the `computed` and `declared`
boolean fields). Naming the host function is honest — it is what the reader
has — but it is explicitly not a destination, which is why the suffix says
so rather than leaving a bare, misleadingly specific-looking function name.

### 4.3 `approximate`

Whether a program can produce a numerically approximate value is derivable
without running it — the same call-graph walk that computes effects,
answering whether the graph reaches `sine` (approximate at every argument)
or `root` (approximate unless its argument is a perfect square). Each entry
in `approximate` is one route, entry point to operation, as an array of
names: `["(top level)", "wave", "cosine", "sine"]` means the top level calls
`wave`, which calls `cosine`, which calls `sine`. Real example
(`paint/bloom.planes --json`):

```json
"approximate": [
  ["(top level)", "wave", "cosine", "sine"],
  ["rings", "wave", "cosine", "sine"],
  ["wave", "cosine", "sine"]
]
```

The first entry is the shortest route from any entry point; the rest are
not alphabetically sorted. `approximate` is unrelated to `complete` and to
a `foreign` claim's `declared`/"not verified" status — it is about whether
the *numbers* a program computes are exact, not about effects at all.

### 4.4 `complete`

`true` when the analyser accounted for everything: no `"unknown"` effect
anywhere in `effects` (every `foreign` declaration stated its effects) and
no call the analyser could not resolve (`unresolved_calls` empty). `false`
otherwise. This is a different axis from `pure` (no effects at all) and
from a per-effect `declared` (claimed, not derived, but still *stated*).

### 4.5 `declared`, `"declared, not verified"`

Planes cannot see inside a `foreign` (host) function — its effects are a
claim by whoever wrote the declaration, never something the analyser
derived. Every such effect has `declared: true` in JSON (`Effect.claimed` in
`shapes.py`) and prints with the suffix `"(declared, not verified)"` in text
mode. `declared: false` means the analyser found the effect itself, by
walking code it can actually read.

### 4.6 The three vacuous situations

A named-subject forbid rule (`rule [x] some-name may not …`) whose subject
resolves but never matches a single effect is reported, not silently
treated as "no violations" — a rule that never did any work must not look
like a rule that passed (P-Q19). `vacuous_situation` distinguishes why:

1. the program performs no effect of the rule's kind at all;
2. effects of that kind exist, but none derive from the named subject;
3. the subject does derive an effect of that kind, but the rule's own
   target excludes every one it reaches.

## 5. `--diff`

`shapes_cli.py --diff old.planes new.planes` has **no JSON output today** —
`--json` alongside `--diff` is silently ignored; the command always prints
the two paths and `SurfaceDiff.render()`'s text, and exits `1` when the
change is significant (a new boundary, or a new destination inside a
boundary already touched — `SurfaceDiff.is_significant()`), `0` otherwise.
If a machine-readable diff is ever needed, it is a new addition to this
document, not something this version already provides silently.

## 6. Format version

`FORMAT_VERSION` (`shapes_cli.py`) is bumped **only when the meaning of an
existing field changes** — never for an added field. A consumer that does
not recognise the version should refuse the document rather than guess at
what changed. H1 (PR #119) is the worked example: it added the entire
`rules` key described in §2.2, and `format` stayed `1`, because every field
that existed before H1 means exactly what it meant before — `rules` is
either present with its own new meaning or entirely absent, and a consumer
that never asks for it sees no difference at all.

## 7. Worked example

`demo/mcp/v2.planes` declares one rule forbidding a telemetry destination,
and then violates it. This is the live output of
`python3 shapes_cli.py demo/mcp/v2.planes --json --rules` — every field in
§2, in one real document, generated by the CLI rather than written by hand
(the plain `--json` form, without `rules`, is committed at
`demo/mcp/v2.surface.json` and gated by `test_mcp_demo.py`):

```json
{
  "format": 1,
  "program": "v2.planes",
  "kind": "program",
  "pure": false,
  "complete": true,
  "boundaries": ["ambient", "console", "file", "network"],
  "kinds": ["ask", "clock", "read", "show", "write"],
  "effects": [
    {"kind": "clock", "boundary": "ambient",
     "target": "time.time (destination not stated)",
     "computed": true, "declared": true},
    {"kind": "show", "boundary": "console", "target": "{...}",
     "computed": true, "declared": false},
    {"kind": "read", "boundary": "file",
     "target": "mcp.stdio.read (destination not stated)",
     "computed": true, "declared": true},
    {"kind": "write", "boundary": "file", "target": "audit.jsonl",
     "computed": false, "declared": false},
    {"kind": "ask", "boundary": "network",
     "target": "https://registry.internal.example.com/v1/packages/{...}",
     "computed": true, "declared": false},
    {"kind": "ask", "boundary": "network",
     "target": "https://telemetry.example.com/collect",
     "computed": false, "declared": true}
  ],
  "runs_on_load": [
    {"kind": "clock", "boundary": "ambient",
     "target": "time.time (destination not stated)"},
    {"kind": "show", "boundary": "console", "target": "{...}"},
    {"kind": "read", "boundary": "file",
     "target": "mcp.stdio.read (destination not stated)"},
    {"kind": "write", "boundary": "file", "target": "audit.jsonl"},
    {"kind": "ask", "boundary": "network",
     "target": "https://registry.internal.example.com/v1/packages/{...}"},
    {"kind": "ask", "boundary": "network",
     "target": "https://telemetry.example.com/collect"}
  ],
  "modules_declared": ["file", "http"],
  "modules_unused": [],
  "effects_undeclared": [],
  "unresolved_calls": [],
  "approximate": [],
  "rules": {
    "checked": 1,
    "resolved_subjects": [],
    "violations": [
      {
        "rule": "no-telemetry-exfiltration",
        "rule_line": 1,
        "assertion": "forbid",
        "kind": "ask",
        "target": "https://telemetry.example.com/collect",
        "condition": "anything may not ask to \"https://telemetry.example.com/collect\"",
        "because": "an MCP tool must not phone a metrics collector behind the agent's back",
        "is_violation": true,
        "vacuous": false,
        "vacuous_situation": null,
        "uncertain": false,
        "effect": {"kind": "ask", "boundary": "network",
                   "target": "https://telemetry.example.com/collect", "line": 9},
        "cleared_by": null,
        "narrowed_by": [],
        "origins": [],
        "message": "[no-telemetry-exfiltration] violated at line 9.\n  ask https://telemetry.example.com/collect (declared, not verified)\n  rule declared at line 1: anything may not ask to \"https://telemetry.example.com/collect\""
      }
    ]
  }
}
```

Notice what §4 predicts: the two `foreign` calls (`clock`, `read`) are
`"declared": true` with `(destination not stated)` targets; the two derived
network reads show the hole convention (a literal prefix plus `{...}`, and
`(computed)` only in `message`'s rendered text, never in `target` itself);
`complete` is `true` because both `foreign` declarations stated their
effects; and the one violation names the exact effect, line, and rendered
message, with `cleared_by`/`narrowed_by`/`origins` all empty because
nothing excepts or relates to it.

A permit exception looks different in exactly one place —
`demo/rules/exception.planes --json --rules` produces a violation with
`"is_violation": false`, `"target": null` (its forbid rule names no
target), and `"cleared_by": {"rule": "audit-allowed", "line": 3}` — the
prohibition would have fired, but a more specific permit rule cleared it,
and the JSON says so structurally rather than only in `message`'s prose.
