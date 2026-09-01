# Numerics: the numeric seam

`adhoc/runtime.py` defines an opaque value type (`int | Fraction | float | Symbolic`) and
a fixed set of operations (`nadd`, `nsub`, `nmul`, `ndiv`, `npow`, `nneg`, `neq`,
`nshow`). Nothing above the seam calls arithmetic operators directly on a value derived
from user input — it only calls through this seam.

## Why a seam

The design's full tower — bignum integers, bignum rationals, symbolic closed forms (`π`,
`√n`, ...), algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback, see
`DESIGN.md` — has no single builtin covering it. If evaluation called `+`/`*` directly,
adding the upper tiers later would mean retrofitting arithmetic dispatch through code that
was never written expecting it. Putting the seam in from the start costs a little now and
avoids that later.

## Backing

Values are Python natives plus one tier type:

- `int` — arbitrary precision natively.
- `fractions.Fraction` — arbitrary-precision rational, always normalized; a denominator of
  `1` collapses back to `int` at every constructor (`_normalize`), so display never prints
  `"1/1"` instead of `"1"` (or rather `1`, since a collapsed rational *is* an int).
- `adhoc/symbolic.py`'s `Symbolic` — a rational coefficient times exactly one recognized
  closed-form atom, stored as the canonical sympy expression (see below).
- `float` — the fallback once an operation can't stay exact (a float literal, a
   non-integer exponent with no closed form), a 53-bit double just like the design's
   default mantissa width. gmpy2 types can slot behind the same functions later without
   touching anything above the seam.

Arithmetic stays at the lowest tier that remains exact: any `float` operand demotes the
result to `float`; otherwise any `Symbolic` operand dispatches into the symbolic tier
(whose own non-representable results demote to `float` in turn); otherwise any
`Fraction` promotes both operands to exact rationals; otherwise plain integer arithmetic.

`npow` keeps an exact base exact for integer exponents (including negative ones — `2^-1`
is the exact rational `1/2`, and `0^-n` raises the typed division-by-zero failure, the
same failure as `1/0`, not a separate untyped error); a non-integer exponent tries the
symbolic tier first (`2^(1/2)` is `√2`, `8^(1/3)` collapses to `2`) and falls to
`float` when no closed form exists.

Every failure mode in this module is a typed `NumError`, not a generic exception — that's
what lets the REPL and script driver catch "arithmetic failed" specifically and attach the
offending expression's span to it, rather than the whole run aborting.

## Symbolic closed forms (tier 3)

`adhoc/symbolic.py` implements the first tier above exact rationals (DESIGN.md,
`## exact arithmetic (internals)`): common irrationals are kept exact as a **rational
coefficient times one recognized atom** instead of being approximated:

| Atom | Form | Examples |
|---|---|---|
| πⁿ | `π` and positive integer powers | `π`, `π·π` = `π²` |
| √r | square root of a positive rational, normalized | `√2`, `√8` = `2√2`, `√(1/2)` = `√2/2` |
| eʳ | e to a nonzero rational power | `e`, `e²` |
| ln r | natural log of a positive rational ≠ 1 | `ln 2` |
| trig | `sin(π·r)`, `cos(π·r)`, `tan(π·r)` for rational r | `sin(π/2)` = `1`, `sin(π/3)` = `√3/2`, `sin(π/7)` stays symbolic |

The backing is **sympy**, and it does the algebra: its automatic simplification produces
exactly these canonical forms (`√2·√3` = `√6`, `(√2)²` = `2`, `π − π` = `0`,
`e^(1/2)·e^(1/2)` = `e`, `sin(π/2)` = `1`), and `classify` is the tier's only admission
gate — a rational result collapses back to `int`/`Fraction`, a coefficient×atom result is
admitted, anything else raises. Because the stored forms are canonical, structural
equality decides the tier's equalities exactly (`√2 = 2^(1/2)` is `true`), and ordering
across exact + symbolic values is decided exactly too (`π < 22/7` is `true` — sympy
settles relational expressions between explicit numbers, not float-compares them).

The **strict single-term shape** is deliberate: a value like `π + 1`, `π·√2` or `1/π`
has no coefficient×atom form, so the gate rejects it and the seam **falls to the float
tier** (`π + 1` is `4.141592653589793`). The float tier is the current stand-in for the
algebraic and RRA tiers above this one — when those land, these values stop being
approximated. Until then, a float result mixed among exact values is the visible sign
that the symbolic tier could not hold the value.

Domain failures are typed `NumError`s — the exact tiers have no infinity and there is no
complex tier:

| Input | Exact tier | Float tier (unchanged) |
|---|---|---|
| `\sqrt(-1)`, `(-2)^(1/2)` | typed error — "not a real number" | `math.sqrt` ValueError / NaN from `_fpow` |
| `\ln(0)`, `\ln(-1)` | typed error — "defined only for positive numbers" | ValueError |
| `\tan(π/2)` | typed error — "odd multiples of pi/2" | huge finite float |
| `0^(-1/2)` | typed division-by-zero (same failure as `1/0`) | `Inf` |

The `√` prefix operator rewrites to a `\sqrt(...)` application at parse time
(docs/grammar.md), so the prelude builtins carry all of this: exact arguments go through
the gate (`\sqrt(2)` stays `√2`, `\ln(2)` stays exact), arguments with no closed form
fall to the float tier (`\sin(1)` is `0.8414709848078965`), and float arguments stay
entirely on the float tier (`\sqrt(2.0)` is `1.4142135623730951`).

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
- Conditions must be booleans — no numeric truthiness. `\nan ? 1 : 2` is a typed
  error exactly like `0 ? 1 : 2` (docs/grammar.md, `## Conditionals`).
- Range bounds must be finite: `1..\inf` and `\inf..3` are typed errors — `a..` is
  the language's infinite range form. A non-finite endpoint in the finite-range loop
  would iterate forever, or exact-accumulate rationals that never converge.
- The convergence riders reject non-finite partials (`\sum`) and anchors (`\lim`),
  as before.

## Display

Exact rationals display as `a/b` (`1/3` prints `1/3`, not `0.333...`) — the collapse step
above means `nshow` only ever sees a genuinely non-integer rational there. Decimal display
is reserved for values that are already inexact or truncated: showing an *exact* rational
through decimal machinery would be a category error — `1/3` never leaves the rational
tier, per the tower's own "stay at the lowest tier that remains exact" rule.

Symbolic reals print as **15 significant digits, expanded positionally, plus a trailing
ellipsis** (`π` is `3.14159265358979...`, `√2` is `1.4142135623731...`, `-π` is
`-3.14159265358979...`) — the DESIGN display examples verbatim. The value is exact; the
digits are a truncation, and the ellipsis says so. (The full display policy for the
non-exact tiers is its own ticket.)

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
| `Symbolic` (an ad symbolic real passed through Python) | passes through |
| a sympy expression (`\py("sympy.sqrt")(2)`) | recognized closed forms convert through the tier's own gate (`sympy.sqrt(2)` arrives as `√2`; sympy rationals convert exactly via the row above); anything else rejected |
| any other `numbers.Real` (incl. numpy floats) | widened to `float` |
| `str` | passes through — a full ad value: bindable, displays quoted and round-trippable, concatenates with `+` (`"data" + ".csv"`); every other arithmetic operator rejects it ("strings are not numbers") |
| `complex` | rejected — no complex tier yet |
| anything else (list, dict, ndarray, ...) | rejected — names the type, never truncates silently |

A callee raising maps to a spanned error at the call (`sqrt: ValueError: math domain
error`), keeping the REPL alive like every other typed failure. Callables themselves are
bindable values (`s = \py("math.sqrt")` displays `<py math.sqrt>`); arithmetic on one is a
typed "operands must be numbers" failure at the operator's span.

## What later phases add here

The symbolic closed-form tier is in (above). Algebraic numbers and the RRA fallback
become new cases in this module's dispatch the same way — the compiler/driver layers
above are unaffected by their addition, which is the entire point of the seam. The
algebraic tier's first payoff is already visible: today's float fallbacks for values like
`π + 1`, `π·√2` and `2^(1/3)` become exact there.
