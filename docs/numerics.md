# Numerics

`ad` keeps finite numbers exact unless an operation uses a float operand or an
approximate iteration method. Exact values may display approximate digits;
that does not change the stored value.

## Numeric tiers

Arithmetic chooses the lowest tier that can represent the result exactly.

| Tier | Representation | Examples |
|---|---|---|
| Integer | Python `int` | `3`, arbitrary precision |
| Rational | Normalized `Fraction` | `1/3`, `0.5` is exactly `1/2` |
| Gaussian rational | `Gaussian` | `2+3i`, rational real and imaginary components |
| Symbolic closed form | `Symbolic` | `π`, `√2`, `π·i` |
| Algebraic | `Algebraic` | `2^(1/3)`, `1+√2·i` |
| Recursive Real Arithmetic | `RRA` | `π+1`, `1/π`, `2^√2`, `\sin(1+i)` |
| Float | Python `float` | `1.`, `5e-1`, `Inf`, `NaN` |
| Complex float | Python `complex` | `1. + i`, `\complex(1., 2.)` |

A rational with denominator 1 collapses to an integer. A complex value with zero
imaginary part collapses to its real component. Exact tiers contain no infinity.
A float operand selects float or complex float arithmetic. Mixed comparisons
use float rounding when conversion stays finite; see [comparisons](#comparisons).
Complex values are not ordered.[^dispatch]

`\eig(A)` preserves the exact tiers for exact matrices. Any float entry selects
numerical computation for the whole matrix; see [eigensystems](eigen.md).

Tensors contain scalars from any tier. Scalar arithmetic applies elementwise,
with scalar broadcasting; contraction uses the same exact scalar operations.
See [tensors](grammar.md#tensors).

Matrix elimination preserves exact pivots for exact coefficient matrices.
Any float or complex-float coefficient selects a relative machine-precision
pivot cutoff; right-hand sides do not affect that choice. See
[linear algebra](stdlib.md#linear-algebra) for singularity behavior and examples.
The cutoff is independent of `\prec` and is not user-configurable.

## Powers and roots

Integer exponents preserve exactness, including negative exponents: `2^-1` is
`1/2`. Zero raised to a negative exponent gives a typed division-by-zero error.

For a negative real base, an exact exponent `p/q` in lowest terms selects the
real branch when `q` is odd. Other fractional exponents select the complex
principal value.

| Expression | Result |
|---|---|
| `(-8)^(1/3)` | `-2` |
| `(-8)^(2/3)` | `4` |
| `(-2)^(1/2)` | Exact `√2·i` |
| `2^(1/2)` | Exact `√2` |
| `8^(1/3)` | `2` |
| `2^(1/3)` | Exact algebraic value |
| `(√2)^(1/2)` | Exact `2^(1/4)` |
| `(1+i)^(1/2)` | Exact complex algebraic value |
| `2^√2` | Exact RRA value |
| `(-8.)^(1/3)` | `-2.0` |
| `(-2.)^(1/2)` | `1.4142135623730951i` |

`√x` parses as `\sqrt(x)`. Exact arguments pass through the symbolic, algebraic
and RRA tiers as needed; float arguments stay inexact. Real floats with non-real
principal results and complex floats use `cmath`; `\gamma` and `\erf` use
`mpmath` for complex float results.

## Symbolic closed forms (tier 3)

A symbolic value is a rational coefficient times one recognized atom. A
pure-imaginary value remains symbolic when its imaginary component has this form.

| Atom | Allowed form | Examples |
|---|---|---|
| πⁿ | Positive integer powers of π | `π`, `π²` |
| √r | Square root of a positive rational | `√8 = 2√2`, `√(1/2) = √2/2` |
| eʳ | Nonzero rational exponent | `e`, `e²` |
| ln r | Positive rational argument other than 1 | `\ln(2)` |
| Trigonometric | `sin(πr)`, `cos(πr)`, `tan(πr)` for rational r | `\sin(π/3) = √3/2` |

SymPy simplification supplies canonical forms. Rational results collapse to
integers or fractions. Structural equality decides symbolic equality; real
ordering uses exact SymPy relations, such as `π < 22/7`.[^symbolic]

Values outside the single-atom form pass to the algebraic or RRA tier:
`√2 + 2^(1/3)` is algebraic; `π + 1`, `π·√2` and `1/π` are RRA values.

| Input | Exact argument | Float argument |
|---|---|---|
| `\sqrt(-1)` | `i` | `1.0i` |
| `\ln(-1)` | `π·i` | `3.141592653589793i` |
| `\ln(0)` | Typed domain error | Wrapped `ValueError` |
| `\tan(π/2)` | Typed domain error | A float approximation to π/2 gives a huge finite value |
| `0^(-1/2)` | Typed division-by-zero error | `Inf` |

## Algebraic numbers (tier 4)

Algebraic values have no recognized symbolic closed form and remain exact as
canonical SymPy expressions. Examples include `2^(1/3)`, `2^(1/4)` and
`√2 + 2^(1/3)`. Complex algebraic values use the same representation.

Every operation tries lower tiers again: `(2^(1/3))^3` collapses to `2`.
Transcendental results such as `π + 2^(1/3)` and `2^√2` pass to RRA.
Equality uses structural identity, then an exact minimal-polynomial fallback.
Real ordering is exact; complex ordering is a typed error.[^algebraic]

Square roots can remain algebraic: `\sqrt(2^(1/3))` is `2^(1/6)`.
Transcendental function results such as `\sin(2^(1/3))` pass to RRA.

## Recursive Real Arithmetic (tier 5)

RRA holds other finite real and complex values as canonical SymPy expressions.
Examples include `π + 1`, `1/π`, `2^√2`, `\sin(1)` and `\sin(1+i)`.
Results simplify back to lower tiers when possible: `(π + 1) - π` is `1`.

Approximation accepts a tolerance and returns a rational approximation. It raises
precision until successive evaluations agree within half that tolerance;
exhaustion gives an error.[^approximation]

RRA equality uses the Richardson–Fitch heuristic. Structural identity and exact
rational differences are checked first; otherwise progressively tighter probes
check whether the difference is distinguishable from zero. Complex comparisons
probe the modulus. Statement-level `=` uses this policy. See
[limitations](#limitations) for its accuracy ceiling.[^rra-equality]

Real ordering uses exact SymPy relations rather than the equality heuristic.
Mixed float comparisons follow the [comparison rules](#comparisons).

## Comparisons

Equality and ordering with a float operand compare float-rounded values when
the exact operand converts to a finite float. For example, `π` equals its float
approximation `3.141592653589793e0`, and `2^53+1` equals `9007199254740992.`.
Very small exact values can round to zero.

If the exact operand exceeds float range, real comparisons preserve the exact
value and compare the finite float as an exact binary rational.[^mixed-comparison]
Every finite exact value is less than `Inf`, greater than `-Inf`, and unequal
to either. Equality and ordering with `NaN` return `false`.

```text
10^1000 > 1.                -> = true
10^1000 < \inf              -> = true
r = 10^1000; r = 1.         -> false
```

Complex-float equality uses float-rounded components when conversion stays
finite. An exact value compares unequal if a component exceeds float range or
the complex float contains infinity or NaN. Complex floats with matching
infinity components compare equal; NaN components never compare equal.
A real float compares unequal to an exact complex value with a nonzero
imaginary part. Complex values are not ordered.

## Convergence

Infinite folds and numeric limits return approximate float or complex float
results. They stop when consecutive observations stabilize within tolerance,
or produce a typed error at their iteration cap. Non-finite partials and anchors
are rejected.

| Setting in `runtime.py` | Value | Purpose |
|---|---|---|
| `CONVERGENCE_TOLERANCE` | `1e-12` | Fold and limit plateau test[^plateau] |
| `MAX_TERMS` | `2_000_000` | Infinite-fold term budget |
| `MAX_PROBES` | `200` | Limit probe budget per side |
| `DIFF_TOLERANCE` | `1e-9` | First-derivative error estimate |
| `DIFF2_TOLERANCE` | `1e-6` | Second-derivative error estimate |
| `DIFF_HIGHER_TOLERANCE` | `1e-3` | Higher-derivative error estimate |
| `MAX_DIFF_POINTS` | `32` | Points per derivative stencil |
| `MAX_DIFF_SAMPLES` | `2000` | Body evaluations per numeric derivative |
| `MAX_INTERVALS` | `2000` | Adaptive integral subinterval budget per finite interval or infinite tail |

### Infinite folds

Finite folds accumulate at the lowest exact tier. Infinite `\sum`, `\prod`
and `\fold` over ranges or lazy sequences accumulate in the float tier.
Complex partials use complex floats and modulus comparisons.

Infinite sums can also return a confirmed tail estimate. Recognized shapes are
monotone power-law decay and strictly alternating shrinking terms. Divergent or
unrecognized shapes retain plateau detection and the cap error.[^tails]

Products use plateau detection only. Slow-tail products can require many terms
and retain roughly `1e-6` accuracy. The two heavyweight product tests carry the
`slow` pytest mark.

```text
\sum(i=1..10) i^2       ->  = 385
\sum(i=1..) 1/i^2       -- approximate infinite sum
\sum(i=1..) i           -- convergence error
```

### Limits

`\lim(x=a)` converts the anchor to float or complex float and probes shrinking
steps without evaluating at the anchor. Real anchors use both sides; estimates
must agree within twice the scaled tolerance. Disagreement reports
`limit does not exist`. A side that does not stabilize exhausts its probe budget.

Complex anchors use eight rays at golden-angle spacing. All rays must agree.
A complex result drops a component below the scaled tolerance:
`\lim(x=i) x^2` returns `-1.0`.[^limit-probes]

`\diff` and `\int` also use float iteration and typed cap errors, with Ridders
extrapolation and adaptive Gauss–Kronrod estimators. See [calculus](calculus.md).

## Float semantics

A trailing dot (`1.`) or exponent (`5e-1`, `1.5e3`) selects a float literal.
Plain decimals such as `0.5` are exact rationals. Python returns, float-argument
calls, non-finite constants and approximate iteration also produce floats.

| Operation | ad behavior | Python default |
|---|---|---|
| `x / ±0.0` | Signed infinity; `NaN` for `0/0` | `ZeroDivisionError` |
| Float power overflow | Signed infinity | `OverflowError` |
| Negative base, fractional exponent | Real odd-root branch for an exact odd-denominator exponent; otherwise complex principal value | Complex principal value |
| Complex float power overflow | Signed infinity per component | `OverflowError` |
| Complex float division by zero | Signed infinity or `NaN` per component | `ZeroDivisionError` |
| `x % 0.0` | `NaN`; exact `x % 0` is a typed error | `ZeroDivisionError` |
| `\round(2.675e0, 2)` | `2.68`; half away from zero on the shortest decimal representation | `2.67`; rounds the binary value |

### Standard library exactness

| Operation | Exact behavior |
|---|---|
| `%` | Floored remainder on rationals; symbolic reals use `a - b⌊a/b⌋` |
| `\floor`, `\ceil`, `\trunc`, `\round` | Exact integers for exact inputs |
| `\log(b, x)` | Exact for positive rationals with proportional prime factorizations; otherwise symbolic or RRA |
| Negative or complex logarithm | Complex principal value; complex `\log(b, x)` uses `\ln(x)/\ln(b)` |
| `\atan2` | Real arguments only; use `\arg` for a complex angle |
| Half-integer `\gamma(x)` and `x!` | Multiples of `√π`; other non-integers use RRA |
| `r∠θ` | RRA for non-special angles; `\abs(2∠1)` simplifies to `2`, `\arg(2∠3)` to `3` |

For example, `\log(1/2, 8)` is `-3` and `\log(2, i)` stays exact.
See [standard library](stdlib.md) for the complete function reference.

## Non-finite values

`\inf` and `\nan` are protected float constants. `-\inf` is unary negation.
Non-finite values bind and propagate through arithmetic, but operations requiring
finite inputs reject them.

| Context | Rule |
|---|---|
| Existing binding check with NaN | `false`, even when the existing value is NaN |
| Numeric comparisons with NaN | `false` |
| `\isnan`, `\isinf`, `\isfinite` | Inspect float states; exact values are finite |
| Conditional | Requires a boolean; `\nan ? 1 : 2` is a typed error |
| Range bound | Real; explicit infinite endpoints create non-iterable [intervals](intervals.md); finite-start `a..` is a lazy progression; NaN is rejected |
| Infinite fold partial or limit anchor | Non-finite values are rejected |

## Display

| Value | Display policy | Example |
|---|---|---|
| Integer | Whole number | `2` |
| Rational | Fraction | `1/3` |
| Gaussian rational | Exact components | `2-3i`, `i`, `1/2-1/3i` |
| Symbolic or algebraic | 15 significant digits and ellipsis | `√2` → `1.4142135623731...` |
| RRA | Session precision and ellipsis; default 15 | `π + 1` → `4.14159265358979...` |
| Float | Shortest round-trip decimal, expanded positionally | `1.0`, `0.0000001` |
| Non-finite float | Named state | `NaN`, `Inf`, `-Inf` |

Complex values display each component with its tier's policy. A zero imaginary
part collapses to the real value; a zero real part is omitted.
`1 + √2·i` prints `1+1.4142135623731...i`.

`\prec(n)` sets RRA display precision from 1 to 1000 significant digits and
returns the new setting. It is protected and applies to both REPL and script
output. Symbolic and algebraic display stays at 15 digits; rationals and floats
retain their own policies.

RRA display compares successive approximations before printing the requested
digits. If they do not agree, it prints the longest agreed prefix. The ellipsis
marks approximate displayed digits; the value remains exact.[^display-tightening]

## The Python boundary: conversion matrix

`\py` and `\pyimport` convert Python results through `_to_ad`.

| Python value | ad result |
|---|---|
| `None` | Error: “the call returned nothing” |
| `bool` | Integer: `True` → `1` |
| `int`, `float`, `Fraction` | Unchanged |
| `decimal.Decimal` | Exact normalized fraction or integer |
| Other `numbers.Rational` | Normalized fraction or integer[^rational] |
| ad numeric or collection value | Unchanged |
| SymPy expression | Symbolic, algebraic or RRA when admissible; rationals convert exactly; other expressions rejected |
| Other `numbers.Real`, including NumPy floats | Widened to `float` |
| `str` | String; quoted display and `+` concatenation |
| `complex` | Complex float; zero imaginary part collapses to float; non-finite components retained |
| `list`, `tuple` | Array with recursively converted elements |
| `set`, `frozenset` | Set with recursively converted elements |
| NumPy `ndarray` | Tensor; 0-dimensional array becomes a scalar[^ndarray] |
| Other types, including `dict` | Typed rejection naming the type |

Arguments convert in the other direction:

| ad value | Python argument |
|---|---|
| Tensor | Nested row-major lists |
| Array | List of converted elements |
| Set | `frozenset`; list when an element is unhashable |
| Symbolic solution set | Unchanged non-enumerating value |
| Other value | Unchanged |

```text
\py("sorted")({3, 1, 2})    ->  = ⟨1, 2, 3⟩
\py("len")([1, 2; 3, 4])    ->  = 2
```

Strings remain native Python strings. Internal prelude functions and user-defined
functions retain boolean results; conversion to integers applies to Python
callables at the boundary.

Python callables bind as values: `s = \py("math.sqrt")` displays `<py math.sqrt>`.
Arithmetic on a callable is a typed error. Python exceptions become errors at the
call's source span, such as `sqrt: ValueError: math domain error`; the REPL stays
alive.

## Limitations

- RRA equality is a heuristic relying on Schanuel's conjecture. Distinct values
  closer than the tightest probe (`1e-50`) can compare equal.
- Eight-ray complex limits are a heuristic, not a proof of a two-dimensional
  limit. See [standard library limitations](stdlib.md#limitations).
- Irregular sign-changing series may have no recognized tail bound and use
  plateau detection. Near zero the tolerance has an absolute floor; exact-zero
  limits outside recognized tail shapes are unsupported.
- Cancellation near removable singularities can prevent numeric limits from
  stabilizing. Simplify the body before probing.
- Empty, ragged and non-numeric NumPy arrays cannot become tensors.

[^mixed-comparison]: Comparison conversion handles both `OverflowError` and a
    conversion that silently returns infinity. Finite floats convert with
    `Fraction`, preserving their binary value; the numeric seam then uses its
    existing exact-tier equality and ordering dispatch.

[^dispatch]: `adhoc/runtime.py` exposes the numeric operations (`nadd`, `nsub`,
    `nmul`, `ndiv`, `npow`, `nneg`, `neq`, `nshow`). Evaluation uses these functions
    for user values. Dispatch checks floats first, then symbolic/algebraic/RRA,
    Gaussian, rational and integer arithmetic. Exact expressions of undecided
    reality fall back to real or complex floats.

[^symbolic]: `adhoc/symbolic.py` uses `classify` as its admission gate. SymPy
    supplies simplifications such as `√2·√3 = √6`, `(√2)² = 2` and `π - π = 0`.
    Rational results collapse; coefficient-times-atom results enter this tier;
    other results pass to higher tiers. Gaussian rationals collapse to their own tier.

[^algebraic]: `adhoc/algebraic.py` stores SymPy expressions without inspecting
    their internal minimal-polynomial and isolating-interval representation.
    Equality checks whether `minpoly(a-b) == x`, including complex differences.

[^approximation]: `adhoc/rra.py` exposes `approximate` and `to_function`.
    Successive SymPy evaluations at escalating precision return the agreed
    decimal value as an exact `Fraction`. SymPy supplies the series and iterative
    methods; there is no separate interval-refinement implementation.

[^rra-equality]: Probes use tolerances `1e-12`, `1e-30` and `1e-50`. An exact
    rational difference, or rational modulus for a complex difference, bypasses
    the probes. Otherwise equality holds while every probe is indistinguishable
    from zero; the first distinguishable probe decides inequality.

[^plateau]: Float comparisons use `|Δ| <= tol × max(1, |prev|, |cur|)`.
    `EXACT_CONVERGENCE_TOLERANCE = 1/10^12` supplies the exact-tier counterpart.
    RRA approximation uses a caller-supplied tolerance rather than this fixed setting.

[^tails]: `_FoldTailEstimator` infers a power-law exponent from consecutive
    term ratios and estimates the tail with the integral-test form. Alternating
    terms use the Leibniz bound and midpoint correction. A confirmation window
    checks the proposed error before returning; raw plateaus win ties. Harmonic
    tails (`p = 1`), monotone divergence and non-finite partials do not get a tail
    estimate. `\sum(i=1..) 1/i^2` typically stops around 100,000 terms at roughly
    `1e-10` accuracy. `_ComplexTailEstimator` estimates each component separately;
    identically zero components, or shapeless components whose last eight terms
    vanish, settle at their partial value.

[^limit-probes]: The step starts around 0.8% of `max(|a|, 1)` and halves each
    probe. A side stops before a step rounds back onto the anchor. Complex probes
    use four golden-angle directions and their opposites. Components below the
    modulus-scaled tolerance are dropped from complex results.

[^display-tightening]: RRA display starts with a two-digit guard and tightens
    tolerances by about 1000×, for up to six rounds. Complex components tighten
    as a pair. Float formatting starts from Python `repr`, expands scientific
    notation positionally and adds `.0` to integer-looking finite values.

[^rational]: Construction uses numerator and denominator explicitly; Python
    3.12's single-rational-argument `Fraction` constructor can copy unnormalized
    components. Python booleans are checked before integers because `bool`
    subclasses `int`.

[^ndarray]: Array conversion detects the module name and uses `tolist`.
    NumPy is a runtime dependency and supplies numerical eigenpairs for `\eig`.
