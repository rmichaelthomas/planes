// js/rules.mjs — the rule-plane checker, ported from rules.py.
//
// Permits, exception resolution, and fingerprinting. shapes.mjs computes a
// program's effect surface; this only consumes it, through the public Surface
// queries (at/targets/touches/declared/kinds/boundaries/originsOf). Matching is
// static and structural — a rule is never triggered; it is only ever checked
// against a surface computed without running anything.
//
// Checked against rules.py by agreement on pass/fail per rule WITH the message
// text (A.3): errors-that-name-the-fix is a language-level commitment, so a
// divergent message is a divergent implementation (test_js_rules.py). rules.py
// is the specification.
//
// Browser-safe (A.7): the only imports are the synchronous pure-JS hash
// (sha256.mjs) and planes_text.mjs. A.2's synchronous hash is what keeps
// fingerprinting off the filesystem, so this module needs no node: import and
// no split.

import { sha256Hex } from "./sha256.mjs";
import { escapeStringLiteral } from "./planes_text.mjs";

export class RuleNotSupported extends Error {
  constructor(message) {
    super(message);
    this.name = "RuleNotSupported";
  }
}

export class RuleConflict extends Error {
  constructor(message) {
    super(message);
    this.name = "RuleConflict";
  }
}

// A stable, content-derived identity for a rule (v2.0 §29): subject, assertion,
// kind, target — never name or line. sha256, truncated to six hex, byte-for-byte
// what rules.py's fingerprint() produces (Phase 1).
export function fingerprint(rule) {
  const canonical = [rule.subject, rule.assertion, rule.kind, rule.target || ""].join(
    "\x1f",
  );
  return sha256Hex(canonical).slice(0, 6);
}

// A rule's condition, exactly as written, for echoing into a message.
export function condition(rule) {
  const verb = rule.assertion === "forbid" ? "may not" : "may";
  let text = `${rule.subject} ${verb} ${rule.kind}`;
  if (rule.target !== null && rule.target !== undefined) {
    text += ` to "${escapeStringLiteral(rule.target)}"`;
  }
  return text;
}

// One forbid rule matched against one effect — or, for the vacuous shape,
// matched against nothing at all. A fifth shape, the contradiction (B3,
// Track 0 #5), is told apart by contradicts_rule: both rules of a declared
// `contradicts` pair matched at least one effect. is_violation is true for
// it, same as a real violation — an authored incompatibility both sides
// actually reach is a real problem with the program.
export class Violation {
  constructor(rule, effect, {
    uncertain = false,
    cleared_by = null,
    narrowed_by = null,
    origins = null,
    vacuous = false,
    contradicts_rule = null,
    contradicts_effect = null,
  } = {}) {
    this.rule = rule;
    this.effect = effect;
    this.uncertain = uncertain;
    this.cleared_by = cleared_by;
    this.narrowed_by = narrowed_by || [];
    this.origins = origins || [];
    this.vacuous = vacuous;
    this.vacuous_situation = null;
    // The other rule of a declared `contradicts` pair, and the effect IT
    // matched — set only for the contradiction shape (B3).
    this.contradicts_rule = contradicts_rule;
    this.contradicts_effect = contradicts_effect;
  }

  get is_violation() {
    if (this.contradicts_rule !== null) return true;
    return this.cleared_by === null && !this.vacuous;
  }

  render() {
    if (this.contradicts_rule !== null) return this._renderContradiction();

    if (this.vacuous) return this._renderVacuous();

    if (this.cleared_by !== null) {
      return (
        `[${this.rule.name}] would have been violated at ` +
        `line ${this.effect.site} — excepted by ` +
        `[${this.cleared_by.name}] ` +
        `(line ${this.cleared_by.line})`
      );
    }

    const lines = [`[${this.rule.name}] violated at line ${this.effect.site}.`];
    lines.push(`  ${this.effect}`);
    if (this.uncertain) {
      lines.push(
        "  target could not be pinned down statically — this " +
          "computed value may or may not be " +
          `"${escapeStringLiteral(this.rule.target)}"`,
      );
    }
    lines.push(
      `  rule declared at line ${this.rule.line}: ${condition(this.rule)}`,
    );
    if (this.narrowed_by.length) {
      const names = this.narrowed_by
        .map((r) => `[${r.name}] (line ${r.line})`)
        .join(", ");
      lines.push(`  narrowed here by ${names}`);
    }
    if (this.origins.length) {
      const parts = [
        ...new Set(this.origins.map(([n, f]) => (f ? `${n} (${f})` : n))),
      ].sort(pyStrCmp);
      lines.push(`  derived from: ${parts.join(", ")}`);
    }
    return lines.join("\n");
  }

  // B3 (Track 0 #5): both rules of a declared `contradicts` pair matched
  // at least one effect in this surface. this.rule is the rule that wrote
  // the `contradicts` clause and this.effect is the effect it matched;
  // contradicts_rule/contradicts_effect are the named rule's own match.
  // Names both rules, one effect each matched, and the declaring rule's
  // `because` if it has one — never the named rule's, since the
  // declaration belongs to the rule that wrote the clause.
  _renderContradiction() {
    const a = this.rule;
    const b = this.contradicts_rule;
    const ea = this.effect;
    const eb = this.contradicts_effect;
    const line =
      `[${a.name}] contradicts [${b.name}]: both apply to this ` +
      `program — [${a.name}] at line ${ea.site} (${ea}), ` +
      `[${b.name}] at line ${eb.site} (${eb})`;
    if (!a.annotation) return line;
    return line + `\n  [${a.name}] because "${a.annotation.text}"`;
  }

  // Every field render() reads, as data rather than prose (H1). A
  // --json --rules consumer gets the rule name, the rule's own
  // kind/target/assertion/because, the specific effect (kind, boundary,
  // target, line) it matched or null for the vacuous shape, and the
  // supersedes/permit outcome (cleared_by) or narrowing sibling
  // (narrowed_by) — every structural fact render()'s prose is built from.
  // `message` is render()'s own text, included verbatim beside the fields
  // so a host can print exactly what text mode prints without re-deriving
  // it (rules.py's Violation.as_json and Rules.swift's Violation.asJSON
  // must agree with this field for field). `origins` dedupes the same way
  // render()'s derivation line does — by the formatted "name (file)"
  // string, not by the raw pair.
  //
  // `contradiction` (B3) is null except for the contradiction shape,
  // where it names both rules of the declared pair and one effect each
  // matched — self-contained, so a consumer reading only this key gets
  // both sides without also reading the top-level rule/effect.
  asJson() {
    const rule = this.rule;
    const effect = this.effect;
    const seen = new Map();
    for (const [n, f] of this.origins) {
      const key = f ? `${n} (${f})` : n;
      if (!seen.has(key)) seen.set(key, [n, f]);
    }
    const origins = [...seen.keys()].sort(pyStrCmp).map((key) => {
      const [n, f] = seen.get(key);
      return { name: n, file: f ?? null };
    });
    return {
      rule: rule.name,
      rule_line: rule.line,
      assertion: rule.assertion,
      kind: rule.kind,
      target: rule.target ?? null,
      condition: condition(rule),
      because: rule.annotation ? rule.annotation.text : null,
      is_violation: this.is_violation,
      vacuous: this.vacuous,
      vacuous_situation: this.vacuous_situation,
      uncertain: this.uncertain,
      effect: effect
        ? {
            kind: effect.kind,
            boundary: effect.boundary,
            target: effect.target,
            line: effect.site,
          }
        : null,
      cleared_by: this.cleared_by
        ? { rule: this.cleared_by.name, line: this.cleared_by.line }
        : null,
      narrowed_by: this.narrowed_by.map((r) => ({ rule: r.name, line: r.line })),
      contradiction: this.contradicts_rule
        ? {
            rule: rule.name,
            effect: effect
              ? {
                  kind: effect.kind,
                  boundary: effect.boundary,
                  target: effect.target,
                  line: effect.site,
                }
              : null,
            with_rule: this.contradicts_rule.name,
            with_effect: {
              kind: this.contradicts_effect.kind,
              boundary: this.contradicts_effect.boundary,
              target: this.contradicts_effect.target,
              line: this.contradicts_effect.site,
            },
          }
        : null,
      origins,
      message: this.render(),
    };
  }

  _renderVacuous() {
    const rule = this.rule;
    const situation = this.vacuous_situation;
    let header, reason, fix;

    if (situation === 1) {
      header =
        `[${rule.name}] (line ${rule.line}) checked nothing ` +
        `— subject '${rule.subject}' resolves in this file, ` +
        `but the program performs no '${rule.kind}' effect ` +
        `at all`;
      reason = "the rule is inert against this program as written";
      fix =
        "check the program still performs the effect you " +
        "expect, or remove the rule if it no longer applies";
    } else if (situation === 3) {
      header =
        `[${rule.name}] (line ${rule.line}) checked nothing ` +
        `— subject '${rule.subject}' derives a ` +
        `'${rule.kind}' effect, but the rule's target ` +
        `excludes every one`;
      reason =
        `'${rule.subject}' reaches this effect kind, but ` +
        `never at "${escapeStringLiteral(rule.target)}"`;
      fix =
        `check the target matches where '${rule.subject}' ` +
        `actually goes, or remove the target to check every ` +
        `'${rule.kind}' effect '${rule.subject}' reaches`;
    } else {
      header =
        `[${rule.name}] (line ${rule.line}) checked nothing ` +
        `— subject '${rule.subject}' resolves in this file, ` +
        `but no '${rule.kind}' effect derives from it`;
      reason =
        `the program performs '${rule.kind}', but to a ` +
        `target that does not derive from '${rule.subject}'`;
      fix =
        "check the subject names the value you meant, or " +
        "write the rule against 'anything'";
    }

    return [header, `  ${reason}`, `  ${fix}`].join("\n");
  }

  toString() {
    return this.render();
  }
}

// check()'s return value: a plain array of Violation with resolvedSubjects
// attached — the readback shapes_cli needs (P-Q20). rules.py subclasses list for
// exactly this; a plain array with one extra property keeps every caller working
// (iteration, .length, indexing, .some(...)) without the Array-subclass hazard
// where .filter/.map reconstruct via the constructor.
export function RuleResults(items = [], resolvedSubjects = []) {
  const arr = [...items];
  arr.resolvedSubjects = [...resolvedSubjects];
  return arr;
}

// Folds only ASCII A-Z to a-z; every other character is left exactly as
// written (B2 follow-up). Scheme and host are DNS-shaped, and DNS
// case-insensitivity is ASCII-only -- a full Unicode lower (String.
// toLowerCase()) can map a character context-dependently (a final Greek
// sigma U+03A3 becomes U+03C2 under some case-folding rules, U+03C3 under
// others), and there is no guarantee another host's Unicode tables agree
// with this one's on the exact mapping. That would silently break the
// byte-for-byte agreement the three hosts promise. Used only where B2 asks
// for case-insensitive comparison (scheme, host); a rule's path stays
// case-sensitive and untouched by this function. Plain UTF-16 code-unit
// indexing is safe here: every code unit this touches (0x41-0x5A) is ASCII
// and can never be half of a surrogate pair. rules.py's and Rules.swift's
// identically-named function must agree with this one.
function asciiLower(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    out += code >= 65 && code <= 90 ? String.fromCharCode(code + 32) : text[i];
  }
  return out;
}

// Is `text` a legal URL scheme (ALPHA *( ALPHA / DIGIT / "+" / "-" / "." ),
// RFC 3986 §3.1)? ASCII-only by construction, so a plain ASCII check.
function isScheme(text) {
  if (!text) return false;
  const first = asciiLower(text[0]);
  if (!(first >= "a" && first <= "z")) return false;
  for (const ch of text.slice(1)) {
    const lower = asciiLower(ch);
    if ((lower >= "a" && lower <= "z") || (ch >= "0" && ch <= "9") || ch === "+" || ch === "-" || ch === ".") {
      continue;
    }
    return false;
  }
  return true;
}

// Split `target` into [scheme, host, path, query, fragment] if it has the
// shape scheme://host[:port][/path][?query][#fragment] (B2); null otherwise
// — a file path, a queue:send-style name, or console text, none of which are
// addresses this matches by host and path (B2 keeps those on today's
// exact-string matching, unchanged).
//
// query and fragment carry their leading "?"/"#" when present, else null. No
// percent-decoding, no Unicode normalisation, no default-port folding: every
// piece is exactly the substring as written (B2). rules.py's
// _parse_url_target and Rules.swift's parseURLTarget must agree with this.
function parseUrlTarget(target) {
  const sep = target.indexOf("://");
  if (sep <= 0 || !isScheme(target.slice(0, sep))) return null;
  const scheme = target.slice(0, sep);
  const rest = target.slice(sep + 3);
  let hostEnd = rest.length;
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "/" || rest[i] === "?" || rest[i] === "#") {
      hostEnd = i;
      break;
    }
  }
  const host = rest.slice(0, hostEnd);
  const tail = rest.slice(hostEnd);
  let path, remainder;
  if (tail[0] === "?" || tail[0] === "#") {
    path = "";
    remainder = tail;
  } else {
    let pathEnd = tail.length;
    for (let i = 0; i < tail.length; i++) {
      if (tail[i] === "?" || tail[i] === "#") {
        pathEnd = i;
        break;
      }
    }
    path = tail.slice(0, pathEnd);
    remainder = tail.slice(pathEnd);
  }
  let query, fragment;
  if (remainder[0] === "#") {
    query = null;
    fragment = remainder;
  } else if (remainder[0] === "?") {
    const hashAt = remainder.indexOf("#");
    if (hashAt < 0) {
      query = remainder;
      fragment = null;
    } else {
      query = remainder.slice(0, hashAt);
      fragment = remainder.slice(hashAt);
    }
  } else {
    query = null;
    fragment = null;
  }
  return [scheme, host, path, query, fragment];
}

// Does rulePath cover effectPath at a "/" boundary (B2)? An empty path or "/"
// in the rule covers every path on the host. Otherwise rulePath must be a
// prefix of effectPath, and either they're equal, rulePath itself already
// ends in "/" (everything under it is covered), or the next character of
// effectPath past the prefix is "/". Compared case-sensitively, exactly as
// written.
function pathCovers(rulePath, effectPath) {
  if (rulePath === "" || rulePath === "/") return true;
  if (effectPath === rulePath) return true;
  if (!effectPath.startsWith(rulePath)) return false;
  if (rulePath.endsWith("/")) return true;
  return effectPath.slice(rulePath.length, rulePath.length + 1) === "/";
}

// Does the URL-shaped ruleTarget cover the URL-shaped effectTarget (B2)? Same
// scheme and host, compared case-insensitively; port is part of the host and
// compared exactly as written -- no default-port folding, so "https://x" and
// "https://x:443" differ. The effect's own query and fragment are ignored
// entirely -- only its path is compared, against the rule's path.
function urlCovers(ruleTarget, effectTarget) {
  const [rScheme, rHost, rPath] = parseUrlTarget(ruleTarget);
  const [eScheme, eHost, ePath] = parseUrlTarget(effectTarget);
  if (asciiLower(rScheme) !== asciiLower(eScheme)) return false;
  if (asciiLower(rHost) !== asciiLower(eHost)) return false;
  return pathCovers(rPath, ePath);
}

// Does every address `narrow` (a target string, or null/undefined) ranges
// over also fall inside `wide`'s range (B2)? null/undefined is the top of
// the lattice -- every target of the kind. Identical strings are always the
// same scope. A URL-shaped pair compares by urlCovers; anything else -- a
// target that isn't URL-shaped, or a URL paired with a non-URL -- only ever
// covers its own exact string, exactly as before B2.
function scopeCovers(wide, narrow) {
  if (wide === null || wide === undefined) return true;
  if (narrow === null || narrow === undefined) return false;
  if (wide === narrow) return true;
  if (parseUrlTarget(wide) === null || parseUrlTarget(narrow) === null) return false;
  return urlCovers(wide, narrow);
}

// Do a and b (two rule targets, or null/undefined) range over exactly the
// same addresses (B2)? Equal by mutual coverage rather than ===, so
// "https://x" and "https://x/" -- two spellings of "every path on x" -- are
// the same scope even though the strings differ.
function sameScope(a, b) {
  return scopeCovers(a, b) && scopeCovers(b, a);
}

// The set of effect kinds this rule's declared kind matches against (B1,
// Sprint B, Track 0 #10). Must agree with rules.py's _covered_kinds. Only a
// FORBID on "ask" widens (forbidding ask also forbids send, the same
// network boundary's outbound half); a PERMIT never widens ("may ask to X"
// permits only ask, "may send to X" permits only send); a forbid on any
// other kind, including "send" itself, covers only itself. Orthogonal to
// B2's scope generalisation above: this is about which KINDS a rule's
// declared kind stands for, scopeCovers/sameScope are about which ADDRESSES
// its target stands for. narrows and checkConflicts combine both.
export function coveredKinds(rule) {
  if (rule.assertion === "forbid" && rule.kind === "ask") {
    return new Set(["ask", "send"]);
  }
  return new Set([rule.kind]);
}

function overlaps(a, b) {
  for (const k of a) if (b.has(k)) return true;
  return false;
}

// Does rule `b` cover a strict subset of what rule `a` ranges over? (v2.0
// §30; re-proven for host/path covering at B2, and for kind covering at
// B1.) Two dimensions, both required, never assertion:
//   - KIND: a's and b's covered kinds (coveredKinds, B1) must overlap.
//     Comparable within the same literal kind (as before B1 -- coveredKinds
//     always includes a rule's own kind); also comparable across ask/send
//     when a forbid's widened coverage reaches a narrower rule's kind -- a
//     `may send to X/public` permit can narrow a bare `may not ask` forbid
//     the same way a `may ask to X/public` permit already did.
//   - SCOPE: a's target must cover b's (B2's scopeCovers) and the two must
//     not be the SAME scope -- the pre-B2 case (a has no target, b does) is
//     one instance; a rule whose covered address set is strictly inside
//     another's target now is too.
// Two rules with overlapping kinds and the same scope are equally specific
// -- neither narrows the other; that pair is checkConflicts's job.
export function narrows(b, a) {
  if (a.name === b.name) return false;
  if (!overlaps(coveredKinds(a), coveredKinds(b))) return false;
  return scopeCovers(a.target, b.target) && !scopeCovers(b.target, a.target);
}

// (matched, uncertain). No target on the rule means every target of the kind
// -- always a certain match. Otherwise, for a computed effect target: a
// possible match unless its known chunks rule the rule's target out (v37.0
// §513, B2's patternExcludes). For a literal effect target: when both it and
// the rule's target are URL-shaped, the rule's target must COVER the
// effect's -- the same address, or anything under it (B2), the effect's own
// query and fragment ignored; otherwise (a file path, a queue:send-style
// name, console text) an exact string match, exactly as before B2.
function targetMatches(rule, effect) {
  if (rule.target === null || rule.target === undefined) return [true, false];
  if (effect.computed) {
    if (patternExcludes(rule.target, effect.target)) return [false, false];
    return [true, true];
  }
  if (parseUrlTarget(rule.target) !== null && parseUrlTarget(effect.target) !== null) {
    return [urlCovers(rule.target, effect.target), false];
  }
  return [effect.target === rule.target, false];
}

const HOLE = "{...}";
const NO_DESTINATION = " (destination not stated)";

// rules.py's _pattern_excludes, which this must agree with: can a computed
// target provably never be covered by the rule's target (B2; originally
// "never equal", v37.0 §513)? When the rule's target isn't URL-shaped,
// covering is exact-string equality, unchanged since v37.0
// (exactPatternExcludes). When it is, B2 re-proves the guard for host/path
// covering (urlPatternExcludes). A target with no hole, or a foreign's
// "(destination not stated)", excludes nothing either way.
function patternExcludes(ruleTarget, effectTarget) {
  if (!effectTarget.includes(HOLE) || effectTarget.endsWith(NO_DESTINATION)) return false;
  const ruleUrl = parseUrlTarget(ruleTarget);
  if (ruleUrl === null) return exactPatternExcludes(ruleTarget, effectTarget);
  const [rScheme, rHost, rPath] = ruleUrl;
  return urlPatternExcludes(rScheme, rHost, rPath, effectTarget);
}

// The v37.0 §513 algorithm, unchanged: can this pattern never equal
// ruleTarget as a flat string? Its known chunks must appear in it in order --
// the first anchored to the start, the last to the end, unless the pattern
// opens or closes with a hole -- with a hole free to stand for any text,
// including none. Still what governs a rule target B2 leaves on exact
// matching (not URL-shaped: a file path, a queue:send-style name, console
// text). Plain string search is code-point exact here: a well-formed chunk
// cannot match across a surrogate pair.
function exactPatternExcludes(ruleTarget, effectTarget) {
  const chunks = effectTarget.split(HOLE);
  const first = chunks[0];
  const last = chunks[chunks.length - 1];
  if (first.length + last.length > ruleTarget.length) return true;
  if (!ruleTarget.startsWith(first) || !ruleTarget.endsWith(last)) return true;
  let pos = first.length;
  const end = ruleTarget.length - last.length;
  for (const chunk of chunks.slice(1, -1)) {
    const at = ruleTarget.indexOf(chunk, pos);
    if (at < 0 || at + chunk.length > end) return true;
    pos = at + chunk.length;
  }
  return false;
}

// B2's re-proof of the v37.0 §513 guard for a URL-shaped rule target: can
// this computed target's KNOWN prefix -- the literal text before its first
// hole, which is a true, certain prefix of whatever the hole goes on to
// produce (v37.0 §511) -- prove no completion could ever be covered by the
// rule?
//
// Reasons from that one chunk only. It's the one piece of the pattern
// guaranteed to survive regardless of what any hole produces, so a proof
// built from it alone is sound: it can only prove exclusions that are real.
// A later chunk could in principle prove more, but skipping it only means
// staying uncertain more often -- the conservative side of the guarantee
// ("when in doubt, don't exclude").
function urlPatternExcludes(rScheme, rHost, rPath, effectTarget) {
  const first = effectTarget.split(HOLE)[0];
  const sep = first.indexOf("://");
  if (sep <= 0 || !isScheme(first.slice(0, sep))) return false;
  if (asciiLower(first.slice(0, sep)) !== asciiLower(rScheme)) return true;

  const remainder = first.slice(sep + 3);
  let term = remainder.length;
  for (let i = 0; i < remainder.length; i++) {
    if (remainder[i] === "/" || remainder[i] === "?" || remainder[i] === "#") {
      term = i;
      break;
    }
  }
  if (term === remainder.length) {
    // The host itself isn't fully known here -- only a prefix of it is,
    // from this chunk. Whatever it resolves to will still start with this
    // prefix, so a rule host that does NOT start with it can never be
    // that host.
    return !asciiLower(rHost).startsWith(asciiLower(remainder));
  }

  const eHost = remainder.slice(0, term);
  const rest = remainder.slice(term);
  if (asciiLower(eHost) !== asciiLower(rHost)) return true;

  if (rest[0] === "?" || rest[0] === "#") {
    // The path is fully known here, from certain text -- and empty.
    return rPath !== "" && rPath !== "/";
  }

  const knownPath = rest;
  if (rPath === "" || rPath === "/") return false;
  const lr = rPath.length;
  if (knownPath.length < lr) return knownPath !== rPath.slice(0, knownPath.length);
  if (knownPath.slice(0, lr) !== rPath) return true;
  if (knownPath.length === lr) return false;
  return knownPath[lr] !== "/";
}

// Code-point string compare, matching Python's sorted() (see shapes.mjs).
function pyStrCmp(a, b) {
  if (a === b) return 0;
  const ca = [...a];
  const cb = [...b];
  const n = Math.min(ca.length, cb.length);
  for (let i = 0; i < n; i++) {
    const x = ca[i].codePointAt(0);
    const y = cb[i].codePointAt(0);
    if (x !== y) return x < y ? -1 : 1;
  }
  return ca.length < cb.length ? -1 : ca.length > cb.length ? 1 : 0;
}

function resolveSubject(rule, surface, declaringFile) {
  const allOrigins = [];
  for (const effect of surface.declared) {
    allOrigins.push(...surface.originsOf(effect));
  }
  const hits = allOrigins.filter(([n]) => n === rule.subject).map(([, f]) => f);
  if (hits.includes(declaringFile)) return;
  if (hits.length) {
    const other = hits[0];
    throw new RuleNotSupported(
      `rule [${rule.name}] (line ${rule.line}): subject ` +
        `'${rule.subject}' only resolves in ${other}, not in the file ` +
        `that declares this rule — a rule cannot reach across an ` +
        `import boundary to a name it never saw declared\n` +
        `  write the rule in ${other} instead, or name a subject ` +
        `local to this file`,
    );
  }
  throw new RuleNotSupported(
    `rule [${rule.name}] (line ${rule.line}): subject ` +
      `'${rule.subject}' does not resolve to anything in the traced ` +
      `effect surface — checking it needs a value this file's ` +
      `derivation graph can reach\n` +
      `  check the name is spelled as it appears in this file, or ` +
      `write the rule against 'anything' instead`,
  );
}

function subjectMatches(rule, effect, surface, declaringFile) {
  if (rule.subject === "anything") return true;
  const origins = surface.originsOf(effect);
  return origins.some(([n, f]) => n === rule.subject && f === declaringFile);
}

function resolveActive(rules) {
  const byName = new Map();
  for (const r of rules) {
    if (byName.has(r.name)) {
      const other = byName.get(r.name);
      throw new RuleConflict(
        `two rules are both named [${r.name}] (line ${other.line} ` +
          `and line ${r.line}) — a rule name must be unique\n` +
          `  rename one of them`,
      );
    }
    byName.set(r.name, r);
  }

  const dropped = new Set();
  for (const r of rules) {
    if (r.supersedes === null || r.supersedes === undefined) continue;
    if (r.supersedes === r.name) {
      throw new RuleConflict(
        `rule [${r.name}] (line ${r.line}) supersedes itself\n` +
          `  supersedes should name an earlier, different rule`,
      );
    }
    if (!byName.has(r.supersedes)) {
      throw new RuleConflict(
        `rule [${r.name}] (line ${r.line}) supersedes ` +
          `[${r.supersedes}], which is not a rule in this file\n` +
          `  check the name, or remove the supersedes clause`,
      );
    }

    const targetRule = byName.get(r.supersedes);
    const actual = fingerprint(targetRule);
    // B3 (Track 0 #3): a supersedes clause with no fingerprint at all is
    // refused — the parser cannot know the other rule's fingerprint, so
    // this is where the requirement is enforced, with the named rule
    // actually in hand to compute one from.
    if (r.supersedes_fingerprint === null || r.supersedes_fingerprint === undefined) {
      throw new RuleConflict(
        `rule [${r.name}] (line ${r.line}) supersedes ` +
          `[${r.supersedes}] (line ${targetRule.line}) without its ` +
          `fingerprint\n` +
          `  write supersedes [${r.supersedes}] @${actual}`,
      );
    }
    if (actual !== r.supersedes_fingerprint) {
      throw new RuleConflict(
        `rule [${r.name}] (line ${r.line}) supersedes ` +
          `[${r.supersedes}] (line ${targetRule.line}) as of ` +
          `@${r.supersedes_fingerprint}, but [${r.supersedes}] ` +
          `is now @${actual} — it changed after [${r.name}] was ` +
          `written to override it\n` +
          `  confirm the override still means what it meant, ` +
          `then update the fingerprint to @${actual}`,
      );
    }

    if (targetRule.assertion === r.assertion) dropped.add(r.supersedes);
  }

  // B3 (Track 0 #5): `contradicts` resolution — same error class as
  // supersedes above. Checked against byName (every named rule), whether
  // or not either side later gets dropped above, since these are facts
  // about the clause as written.
  const contradictedPairs = new Map();
  for (const r of rules) {
    if (r.contradicts === null || r.contradicts === undefined) continue;
    if (r.contradicts === r.name) {
      throw new RuleConflict(
        `rule [${r.name}] (line ${r.line}) contradicts itself\n` +
          `  contradicts should name a different rule`,
      );
    }
    if (!byName.has(r.contradicts)) {
      throw new RuleConflict(
        `rule [${r.name}] (line ${r.line}) contradicts ` +
          `[${r.contradicts}], which is not a rule in this file\n` +
          `  check the name, or remove the contradicts clause`,
      );
    }
    const pairKey = [r.name, r.contradicts].sort().join("\x1f");
    if (contradictedPairs.has(pairKey)) {
      const first = contradictedPairs.get(pairKey);
      throw new RuleConflict(
        `rule [${r.name}] (line ${r.line}) contradicts ` +
          `[${r.contradicts}], but [${first.name}] (line ` +
          `${first.line}) already contradicts [${first.contradicts}] ` +
          `— the pair only needs declaring once\n` +
          `  remove the contradicts clause from one of them`,
      );
    }
    contradictedPairs.set(pairKey, r);
  }

  return rules.filter((r) => !dropped.has(r.name));
}

// B2: a rule target names an address, not a request. The matcher ignores an
// EFFECT's own query string and fragment (B2 §3) -- but a query or fragment
// written into the RULE's own target is an authoring mistake, not something
// to silently drop, so a URL-shaped target carrying one is refused before
// any matching runs. Checked for every declared rule, forbid or permit,
// superseded or not.
function checkTargetIsAnAddress(rule) {
  if (rule.target === null || rule.target === undefined) return;
  const parsed = parseUrlTarget(rule.target);
  if (parsed === null) return;
  const [, , , query, fragment] = parsed;
  if (query === null && fragment === null) return;
  throw new RuleConflict(
    `rule [${rule.name}] (line ${rule.line}): target ` +
      `"${escapeStringLiteral(rule.target)}" has a query string or ` +
      `fragment — a rule target names an address, and only an ` +
      `effect's own query and fragment are ever ignored, never the ` +
      `rule's\n` +
      `  drop everything from the "?" or "#" onward`,
  );
}

function checkPermitsAreRelated(active) {
  const forbids = active.filter((r) => r.assertion === "forbid");
  for (const p of active) {
    if (p.assertion !== "permit") continue;
    // B1: coveredKinds(f) replaces the old f.kind === p.kind -- a "send"
    // permit can be related to (named in supersedes, share a scope with, or
    // be strictly narrower in BOTH scope and kind than) an "ask" forbid,
    // since forbidding ask also forbids send. narrows(p, f) is itself now
    // generalised the same way (kind overlap, not literal equality), so a
    // `may send to X/public` permit narrows a bare `may not ask` forbid
    // automatically, no supersedes needed. Only an equal-scope cross-kind
    // pair still demands an explicit supersedes -- checkConflicts's job.
    const related = forbids.some(
      (f) =>
        coveredKinds(f).has(p.kind) &&
        (p.supersedes === f.name || narrows(p, f) || sameScope(p.target, f.target)),
    );
    if (!related) {
      throw new RuleConflict(
        `rule [${p.name}] (line ${p.line}) permits '${p.kind}' but ` +
          `excepts no forbid rule — a permit only has force ` +
          `against a prohibition it supersedes or narrows\n` +
          `  add 'supersedes [name-of-the-forbid-rule]' to ` +
          `[${p.name}], or give it a target that narrows one of ` +
          `the forbid rules over '${p.kind}'`,
      );
    }
  }
}

// Equal-specificity conflicts (v2.0 §32; B2's sameScope in place of === on
// the target; B1's coveredKinds overlap in place of === on the kind for an
// opposite-assertion pair). Same assertion + different literal kind (two
// forbids, one ask one send) never conflicts -- both prohibit, so stacking
// agrees about everything. Opposite assertion + overlapping covered kinds +
// same scope does conflict -- "rule [deny] anything may not ask to X"
// beside "rule [also] anything may send to X", with no supersedes, is
// exactly such a pair -- resolved the same way as the same-kind case: an
// explicit supersedes naming the forbid. A strictly narrower scope needs no
// supersedes at all, since narrows (generalised the same way) resolves it.
function checkConflicts(active) {
  for (let i = 0; i < active.length; i++) {
    const a = active[i];
    for (let j = i + 1; j < active.length; j++) {
      const b = active[j];
      if (!sameScope(a.target, b.target)) continue;
      if (a.assertion === b.assertion) {
        if (a.kind !== b.kind) continue;
      } else if (![...coveredKinds(a)].some((k) => coveredKinds(b).has(k))) {
        continue;
      }
      if (narrows(a, b) || narrows(b, a)) continue;
      if (a.supersedes === b.name || b.supersedes === a.name) continue;

      let where;
      if (a.kind === b.kind) {
        where =
          `'${a.kind}'` +
          (a.target ? ` to "${escapeStringLiteral(a.target)}"` : "");
      } else {
        const overlap = [...coveredKinds(a)]
          .filter((k) => coveredKinds(b).has(k))
          .sort();
        where =
          `'${a.kind}' and '${b.kind}' (both reach ${overlap.join("/")})` +
          (a.target ? ` to "${escapeStringLiteral(a.target)}"` : "");
      }
      if (a.assertion !== b.assertion) {
        const [forbid, permit] = a.assertion === "forbid" ? [a, b] : [b, a];
        throw new RuleConflict(
          `rule [${forbid.name}] (line ${forbid.line}) and rule ` +
            `[${permit.name}] (line ${permit.line}) demand ` +
            `opposite things over ${where} — one forbids it, the ` +
            `other permits it, and neither narrows nor ` +
            `supersedes the other\n` +
            `  add 'supersedes [${forbid.name}]' to ` +
            `[${permit.name}] to make the exception explicit, or ` +
            `give one of them a target the other lacks`,
        );
      }
      throw new RuleConflict(
        `rule [${a.name}] (line ${a.line}) and rule [${b.name}] ` +
          `(line ${b.line}) are equally specific over ${where} — ` +
          `neither narrows nor supersedes the other\n` +
          `  add 'supersedes [${a.name}]' to [${b.name}] (or the ` +
          `reverse), or give one of them a target the other lacks`,
      );
    }
  }
}

// Does this rule's condition match at least one effect in the surface (B3,
// Track 0 #5)? A rule *applies* when it matches, whether as a forbid rule
// that would be violated or cleared, or as a permit rule that matched an
// effect; a rule matching nothing (vacuous) does not apply. For a forbid
// rule this is the same widen-on-uncertainty rule the vacuous check uses;
// for a permit rule an uncertain match must NOT count — the conservatism
// flips at the permit boundary (v2.0 §34b), the same asymmetry `clearer`
// matching above uses. Returns [applies, firstMatchingEffectOrNull] — the
// first effect by surface.declared's existing ordering.
function ruleApplies(rule, surface, declaringFile) {
  for (const effect of surface.declared) {
    if (effect.kind !== rule.kind) continue;
    const [matched, uncertain] = targetMatches(rule, effect);
    if (!matched) continue;
    if (rule.assertion === "permit" && uncertain) continue;
    if (!subjectMatches(rule, effect, surface, declaringFile)) continue;
    return [true, effect];
  }
  return [false, null];
}

// Contradiction violations (B3, Track 0 #5): every declared `contradicts`
// pair where both rules apply to this surface. Iterates `active` in its
// existing order, so this is deterministic and identical across hosts given
// the same source. resolveActive already refused declaring the same pair
// from both sides, so at most one of the two rules carries the
// `contradicts` clause and no pair is ever reported twice. A pair naming a
// rule resolveActive dropped (superseded away) can never fire: a dropped
// rule is not in `active` and so cannot apply.
function checkContradictions(active, surface, declaringFile) {
  const byName = new Map(active.map((r) => [r.name, r]));
  const results = [];
  for (const r of active) {
    if (r.contradicts === null || r.contradicts === undefined) continue;
    const other = byName.get(r.contradicts);
    if (!other) continue;
    const [applies, effect] = ruleApplies(r, surface, declaringFile);
    if (!applies) continue;
    const [otherApplies, otherEffect] = ruleApplies(other, surface, declaringFile);
    if (!otherApplies) continue;
    results.push(
      new Violation(r, effect, {
        contradicts_rule: other,
        contradicts_effect: otherEffect,
      }),
    );
  }
  return results;
}

export function check(rules, surface, declaringFile = null) {
  for (const rule of rules) {
    checkTargetIsAnAddress(rule);
  }

  const resolvedSubjects = [];
  for (const rule of rules) {
    if (rule.subject !== "anything") {
      resolveSubject(rule, surface, declaringFile);
      resolvedSubjects.push(rule.subject);
    }
  }

  const active = resolveActive(rules);
  checkPermitsAreRelated(active);
  checkConflicts(active);

  const forbids = active.filter((r) => r.assertion === "forbid");
  const permits = active.filter((r) => r.assertion === "permit");

  const results = [];
  for (const rule of forbids) {
    const covered = coveredKinds(rule);
    let nKind = 0;
    let nKindSubject = 0;
    let matchedAny = false;
    for (const effect of surface.declared) {
      if (!covered.has(effect.kind)) continue;
      nKind += 1;
      const [matched, uncertain] = targetMatches(rule, effect);
      const subjectOk = subjectMatches(rule, effect, surface, declaringFile);
      if (subjectOk) nKindSubject += 1;
      if (!matched || !subjectOk) continue;
      matchedAny = true;

      let clearer = null;
      for (const p of permits) {
        // A permit never widens: it clears an effect only when its own
        // kind is the effect's actual kind, exactly -- "a permit for ask
        // never clears a forbidden send" (B1, Track 0 #10).
        if (p.kind !== effect.kind) continue;
        if (!(p.supersedes === rule.name || narrows(p, rule))) continue;
        const [pMatched, pUncertain] = targetMatches(p, effect);
        if (
          pMatched &&
          !pUncertain &&
          subjectMatches(p, effect, surface, declaringFile)
        ) {
          clearer = p;
          break;
        }
      }

      const origins = surface.originsOf(effect);
      if (clearer !== null) {
        results.push(
          new Violation(rule, effect, { uncertain, cleared_by: clearer, origins }),
        );
        continue;
      }

      const narrowers = forbids.filter(
        (other) =>
          other !== rule && narrows(other, rule) && targetMatches(other, effect)[0],
      );
      results.push(
        new Violation(rule, effect, { uncertain, narrowed_by: narrowers, origins }),
      );
    }

    if (rule.subject !== "anything" && !matchedAny) {
      const vacuous = new Violation(rule, null, { vacuous: true });
      if (nKind === 0) vacuous.vacuous_situation = 1;
      else if (nKindSubject === 0) vacuous.vacuous_situation = 2;
      else vacuous.vacuous_situation = 3;
      results.push(vacuous);
    }
  }

  results.push(...checkContradictions(active, surface, declaringFile));

  return RuleResults(results, resolvedSubjects);
}
