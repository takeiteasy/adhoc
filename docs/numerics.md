# Numerics: the `Num` seam

`src/num` defines a fixed set of operations (`nadd`, `nsub`, `nmul`, `ndiv`, `npow`, `nneg`,
`neq`, `nshow`) over an opaque numeric value. `src/interpreter` never calls CL's `+`/`*`/...
directly on a value that came from user input — it only calls through this seam.

## Why a seam, in phase 0

CL's own numeric tower already gives us most of what the target design's tower needs at the
bottom (arbitrary-precision integers, exact rationals), so phase 0 gets those for free. But the
design's upper tiers — symbolic closed forms (`π`, `√n`, ...), algebraic numbers, and a
Recursive Real Arithmetic fallback — have no CL builtin at all. If the evaluator called
`+`/`*` directly, adding those tiers later would mean retrofitting arithmetic dispatch through
code that was never written expecting it. Putting the seam in from the start costs a little now
and avoids that.

## Phase 0 backing

Three CL types stand in for the bottom of the tower:

- `integer` — arbitrary-precision natively; no separate bignum type to widen into.
- `ratio` — `int / int` produces a ratio, and CL never represents a ratio with denominator
  `1` — it collapses back to an integer automatically (`1/3 + 1/3 + 1/3 == 1`, exactly, not
  `0.999...`). Unlike a host language without native rationals, this tier-collapse rule is
  native to CL, not something `src/num` implements.
- `double-float` — the fallback once an operation can't stay exact (e.g. non-integer powers).

`npow` keeps a rational base exact for integer exponents (CL's `expt` handles negative integer
exponents on rationals natively, producing a rational); otherwise it falls to `double-float`.

### Float format

CL's `*read-default-float-format*` defaults to `single-float`. Left alone, this would make a
literal like `0.5` read as a single-float (a real precision loss relative to the `double-float`
the tower is supposed to guarantee) and would print a double as `1.0d0` rather than `1.0`.
`src/interpreter`'s literal parser binds `*read-default-float-format*` to `double-float`
locally around every float read, `src/num`'s `nshow` binds it locally around every float
print, and `src/cli`'s `main` binds it for the whole session as a backstop. All three are
covered by tests (`test/test-num.lisp`, `test/test-grammar.lisp`) — this is the one place a
default CL behavior would otherwise silently diverge from the design.

## Display

Exact rationals display as `a/b` (`1/3` prints `1/3`, not `0.333...`) — a ratio can never have
denominator `1`, so `nshow` only ever sees a genuinely non-integer value here. Decimal display
is reserved for the RRA tier (phase 3): once a value needs RRA to represent at all, it's no
longer exact, so a decimal approximation is the honest display, obtained by repeatedly
requesting tighter tolerance until enough digits are provably stable. Showing an *exact*
rational through that same decimal machinery would have been a category error — `1/3` never
leaves the rational tier, per the tower's own "stay at the lowest tier that remains exact"
rule, so it never needed RRA-style display in the first place.

## What later phases add here

Symbolic closed forms, algebraic numbers, and the RRA fallback all become new cases inside
this module's dispatch — `src/interpreter` and everything above it is unaffected by their
addition, which is the entire point of the seam.
