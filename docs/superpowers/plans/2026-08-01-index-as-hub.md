# The index becomes a hub — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `index.html` a hub that links every served page, move the demo to `try.html`, move mockups out of the served root, and replace the landing-page rule's spec-parsing exemption with the stronger structural one.

**Architecture:** The deploy is `cp ./*.html _site/`, so *the root directory is the served set*. Moving mockups to `mockups/` un-publishes them structurally, which in turn makes `test_gate.py`'s `_reference_mockups()` exemption mechanism unnecessary — the landing-page rule becomes absolute rather than spec-parsed. The hub itself is static HTML with no JavaScript.

**Tech Stack:** Static HTML/CSS. Python `test_gate.py` (stdlib only, run by `scripts/run_suites.py`). GitHub Actions `pages.yml`. No build step anywhere.

## Global Constraints

- **No build step.** Pages are ordinary root-relative fetches and imports a browser can walk. Nothing may require compilation, bundling or a generator.
- **The deploy is derived from the tree, never an allowlist.** `cp ./*.html _site/` must remain; naming a page individually is what `test_every_servable_page_reaches_the_deploy` forbids.
- **The hub carries no `<script>` of its own** and imports no module.
- **`paint.html` and `garden.html` are byte-identical to `main` at the end of this plan.**
- **`try.html` keeps its current styling.** Two visual languages on the site is a stated, accepted limit (spec §3).
- Python is stdlib-only in `test_gate.py`; `ruff` and `mypy` must stay clean.
- Run the whole gate with `PATH="$PWD/.venv/bin:$PATH" scripts/ci.sh`.

---

### Task 1: Move the demo to `try.html`

**Files:**
- Rename: `index.html` → `try.html`
- Modify: `try.html` (title and self-referential copy only)
- Test: `test_gate.py` (existing tests must still pass)

**Interfaces:**
- Consumes: nothing.
- Produces: `try.html`, a served root page carrying element ids `run`, `surface`, `source`, `output` — the four `js/browser_main.mjs:322` guards on. Task 3's hub links to `./try.html`.

- [ ] **Step 1: Confirm the wiring is filename-independent before moving anything**

Run: `grep -n 'getElementById("run")' js/browser_main.mjs`
Expected: a hit at `js/browser_main.mjs:323`, inside an `if` that also tests `surface`, `source` and `output`. This is why the move needs no JS change. If this does not match, STOP — the move is not safe and the plan needs revising.

- [ ] **Step 2: Move the file with git so history follows it**

```bash
git mv index.html try.html
```

- [ ] **Step 3: Retitle the moved page**

In `try.html`, replace these three strings (they are the only places the page names itself):

- `<title>Planes — running in a browser</title>` → `<title>Try Planes — run it in a browser</title>`
- `<meta property="og:title" content="Planes — running in a browser" />` → `<meta property="og:title" content="Try Planes — run it in a browser" />`
- `<h1>Planes, in JavaScript</h1>` → `<h1>Try Planes</h1>`

- [ ] **Step 4: Remove the nav block — the hub owns navigation now**

Delete the whole `<nav class="pages">…</nav>` element (currently `index.html:88-100`) and the `nav.pages` CSS rules (currently `index.html:62-75`, including the `@media (prefers-color-scheme: dark)` block that only styles `nav.pages`). Leave every other style untouched.

Add, immediately after the `<h1>`, a single link back to the hub:

```html
    <p class="sub"><a href="./index.html">← all of Planes</a></p>
```

- [ ] **Step 5: Verify the page still runs, in a real browser**

Run: `python3 -m http.server 8000` then open `http://localhost:8000/try.html`, click **Run ▸**, then **Surface ⊚**.
Expected: Run prints `0.1 + 0.2 = 0.3` and the `wrote 5 readings` line; Surface reports the file and network boundaries without executing. If either button does nothing, the id-based wiring assumption failed — STOP.

- [ ] **Step 6: Commit**

```bash
git add -A -- try.html index.html
git commit -m "The demo moves to try.html, so index can be the front door"
```

---

### Task 2: Move the mockup out of the served root

**Files:**
- Create: `mockups/tutor-garden-mockup.html` (moved)
- Modify: `garden-page-spec.md` (the citation's path)
- Modify: `.gitignore` (the `the-living-garden.html` entry's path)

**Interfaces:**
- Consumes: nothing.
- Produces: an empty mockup set at the root. Task 4 depends on this: `_reference_mockups()` can only be deleted once no root page needs exempting.

- [ ] **Step 1: Move the mockup**

```bash
mkdir -p mockups
git mv tutor-garden-mockup.html mockups/tutor-garden-mockup.html
```

- [ ] **Step 2: Fix the citation that points at it**

`garden-page-spec.md:3` says ``**Reference implementations:** `tutor-garden-mockup.html` `` and later "open it, and match it" — the path has to be true or the instruction is dead. Change that one backtick-quoted name to `mockups/tutor-garden-mockup.html`.

- [ ] **Step 3: Move the ignored mockup's path too**

`.gitignore` currently ignores `the-living-garden.html` at the root. A local reference copy belongs beside the other mockup now. Replace that line with:

```
mockups/the-living-garden.html
```

and add a line to the comment above it noting mockups live in `mockups/` and are never served.

- [ ] **Step 4: Verify no mockup remains at the root and the deploy set shrank**

Run: `ls *.html`
Expected: exactly `garden.html`, `index.html`, `paint.html`, `try.html` — four pages, no mockup.

- [ ] **Step 5: Verify the existing exemption now finds nothing to exempt**

Run: `python3 -c "import test_gate; print(test_gate._reference_mockups())"`
Expected: the set still contains the two names (it parses the spec, not the filesystem) — that is fine and expected here; Task 4 is what removes it. What matters is the next check.

Run: `python3 -c "import test_gate, os; print(sorted(f for f in os.listdir('.') if f.endswith('.html')))"`
Expected: the four pages above. No exempt name appears in it.

- [ ] **Step 6: Commit**

```bash
git add -A -- mockups garden-page-spec.md .gitignore
git commit -m "Mockups leave the served root, which is what un-publishes them"
```

---

### Task 3: The hub

**Files:**
- Create: `index.html` (new content — the old file became `try.html` in Task 1)

**Interfaces:**
- Consumes: `try.html` from Task 1; `paint.html` and `garden.html` unchanged on main.
- Produces: an `index.html` containing `href="./try.html"`, `href="./paint.html"` and `href="./garden.html"` — the exact string form (`href="./NAME"`) that `test_the_landing_page_links_to_the_pages_it_ships_with` matches on. Task 4's assertions read this file.

- [ ] **Step 1: Read the design language to copy, rather than inventing one**

Run: `sed -n '25,60p' garden.html`
Expected: the `:root` custom properties (`--paper:#F7F2E9`, `--graphite:#211D19`, `--line:#D6C9B4`, `--clay:#A65A2E`, the `--ink-*` values) and the `@font-face` blocks for Red Hat Display and Martian Mono pointing at `./identity/fonts/`. Copy these verbatim into the new page — same tokens, same font paths. Do not restyle them.

- [ ] **Step 2: Write the hub**

Create `index.html` with, in order:

1. The `<head>` meta block from `try.html` as it was (charset, viewport, canonical, `og:*`, `twitter:card`) with the title and descriptions rewritten for a hub: `<title>Planes</title>`, and a description reading `A programming language that shows its work — what a program can do to the outside world, and where every value came from. Three pages, no build step.`
2. The `:root` tokens and `@font-face` blocks from Step 1.
3. An `<h1>Planes</h1>` and a one-paragraph pitch: a language you can read aloud, two independent implementations that agree, a static effect surface that says what a program would touch without running it, and no build step anywhere.
4. Three cards, in this order, each an `<a>` with a `<strong>` title and a `<span>` line:

| `href` | title | line |
|---|---|---|
| `./garden.html` | the garden | a scene that lives — weather, growth, sound — and explains where every mark came from |
| `./paint.html` | paint | the same language, drawing: turtle, bloom, snake, one program and two renderers |
| `./try.html` | try it | write Planes and run it in the page, with nothing installed |

5. A footer linking the repo at `https://github.com/rmichaelthomas/planes`.

**No `<script>` tag and no module import anywhere in this file.**

- [ ] **Step 3: Verify the hub has no JavaScript**

Run: `grep -c "<script" index.html`
Expected: `0`. If this is not zero, the constraint is broken — remove it before continuing.

- [ ] **Step 4: Verify every card resolves and the page loads**

Run: `python3 -m http.server 8000` then open `http://localhost:8000/` and click each of the three cards in turn, using Back between them.
Expected: the garden, paint and try each load and work. No 404.

- [ ] **Step 5: Verify the existing landing-page rule passes on the new hub**

Run: `python3 -c "import test_gate; test_gate.test_the_landing_page_links_to_the_pages_it_ships_with(); print('ok')"`
Expected: `ok`. This is the pre-existing rule — it should pass now that all three pages are linked.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "index.html is a hub: a pitch and three cards, and no JavaScript at all"
```

---

### Task 4: The rule loses its exemption and gains a dead-link check

**Files:**
- Modify: `test_gate.py` — delete `_reference_mockups()` (starts at line 377), rewrite `test_the_landing_page_links_to_the_pages_it_ships_with` (starts at line 415); both end before `if __name__` at line 436

**Interfaces:**
- Consumes: an empty mockup set at the root (Task 2) and a hub linking all three pages (Task 3). Both must be done first or this task's assertions fail correctly.
- Produces: no callable interface. `_reference_mockups` ceases to exist — confirm nothing else imports it.

- [ ] **Step 1: Confirm nothing else uses the function about to be deleted**

Run: `grep -rn "_reference_mockups" --include='*.py' .`
Expected: hits only inside `test_gate.py`. If any other file uses it, STOP and revise.

- [ ] **Step 2: Write the replacement test, failing first**

Replace `_reference_mockups()` and the existing test with this single test. Write it now, before deleting anything, so Step 3 can show it failing for the right reason.

```python
def test_the_landing_page_links_to_the_pages_it_ships_with():
    """The deploy carried paint.html and garden.html while index.html linked
    to nothing but the repo, so a shipped page was unreachable by anyone who
    did not already know its filename -- indistinguishable, from outside,
    from the page not being deployed at all.

    THIS RULE USED TO HAVE AN EXEMPTION, and the exemption is what let a
    mockup ship. `_reference_mockups()` parsed `*-spec.md` preambles to decide
    which pages were excused, and its own comments record two near-misses: a
    reworded preamble once put `garden.html` inside the reference sentence and
    "silently exempted the very page the rule was written for", and an earlier
    version "emptied itself out". It excused a page from being FINDABLE and
    could not excuse it from being SERVED -- `cp ./*.html _site/` copies every
    root page regardless -- so an exempt page was published and unreachable.

    Mockups live in `mockups/` now. A page that is not at the root is not
    served, so it needs no excuse for not being linked, and the rule is
    absolute: every root page except the landing page is linked from it."""
    idx = os.path.join(REPO, "index.html")
    with open(idx, encoding="utf-8") as fh:
        html = fh.read()

    pages = sorted(f for f in os.listdir(REPO)
                   if f.endswith(".html") and f != "index.html")
    assert pages, "no page to link -- the rule has nothing to hold"
    for page in pages:
        assert f'href="./{page}"' in html, (
            f"{page} is deployed but index.html does not link to it")

    # And the other direction: a card pointing at nothing. The old rule caught
    # an unlinked page and nothing caught a dead link, so a renamed page would
    # have left the hub pointing into space with the gate still green.
    for href in re.findall(r'href="\./([A-Za-z0-9._-]+\.html)"', html):
        assert os.path.exists(os.path.join(REPO, href)), (
            f"index.html links ./{href}, which does not exist")
```

- [ ] **Step 3: Prove the dead-link half actually fails**

Temporarily add `<a href="./nope.html">x</a>` to `index.html`, then run:

Run: `python3 -c "import test_gate; test_gate.test_the_landing_page_links_to_the_pages_it_ships_with()"`
Expected: `AssertionError: index.html links ./nope.html, which does not exist`

Remove the temporary line.

- [ ] **Step 4: Prove the unlinked-page half actually fails**

Temporarily `cp try.html spare.html`, then run:

Run: `python3 -c "import test_gate; test_gate.test_the_landing_page_links_to_the_pages_it_ships_with()"`
Expected: `AssertionError: spare.html is deployed but index.html does not link to it`

Then `rm spare.html`.

- [ ] **Step 5: Delete the exemption machinery**

Delete the whole `_reference_mockups()` function, its docstring, and the `exempt = _reference_mockups()` / `linked = [...]` / `assert linked, "every page is exempt..."` lines from the old test body. The `re` import stays — the new test uses it for the href scan.

- [ ] **Step 6: Run the test and the linters**

Run: `python3 test_gate.py`
Expected: every test `ok`, including the rewritten one.

Run: `PATH="$PWD/.venv/bin:$PATH" ruff check . && PATH="$PWD/.venv/bin:$PATH" mypy .`
Expected: both clean. `ruff` will flag `_reference_mockups` if any reference survives.

- [ ] **Step 7: Commit**

```bash
git add test_gate.py
git commit -m "The landing-page rule loses its exemption and gains a dead-link check"
```

---

### Task 5: The whole gate, the deploy, and the live site

**Files:**
- Modify: none expected. This task is verification; any fix it forces is a change to the file that failed.

**Interfaces:**
- Consumes: Tasks 1-4 complete.
- Produces: a merged, deployed, verified site.

- [ ] **Step 1: Run the full gate**

Run: `PATH="$PWD/.venv/bin:$PATH" scripts/ci.sh`
Expected: `all checks passed`. Suites at or above 61 files / 1237 oks; JS tests at 711; ruff and mypy clean. `test_every_servable_page_reaches_the_deploy` and `check_pages_surface.py` must both still pass — they are the two guards this build must not weaken.

- [ ] **Step 2: Confirm paint and garden were not touched**

Run: `git diff --stat main -- paint.html garden.html`
Expected: empty output. If either changed, revert it — the plan's global constraint says byte-identical.

- [ ] **Step 3: Confirm the served set is what the hub links**

Run:
```bash
python3 - <<'PY'
import os, re
pages = {f for f in os.listdir('.') if f.endswith('.html')}
html = open('index.html', encoding='utf-8').read()
linked = set(re.findall(r'href="\./([A-Za-z0-9._-]+\.html)"', html))
print('served :', sorted(pages))
print('linked :', sorted(linked))
print('served but unlinked:', sorted(pages - linked - {'index.html'}) or 'none')
print('linked but missing :', sorted(linked - pages) or 'none')
PY
```
Expected: four served pages, three linked, and both discrepancy lines `none`.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/index-as-hub
```

Then open the PR with this body, adjusting only the measured numbers:

> `index.html` was the oldest demo wearing the front-door name, and
> `tutor-garden-mockup.html` was live on the public site linked from nothing.
>
> **The landing-page rule already existed.** `test_the_landing_page_links_to_the_pages_it_ships_with` has been green throughout — the mockup shipped because it was *deliberately exempt*, cited as a reference implementation in `garden-page-spec.md` and read out of that preamble by `_reference_mockups()`. The real defect is that **the exemption excused a page from being FINDABLE but could not excuse it from being SERVED**: `cp ./*.html _site/` copies every root page regardless. Exempt and published.
>
> So mockups moved to `mockups/`, and being out of the root is what un-publishes them — no allowlist, the same lesson #52 taught in reverse. That let the exemption be **deleted**: forty lines of spec-preamble parsing whose own comments record two near-misses (a reworded preamble once "silently exempted the very page the rule was written for"; an earlier version "emptied itself out"). The rule is absolute now, and gained the check nobody had: a card pointing at a file that does not exist.
>
> The demo moved to `try.html` — a `git mv` with zero JavaScript changes, because `js/browser_main.mjs:322` wires on element ids and not on a filename. The hub is a pitch and three cards with **no `<script>` at all**: the front door is the page whose failure is total, and a stale module cache blanked `garden.html` this week.
>
> Stated, not fixed: the site carries two visual languages, and a bookmark to the root now lands on the hub.
>
> Gate: 61 suites / 1237 Python oks / 711 JS tests, 0 failures.

- [ ] **Step 5: Merge, then verify the LIVE site**

```bash
gh pr merge --squash --delete-branch
git checkout main && git pull
```

Then wait for Deploy Pages to finish and open the live site. Check, in order: the hub loads; each of the three cards opens its page; `mockups/tutor-garden-mockup.html` returns **404** on the live site, because that is the whole point of the move.

- [ ] **Step 6: Report the live verification**

State plainly which of the three cards were opened on the live site and what the mockup URL returned. A deploy that was not looked at is not verified — `garden.html` 404'd for two builds while the workflow reported success on every push.
