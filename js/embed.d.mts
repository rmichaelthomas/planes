// js/embed.d.mts — hand-written types for js/embed.mjs.
//
// There is no build step that derives these from the implementation (the JS
// implementation is plain, untyped ESM, checked against the Python and Swift
// hosts by runtime agreement suites, not by a type checker) — so this file is
// authored and kept in sync by hand, and is deliberately narrower than the
// implementation: it only describes what `js/embed.mjs` exports, and only
// down to the level a host actually needs. Where the implementation's own
// shape is internal, not part of the frozen embedding surface, or expected to
// keep growing (an `Effect`, a `Surface`, an AST node, a rule `Violation`'s
// `rule`/`effect` fields), the type here is `unknown` rather than a guess —
// read it back through the accessor functions this module exports
// (`asJson`, `functionsBreakdown`, `derivationForm`, `diff`, `toJson`,
// `toHost`) instead of reaching into those fields directly.
//
// No `.d.ts`/`.d.mts` file existed anywhere in js/ before this one (verified
// while planning this work); this is the first, scoped to embed.mjs alone.

// ================================================================ grammar data
//
// Importing "./embed.mjs" loads the grammar synchronously as a side effect —
// nothing here needs to be called first, and nothing in this file's surface
// can throw GrammarDataError("vocabulary not loaded", ...).

/** Mirrors lexer.py's GrammarDataError: refuse, don't guess. Not thrown by
 * anything `embed.mjs` itself does — the load happens at import and either
 * succeeds or throws synchronously during that import — exported so a host
 * can still write `instanceof GrammarDataError` for symmetry with the rest
 * of the implementation. */
export class GrammarDataError extends Error {
  readonly name: "GrammarDataError";
  readonly tag: string;
  readonly detail: string;
  readonly fix: string;
  constructor(tag: string, detail?: string, fix?: string);
}

// ================================================================ lexing (js/lexer.mjs)

/** One lexed token: `kind` is a token class name from
 * grammar/vocabulary.json's `token_classes` (e.g. "NAME", "STRING",
 * "NUMBER", "OP"); `value` is its text, already escape-resolved for a
 * STRING; `line` is 1-based. */
export class Token {
  readonly kind: string;
  readonly value: string;
  readonly line: number;
}

/** Raised by `tokenize` and `parse` on malformed source. `message` already
 * contains the fix clause (every Planes error names one); `line` is
 * 1-based when known. */
export class PlanesSyntaxError extends Error {
  readonly name: string;
  readonly line: number | null;
}

/** The source's tokens, in order. Throws `PlanesSyntaxError` on malformed
 * input (an unterminated string, a stray character, …). */
export function tokenize(src: string): Token[];

/** The grammar's reserved keywords (`grammar/vocabulary.json`'s `keywords`),
 * as a Set of the exact spellings. */
export function keywords(): Set<string>;

/** The seven effect-kind words (`ask clock env random read send show
 * write` — see grammar/vocabulary.json's `effect_kinds`), as a Set. */
export function effectKinds(): Set<string>;

/** The builtin function names (`grammar/vocabulary.json`'s `builtins`), as
 * a Set. */
export function builtinNames(): Set<string>;

// ================================================================ parsing (js/parser.mjs)

/** A parsed statement or expression node. Every node carries `__node`
 * naming its AST kind (e.g. "Let", "Show", "Rule", "FuncDef"); the rest of
 * its shape is internal and intentionally untyped here — read it back
 * through `analyse`/`check`/`asJson` rather than pattern-matching on
 * fields this file does not name. A caller that needs `.filter(s =>
 * s.__node === "Rule")` (the way `check` below is fed its rules, and the
 * way js/cli.mjs itself does it) can rely on `__node` alone. */
export type PlanesNode = { readonly __node: string } & Record<string, unknown>;

/** Raised when a construct has more than one legal reading and the parser
 * cannot pick one without a runtime clarification. A subclass of
 * `PlanesSyntaxError`. */
export class PlanesAmbiguity extends PlanesSyntaxError {}

/**
 * Parse Planes source into its statement list. Single-file: it does not
 * follow `use` across files (that needs a module loader with a way to read
 * another file — js/modules.mjs plus js/module_loader_node.mjs under Node —
 * which is Node-only and stays out of this module on purpose). `known`
 * pre-declares cross-file names (a Map of name -> arity, or an iterable of
 * names) the same way js/cli.mjs's `ast` subcommand does for its multi-file
 * oracle; omit it for an ordinary single-file program.
 *
 * Throws `PlanesSyntaxError` or `PlanesAmbiguity` on malformed or ambiguous
 * source.
 */
export function parse(src: string, known?: Map<string, number | null> | Iterable<string> | null): PlanesNode[];

// ================================================================ effect-surface analysis (js/shapes.mjs)

/**
 * A program's computed effect surface — what analyse() returns, and what
 * `asJson`/`functionsBreakdown`/`derivationForm`/`diff`/`check` all consume.
 * Opaque here on purpose: its fields (`effects`, `functions`, `modules`,
 * `unresolved`, `foreign`, `approximate`, plus derived getters like
 * `declared`/`kinds()`/`boundaries()`) are shapes.mjs's internal
 * representation, not a frozen part of this embedding's contract — use the
 * plain-data views below instead of reaching into a Surface directly.
 */
export type Surface = unknown;

/** Bumped when a field's meaning changes; matches shapes_cli.py's
 * `FORMAT_VERSION` and shapes.mjs's own `FORMAT_VERSION` (re-exported here
 * under this name to avoid colliding with any other format-version constant
 * a host embeds alongside this one). */
export const SURFACE_FORMAT_VERSION: number;

/** shapes_cli.py's `as_json` form, byte-for-byte what the Python and Swift
 * hosts agree on: `program` (the last path segment of `path` — a label, not
 * a read), `kind` ("library" | "pure" | "program"), `pure`, `complete`,
 * `boundaries`, `kinds`, `effects` (declared, each `{kind, boundary, target,
 * computed, declared}`), `runs_on_load`, `modules_declared`,
 * `modules_unused`, `effects_undeclared`, `unresolved_calls`, and
 * `approximate` (routes from an entry point to an approximating operation
 * such as `sine`). Left as `unknown` field-by-field rather than restated
 * here — the shape is the published surface schema, and restating it by
 * hand in two places is exactly the drift this codebase's generators exist
 * to avoid; treat the object this returns as JSON.
 */
export function asJson(surface: Surface, path: string): Record<string, unknown>;

/** Per-function effect breakdown: each function name (sorted) to its own
 * sorted list of `{kind, boundary, target, computed, claimed}`. */
export function functionsBreakdown(surface: Surface): Record<string, unknown[]>;

/** Per-declared-effect derivation + origins, in declared order — the
 * derivation-agreement form js/cli.mjs's `shapes-deriv` emits. */
export function derivationForm(surface: Surface): unknown[];

/** What changed between two effect surfaces of the same program (e.g.
 * before/after an edit) — new/removed effects, and boundaries newly
 * crossed or dropped entirely. Mirrors `shapes_cli.py --diff`. */
export class SurfaceDiff {
  readonly added: unknown[];
  readonly removed: unknown[];
  readonly newBoundaries: string[];
  readonly droppedBoundaries: string[];
  /** True when nothing was added or removed (boundary changes aside). */
  isEmpty(): boolean;
  /** Effects whose destination is new (excludes a merely-recomputed one). */
  newDestinations(): unknown[];
  /** True when this diff is worth a human's attention: a new boundary, or
   * a genuinely new destination. */
  isSignificant(): boolean;
  /** A human-readable rendering, the same text `shapes_cli.py --diff`
   * prints. */
  render(): string;
}

/** Computes a `SurfaceDiff` between two effect surfaces of (usually) the
 * same program at two points in time. */
export function diff(before: Surface, after: Surface): SurfaceDiff;

/**
 * Compute a program's effect surface: everything it can do, without
 * running it. `file` is a label only (attached to derivation nodes; pass
 * `null` for an in-memory program with no file identity, the same way
 * js/cli.mjs's single-file subcommands do).
 */
export function analyse(src: string, file?: string | null): Surface;

// ================================================================ rule checking (js/rules.mjs)

/** Raised when two rules on the same subject/kind/target conflict (a
 * `forbid` and a `permit` that neither supersedes nor narrows the other). */
export class RuleConflict extends Error {}

/** Raised when a rule's subject cannot be resolved against the traced
 * effect surface (see the error's own message for the fix — it names the
 * available subjects). */
export class RuleNotSupported extends Error {}

/** A stable, content-derived six-hex-character identity for a rule
 * (subject + assertion + kind + target — never name or line), matching
 * the `@xxxxxx` fingerprint token a rendered rule carries. */
export function fingerprint(rule: PlanesNode): string;

/** A rule's condition, exactly as written, for echoing into a message —
 * e.g. `program may not write to "refunds.json"`. */
export function condition(rule: PlanesNode): string;

/** One matched effect, as a violation's `effect`/`cleared_by`/`contradiction`
 * fields carry it (docs/surface-format-v2.md §2.7) — `kind`/`boundary` are
 * the effect's ACTUAL kind/boundary (which can differ from the violated
 * rule's own declared `kind`: forbidding `ask` also forbids `send`, B1),
 * `line` is its source line, and `computed`/`declared` are `Effect#computed`/
 * `Effect#claimed` (B4) — the facts the rendered text's `" (computed)"` /
 * `" (declared, not verified)"` suffixes come from. */
export interface EffectJson {
  kind: string;
  boundary: string;
  target: string;
  line: number;
  computed: boolean;
  declared: boolean;
}

/** `{rule, line}` — the identity of another rule, nothing else. Used for
 * `cleared_by` (the permit that excepted a match) and each entry of
 * `narrowed_by` (a sibling forbid rule with a narrower scope that also
 * matched). */
export interface RuleRef {
  rule: string;
  line: number;
}

/** One entry in `origins`: every name/file a matched effect's target
 * provably derives from (alphabetically sorted and deduplicated the same
 * way the rendered "derived from:" line is). `file` is `null` when the
 * name has no associated file. */
export interface OriginJson {
  name: string;
  file: string | null;
}

/** B3's contradiction shape (docs/surface-format-v2.md §2.10): both rules
 * of a declared `contradicts` pair matched at least one effect. `rule`/
 * `effect` name the rule that wrote the `contradicts` clause and the effect
 * it matched — the same values the violation's own top-level `rule`/`effect`
 * fields carry, repeated here so a consumer reading only this key gets both
 * sides of the pair. `with_rule`/`with_effect` name the rule `contradicts`
 * pointed at and the effect THAT rule matched. */
export interface ContradictionJson {
  rule: string;
  effect: EffectJson | null;
  with_rule: string;
  with_effect: EffectJson;
}

/**
 * `Violation#asJson()`'s exact document (H1, B4; docs/surface-format-v2.md
 * §2.6) — every field `render()`'s text is built from, so a host never has
 * to parse `message`/`render()` to get at a fact this interface already
 * names. Five shapes, told apart by `contradiction` (non-null), `vacuous`
 * (true), `cleared_by` (non-null), and `narrowed_by` (non-empty) — none set
 * is a plain, genuine violation.
 *
 * `subject` (B4) is the rule's own named subject (`"anything"` for the
 * wildcard) — present because the vacuous shapes' text uses it raw, never
 * folded into `condition` the way `assertion`/`kind`/`target` are.
 * `message` is `render()`'s own text, included verbatim so a host can print
 * exactly what text mode prints without re-deriving it; `renderViolation`
 * (below) is what proves every OTHER field here is enough to reconstruct it.
 */
export interface ViolationJson {
  rule: string;
  rule_line: number;
  subject: string;
  assertion: "forbid" | "permit";
  kind: string;
  target: string | null;
  condition: string;
  because: string | null;
  is_violation: boolean;
  vacuous: boolean;
  vacuous_situation: 1 | 2 | 3 | null;
  uncertain: boolean;
  effect: EffectJson | null;
  cleared_by: RuleRef | null;
  narrowed_by: RuleRef[];
  contradiction: ContradictionJson | null;
  origins: OriginJson[];
  message: string;
}

/** `render()`'s text, computed purely from a `ViolationJson` document (B4)
 * — never from a `Violation`/rule/effect object. `Violation#render()` is
 * itself defined as `renderViolation(this.asJson())`; a host can call this
 * directly on its own copy of `asJson()`'s output (including one round-
 * tripped through `JSON.stringify`/`JSON.parse`, or received over the wire
 * from `shapes_cli.py --json --rules`) to get the identical text without
 * re-deriving it — or, more to B4's point, skip this entirely and build its
 * own wording straight from the fields (see README's "Embedding from
 * JavaScript" and docs/surface-format-v2.md's "Writing your own wording"). */
export function renderViolation(fields: ViolationJson): string;

/** One `forbid` rule matched — or, for the vacuous shape, not matched
 * against anything at all — against the traced effect surface. */
export class Violation {
  /** The rule AST node this violation is about. */
  readonly rule: PlanesNode;
  /** The effect it matched, or `null` for the vacuous ("this rule matches
   * nothing in this program") shape. */
  readonly effect: unknown;
  readonly uncertain: boolean;
  readonly cleared_by: unknown;
  readonly narrowed_by: unknown[];
  readonly origins: unknown[];
  /** True for the vacuous shape: the rule is well-formed but never
   * triggers in this program (a report, not necessarily a problem). */
  readonly vacuous: boolean;
  /** True when this is a genuine, non-vacuous rule violation — the field
   * js/cli.mjs's `rules`/`rules-src` and a host's own exit-code decision
   * both read. */
  readonly is_violation: boolean;
  /** The human-readable finding, the same text `shapes_cli.py --rules`
   * prints for this violation — equivalent to `renderViolation(this.
   * asJson())`. */
  render(): string;
  toString(): string;
  /** Every field `render()` reads, as data rather than prose (H1, B4) — see
   * `ViolationJson`. */
  asJson(): ViolationJson;
}

/** `check()`'s return value: every rule's result, plus which rule subjects
 * actually resolved against the surface (`resolvedSubjects`) — the readback
 * `shapes_cli.py` needs. An ordinary array with one extra property, not an
 * Array subclass. */
export type RuleResults = Violation[] & { resolvedSubjects: string[] };

/**
 * Check a program's `rule` statements against its effect surface.
 * `rules` is typically `parse(src).filter(s => s.__node === "Rule")`;
 * `declaringFile` is a label used to resolve a subject named by file path
 * (pass `null` for an in-memory program, matching `analyse`'s `file`).
 *
 * Throws `RuleConflict` or `RuleNotSupported` — both fatal, matching
 * `shapes_cli.py --rules`'s own exit behaviour — rather than returning a
 * partial result.
 */
export function check(rules: PlanesNode[], surface: Surface, declaringFile?: string | null): RuleResults;

// ================================================================ exact-rational numbers (js/planes_num.mjs)
//
// A Planes number is NEVER a JavaScript `number` internally: it is an exact
// rational, a `Fraction` of two `bigint`s in lowest terms with a positive
// denominator (mirroring Python's `fractions.Fraction`), so `0.1 + 0.2` is
// exactly `0.3` and `1 / 3` stays one third rather than rounding to a float.
// `PlanesNumber` wraps a `Fraction` and additionally tracks whether the
// value is EXACT or APPROXIMATE (the latter only ever produced by `sine`/
// `root of` today) — `isExact` and `approx` together carry that, never a
// silently-dropped flag. A denominator past `2n ** 4000n` refuses (throws
// `Inexact`) rather than rounding invisibly. Reach for `.toNumber()` only at
// a genuine host boundary (logging, an approximate display); every other
// use of a Planes number should stay exact.

/** An exact rational: `n`/`d`, both `bigint`, always reduced to lowest
 * terms with `d > 0n`. */
export class Fraction {
  readonly n: bigint;
  readonly d: bigint;
  constructor(num: bigint, den?: bigint);
  add(o: Fraction): Fraction;
  sub(o: Fraction): Fraction;
  mul(o: Fraction): Fraction;
  div(o: Fraction): Fraction;
  neg(): Fraction;
  /** -1, 0 or 1: the sign of `this - o`. */
  cmp(o: Fraction): -1 | 0 | 1;
  eq(o: Fraction): boolean;
  lt(o: Fraction): boolean;
}

/** Why a value is approximate: which operation produced it (currently only
 * `sine`/`root of`) and how many correct decimal places it carries. */
export type Approximation = unknown;

/** A Planes number: an exact rational, optionally flagged approximate.
 * Construct one with `PlanesNumber.parse` (from Planes NUMBER-literal
 * text), `PlanesNumber.of` (from a JS number/bigint/string/Fraction — a
 * JS `number` is converted via its shortest round-trip decimal text, the
 * same route `Number.of` takes in the interpreter, never via the float's
 * raw bits), or by wrapping a `Fraction` directly with `new
 * PlanesNumber(fraction)`. */
export class PlanesNumber {
  /** The exact value. Read `.n`/`.d` off this for the numerator/denominator
   * rather than assuming `PlanesNumber` itself carries them. */
  readonly q: Fraction;
  /** `null` when exact; otherwise why/how this value is approximate. */
  readonly approx: Approximation | null;
  constructor(q: Fraction, approx?: Approximation | null);
  /** `true` iff `approx` is `null`. */
  readonly isExact: boolean;
  static parse(text: string): PlanesNumber;
  static of(v: PlanesNumber | bigint | number | string | Fraction): PlanesNumber;
  /** `true` iff the denominator is 1 (a whole number). */
  isWhole(): boolean;
  /** The value as a `bigint`. Throws `RangeError` if not whole. */
  asInt(): bigint;
  /** The value as a host `number` (a float) — `planes_num.py`'s `float(q)`,
   * correctly rounded from the exact rational, not the quotient of two
   * already-rounded floats. Only ever use this at a genuine host boundary;
   * nothing inside a running program computes from it. */
  toNumber(): number;
  add(o: PlanesNumber | bigint | number | string | Fraction): PlanesNumber;
  sub(o: PlanesNumber | bigint | number | string | Fraction): PlanesNumber;
  mul(o: PlanesNumber | bigint | number | string | Fraction): PlanesNumber;
  div(o: PlanesNumber | bigint | number | string | Fraction): PlanesNumber;
  /** The value's canonical text (what `show`/`why` render), e.g. "1/3",
   * "8", "0.33". */
  text(): string;
}

/** Raised in place of silently rounding: a computation's exact result
 * would need a denominator past `2n ** 4000n`. */
export class Inexact extends Error {}

/** Raised by `numberFromText` when text does not read as a Planes number
 * (`number of` in the language). Carries `approximation`, the nearest
 * value it could have meant, when there is one. */
export class NotANumber extends Error {
  readonly approximation: PlanesNumber | null;
}

/** `number of` — parses `text` the way the language's own builtin does
 * (Python whitespace and `\d`, not JavaScript's). Throws `NotANumber` on
 * text that does not read as a number. */
export function numberFromText(text: string): PlanesNumber;

// ================================================================ running programs (js/interp.mjs)

/** Raised for a program error — something wrong with the PROGRAM, not the
 * host running it (contrast `CoreRestrictionError`). `message` already
 * contains the fix clause. */
export class PlanesError extends Error {
  readonly name: "PlanesError";
  readonly tag: string;
  readonly detail: string;
  readonly fix: string;
  readonly path: string | null;
}

/** Raised only by an `Interpreter` constructed with `coreOnly: true`, when
 * the program reaches a construct outside `grammar/core.json`'s declared
 * port surface. Distinct from `PlanesError`: the program is legal Planes: a
 * full host would run it; this one, by its own construction, does not. */
export class CoreRestrictionError extends Error {
  readonly name: "CoreRestrictionError";
  readonly construct: string;
  readonly category: string;
  readonly file: string | null;
  readonly line: number | null;
  readonly approximateLine: boolean;
}

/** A value together with the derivation node `why` walks — what
 * `Interpreter#env.get(name)` returns. `.value` is the plain evaluated
 * value: `null`, `boolean`, `PlanesNumber`, `string`, an `Array` (a Planes
 * list) or a `Map` (a Planes record — insertion-ordered, never a plain
 * object). `.node` is opaque provenance, not part of this embedding's
 * frozen surface. */
export class Traced {
  readonly value: null | boolean | PlanesNumber | string | unknown[] | Map<string, unknown>;
  readonly node: unknown;
  constructor(value: Traced["value"], node: unknown);
}

/** Wraps a plain value as a `Traced` with a literal-derivation label — the
 * way to hand a host-computed value to the interpreter (e.g. seeding an
 * `Env`) or to build one for a test. `label` defaults to the value's own
 * rendered form (`fmt(v)`). */
export function lit(v: Traced["value"], label?: string | null): Traced;

/** Renders a value the way `show`/`why` do: `true`/`false`, `nothing`,
 * a Planes number's canonical text, a quoted+escaped string, or a
 * recursively rendered list/record. */
export function fmt(v: Traced["value"]): string;

/** Unwraps a (possibly `Traced`) Planes value into plain JSON-shaped data
 * and serialises it exactly as the `write` effect does: `json.dumps(v,
 * indent=2)` with non-ASCII escaped, a whole `PlanesNumber` as a bare
 * integer and any other number as its exact text (never silently
 * rounded). */
export function toJson(v: unknown): string;

/** Unwraps a (possibly `Traced`) Planes value into plain JS data — a
 * `PlanesNumber` becomes a JS integer (if whole) or float, an `Array` stays
 * an array (recursively converted), a `Map` becomes a plain object. Use
 * this, not `toJson`, when the host wants a JS value rather than a JSON
 * string — and remember a non-whole number loses exactness the moment it
 * crosses this boundary. */
export function toHost(x: unknown): unknown;

/** The inverse of `toHost`: lifts a plain JS value (as a foreign function's
 * host-side return, or a host response) into a Planes value — a JS
 * `number`/`bigint` becomes an exact `PlanesNumber` (via `PlanesNumber.of`,
 * never a raw float already carrying rounding error), an array becomes a
 * Planes list (recursively converted), and a plain object becomes a Planes
 * record (a `Map`, so field order matches the object's own key order). */
export function fromForeign(x: unknown): unknown;

/** What running a program can do to the outside world, one entry per
 * effect performed, in execution order — the log `Interpreter#effects`
 * accumulates. Each entry is `[kind, ...args]`; `kind` is one of the seven
 * effect-kind words and the trailing fields vary by kind (see
 * js/interp.mjs's own `this.effects.push(...)` call sites — e.g. `["show",
 * text]`, `["write", path, byteLength]`, `["ask", url, byteLength]`) — kept
 * as `unknown` here rather than a per-kind union that would have to be
 * updated by hand every time a call site changes what it logs. */
export type EffectLogEntry = readonly [string, ...unknown[]];

/** A binding lookup, as `Interpreter#env` provides it. Throws
 * `PlanesError` (tag `"unknown-name"`) for a name that is not bound. */
export interface Env {
  get(name: string): Traced;
}

export interface InterpreterOptions {
  /** The host: what actually performs `ask`/`read`/`write`/`show`/`clock`
   * and resolves `foreign` targets. Required for any program that
   * performs an effect; `new MemoryHost()`/`new TestHost()` are ready-made
   * stand-ins that need no real filesystem or network. */
  host?: unknown;
  /** Turns on retention-window bookkeeping past `window` generations
   * (R1). Leave `null` (the default: unbounded) unless the host is
   * specifically exercising retention. */
  window?: number | null;
  /** Arms the core-restricted mode (§3.5): a construct outside
   * `grammar/core.json`'s declared port surface throws
   * `CoreRestrictionError` the first time it is reached, rather than
   * running. Off by default. */
  coreOnly?: boolean;
  /** With `coreOnly`, record every distinct non-core construct reached
   * (in `Interpreter#coreReached`) instead of stopping at the first —
   * a census, not a restricted host; see js/interp.mjs's own commentary
   * before relying on this for anything but that census. */
  coreSurvey?: boolean;
  /** Keep full derivation provenance for `why` (default `true`). A host
   * that only needs `show` output and effects, not `why`, can set this
   * `false`. */
  trace?: boolean;
  /** Record an effect log even with `trace: false`, for `replay()`
   * (js/interp.mjs's own export; not re-exported here — pull it from
   * "./interp.mjs" directly if needed). */
  record?: boolean;
}

/**
 * The Planes evaluator. Construct one per run (or reuse across `run()`
 * calls to share bindings, the way js/cli.mjs's `meta` subcommand does for
 * its metacircular stage).
 */
export class Interpreter {
  constructor(options?: InterpreterOptions);
  /** Every `show`n line so far, in order — also `run()`'s return value. */
  readonly output: string[];
  /** Every effect performed so far, in order. */
  readonly effects: EffectLogEntry[];
  /** The top-level bindings this interpreter has executed into. */
  readonly env: Env;
  /** Set only under `coreOnly: true, coreSurvey: true` — every distinct
   * non-core construct reached, each `{construct, category, file, line,
   * approximateLine}` (untyped here: this census shape is
   * survey-mode-only and not part of the ordinary embedding surface). */
  readonly coreReached: unknown[];
  /**
   * Parse and run `src` against this interpreter's env and host, in
   * order. Returns `output` (the same array as `.output`).
   *
   * Throws `PlanesSyntaxError`/`PlanesAmbiguity` on a parse failure,
   * `PlanesError` for a program error, `CoreRestrictionError` under
   * `coreOnly` when the program reaches outside the declared core, and a
   * plain `RangeError` on runaway recursion (mirroring Python's
   * `RecursionError`) — the same four outcomes `js/cli.mjs`'s `run`
   * subcommand reports as `{output, tag, message, effects}`.
   */
  run(src: string): string[];
}

// ================================================================ hosts (js/host.mjs)

/** The host could not do what was asked — distinct from a program error
 * (`PlanesError`): the machine failing, not the program being wrong. */
export class HostError extends Error {
  readonly name: "HostError";
}

/**
 * What a host must provide to run Planes: five effect capabilities
 * (`ask`, `read`, `write`, `show`, `clock`), `resolve` for `foreign`
 * targets, and `parseJson`. `record`/`snapshot`/`appendEvent` are optional
 * no-ops by default. Every method throws `HostError` on the abstract base;
 * a real host overrides what it supports and leaves the rest to throw.
 */
export abstract class Host {
  readonly name: string;
  ask(url: string): string;
  read(path: string): string;
  write(path: string, text: string): void;
  show(text: string): void;
  clock(): number;
  record(entry: unknown): void;
  snapshot(fingerprint: string, entry: unknown): void;
  appendEvent(entry: unknown): void;
  resolve(target: string): (...args: unknown[]) => unknown;
  targetHint(): string;
  parseJson(text: string): unknown;
}

export interface MemoryHostOptions {
  /** Canned `ask` responses: either a `{url: response}` map, or a function
   * `(url) => response` for a host that wants to compute one. */
  responses?: Record<string, string> | ((url: string) => string);
  /** The in-memory filesystem's initial contents, `{path: text}`. */
  files?: Record<string, string>;
  /** A fixed clock reading; omit for `Date.now() / 1000`. */
  now?: number | null;
  cwd?: string;
}

/**
 * A host with the outside world replaced: an in-memory filesystem, a
 * responses map for `ask`, and a fixed or wall clock. The base both
 * `TestHost` (this package's own hermetic tests) and `js/host_browser.mjs`'s
 * `BrowserHost` build on; usable as-is for an embedding host that has no
 * real filesystem or network of its own (a Worker, a sandboxed page).
 */
export class MemoryHost extends Host {
  constructor(options?: MemoryHostOptions);
  /** Every file currently in the in-memory filesystem, `{path: text}} —
   * read this after `run()` to see what a program wrote. */
  readonly files: Record<string, string>;
  /** Every `show`n line, in arrival order (same content as
   * `Interpreter#output` for a program run against this host). */
  readonly shown: string[];
}

/** `MemoryHost` with a fixed clock by default (`now` defaults to
 * `1000000.0`) — reproducible runs for a program that reads the clock. */
export class TestHost extends MemoryHost {
  constructor(options?: MemoryHostOptions);
}
