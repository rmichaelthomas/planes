"""The Swift and JavaScript hosts' embedded Unicode data, held to the Python
that generated it.

shapes.py folds `lower of`, `upper of` and `normalize of` with Python's own
str.lower, str.upper and NFC, and reads a known list as Python's repr; interp.py
runs the same three. Neither host can take these from its platform — Swift's
Unicode.Scalar properties follow the OS runtime's Unicode version, Foundation's
normalisation is older than Python's and loses code points in long combining
runs, and a JavaScript engine's case mapping and normalize are its own ICU's — so
swift/Sources/Planes/Generated/PythonUnicodeData.swift and
js/python_unicode_data.mjs carry Python's behaviour, read out of Python by
scripts/python_unicode_gen.py. A copy goes stale silently when Python's Unicode
moves, so `--check` regenerates both in memory and fails on any difference, and
this suite runs that check. It needs no Swift toolchain and no node;
test_swift_shapes.py and test_js_shapes.py drive each host over every assigned
code point.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unicodedata

from scripts import python_unicode_gen as gen

REPO = os.path.dirname(os.path.abspath(__file__))


def test_the_embedded_unicode_data_is_up_to_date():
    r = subprocess.run([sys.executable, "scripts/python_unicode_gen.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr
    for rel in (gen.SWIFT_REL, gen.JS_REL):
        assert f"{rel}: up to date" in r.stdout, r.stdout[-4000:]


def test_each_file_records_the_running_pythons_unicode_version():
    version = unicodedata.unidata_version
    with open(gen.OUT_PATHS[gen.SWIFT_REL], encoding="utf-8") as f:
        assert f'unicodeVersion = "{version}"' in f.read()
    with open(gen.OUT_PATHS[gen.JS_REL], encoding="utf-8") as f:
        assert f'export const unicodeVersion = "{version}";' in f.read()


def test_check_fails_on_a_stale_copy():
    """The gate has teeth: a committed file that differs from what the generator
    produces is reported and exits non-zero — either one, alone."""
    generated = gen.generate()
    stale = {
        gen.SWIFT_REL: generated[gen.SWIFT_REL].replace("0x3A2, 0x3A2,", "0x3A2, 0x3A3,", 1),
        gen.JS_REL: generated[gen.JS_REL].replace(" 0x3a3,", " 0x3a2,", 1),
    }
    for rel in stale:
        assert stale[rel] != generated[rel], rel
    saved = gen.OUT_PATHS
    for bad in stale:
        with tempfile.TemporaryDirectory() as d:
            gen.OUT_PATHS = {rel: os.path.join(d, os.path.basename(rel)) for rel in generated}
            try:
                for rel, text in generated.items():
                    with open(gen.OUT_PATHS[rel], "w", encoding="utf-8", newline="") as f:
                        f.write(stale[rel] if rel == bad else text)
                argv, sys.argv = sys.argv, ["python_unicode_gen.py", "--check"]
                try:
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        assert gen.main() == 1
                    assert f"{bad}: OUT OF DATE" in out.getvalue()
                    good = next(rel for rel in generated if rel != bad)
                    assert f"{good}: up to date" in out.getvalue()
                finally:
                    sys.argv = argv
            finally:
                gen.OUT_PATHS = saved


def test_the_sigma_probes_read_what_they_claim():
    """The generator reads case-ignorable and cased off str.lower()'s final-sigma
    rule. Held against characters whose properties are not in doubt."""
    def classify(ch):
        before = ("A" + ch + "Σ").lower()[-1] == "ς"
        after = ("AΣ" + ch).lower()[1] == "ς"
        return "ignorable" if before and after else "cased" if before else "neither"
    assert classify("́") == "ignorable"   # combining acute
    assert classify("'") == "ignorable"        # apostrophe, MidNumLet
    assert classify("b") == "cased"
    assert classify("Σ") == "cased"
    assert classify("1") == "neither"
    assert classify("一") == "neither"     # a CJK ideograph is uncased


if __name__ == "__main__":
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
