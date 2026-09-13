"""The Swift host's embedded Unicode data, held to the Python that generated it.

shapes.py folds `lower of`, `upper of` and `normalize of` with Python's own
str.lower, str.upper and NFC, and reads a known list as Python's repr. The Swift
host cannot take these from its platform — Swift's Unicode.Scalar properties
follow the OS runtime's Unicode version, and Foundation's normalisation is older
than Python's and loses code points in long combining runs — so
swift/Sources/Planes/Generated/PythonUnicodeData.swift carries Python's behaviour,
read out of Python by scripts/swift_unicode_gen.py. A copy goes stale silently
when Python's Unicode moves, so `--check` regenerates it in memory and fails on
any difference, and this suite runs that check. It needs no Swift toolchain;
test_swift_shapes.py drives the Swift side over every assigned code point.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unicodedata

from scripts import swift_unicode_gen as gen

REPO = os.path.dirname(os.path.abspath(__file__))


def test_the_embedded_unicode_data_is_up_to_date():
    r = subprocess.run([sys.executable, "scripts/swift_unicode_gen.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr
    assert "up to date" in r.stdout, r.stdout[-4000:]


def test_it_records_the_running_pythons_unicode_version():
    with open(gen.OUT_PATH, encoding="utf-8") as f:
        text = f.read()
    assert f'unicodeVersion = "{unicodedata.unidata_version}"' in text


def test_check_fails_on_a_stale_copy():
    """The gate has teeth: a committed file that differs from what the generator
    produces is reported and exits non-zero."""
    generated = gen.generate()
    stale = generated.replace("0x3A2, 0x3A2,", "0x3A2, 0x3A3,", 1)
    assert stale != generated
    saved = gen.OUT_PATH
    with tempfile.TemporaryDirectory() as d:
        gen.OUT_PATH = os.path.join(d, "PythonUnicodeData.swift")
        try:
            with open(gen.OUT_PATH, "w", encoding="utf-8", newline="") as f:
                f.write(stale)
            argv, sys.argv = sys.argv, ["swift_unicode_gen.py", "--check"]
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    assert gen.main() == 1
                assert "OUT OF DATE" in out.getvalue()
            finally:
                sys.argv = argv
        finally:
            gen.OUT_PATH = saved


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
