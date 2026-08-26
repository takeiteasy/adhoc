# Numerics: the numeric seam

`adhoc/runtime.py` defines an opaque value type (`int | Fraction | float`) and a fixed set
of operations (`nadd`, `nsub`, `nmul`, `ndiv`, `npow`, `nneg`, `neq`, `nshow`). Nothing above
the seam calls arithmetic operators directly on a value derived from user input — it only
calls through this seam.

## Why a seam

The design's full tower — bignum integers, bignum rationals, symbolic closed forms (`π`,
`√n`, ...), algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback, see
`DESIGN.md` — has no single builtin covering it. If evaluation called `+`/`*` directly,
adding the upper tiers later would mean retrofitting arithmetic dispatch through code that
was never written expecting it. Putting the seam in from the start costs a little now and
avoids that later.

## Backing

Values are Python natives:

- `int` — arbitrary precision natively.
- `fractions.Fraction` — arbitrary-precision rational, always normalized; a denominator of
  `1` collapses back to `int` at every constructor (`_normalize`), so display never prints
  `"1/1"` instead of `"1"` (or rather `1`, since a collapsed rational *is* an int).
- `float` — the fallback once an operation can't stay exact (a float literal or a
  non-integer exponent), a 53-bit double just like the design's default mantissa width.
  gmpy2 or sympy types can slot behind the same functions later without touching anything
  above the seam.

Arithmetic stays at the lowest tier that remains exact: any `float` operand demotes the
result to `float`; otherwise any `Fraction` promotes both operands to exact rationals;
otherwise plain integer arithmetic.

`npow` keeps an exact base exact for integer exponents (including negative ones — `2^-1`
is the exact rational `1/2`, and `0^-n` raises the typed division-by-zero failure, the
same failure as `1/0`, not a separate untyped error); a non-integer exponent falls to
`float`.

Every failure mode in this module is a typed `NumError`, not a generic exception — that's
what lets the REPL and script driver catch "arithmetic failed" specifically and attach the
offending expression's span to it, rather than the whole run aborting.

## Float semantics

CPython floats deviate from MPFR in three places; the seam pins each deliberately rather
than inheriting the Python default:

| Situation | MPFR/rug behavior | Python default | Seam behavior |
|---|---|---|---|
| `x / ±0.0` | signed infinity (`NaN` only for `0/0`) | raises `ZeroDivisionError` | signed infinity / `NaN` |
| float power overflow | unbounded exponent range | raises `OverflowError` | saturates to signed infinity |
| negative base, fractional exponent | `NaN` | returns a `complex` | `NaN` |

## Display

Exact rationals display as `a/b` (`1/3` prints `1/3`, not `0.333...`) — the collapse step
above means `nshow` only ever sees a genuinely non-integer rational there. Decimal display
is reserved for values that are already inexact: showing an *exact* rational through
decimal machinery would be a category error — `1/3` never leaves the rational tier, per
the tower's own "stay at the lowest tier that remains exact" rule.

Floats print via Python's shortest-round-trip `repr` (`"1.0"`, `"1.4142135623730951"`),
with two adjustments so output matches `f64` `Display`: scientific notation is expanded
positionally (`10000000000000000.0`, `0.0000001`), and a bare integer-looking value gets a
trailing `.0`. Non-finite values print `NaN`, `Inf`, `-Inf`.

## What later phases add here

Symbolic closed forms, algebraic numbers, and the RRA fallback all become new cases in
this module's dispatch — the compiler/driver layers above are unaffected by their
addition, which is the entire point of the seam.
