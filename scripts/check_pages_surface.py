#!/usr/bin/env python3
"""Every root page's module graph and data fetches resolve inside a served root.

garden.html shipped in #52 and returned 404 on GitHub Pages for two builds
while the deploy workflow reported success on every push. The workflow copied
a hardcoded allowlist -- `cp index.html paint.html _site/` -- and copying a
list of files that all exist always succeeds. A page missing from the list is
invisible to the thing that is supposed to notice.

`js/sound/*.mjs` was the same defect one layer down: the workflow copied
`js/*.mjs` and `js/paint/*.mjs`, so #52's sound modules were absent from the
deploy even though the page that imports them would have been present.

This walks what a browser walks -- each root `*.html`, transitively through
every relative `import`/`export ... from` in the modules it loads, plus the
sibling data files the pages fetch by name -- and reports every reference that
does not resolve under the given root. Run against `_site/` in CI it is the
deploy's own check; run against the repo root it catches a typo'd import path.

    python3 scripts/check_pages_surface.py _site
"""

import os
import re
import sys

# `import x from "./y.mjs"`, `export * from "../z.mjs"`, `import("./w.mjs")`,
# and the `with { type: "json" }` attribute form all reduce to a quoted
# specifier following `from` or a bare dynamic `import(`. The specifier may
# not span a newline: `[^"']+` without that bound happily swallows a comment
# containing the word "from" and everything up to the next quote in the file.
_SPECIFIER = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*)["']([^"'\n]+)["']""")

# `<script type="module" src="./js/browser_main.mjs">` and `<link href=...>`.
_HTML_REF = re.compile(r"""\b(?:src|href)\s*=\s*["']([^"'\n]+)["']""")

# The pages name their programs as plain sibling paths in JS object literals
# (`file: "paint/garden.planes"`), so there is no import to follow -- match the
# extension directly. Any quoted `<dir>/<name>.planes` counts as a fetch.
_PLANES_REF = re.compile(r"""["']([A-Za-z0-9_./-]+\.planes)["']""")

# Line and block comments, so prose is never mistaken for a specifier. Quotes
# inside a comment are the only thing this needs to defeat, so a plain strip
# is enough -- it is not trying to be a JS tokenizer.
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)

_LOADABLE = (".mjs", ".js", ".json", ".planes", ".css")


def _is_local(spec):
    """Relative or root-relative, i.e. something the root has to contain."""
    if spec.startswith(("http://", "https://", "//", "data:", "mailto:", "#")):
        return False
    # A bare package specifier (`node:fs`, `lodash`) is not ours to resolve.
    # Everything a page actually loads from the served root is one of these.
    return spec.endswith(_LOADABLE)


def _resolve(spec, from_path, root):
    """Resolve `spec` as a browser would, relative to the file that names it."""
    spec = spec.split("?", 1)[0].split("#", 1)[0]
    if not spec:
        return None
    if spec.startswith("/"):
        return os.path.normpath(os.path.join(root, spec.lstrip("/")))
    return os.path.normpath(os.path.join(os.path.dirname(from_path), spec))


def _pages_in(root):
    return sorted(f for f in os.listdir(root)
                  if f.endswith(".html") and os.path.isfile(
                      os.path.join(root, f)))


def check(root, source=None):
    root = os.path.abspath(root)
    pages = [os.path.join(root, f) for f in _pages_in(root)]
    if not pages:
        return [("<root>", root, "no .html pages found under the served root")]

    missing = []

    # THE CHECK THIS SCRIPT EXISTS FOR. Walking only the pages that are
    # present is blind in exactly the way the allowlist was: a page left out
    # of the deploy has no references to fail on, so the walk below reports
    # success for a root that is missing the page entirely. The served set
    # has to be compared against the authored set, which only `source`
    # knows. Without it this script cannot see an omission -- only a broken
    # reference in something that did ship.
    if source:
        authored = set(_pages_in(os.path.abspath(source)))
        for page in sorted(authored - set(_pages_in(root))):
            missing.append(
                ("<deploy>", page, "authored at the source root but absent "
                                   "from the served root -- never deployed"))

    seen = set()
    queue = [(p, "<root>") for p in pages]

    while queue:
        path, referrer = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        if not os.path.exists(path):
            missing.append((referrer, os.path.relpath(path, root), "not found"))
            continue
        if not path.endswith((".html", ".mjs", ".js")):
            continue  # a leaf: .json/.planes/.css are fetched, not parsed
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if path.endswith((".mjs", ".js")):
            text = _COMMENTS.sub(" ", text)

        refs = set(_SPECIFIER.findall(text)) | set(_PLANES_REF.findall(text))
        if path.endswith(".html"):
            refs |= set(_HTML_REF.findall(text))

        for spec in sorted(refs):
            if not _is_local(spec):
                continue
            target = _resolve(spec, path, root)
            if target is None:
                continue
            # Stay inside the served root -- an escaping `../` is its own bug.
            if not target.startswith(root + os.sep) and target != root:
                missing.append(
                    (os.path.relpath(path, root), spec, "escapes the root"))
                continue
            queue.append((target, os.path.relpath(path, root)))

    return missing


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    source = None
    for a in argv[1:]:
        if a.startswith("--source="):
            source = a.split("=", 1)[1]
    root = args[0] if args else "."
    for label, path in (("root", root), ("source", source)):
        if path is not None and not os.path.isdir(path):
            print(f"check_pages_surface: no such {label} directory: {path}")
            return 2
    missing = check(root, source)
    if missing:
        print(f"check_pages_surface: {len(missing)} problem(s) under {root}:")
        for referrer, spec, why in missing:
            print(f"  {referrer} -> {spec}  ({why})")
        return 1
    pages = _pages_in(root)
    against = f" (all {len(_pages_in(source))} authored)" if source else ""
    print(f"check_pages_surface: {len(pages)} page(s){against} "
          f"[{', '.join(pages)}] resolve completely under {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
