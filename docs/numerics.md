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

## Convergence: one mechanism, two riders

Approximate iteration has a single shape (DESIGN.md "convergence over a lazy range"):
advance until successive observations differ by at most `CONVERGENCE_TOLERANCE`
(`1e-12`), otherwise error at the cap rather than return a possibly-misleading partial
result. Three knobs live at the top of `runtime.py`:

| Knob | Value | Role |
|---|---|---|
| `CONVERGENCE_TOLERANCE` | `1e-12` | plateau test shared by both features (`EXACT_CONVERGENCE_TOLERANCE = 1/10^12` mirrors it for exact-tier comparisons) |
| `MAX_TERMS` | `2_000_000` | fold-term budget before `` `\sum did not converge within … terms `` |
| `MAX_PROBES` | `200` | per-side `\lim` probe budget |

The two riders:

- **Infinite-range folds** (`\sum(i=1..) 1/i^2`) accumulate partial sums/products in the
  **float tier**. Exact tiers are wrong for this job twice over: rationals with
  exponentially growing denominators stall plateau detection long before the tolerance is
  meaningful, and the tail remaining when a plateau triggers (~tolerance-sized) only makes
  sense compared in floating point. Consequences, pinned: results print as floats;
  slow-tail series like ζ(2) stop around one million terms and land within ~1e-6 of the
  limit; monotone divergence and NaN partials error immediately or at the cap.
- **`\lim(x=a)`** coerces its anchor to float, probes at `a ± h` with `h` halving from
  ~0.8% of `max(|a|, 1)`, and never evaluates at `a` itself — a step that would round back
  onto the anchor ends the side first. Each side stops on the same plateau test; sides
  further apart than *twice* the tolerance report `` limit does not exist `` (each side
  legitimately plateaus up to one tolerance-radius away, so two matching estimates may sit
  2× apart).

Known sharp edges (not bugs): a body whose value approaches 0 can plateau prematurely
(the consecutive-partial test cannot distinguish "stable" from "the increments vanished");
cancellation-prone spellings of removable singularities lose float precision as steps
shrink and usually fail to stabilize. A relative-stopping rule or Richardson extrapolation
would tighten both if it ever matters.

## Float semantics

CPython floats deviate from MPFR in three places; the seam pins each deliberately rather
than inheriting the Python default:

| Situation | MPFR/rug behavior | Python default | Seam behavior |
|---|---|---|---|
| `x / ±0.0` | signed infinity (`NaN` only for `0/0`) | raises `ZeroDivisionError` | signed infinity / `NaN` |
| float power overflow | unbounded exponent range | raises `OverflowError` | saturates to signed infinity |
| negative base, fractional exponent | `NaN` | returns a `complex` | `NaN` |

## Non-finite values

The float tier carries IEEE non-finite values under the pinned semantics above:
`0.0/0.0` → `NaN`, `1.0/0.0` → signed `Inf`, float overflow saturates. `\inf` and
`\nan` name them as protected prelude constants (`-\inf` is unary minus on `\inf`).
They are ordinary float values — they bind, propagate through arithmetic, and are
rejected anywhere a finite number is required:

- Assign-or-check `=` is IEEE-strict: NaN never equals itself, so `x = \nan` always
  prints `false` even when `x` is NaN (matching MPFR/rug). Comparisons are all
  `false` on NaN, also per IEEE. There is no direct NaN test today.
- Conditions must be booleans — no numeric truthiness. `\if(\nan, ...)` is a typed
  error exactly like `\if(0, ...)` (docs/grammar.md, `## Functions and conditionals`).
- Range bounds must be finite: `1..\inf` and `\inf..3` are typed errors — `a..` is
  the language's infinite range form. A non-finite endpoint in the finite-range loop
  would iterate forever, or exact-accumulate rationals that never converge.
- The convergence riders reject non-finite partials (`\sum`) and anchors (`\lim`),
  as before.

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

## The Python boundary: conversion matrix

The seam is also where the `\py` escape hatch converts (docs/grammar.md). Values crossing
*into* Python need no conversion — ad numbers already are native `int`/`Fraction`/`float`,
and a string argument arrives as the native `str` it already is. Values coming *back* go
through `_to_ad`:

| Python value | ad result |
|---|---|
| `None` | rejected — "the call returned nothing" |
| `bool` | `int` (`True` → `1`; bool is an int subclass, checked first) |
| `int`, `float`, `Fraction` | pass through |
| `decimal.Decimal` | exact `Fraction`/`int` via its string-exact value |
| any other `numbers.Rational` | normalized `Fraction`/`int` (constructed from numerator/denominator explicitly — py3.12+'s single-Rational-arg constructor copies them unnormalized) |
| any other `numbers.Real` (incl. numpy floats) | widened to `float` |
| `str` | passes through — a full ad value: bindable, displays quoted and round-trippable, concatenates with `+` (`"data" + ".csv"`); every other arithmetic operator rejects it ("strings are not numbers") |
| `complex` | rejected — no complex tier yet |
| anything else (list, dict, ndarray, ...) | rejected — names the type, never truncates silently |

A callee raising maps to a spanned error at the call (`sqrt: ValueError: math domain
error`), keeping the REPL alive like every other typed failure. Callables themselves are
bindable values (`s = \py("math.sqrt")` displays `<py math.sqrt>`); arithmetic on one is a
typed "operands must be numbers" failure at the operator's span.

## What later phases add here

Symbolic closed forms, algebraic numbers, and the RRA fallback all become new cases in
this module's dispatch — the compiler/driver layers above are unaffected by their
addition, which is the entire point of the seam.
