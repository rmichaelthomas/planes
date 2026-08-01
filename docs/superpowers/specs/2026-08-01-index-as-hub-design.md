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

**CORRECTED AFTER APPROVAL.** The first version of this section claimed that
nothing asserts a served page can be found. That is false, and was corrected
before any implementation began.
`test_gate.py::test_the_landing_page_links_to_the_pages_it_ships_with` exists,
is green, and asserts exactly that. `tutor-garden-mockup.html` is not
unguarded — it is **deliberately exempt**, because `garden-page-spec.md` cites
it as a reference implementation and `_reference_mockups()` reads that citation
out of the spec's own preamble.

The real defect is narrower, and more interesting than a missing rule:

> **The exemption excuses a page from being FINDABLE but not from being
> SERVED.** `cp ./*.html _site/` copies every root page regardless of any
> exemption. So a page can be exempt-and-published, which is exactly the state
> the live site is in.

The three guards that exist cover *ships*, *loads*, and *is linked* — and the
gap between them is that the third one has an escape hatch the first one does
not honour.

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

The rule is not written — it is **strengthened by deletion.**

`test_the_landing_page_links_to_the_pages_it_ships_with` already reads the root
page set from the filesystem and asserts each one is linked from `index.html`.
Its only weakness is `_reference_mockups()`: forty lines that parse
`*-spec.md` preambles to decide which pages are exempt, carrying two recorded
near-misses in its own comments — once a reworded preamble put `garden.html`
inside the reference sentence and "silently exempted the very page the rule was
written for", and once "the first version of this emptied itself out".

Once no mockup lives at the root, nothing needs exempting. So:

1. **`_reference_mockups()` is deleted**, along with the `exempt` filter and the
   `assert linked, "every page is exempt"` backstop that existed only because
   exemptions could empty the list.
2. The rule becomes absolute: **every root page except `index.html` must be
   linked from `index.html`.** No exemptions, no spec-parsing, nothing that can
   silently widen.
3. **One assertion is added**: every `.html` href in `index.html` resolves to a
   file that exists. The old rule caught unlinked pages; nothing caught a dead
   card.

Deleting a guard is normally the wrong direction. It is right here because the
exemption is being replaced by something stronger — a page that is not at the
root cannot be served at all, so it needs no excuse for not being linked. The
mechanism moves from *parsing prose to decide who is excused* to *being in a
different directory*.

Together with what already exists:

| Assertion | Question it answers | Where |
|---|---|---|
| deploy is derived from the tree | does it **ship**? | `test_gate.py` (exists) |
| every reference resolves | does it **load**? | `check_pages_surface.py` (exists) |
| every served page is linked | can it be **found**? | `test_gate.py` (exists — **loses its exemption**) |

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
