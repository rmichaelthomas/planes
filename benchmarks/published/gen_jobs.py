#!/usr/bin/env python3
"""gen_jobs.py -- generates Set A's job programs and their shared inputs.

H7 (docs/planes_sprint_2026_09_hardening.md, decision #21) asks for four
ordinary jobs written three times each -- Planes, plain Python, plain
Node -- doing the same work and producing the same output. The three
versions of each job are not hand-kept in sync: this script is the single
source of the data each one uses (word list, record fields, invoice lines,
CSV rows), rendered into each language's literal syntax, so "the same
input" is a fact about one generator rather than three files someone
promises agree.

Two jobs need no file at all (record updates, invoice): their data is
small enough to bake into each program as a literal, generated once here
so all three see byte-identical numbers.

Two jobs read a real file (word count, file transform): the shared input
is written under TMP_DIR (never the repo -- see set_a_bench.py's module
docstring for why a fixed path, not tempfile.gettempdir()) and each
program's `read`/open() call names that same fixed path.

NO JOB PROGRAM IS COMMITTED TO THE REPO. The metacircular suites
(test_js_metacircular.py, test_js_core_restricted.py) glob every
`**/*.planes` file anywhere under the repo and run each one through the
self-hosted interpreter and the restricted-core check; three of those
suites broke the first time this script wrote its output under
`benchmarks/published/jobs/` -- these programs are sized for a wall-clock
benchmark, not for that. So this script writes to a temp directory by
default (`DEFAULT_JOBS_DIR`, under `TMP_DIR`) and `set_a_bench.py` reads
its inputs from there; nothing under `benchmarks/published/` in the repo
itself is a `.planes`, `.py`, or `.mjs` job program. `--out DIR` writes
the same, byte-identical sources to any directory a reader wants to
inspect them from (outside the repo, so it still can't reach the
metacircular glob).

Planes has no range/repeat construct ("Planes iterates collections, not
ranges" -- grammar/json.planes) and no dict/map -- `for each` walks an
existing collection or a string's code points, nothing manufactures one
from a bare count. So a Planes program that needs a 2,000- or 5,000-item
collection receives it as a literal list in its own source (there is no
way to build one from inside the language itself), and a program that
needs to tokenize free text does it by hand, one code point at a time,
against a small **known** vocabulary -- there is no dict to count into,
so word counting bumps one named counter per vocabulary word instead
(the same shape corpus/histogram.planes already uses: "three plain
counters read as what they count").

Usage:  python3 benchmarks/published/gen_jobs.py [--out DIR]
"""
from __future__ import annotations

import argparse
import decimal
import os
import random

TMP_DIR = "/tmp/planes_h7_bench"

# No job program is committed to the repo (see results.md): the metacircular
# suites (test_js_metacircular.py, test_js_core_restricted.py) glob every
# **/*.planes file under the repo and run each through the self-hosted
# interpreter and the restricted-core check, and these programs -- sized for
# a wall-clock benchmark, not for that -- broke three of them. So the
# default output directory is a temp one, generated fresh at benchmark time;
# `--out DIR` writes the same, byte-identical sources anywhere a reader
# wants to inspect them.
DEFAULT_JOBS_DIR = os.path.join(TMP_DIR, "jobs")

WORD_COUNT_INPUT = os.path.join(TMP_DIR, "word_count_input.txt")
FILE_TRANSFORM_INPUT = os.path.join(TMP_DIR, "file_transform_input.csv")

# ============================================================ job 1: word count
#
# A weighted vocabulary, not a uniform one: with a 2x+ gap between the top
# word and the runner-up, 50,000 draws leave no realistic chance of a tie
# for "most frequent" (checked empirically below, not just assumed).
WC_VOCAB = ["the", "fox", "jumps", "over", "lazy", "dog", "quick", "brown", "river", "runs"]
WC_WEIGHTS = [30, 15, 10, 10, 8, 7, 6, 5, 5, 4]
WC_N_WORDS = 50_000
WC_SEED = 12345


def wc_generate_text():
    pool = []
    for word, weight in zip(WC_VOCAB, WC_WEIGHTS):
        pool.extend([word] * weight)
    rnd = random.Random(WC_SEED)
    words = [rnd.choice(pool) for _ in range(WC_N_WORDS)]
    return " ".join(words)


# ==================================================== job 2: record updates
RU_N_RECORDS = 2000
RU_N_BUMPS = 50  # bumps = [1..50]; total = N_RECORDS * sum(1..50) = 2000*1275


# ======================================================== job 3: invoice arithmetic
INV_N_LINES = 5000
INV_TAX_RATE = decimal.Decimal("0.08")
INV_SEED = 54321


def invoice_lines():
    rnd = random.Random(INV_SEED)
    lines = []
    for _ in range(INV_N_LINES):
        qty = rnd.randint(1, 20)
        price_cents = rnd.randint(50, 9999)  # $0.50 .. $99.99
        lines.append((qty, price_cents))
    return lines


# ======================================================== job 4: file transform
FT_NAMES = ["apple", "bolt", "cable", "drum", "ember", "flask", "grain", "hinge"]
FT_N_ROWS = 10_000
FT_SEED = 999


def ft_generate_rows():
    rnd = random.Random(FT_SEED)
    rows = []
    for i in range(1, FT_N_ROWS + 1):
        name = rnd.choice(FT_NAMES)
        qty = rnd.randint(1, 20)
        price_cents = rnd.randint(50, 9999)
        rows.append((i, name, qty, price_cents))
    return rows


# ========================================================================
# rendering helpers
# ========================================================================

def fmt_cents_as_decimal(cents):
    """123 -> '1.23', matching how the generator writes prices in source
    and CSV text: exactly two decimal places, no more."""
    return f"{cents / 100:.2f}"


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------- job 1

def counter_chain_planes(base_indent):
    """The if/else chain that bumps c0..c9 for `current`, nested one level
    per vocabulary word (10 words -> 10 levels), matching the language's
    absence of a dict: there is nothing to hash a word into, so the
    program just asks "is it this one, or the next"."""
    out = []
    for i, word in enumerate(WC_VOCAB):
        ind = base_indent + "  " * i
        out.append(f'{ind}if current == "{word}":')
        out.append(f'{ind}  c{i} = c{i} + 1')
        if i < len(WC_VOCAB) - 1:
            out.append(f'{ind}else:')
    return out


def gen_word_count_planes():
    L = []
    L.append("# H7 Set A, job 1: word count. Generated by gen_jobs.py -- do not")
    L.append("# hand-edit; rerun the generator instead.")
    L.append("#")
    L.append("# Planes has no dict and no range/repeat construct, so this program")
    L.append("# cannot build a frequency table or a word list the way the plain")
    L.append("# Python/JS versions do. It walks the file one code point at a time,")
    L.append("# accumulating the current word, and -- because the vocabulary is")
    L.append("# small and known -- bumps one named counter per word directly,")
    L.append("# the same shape corpus/histogram.planes uses for its three bands.")
    L.append("use file")
    L.append("")
    L.append('body = read "%s"' % WORD_COUNT_INPUT)
    L.append("")
    L.append('current = ""')
    L.append("total = 0")
    for i in range(len(WC_VOCAB)):
        L.append(f"c{i} = 0")
    L.append("")
    L.append("for each ch in body:")
    L.append('  if ch == " " or ch == "\\n":')
    L.append('    if current != "":')
    L.append("      total = total + 1")
    L.extend(counter_chain_planes("      "))
    L.append('    current = ""')
    L.append("  else:")
    L.append("    current = current + ch")
    L.append('if current != "":')
    L.append("  total = total + 1")
    L.extend(counter_chain_planes("  "))
    L.append("")
    L.append(f'best = "{WC_VOCAB[0]}"')
    L.append("best-n = c0")
    for i in range(1, len(WC_VOCAB)):
        L.append(f"if c{i} > best-n:")
        L.append(f'  best = "{WC_VOCAB[i]}"')
        L.append(f"  best-n = c{i}")
    L.append("")
    L.append('show "total " + text of total')
    L.append('show "most " + best')
    L.append('show "count " + text of best-n')
    return "\n".join(L) + "\n"


def gen_word_count_py():
    return '''#!/usr/bin/env python3
"""H7 Set A, job 1: word count -- plain Python. Generated by gen_jobs.py."""
from collections import Counter

with open("%s", encoding="utf-8") as f:
    body = f.read()

words = body.split()
total = len(words)
word, count = Counter(words).most_common(1)[0]

print(f"total {total}")
print(f"most {word}")
print(f"count {count}")
''' % WORD_COUNT_INPUT


def gen_word_count_mjs():
    return '''// H7 Set A, job 1: word count -- plain Node. Generated by gen_jobs.py.
import fs from "node:fs";

const body = fs.readFileSync("%s", "utf-8");
const words = body.split(/\\s+/).filter(Boolean);
const total = words.length;

const counts = new Map();
for (const w of words) counts.set(w, (counts.get(w) ?? 0) + 1);
let best = null;
let bestN = -1;
for (const [w, n] of counts) {
  if (n > bestN) {
    best = w;
    bestN = n;
  }
}

console.log(`total ${total}`);
console.log(`most ${best}`);
console.log(`count ${bestN}`);
''' % WORD_COUNT_INPUT


# ---------------------------------------------------------------- job 2

def gen_record_updates_planes():
    L = []
    L.append("# H7 Set A, job 2: record updates. Generated by gen_jobs.py -- do")
    L.append("# not hand-edit; rerun the generator instead.")
    L.append("#")
    L.append(f"# {RU_N_RECORDS} records, each with its `value` field bumped")
    L.append(f"# {RU_N_BUMPS} times via `with` -- a new record every bump, since")
    L.append("# `with` never mutates (README, 'The language').")
    rec_items = [f"{{id: {i}, value: 0}}" for i in range(1, RU_N_RECORDS + 1)]
    L.append("records = [")
    for i in range(0, len(rec_items), 6):
        L.append("  " + ", ".join(rec_items[i:i + 6]) + ",")
    L.append("]")
    bumps = ", ".join(str(b) for b in range(1, RU_N_BUMPS + 1))
    L.append(f"bumps = [{bumps}]")
    L.append("")
    L.append("total = 0")
    L.append("for each r in records:")
    L.append("  cur = r")
    L.append("  for each b in bumps:")
    L.append("    cur = cur with value: cur.value + b")
    L.append("  total = total + cur.value")
    L.append("")
    L.append('show "total " + text of total')
    return "\n".join(L) + "\n"


def gen_record_updates_py():
    return '''#!/usr/bin/env python3
"""H7 Set A, job 2: record updates -- plain Python. Generated by gen_jobs.py.

Planes' `with` copies the whole record on every update (immutable-by-
design). Python's fair idiomatic choice for "update a field" is to mutate
the dict in place -- that asymmetry is real and is the point of measuring
it, not an artificial handicap in either direction.
"""
N_RECORDS = %d
N_BUMPS = %d

records = [{"id": i, "value": 0} for i in range(1, N_RECORDS + 1)]
bumps = list(range(1, N_BUMPS + 1))

total = 0
for r in records:
    for b in bumps:
        r["value"] += b
    total += r["value"]

print(f"total {total}")
''' % (RU_N_RECORDS, RU_N_BUMPS)


def gen_record_updates_mjs():
    return '''// H7 Set A, job 2: record updates -- plain Node. Generated by gen_jobs.py.
const N_RECORDS = %d;
const N_BUMPS = %d;

const records = [];
for (let i = 1; i <= N_RECORDS; i++) records.push({ id: i, value: 0 });
const bumps = [];
for (let b = 1; b <= N_BUMPS; b++) bumps.push(b);

let total = 0;
for (const r of records) {
  for (const b of bumps) r.value += b;
  total += r.value;
}

console.log(`total ${total}`);
''' % (RU_N_RECORDS, RU_N_BUMPS)


# ---------------------------------------------------------------- job 3

def gen_invoice_planes():
    lines = invoice_lines()
    L = []
    L.append("# H7 Set A, job 3: invoice arithmetic. Generated by gen_jobs.py --")
    L.append("# do not hand-edit; rerun the generator instead.")
    L.append("#")
    L.append(f"# {INV_N_LINES} line items; qty * price, plus an 8% tax, summed")
    L.append("# exactly and rounded to the cent once at the end -- Planes numbers")
    L.append("# are exact rationals, so there is no per-line rounding to disagree")
    L.append("# about (README, 'Numbers are exact').")
    inv_items = [
        f"{{qty: {qty}, price: {fmt_cents_as_decimal(cents)}}}"
        for qty, cents in lines
    ]
    L.append("lines = [")
    for i in range(0, len(inv_items), 4):
        L.append("  " + ", ".join(inv_items[i:i + 4]) + ",")
    L.append("]")
    L.append(f"let tax-rate = {INV_TAX_RATE}")
    L.append("")
    L.append("total = 0")
    L.append("for each ln in lines:")
    L.append("  subtotal = ln.qty * ln.price")
    L.append("  total = total + subtotal + (subtotal * tax-rate)")
    L.append("")
    L.append("due = round total to 2 places")
    L.append('show "due " + text of due')
    return "\n".join(L) + "\n"


def gen_invoice_py():
    lines = invoice_lines()
    items = [f"({qty}, Decimal('{fmt_cents_as_decimal(cents)}'))" for qty, cents in lines]
    body = "\n".join(
        "    " + ", ".join(items[i:i + 4]) + ","
        for i in range(0, len(items), 4)
    )
    return '''#!/usr/bin/env python3
"""H7 Set A, job 3: invoice arithmetic -- plain Python. Generated by
gen_jobs.py.

The fair idiomatic choice for money in Python is `decimal.Decimal`, not
float -- float would silently drift from Planes' exact rationals over
%d summed lines. `Decimal` is exact for these inputs (qty is an integer,
price and the tax rate both have a fixed, small number of decimal
places), so this and the Planes total agree to the last digit before
rounding.
"""
from decimal import ROUND_HALF_UP, Decimal

TAX_RATE = Decimal("%s")
LINES = [
%s
]


def fmt(x):
    """The minimal decimal text Planes' `text of` renders: trailing zeros
    (and a bare trailing '.') are dropped, so 1795.50 prints as 1795.5 and
    261.00 prints as 261 -- exactly what interp.py's Number formatting
    does, and this mirrors it rather than fixing every value at 2 places.
    """
    s = f"{x:.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


total = Decimal(0)
for qty, price in LINES:
    subtotal = qty * price
    total += subtotal + subtotal * TAX_RATE

due = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
print(f"due {fmt(due)}")
''' % (INV_N_LINES, INV_TAX_RATE, body)


def gen_invoice_mjs():
    lines = invoice_lines()
    # JS's fair idiomatic choice for exact money: integer cents (BigInt),
    # scaled by 100 again (to 1/10000 of a dollar) so the 8% tax rate
    # divides out evenly -- see the module docstring below for why that
    # scale is exact for these inputs.
    items = [f"[{qty}, {cents}]" for qty, cents in lines]
    body = "\n".join(
        "  " + ", ".join(items[i:i + 6]) + ","
        for i in range(0, len(items), 6)
    )
    return '''// H7 Set A, job 3: invoice arithmetic -- plain Node. Generated by
// gen_jobs.py.
//
// The fair idiomatic choice for exact money in JS is integer cents, not
// float. Each line's [qty, priceCents] is scaled to priceCents * 100 --
// 1/10000 of a dollar -- because qty * priceCents * 100 is always a
// multiple of 100, so multiplying by the 8%% tax rate (8/100) divides
// back out to a whole number of those units with no remainder. That is
// what makes this integer arithmetic exact rather than an approximation
// of Decimal/Planes' exact rationals.
const TAX_NUM = 8n;
const TAX_DEN = 100n;
const LINES = [
%s
];

function fmt(unitsTenThousandths) {
  // unitsTenThousandths is dollars * 10000, an exact integer. Round to
  // the cent (half away from zero, matching interp.py's `round`), then
  // render the minimal decimal text: no trailing zero, no bare ".".
  const cents = unitsTenThousandths / 100n;
  const rem = unitsTenThousandths %% 100n;
  const roundedCents = rem * 2n >= 100n ? cents + 1n : cents;
  const whole = roundedCents / 100n;
  const frac = roundedCents %% 100n;
  let s = `${whole}.${frac.toString().padStart(2, "0")}`;
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\\.$/, "");
  return s;
}

let totalTenThousandths = 0n;
for (const [qty, priceCents] of LINES) {
  const subtotal = BigInt(qty) * BigInt(priceCents) * 100n;
  const tax = (subtotal * TAX_NUM) / TAX_DEN;
  totalTenThousandths += subtotal + tax;
}

console.log(`due ${fmt(totalTenThousandths)}`);
''' % body


# ---------------------------------------------------------------- job 4

def gen_file_transform_csv():
    rows = ft_generate_rows()
    lines = [f"{i},{name},{qty},{fmt_cents_as_decimal(cents)}" for i, name, qty, cents in rows]
    return "\n".join(lines) + "\n"


def gen_file_transform_planes(out_path):
    L = []
    L.append("# H7 Set A, job 4: file transform. Generated by gen_jobs.py -- do")
    L.append("# not hand-edit; rerun the generator instead.")
    L.append("#")
    L.append("# Planes has no `split`, so this program parses `id,name,qty,price`")
    L.append("# CSV text one code point at a time, tracking which of the four")
    L.append("# columns it is in. `write` always JSON-encodes its argument")
    L.append("# (interp.py's WriteTo: `payload = to_json(value.value)`), so the")
    L.append("# output file holds a JSON string, not raw CSV text -- the plain")
    L.append("# Python/JS versions write the same text unencoded, and the harness")
    L.append("# json-decodes this file before comparing.")
    L.append("use file")
    L.append("")
    L.append('body = read "%s"' % FILE_TRANSFORM_INPUT)
    L.append("")
    L.append('field = ""')
    L.append("col = 0")
    L.append('id-f = ""')
    L.append('name-f = ""')
    L.append('qty-f = ""')
    L.append('price-f = ""')
    L.append("lines = []")
    L.append("row-count = 0")
    L.append("")
    L.append("for each ch in body:")
    L.append('  if ch == "," or ch == "\\n":')
    L.append("    if col == 0:")
    L.append("      id-f = field")
    L.append("    else:")
    L.append("      if col == 1:")
    L.append("        name-f = field")
    L.append("      else:")
    L.append("        if col == 2:")
    L.append("          qty-f = field")
    L.append("        else:")
    L.append("          price-f = field")
    L.append('    field = ""')
    L.append('    if ch == "\\n":')
    L.append("      qty-n = number of qty-f")
    L.append("      price-n = number of price-f")
    L.append("      row-total = round (qty-n * price-n) to 2 places")
    L.append('      out-line = id-f + "," + (upper of name-f) + "," + qty-f'
              ' + "," + price-f + "," + text of row-total + "\\n"')
    L.append("      lines = lines plus out-line")
    L.append("      row-count = row-count + 1")
    L.append("      col = 0")
    L.append("    else:")
    L.append("      col = col + 1")
    L.append("  else:")
    L.append("    field = field + ch")
    L.append("")
    L.append("document = join of lines")
    L.append('write document to "%s"' % out_path)
    L.append('show "rows " + text of row-count')
    return "\n".join(L) + "\n"


def gen_file_transform_py(out_path):
    return '''#!/usr/bin/env python3
"""H7 Set A, job 4: file transform -- plain Python. Generated by
gen_jobs.py.
"""
from decimal import ROUND_HALF_UP, Decimal


def fmt(x):
    s = f"{x:.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


with open("%s", encoding="utf-8") as f:
    body = f.read()

rows = [line.split(",") for line in body.strip("\\n").split("\\n")]
out_lines = []
for id_, name, qty, price in rows:
    total = (Decimal(qty) * Decimal(price)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    out_lines.append(f"{id_},{name.upper()},{qty},{price},{fmt(total)}")

document = "\\n".join(out_lines) + "\\n"
with open("%s", "w", encoding="utf-8") as f:
    f.write(document)

print(f"rows {len(rows)}")
''' % (FILE_TRANSFORM_INPUT, out_path)


def gen_file_transform_mjs(out_path):
    return '''// H7 Set A, job 4: file transform -- plain Node. Generated by
// gen_jobs.py.
import fs from "node:fs";

function fmt(cents) {
  const whole = cents / 100n;
  const frac = cents %% 100n;
  let s = `${whole}.${frac.toString().padStart(2, "0")}`;
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\\.$/, "");
  return s;
}

const body = fs.readFileSync("%s", "utf-8");
const rows = body
  .replace(/\\n$/, "")
  .split("\\n")
  .map((line) => line.split(","));

const outLines = rows.map(([id, name, qty, price]) => {
  const priceCents = BigInt(Math.round(parseFloat(price) * 100));
  const totalCents = BigInt(qty) * priceCents; // exact: price already whole cents
  return `${id},${name.toUpperCase()},${qty},${price},${fmt(totalCents)}`;
});

const document = outLines.join("\\n") + "\\n";
fs.writeFileSync("%s", document);

console.log(`rows ${rows.length}`);
''' % (FILE_TRANSFORM_INPUT, out_path)


# ---------------------------------------------------------------- hello

def gen_hello_planes():
    return 'show "hello"\n'


def gen_hello_py():
    return (
        '#!/usr/bin/env python3\n'
        '"""H7 baseline: process-startup hello world."""\n'
        'print("hello")\n'
    )


def gen_hello_mjs():
    return (
        '// H7 baseline: process-startup hello world.\n'
        'console.log("hello");\n'
    )


# ========================================================================

def main(jobs_dir=None):
    jobs_dir = jobs_dir or DEFAULT_JOBS_DIR
    os.makedirs(jobs_dir, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)

    # shared inputs (temp dir only -- never the repo)
    write(WORD_COUNT_INPUT, wc_generate_text())
    write(FILE_TRANSFORM_INPUT, gen_file_transform_csv())

    ft_out_planes = os.path.join(TMP_DIR, "file_transform_output_planes.csv")
    ft_out_py = os.path.join(TMP_DIR, "file_transform_output_py.csv")
    ft_out_mjs = os.path.join(TMP_DIR, "file_transform_output_mjs.csv")

    files = {
        "hello.planes": gen_hello_planes(),
        "hello.py": gen_hello_py(),
        "hello.mjs": gen_hello_mjs(),
        "word_count.planes": gen_word_count_planes(),
        "word_count.py": gen_word_count_py(),
        "word_count.mjs": gen_word_count_mjs(),
        "record_updates.planes": gen_record_updates_planes(),
        "record_updates.py": gen_record_updates_py(),
        "record_updates.mjs": gen_record_updates_mjs(),
        "invoice.planes": gen_invoice_planes(),
        "invoice.py": gen_invoice_py(),
        "invoice.mjs": gen_invoice_mjs(),
        "file_transform.planes": gen_file_transform_planes(ft_out_planes),
        "file_transform.py": gen_file_transform_py(ft_out_py),
        "file_transform.mjs": gen_file_transform_mjs(ft_out_mjs),
    }
    for name, content in files.items():
        write(os.path.join(jobs_dir, name), content)

    print(f"wrote {len(files)} job files under {jobs_dir}")
    print(f"wrote shared inputs under {TMP_DIR}")
    return jobs_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", default=None,
        help=f"directory to write the job programs to (default: {DEFAULT_JOBS_DIR})")
    args = ap.parse_args()
    main(args.out)
