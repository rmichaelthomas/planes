#!/usr/bin/env bash
# scripts/assemble_site.sh — build the servable surface into $1 (default _site).
#
# WHY THIS IS A SCRIPT AND NOT A `run:` BLOCK. It used to live inline in
# .github/workflows/pages.yml, which meant the only place the assembly could be
# exercised was a runner, on main, after merge. `test_gate.py` asserted that the
# workflow SAID the right things and then ran the surface check against the
# REPO — a tree where every file exists by construction — so a missing copy rule
# was invisible locally and fatal remotely. meta.html shipped that way: it fetches
# grammar/*.planes and grammar/core.json, none of which were copied, and the gate
# went green while Deploy Pages failed on the very next push.
#
# That is the same blind spot the allowlist had, one level up. The remedy is the
# same: one derivation, in one place, run by both the workflow and the gate.
#
# THE COPY IS DERIVED FROM THE TREE, NEVER AN ALLOWLIST. An allowlist is how
# garden.html shipped in #52 and 404'd on Pages for two builds while this
# workflow reported success on every push — copying a list of files that all
# exist always succeeds, so a page missing from the list fails silently.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

SITE="${1:-_site}"
rm -rf "$SITE"
mkdir -p "$SITE/paint" "$SITE/grammar" "$SITE/identity/fonts"

# Every root page, not a named few.
cp ./*.html "$SITE/"

# Every module directory under js/ except the test tree.
find js -name '*.mjs' -not -path 'js/test/*' -print0 \
  | while IFS= read -r -d '' f; do
      mkdir -p "$SITE/$(dirname "$f")"
      cp "$f" "$SITE/$f"
    done

# Every .planes source, at any depth — a flat `paint/*.planes` glob missed
# paint/world/kernel_spike_fixture.planes (js/world/runtime/worker.mjs's
# own fetch target since Horizon Phase 1's renderer pipeline, PR #91):
# invisible locally (the repo tree has the file; only the ASSEMBLED site
# was missing it) and exactly the blind spot this script's own header
# describes meta.html and garden.html already hitting once each.
find paint -name '*.planes' -print0 \
  | while IFS= read -r -d '' f; do
      mkdir -p "$SITE/$(dirname "$f")"
      cp "$f" "$SITE/$f"
    done

# Every authored visual asset, preserving its relative path. The tree is
# derived rather than naming A Crossing or one asset type: future showcases
# can add sprites, plates, maps, textures, or other browser-native files under
# assets/ without opening another deployment allowlist.
if [ -d assets ]; then
  find assets -type f -print0 \
    | while IFS= read -r -d '' f; do
        mkdir -p "$SITE/$(dirname "$f")"
        cp "$f" "$SITE/$f"
      done
fi

# The identity assets a page consumes: the generated marks and the self-hosted
# typefaces. garden.html reaches both, the mark through <img src> and the fonts
# through @font-face url() — neither of which is an import, which is why the
# surface check had to learn to follow them. render_logo.py and the identity
# suites stay behind: they generate these files, they are not served with them.
cp identity/*.svg "$SITE/identity/"
cp identity/fonts/* "$SITE/identity/fonts/"

# ALL of grammar's data and ALL of its self-hosted sources.
#
# This used to be two named files, vocabulary.json and messages/amber.json, on
# the stated grounds that "the rest of grammar/ (the self-hosted .planes sources
# and its own tests) are not part of what any page reaches". That was true when
# it was written and stopped being true the moment meta.html landed: it runs the
# self-hosted stack in the browser, so it FETCHES grammar/interp.planes and the
# graph beneath it, and browser_main.mjs imports grammar/core.json for the
# core-restricted mode. Globbed rather than listed, so the next page to reach
# for a grammar file does not repeat this. Recursive (find, not a flat
# `grammar/*.json` glob) for the same reason paint/*.planes above is now
# recursive: a flat glob silently missed grammar/protocols/world-v1.json
# (js/world_ir.mjs's own fetch target since Horizon Phase 0) — one `find`
# pass covers grammar/*.json, grammar/messages/*.json, and
# grammar/protocols/*.json alike, so a future grammar/ subdirectory does
# not reopen the same gap a third time.
find grammar -name '*.json' -print0 \
  | while IFS= read -r -d '' f; do
      mkdir -p "$SITE/$(dirname "$f")"
      cp "$f" "$SITE/$f"
    done
cp grammar/*.planes "$SITE/grammar/"

echo "assemble_site: $SITE built from the tree"
