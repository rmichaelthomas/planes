# The index becomes a hub, and every served page is reachable

**Date:** 2026-08-01
**Branch:** `feat/index-as-hub`
**Status:** approved, ready for an implementation plan

---

## 1. The problem

Three pages have shipped to GitHub Pages across three builds, and the one named
`index.html` is the oldest of them. A visitor arriving at the site root meets
the first demo Planes ever had — an editor, a Run button, an effect-surface
panel — rather than the work the project is actually for.

There is a second, sharper problem underneath it. `cp ./*.html _site/` deploys
**four** pages, and the fourth is `tutor-garden-mockup.html`: a mockup, titled
"tutor — the garden", live on the public site and linked from nothing. Nobody
decided to publish it. It is at the repo root, and being at the root is what
publishes a page.

Nothing in the gate objects. `test_gate.py::test_every_servable_page_reaches_the_deploy`
proves every authored page **ships**, and `scripts/check_pages_surface.py`
proves every page's own references **resolve** — but nothing asserts that a
served page can be **found**. A page can be authored, deployed, load perfectly,
and be reachable only by typing its filename.

That gap is what this build closes.

## 2. The page set, and the invariant that falls out of it

```
root/          SERVED. Every one must be linked from index.html.
  index.html   the hub — new content
  try.html     the current demo, git mv'd
  paint.html   unchanged
  garden.html  unchanged

mockups/       kept as reference, never served
  tutor-garden-mockup.html
```

The deploy copies `./*.html`, so **being out of the root is what stops a mockup
shipping.** No allowlist, no exclusion pattern, nothing to keep in sync. This
matters more than it looks: an allowlist is exactly how `garden.html` 404'd for
two builds while Deploy Pages went green on every push (#52, #54), and the
lesson recorded then was that the deploy must be *derived from the tree*. The
same reasoning applies in reverse here — a page is excluded by where it lives,
not by a rule that remembers to exclude it.

The invariant is then one sentence:

> **A root page is a served page is a linked page.**

### Why not delete the mockups

PR #56 deleted `the-living-garden.html` outright under the retirement rule, and
two days later it was needed as the normative reference for protocol v3's blur
radii — recovered only because a copy existed in a vault outside the repo.
Mockups are references, not products. `mockups/` keeps them legible to the next
build without publishing them.

## 3. `try.html` — the move

`index.html` is 147 lines and carries no logic of its own. Everything it does
lives in `js/browser_main.mjs`, whose DOM wiring is guarded on the presence of
four element ids — `#run`, `#surface`, `#source`, `#output` — and not on the
page's filename:

```js
  typeof document !== "undefined" &&
  document.getElementById("run") &&
  document.getElementById("surface") &&
  document.getElementById("source") &&
  document.getElementById("output")
) {
```
(`js/browser_main.mjs:322`, verified — not paraphrased.)

So the move is `git mv index.html try.html` with **zero JavaScript changes**.
The only edits inside it are its `<title>` and any self-referential copy.

**`try.html` keeps its current styling.** It does not share the garden's
`--paper` / `--graphite` / `--clay` tokens, and it is not restyled here. The
site therefore carries two visual languages after this build: the hub and the
garden in one, `try.html` and `paint.html` in the older one. That is stated
rather than fixed — bringing three working pages onto one design language is a
separate change with its own risks and its own visual gate, and nothing about
reachability needs it.

## 4. The hub

A pitch, then one card per page. It matches the garden's design language — the
`--paper` / `--graphite` / `--clay` tokens, and the self-hosted Red Hat Display
and Martian Mono already under `identity/fonts/`, which already deploy.

Each card carries the one fact that makes the page worth opening rather than a
category label:

| Card | The fact |
|---|---|
| the garden | a scene that lives, and explains where every mark came from |
| paint | the same language, drawing — and the programs that draw |
| try it | write Planes and run it, in the page, with nothing installed |

### The hub carries no JavaScript

No module imports, no fetches. This is a decision, not an omission.

The front door is the one page whose failure is total, and this week a stale
module cache made `garden.html` render an empty canvas while every gate stayed
green. A hub with no modules cannot fail that way, because it has nothing that
can go stale. It is also the page most likely to be linked from elsewhere and
least likely to be reloaded with a cleared cache.

## 5. The guard

`test_gate.py`, immediately beside `test_every_servable_page_reaches_the_deploy`
— same subject, same file. Two assertions, both hard gates:

1. **Every root `*.html` except `index.html` appears as an `href` in
   `index.html`.** Adding a page and forgetting to link it fails the build.
2. **Every `.html` href in `index.html` resolves to a file that exists.** No
   dead cards.

The page set is read from the filesystem, never from a list in the test. A
hardcoded list of files that all exist always passes — that is the precise
failure mode `cp index.html paint.html _site/` had, and repeating its shape in
the test that guards against it would be a poor joke.

Together with what already exists:

| Assertion | Question it answers | Where |
|---|---|---|
| deploy is derived from the tree | does it **ship**? | `test_gate.py` (exists) |
| every reference resolves | does it **load**? | `check_pages_surface.py` (exists) |
| every served page is linked | can it be **found**? | `test_gate.py` (**new**) |

## 6. Deliberately not doing

- **No generated hub.** This repo has no build step and that is load-bearing —
  it is why the pages are ordinary imports a browser can walk. The hub is
  hand-written and mechanically checked, the same shape as `draw.planes` ↔
  `VERBS`: two things written twice, held together by a test.
- **No transitive link-walking.** Direct links only. With four pages a
  breadth-first reachability walk is machinery for a problem that does not
  exist, and it would let a page hide two clicks deep and still pass.
- **No nav bar across every page.** The hub is the index; the pages stay as
  they are. Adding shared chrome to three working pages is a separate change
  with its own risks, and nothing about the current problem needs it.

## 7. Accepted risk

**A bookmark to the site root now lands on the hub rather than the demo.** The
demo is one click away and the site is young. This is stated rather than
mitigated: no redirect, no alias. If a URL needs to keep its old meaning, that
is a different decision and should be made explicitly.

## 8. Acceptance

- `index.html` is a hub: a pitch and three cards, no `<script>` of its own.
- `try.html` runs the editor exactly as `index.html` did — verified in a real
  browser, not asserted.
- `mockups/tutor-garden-mockup.html` exists; no mockup remains at the root.
- The new gate fails when a root page is unlinked, and fails when the hub links
  a file that does not exist. Both proven by temporarily breaking each.
- `scripts/ci.sh` green; the existing deploy and page-surface checks unchanged
  and still passing.
- Deployed and loaded from the live site, since the whole subject is what the
  live site serves.
