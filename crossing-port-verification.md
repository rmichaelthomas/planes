# Horizon Phase 2 Build 2 — crossing-port verification

Build prompt §6.2, checks A–F. A and B are blocking (§6.2's own rule): a
failure in either means the port changed the game or broke replay.

| # | Check | Result | Evidence |
|---|---|---|---|
| A | Behavior parity vs. the pre-port showcase baseline | **PASS** | `js/test/a_crossing_scene.test.mjs` (12/12), `test_a_crossing_in_planes.py` (5/5) — every route/need/power/radio branch and the tick-driven arrival, rewritten against `world-init`/`advance` and re-asserting every original transition |
| B | Cross-implementation + cross-run determinism (Python vs JS, two fresh runs each) | **PASS** | `test_crossing_port.py` (5/5) — Python/JS agree tick-for-tick over a full 200-tick crossing under two disjoint event sequences; both implementations independently reproduce their own hash sequence across two fresh runs |
| C | Input applies through the worker (real typed event shapes) | **PASS** | `js/test/crossing_port.test.mjs` (7/7 input-related) — `select`/`need`/`power`/`radio`/`route` all reach the worker and produce the expected scene-intent reaction; a worker-driven run matches a directly-driven `BrowserWorldRuntime` run line-for-line |
| D | Lifecycle: pause/resume, snapshot, event-log replay, save/restore | **PASS** | `js/test/crossing_port.test.mjs` (3/3) — pause halts ticking with no drift on resume; a saved snapshot self-verifies and event-log-driven replay reproduces it byte-identically (hash match); save/restore round-trips |
| E | Fidelity-tier invariance (Sun/Breeze/Harbor mid-run switching) | **PASS** | `js/test/crossing_port.test.mjs` (1/1) — switching every tier mid-run never changes the worker's own scene-intent line/hash sequence |
| F | Render presence (environment plate, hydrofoil at a non-placeholder position, boat advancing across two captures) | **PASS** | Agent-performed live-browser capture via `playwright-cli` against `horizon-crossing.html` served locally — see the two attached frames below. No `node --test`/`pytest` assertion exists for this check by design (this repo has no project dependency on a browser-automation library — see `scripts/world_renderer_bench.mjs`'s own header for the established precedent) |

**Full repo gate** (`scripts/ci.sh`'s own step list, run directly rather than
through `ci.sh` itself, per this project's own standing note that `set -e`
truncates the gate at the first failure): `run_suites.py` (89 files, 1516
oks), `check_js_tests.py`, `node --test js/test/*.test.mjs` (960/960),
`audit_locked_vs_built.py`, `grammar_gen.py --check`, `protocol_gen.mjs
--check`, `core_check.py` ×2, `check_derived_claims.py`, `errors_coverage.py`
/ `corpus_coverage.py` (reports, non-blocking), `ruff check .`, `mypy .` — all
green.

## Capture frames (check F)

**t0** — `horizon-crossing-capture-t0.png`: the crossing just committed
(`route: depart`). Environment plate rendered from `passage-environment.webp`,
hydrofoil rendered from `hydrofoil.webp` at its own boat-scene-x/y (not a
placeholder rect), Reso/Kordas/Market subject badges at their real scene
positions, HUD reading "care · Reso to Nkwo Eriri / ACTIVE".

**t1** — `horizon-crossing-capture-t1.png`, ~3 seconds later, same run, no
reload: the hydrofoil has visibly advanced along the route cord (now
past the wave-array pier, camera panned/zoomed to follow it per
`camera-x`/`camera-zoom`'s own progress-driven derivation), the traveled
portion of the route cord rendered bright against the untraveled remainder,
Fog-capture/Wave-array/Radio-mast badges now in frame as the camera followed
the boat.

Both frames come from the same live worker/kernel-driven session — no state
was hand-constructed for the capture.

## Findings closed during this build (not scope creep — surfaced by running
## the checks above, fixed in the same turn, per this project's own standing
## rule)

- **`paint/a_crossing.planes`'s single-pass calling convention could not
  coexist with `world-init`/`advance` in one file.** a-crossing.html's own
  `stepGraph`-based wiring depends on a prelude (`state`/`event`/`tick`/
  `seed`) the persistent-kernel loader never provides — confirmed a thin
  top-level adapter is impossible (the persistent-kernel loader executes
  every top-level statement immediately, with no prelude, so any code
  referencing those names crashes `load()`). Retired (deleted) a-crossing.html
  and its dedicated `js/test/a_crossing_page.test.mjs` suite;
  `horizon-crossing.html` is its replacement; `index.html`'s showcase card
  now points there. Decision confirmed with the user before deleting.
- **`js/test/a_crossing_scene.test.mjs` and `test_a_crossing_in_planes.py`**
  drove the OLD calling convention directly — rewritten against
  `world-init`/`advance`, preserving every original assertion's intent.
- **`world_snapshot.mjs`/`world_recovery.mjs` are single-subject-envelope-
  specific by construction, and `world_recovery.mjs` is Node-only** — neither
  usable for the crossing's scene-intent protocol in a browser worker. A
  real, disclosed gap (build prompt §2's own anticipated case): built a small,
  protocol-appropriate sibling (`js/world/runtime/crossing_persistence.mjs`)
  rather than forcing the crossing through machinery built for a different
  shape.
- **`WorldRuntime` (Python and JS) had no channel to read a call's `show`
  output** — only `.envelope`, which is world-v1-specific. Added
  `take_output()`/`takeOutput()`: a passive drain of `itp.output`/`.trace`,
  which already accumulate identically regardless of call depth.
- **`test_cut_cost_verification.py`'s `test_f_only_expected_files_changed`
  diffed a moving branch name (`"main"`) against the current working tree**
  — a permanent suite member that can only ever pass at the exact moment its
  own PR merges. Pinned to that PR's own fixed historical commit range
  (`02010fd`..`4039685`); applied the same fix to
  `test_f_interp_py_and_js_interp_mjs_changes_confined_to_cut`'s identical
  latent bug (not yet triggered on this branch, since it never touches
  `interp.py`, but structurally the same landmine for the next build that
  does).
- **`scripts/assemble_site.sh`'s `paint/*.planes` and `grammar/*.json` globs
  were not recursive** — `paint/world/kernel_spike_fixture.planes` and
  `grammar/protocols/*.json` (both pre-existing, predating this build) never
  reached the deployed site, caught by `test_gate.py`'s
  `test_every_servable_page_reaches_the_deploy`. Made both copies recursive
  (`find`-based, matching the script's own already-established pattern for
  `js/` and `assets/`).
- Two pre-existing `ruff` violations unrelated to this build's own diff
  (`test_cut_cost_verification.py`'s unused `hashlib` import,
  `world_cut_bench.py`'s `E501`/`F541`) — fixed while running the gate
  directly.
