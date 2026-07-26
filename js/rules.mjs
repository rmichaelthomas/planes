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
// matched against nothing at all.
export class Violation {
  constructor(rule, effect, {
    uncertain = false,
    cleared_by = null,
    narrowed_by = null,
    origins = null,
    vacuous = false,
  } = {}) {
    this.rule = rule;
    this.effect = effect;
    this.uncertain = uncertain;
    this.cleared_by = cleared_by;
    this.narrowed_by = narrowed_by || [];
    this.origins = origins || [];
    this.vacuous = vacuous;
    this.vacuous_situation = null;
  }

  get is_violation() {
    return this.cleared_by === null && !this.vacuous;
  }

  render() {
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

// Does rule `b` cover a strict subset of what rule `a` ranges over? (v2.0 §30.)
// Kind and target only, never assertion.
export function narrows(b, a) {
  if (a.name === b.name) return false;
  if (a.kind !== b.kind) return false;
  return (
    (a.target === null || a.target === undefined) &&
    b.target !== null &&
    b.target !== undefined
  );
}

function targetMatches(rule, effect) {
  if (rule.target === null || rule.target === undefined) return [true, false];
  if (effect.computed) return [true, true];
  return [effect.target === rule.target, false];
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
    if (r.supersedes_fingerprint !== null && r.supersedes_fingerprint !== undefined) {
      const actual = fingerprint(targetRule);
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
    }

    if (targetRule.assertion === r.assertion) dropped.add(r.supersedes);
  }

  return rules.filter((r) => !dropped.has(r.name));
}

function checkPermitsAreRelated(active) {
  const forbids = active.filter((r) => r.assertion === "forbid");
  for (const p of active) {
    if (p.assertion !== "permit") continue;
    const related = forbids.some(
      (f) =>
        f.kind === p.kind &&
        (p.supersedes === f.name || narrows(p, f) || p.target === f.target),
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

function checkConflicts(active) {
  for (let i = 0; i < active.length; i++) {
    const a = active[i];
    for (let j = i + 1; j < active.length; j++) {
      const b = active[j];
      if (a.kind !== b.kind || a.target !== b.target) continue;
      if (narrows(a, b) || narrows(b, a)) continue;
      if (a.supersedes === b.name || b.supersedes === a.name) continue;

      const where =
        `'${a.kind}'` +
        (a.target ? ` to "${escapeStringLiteral(a.target)}"` : "");
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

export function check(rules, surface, declaringFile = null) {
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
    let nKind = 0;
    let nKindSubject = 0;
    let matchedAny = false;
    for (const effect of surface.declared) {
      if (effect.kind !== rule.kind) continue;
      nKind += 1;
      const [matched, uncertain] = targetMatches(rule, effect);
      const subjectOk = subjectMatches(rule, effect, surface, declaringFile);
      if (subjectOk) nKindSubject += 1;
      if (!matched || !subjectOk) continue;
      matchedAny = true;

      let clearer = null;
      for (const p of permits) {
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

  return RuleResults(results, resolvedSubjects);
}
