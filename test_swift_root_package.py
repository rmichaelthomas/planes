"""The root Package.swift, checked against swift/Package.swift and built.

SwiftPM resolves a remote package dependency (`.package(url: ..., from: ...)`)
only from a manifest at the repository root (Koncord v1.12 build prompt §2,
E3) — never from one in a subdirectory. Before this file, only
swift/Package.swift existed, so a downstream consumer could not add this repo
as a SwiftPM dependency at all; the local suites always built by
`--package-path swift` (swift_host.py), which never exercised a root manifest.

The root Package.swift is not a copy: it points `path:` at the same
swift/Sources/Planes and swift/Sources/PlanesCLI directories swift/Package.swift
builds, under the same product names (`Planes`, `planes-swift`), so there is one
copy of the sources and two ways to reach them. This suite holds three claims:

  1. `swift package describe --type json`, run from the repo root with no
     `--package-path`, reports the same two consumer-facing products
     (`Planes`, `planes-swift`) as swift/Package.swift does, at the
     swift/Sources/... paths — the structural check the sprint hardening doc
     allows in place of a full build if one proves too slow for the gate.
     swift/Package.swift also carries H4's HostRulesBench target, which the
     root manifest deliberately does not expose; that asymmetry is checked
     too, not just the overlap.
  2. `swift build`, run from the repo root with no `--package-path`, actually
     succeeds — built and cached the way swift_host.py caches `swift/`'s
     binary, so a gate re-run does not pay for a from-scratch build every time.
  3. The root-built `planes-swift` binary runs correctly: it lexes a program
     (proving Grammar.swift's embedded GrammarData.swift resolved, since
     nothing here runs from within `swift/`) and it agrees with `demo/rules/
     exception.planes` through `host-rules`, the same scenario
     test_swift_host_rules.py holds to Python — so the root build is not just
     present, it is the same Planes.

A throwaway package outside this repo, depending on this worktree by
`.package(path:)`, importing Planes and running HostRuleSet successfully, was
verified by hand while building this (see swift/README.md's root-manifest
note); that is not repeated here because it needs a second scratch package
tree this gate should not create and clean up on every run.
"""
import json
import os
import subprocess
import sys
import tempfile

from swift_host import REPO, SWIFT


def _bin_path():
    """The directory `swift build` writes this configuration's products to.
    Not `.build/debug`: that is a convenience symlink SwiftPM repoints at
    whichever triple was built last, so it can point at a non-native build
    (e.g. an iOS cross-build done for E3's platform check) and hand back a
    binary this machine refuses to run. `--show-bin-path` names the real,
    triple-specific directory for a plain native `swift build`."""
    r = subprocess.run([SWIFT, "build", "--show-bin-path"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"swift build --show-bin-path failed: {r.stderr}"
    return r.stdout.strip()


def _describe(package_path=None):
    args = [SWIFT, "package"]
    if package_path:
        args += ["--package-path", package_path]
    args += ["describe", "--type", "json"]
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, f"swift package describe failed: {r.stderr}"
    return json.loads(r.stdout)


def _targets_by_name(desc):
    return {t["name"]: t for t in desc["targets"]}


def test_the_root_manifest_exposes_the_same_products_as_swift_package_swift():
    """The two consumer-facing products (the library and the agreement CLI)
    agree between the two manifests. swift/Package.swift also carries
    HostRulesBench (H4's repo-internal benchmark, an implicit product for its
    own executable target — SwiftPM synthesises one per executable target
    with no explicit product) on purpose: a downstream consumer resolving
    the root manifest should never see it, and does not."""
    root = _describe()
    sub = _describe(package_path="swift")

    assert root["name"] == sub["name"] == "Planes"

    SHARED_PRODUCTS = {"Planes": ["Planes"], "planes-swift": ["PlanesCLI"]}
    root_products = {p["name"]: sorted(p["targets"]) for p in root["products"]}
    sub_products = {p["name"]: sorted(p["targets"]) for p in sub["products"]}
    assert root_products == SHARED_PRODUCTS, root_products
    for name, targets in SHARED_PRODUCTS.items():
        assert sub_products.get(name) == targets, sub_products

    # The root manifest exposes nothing else: no benchmark tool.
    assert set(root_products) == set(SHARED_PRODUCTS)
    # swift/Package.swift additionally carries H4's benchmark target/product.
    assert sub_products.get("HostRulesBench") == ["HostRulesBench"], sub_products

    root_targets = _targets_by_name(root)
    assert set(root_targets) == {"Planes", "PlanesCLI"}
    assert root_targets["Planes"]["path"] == "swift/Sources/Planes"
    assert root_targets["PlanesCLI"]["path"] == "swift/Sources/PlanesCLI"

    sub_targets = _targets_by_name(sub)
    assert set(sub_targets) == {"Planes", "PlanesCLI", "HostRulesBench"}
    assert sub_targets["Planes"]["path"] == "Sources/Planes"
    assert sub_targets["PlanesCLI"]["path"] == "Sources/PlanesCLI"


def test_the_root_manifest_declares_macos_and_ios_platforms():
    root = _describe()
    platforms = {p["name"]: p["version"] for p in root["platforms"]}
    assert platforms.get("macos") == "14.0", platforms
    assert platforms.get("ios") == "17.0", platforms


def _newest_source_mtime():
    newest = os.path.getmtime(os.path.join(REPO, "Package.swift"))
    for root, _dirs, files in os.walk(os.path.join(REPO, "swift", "Sources")):
        for name in files:
            if name.endswith(".swift"):
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
    return newest


def _root_binary():
    """The path to a current root-built `planes-swift`, building it if it is
    missing or stale — the same staleness trick swift_host.py uses for
    swift/.build/, so repeated gate runs do not rebuild for nothing."""
    binary = os.path.join(_bin_path(), "planes-swift")
    if not os.path.exists(binary) or os.path.getmtime(binary) < _newest_source_mtime():
        r = subprocess.run([SWIFT, "build"], cwd=REPO, capture_output=True, text=True)
        assert r.returncode == 0, (
            f"swift build (root manifest) failed:\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}")
        os.utime(binary)
    return binary


def test_the_root_manifest_builds_and_the_binary_lexes():
    binary = _root_binary()
    with tempfile.NamedTemporaryFile("w", suffix=".planes", delete=False, encoding="utf-8") as fh:
        fh.write('x = 1\n')
        path = fh.name
    try:
        r = subprocess.run([binary, "tokens", path], cwd=REPO, capture_output=True, text=True)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    kinds = [tok[0] for tok in json.loads(r.stdout)]
    assert kinds == ["NAME", "OP", "NUMBER", "EOL", "EOF"], r.stdout


def test_the_root_manifest_binary_agrees_on_the_exception_demo():
    """The root build is not just present, it is the same Planes: the
    default-deny-with-exception scenario test_swift_host_rules.py holds to
    Python, run against the root-built binary instead of swift/.build's."""
    binary = _root_binary()
    effects = json.dumps([
        {"kind": "ask", "target": "https://audit.internal"},
        {"kind": "ask", "target": "https://tracker.example/pixel.gif"},
        {"kind": "show", "target": "sending audit event"},
    ])
    r = subprocess.run([binary, "host-rules", "demo/rules/exception.planes", effects],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["admitted"] is False
    renders = [v["render"] for v in out["rules"]["violations"]]
    assert any("excepted by [audit-allowed]" in r for r in renders), renders
    assert any("[no-external-sends] violated at line 2." in r for r in renders), renders


if __name__ == "__main__":
    if SWIFT is None:
        print("  SKIP  swift not on PATH")
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
