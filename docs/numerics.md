# Numerics: the numeric seam

`adhoc/runtime.py` defines an opaque value type (`int | Fraction | float | Gaussian |
Symbolic | Algebraic | RRA`) and a fixed set of operations (`nadd`, `nsub`, `nmul`,
`ndiv`, `npow`, `nneg`, `neq`, `nshow`). Nothing above the seam calls arithmetic
operators directly on a value derived from user input — it only calls through this seam.

## Why a seam

The design's full tower — bignum integers, bignum rationals, symbolic closed forms (`π`,
`√n`, ...), algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback, see
`DESIGN.md` — has no single builtin covering it. If evaluation called `+`/`*` directly,
adding the upper tiers later would mean retrofitting arithmetic dispatch through code that
was never written expecting it. Putting the seam in from the start costs a little now and
avoids that later.

## Backing

Values are Python natives plus four tier types:

- `int` — arbitrary precision natively.
- `fractions.Fraction` — arbitrary-precision rational, always normalized; a denominator of
  `1` collapses back to `int` at every constructor (`_normalize`), so display never prints
  `"1/1"` instead of `"1"` (or rather `1`, since a collapsed rational *is* an int).
- `adhoc/gauss.py`'s `Gaussian` — an exact complex number with rational components
  (`2+3i`), the complex analogue of `Fraction`: ordinary exact rational component
  arithmetic, no sympy. The imaginary part never vanishes — a vanishing one collapses
  back to `int`/`Fraction` at every constructor (`make`), so display never prints
  `"2+0i"`.
- `adhoc/symbolic.py`'s `Symbolic` — a rational coefficient times exactly one recognized
  closed-form atom, stored as the canonical sympy expression (see below); the atom may
  be pure-imaginary (`√2·i`, `π·i`).
- `adhoc/algebraic.py`'s `Algebraic` — an algebraic number with no symbolic closed form
  (`2^(1/3)`, `2^(1/4)`, `√2 + 2^(1/3)`, `1 + √2·i`), stored as the canonical sympy
  expression (see below).
- `adhoc/rra.py`'s `RRA` — every other finite number, real or complex (`π + 1`, `π·√2`,
  `1/π`, `2^√2`, `sin(1)`, `sin(1+i)`), stored as the canonical sympy expression and
  approximated on demand as a `tolerance -> rational` function (see below).
- `float` — the explicitly-inexact tier: a float *spelling* (the trailing-dot marker
  `1.` or an exponent form `5e-1` — plain decimals are exact now), a float-argument
  call, or an IEEE non-finite value. Any float operand demotes the result to
  `float` (the fast path); no exact tier ever produces it. gmpy2 types can
  slot behind the same functions later without touching anything above the
  seam.

Arithmetic stays at the lowest tier that remains exact: any `float` operand demotes the
result to `float` — except a complex one, which is a typed error (there is no
complex-float tier, so float arithmetic can never silently truncate a complex
operand); otherwise any `Symbolic`, `Algebraic` or `RRA` operand dispatches into the
exact tiers (symbolic tried first, then algebraic, then RRA; a real value of undecided
reality demotes to `float` in turn — an undecided complex one is a typed error);
otherwise any `Gaussian` operand routes into the exact complex arithmetic
(`adhoc/gauss.py`); otherwise any `Fraction` promotes both operands to exact rationals;
otherwise plain integer arithmetic.

`npow` keeps an exact base exact for integer exponents (including negative ones — `2^-1`
is the exact rational `1/2`, and `0^-n` raises the typed division-by-zero failure, the
same failure as `1/0`, not a separate untyped error); a non-integer exponent on a
negative real base takes the **odd-root split** first — an exponent `p/q` in lowest
terms with `q` odd is the real branch via sign extraction (`(-8)^(1/3)` is `-2`,
`(-8)^(2/3)` is `4`), anything else the complex principal (`(-2)^(1/2)` is `√2·i`) —
and then tries the symbolic tier (`2^(1/2)` is `√2`, `8^(1/3)` collapses to `2`),
then the algebraic tier (`2^(1/3)` stays `2^(1/3)`, `(√2)^(1/2)` arrives as `2^(1/4)`,
`(1+i)^(1/2)` is algebraic complex), then the RRA tier (`2^√2` stays exact). The float
tier keeps its pinned NaN for negative bases with fractional exponents.

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
has no coefficient×atom form and is transcendental (not algebraic either), so the gate
rejects it and the seam tries the algebraic tier next, then the RRA tier, which
holds every finite number (`π + 1` is `4.14159265358979...`). A pure-imaginary
value whose imaginary side has a recognized real shape stays symbolic too
(`√2·i`, `π·i` — `\sqrt(-2)` is `1.4142135623731...i`, `\ln(-1)` is `π·i`); a
Gaussian rational collapses back to exact. A real value of undecided
reality is the only thing that still reaches the float tier. Algebraic
results without a closed form (`2^(1/3)`, `√2 + 2^(1/3)`) stay exact in the
algebraic tier instead.

Domain failures are typed `NumError`s — the exact tiers have no infinity (complex
results are values now, not failures):

| Input | Exact tier | Float tier (unchanged) |
|---|---|---|
| `\sqrt(-1)`, `(-2)^(1/2)` | the exact value `i` / `√2·i` | `math.sqrt` ValueError / NaN from `_fpow` |
| `\ln(-1)` | the exact value `π·i` | ValueError |
| `\ln(0)`, `\tan(π/2)` | typed error — "defined only for positive numbers" / "odd multiples of pi/2" | ValueError / huge finite float |
| `0^(-1/2)` | typed division-by-zero (same failure as `1/0`) | `Inf` |

The `√` prefix operator rewrites to a `\sqrt(...)` application at parse time
(docs/grammar.md), so the prelude builtins carry all of this: exact arguments go through
the gate (`\sqrt(2)` stays `√2`, `\ln(2)` stays exact, `\sqrt(-2)` is `√2·i`),
algebraic `√` arguments
through the algebraic gate (`\sqrt(2^(1/3))` is `2^(1/6)`, `\sqrt(√2)` is
`2^(1/4)`), arguments with no lower-tier form through the RRA gate (`\sin(1)`
stays exact, complex results included), and float arguments stay
entirely on the float tier (`\sqrt(2.)` is `1.4142135623730951`).

## Algebraic numbers (tier 4)

`adhoc/algebraic.py` implements the tier above symbolic closed forms (DESIGN.md,
`## exact arithmetic (internals)`): algebraic numbers with no recognized closed
form are kept exact as the canonical sympy expression — sympy holds the classic
minimal-polynomial + isolating-interval representation behind the seam, so this
module never inspects it directly.

The seam tries the symbolic tier first and this tier second: `2^(1/3)` and
`2^(1/4)` stay exact, `(√2)^(1/2)` arrives as `2^(1/4)`, multi-term sums like
`√2 + 2^(1/3)` stay exact, and integer powers collapse back down
(`2^(1/3)^3` is the integer `2`). Complex algebraics are held the same way
(`(1+i)^(1/2)` is `1.09868411346781...+0.455089860562227...i`, displayed as
each side truncated; negative algebraic bases take the odd-root real branch or
the complex principal per `npow`'s split). Transcendental results
(`π + 2^(1/3)`, `2^√2`) are not algebraic and fall to the RRA tier. Equality is
exact: structural identity is the fast path, with a minimal-polynomial fallback
for the pairs sympy never canonicalizes (`(1+√2)^2` vs `3+2√2` — the difference
of two algebraics is algebraic, so `minpoly(a-b) == x` decides it, complex
differences included); ordering is exact like the symbolic tier's (real values
only — complex ones are a typed "complex values are not ordered" failure). Only
`\sqrt` routes algebraic arguments through the gate (`\sqrt(2^(1/3))` is
`2^(1/6)` — `\sin`/`\ln` of a nonzero algebraic are transcendental, so those go
to the RRA tier). Display reuses the symbolic policy — 15 significant digits
plus a trailing ellipsis, each side for a complex value.

## Recursive Real Arithmetic (tier 5)

`adhoc/rra.py` implements the fallback above the algebraic tier (DESIGN.md,
`## exact arithmetic (internals)`): every other finite number, real or complex —
multi-term transcendental sums (`π + 1`, `π·√2`), reciprocals of atoms (`1/π`),
transcendental powers (`2^√2`), closed-form-free function results (`sin(1)`),
and their complex kin (`sin(1+i)`) — is kept exact as the canonical sympy
expression, the same Expr-wrapper pattern as the symbolic and algebraic tiers.
Equality for any RRA-involved pair is the Richardson–Fitch heuristic (DESIGN.md
`## exact arithmetic`): structural identity first, an exact shortcut when the
difference simplifies to a rational (or its modulus does, for a complex
difference), otherwise escalating `approximate` probes on the difference — on
its modulus when complex — (`1e-12`, `1e-30`, `1e-50`) — equal while
indistinguishable from zero at every probe, unequal at the first
distinguishable one. This proves hidden identities sympy never simplifies
(`\sin(1)^2 + \cos(1)^2` equals `1`, including across the tiers and on the
complex plane), and it is what statement-level `=` inherits. It is a heuristic
relying on Schanuel's conjecture — an accepted limitation, not a proof: values
closer than the tightest probe would miscompare, and ordering stays on the
exact sympy-relational path, never the heuristic (complex values are not
ordered at all). A float operand never reaches it: any float side demotes
equality to the float tier first, and a float/complex pair compares `false` —
a float is real, a complex value's imaginary part never vanishes.

The ticket's spelling — a real as a function `tolerance -> rational` — is
`approximate`/`to_function`: the stored expression evaluated at escalating
sympy precision until two successive evaluations agree within half the
requested tolerance, returning the agreed value's exact decimal expansion as a
`Fraction`. The series, continued fractions and iterative methods behind that
evaluation are sympy's, never hand-rolled at the seam; no separate
interval-refinement machinery exists. Pointwise sympy evaluation re-gates from
the top on every operation, so exact results collapse back down (`(π + 1) − π`
is the integer `1`, never an RRA value), and only `\sqrt` of a symbolic
argument additionally routes through the algebraic gate (`\sqrt(√2)` is
`2^(1/4)`) — every other closed-form-free builtin result is transcendental and
goes straight here. Display prints the session precision's significant digits
plus a trailing ellipsis (default 15: `π + 1` is `4.14159265358979...`),
tightened iteratively (below); a complex value tightens and truncates each
side (`sin(1+i)` is `1.29845758141598...+0.634963914784736...i`).

Display tightening shares the convergence shape with a caller-supplied
target: successive `approximate` observations at tightening tolerances (each
~1000x tighter, from a 2-digit guard, up to six rounds) must render
identically to the full target before those digits print; when no two
successive observations agree, the longest agreed prefix prints instead —
degrade, never a display error. `\prec(n)` sets the session target
(significant digits, 1..1000, RRA tier only — symbolic and algebraic display
stay fixed at 15, floats keep shortest-round-trip, exact rationals keep
`a/b`); it returns the new value, is protected like every prelude name, and
reaches display through the single `nshow` path, so REPL and script mode
agree.

## Convergence: one mechanism, two riders, one estimator

Approximate iteration has a single shape (DESIGN.md "convergence over a lazy range"):
advance until successive observations differ by at most `CONVERGENCE_TOLERANCE`
(`1e-12`, relatively scaled for large magnitudes — see below), otherwise error at the cap
rather than return a possibly-misleading partial
result. Three knobs live at the top of `runtime.py`:

| Knob | Value | Role |
|---|---|---|
| `CONVERGENCE_TOLERANCE` | `1e-12` | plateau test shared by both features (`EXACT_CONVERGENCE_TOLERANCE = 1/10^12` mirrors it for exact-tier comparisons). The float branch scales relatively — `|Δ| <= tol · max(1, |prev|, |cur|)` — so O(1) and near-zero iteration behaves exactly as before while large-magnitude iteration (whose float64 ulps dwarf an absolute tolerance) can still settle |
| `MAX_TERMS` | `2_000_000` | fold-term budget before `` `\sum did not converge within … terms `` |
| `MAX_PROBES` | `200` | per-side `\lim` probe budget |

RRA approximation (`approximate` in `adhoc/rra.py`) shares the shape with a
caller-supplied tolerance rather than the fixed knob: escalate precision until
two successive evaluations agree within half the tolerance, otherwise error
rather than return a possibly-misleading partial. No second mechanism exists.

The two riders:

- **Infinite-range folds** (`\sum(i=1..) 1/i^2`) accumulate partial sums/products in the
  **float tier**. Exact tiers are wrong for this job twice over: rationals with
  exponentially growing denominators stall plateau detection long before the tolerance is
  meaningful, and the tail remaining when a plateau triggers (~tolerance-sized) only makes
  sense compared in floating point. Consequences, pinned: results print as floats.
  Infinite **sums** additionally get a tail-estimated early exit (`_FoldTailEstimator`
  in `adhoc/runtime.py`): monotone `k^-p` terms (decay exponent read from consecutive
  ratios, tail from the integral-test form, partial-plus-tail returned) and strictly
  alternating shrinking terms (Leibniz bound with the midpoint correction) propose a
  limit with a claimed error, and the proposal returns only after a confirmation window
  honors it — verify-before-return, with the raw plateau always winning ties and the cap
  error untouched. `\sum(i=1..) 1/i^2` now stops around one hundred thousand terms at
  ~1e-10-grade instead of around one million at ~1e-6; monotone divergence, the harmonic
  tail (`p = 1`) and NaN partials still abstain and error immediately or at the cap.
  Infinite **products** keep the plateau only: their log-space decay ratios inherit the
  body's own float-cancellation noise, which can bias the estimate invisibly to every
  local check — so slow-tail products like `\prod(i=1..) (1 + 1/i^2)` stay slow (~1e-6
  grade) rather than risk a misleading partial; the two heavyweight tests carry the
  `slow` pytest mark so the default suite stays fast.
- **`\lim(x=a)`** coerces its anchor to float, probes at `a ± h` with `h` halving from
  ~0.8% of `max(|a|, 1)`, and never evaluates at `a` itself — a step that would round back
  onto the anchor ends the side first. Each side stops on the same plateau test; sides
  further apart than *twice* the (relatively scaled) tolerance report `` limit does not
  exist `` (each side legitimately plateaus up to one tolerance-radius away, so two
  matching estimates may sit
  2× apart).

Known sharp edges (not bugs): series whose terms change sign irregularly have no
boundable tail shape, so they keep the plateau's best effort — near zero that stays
absolute-floored rather than relative (a strictly alternating run provably cannot sum
to exactly zero, so exact-zero limits outside the recognized shapes remain unsupported);
cancellation-prone spellings of removable singularities lose float precision as steps
shrink and usually fail to stabilize. Richardson extrapolation for `\lim` probes would
tighten the remaining slow cases if it ever matters.

## Float semantics

A float value arises only from a float *spelling* — the trailing-dot marker
(`1.` is the float 1.0) or an exponent form (`5e-1`, `1.5e3`) — from a
float-argument call, or from an IEEE non-finite value. A plain decimal
(`0.5`) is an exact rational; the float spellings exist so the inexact tier
stays reachable and visually marked.

CPython floats deviate from MPFR in three places; the seam pins each deliberately rather
than inheriting the Python default:

| Situation | MPFR/rug behavior | Python default | Seam behavior |
|---|---|---|---|
| `x / ±0.0` | signed infinity (`NaN` only for `0/0`) | raises `ZeroDivisionError` | signed infinity / `NaN` |
| float power overflow | unbounded exponent range | raises `OverflowError` | saturates to signed infinity |
| negative base, fractional exponent | `NaN` | returns a `complex` | `NaN` (the exact tiers instead take the odd-root real branch or the complex principal) |

## Non-finite values

The float tier carries IEEE non-finite values under the pinned semantics above:
`0./0.` → `NaN`, `1./0.` → signed `Inf`, float overflow saturates. `\inf` and
`\nan` name them as protected prelude constants (`-\inf` is unary minus on `\inf`).
They are ordinary float values — they bind, propagate through arithmetic, and are
rejected anywhere a finite number is required:

- Assign-or-check `=` is IEEE-strict: NaN never equals itself, so `x = \nan` always
  prints `false` even when `x` is NaN (matching MPFR/rug). Comparisons are all
  `false` on NaN, also per IEEE. There is no direct NaN test today.
- Conditions must be booleans — no numeric truthiness. `\nan ? 1 : 2` is a typed
  error exactly like `0 ? 1 : 2` (docs/grammar.md, `## Conditionals`).
- Range bounds must be finite and real: `1..\inf` and `\inf..3` are typed errors —
  `a..` is the language's infinite range form — and a complex bound is a typed
  "range bounds must be real numbers" error (complex values are not ordered, so a
  range over them cannot exist). A non-finite endpoint in the finite-range loop
  would iterate forever, or exact-accumulate rationals that never converge.
- The convergence riders reject non-finite partials (`\sum`) and anchors (`\lim`),
  as before.

## Display

Exact rationals display as `a/b` (`1/3` prints `1/3`, not `0.333...`) — the collapse step
above means `nshow` only ever sees a genuinely non-integer rational there. Gaussian
rationals print whole, both sides, with the imaginary part first when the real part
vanishes (`2+3i`, `2-3i`, `3i`, `-3i`, `i`, `-i`, `1/2-1/3i`) — a vanishing imaginary
part is the real itself, never `2+0i`. Decimal display
is reserved for values that are already inexact or truncated: showing an *exact* rational
through decimal machinery would be a category error — `1/3` never leaves the rational
tier, per the tower's own "stay at the lowest tier that remains exact" rule.

Symbolic and algebraic values print as **15 significant digits, expanded
positionally, plus a trailing ellipsis** (`π` is `3.14159265358979...`, `√2` is
`1.4142135623731...`, `-π` is `-3.14159265358979...`) — the DESIGN display
examples verbatim. A complex value prints each side under the same truncation
(`√2·i` is `1.4142135623731...i`, `1 + √2·i` is
`1+1.4142135623731...i`). RRA values print the same way at the session precision
(default 15: `π + 1` is `4.14159265358979...`; `\prec(5)` makes it
`4.1416...`), except the digits are proven stable first: successive
`approximate` observations at tightening tolerances must agree to the full
target, otherwise the longest agreed prefix prints (both sides tightened as a
pair for a complex value). The value is exact; the digits are a truncation,
and the ellipsis says so.

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
| `Symbolic`/`Algebraic`/`RRA`/`Gaussian` (an ad value passed through Python) | passes through |
| a sympy expression (`\py("sympy.sqrt")(2)`) | recognized closed forms convert through the symbolic tier's gate (`sympy.sqrt(2)` arrives as `√2`), algebraic values through the algebraic tier's (`sympy.cbrt(2)` arrives exact), every other finite number through the RRA tier's (`sympy.pi + 1` arrives exact); sympy rationals convert exactly via the row above; anything else rejected |
| any other `numbers.Real` (incl. numpy floats) | widened to `float` |
| `str` | passes through — a full ad value: bindable, displays quoted and round-trippable, concatenates with `+` (`"data" + ".csv"`); every other arithmetic operator rejects it ("strings are not numbers") |
| `complex` | exact `Gaussian` — both components read through their shortest round-trip decimal (`complex(0.5, 0.25)` is `1/2+1/4i`) and collapse through `make` (a vanishing imaginary part returns the real); non-finite components are rejected |
| anything else (list, dict, ndarray, ...) | rejected — names the type, never truncates silently |

A callee raising maps to a spanned error at the call (`sqrt: ValueError: math domain
error`), keeping the REPL alive like every other typed failure. Callables themselves are
bindable values (`s = \py("math.sqrt")` displays `<py math.sqrt>`); arithmetic on one is a
typed "operands must be numbers" failure at the operator's span.

## What later phases add here

The symbolic closed-form tier is in (above), as is the algebraic tier, as is
the RRA fallback — each becomes a new case in this module's dispatch the same
way, and the compiler/driver layers above are unaffected by each addition,
which is the entire point of the seam. The exact complex tower is in too
(above): the `Gaussian` tier, complex admission through every gate, the
odd-root split, and the `i`/`\i`/`\complex`/`\re`/`\im` prelude surface.
Iterative display tightening with the `\prec`
precision setting is in (above), as is Richardson–Fitch equality for any
RRA-involved pair and minimal-polynomial fallback equality for the algebraic
tier — both build on the exact tiers' canonical forms, and statement-level
`=` inherits them.
