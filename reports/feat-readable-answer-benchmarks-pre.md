# Pre — HEAD's depth-14 truncation (why_tree, before R2)

Machine: Apple M1 Pro, Python 3.14.6, Darwin 25.5.0 arm64.

A reassignment chain (`x = 0` then `x = x + 1` N times — `test_retention.py`'s own `_chain(n)` fixture, the shape a long-running `with`/reassignment loop actually builds), `why_tree(traced)` called 30 times per checkpoint, timed with `time.perf_counter()`. HEAD's algorithm — a plain recursive walk that stops at `depth > 14` and appends `"..."` — measured by re-running its verbatim body (not restored into `interp.py`; this file exists to be diffed against, not to be a code path in the repo).

Window: unbounded (no `window` argument — chain length is the only variable).

| chain length (reassignment steps) | why_tree (ms/call) |
|---:|---:|
| 14 | 0.0121 |
| 100 | 0.0113 |
| 1,000 | 0.0114 |
| 10,000 | 0.0122 |

Flat, by construction: HEAD's walk never looks past depth 14 regardless of how deep the actual derivation goes, so cost is **O(1) in chain length** — and uninformative in exactly the cases where that matters, since a chain past depth 14 renders as 14 raw lines and a bare `"..."` that names neither how much was cut nor where it leads.

**A second fixture** — `benchmarks/world_shape.planes` (R1's own S=64 canonical instance: 32 ticks, 64 subjects, seven record facets per subject) — is included in the post report but not here: HEAD's depth-14 walk is the same flat cost on it as on the chain above (bounded by depth, not by the program), so it adds no new data point on this side of the comparison.
