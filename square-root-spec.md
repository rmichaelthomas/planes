# Square Root — Specification

**For:** `root of x`, the thirteenth builtin. **Closes:** §253, open since the sine-and-exactness build.

This document states the rules before any code, because the interesting part of square root is not the algorithm — it is what the answer's *exactness* is, and that had to be decided rather than discovered.

---

## 1. The name

`root of x`. Prose, like `sine` and unlike `sqrt`: this language spells operations out, and `sine` set that precedent when it could have been `sin`.

Unary, like every builtin. There is no nth root — `root` is the square root, and a general nth root is a different function with a different name if it is ever wanted.

## 2. The rule that decides exactness

> **A value is approximate when the true result of the operation that produced it cannot be represented as a rational. It is exact otherwise.**
> — `grammar/vocabulary.json`, `value_properties.exactness.entry`

This rule already decides square root, and it decides it **per argument**:

- `root of 9` is **3, exact.** The true result is a rational and the implementation returns exactly it.
- `root of 2` is **approximate.** The true result is irrational; no rational is it.
- `root of 0.25` is **0.5, exact.** 1/4 is a ratio of two perfect squares.
- `root of 2 * root of 2` is **approximate, and is not 2.** Two approximate values multiplied stay approximate, and the product of two 30-place approximations of √2 is not 2 exactly. `== 2` is **false**, and that is the honest answer rather than a hidden tolerance.

### 2.1 Why this differs from `sine`, which is approximate for every input

`sine` returns an approximate value for **every** argument, including `sine of 0`. That is not an inconsistency with the rule above — it is a fact about sine's *algorithm*. Sine is computed by a truncated Taylor series over a stated rational approximation of pi/180; there is no path by which that computation produces an exact answer, at any argument. The operation approximates, so its results are approximate.

Square root is different **in kind**, not in degree. Whether √(n/d) is rational is *decidable* — it is rational exactly when `n` and `d` are both perfect squares — and when it is, the exact answer is computable with integer arithmetic and no approximation at all. An implementation that returned "approximate 3" for `root of 9` would be reporting a property of its own laziness, not of the number.

**This is the precedent for a class, and that is the argument that decides it.** `root` is the first of several operations whose exactness depends on their argument: an nth root, `log of 100`, exponentiation by a rational. If `root of 9` were approximate on the grounds that square roots are usually irrational, then `log of 100` would be approximate too, and soon nearly every number in a program carries the flag. **A property that marks everything discriminates nothing** — and discriminating is the entire purpose of tracking exactness.

## 3. The domain

`root of x` for **x < 0 is an error**, tagged `not-a-number`, and not a silent `nothing`.

There is no imaginary number in this language and inventing one for a single builtin would be a larger decision than this document is making. The refusal names the fix.

`root of 0` is **0, exact.**

## 4. The algorithm

Exact first, and approximate only when exactness has been ruled out.

Let the argument be the reduced fraction `n/d`, with `n >= 0` and `d > 0`. Because the fraction is reduced, √(n/d) is rational **if and only if** both `n` and `d` are perfect squares.

1. **The exact path.** If `isqrt(n)² = n` and `isqrt(d)² = d`, return `isqrt(n) / isqrt(d)` — exact.
2. **The approximate path.** Otherwise return the value rounded to **30 decimal places**, the same `RESULT_PLACES` sine keeps, computed on integers:

   ```
   scaled = isqrt((4 · n · 10^60) // d)      # = floor(2 · √(n/d) · 10^30)
   result = (scaled + 1) // 2                # round half away from zero
   value  = result / 10^30                   # approximate
   ```

   The doubling-then-halving is how a floor becomes a round with no division and no rounding mode to disagree about. `isqrt(floor(x)) = floor(√x)` for every non-negative real `x`, which is why taking the floor of the quotient first is not a second approximation.

**Integer arithmetic and one rounding rule, exactly as sine does it**, and for the same reason: three implementations reading "reduce a fraction" three ways can drift, and three implementations doing integer division cannot. The three must agree **bit for bit**.

### 4.1 `isqrt`

Newton's method on integers, from a decimal-length estimate rather than from `n` itself: a start of `10^ceil(digits(n)/2)` converges in a handful of steps where a start of `n` takes one step per bit. Terminates on `x² ≤ n < (x+1)²`, which is the definition rather than a tolerance.

## 5. Propagation

Unchanged, and stated here only because `root` is the first operation that can return *either*:

- An exact `root` result combined with exact values stays exact.
- An **approximate argument gives an approximate result**, whatever the argument's value. `root of (sine of 30)` is approximate even in the impossible case that the sine came back a perfect square: the input was already not the number it claimed to be.

## 6. What the static surface says

The surface answers *"can this program produce approximate values"* **without running it**, by walking the call graph. `root` joins `sine` as a source, and the two are **reported differently, because they mean different things**:

| the program reaches | the surface says |
|---|---|
| `sine` | `numbers: approximate — this program reaches \`sine\`` |
| `root` only | `numbers: may be approximate — this program reaches \`root\`, which is exact when its argument is a perfect square` |
| both | the `sine` line, which is the stronger claim |

**This does not weaken the static guarantee, and the reason is worth stating.** The effect surface has always been a *may*-analysis: a program whose network call sits inside a function nothing calls still reports `network`, because the surface reports what a program CAN do. `root` introduces no new kind of imprecision — it introduces a second wording, because "reaches an operation that sometimes approximates" is a different fact from "reaches an operation that always does", and a surface that flattened them would be less informative, not more.

## 7. What this does not change

- **`==` has no tolerance.** Two approximate values compare as their underlying rationals. `root of 2 * root of 2 == 2` is `false`.
- **`round ... to N places` stays exact.** A deliberate precision reduction is not an approximation.
- Counts move to **32 keywords, 13 builtins, 7 effect kinds** — one builtin, no new keyword, no new effect kind, no new syntax.

## 8. Acceptance

- [ ] `root of 0/1/4/9/0.25/2.25` exact and correct; `root of 2/3/10` approximate.
- [ ] `root of -1` errors with `not-a-number` and names the fix, identically in all three implementations.
- [ ] The three implementations agree **bit for bit** across a sweep of exact and inexact arguments.
- [ ] `root of (sine of 30)` is approximate.
- [ ] The static surface distinguishes a `root`-only program from a `sine` program.
- [ ] `root of 9` reports **exact** through the `why` chain and the value's own property.
- [ ] Counts are 32 / 13 / 7.
