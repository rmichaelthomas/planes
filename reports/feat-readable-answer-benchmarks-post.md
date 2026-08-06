# Post — labeled-aggregate folding (why_tree, feat/readable-answer-and-js-whytree)

Machine: Apple M1 Pro, Python 3.14.6, Darwin 25.5.0 arm64.

Same fixture and method as the pre report: `_chain(n)`, `why_tree(traced)` called 30 times per checkpoint, `time.perf_counter()`.

**Unbounded window** — the case that changes:

| chain length (reassignment steps) | why_tree (ms/call) |
|---:|---:|
| 14 | 0.0711 |
| 100 | 0.4427 |
| 1,000 | 4.3461 |
| 10,000 | 43.8347 |

Cost is no longer O(1) in chain length: finding a fold's exact extent (`_why_find_run`/`_why_hop_shape`) walks the whole reachable chain once, so it is **O(N)** where HEAD's truncation was O(1) — the direct price of an exact, honest count (F2's own requirement) rather than a silent, uninformative stop. In absolute terms this stays small — 43.8 ms at 10,000 steps, a length no interactive `why` query is likely to reach — but it is a real, measured trade and is recorded here rather than left for someone else to discover.

**Windowed (R1's own recommended sizing, `window=900` — REPORT_RETENTION.md §6) — the realistic deployment shape:**

| chain length | why_tree (ms/call) |
|---:|---:|
| 14 | 0.0689 |
| 100 | 0.4379 |
| 900 (window boundary) | 1.3023 |
| 10,000 (far past the seal) | 1.3016 |

With R1's window applied, cost stops growing once the chain passes the window: a seal bounds how far `_why_find_run`/`_why_hop_shape` ever have to walk, the same way it already bounds reachable `Deriv` count (REPORT_RETENTION.md §6's own finding, 53,586 → 22 nodes at window=900). N=10,000 costs the same as N=900 — **~1.3 ms either way** — because nothing beyond the window is walked at all; R2's own O(N) cost applies only to the live, unwindowed case, and R1's own recommendation (set a window) is what keeps it flat in practice.

**A second, wider fixture** — `benchmarks/world_shape.planes` (R1's own S=64 canonical instance: 32 ticks, 64 subjects, seven record facets per subject each, unwindowed): why_tree over all 6 traced values averages **278.9 ms**, dominated by the record-heavy structure's own size rather than any single long chain. This is the shape that found the two correctness/performance defects below — a synthetic linear chain alone did not exercise either.

## Two things found and fixed before this build's own benchmark was trusted (self-run gate discipline)

Both defects were invisible on the synthetic `_chain(n)` fixture above — it is a linear chain with small, cheap hops — and were found only by running the new code against `benchmarks/world_shape.planes`, a wider, record-heavy program, per this project's own standing discipline of not trusting a result the gate has not actually exercised.

**A. Comparing shapes, not just building them, needs to be bounded.** The first working draft returned each hop's shape as a nested tuple and compared two shapes with structural equality directly. Building one shape was correctly bounded by `_WHY_SEARCH_BUDGET`; comparing two was not — Python's tuple equality recurses into every shared level natively, and `_why_find_run`'s loop performs that comparison once per hop. A hop whose own subtree is large (a record with several facets, each with several fields, as `world_shape.planes` builds every tick) paid that full recursive-compare cost on every iteration, not once, and the loop ran for minutes rather than milliseconds. Fixed by hashing each shape to a fixed-length SHA-256 digest (`_why_hop_shape`, reusing the same technique R1's own seal fingerprint already established) — comparison is then a fixed-length string check, not a walk, regardless of how large the underlying subtree is.

**B. A search needs to be bounded by memory, not by the recursion depth of a helper's own return-value chain.** `_why_next_stop` and `_why_hop_shape`'s inner search was ordinary recursive Python. `probe/parser/cursor_scales.planes` — 200 calls threading a state record through a `for each` loop, each field access one more indirection — put the path to the next matching name several hundred stack frames deep, past Python's default recursion limit, independent of the node-count budget (which was never exceeded; the recursion depth was). Fixed by converting both to iterative, explicit-stack traversal with `("enter"/"exit")` sentinel frames for correct post-order digest construction — the same pattern R1's own `_cut`/`_seal` already use for the identical reason, applied here rather than reinvented.

Both fixes are captured in `test_why_readable.py`'s own scenarios (a `fact of 20` recursive-argument-sharing case, and the `world_shape.planes`/`cursor_scales.planes` corpus-wide cross-language check) so a regression on either axis fails the gate, not just this report's own numbers.

## A named, not-fixed limit

`_WHY_SEARCH_BUDGET` (4,000 operations, shared across one `_why_find_run` call) caps how far a single fold is confirmed before the walk gives up and falls back to ordinary depth-limited rendering for what remains. For an unwindowed chain of ordinary shape (one or two small nodes per hop, `_chain(n)`'s own shape) this is generous — chains well into the thousands fold completely — but an unwindowed chain of ~2,000+ steps whose *individual* hops are unusually large can hit the cap before reaching the chain's true end, producing a correct but partial fold (the confirmed count is always exact; F2 holds) rather than one line covering the whole chain. This is the same shape of trade R1's own §6 finding named for RSS: a real, measured cost of the current design, not a correctness defect (nothing here can under-count what it claims or leak released history into a count), left as a named limit rather than redesigned under this build's own time budget. R1's own recommendation — set a retention window — keeps any live chain well under this cap in practice, since a seal bounds the reachable history long before 4,000 operations would be spent proving a fold.
