# Numerics: the `Num` seam

`src/num.jl` defines an opaque `AdNum` value and a fixed set of operations
(`nadd`, `nsub`, `nmul`, `ndiv`, `npow`, `nneg`, `neq`, `nshow`). `src/eval.jl` never calls
Julia's `+`/`*`/... directly on a value that came from user input — it only calls through
this seam.

## Why a seam, in phase 0

Julia's own numeric tower already gives us most of what the target design's tower needs at the
bottom (arbitrary-precision integers via `BigInt`, exact rationals via `Rational{BigInt}`), so
phase 0 gets those almost for free. But the design's upper tiers — symbolic closed forms
(`π`, `√n`, ...), algebraic numbers, and a Recursive Real Arithmetic fallback — have no Julia
builtin at all. If the evaluator called `+`/`*` directly, adding those tiers later would mean
retrofitting arithmetic dispatch through code that was never written expecting it. Putting the
seam in from the start costs a little now and avoids that.

## Phase 0 backing

Three Julia types stand in for the bottom of the tower:

- `Int` / `BigInt` — widens automatically on overflow.
- `Rational{BigInt}` — `int / int` produces a rational, normalized so a denominator of `1`
  collapses back to an integer (`1/3 + 1/3 + 1/3 == 1`, exactly, not `0.999...`).
- `Float64` — the fallback once an operation can't stay exact (e.g. non-integer powers).

`npow` keeps a rational base exact for integer exponents; otherwise it falls to `Float64`.

## Display

Exact rationals display as `a/b` (`1/3` prints `1/3`, not `0.333...`) — `normalize` already
collapses an integral rational back to `BigInt`, so `nshow` only ever sees a genuinely
non-integer value here. Decimal display is reserved for the RRA tier (phase 3): once a value
needs RRA to represent at all, it's no longer exact, so a decimal approximation is the honest
display, obtained by repeatedly requesting tighter tolerance until enough digits are provably
stable. Showing an *exact* rational through that same decimal machinery would have been a
category error — `1/3` never leaves the rational tier, per the tower's own "stay at the lowest
tier that remains exact" rule, so it never needed RRA-style display in the first place.

## What later phases add here

Symbolic closed forms, algebraic numbers, and the RRA fallback all become new cases inside
this module's dispatch — `src/eval.jl` and everything above it is unaffected by their
addition, which is the entire point of the seam.
