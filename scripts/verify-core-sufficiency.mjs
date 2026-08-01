#!/usr/bin/env node
// scripts/verify-core-sufficiency.mjs — the verification gate for this build.
//
// THE RETIREMENT RULE APPLIES TO THIS FILE. A verification script graduates into
// a suite or is deleted when its build merges — there is no third option, in
// either language (scripts/ci.sh states it at length, and test_gate.py enforces
// the name in every executable extension). The structural half of what this
// asserts is already in test_js_core_restricted.py, which ci.sh runs on every
// gate; what is here and not there is the cross-tree byte-identity check, which
// needs a git worktree of main and does not belong in a suite. This file goes
// when the build merges.
//
// Inputs required from Rob: NONE. Every question below has a machine-checkable
// answer.
//
//   A  the restriction FIRES, at evaluation, naming construct + file + line
//   B  all seven effect kinds pass under restriction        (reported)
//   C  identical when off — byte-for-byte against main, whole corpus
//   D  both readers agree — core_check.py and the JS mode, every name
//   E  the graph, per file                                  (reported)
//   F  ANTI-VACUITY — break each subject, confirm the assertion fails
//
// A, C, D and F block. B and E are reported: a refusal in E is the finding this
// build exists to produce, and blocking on it would mean the build could only
// succeed by finding nothing.

import { execFileSync, execFileSync as run } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MAIN = "90d5ae9"; // the base this branch measures against
const rows = [];
let blockingFailures = 0;

function record(group, name, ok, detail, blocking = true) {
  rows.push({ group, name, ok, detail, blocking });
  if (!ok && blocking) blockingFailures += 1;
  const mark = ok ? "PASS" : blocking ? "FAIL" : "note";
  console.log(`  ${mark}  [${group}] ${name}${detail ? ` — ${detail}` : ""}`);
}

function cli(args, cwd = REPO) {
  return run("node", ["js/cli.mjs", ...args], {
    cwd,
    encoding: "utf-8",
    maxBuffer: 1 << 28,
  });
}

function cliJson(args, cwd = REPO) {
  return JSON.parse(cli(args, cwd));
}

function corpus(cwd = REPO) {
  const out = [];
  const walk = (d) => {
    for (const e of fs.readdirSync(path.join(cwd, d), { withFileTypes: true })) {
      const rel = d === "." ? e.name : `${d}/${e.name}`;
      if (e.isDirectory()) {
        if (e.name === ".venv" || e.name === ".git" || e.name === "node_modules") continue;
        walk(rel);
      } else if (e.name.endsWith(".planes")) out.push(rel);
    }
  };
  walk(".");
  return out.sort();
}

function standalone(files, cwd = REPO) {
  return files.filter(
    (f) =>
      !fs
        .readFileSync(path.join(cwd, f), "utf-8")
        .split("\n")
        .some((l) => l.trim().startsWith("use ")),
  );
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "core-suff-"));
function scratch(name, text) {
  const p = path.join(tmp, name);
  fs.writeFileSync(p, text);
  return p;
}

// A core.json with one edit — for group F, so a crafted core can be run end to
// end rather than only reasoned about.
function craftedCore(mutate) {
  const doc = JSON.parse(
    fs.readFileSync(path.join(REPO, "grammar", "core.json"), "utf-8"),
  );
  mutate(doc);
  return scratch(`core-${rows.length}.json`, JSON.stringify(doc));
}

const LET_PROGRAM =
  "total = 0\n" +
  "for each n in [1, 2, 3]:\n" +
  "  let doubled = n * 2\n" +
  "  total = total + doubled\n" +
  "show total\n";

const SEVEN_EFFECTS =
  'use file\n' +
  'use http\n' +
  'foreign now from "time.time" doing clock\n' +
  'foreign pick from "random.random" doing random\n' +
  'foreign here from "os.getcwd" doing env\n' +
  'write { a: 1 } to "out.json"\n' +
  'body = ask "https://example.test/x"\n' +
  'seen = read "out.json"\n' +
  't = now\nr = pick\nw = here\n' +
  'show "did them all"\n';
const EFFECT_CONFIG = JSON.stringify({
  responses: { "https://example.test/x": '{"ok": true}' },
});

console.log("verify-core-sufficiency — is grammar/core.json's declared core enough?\n");

// ============================================================ A — it fires
console.log("A. the restriction fires, at evaluation");
{
  const p = scratch("uses_let.planes", LET_PROGRAM);
  const got = cliJson(["run-file", "--core", p]);
  const c = got.core ?? {};
  record(
    "A",
    "a `let` program refuses under --core",
    got.core !== undefined,
    got.core ? "" : `no refusal: ${JSON.stringify(got).slice(0, 120)}`,
  );
  record("A", "the refusal names the construct", c.construct === "let", `got ${c.construct}`);
  record(
    "A",
    "the refusal names the file",
    typeof c.file === "string" && fs.realpathSync(c.file) === fs.realpathSync(p),
    `got ${c.file}`,
  );
  record(
    "A",
    "the refusal names the line, exactly",
    c.line === 3 && c.approximateLine === false,
    `got line ${c.line}, approximate=${c.approximateLine}`,
  );
  record(
    "A",
    "nothing ran before the refusal",
    Array.isArray(got.output) && got.output.length === 0,
    `output=${JSON.stringify(got.output)}`,
  );
  const off = cliJson(["run-file", p]);
  record(
    "A",
    "the same program runs clean with the flag OFF",
    off.core === undefined && JSON.stringify(off.output) === '["12"]',
    JSON.stringify(off.output),
  );
  // The restriction must be evaluation-time, not a source scan: a `let` the run
  // never REACHES must not refuse. This is the assertion that separates this
  // build from a second copy of core_check.py.
  const unreached = scratch(
    "unreached_let.planes",
    "to never-called of n:\n  let x = n * 2\n  give x\nshow 1\n",
  );
  const u = cliJson(["run-file", "--core", unreached]);
  record(
    "A",
    "a `let` in an UNCALLED function does not refuse (runtime, not static)",
    u.core === undefined && JSON.stringify(u.output) === '["1"]',
    u.core ? `refused at ${u.core.file}:${u.core.line}` : JSON.stringify(u.output),
  );
}

// ============================================================ B — effect kinds
console.log("\nB. all seven effect kinds pass under restriction (reported)");
{
  const p = scratch("seven.planes", SEVEN_EFFECTS);
  const got = cliJson(["run-file", "--core", p, EFFECT_CONFIG]);
  const kinds = new Set((got.effects ?? []).map((e) => e[0]));
  const want = ["ask", "clock", "env", "random", "read", "show", "write"];
  record(
    "B",
    "seven effect kinds performed, none flagged",
    got.core === undefined && want.every((k) => kinds.has(k)),
    got.core
      ? `refused on ${got.core.construct}`
      : `performed ${[...kinds].sort().join(", ")}`,
    false,
  );
}

// ============================================================ C — identical off
console.log("\nC. identical when off — byte-for-byte against main, whole corpus");
{
  const wt = fs.mkdtempSync(path.join(os.tmpdir(), "planes-main-"));
  execFileSync("git", ["worktree", "add", "--detach", wt, MAIN], {
    cwd: REPO,
    stdio: "pipe",
  });
  try {
    const all = corpus();
    const std = standalone(all);
    for (const [stage, files] of [
      ["lex", all],
      ["parse", std],
      ["run", std],
    ]) {
      const a = cli(["meta", stage, ...files]);
      const b = cli(["meta", stage, ...files], wt);
      record(
        "C",
        `meta ${stage} (${files.length} files) is byte-identical to ${MAIN}`,
        a === b,
        `${a.length} bytes here, ${b.length} there`,
      );
    }
  } finally {
    execFileSync("git", ["worktree", "remove", "--force", wt], {
      cwd: REPO,
      stdio: "pipe",
    });
  }
}

// ============================================================ D — readers agree
console.log("\nD. both readers agree — core_check.py and the JS mode");
{
  const js = cliJson(["core-classify"]);
  const py = JSON.parse(
    run(
      "python3",
      [
        "-c",
        "import json,core_check;from lexer import KEYWORDS;from parser import BUILTIN_NAMES;" +
          "k,b,_=core_check.load_core();" +
          "print(json.dumps({'keywords':sorted(k),'builtins':sorted(b)," +
          "'allKeywords':sorted(KEYWORDS),'allBuiltins':sorted(BUILTIN_NAMES)}))",
      ],
      { cwd: REPO, encoding: "utf-8" },
    ),
  );
  record(
    "D",
    "the same core keyword set",
    JSON.stringify(js.keywords) === JSON.stringify(py.keywords),
    `js ${js.keywords.length}, py ${py.keywords.length}`,
  );
  record(
    "D",
    "the same core builtin set",
    JSON.stringify(js.builtins) === JSON.stringify(py.builtins),
    `js ${js.builtins.length}, py ${py.builtins.length}`,
  );
  const kwDisagree = py.allKeywords.filter(
    (w) => py.keywords.includes(w) !== js.keywords.includes(w),
  );
  const biDisagree = py.allBuiltins.filter(
    (w) => py.builtins.includes(w) !== js.builtins.includes(w),
  );
  record(
    "D",
    `every one of the ${py.allKeywords.length} keywords classified the same`,
    kwDisagree.length === 0,
    kwDisagree.join(", "),
  );
  record(
    "D",
    `every one of the ${py.allBuiltins.length} builtins classified the same`,
    biDisagree.length === 0,
    biDisagree.join(", "),
  );
  record(
    "D",
    "the node -> keyword map covers every keyword (nothing is invisible)",
    js.coverageGaps.length === 0,
    js.coverageGaps.join(", "),
  );
}

// ============================================================ E — the graph
console.log("\nE. the module graph, per file (reported — a refusal here IS the finding)");
const graphRows = [];
{
  const all = corpus();
  const std = standalone(all);
  const modules = JSON.parse(
    run(
      "python3",
      [
        "-c",
        "import json,os,core_check as c;" +
          "t=os.path.join('grammar','interp.planes');" +
          "print(json.dumps([t]+c.modules_reached(t)))",
      ],
      { cwd: REPO, encoding: "utf-8" },
    ),
  );
  const seen = new Map(modules.map((m) => [m, { kw: new Set(), bi: new Set() }]));
  let completed = true;
  for (const [stage, files] of [
    ["run", std],
    ["lex", all],
    ["parse", std],
  ]) {
    const got = cliJson(["meta", stage, "--core-survey", ...files]);
    for (const e of got.coreReached) {
      const rel = path.relative(REPO, e.file);
      if (!seen.has(rel)) seen.set(rel, { kw: new Set(), bi: new Set() });
      seen.get(rel)[e.category === "keyword" ? "kw" : "bi"].add(e.construct);
    }
    // The refusing run — the honest host simulation — for the same stage.
    const strict = cliJson(["meta", stage, "--core", ...files]);
    if (strict.core) completed = false;
  }
  for (const [file, s] of seen) {
    graphRows.push({
      file,
      keywords: [...s.kw].sort(),
      builtins: [...s.bi].sort(),
      clean: s.kw.size === 0 && s.bi.size === 0,
    });
    record(
      "E",
      `${file}`,
      true,
      s.kw.size + s.bi.size === 0
        ? "conforms — nothing outside the core reached"
        : `non-core keywords [${[...s.kw].sort()}], builtins [${[...s.bi].sort()}]`,
      false,
    );
  }
  record(
    "E",
    "the restricted run of interp.planes + its graph completed",
    completed,
    completed ? "" : "it refused — see the report; this is the finding, not a failure",
    false,
  );
}

// ============================================================ F — anti-vacuity
console.log("\nF. anti-vacuity — break each subject, confirm the assertion fails");
{
  // F/A: break the restriction itself. A's assertion is "a `let` program
  // refuses"; with the flag off it must NOT, or A was never testing the flag.
  const p = scratch("uses_let2.planes", LET_PROGRAM);
  const off = cliJson(["run-file", p]);
  record(
    "F",
    "A fails when the restriction is removed",
    off.core === undefined,
    off.core ? "still refused with the flag off — A proves nothing" : "",
  );

  // F/A2: break the SUBJECT rather than the flag — make `let` core, and confirm
  // the same restricted run stops refusing. This is the one that shows A is
  // reading core.json and not a hardcoded list of four words.
  const letIsCore = craftedCore((d) => {
    d.keywords = [...d.keywords, "let"].sort();
    delete d.excluded_keywords.let;
  });
  const widened = cliJson(["run-file", "--core", "--core-json", letIsCore, p]);
  record(
    "F",
    "A fails when `let` is moved INTO the core (the map reads core.json)",
    widened.core === undefined && JSON.stringify(widened.output) === '["12"]',
    widened.core ? `still refused on ${widened.core.construct}` : "",
  );

  // F/B: break B's subject — narrow the core so a construct the seven-effects
  // program needs is outside it. B's "runs clean" must fail.
  const noUse = craftedCore((d) => {
    d.keywords = d.keywords.filter((k) => k !== "use");
    d.excluded_keywords.use = "crafted, for the anti-vacuity check";
  });
  const q = scratch("seven2.planes", SEVEN_EFFECTS);
  const broken = cliJson(["run-file", "--core", "--core-json", noUse, q, EFFECT_CONFIG]);
  record(
    "F",
    "B fails when a construct it needs leaves the core",
    broken.core !== undefined && broken.core.construct === "use",
    broken.core ? "" : "ran clean against a core missing `use` — B proves nothing",
  );

  // F/C: break C's SUBJECT, not its arithmetic. C asserts that this tree's
  // `meta` bytes equal main's. The subject is the interpreter's behaviour with
  // the restriction off; the way to break it is to turn the restriction ON and
  // confirm the identical comparison then reports a difference. A C that could
  // not tell those apart would be passing on a constant.
  const wt2 = fs.mkdtempSync(path.join(os.tmpdir(), "planes-main-f-"));
  execFileSync("git", ["worktree", "add", "--detach", wt2, MAIN], {
    cwd: REPO,
    stdio: "pipe",
  });
  try {
    const mainBytes = cli(["meta", "run", "ordinary.planes"], wt2);
    const offBytes = cli(["meta", "run", "ordinary.planes"]);
    const onBytes = cli(["meta", "run", "--core", "ordinary.planes"]);
    record(
      "F",
      "C fails when the interpreter's behaviour actually changes",
      offBytes === mainBytes && onBytes !== mainBytes,
      `off ${offBytes === mainBytes ? "matches" : "DIFFERS"}, ` +
        `on ${onBytes === mainBytes ? "MATCHES (C proves nothing)" : "differs"}`,
    );
  } finally {
    execFileSync("git", ["worktree", "remove", "--force", wt2], {
      cwd: REPO,
      stdio: "pipe",
    });
  }

  // F/D: break D's subject — hand the JS side a core the Python side does not
  // have, and confirm the sets stop matching.
  const extra = craftedCore((d) => {
    d.keywords = [...d.keywords, "when"].sort();
    delete d.excluded_keywords.when;
  });
  const jsDivergent = cliJson(["core-classify", "--core-json", extra]);
  const py = JSON.parse(
    run(
      "python3",
      [
        "-c",
        "import json,core_check;k,_,_=core_check.load_core();print(json.dumps(sorted(k)))",
      ],
      { cwd: REPO, encoding: "utf-8" },
    ),
  );
  record(
    "F",
    "D fails when the two readers are given different cores",
    JSON.stringify(jsDivergent.keywords) !== JSON.stringify(py),
    "the comparison is on the loaded documents, not on a constant",
  );

  // F/E: break E's subject — the census must report nothing when the core is
  // wide enough to contain everything reached.
  const whenIsCore = craftedCore((d) => {
    d.keywords = [...d.keywords, "when"].sort();
    delete d.excluded_keywords.when;
  });
  const clean = cliJson([
    "meta", "run", "--core-survey", "--core-json", whenIsCore, "ordinary.planes",
  ]);
  const stillStrict = cliJson([
    "meta", "run", "--core", "--core-json", whenIsCore, "ordinary.planes",
  ]);
  record(
    "F",
    "E reports nothing once `when` is inside the core, and the run completes",
    clean.coreReached.length === 0 && stillStrict.core === undefined,
    `census ${clean.coreReached.length} entr(ies); strict ${
      stillStrict.core ? "refused" : "completed"
    }`,
  );
}

// ============================================================ the table
const md = [];
md.push("# core-sufficiency — verification\n");
md.push(
  `Generated by \`scripts/verify-core-sufficiency.mjs\` (a throwaway; the ` +
    `retirement rule applies).\nBase for the byte-identity comparison: \`${MAIN}\`.\n`,
);
md.push("| group | assertion | result | blocking | detail |");
md.push("|-------|-----------|--------|----------|--------|");
for (const r of rows) {
  md.push(
    `| ${r.group} | ${r.name} | ${r.ok ? "PASS" : r.blocking ? "**FAIL**" : "note"} | ` +
      `${r.blocking ? "yes" : "no"} | ${r.detail || ""} |`,
  );
}
md.push("\n## E — the module graph, per file\n");
md.push("| file | non-core keywords reached | non-core builtins reached | ran to completion |");
md.push("|------|---------------------------|---------------------------|-------------------|");
for (const g of graphRows) {
  md.push(
    `| \`${g.file}\` | ${g.keywords.length ? g.keywords.map((k) => `\`${k}\``).join(", ") : "—"} | ` +
      `${g.builtins.length ? g.builtins.map((b) => `\`${b}\``).join(", ") : "—"} | ` +
      `${g.clean ? "yes" : "**no**"} |`,
  );
}
md.push(
  `\n**${rows.filter((r) => r.ok).length}/${rows.length} assertions passed; ` +
    `${blockingFailures} blocking failure(s).**\n`,
);
fs.writeFileSync(path.join(REPO, "core-sufficiency-verification.md"), md.join("\n") + "\n");

console.log(
  `\n${rows.filter((r) => r.ok).length}/${rows.length} assertions passed, ` +
    `${blockingFailures} blocking failure(s) — written to core-sufficiency-verification.md`,
);
fs.rmSync(tmp, { recursive: true, force: true });
process.exit(blockingFailures ? 1 : 0);
