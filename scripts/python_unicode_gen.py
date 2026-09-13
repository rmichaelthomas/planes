#!/usr/bin/env python3
"""Embed Python's Unicode behaviour in the Swift and JavaScript hosts.

    python3 scripts/python_unicode_gen.py            write both files
    python3 scripts/python_unicode_gen.py --check    regenerate into memory, diff
                                                     against the committed files,
                                                     exit non-zero on any difference

shapes.py folds `lower of`, `upper of` and `normalize of` a known value with
Python's str.lower, str.upper and unicodedata.normalize("NFC", ...), and reads a
known list as Python's repr, which escapes every character str.isprintable()
refuses; interp.py's `lower of`, `upper of` and `normalize of` are the same three
calls. Neither host can borrow these from its platform. Swift's Unicode.Scalar
properties come from the OS's Swift runtime, so they change with the macOS the
library runs on (Unicode 17 on macOS 26, where Python 3.14 has 16), and
Foundation's normalisation lacks Unicode 16's composites and drops code points
from a long run of combining marks. JavaScript's toLowerCase, toUpperCase and
normalize are the engine's ICU, a version ahead of Python in Node 22 and behind
it in an older browser. So, as the lexers do for `\\d` and str.isspace, the data
is Python's own, read out of the running Python by asking it — not from a
Unicode database file — and written to
swift/Sources/Planes/Generated/PythonUnicodeData.swift, which PythonUnicode.swift
turns back into the four operations, and to js/python_unicode_data.mjs, which
js/python_unicode.mjs turns back into three (js/planes_text.mjs already holds
str.isprintable's set).

What is recorded, per code point:

  * whether str.isprintable() is false (as ranges; Swift only);
  * str.lower() and str.upper() of the lone character, where it changes;
  * whether the character is case-ignorable, and whether it is cased, as
    str.lower()'s final-sigma rule sees them — read by probing that rule:
    "A" + c + "Σ" lowers to final sigma exactly when c is ignorable or
    cased, and "AΣ" + c exactly when c is ignorable or not cased;
  * its canonical combining class, its full canonical decomposition (Hangul
    syllables excepted, which the algorithm derives), and every primary
    composite NFC builds from a pair.

`--check` regenerates from the running Python and diffs, which
test_python_unicode_data.py runs: a Python whose Unicode moved fails the suites
until these files are regenerated.
"""
import difflib
import os
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWIFT_REL = "swift/Sources/Planes/Generated/PythonUnicodeData.swift"
JS_REL = "js/python_unicode_data.mjs"
# Where each output goes, by repo-relative name; a test points one elsewhere.
OUT_PATHS = {rel: os.path.join(REPO, rel) for rel in (SWIFT_REL, JS_REL)}

SBASE, SCOUNT = 0xAC00, 11172
SIGMA = "Σ"


def _code_points():
    return (c for c in range(0x110000) if not 0xD800 <= c < 0xE000)


def _ranges(members):
    out = []
    for c in members:
        if out and out[-1][1] == c - 1:
            out[-1][1] = c
        else:
            out.append([c, c])
    return out


def _array(name, kind, values, comment):
    body = []
    line = "   "
    for v in values:
        item = f" 0x{v:X},"
        if len(line) + len(item) > 100:
            body.append(line)
            line = "   "
        line += item
    if line.strip():
        body.append(line)
    return (f"    /// {comment}\n"
            f"    static let {name}: [{kind}] = [\n" + "\n".join(body) + "\n    ]\n")


def _mapping(prefix, table, comment):
    keys, starts, values = [], [0], []
    for k in sorted(table):
        keys.append(k)
        values.extend(ord(ch) for ch in table[k])
        starts.append(len(values))
    return (_array(f"{prefix}Keys", "UInt32", keys, comment + " — the code points, ascending.")
            + _array(f"{prefix}Starts", "UInt32", starts,
                     "Where each key's scalars start in the values; one more entry than keys.")
            + _array(f"{prefix}Values", "UInt32", values, "The mapped scalars, concatenated."))


def collect() -> dict:
    not_printable, ignorable, cased = [], [], []
    lower, upper, decomposition = {}, {}, {}
    ccc = []
    composites = []
    for c in _code_points():
        ch = chr(c)
        if not ch.isprintable():
            not_printable.append(c)
        if c != 0x3A3 and ch.lower() != ch:
            lower[c] = ch.lower()
        if ch.upper() != ch:
            upper[c] = ch.upper()
        before = ("A" + ch + SIGMA).lower()[-1] == "ς"
        after = ("A" + SIGMA + ch).lower()[1] == "ς"
        if before and after:
            ignorable.append(c)
        elif before:
            cased.append(c)
        cls = unicodedata.combining(ch)
        if cls:
            ccc.append((c, cls))
        if not SBASE <= c < SBASE + SCOUNT:
            nfd = unicodedata.normalize("NFD", ch)
            if nfd != ch:
                decomposition[c] = nfd
            fields = unicodedata.decomposition(ch).split()
            if len(fields) == 2 and not fields[0].startswith("<"):
                a, b = (int(f, 16) for f in fields)
                if unicodedata.normalize("NFC", chr(a) + chr(b)) == ch:
                    composites.append((a, b, c))

    class_ranges: list[list[int]] = []
    for c, cls in ccc:
        if class_ranges and class_ranges[-1][1] == c - 1 and class_ranges[-1][2] == cls:
            class_ranges[-1][1] = c
        else:
            class_ranges.append([c, c, cls])
    composites.sort()

    return {
        "not_printable": [v for r in _ranges(not_printable) for v in r],
        "ignorable": [v for r in _ranges(ignorable) for v in r],
        "cased": [v for r in _ranges(cased) for v in r],
        "lower": lower, "upper": upper,
        "combining_class": [v for r in class_ranges for v in r],
        "decomposition": decomposition,
        "composites": [v for t in composites for v in t],
    }


def render_swift(d) -> str:
    parts = [
        "// GENERATED by scripts/python_unicode_gen.py — do not hand-edit.\n",
        "//\n",
        "// Python's Unicode behaviour, read out of the Python that generated it, for\n",
        "// PythonUnicode.swift: str.isprintable, str.lower, str.upper, the final-sigma\n",
        "// rule's cased and case-ignorable sets, and NFC's classes, decompositions and\n",
        "// composites. Regenerate with `python3 scripts/python_unicode_gen.py`;\n",
        "// `--check` (run by test_python_unicode_data.py) fails when this file is stale.\n",
        "\n",
        "enum PythonUnicodeData {\n",
        f'    static let unicodeVersion = "{unicodedata.unidata_version}"\n',
        "\n",
        _array("notPrintable", "UInt32", d["not_printable"],
               "Code points str.isprintable() refuses, as inclusive (low, high) pairs."),
        "\n",
        _array("caseIgnorable", "UInt32", d["ignorable"],
               "Case-ignorable to str.lower()'s final-sigma rule, as (low, high) pairs."),
        "\n",
        _array("cased", "UInt32", d["cased"],
               "Cased and not case-ignorable to that rule, as (low, high) pairs."),
        "\n",
        _mapping("lower", d["lower"],
                 "str.lower() of the lone character, where it differs (U+03A3 aside)"),
        "\n",
        _mapping("upper", d["upper"], "str.upper() of the lone character, where it differs"),
        "\n",
        _array("combiningClass", "UInt32", d["combining_class"],
               "Nonzero canonical combining classes, as (low, high, class) triples."),
        "\n",
        _mapping("decomposition", d["decomposition"],
                 "The full canonical decomposition (NFD), where it differs, "
                 "Hangul syllables aside"),
        "\n",
        _array("composites", "UInt32", d["composites"],
               "NFC's primary composites, as (first, second, composite) triples sorted by pair."),
        "}\n",
    ]
    return "".join(parts)


def _js_array(name, values, comment):
    body = []
    line = " "
    for v in values:
        item = f" 0x{v:x},"
        if len(line) + len(item) > 80:
            body.append(line)
            line = " "
        line += item
    if line.strip():
        body.append(line)
    return f"// {comment}\nexport const {name} = [\n" + "\n".join(body) + "\n];\n"


def _js_mapping(prefix, table, comment):
    keys, starts, values = [], [0], []
    for k in sorted(table):
        keys.append(k)
        values.extend(ord(ch) for ch in table[k])
        starts.append(len(values))
    return (_js_array(f"{prefix}Keys", keys, comment + " — the code points, ascending.")
            + _js_array(f"{prefix}Starts", starts,
                        "Where each key's code points start in the values; "
                        "one more entry than keys.")
            + _js_array(f"{prefix}Values", values, "The mapped code points, concatenated."))


def render_js(d) -> str:
    parts = [
        "// GENERATED by scripts/python_unicode_gen.py — do not hand-edit.\n",
        "//\n",
        "// Python's Unicode behaviour, read out of the Python that generated it, for\n",
        "// js/python_unicode.mjs: str.lower, str.upper, the final-sigma rule's cased and\n",
        "// case-ignorable sets, and NFC's classes, decompositions and composites.\n",
        "// Regenerate with `python3 scripts/python_unicode_gen.py`; `--check` (run by\n",
        "// test_python_unicode_data.py) fails when this file is stale.\n",
        "\n",
        f'export const unicodeVersion = "{unicodedata.unidata_version}";\n',
        "\n",
        _js_array("caseIgnorable", d["ignorable"],
                  "Case-ignorable to str.lower()'s final-sigma rule, as (low, high) pairs."),
        "\n",
        _js_array("cased", d["cased"],
                  "Cased and not case-ignorable to that rule, as (low, high) pairs."),
        "\n",
        _js_mapping("lower", d["lower"],
                    "str.lower() of the lone character, where it differs (U+03A3 aside)"),
        "\n",
        _js_mapping("upper", d["upper"], "str.upper() of the lone character, where it differs"),
        "\n",
        _js_array("combiningClass", d["combining_class"],
                  "Nonzero canonical combining classes, as (low, high, class) triples."),
        "\n",
        _js_mapping("decomposition", d["decomposition"],
                    "The full canonical decomposition (NFD), where it differs, "
                    "Hangul syllables aside"),
        "\n",
        _js_array("composites", d["composites"],
                  "NFC's primary composites, as (first, second, composite) triples "
                  "sorted by pair."),
    ]
    return "".join(parts)


def generate() -> dict:
    """Every output, by repo-relative name."""
    d = collect()
    return {SWIFT_REL: render_swift(d), JS_REL: render_js(d)}


def main() -> int:
    check = "--check" in sys.argv[1:]
    outputs = generate()
    if not check:
        for rel, text in outputs.items():
            path = OUT_PATHS[rel]
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            print(f"wrote {rel} (Unicode {unicodedata.unidata_version})")
        return 0
    status = 0
    for rel, generated in outputs.items():
        path = OUT_PATHS[rel]
        existing = None
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as f:
                existing = f.read()
        if existing == generated:
            print(f"{rel}: up to date")
            continue
        status = 1
        print(f"{rel}: OUT OF DATE — regenerate with python3 scripts/python_unicode_gen.py")
        sys.stdout.writelines(difflib.unified_diff(
            (existing or "").splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile=f"{rel} (committed)", tofile=f"{rel} (generated)"))
    return status


if __name__ == "__main__":
    sys.exit(main())
