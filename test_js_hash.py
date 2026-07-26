"""S5, Phase 1 — the JS hash, checked against hashlib.

rules.py fingerprints a rule with hashlib.sha256(...).hexdigest()[:6], and a
fingerprint appears in Planes source (the FINGERPRINT token). A JS fingerprint
that differs from a Python one by a single byte makes source written by one
implementation invalid under the other — so js/sha256.mjs must be byte-identical
to hashlib for arbitrary UTF-8 input (A.2).

This drives a battery of inputs through both hashlib.sha256 and js/sha256.mjs
and compares the full 64-character hex digests: empty input, ASCII, multi-byte
UTF-8, and — the case a naive block loop gets wrong — inputs spanning the
64-byte block boundary (55..65 bytes, where padding tips into a second block).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _js_hashes(strings):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "hash", json.dumps(strings)],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    return json.loads(r.stdout)


def _py_hashes(strings):
    return [hashlib.sha256(s.encode("utf-8")).hexdigest() for s in strings]


def _agree(strings):
    got = _js_hashes(strings)
    want = _py_hashes(strings)
    assert got == want, "\n".join(
        f"{s!r}: js={g} py={w}"
        for s, g, w in zip(strings, got, want) if g != w)


# ================================================================ empty and ASCII

def test_empty_input():
    _agree([""])
    # the known SHA-256 of the empty string, as a fixed anchor
    assert _js_hashes([""]) == [
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"]


def test_ascii_inputs():
    _agree(["a", "abc", "hello world", "The quick brown fox jumps over "
            "the lazy dog", "0123456789", "\x1f", "forbid\x1fask\x1f\x1f"])


# ================================================================ multi-byte UTF-8

def test_multibyte_utf8():
    _agree(["café", "naïve", "Ω", "日本語", "😀", "a😀b", "𝕏 marks",
            "👨‍👩‍👧", "https://example.com/ünïcode.json"])


# ================================================================ the block boundary

def test_inputs_spanning_the_block_boundary():
    # SHA-256 processes 64-byte blocks; the 0x80 pad byte plus the 8-byte
    # length must fit, so 56..63 bytes tip into a second block. Cover 55..65.
    _agree([("x" * n) for n in range(50, 70)])


def test_multibyte_across_the_boundary():
    # A multi-byte char straddling byte 64 stresses UTF-8 length accounting.
    _agree([("a" * n) + "😀" for n in range(58, 66)])


# ================================================================ the real fingerprint inputs

def test_actual_rule_fingerprint_strings():
    """The exact canonical strings rules.py hashes: subject\x1fassertion\x1f
    kind\x1ftarget. fingerprint() truncates to 6 hex — check the full digest
    agrees, so the truncation agrees too."""
    canon = [
        "anything\x1fforbid\x1fask\x1f",
        "anything\x1fforbid\x1fwrite\x1frefunds.json",
        'cap\x1fforbid\x1fask\x1f',
        'anything\x1fpermit\x1fwrite\x1fa.json',
        'user\x1fforbid\x1fask\x1fhttps://collector.example.com/?d="q"',
    ]
    _agree(canon)
    # and the truncation rules.py actually uses
    got6 = [h[:6] for h in _js_hashes(canon)]
    want6 = [hashlib.sha256(s.encode()).hexdigest()[:6] for s in canon]
    assert got6 == want6


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
        sys.exit(0)
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
