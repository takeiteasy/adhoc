"""The numeric seam plus the statement machinery the lowered code calls into.

Mirrors `num.rs` one-to-one (`nadd`/`nsub`/`nmul`/`ndiv`/`npow`/`nneg`/`neq`/`nshow`).
Values map onto Python natives — Int→`int`, Rat→`fractions.Fraction`, Float→`float`,
Gaussian→`adhoc/gauss.py`'s `Gaussian` (exact complex with rational components),
Symbol→`adhoc/symbolic.py`'s `Symbolic` (a rational coefficient times one recognized
closed-form atom, backed by sympy), Algebraic→`adhoc/algebraic.py`'s `Algebraic` (an
algebraic number with no symbolic closed form, backed by sympy) — and arithmetic
stays at the lowest tier that remains exact:

1. `int` — arbitrary precision natively.
2. `Fraction` — arbitrary precision rational; auto-normalized, and collapsed back to
   `int` whenever its denominator is 1, or display would print `"1/1"`-style values.
3. `Gaussian` — exact complex with rational components (`2+3i`); a vanishing
   imaginary part collapses back to `int`/`Fraction`, so display never prints
   `"2+0i"`-style values (adhoc/gauss.py, docs/numerics.md).
4. `Symbolic` — closed forms (`√2`, `π`, `e²`, `ln(2)`, `sin(π/7)`, `√2·i`,
   `π·i`, ...): recognized coefficient×atom shapes, real or pure-imaginary,
   stay exact (`√2·√2` collapses back to the integer `2`); an algebraic result
   with no recognized form falls to the algebraic tier, a transcendental one
   to the RRA tier (adhoc/symbolic.py, adhoc/algebraic.py, docs/numerics.md).
5. `Algebraic` — algebraic numbers beyond the single-term shape (`2^(1/3)`,
   `2^(1/4)`, `√2 + 2^(1/3)`, `1 + √2·i`, ...): tried after the symbolic tier,
   exact with decidable equality (structural fast path plus
   minimal-polynomial fallback, complex differences included); anything not
   algebraic falls to the RRA tier
   (adhoc/algebraic.py, adhoc/rra.py, docs/numerics.md).
6. `RRA` — every other finite number, real or complex (`π + 1`, `π·√2`, `1/π`,
   `2^√2`, `sin(1)`, `1 + π·i`, ...): stored as the canonical sympy expression
   and approximated on demand as a `tolerance -> rational` function; equality
   for any RRA-involved pair is the Richardson–Fitch heuristic over those
   approximations — over the modulus when the difference is complex
   (adhoc/rra.py).
7. `float` — the explicitly-inexact tier: a float literal (trailing-dot `1.`
   or exponent `5e-1` spelling), a float-argument call, or an IEEE non-finite
   value. Any float operand demotes the result to float (the fast path);
   exact tiers never produce it.
8. complex float — Python `complex`, from a float meeting a complex value: `1. + i`,
   `2.∠1`, `\\sqrt(-2.)`. The imaginary part is never zero; a zero part collapses to
   `float`, mirroring the Gaussian invariant.

The `Engine` object is the seam's other half: every operation in generated code routes
through it carrying a span id, which is what keeps runtime-error spans narrow (a
sub-expression's failure points at the sub-expression, matching interp.rs's narrowing).
Name-bearing operations also carry canonical names for lookup and optional source
spellings for diagnostics and declaration echoes. Statement-level bind-or-check lives
here too, since `=` never lowers to Python assignment.


## Convergence

Approximate iteration has exactly one mechanism (docs/numerics.md): drive observations
until successive ones differ by at most `CONVERGENCE_TOLERANCE` (relatively scaled for
large magnitudes), otherwise error at the
cap (`MAX_TERMS` for fold terms, `MAX_PROBES` for `\\lim` probes) rather than return a
possibly-misleading partial result. Two features ride it: `\\sum`/`\\prod` over a lazy
infinite range (limit of partial sums/products) and `\\lim(x=a)` (two-sided shrinking-step
probing that never evaluates at `a`). Infinite sums get one earlier-only exit on top:
a confirmed tail estimate for monotone-decay and alternating shapes
(`_FoldTailEstimator`); products keep the plateau. Both operate in the float tier — exact tiers would
either stall plateau detection behind exponentially-growing rationals or make the
tolerance meaningless — while finite folds accumulate exactly like any other expression.

## Strings and the `\\py` boundary

Strings are ad values (docs/grammar.md): they bind, display, concatenate with `+`, and
compare equal only to other strings. The conversion matrix (`_to_ad`) is deliberately
small:

- bool → int at the Python boundary (true becomes 1); internal prelude and user-function
  results preserve booleans. int/float/Fraction pass through, `numbers.Rational` collapses
  to Fraction/int, `Gaussian`/`Symbolic`/`Algebraic`/`RRA` pass through, recognized sympy
  expressions convert through the symbolic tier's gate then the algebraic tier's then the
  RRA tier's,
  other `numbers.Real` widens to float,
  Decimal converts exactly via Fraction.
- `complex` converts to a complex float (`complex(0.5, 0.25)` is `0.5+0.25i`); a
  vanishing imaginary part returns the float real.
- `str` passes through as the value it already is — printable by `out`, bindable,
  concatenable; rejected by every other arithmetic operator.
- None, and everything else (lists, dicts, ...) are span-pointed rejections —
  no silent truncation.

`Engine.py` resolves a dotted path like `math.sqrt` (longest importable module prefix,
then attributes) and requires the result to be callable. This is a full-trust escape
hatch by design: a script that can call `\\py` can do anything Python can.

## Modules and imports

Two statement-level forms, two semantics (a module value and dotted attribute access do
not exist in the grammar — identifiers are one character):

- `\\import("lib")` reads an ad source file, evaluates it once per session in a fresh
  root environment, and binds its top-level names into the importing environment (all
  of them, or only the members after `:`). Resolution searches the importing file's
  directory first, then the working directory. The session's module registry (shared by
  every engine in a session) caches each module by absolute path, so re-imports re-copy
  cached bindings instead of re-evaluating; a file currently being evaluated is a
  circular-import error. Imported functions keep the module's environment as their
  closure — their reads of module globals stay live — while the copied values are
  snapshots. Bindings land as fresh ordinary bindings: a protected or already-bound
  name (identical cached value excepted) is a typed error.
- `\\pyimport("math": \\sqrt, \\tau)` resolves a Python module and binds the named
  members. Member selection is mandatory. Callables bind as callables (the `\\py`
  rule); every other member converts through the interop matrix or fails at the
  import's span. The usual binding rules apply: a protected or already-bound name is a
  typed error.

## The prelude

A built-in scope present in every session (`PRELUDE` below): symbolic constants
(`\\pi`, `e` — exact symbolic reals, displaying with a trailing ellipsis), the
imaginary unit (`i` and `\\i` — one prelude key, two spellings, an exact
`Gaussian(0, 1)` displaying as `i`), the non-finite floats (`\\inf`, `\\nan`),
booleans (`\\true`, `\\false`), and the function builtins (`\\sin`, `\\cos`,
`\\tan`, `\\ln`, `\\sqrt`, `\\isnan`, `\\isinf`, `\\isfinite`, plus `\\complex`,
`\\re`, `\\im`) — seam-native
`PreludeFn` callables that replaced the original float-tier `math.*` aliases in
place: exact arguments go through the symbolic tier (`\\sqrt(2)` stays `√2`,
`\\sqrt(-2)` is `√2·i`, `\\ln(-1)` is `π·i`), algebraic `\\sqrt` arguments
through the algebraic tier (`\\sqrt(2^(1/3))` is `2^(1/6)`), anything finite
the lower tiers cannot hold through the RRA tier (`\\sin(1)` stays exact),
everything else falls to the `math.*` float tier (`\\sqrt(2.)`).
`\\complex(re, im)` builds a complex value from two real components,
`\\re`/`\\im` project the sides. `\\isnan(x)`, `\\isinf(x)`, and `\\isfinite(x)`
test the float tier's non-finite states; exact-tier values are finite, so the
last predicate returns true and the first two return false. `\\prec(n)` sets the
RRA display precision (significant digits, default 15) as a session-wide setting
and returns the new value.
Unicode spellings of prelude names (`π`, `Σ`, `Π`) are not separate keys: the parser's
alias map normalizes them to the canonical `\\`-name before evaluation, so `π` and
`\\pi` are one name, not two (docs/grammar.md, `## Name aliases`); `i` and `\\i`
are likewise one key reached as a `Var` and as a `BackslashRef`. `√` is not a name
at all but the prefix-operator spelling of `\\sqrt(...)`. Prelude names
are permanently protected — they can never be rebound or shadowed, so a parameter,
local, or binder named like a prelude entry is a redefinition error — with one
exception: `i` may be bound anywhere, shadowing the unit in that scope (the collision rule — the same clash as any other identifier, handled the same
way). Both spellings resolve through the one key, so a shadow covers both: inside
an `i`-binder body the unit is spelled `\\complex(0, 1)`.

## Bindings

One rule everywhere (`Engine.assign`): `x = e` binds a fresh name into the current
frame, or compares by value against a name already bound in that frame (echoing
`true`/`false`; `1 = 1.` is true — the tower, not the type). `\\let x = e` uses the
same binding path but rejects an existing current-frame name. Reads walk the frame
chain, binds and compares stay frame-local, and no operation ever rebinds an existing
binding. Function definitions (`Engine.define`) are fresh-only declarations: a
protected or already-visible name is an error. The one shadowable prelude name is `i`
(see above).

## Pinned divergences from the rug/MPFR backing (docs/numerics.md)

- Float division by ±0.0 yields signed infinity (NaN only for 0/0) — MPFR semantics;
  CPython's `/` would raise `ZeroDivisionError`.
- Float exponentiation overflow saturates to signed infinity — MPFR has unbounded
  exponent range; CPython raises `OverflowError`.
- `x % 0.0` yields NaN on the float tier, where CPython raises `ZeroDivisionError`.
- `\\round(x, n)` of a float rounds its shortest-repr decimal half away from zero
  (`2.675` gives `2.68`), where CPython's `round` works on the binary value (`2.67`).
- Negative base with a fractional exponent takes the real branch for an exact
  odd-denominator exponent (`(-8.)^(1/3)` is `-2.0`) and the complex principal otherwise
  (`(-2.)^(1/2)` is `1.4142135623730951i`), like the exact tiers.
- A complex float `÷ 0` gives signed infinity or NaN per component, and complex
  overflow saturates per component.
- Display never uses scientific notation: the shortest-round-trip `repr` is expanded
  positionally, matching `f64`'s `Display` (`10000000000000000.0`, `0.0000001`);
  symbolic and algebraic values show 15 significant digits plus a trailing
  ellipsis (`π` is `3.14159265358979...`); RRA values show the session
  precision's significant digits (default 15, tunable via `\\prec`) plus a
  trailing ellipsis, tightened until successive approximations agree. Gaussian
  rationals print whole (`2+3i`, `1/2-1/3i`); complex tier values print each
  side truncated (`√2·i` is `1.4142135623731...i`).
"""

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import functools
import heapq
import importlib
from itertools import count, islice
import cmath
import math
import numbers
import os
import re
import sys
import sympy
import types
from typing import Any, Callable, NoReturn

from . import algebraic, eigen, gauss, linalg, matrix_numeric, rra, symbolic
from . import tensor as tn
from .gauss import Gaussian, make as _make_gaussian
from .gauss import show as _show_gaussian
from .span import Span
from .graph import (GraphValue, DEFAULT_TOLERANCE, DEFAULT_MAX_POINTS, INITIAL_POINTS,
                    sample as sample_graph)
from .solution_set import SymbolicSetValue
from .expression import ExpressionValue, show_quote
from .syntax import OP_SYMBOLS, Seq, is_short_name
from .algebraic import Algebraic
from .rra import RRA
from .symbolic import DomainError, Symbolic, Unrepresentable
from . import units
from .units import Quantity, UnitValue
from .tensor import ArrayValue, SetValue, TensorError, TensorValue

AdValue = (int | Fraction | float | complex | bool | str | Gaussian | Symbolic | Algebraic | RRA
           | ExpressionValue | TensorValue | ArrayValue | SetValue | SymbolicSetValue | GraphValue | Quantity | UnitValue)

DIVISION_BY_ZERO = "division by zero"
STRINGS_NOT_NUMBERS = "strings are not numbers"
NOT_A_NUMBER = "operands must be numbers"

DEFAULT_FLOAT_PRECISION_BITS = 53

# Convergence knobs — the one approximate-iteration mechanism shared by infinite-range
# Σ/Π folds and `\lim` (see module docstring and docs/numerics.md).
CONVERGENCE_TOLERANCE = 1e-12
EXACT_CONVERGENCE_TOLERANCE = Fraction(1, 10**12)
MAX_TERMS = 2_000_000
MAX_PROBES = 200
DIFF_TOLERANCE = 1e-9  # Ridders error estimate for `\\diff` and `f'`, relatively scaled
DIFF2_TOLERANCE = 1e-6  # the same for `f''`: second differences amplify rounding noise
DIFF_HIGHER_TOLERANCE = 1e-3
MAX_DIFF_POINTS = 32
MAX_DIFF_SAMPLES = 2000
MAX_INTERVALS = 2000  # adaptive quadrature subintervals for `\\int`

FOLD_LABELS = {"add": "\\sum", "mul": "\\prod", "and": "\\forall", "or": "\\exists"}

_NUMERIC_TYPES = (int, float, complex, Fraction, Gaussian, Symbolic, Algebraic, RRA, Quantity, UnitValue)

#: The one shadowable prelude name: `i` may be bound at any binding
#: site, shadowing the imaginary unit in that scope — the collision between the
#: unit literal and the conventional loop-binder variable, handled like any
#: other identifier clash.
SHADOWABLE_PRELUDE = frozenset({"i"})
RESERVED_NAMES = frozenset({"graph", "infix", "let", "expr", "eval", "contract", "times", "otimes", "arr", "cup", "cap", "setminus",
                           "in", "subseteq", "circ", "mod", "angle", "and", "or", "not", "implies",
                           "iff", "neq", "approx", "notin", "subset",
                           "supseteq", "supset", "per", "equiv"})


_CALL_ENGINE = ContextVar("adhoc_call_engine", default=None)


class PreludeFn:
    """A seam-native prelude builtin (`\\sqrt`, `\\sin`, ...): the symbolic tier's
    in-place replacement for the original float-tier `math.*` aliases. Displays
    like a user-defined function; protected like every prelude name."""

    __slots__ = ("name", "fn", "__name__")

    def __init__(self, name: str, fn: Callable):
        self.name = name
        self.fn = fn
        # app()'s error prefix names the builtin, not its class.
        self.__name__ = name

    def __call__(self, *args, **kwargs):
        if any(isinstance(v, Quantity | UnitValue) for v in args):
            if self.name == "sqrt" and len(args) == 1:
                return npow(args[0], Fraction(1, 2))
            if self.name == "root" and len(args) == 2:
                return self.fn(args[0], units.dimensionless(args[1], "root"), **kwargs)
            if self.name in {"abs", "conj", "re", "im", "floor", "ceil", "trunc", "round"}:
                magnitude, dims = units.parts(args[0])
                rest = [units.dimensionless(v, self.name) for v in args[1:]]
                return units.attach(self.fn(magnitude, *rest, **kwargs), dims)
            if self.name in {"sign", "arg", "isfinite", "isinf", "isnan"}:
                return self.fn(*(units.parts(v)[0] for v in args), **kwargs)
            if self.name in {"atan2", "complex"} and len(args) == 2:
                a, b, dims = units.matching(*args)
                result = self.fn(a, b, **kwargs)
                return units.attach(result, dims) if self.name == "complex" else result
            if self.name not in {"convert", "magnitude", "unit", "norm", "det", "inv", "tr",
                                 "rank", "rref", "linsolve", "kron", "outer", "cross", "diag",
                                 "stack", "concat", "reshape", "polar", "tex", "min", "max",
                                 "mean", "median", "stdev", "sstdev", "root", "congruent"}:
                args = tuple(units.dimensionless(v, self.name) for v in args)
        return self.fn(*args, **kwargs)


_CMATH_FNS: dict[str, Callable[[complex], complex]] = {
    "sin": cmath.sin, "cos": cmath.cos, "tan": cmath.tan, "asin": cmath.asin,
    "acos": cmath.acos, "atan": cmath.atan, "ln": cmath.log, "sqrt": cmath.sqrt,
    "exp": cmath.exp, "sinh": cmath.sinh, "cosh": cmath.cosh, "tanh": cmath.tanh,
    "asinh": cmath.asinh, "acosh": cmath.acosh, "atanh": cmath.atanh,
}


def _mpmath_fn(name: str) -> Callable[[complex], complex]:
    import mpmath
    return lambda z: complex(getattr(mpmath, name)(z))


def _complex_fn(name: str, z: complex) -> AdValue:
    """A prelude function of a complex float, through `cmath` (`\\gamma` and `\\erf`
    through `mpmath`)."""
    fn = _CMATH_FNS.get(name) or (_mpmath_fn(name) if name in ("gamma", "erf") else None)
    if fn is None:
        raise NumError(f"\\{name} does not take complex values")
    try:
        return _inexact(fn(z))
    except (ValueError, OverflowError, ZeroDivisionError) as e:
        raise NumericDomainError(f"\\{name}: {e}") from e


def _float_fn(name: str, float_fn: Callable, x: float) -> AdValue:
    """A prelude function of a real float: `math.*`, except a domain error whose complex
    principal value exists (`\\sqrt(-2.)`, `\\asin(2.)`) gives that value."""
    try:
        return float_fn(x)
    except ValueError as error:
        if name in _CMATH_FNS:
            try:
                return _inexact(_CMATH_FNS[name](x))
            except ValueError:
                pass
        raise NumericDomainError(f"\\{name}: ValueError: {error}") from error
    except (OverflowError, ZeroDivisionError) as error:
        raise NumericDomainError(f"\\{name}: {type(error).__name__}: {error}") from error


def _float_fall(name: str, float_fn: Callable, v: AdValue) -> AdValue:
    """The inexact fallback for a prelude argument the exact tiers cannot hold."""
    if _is_complex(v):
        return _complex_fn(name, _to_complex(v))
    return _float_fn(name, float_fn, _to_float(v))


def _prelude_fn(name: str, float_fn: Callable) -> PreludeFn:
    """Build one prelude function builtin: exact/symbolic arguments go through the
    symbolic tier (`\\sqrt(2)` stays `√2`, `\\sqrt(-2)` is `√2·i`, `\\sin(π/3)` is
    `√3/2`, `\\ln(2)` stays exact, `\\ln(-1)` is `π·i`), algebraic `\\sqrt`
    arguments through the algebraic tier (`\\sqrt(2^(1/3))` is `2^(1/6)`),
    anything finite the lower tiers cannot hold through the RRA tier (`\\sin(1)`
    stays exact, complex results included), falling to the `math.*` float tier
    only when the value is not an established real. Float arguments stay
    on the inexact tiers: `math.*` with the complex principal value where a
    domain error has one (`\\sqrt(-2.)`), `cmath.*` for a complex float.
    Exact-tier domain failures (`\\ln(0)`, `\\tan(π/2)`) are typed NumErrors at the
    call's span; float-tier domain failures retain that category and span."""
    def call(v: AdValue) -> AdValue:
        _reject_non_numeric(v)
        if isinstance(v, float):
            return _float_fn(name, float_fn, v)
        if isinstance(v, complex):
            return _complex_fn(name, v)
        if isinstance(v, RRA):
            # An RRA argument is already beyond the lower tiers; the call stays
            # finite — real or complex — so the RRA tier holds it.
            try:
                return rra.apply(name, v)
            except rra.DomainError as e:
                raise NumericDomainError(e.args[0])
            except rra.Unrepresentable:
                return _float_fall(name, float_fn, v)
        if isinstance(v, Algebraic):
            # Only `sqrt` preserves algebraicity (`sin`/`cos`/`tan`/`ln` of a
            # nonzero algebraic are transcendental), so only it routes through
            # the algebraic gate — everything else goes to the RRA tier, which
            # holds every finite number, before the float tier.
            if name != "sqrt":
                try:
                    return rra.apply(name, v)
                except rra.DomainError as e:
                    raise NumericDomainError(e.args[0])
                except rra.Unrepresentable:
                    return _float_fall(name, float_fn, v)
            try:
                return algebraic.apply(name, v)
            except algebraic.Unrepresentable:
                pass
            except algebraic.DomainError as e:
                raise NumericDomainError(e.args[0])
        try:
            return symbolic.apply(name, v)
        except Unrepresentable:
            pass
        except DomainError as e:
            raise NumericDomainError(e.args[0])
        if name == "sqrt":
            # `sqrt` preserves algebraicity for symbolic arguments too
            # (`\sqrt(√2)` is `2^(1/4)`), so it routes through the algebraic
            # gate before the RRA tier — every other builtin of an exact
            # argument with no closed form is transcendental.
            try:
                return algebraic.apply(name, v)
            except algebraic.Unrepresentable:
                pass
            except algebraic.DomainError as e:
                raise NumericDomainError(e.args[0])
        try:
            return rra.apply(name, v)
        except rra.Unrepresentable:
            return _float_fall(name, float_fn, v)
        except rra.DomainError as e:
            raise NumericDomainError(e.args[0])
    return PreludeFn(name, call)


def _predicate_fn(name: str, float_fn: Callable[[float], bool], exact: bool) -> PreludeFn:
    def call(v: AdValue) -> bool:
        _reject_non_numeric(v)
        if isinstance(v, float):
            return float_fn(v)
        if isinstance(v, complex):
            return getattr(cmath, name)(v)
        return exact
    return PreludeFn(name, call)


def _prec_call(v: AdValue) -> AdValue:
    """The `\\prec(n)` display-precision setting: set the RRA tier's session
    precision (significant digits) and return the new value. A session-wide
    setting with a side effect, so the single `nshow` path serves REPL and
    script mode identically. Exact integers 1..1000 only (bools rejected like
    every other numeric operand); anything else is the seam's typed NumError
    at the call's span."""
    if isinstance(v, bool) or not isinstance(v, int):
        raise NumError("\\prec takes an integer 1..1000")
    try:
        return rra.set_precision(v)
    except rra.DomainError as e:
        raise NumericDomainError(e.args[0])


def _complex_call(*args: AdValue) -> AdValue:
    """The `\\complex(re, im)` constructor: a complex value from two real
    components, exact unless a component is a float (`\\complex(0.5, 0.25)` is the
    complex float `0.5+0.25i`); complex components do not nest (a typed error) and
    a vanishing imaginary part collapses to the real."""
    if len(args) != 2:
        raise NumError("\\complex takes two components: \\complex(re, im)")
    re_v, im_v = args
    _reject_non_numeric(re_v, im_v)
    if _is_complex(re_v) or _is_complex(im_v):
        raise NumError("\\complex takes real components")
    if isinstance(re_v, float) or isinstance(im_v, float):
        return _inexact(complex(_to_float(re_v), _to_float(im_v)))
    return _make_gaussian(re_v, im_v)


def _project(v: AdValue, imag: bool) -> AdValue:
    """The `\\re`/`\\im` projection: the real or imaginary side of a value.
    A float is real (the side is the float itself, or 0.0 — the tier stays);
    a complex float's sides are floats; a Gaussian's sides are its components; any tier value projects through
    sympy's `as_real_imag` with each side re-classified through the `\\py`
    gates (`\\im(π·i)` is the symbolic `π`, `\\re(sin(1)+cos(1)·i)` stays
    RRA)."""
    _reject_non_numeric(v)
    if isinstance(v, Gaussian):
        return v.im if imag else v.re
    if isinstance(v, float):
        return 0.0 if imag else v
    if isinstance(v, complex):
        return v.imag if imag else v.real
    if isinstance(v, Symbolic | Algebraic | RRA):
        if not _is_complex(v):
            return 0 if imag else v
        re, im = v.expr.as_real_imag()
        return _sympy_to_ad(im if imag else re, type(v).__name__)
    return 0 if imag else v  # int/Fraction are real


def _re_call(v: AdValue) -> AdValue:
    return _project(v, imag=False)


def _im_call(v: AdValue) -> AdValue:
    return _project(v, imag=True)


def _body_call(value: Any) -> ExpressionValue:
    if not isinstance(value, AdFunction):
        raise NumError("\\body needs a user-defined function")
    body = value.body
    node = body.node
    if not isinstance(node, Seq):
        node = Seq(statements=(node,), span=node.span)
    return ExpressionValue(node, body.source, statement_body=True)


def _reduce_call(value: Any) -> ExpressionValue:
    if not isinstance(value, ExpressionValue):
        raise NumError("\\reduce needs an expression value")
    from .reduction import ReduceError, reduce_expression

    try:
        return reduce_expression(value)
    except ReduceError as error:
        raise NumError(str(error)) from error


def _rewrite_call(name: str, operation: Callable[[sympy.Expr], sympy.Expr]) -> PreludeFn:
    def call(value: Any, *, dimensions=None) -> ExpressionValue:
        from . import rewrite
        try:
            return rewrite.rewrite(value, operation, dimensions=dimensions)
        except rewrite.RewriteError as error:
            raise NumError(f"\\{name} {error}") from None
    return PreludeFn(name, call)


def _solve_call(value: Any, unknown: Any = None, *,
                domain: str = "complex", dimensions=None) -> SetValue | SymbolicSetValue:
    from . import rewrite
    try:
        return rewrite.solve(value, unknown, domain=domain, dimensions=dimensions)
    except rewrite.RewriteError as error:
        raise NumError(f"\\solve {error}") from None


def _deriv_call(value: Any, unknown: Any = None, order: Any = 1, *, dimensions=None) -> ExpressionValue | ArrayValue:
    from . import rewrite
    try:
        return rewrite.derivative(value, unknown, order, dimensions=dimensions)
    except rewrite.RewriteError as error:
        raise NumError(f"\\deriv {error}") from None


def _grad_call(value: Any, unknown: Any = None, *, dimensions=None) -> ArrayValue:
    from . import rewrite
    try:
        return rewrite.gradient(value, unknown, dimensions=dimensions)
    except rewrite.RewriteError as error:
        raise NumError(f"\\grad {error}") from None


def _matrix_derivative_call(name):
    def call(value, unknown=None, *, dimensions=None):
        from . import rewrite
        try:
            return getattr(rewrite, name)(value, unknown, dimensions=dimensions)
        except rewrite.RewriteError as error:
            raise NumError(f"\\{name} {error}") from None
    return PreludeFn(name, call)


def _tensor_call(value):
    if not isinstance(value, ArrayValue):
        raise NumError("\\tensor needs an array")

    def build(part):
        if not isinstance(part, ArrayValue):
            _reject_non_numeric(part)
            return part
        if not part.items:
            raise NumError("\\tensor cannot contain an empty axis")
        return _linalg(tn.stack, [build(item) for item in part.items])

    result = build(value)
    units.dimensions(result)
    return result


def _transpose_call(value: Any) -> AdValue:
    return ntranspose(value)


def _tex_call(value: Any) -> str:
    from .tex import TexError, value_tex
    try:
        engine = _CALL_ENGINE.get()
        return value_tex(value, nshow, lookup=engine._lookup if engine is not None else None)
    except TexError as e:
        raise NumError(e.args[0]) from None


def _len_call(value: Any) -> int:
    if isinstance(value, SymbolicSetValue):
        raise NumError("symbolic sets do not support length")
    if isinstance(value, TensorValue):
        return value.shape[0]
    if isinstance(value, ArrayValue | SetValue):
        return len(value.items)
    raise NumError("\\len needs a collection")


def _shape_call(value: Any) -> TensorValue:
    if not isinstance(value, TensorValue):
        raise NumError("\\shape needs a tensor")
    return TensorValue((value.order,), value.shape)


def _root_call(*args: AdValue) -> AdValue:
    if len(args) != 2:
        raise NumError("\\root takes a value and a root index: \\root(x, n)")
    x, index = args
    _reject_non_numeric(x)
    n = _integer_exponent(index) if not isinstance(index, bool) else None
    if n is None or n < 1:
        raise NumError(f"\\root needs a positive exact integer index, got {nshow(index)}")
    return npow(x, Fraction(1, n))


PRELUDE: dict[str, Any] = {
    "pi": symbolic.PI,
    "e": symbolic.E,
    "i": _make_gaussian(0, 1),
    "inf": math.inf,
    "nan": math.nan,
    "true": True,
    "false": False,
    "sin": _prelude_fn("sin", math.sin),
    "cos": _prelude_fn("cos", math.cos),
    "tan": _prelude_fn("tan", math.tan),
    "asin": _prelude_fn("asin", math.asin),
    "acos": _prelude_fn("acos", math.acos),
    "atan": _prelude_fn("atan", math.atan),
    "ln": _prelude_fn("ln", math.log),
    "sqrt": _prelude_fn("sqrt", math.sqrt),
    "root": PreludeFn("root", _root_call),
    "emptyset": SetValue(()),
    "isnan": _predicate_fn("isnan", math.isnan, False),
    "isinf": _predicate_fn("isinf", math.isinf, False),
    "isfinite": _predicate_fn("isfinite", math.isfinite, True),
    "complex": PreludeFn("complex", _complex_call),
    "re": PreludeFn("re", _re_call),
    "im": PreludeFn("im", _im_call),
    "prec": PreludeFn("prec", _prec_call),
    "body": PreludeFn("body", _body_call),
    "reduce": PreludeFn("reduce", _reduce_call),
    "transpose": PreludeFn("transpose", _transpose_call),
    "len": PreludeFn("len", _len_call),
    "tex": PreludeFn("tex", _tex_call),
    "shape": PreludeFn("shape", _shape_call),
}

_PRELUDE_PROTECTED = frozenset(PRELUDE)



@dataclass(frozen=True)
class IntervalValue:
    """Non-iterable real integration bounds, preserving orientation."""

    start: AdValue
    end: AdValue


@dataclass(frozen=True)
class RangeValue:
    """A lazy arithmetic progression; `end=None` denotes an infinite range."""

    start: AdValue
    step: AdValue
    end: AdValue | None
    second: AdValue | None = None

    def __iter__(self):
        current = self.start
        if self.end is None:
            while True:
                yield current
                current = nadd(current, self.step)
        elif self.step > 0:
            while current <= self.end:
                yield current
                current = nadd(current, self.step)
        else:
            while current >= self.end:
                yield current
                current = nadd(current, self.step)


class NumError(Exception):
    """Typed numeric failure; callers attach the offending expression's span."""

    domain = False


class NumericDomainError(NumError):
    domain = True


def _is_float(v: AdValue) -> bool:
    return isinstance(v, float)


def _is_inexact(v: AdValue) -> bool:
    return isinstance(v, float | complex)


def _is_complex(v: AdValue) -> bool:
    """A decided non-real value — nonzero imaginary part at every tier. Ordering,
    range bounds, `\\lim` anchors and float widening reject these with typed errors."""
    if isinstance(v, Quantity | UnitValue):
        return _is_complex(units.parts(v)[0])
    if isinstance(v, complex | Gaussian):
        return True
    if isinstance(v, Symbolic | Algebraic):
        return v.expr.is_real is False
    if isinstance(v, RRA):
        return v.is_complex
    return False


def _to_float(v: AdValue) -> float:
    return float(v)


def _comparison_pair(a: AdValue, b: AdValue) -> tuple[AdValue, AdValue]:
    if any(isinstance(v, float) and not math.isfinite(v) for v in (a, b)):
        # Exact values are finite; zero preserves their relation to NaN and infinities.
        return (a if isinstance(a, float) else 0,
                b if isinstance(b, float) else 0)
    try:
        fa, fb = float(a), float(b)
        if math.isfinite(fa) and math.isfinite(fb):
            return fa, fb
    except OverflowError:
        pass
    # Keep overflowing exact values finite; floats become exact binary rationals.
    return (Fraction(a) if isinstance(a, float) else a,
            Fraction(b) if isinstance(b, float) else b)


def _to_complex(v: AdValue) -> complex:
    if isinstance(v, complex):
        return v
    if isinstance(v, Gaussian):
        return complex(float(v.re), float(v.im))
    if isinstance(v, Symbolic | Algebraic | RRA):
        return complex(sympy.N(v.expr))
    return complex(float(v))


def _inexact(z: complex) -> float | complex:
    """The complex-float invariant: the imaginary part is never zero."""
    return z.real if z.imag == 0 else z


def _cdiv(a: complex, b: complex) -> complex:
    if b == 0:
        return complex(_fdiv(a.real, 0.0), _fdiv(a.imag, 0.0))
    return a / b


def _cpow(a: complex, b: complex) -> complex:
    if b == 0.5:
        return cmath.sqrt(a)
    try:
        return a ** b
    except ZeroDivisionError:
        raise NumericDomainError(DIVISION_BY_ZERO) from None
    except OverflowError:
        # Saturate per component like the real float tier.
        log_r, theta = math.log(abs(a)), cmath.phase(a)
        angle = b.imag * log_r + b.real * theta
        return complex(math.copysign(math.inf, math.cos(angle)),
                       math.copysign(math.inf, math.sin(angle)))


_COMPLEX_OPS: dict[str, Callable[[complex, complex], complex]] = {
    "add": lambda a, b: a + b, "sub": lambda a, b: a - b, "mul": lambda a, b: a * b,
    "div": _cdiv, "pow": _cpow,
}


def _complex_binary(op: str, a: AdValue, b: AdValue) -> AdValue:
    """A binary operation on the complex-float tier, collapsing a zero imaginary part."""
    return _inexact(_COMPLEX_OPS[op](_to_complex(a), _to_complex(b)))


def _normalize(x: Fraction) -> int | Fraction:
    """Collapse a denominator-1 rational back to an integer."""
    if x.denominator == 1:
        return int(x)
    return x


def _reject_non_numeric(*vals: AdValue) -> None:
    """Guard the arithmetic seam against everything that is not an ad number — a
    string value (a full value, but never a numeric operand; `+` concats before this
    guard runs) or a bound callable reaching an operator. The failure must stay a
    spanned NumError, never a TypeError escaping the engine."""
    for v in vals:
        if isinstance(v, ArrayValue):
            raise NumError("arrays do not support arithmetic")
        if isinstance(v, SetValue | SymbolicSetValue):
            raise NumError("sets do not support arithmetic")
        if isinstance(v, bool):
            raise NumError("booleans are not numbers")
        if isinstance(v, str):
            raise NumError(STRINGS_NOT_NUMBERS)
        if not isinstance(v, _NUMERIC_TYPES):
            raise NumError(NOT_A_NUMBER)


def _exact_combine(op: str, a: AdValue, b: AdValue,
                   float_fallback: Callable[[], AdValue]) -> AdValue:
    """The exact tiers' binary-op shim: dispatch into symbolic.combine first,
    then algebraic.combine, then rra.combine. A symbolic coefficient×atom result
    stays symbolic; a real algebraic result with no recognized closed form
    (`2^(1/3)`, `√2 + 2^(1/3)`) stays algebraic; every other finite value —
    real or complex (`π + 1/3`, `π·√2`, `2^√2`, `1 + π·i`) — stays RRA,
    approximated on demand as a `tolerance -> rational` function (the modulus
    when complex; adhoc/rra.py). A Gaussian rational result collapses back to
    `Gaussian`/exact at the gates. Only a real value of undecided reality
    falls to the float tier, a complex one to the complex-float tier. An exact-tier domain failure (`1/0` shapes) becomes the
    seam's typed NumError (the caller attaches the span)."""
    try:
        return symbolic.combine(op, a, b)
    except Unrepresentable:
        pass
    except DomainError as e:
        raise NumericDomainError(e.args[0])
    try:
        return algebraic.combine(op, a, b)
    except algebraic.Unrepresentable:
        pass
    except algebraic.DomainError as e:
        raise NumericDomainError(e.args[0])
    try:
        return rra.combine(op, a, b)
    except rra.Unrepresentable:
        if _is_complex(a) or _is_complex(b):
            return _complex_binary(op, a, b)
        return float_fallback()
    except rra.DomainError as e:
        raise NumericDomainError(e.args[0])


def _tensor_op(f: Callable, a: AdValue, b: AdValue) -> AdValue:
    try:
        result = tn.map2(f, a, b)
        units.dimensions(result)
        return result
    except TensorError as e:
        raise NumError(e.args[0]) from e


def nadd(a: AdValue, b: AdValue) -> AdValue:
    if isinstance(a, TensorValue) or isinstance(b, TensorValue):
        return _tensor_op(nadd, a, b)
    if isinstance(a, str) and isinstance(b, str):
        return a + b  # string + string concatenates; mixed never coerces
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        return units.binary("add", a, b)
    _reject_non_numeric(a, b)
    if _is_inexact(a) or _is_inexact(b):
        if _is_complex(a) or _is_complex(b):
            return _complex_binary("add", a, b)
        return _to_float(a) + _to_float(b)
    if isinstance(a, (Symbolic, Algebraic, RRA)) or isinstance(b, (Symbolic, Algebraic, RRA)):
        return _exact_combine("add", a, b,
                                 lambda: _to_float(a) + _to_float(b))
    if isinstance(a, Gaussian) or isinstance(b, Gaussian):
        return gauss.add(a, b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) + Fraction(b))
    return a + b


def nsub(a: AdValue, b: AdValue) -> AdValue:
    if isinstance(a, TensorValue) or isinstance(b, TensorValue):
        return _tensor_op(nsub, a, b)
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        return units.binary("sub", a, b)
    _reject_non_numeric(a, b)
    if _is_inexact(a) or _is_inexact(b):
        if _is_complex(a) or _is_complex(b):
            return _complex_binary("sub", a, b)
        return _to_float(a) - _to_float(b)
    if isinstance(a, (Symbolic, Algebraic, RRA)) or isinstance(b, (Symbolic, Algebraic, RRA)):
        return _exact_combine("sub", a, b,
                                 lambda: _to_float(a) - _to_float(b))
    if isinstance(a, Gaussian) or isinstance(b, Gaussian):
        return gauss.sub(a, b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) - Fraction(b))
    return a - b


def nmul(a: AdValue, b: AdValue) -> AdValue:
    if isinstance(a, TensorValue) or isinstance(b, TensorValue):
        return _tensor_op(nmul, a, b)
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        return units.binary("mul", a, b)
    _reject_non_numeric(a, b)
    if _is_inexact(a) or _is_inexact(b):
        if _is_complex(a) or _is_complex(b):
            return _complex_binary("mul", a, b)
        return _to_float(a) * _to_float(b)
    if isinstance(a, (Symbolic, Algebraic, RRA)) or isinstance(b, (Symbolic, Algebraic, RRA)):
        return _exact_combine("mul", a, b,
                                 lambda: _to_float(a) * _to_float(b))
    if isinstance(a, Gaussian) or isinstance(b, Gaussian):
        return gauss.mul(a, b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) * Fraction(b))
    return a * b


def ndiv(a: AdValue, b: AdValue) -> AdValue:
    if isinstance(a, TensorValue) or isinstance(b, TensorValue):
        return _tensor_op(ndiv, a, b)
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        return units.binary("div", a, b)
    _reject_non_numeric(a, b)
    if _is_inexact(a) or _is_inexact(b):
        if _is_complex(a) or _is_complex(b):
            return _complex_binary("div", a, b)
        return _fdiv(_to_float(a), _to_float(b))
    if isinstance(a, (Symbolic, Algebraic, RRA)) or isinstance(b, (Symbolic, Algebraic, RRA)):
        return _exact_combine("div", a, b,
                                 lambda: _fdiv(_to_float(a), _to_float(b)))
    if isinstance(a, Gaussian) or isinstance(b, Gaussian):
        # A Gaussian divisor never vanishes (the imaginary part cannot), so the
        # zero check only fires on a bare exact 0.
        if b == 0:
            raise NumericDomainError(DIVISION_BY_ZERO)
        return gauss.div(a, b)
    divisor = Fraction(b)
    if divisor == 0:
        raise NumericDomainError(DIVISION_BY_ZERO)
    return _normalize(Fraction(a) / divisor)


def nmod(a: AdValue, b: AdValue) -> AdValue:
    """`a % b`, floored: the result takes the divisor's sign."""
    if isinstance(a, TensorValue) or isinstance(b, TensorValue):
        return _tensor_op(nmod, a, b)
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        return units.binary("mod", a, b)
    _reject_non_numeric(a, b)
    if _is_complex(a) or _is_complex(b):
        raise NumError("`%` needs real numbers")
    if _is_float(a) or _is_float(b):
        try:
            return _to_float(a) % _to_float(b)
        except ZeroDivisionError:
            return math.nan
    if isinstance(a, (int, Fraction)) and isinstance(b, (int, Fraction)):
        if b == 0:
            raise NumericDomainError(DIVISION_BY_ZERO)
        return _normalize(Fraction(a) % Fraction(b))
    quotient = ndiv(a, b)
    return nsub(a, nmul(b, _integral(quotient, "floor")))


def npolar(r: AdValue, theta: AdValue) -> AdValue:
    """`r∠θ` / `\\polar(r, θ)`: the complex number of modulus `r` and angle `θ`."""
    _reject_non_numeric(r, theta)
    if _is_complex(r) or _is_complex(theta):
        raise NumError("`∠` needs real numbers")
    side = nmul(r, PRELUDE["sin"](theta))
    return nadd(nmul(r, PRELUDE["cos"](theta)), nmul(side, PRELUDE["i"]))


def _fdiv(fa: float, fb: float) -> float:
    """Float division under MPFR semantics: division by ±0.0 yields signed infinity
    (NaN only for 0/0), where CPython's `/` would raise ZeroDivisionError."""
    try:
        return fa / fb
    except ZeroDivisionError:
        if fa == 0:
            return math.nan
        sign = math.copysign(1.0, fa) * math.copysign(1.0, fb)
        return math.copysign(math.inf, sign)


def npow(a: AdValue, b: AdValue) -> AdValue:
    if isinstance(a, TensorValue) or isinstance(b, TensorValue):
        return _tensor_op(npow, a, b)
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        return units.binary("pow", a, b)
    _reject_non_numeric(a, b)
    n = _integer_exponent(b)
    if n is not None:
        if isinstance(a, (Symbolic, Algebraic, RRA)):
            # A symbolic/algebraic/RRA base to an integer power stays exact when
            # the result has a closed form ((√2)² collapses to 2, e³ stays
            # `e³`, `2^(1/3)^3` collapses to 2); `π⁻¹` has none and falls to
            # the RRA tier.
            return _exact_combine("pow", a, n,
                                     lambda: _fpow(_to_float(a), float(n)))
        if isinstance(a, complex):
            return _complex_binary("pow", a, n)
        if isinstance(a, Gaussian):
            # `i²` is the integer -1, `(1+i)⁻³` an exact Gaussian — sympy
            # stays for tier mixing only.
            return gauss.pow_int(a, n)
        return _pow_exact_base(a, n)
    if _is_inexact(a) or _is_inexact(b):
        if _is_complex(a) or _is_complex(b):
            return _complex_binary("pow", a, b)
        return _float_pow(a, b)
    # Non-integer exponent on exact, symbolic, algebraic or RRA operands: the
    # symbolic tier recognizes closed forms (`2^(1/2)` is `√2`, `8^(1/3)`
    # collapses to `2`), the algebraic tier real algebraic roots (`2^(1/3)`
    # is `2^(1/3)`), the RRA tier every other real, and complex results rise
    # through the same gates (`(-2)^(1/2)` is `√2·i`, `(1+i)^(1/2)` is
    # algebraic complex). A negative real base takes the odd-root split first
    # (below). Only a real value of undecided reality falls to the float
    # tier.
    sign = _real_sign(a)
    if sign == -1 and isinstance(b, Fraction) and b.denominator % 2 == 1:
        # The odd-root real branch: `(-x)^(p/q)` in lowest terms with q odd
        # is `(-1)^p · x^(p/q)` — the real value the complex principal branch
        # would hide. The magnitude keeps its tier; the sign rides on top.
        magnitude = nneg(a)
        powered = _exact_combine(
            "pow", magnitude, b,
            lambda: _fpow(_to_float(magnitude), _to_float(b)))
        return nneg(powered) if b.numerator % 2 else powered
    return _exact_combine("pow", a, b,
                             lambda: _fpow(_to_float(a), _to_float(b)))


def _float_pow(a: AdValue, b: AdValue) -> AdValue:
    """Real float power. A negative base with a non-integer exponent takes the real odd
    root for an exact odd-denominator exponent (`(-8.)^(1/3)` is `-2.0`), else the
    complex principal value."""
    fa, fb = _to_float(a), _to_float(b)
    if fa < 0 and math.isfinite(fb) and fb != math.floor(fb):
        if isinstance(b, Fraction) and b.denominator % 2 == 1:
            magnitude = _fpow(-fa, fb)
            return -magnitude if b.numerator % 2 else magnitude
        return _complex_binary("pow", fa, fb)
    return _fpow(fa, fb)


def _real_sign(v: AdValue) -> int | None:
    """The sign of a real ad value — None for a complex one (and for floats,
    which never reach it: the float branch handles them first). Exact
    comparisons per tier; a gate-passing symbolic/algebraic/RRA value is
    irrational and never zero."""
    if _is_complex(v) or isinstance(v, float):
        return None
    if isinstance(v, (int, Fraction)):
        return (v > 0) - (v < 0)
    if isinstance(v, Symbolic):
        return -1 if symbolic.compare("lt", v, 0) else 1
    if isinstance(v, Algebraic):
        return -1 if algebraic.compare("lt", v, 0) else 1
    if isinstance(v, RRA):
        return -1 if rra.compare("lt", v, 0) else 1
    return None


def _integer_exponent(v: AdValue) -> int | None:
    """An exact integer value usable as an exponent, else None — decides whether an
    exact base can stay exact."""
    if isinstance(v, int):
        return v
    if isinstance(v, Fraction) and v.denominator == 1:
        return int(v)
    return None


def _pow_exact_base(a: AdValue, n: int) -> AdValue:
    if _is_float(a):
        # rug routed integer exponents on float bases through f64 as well.
        return _fpow(_to_float(a), float(n))
    base = Fraction(a)
    if n == 0:
        return 1
    if n > 0:
        return _normalize(base**n)
    # Negative integer exponent on an exact value: invert then raise. `0^-n` is the
    # same failure as `1/0` and must be reported the same way.
    if base == 0:
        raise NumericDomainError(DIVISION_BY_ZERO)
    return _normalize(Fraction(1) / base ** (-n))


def _fpow(base: float, exp: float) -> float:
    """Float power under MPFR semantics (see module divergences)."""
    if base < 0 and exp != math.floor(exp):
        return math.nan
    try:
        return base**exp
    except OverflowError:
        if base < 0 and math.isfinite(exp) and math.floor(exp) % 2 != 0:
            return -math.inf
        return math.inf
    except ZeroDivisionError:
        return math.inf  # 0.0 ** negative


def nneg(a: AdValue) -> AdValue:
    if isinstance(a, TensorValue):
        return tn.map1(nneg, a)
    if isinstance(a, Quantity | UnitValue):
        return units.unary(a, nneg)
    _reject_non_numeric(a)
    if isinstance(a, Symbolic):
        return symbolic.negate(a)  # negating a coefficient×atom form stays one
    if isinstance(a, Algebraic):
        return algebraic.negate(a)  # negating an algebraic stays one
    if isinstance(a, RRA):
        return rra.negate(a)  # negating a finite value stays one
    if isinstance(a, Gaussian):
        return gauss.neg(a)  # negating a Gaussian stays one (or collapses)
    return -a


MAX_FACTORIAL = 100_000


def _factorial_arg(a: AdValue, symbol: str) -> int:
    _reject_non_numeric(a)
    n = _integer_exponent(a)
    if n is None or n < 0:
        raise NumError(f"`{symbol}` needs an exact non-negative integer, got {nshow(a)}")
    if n > MAX_FACTORIAL:
        raise NumError(f"`{symbol}` is limited to arguments up to {MAX_FACTORIAL}")
    return n


def nfact(a: AdValue) -> AdValue:
    _reject_non_numeric(a)
    n = _integer_exponent(a)
    if n is not None or _is_complex(a):
        return math.factorial(_factorial_arg(a, "!"))
    return PRELUDE["gamma"](nadd(a, 1))


def ndfact(a: AdValue) -> AdValue:
    return math.prod(range(_factorial_arg(a, "‼"), 1, -2))


def ndot(a: AdValue, b: AdValue) -> AdValue:
    """`a @ b`: contract the last axis of `a` with the first of `b`; a scalar operand scales."""
    if isinstance(a, TensorValue) and isinstance(b, TensorValue):
        try:
            return tn.contract(nmul, nadd, a, b)
        except TensorError as e:
            raise NumError(e.args[0]) from e
    return nmul(a, b)


def ntimes(a: AdValue, b: AdValue) -> AdValue:
    """`a × b`: the cross product of two 3-vectors; a scalar operand scales."""
    if isinstance(a, TensorValue) and isinstance(b, TensorValue):
        return PRELUDE["cross"](a, b)
    return nmul(a, b)


def notimes(a: AdValue, b: AdValue) -> AdValue:
    """`a ⊗ b`: the tensor product, whose shape concatenates the operands'; a scalar operand scales."""
    if isinstance(a, TensorValue) and isinstance(b, TensorValue):
        return _linalg(linalg.outer, _SCALARS, a, b)
    return nmul(a, b)


def ntranspose(a: AdValue) -> AdValue:
    if not isinstance(a, TensorValue):
        raise NumError("transpose needs a tensor")
    return tn.transpose(a)


def _contains(items: tuple, value: AdValue) -> bool:
    return any(neq(value, item) for item in items)


def _dedup(items) -> tuple:
    # TODO: O(n²) pairwise `neq`; hash canonical exact keys for large sets (ticket https://github.com/takeiteasy/adhoc/issues/4)
    unique: list = []
    for item in items:
        if not _contains(tuple(unique), item):
            unique.append(item)
    return tuple(unique)


def neq(a: AdValue, b: AdValue) -> bool:
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        am, ad = units.parts(a)
        bm, bd = units.parts(b)
        return ad == bd and neq(am, bm)
    if isinstance(a, SymbolicSetValue) or isinstance(b, SymbolicSetValue):
        return a == b
    if isinstance(a, IntervalValue) or isinstance(b, IntervalValue):
        return (isinstance(a, IntervalValue) and isinstance(b, IntervalValue)
                and neq(a.start, b.start)
                and neq(a.end, b.end))
    if isinstance(a, SetValue) or isinstance(b, SetValue):
        return (isinstance(a, SetValue) and isinstance(b, SetValue)
                and len(a.items) == len(b.items)
                and all(_contains(b.items, item) for item in a.items))
    if isinstance(a, ArrayValue) or isinstance(b, ArrayValue):
        return (isinstance(a, ArrayValue) and isinstance(b, ArrayValue)
                and len(a.items) == len(b.items)
                and all(neq(x, y) for x, y in zip(a.items, b.items)))
    if isinstance(a, TensorValue) or isinstance(b, TensorValue):
        return (isinstance(a, TensorValue) and isinstance(b, TensorValue)
                and a.shape == b.shape
                and all(neq(x, y) for x, y in zip(a.items, b.items)))
    if isinstance(a, ExpressionValue) or isinstance(b, ExpressionValue):
        return a == b if isinstance(a, ExpressionValue) and isinstance(b, ExpressionValue) else False
    if isinstance(a, str) or isinstance(b, str):
        return a == b if isinstance(a, str) and isinstance(b, str) else False
    if not isinstance(a, _NUMERIC_TYPES) or not isinstance(b, _NUMERIC_TYPES):
        return a is b  # callables and other exotics compare by identity
    if isinstance(a, complex) or isinstance(b, complex):
        if _is_inexact(a) and _is_inexact(b):
            return a == b
        inexact = a if _is_inexact(a) else b
        if not all(math.isfinite(part) for part in (inexact.real, inexact.imag)):
            return False
        try:
            ca, cb = _to_complex(a), _to_complex(b)
        except OverflowError:
            return False
        return (all(math.isfinite(part) for part in (ca.real, ca.imag, cb.real, cb.imag))
                and ca == cb)
    if _is_float(a) or _is_float(b):
        if _is_complex(a) or _is_complex(b):
            # A float is real; a complex value's imaginary part never vanishes.
            return False
        a, b = _comparison_pair(a, b)
        if isinstance(a, float) or isinstance(b, float):
            return a == b
        return neq(a, b)
    if isinstance(a, RRA) or isinstance(b, RRA):
        # Richardson–Fitch heuristic (docs/numerics.md#comparisons): structural
        # identity first, then escalating `approximate` probes on the
        # difference (on its modulus when complex) — equal while
        # indistinguishable from zero (Schanuel's conjecture; an accepted
        # limitation, not a proof). Covers any RRA-involved pair, including
        # RRA vs exact (`sin(1)^2+cos(1)^2` equals `1` though sympy never
        # simplifies it). A float operand takes the approximate float branch
        # above.
        return rra.equal(a, b)
    if isinstance(a, Algebraic) or isinstance(b, Algebraic):
        # Exact, decided on canonical forms with a minimal-polynomial fallback
        # (`(1+√2)^2` and `3+2√2` store differently but share a minimal
        # polynomial; an algebraic never equals a rational). A float operand
        # takes the approximate float branch above.
        return algebraic.structurally_equal(a, b)
    if isinstance(a, Symbolic) or isinstance(b, Symbolic):
        # Exact, decided on the symbolic tier's canonical forms (`√4` has already
        # collapsed; `√2 = 2^(1/2)` stores identically; an atom never equals a
        # rational). A float operand takes the approximate float branch above.
        return symbolic.structurally_equal(a, b)
    if isinstance(a, Gaussian) or isinstance(b, Gaussian):
        if isinstance(a, Gaussian) and isinstance(b, Gaussian):
            return a.re == b.re and a.im == b.im
        return False  # a complex value never equals a real exact one
    return Fraction(a) == Fraction(b)


def _show_tensor(t: TensorValue, digits: int | None) -> str:
    if t.order == 1:
        return "[" + ", ".join(nshow(x, digits) for x in t.items) + "]"
    if t.order == 2:
        rows, cols = t.shape
        body = "; ".join(", ".join(nshow(t.items[r * cols + c], digits) for c in range(cols))
                         for r in range(rows))
        return f"[{body};]" if rows == 1 else f"[{body}]"
    return "[" + ", ".join(_show_tensor(part, digits) for part in tn.slices(t)) + "]"


def nshow(v: AdValue | str, digits: int | None = None) -> str:
    if isinstance(v, Quantity | UnitValue):
        return units.show(v, lambda x: nshow(x, digits))
    if isinstance(v, GraphValue):
        status = "complete" if v.complete else "incomplete: " + ", ".join(v.stopping_reasons)
        return (f"<graph {v.axis_spelling}={nshow(v.bounds[0], digits)}..{nshow(v.bounds[1], digits)}; "
                f"{v.evaluations} samples; {len(v.breaks)} gaps; {status}>")
    if isinstance(v, SymbolicSetValue):
        return v.render()
    if isinstance(v, SetValue):
        return "{" + ", ".join(nshow(x, digits) for x in v.items) + "}"
    if isinstance(v, ArrayValue):
        return "⟨" + ", ".join(nshow(x, digits) for x in v.items) + "⟩"
    if isinstance(v, TensorValue):
        return _show_tensor(v, digits)
    if isinstance(v, ExpressionValue):
        return show_quote(v.node, v.statement_body)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, AdFunction):
        if not v.name:
            return f"<λ({', '.join(v.param_spellings)})>"
        return f"<fn {v.display_name}({', '.join(v.param_spellings)})>"
    if isinstance(v, str):
        return _show_str(v)
    if isinstance(v, LazySeq):
        return f"<seq {v.text()}>"
    if isinstance(v, IntervalValue):
        return f"<interval {nshow(v.start, digits)}..{nshow(v.end, digits)}>"
    if isinstance(v, RangeValue):
        start = nshow(v.start, digits)
        middle = f",{nshow(v.second, digits)}" if v.second is not None else ""
        end = "" if v.end is None else nshow(v.end, digits)
        suffix = " (lazy, infinite)" if v.end is None else ""
        return f"<range {start}{middle}..{end}{suffix}>"
    if isinstance(v, Gaussian):
        return _show_gaussian(v)  # exact components, whole, no ellipsis
    if isinstance(v, Symbolic):
        return symbolic.show(v)  # exact value, truncated digits + ellipsis
    if isinstance(v, Algebraic):
        return algebraic.show(v)  # exact value, truncated digits + ellipsis
    if isinstance(v, RRA):
        # Exact value, tightened digits + ellipsis: an explicit `digits`
        # overrides the session precision for that call only, otherwise the
        # `\prec` session value governs (one path for REPL and script mode).
        try:
            return rra.show(v, digits)
        except rra.DomainError as e:
            raise NumericDomainError(e.args[0])
    if isinstance(v, Inverse) and id(v.fn) in _INVERSES:
        return nshow(_INVERSES[id(v.fn)], digits)
    if isinstance(v, Composed | Partial | OperatorFn | Derivative | Inverse):
        return f"<fn {_callable_label(v)}>"
    if isinstance(v, PreludeFn):
        return f"<fn \\{v.name}(x)>"
    if callable(v) and not isinstance(v, _NUMERIC_TYPES):
        return _show_callable(v)
    if isinstance(v, float):
        return _show_float(v)
    if isinstance(v, complex):
        return _show_complex(v)
    return str(v)


def _show_str(s: str) -> str:
    """Strings print quoted and round-trippable: the `\"`/`\\\\` escaping the lexer
    decodes is exactly what this emits, so a displayed string can be read back."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _show_callable(fn: Any) -> str:
    """Bound callables print as `<py module.qualname>` where the object carries one."""
    mod = getattr(fn, "__module__", None)
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
    if name:
        prefix = f"{mod}." if mod else ""
        return f"<py {prefix}{name}>"
    return f"<py {type(fn).__name__}>"


def _name_text(name: str) -> str:
    return name if is_short_name(name) else f"\\{name}"


def _display_name(name: str, spelling: str | None) -> str:
    return spelling or _name_text(name)


def _display_params(params: tuple[str, ...], spellings: tuple[str, ...] = ()) -> tuple[str, ...]:
    return tuple(
        spellings[index] if index < len(spellings) and spellings[index] else _name_text(param)
        for index, param in enumerate(params)
    )


def _display_builtin_error(message: str, name: str, spelling: str | None) -> str:
    if not spelling:
        return message
    canonical = _name_text(name)
    if canonical in message:
        return message.replace(canonical, spelling)
    pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
    return re.sub(pattern, lambda _: spelling, message)


def _show_complex(z: complex) -> str:
    """`1.0+2.0i`, `2.0i`, `1.0-1.0i`: each part through the float formatter."""
    im = _show_float(z.imag)
    if z.real == 0:
        return f"{im}i"
    return f"{_show_float(z.real)}{'' if im.startswith('-') else '+'}{im}i"


def _show_float(f: float) -> str:
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "-Inf" if f < 0 else "Inf"
    s = repr(f)  # shortest round-trip
    if "e" in s or "E" in s:
        s = format(Decimal(s), "f")
    if "." not in s:
        s += ".0"
    return s


def parse_literal(text: str) -> AdValue:
    """Parse a number literal's source text into its tier. A plain digit run is
    an exact integer; a dotted decimal without an exponent is an exact rational
    read from its own digits (`0.5` is the rational 1/2 — decimals are exact;
    `.5` likewise); the float spellings are the trailing-dot marker (`1.` is
    the float 1.0, deliberately inexact) and any exponent form (`5e-1`,
    `1.5e3`). A whole-value decimal collapses through the shared denominator-1
    rule, so `2.0` is the integer `2`."""
    if "e" in text or "E" in text or text.endswith("."):
        return float(text)
    if "." in text:
        return _normalize(Fraction(text))
    return int(text)


def _as_float(value: AdValue) -> float:
    """Widen an ad number to the float tier for approximate iteration (infinite-range
    folds and `\\lim` probes). Non-numerics and complex values are rejected with the
    seam's typed error so the caller can attach a span."""
    if isinstance(value, Quantity | UnitValue):
        raise NumError("dimensioned values require explicit magnitude extraction")
    _reject_non_numeric(value)
    if _is_complex(value):
        raise NumError("a complex value cannot widen to float")
    try:
        return float(value)
    except OverflowError:
        raise NumError("value too large to widen to float")


def _as_inexact(value: AdValue) -> float | complex:
    """`_as_float`, except a complex value widens to a complex float — the widening for
    approximate iteration that may leave the reals (`\\fold` partials, `\\lim` probes)."""
    if isinstance(value, Quantity | UnitValue):
        raise NumError("dimensioned values require explicit magnitude extraction")
    _reject_non_numeric(value)
    if _is_complex(value):
        try:
            return _inexact(_to_complex(value))
        except OverflowError:
            raise NumError("value too large to widen to float")
    return _as_float(value)


_GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
_RAYS = tuple(sign * cmath.exp(1j * k * _GOLDEN_ANGLE) for k in range(4) for sign in (1, -1))


def _drop_stray_parts(value: AdValue) -> AdValue:
    """A complex float with a part below the convergence tolerance (scaled by the modulus)
    loses that part: `\\lim(x=i) x^2` is `-1.0`, not `-1.0+2e-13i`."""
    if not isinstance(value, complex):
        return value
    cutoff = CONVERGENCE_TOLERANCE * max(1.0, abs(value))
    return _inexact(complex(0.0 if abs(value.real) <= cutoff else value.real,
                            0.0 if abs(value.imag) <= cutoff else value.imag))


def _finite(value: AdValue) -> bool:
    return cmath.isfinite(_to_complex(value)) if _is_complex(value) else math.isfinite(value)


def _settled(previous: AdValue, current: AdValue) -> bool:
    """The shared plateau test for every approximate iteration (infinite Σ/Π partials,
    `\\lim` probes): the magnitude of change since the last observation is within the
    convergence tolerance, scaled relatively for large magnitudes. The `max(1, ...)`
    floor keeps the absolute 1e-12 behavior for O(1) and near-zero values — only
    large-magnitude iteration (where float64 ulps dwarf an absolute tolerance and
    the old test could never fire) settles relatively. A non-finite float delta
    never settles. A complex pair is compared by modulus."""
    if _is_complex(previous) or _is_complex(current):
        delta = abs(_to_complex(previous) - _to_complex(current))
        scale = max(1.0, abs(_to_complex(previous)), abs(_to_complex(current)))
        return (math.isfinite(delta) and math.isfinite(scale)
                and delta <= CONVERGENCE_TOLERANCE * scale)
    if isinstance(previous, float) or isinstance(current, float):
        delta = float(previous) - float(current)
        scale = max(1.0, abs(float(previous)), abs(float(current)))
        return (math.isfinite(delta) and math.isfinite(scale)
                and abs(delta) <= CONVERGENCE_TOLERANCE * scale)
    delta = nsub(previous, current)
    return -EXACT_CONVERGENCE_TOLERANCE <= Fraction(delta) <= EXACT_CONVERGENCE_TOLERANCE


def _agree(left: float | complex, right: float | complex) -> bool:
    """The `\\lim` agreement test between sides (complex estimates by modulus), sized off the same (relatively scaled)
    tolerance as the plateau test: each side stops within `tol · scale` of its own
    plateau — up to that far from the true limit even for a perfectly smooth body —
    so legitimate estimates may sit as much as 2× the tolerance apart. Anything wider
    is a genuine disagreement."""
    scale = max(1.0, abs(left), abs(right))
    return math.isfinite(scale) and abs(left - right) <= 2 * CONVERGENCE_TOLERANCE * scale


def _diff_tolerance(order: int) -> float:
    if order < 2:
        return DIFF_TOLERANCE
    return DIFF2_TOLERANCE if order == 2 else DIFF_HIGHER_TOLERANCE


@functools.lru_cache(maxsize=32)
def _diff_weights(order: int, points: tuple[int, ...]) -> tuple[tuple[float, ...], ...]:
    weights = sympy.finite_diff_weights(order, points, 0)
    return tuple(tuple(float(w) for w in derivative[-1]) for derivative in weights)


class _DiffEstimate:
    def __init__(self, accuracy: int, increment: int):
        self.accuracy, self.increment = accuracy, increment
        self.table: list[list[tuple[float | complex, float]]] = []
        self.best: float | complex = 0.0
        self.error = math.inf

    def append(self, value: float | complex, noise: float) -> None:
        row = [(value, noise)]
        for j in range(1, len(self.table) + 1):
            factor = 1.4 ** (self.accuracy + self.increment * (j - 1))
            current, current_noise = row[j - 1]
            previous, previous_noise = self.table[-1][j - 1]
            estimate = (current * factor - previous) / (factor - 1)
            rounding = (current_noise * factor + previous_noise) / (factor - 1)
            row.append((estimate, rounding))
            error = max(abs(estimate - current), abs(estimate - previous), rounding)
            if cmath.isfinite(estimate) and error <= self.error:
                self.best, self.error = estimate, error
        self.table.append(row)

    def converged(self, order: int) -> bool:
        return self.error <= _diff_tolerance(order) * max(1.0, abs(self.best))


def _ridders(evaluate: Callable[[float], AdValue], anchor: float, order: int,
             label: str) -> float | complex:
    """Extrapolate central and near-only one-sided stencils; all orders through
    the requested derivative must agree on both sides of the anchor."""
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise NumError(f"{label} needs the order to be a positive integer")
    if order + 3 > MAX_DIFF_POINTS:
        raise NumError(f"{label}: derivative stencil exceeds the {MAX_DIFF_POINTS}-point resource limit")
    radius = (order + 1) // 2
    points = tuple(range(-radius, radius + 1))
    central_weights = _diff_weights(order, points)[order]
    active = tuple((p, w) for p, w in zip(points, central_weights) if w)
    active_weights = tuple(w for _, w in active)
    side_points = tuple(range(1, order + 4))
    side_weights = _diff_weights(order, side_points)
    central = _DiffEstimate(2, 2)
    sides = [[_DiffEstimate(len(side_points) - k, 1) for k in range(order + 1)]
             for _ in range(2)]
    samples: dict[float, float | complex] = {}

    def sample(offset: int, h: float) -> float | complex:
        t = anchor + offset * h
        if not math.isfinite(t) or (offset and t == anchor):
            raise NumError(f"{label} did not converge: probe spacing is not representable")
        if t not in samples:
            if len(samples) >= MAX_DIFF_SAMPLES:
                raise NumError(f"{label}: derivative exceeds the {MAX_DIFF_SAMPLES}-evaluation resource limit")
            value = _as_inexact(evaluate(t))
            if not cmath.isfinite(value):
                raise NumError(f"{label}: the body is not finite near {nshow(anchor)}")
            samples[t] = value
        return samples[t]

    def quotient(values: Sequence[float | complex], weights: Sequence[float],
                 h: float, degree: int) -> tuple[float | complex, float]:
        try:
            denominator = h ** degree
        except OverflowError:
            raise NumError(f"{label} did not converge: derivative scale is not representable") from None
        if denominator == 0 or not math.isfinite(denominator):
            raise NumError(f"{label} did not converge: derivative scale is not representable")
        base = values[0] if degree else 0.0
        try:
            terms = [w * (v - base) for w, v in zip(weights, values)]
            result = complex(math.fsum(complex(t).real for t in terms),
                             math.fsum(complex(t).imag for t in terms)) / denominator
            noise = 2 * sys.float_info.epsilon * math.fsum(
                abs(w) * (abs(v) + abs(base)) for w, v in zip(weights, values)) / abs(denominator)
        except (ArithmeticError, ValueError):
            raise NumError(f"{label} did not converge: derivative arithmetic overflow") from None
        return _inexact(result), noise

    h = 0.1 * abs(anchor) if anchor else 0.1
    if order > 2:
        h *= 2
    for _ in range(10):
        values = [sample(p, h) for p, _ in active]
        value, noise = quotient(values, active_weights, h, order)
        if order == 1:
            value = (sample(1, h) - sample(-1, h)) / (2 * h)
        elif order == 2:
            value = (sample(1, h) - 2 * sample(0, h) + sample(-1, h)) / (h * h)
        central.append(value, noise)
        for sign, estimates in zip((-1, 1), sides):
            values = [sample(sign * p, h) for p in side_points]
            for degree, (weights, estimate) in enumerate(zip(side_weights, estimates)):
                estimate.append(*quotient(values, weights, sign * h, degree))
        h /= 1.4

    for degree, (left, right) in enumerate(zip(*sides)):
        if not left.converged(degree) or not right.converged(degree):
            raise NumError(f"{label} did not converge: one-sided order {degree} estimates")
        scale = max(1.0, abs(left.best), abs(right.best))
        if abs(left.best - right.best) > 2 * _diff_tolerance(degree) * scale:
            raise NumError(f"{label}: derivative does not exist: left and right estimates disagree")
    if not central.converged(order):
        raise NumError(f"{label} did not converge: estimated error {central.error:.1e}")
    for side in sides:
        estimate = side[order].best
        if abs(central.best - estimate) > 2 * _diff_tolerance(order) * max(1.0, abs(central.best), abs(estimate)):
            raise NumError(f"{label} did not converge: central and one-sided estimates disagree")
    return _drop_stray_parts(central.best)


_GK_NODES = (0.991455371120812639206854697526329, 0.949107912342758524526189684047851,
             0.864864423359769072789712788640926, 0.741531185599394439863864773280788,
             0.586087235467691130294144838258730, 0.405845151377397166906606412076961,
             0.207784955007898467600689403773245, 0.0)
_GK_WEIGHTS = (0.022935322010529224963732008058970, 0.063092092629978553290700663189204,
               0.104790010322250183839876322541518, 0.140653259715525918745189590510238,
               0.169004726639267902826583426598550, 0.190350578064785409913256402421014,
               0.204432940075298892414161999234649, 0.209482141084727828012999174891714)
_GAUSS_WEIGHTS = (0.129484966168869693270611432679082, 0.279705391489276667901467771423780,
                  0.381830050505118944950369775488975, 0.417959183673469387755102040816327)


def _kronrod(f: Callable[[float], float | complex], lo: float, hi: float):
    """One G7–K15 panel: (integral, error estimate, integral of |f|)."""
    centre, half = (lo + hi) / 2, (hi - lo) / 2
    fc = f(centre)
    values = [fc]
    kronrod, gauss = fc * _GK_WEIGHTS[7], fc * _GAUSS_WEIGHTS[3]
    for j in range(7):
        pair = (f(centre - half * _GK_NODES[j]), f(centre + half * _GK_NODES[j]))
        kronrod += _GK_WEIGHTS[j] * (pair[0] + pair[1])
        if j % 2:
            gauss += _GAUSS_WEIGHTS[j // 2] * (pair[0] + pair[1])
        values.extend(pair)
    weights = (_GK_WEIGHTS[7],) + tuple(w for w in _GK_WEIGHTS[:7] for _ in (0, 1))
    absolute = sum(w * abs(v) for w, v in zip(weights, values)) * abs(half)
    mean = kronrod / 2
    spread = sum(w * abs(v - mean) for w, v in zip(weights, values)) * abs(half)
    error = abs((kronrod - gauss) * half)
    if spread and error:
        error = spread * min(1.0, (200 * error / spread) ** 1.5)
    return kronrod * half, max(error, 50 * sys.float_info.epsilon * absolute), absolute


def _quadrature(evaluate: Callable[[float], AdValue], lo: float, hi: float | None,
                label: str) -> float | complex:
    """Globally adaptive Gauss–Kronrod with independent infinite tails.
    The panel with the largest error bisects until the summed error
    is within CONVERGENCE_TOLERANCE (relatively scaled) or MAX_INTERVALS panels exist.
    Endpoints are never evaluated."""
    if hi is None:
        hi = math.inf
    if lo == -math.inf and hi == math.inf:
        return _drop_stray_parts(_quadrature(evaluate, lo, 0.0, label)
                                 + _quadrature(evaluate, 0.0, hi, label))

    def sample(x: float) -> float | complex:
        value = _as_inexact(evaluate(x))
        if not cmath.isfinite(value):
            raise NumError(f"{label}: the body is not finite at {nshow(x)}")
        return value

    if lo == -math.inf or hi == math.inf:
        origin, direction = (hi, -1) if lo == -math.inf else (lo, 1)

        def f(t: float) -> float | complex:
            if t >= 1:
                raise NumError(f"{label} did not converge: the integral diverges or decays too slowly")
            return sample(origin + direction * t / (1 - t)) / (1 - t) ** 2
        lo, hi = 0.0, 1.0
    else:
        f = sample
    ids = count()
    panels = []

    def add(a: float, b: float) -> None:
        value, error, absolute = _kronrod(f, a, b)
        heapq.heappush(panels, (-error, next(ids), a, b, value, absolute))

    add(lo, hi)
    while True:
        total = sum(p[4] for p in panels)
        error = sum(-p[0] for p in panels)
        scale = max(1.0, abs(total), sum(p[5] for p in panels))
        if error <= CONVERGENCE_TOLERANCE * scale:
            return _drop_stray_parts(total)
        if len(panels) >= MAX_INTERVALS:
            raise NumError(f"{label} did not converge within {MAX_INTERVALS} subintervals")
        _, _, a, b, _, _ = heapq.heappop(panels)
        if (a + b) / 2 in (a, b):
            raise NumError(f"{label} did not converge: the integrand is singular inside the range")
        add(a, (a + b) / 2)
        add((a + b) / 2, b)


# Tail-estimation knobs for infinite-range folds. The raw
# consecutive-partial plateau cannot see a slow tail (zeta(2)'s increments drop
# under the tolerance a million terms before the tail does), so infinite folds
# get a second, earlier-only exit: estimate the limit from the recent terms'
# shape, claim a bounded error, and return only after a confirmation window
# honors the claim. Anything unrecognized abstains — the raw plateau and the
# cap error then behave exactly as before.
_FOLD_TAIL_WINDOW = 8
_FOLD_TAIL_MIN_TERMS = 16
_FOLD_TAIL_STABLE_STEPS = 3
_FOLD_TAIL_CONFIRM_TERMS = 24
_FOLD_TAIL_ERROR_BUDGET = 256.0  # claimed accuracy, × CONVERGENCE_TOLERANCE
_FOLD_TAIL_MIN_P = 1.05  # decay exponent must clear 1 with margin (else abstain)
_FOLD_TAIL_MAX_SPREAD = 0.5  # ... and read consistently across the window
_FOLD_TAIL_SAFETY = 4.0  # claimed error = SAFETY × modeled error


class _FoldTailEstimator:
    """Tail-based early exit for one infinite sum (`\\sum` only).

    Fed each term's float value and the running float partial, it recognizes
    two shapes in a sliding window of recent terms and proposes a corrected
    limit with a claimed error bound:

    - monotone terms decaying like `k^-p` (`1/i^2`, ...): the decay exponent
      comes from consecutive term ratios, the tail from the integral-test
      form `|t_k|·k/(p-1)`, and the proposal is the partial plus that tail.
    - strictly alternating terms with shrinking magnitude: the Leibniz bound
      (`|tail| <= |t_k|`) with the midpoint proposal `S_k - t_k/2`.

    Deliberately sums-only: a product's log-space ratios would inherit the
    body's own float-cancellation noise (`log(1 + 1/i^2)` keeps ~5 digits
    once terms pass 1e-10, biasing the decay estimate invisibly to every
    local check), so `\\prod` keeps the consecutive-partial plateau, which
    stays correct there. Sum terms from exactly-rounded division keep full
    precision at every magnitude, and the spread gate below additionally
    rejects any shape whose decay reads inconsistently (exponentials,
    cancellation-noisy bodies, regime changes).

    Verify-before-return: an eligible proposal must hold for
    `_FOLD_TAIL_STABLE_STEPS` consecutive terms to arm, then survive
    `_FOLD_TAIL_CONFIRM_TERMS` further terms with the proposal moving no more
    than twice the claimed error and the shape persisting — otherwise it
    disarms and iteration resumes. The raw plateau always wins ties (it is
    the stronger claim), and the cap error is untouched. Total: never raises,
    returns a float proposal or None."""

    def __init__(self):
        self._recent: list[tuple[int, float]] = []
        self._k = 0
        self._stable = 0
        self._armed: tuple[float, float, str] | None = None
        self._confirm = 0
        self.abstained = True  # the last term gave no shape to estimate from

    def _disarm(self) -> None:
        self._stable = 0
        self._armed = None
        self._confirm = 0

    def observe(self, term: AdValue, acc: AdValue) -> float | None:
        """Offer one evaluated term and running partial; return a corrected
        limit when the confirmation window completes, else None."""
        self.abstained = True
        if not isinstance(term, float) or not isinstance(acc, float):
            self._recent.clear()
            self._disarm()
            return None
        if not math.isfinite(term) or term == 0.0:
            self._recent.clear()
            self._disarm()
            return None
        self._k += 1
        self._recent.append((self._k, term))
        if len(self._recent) > _FOLD_TAIL_WINDOW:
            self._recent.pop(0)
        if self._k < _FOLD_TAIL_MIN_TERMS or len(self._recent) < _FOLD_TAIL_WINDOW:
            return None
        path = self._classify()
        if path is None:
            self._disarm()
            return None
        estimate = self._estimate(path, acc)
        if estimate is None:
            self._disarm()
            return None
        value, error = estimate
        self.abstained = False
        if self._armed is None:
            budget = _FOLD_TAIL_ERROR_BUDGET * CONVERGENCE_TOLERANCE * max(1.0, abs(value))
            if error <= budget:
                self._stable += 1
                if self._stable >= _FOLD_TAIL_STABLE_STEPS:
                    self._armed = (value, error, path)
                    self._confirm = 0
            else:
                self._stable = 0
            return None
        armed_value, armed_error, armed_path = self._armed
        if path != armed_path or error > 4 * armed_error:
            self._disarm()
            return None
        self._confirm += 1
        if self._confirm >= _FOLD_TAIL_CONFIRM_TERMS:
            proposal = value
            if abs(value - armed_value) <= 2 * armed_error:
                self._disarm()
                return proposal
            self._disarm()
        return None

    def _classify(self) -> str | None:
        """Read the window's shape: monotone-decaying `pos`/`neg` terms or a
        strictly alternating `alt` run with shrinking magnitude — else None."""
        signs = [1.0 if t > 0 else -1.0 for _, t in self._recent]
        mags = [abs(t) for _, t in self._recent]
        if any(m == 0.0 or not math.isfinite(m) for m in mags):
            return None
        if all(signs[0] == s for s in signs):
            if all(a > b for a, b in zip(mags, mags[1:])):
                return "pos" if signs[0] > 0 else "neg"
            return None
        if all(s != u for s, u in zip(signs, signs[1:])
               ) and all(a > b for a, b in zip(mags, mags[1:])):
            return "alt"
        return None

    def _estimate(self, path: str, total: float) -> tuple[float, float] | None:
        """A (proposal, claimed-error) pair for this term, or None when the
        decay gates fail."""
        if path == "alt":
            _, t = self._recent[-1]
            return total - t / 2, abs(t) / 2
        # Monotone `k^-p` decay: per-step exponents from consecutive ratios
        # (exact for a pure power law), median for robustness.
        ratios = []
        for (j_prev, t_prev), (j, t) in zip(self._recent, self._recent[1:]):
            ratios.append(math.log(abs(t_prev) / abs(t)) / math.log(j / j_prev))
        if min(ratios) <= _FOLD_TAIL_MIN_P:
            return None
        ordered = sorted(ratios)
        p = ordered[len(ordered) // 2]
        if ordered[-1] - ordered[0] > _FOLD_TAIL_MAX_SPREAD:
            return None
        _, t = self._recent[-1]
        tail = abs(t) * self._k / (p - 1)
        if path == "neg":
            tail = -tail
        error = _FOLD_TAIL_SAFETY * abs(tail) * max(ordered[-1] - ordered[0], 1 / self._k)
        return total + tail, error


class _ComplexTailEstimator:
    """`_FoldTailEstimator` for an infinite sum of complex terms: one estimator per
    component, returning a limit once both components have confirmed. A component whose
    terms are all exactly zero is settled at its partial (`i/k²` has a constant real
    part)."""

    def __init__(self):
        self._parts = (_FoldTailEstimator(), _FoldTailEstimator())
        self._seen_nonzero = [False, False]
        self._limits: list[float | None] = [None, None]
        self._recent: list[list[float]] = [[], []]

    def observe(self, term: complex, acc: complex) -> complex | None:
        terms, accs = (term.real, term.imag), (acc.real, acc.imag)
        for c, (t, a) in enumerate(zip(terms, accs)):
            if t == 0.0 and not self._seen_nonzero[c]:
                self._limits[c] = a
                continue
            if not self._seen_nonzero[c]:
                self._seen_nonzero[c] = True
                self._limits[c] = None
            limit = self._parts[c].observe(t, a)
            self._recent[c] = (self._recent[c] + [abs(t)])[-_FOLD_TAIL_WINDOW:]
            if limit is not None:
                self._limits[c] = limit
            elif (self._parts[c].abstained and len(self._recent[c]) == _FOLD_TAIL_WINDOW
                  and max(self._recent[c]) <= CONVERGENCE_TOLERANCE * max(1.0, abs(a))):
                self._limits[c] = a  # a shapeless component whose recent terms all vanish (a fast tail)
        if None in self._limits:
            return None
        result = complex(*self._limits)
        self._limits = [None, None]
        return result


class EvalError(Exception):
    """A runtime failure with its message and, when known, the offending span."""

    def __init__(self, msg: str, span: Span | None = None, source: str | None = None,
                 *, domain: bool = False):
        super().__init__(msg)
        self.msg = msg
        self.span = span
        self.source = source
        self.domain = domain


_MISSING = object()
_IMPORTING = object()  # module-registry marker: evaluation in progress (cycle guard)


class AdFunction:
    def __init__(self, name, params, body, closure, spelling=None, param_spellings=()):
        self.name, self.params, self.body, self.closure = name, params, body, closure
        self.display_name = _display_name(name, spelling) if name else "λ"
        self.param_spellings = _display_params(params, param_spellings)

    def __call__(self, *args):
        if len(args) != len(self.params):
            raise EvalError(f"{self.display_name} takes {len(self.params)} arguments, "
                            f"got {len(args)}")
        frame = dict(zip(self.params, args))
        if self.name:
            frame[self.name] = self
        child = Engine(frame, self.body.spans, self.body.definitions, self.closure,
                       self.closure.modules,
                       self.closure.base_dir, self.closure.import_chain,
                       quotes=self.body.quotes)
        try:
            scope = {"_e": child}
            exec(self.body.code, scope)
        except EvalError:
            raise
        return scope["_result"]


def _resolve_dotted(path: str) -> Any:
    """Resolve `math.sqrt`-style paths: import the longest importable module prefix,
    then walk attributes over the rest. Bare names (`int`, `len`) resolve against
    `builtins`. Returns _MISSING when unresolvable."""
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr, _MISSING)
            if obj is _MISSING:
                return _MISSING
        return obj
    import builtins

    return getattr(builtins, path, _MISSING)


def _sympy_to_ad(expr: Any, type_name: str) -> AdValue:
    """A sympy expression across the `\\py` boundary: the symbolic gate, then
    the algebraic gate, then the RRA gate — anything still unconvertible is a
    named rejection. Shared by `_to_ad` and the `\\re`/`\\im` projections."""
    try:
        return symbolic.from_sympy(expr)
    except (Unrepresentable, DomainError):
        pass
    try:
        return algebraic.from_sympy(expr)
    except (algebraic.Unrepresentable, algebraic.DomainError):
        pass
    try:
        return rra.from_sympy(expr)
    except (rra.Unrepresentable, rra.DomainError):
        raise NumError(
            f"cannot convert a returned {type_name} to an ad value") from None


def value_to_sympy(value: AdValue) -> sympy.Expr:
    """An ad number as a sympy expression, for the rewrite bridge (`adhoc/rewrite.py`)."""
    if isinstance(value, bool) or not isinstance(value, numbers.Number | Fraction | Gaussian
                                                  | Symbolic | Algebraic | RRA):
        raise NumError(f"cannot rewrite {nshow(value)}")
    if isinstance(value, complex):
        return sympy.Float(value.real) + sympy.I * sympy.Float(value.imag)
    if isinstance(value, float):
        return sympy.Float(value)
    return symbolic._to_expr(value)


def _to_ad(value: Any, preserve_bool: bool = False) -> Any:
    """The Python→ad half of the interop conversion matrix (see module docstring).
    Raises NumError with a matrix-specific message on everything without an ad
    representation; the caller attaches the call's span. Internal callable and
    branch results pass `preserve_bool=True`."""
    if value is None:
        raise NumError("the call returned nothing")
    if isinstance(value, AdFunction | PreludeFn | Composed | Partial | OperatorFn | Derivative | Inverse
                      | ExpressionValue
                      | TensorValue | ArrayValue | SetValue | SymbolicSetValue | GraphValue | Quantity | UnitValue):
        return value
    if isinstance(value, RangeValue | IntervalValue | LazySeq):
        return value
    if isinstance(value, bool):  # before int — bool is an int subclass
        return value if preserve_bool else int(value)
    if isinstance(value, int | float | Fraction):
        return value
    if isinstance(value, Decimal):
        return _normalize(Fraction(value))
    if isinstance(value, numbers.Rational):
        # Two-arg construction normalizes; the single-Rational-arg form copies
        # numerator/denominator verbatim on py3.12+.
        return _normalize(Fraction(int(value.numerator), int(value.denominator)))
    if isinstance(value, Gaussian | Symbolic | Algebraic | RRA):
        return value
    if type(value).__module__.startswith("sympy"):
        # A sympy object returned across the \py boundary: recognized closed forms
        # convert through the symbolic tier's own gate, algebraic numbers through
        # the algebraic tier's, every other finite number through the RRA tier's
        # (sympy rationals were already handled exactly above); anything else
        # is a named rejection.
        return _sympy_to_ad(value, type(value).__name__)
    if isinstance(value, str):
        # Already an ad value: bindable, concatenable, printable.
        return value
    if isinstance(value, complex):
        return _inexact(value)
    if isinstance(value, list | tuple):
        return ArrayValue(tuple(_to_ad(item, preserve_bool) for item in value))
    if isinstance(value, set | frozenset):
        return SetValue(_dedup(_to_ad(item, preserve_bool) for item in value))
    if _is_ndarray(value):
        return _ndarray_to_ad(value)
    if isinstance(value, numbers.Real):
        return float(value)
    raise NumError(f"cannot convert a returned {type(value).__name__} to an ad value")


def _is_ndarray(value: Any) -> bool:
    """Duck-typed so the runtime never imports numpy."""
    return (type(value).__module__.split(".")[0] == "numpy"
            and hasattr(value, "tolist") and hasattr(value, "ndim"))


def _ndarray_to_ad(value: Any) -> Any:
    """A numpy ndarray as a tensor: 0-d gives its scalar, nested entries stack, and
    empty or ragged shapes are typed rejections."""
    if value.ndim == 0:
        return _to_ad(value.tolist())
    if value.size == 0:
        raise NumError("cannot convert an empty ndarray to an ad tensor")

    def build(nested: Any) -> Any:
        if not isinstance(nested, list):
            item = _to_ad(nested)
            _reject_non_numeric(item)
            return item
        try:
            return tn.stack([build(item) for item in nested])
        except TensorError as e:
            raise NumError(e.args[0]) from None

    return build(value.tolist())


def _to_py(value: Any) -> Any:
    """The ad→Python half of the boundary, applied to arguments of Python callables:
    tensors and arrays become nested lists, sets become a `frozenset` (a list when
    an element is unhashable). Everything else is already native."""
    if isinstance(value, Quantity | UnitValue):
        raise NumError("Python calls require explicit magnitude extraction for quantities")
    if isinstance(value, TensorValue):
        return _tensor_to_list(value.shape, value.items)
    if isinstance(value, ArrayValue):
        return [_to_py(item) for item in value.items]
    if isinstance(value, SetValue):
        items = [_to_py(item) for item in value.items]
        try:
            return frozenset(items)
        except TypeError:
            return items
    return value


def _tensor_to_list(shape: tuple[int, ...], items: tuple) -> Any:
    if len(shape) == 1:
        return [_to_py(item) for item in items]
    stride = len(items) // shape[0]
    return [_tensor_to_list(shape[1:], items[k * stride:(k + 1) * stride])
            for k in range(shape[0])]


_INTERNAL_CALLABLES: tuple = ()  # set below, once Composed and Partial exist


def _invoke(fn: Any, args: tuple, kwargs: dict | None = None,
            spelling: str | None = None) -> Any:
    """Apply any callable to ad values and return an ad value. The one call path:
    `app`, `\\map`/`\\fold`/`\\filter`, compositions, and partials all go through it, so
    Python callables convert the same way everywhere. Failures are `NumError`s
    (or already-spanned `EvalError`s from user code); the caller attaches the span."""
    kwargs = kwargs or {}
    if not callable(fn):
        raise NumError(f"{nshow(fn)} is not a function")
    internal = isinstance(fn, _INTERNAL_CALLABLES)
    if kwargs and internal and not isinstance(fn, PreludeFn | Inverse):
        raise NumError("user-defined functions take positional arguments only")
    if isinstance(fn, AdFunction) and len(args) != len(fn.params):
        label = spelling or fn.display_name
        raise NumError(f"{label} takes {len(fn.params)} arguments, got {len(args)}")
    if not internal:
        args = tuple(_to_py(a) for a in args)
        kwargs = {k: _to_py(v) for k, v in kwargs.items()}
    try:
        result = fn(*args, **kwargs)
    except (NumError, EvalError):
        raise
    except Exception as e:
        name = spelling or getattr(fn, "__name__", None) or "<callable>"
        error_type = NumericDomainError if isinstance(e, (ZeroDivisionError, OverflowError)) else NumError
        raise error_type(f"{name}: {type(e).__name__}: {e}") from None
    return _to_ad(result, preserve_bool=internal)


class Composed:
    """`f ∘ g`: applies `g`, then `f` to its result."""

    def __init__(self, outer: Any, inner: Any):
        self.outer, self.inner = outer, inner

    def __call__(self, *args):
        return _invoke(self.outer, (_invoke(self.inner, args),))


class Partial:
    """`f(a, _)`: `fn` with some argument slots fixed; calling it fills the holes, in
    order, from its own arguments."""

    def __init__(self, fn: Any, slots: tuple, holes: tuple[int, ...], kwargs: dict):
        self.fn, self.slots, self.holes, self.kwargs = fn, slots, holes, kwargs

    def __call__(self, *args):
        if len(args) != len(self.holes):
            raise NumError(f"{nshow(self)} takes {len(self.holes)} arguments, got {len(args)}")
        full = list(self.slots)
        for position, value in zip(self.holes, args):
            full[position] = value
        return _invoke(self.fn, tuple(full), self.kwargs)


def ncompare(op: str, a: AdValue, b: AdValue) -> bool:
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        a, b, _ = units.matching(a, b)
    _reject_non_numeric(a, b)
    if _is_complex(a) or _is_complex(b):
        raise NumError("complex values are not ordered")
    if isinstance(a, float) or isinstance(b, float):
        a, b = _comparison_pair(a, b)
        if not isinstance(a, float) and not isinstance(b, float):
            return ncompare(op, a, b)
    elif isinstance(a, RRA) or isinstance(b, RRA):
        # Exact ordering across the exact + symbolic + algebraic + RRA
        # tiers (a float operand takes the approximate float branch
        # above).
        return rra.compare(op, a, b)
    elif isinstance(a, Algebraic) or isinstance(b, Algebraic):
        # Exact ordering across the exact + symbolic + algebraic tiers
        # (a float operand takes the approximate float branch above).
        return algebraic.compare(op, a, b)
    elif isinstance(a, Symbolic) or isinstance(b, Symbolic):
        # Exact ordering across the exact + symbolic tiers (a float operand
        # takes the approximate float branch above).
        return symbolic.compare(op, a, b)
    else:
        a, b = Fraction(a), Fraction(b)
    return {"lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[op]


def _need_sets(symbol: str, a: AdValue, b: AdValue) -> None:
    if isinstance(a, SymbolicSetValue) or isinstance(b, SymbolicSetValue):
        raise NumError(f"`{symbol}` does not support symbolic sets")
    if not isinstance(a, SetValue) or not isinstance(b, SetValue):
        raise NumError(f"`{symbol}` needs two sets, got {nshow(a)} and {nshow(b)}")


def nunion(a: AdValue, b: AdValue) -> AdValue:
    _need_sets("∪", a, b)
    return SetValue(_dedup(a.items + b.items))


def nintersect(a: AdValue, b: AdValue) -> AdValue:
    _need_sets("∩", a, b)
    return SetValue(tuple(x for x in a.items if _contains(b.items, x)))


def nsetminus(a: AdValue, b: AdValue) -> AdValue:
    _need_sets("∖", a, b)
    return SetValue(tuple(x for x in a.items if not _contains(b.items, x)))


def nsubseteq(a: AdValue, b: AdValue) -> bool:
    _need_sets("⊆", a, b)
    return all(_contains(b.items, x) for x in a.items)


def _range_contains(r: RangeValue, x: AdValue) -> bool:
    """`x` is a term of the progression: `(x - start)/step` is a non-negative integer
    (float quotients must be whole floats) and `x` has not passed the end."""
    if (isinstance(x, bool) or not isinstance(x, _NUMERIC_TYPES) or _is_complex(x)):
        return False
    k = ndiv(nsub(x, r.start), r.step)
    if isinstance(k, float):
        if not k.is_integer():
            return False
    elif _integer_exponent(k) is None:
        return False
    if ncompare("lt", k, 0):
        return False
    if r.end is None:
        return True
    return ncompare("le" if ncompare("gt", r.step, 0) else "ge", x, r.end)


def _membership(symbol: str, value: AdValue, collection: AdValue) -> bool:
    if isinstance(collection, SymbolicSetValue):
        return collection.contains(value)
    if isinstance(collection, SetValue | ArrayValue):
        return _contains(collection.items, value)
    if isinstance(collection, RangeValue):
        return _range_contains(collection, value)
    if isinstance(collection, IntervalValue):
        if (isinstance(value, bool) or not isinstance(value, _NUMERIC_TYPES)
                or _is_complex(value)
                or isinstance(value, float) and not math.isfinite(value)):
            return False
        if isinstance(collection.start, float) and math.isinf(collection.start):
            infinity, finite = collection.start, collection.end
        else:
            infinity, finite = collection.end, collection.start
        if isinstance(finite, float) and math.isinf(finite):
            return True
        op = "le" if infinity < 0 else "ge"
        return ncompare(op, value, finite)
    raise NumError(f"`{symbol}` needs a set, array, range, or interval on the right, "
                   f"got {nshow(collection)}")


def nmember(value: AdValue, collection: AdValue) -> bool:
    return _membership("∈", value, collection)


def nnotmember(value: AdValue, collection: AdValue) -> bool:
    return not _membership("∉", value, collection)


def nsubset(a: AdValue, b: AdValue) -> bool:
    _need_sets("⊂", a, b)
    return len(a.items) < len(b.items) and nsubseteq(a, b)


def nsupseteq(a: AdValue, b: AdValue) -> bool:
    _need_sets("⊇", a, b)
    return nsubseteq(b, a)


def nsupset(a: AdValue, b: AdValue) -> bool:
    _need_sets("⊃", a, b)
    return nsubset(b, a)


APPROX_REL_TOL = 1e-9
APPROX_ABS_TOL = 1e-12


def _approx_reals(a: AdValue, b: AdValue) -> bool:
    try:
        return math.isclose(float(a), float(b), rel_tol=APPROX_REL_TOL, abs_tol=APPROX_ABS_TOL)
    except OverflowError:
        return neq(a, b)


def napprox(a: AdValue, b: AdValue) -> bool:
    if isinstance(a, Quantity | UnitValue) or isinstance(b, Quantity | UnitValue):
        a, b, _ = units.matching(a, b)
    _reject_non_numeric(a, b)
    if _is_complex(a) or _is_complex(b):
        return (_approx_reals(_re_call(a), _re_call(b))
                and _approx_reals(_im_call(a), _im_call(b)))
    return _approx_reals(a, b)


def nnotequal(a: AdValue, b: AdValue) -> bool:
    return not neq(a, b)


def _booleans(symbol: str, *vals: AdValue) -> None:
    for v in vals:
        if not isinstance(v, bool):
            raise NumError(f"`{symbol}` needs boolean operands, got {nshow(v)}")


def nand(a: AdValue, b: AdValue) -> bool:
    _booleans("∧", a, b)
    return a and b


def nor(a: AdValue, b: AdValue) -> bool:
    _booleans("∨", a, b)
    return a or b


def nimplies(a: AdValue, b: AdValue) -> bool:
    _booleans("→", a, b)
    return not a or b


def niff(a: AdValue, b: AdValue) -> bool:
    _booleans("↔", a, b)
    return a == b


def nnot(a: AdValue) -> bool:
    _booleans("¬", a)
    return not a


def ncompose(f: Any, g: Any) -> Any:
    if not callable(f) or not callable(g):
        raise NumError(f"`∘` needs two functions, got {nshow(f)} and {nshow(g)}")
    return Composed(f, g)


# Connective -> (left value that decides the result, that result).
_SHORT_CIRCUIT = {"and": (False, False), "or": (True, True), "implies": (False, True)}


class OperatorFn:
    """An operator as a function value: `(+)`, `\\fold(∪, xs)`. Positional only;
    one singleton per operator (`OPERATORS`), so a binding check on two spellings of
    the same operator is an identity match."""

    __slots__ = ("symbol", "fn", "arities")

    def __init__(self, symbol: str, fn: Callable, arities: tuple[int, ...] = (2,)):
        self.symbol, self.fn, self.arities = symbol, fn, arities

    def __call__(self, *args):
        if len(args) not in self.arities:
            wanted = " or ".join(str(n) for n in self.arities)
            raise NumError(f"`{self.symbol}` takes {wanted} arguments, got {len(args)}")
        return self.fn(*args)


def _minus(*args):
    return nneg(*args) if len(args) == 1 else nsub(*args)


def _cmp(op: str) -> Callable:
    return lambda a, b: ncompare(op, a, b)


_OPERATOR_IMPLS = {
    "fact": (nfact, (1,)), "dfact": (ndfact, (1,)),
    "add": (nadd, (2,)), "sub": (_minus, (1, 2)), "mul": (nmul, (2,)),
    "div": (ndiv, (2,)), "pow": (npow, (2,)), "dot": (ndot, (2,)),
    "times": (ntimes, (2,)), "otimes": (notimes, (2,)),
    "compose": (ncompose, (2,)), "mod": (nmod, (2,)), "angle": (npolar, (2,)), "union": (nunion, (2,)),
    "intersect": (nintersect, (2,)), "setminus": (nsetminus, (2,)),
    "and": (nand, (2,)), "or": (nor, (2,)), "implies": (nimplies, (2,)), "iff": (niff, (2,)),
    "not": (nnot, (1,)),
    "lt": (_cmp("lt"), (2,)), "le": (_cmp("le"), (2,)),
    "gt": (_cmp("gt"), (2,)), "ge": (_cmp("ge"), (2,)),
    "member": (nmember, (2,)), "subseteq": (nsubseteq, (2,)),
    "ne": (nnotequal, (2,)), "approx": (napprox, (2,)),
    "notmember": (nnotmember, (2,)), "subset": (nsubset, (2,)),
    "supseteq": (nsupseteq, (2,)), "supset": (nsupset, (2,)),
}
OPERATORS = {name: OperatorFn(OP_SYMBOLS[name], fn, arities)
             for name, (fn, arities) in _OPERATOR_IMPLS.items()}


class _QuantitySamples:
    def __init__(self, function, input_dimensions):
        self.function = function
        self.input_dimensions = input_dimensions
        self.output_dimensions = None

    def __call__(self, magnitude):
        value = self.function(units.attach(magnitude, self.input_dimensions))
        raw, dims = units.parts(value)
        if self.output_dimensions is None:
            self.output_dimensions = dims
        elif self.output_dimensions != dims:
            raise NumError("calculus body dimensions change between samples")
        return _as_inexact(raw)


def _numeric_derivative(function, point, order, label):
    raw, dims = units.parts(point)
    anchor = _as_inexact(raw)
    if isinstance(anchor, complex) or not math.isfinite(anchor):
        raise NumError(f"{label} needs a finite real point")
    samples = _QuantitySamples(function, dims)
    result = _ridders(samples, anchor, order, label)
    dimension = units.combine(samples.output_dimensions, units.power(dims, order), -1)
    return units.attach(result, dimension)


class Derivative:
    """Repeated primes differentiate a one-argument function. Exact when the
    body bridges to sympy and the point is exact; otherwise numeric (`_ridders`)."""

    def __init__(self, fn: Any, order: int):
        self.fn, self.order = fn, order
        self._symbolic: tuple[sympy.Symbol, sympy.Expr] | None | bool = False
        self._dimensional_forms = {}

    def _exact_form(self) -> tuple[sympy.Symbol, sympy.Expr] | None:
        if self._symbolic is False:
            self._symbolic = None
            if isinstance(self.fn, AdFunction) and len(self.fn.params) == 1:
                from . import rewrite
                try:
                    symbol, form, _ = rewrite.run_limited(rewrite._derivative_form, self.fn, self.order)
                    self._symbolic = (symbol, form)
                except (rewrite.RewriteError, NotImplementedError, NumError):
                    pass
        return self._symbolic

    def _exact(self, point: AdValue) -> AdValue | None:
        from . import dimensional, rewrite
        raw, dims = units.parts(point)
        if isinstance(self.fn, AdFunction) and len(self.fn.params) == 1 and (
                isinstance(point, Quantity | UnitValue) or
                dimensional.has_units(self.fn.body.node, self.fn.closure._lookup)):
            if _is_inexact(raw):
                return None
            if dims not in self._dimensional_forms:
                try:
                    self._dimensional_forms[dims] = rewrite.run_limited(
                        rewrite._derivative_form, self.fn, self.order, {self.fn.params[0]: dims})
                except (rewrite.RewriteError, NotImplementedError, NumError):
                    self._dimensional_forms[dims] = None
            if self._dimensional_forms[dims] is None:
                return None
            symbol, form, output = self._dimensional_forms[dims]
            return units.attach(_sympy_to_ad(form.subs(symbol, value_to_sympy(raw)), "derivative"), output)
        if isinstance(point, float | complex):
            return None
        form = self._exact_form()
        if form is None:
            return None
        symbol, expr = form
        try:
            return _sympy_to_ad(expr.subs(symbol, value_to_sympy(point)), "sympy expression")
        except (NumError, TypeError, ValueError, ZeroDivisionError):
            return None

    def __call__(self, *args):
        if len(args) != 1:
            raise NumError(f"{_callable_label(self)} takes 1 argument, got {len(args)}")
        _reject_non_numeric(args[0])
        exact = self._exact(args[0])
        if exact is not None:
            return exact
        return _numeric_derivative(lambda point: _invoke(self.fn, (point,)),
                                   args[0], self.order, _callable_label(self))


class Inverse:
    """A paired scalar inverse or the exact/numeric root nearest the target.
    `all=True` returns the symbolic preimage set instead."""

    SPREAD_STEPS = 60

    def __init__(self, fn: Any):
        self.fn = fn
        self._solved: tuple[sympy.Dummy, list[sympy.Expr]] | None = None

    def _solutions(self) -> tuple[sympy.Dummy, list[sympy.Expr]]:
        """The roots of `f(x) = Y` for a symbolic `Y`, solved once; empty when `f` is not a
        one-parameter user function whose body bridges to sympy."""
        if self._solved is None:
            target = sympy.Dummy("y")
            self._solved = (target, [])
            if isinstance(self.fn, AdFunction) and len(self.fn.params) == 1:
                from . import rewrite
                try:
                    self._solved = rewrite.run_limited(rewrite._inverse_form, self.fn)
                except (rewrite.RewriteError, NotImplementedError, NumError):
                    pass
        return self._solved

    def _exact(self, y: AdValue) -> AdValue | None:
        """The exact root of `f(x) = y` nearest `y` (the larger real part on a tie), or None
        when there is none the exact tiers can hold. A real `y` takes real roots only."""
        if isinstance(y, float | complex):
            return None
        target, roots = self._solutions()
        if not roots:
            return None
        point = value_to_sympy(y)
        found = []
        for root in roots:
            value = root.subs(target, point)
            if value.free_symbols:
                continue
            approx = sympy.N(value, 30)
            if not isinstance(y, Gaussian) and abs(sympy.im(approx)) > 1e-20:
                continue
            found.append((float(abs(approx - sympy.N(point, 30))),
                          -float(sympy.re(approx)), value))
        for *_, value in sorted(found, key=lambda item: item[:2]):
            try:
                return _sympy_to_ad(value, "sympy expression")
            except NumError:
                continue
        return None

    def __call__(self, *args, all=False, domain=_MISSING):
        label = _callable_label(self)
        if not isinstance(all, bool):
            raise NumError(f"{label}: all needs a boolean")
        if not all and domain is not _MISSING:
            raise NumError(f"{label}: domain requires all=true")
        if len(args) != 1:
            raise NumError(f"{label} takes 1 argument, got {len(args)}")
        _reject_non_numeric(args[0])
        if all:
            if isinstance(args[0], Quantity | UnitValue):
                raise NumError("dimensioned inverse functions are unsupported")
            from . import rewrite
            try:
                return rewrite.preimages(self.fn, args[0], "complex" if domain is _MISSING else domain)
            except rewrite.RewriteError as error:
                raise NumError(f"{label}: {error}") from None
        paired = _INVERSES.get(id(self.fn))
        if paired is not None:
            return _invoke(paired, args)
        if isinstance(args[0], Quantity | UnitValue):
            raise NumError("dimensioned inverse functions are unsupported")
        exact = self._exact(args[0])
        if exact is not None:
            return exact
        target = _as_inexact(args[0])
        if isinstance(target, complex) or not math.isfinite(target):
            raise NumError(f"{label} needs a finite real value")

        def gap(x: float) -> float:
            raw = _invoke(self.fn, (x,))
            if isinstance(raw, Quantity | UnitValue):
                raise NumError("dimensioned inverse functions are unsupported")
            value = _as_inexact(raw)
            if isinstance(value, complex):
                raise NumError(f"{label}: the function is not real-valued near {nshow(x)}")
            return value - target

        root = self._bracket(gap, target) or self._secant(gap, target)
        scale = max(1.0, abs(target))
        if root is None or abs(gap(root)) > 1e-9 * scale:
            raise NumError(f"{label}: no value maps to {nshow(args[0])} near it")
        return root

    def _bracket(self, gap: Callable[[float], float], seed: float) -> float | None:
        centre = gap(seed)
        if centre == 0:
            return seed
        width = max(abs(seed), 1.0) / 16
        for _ in range(self.SPREAD_STEPS):
            for side in (width, -width):
                try:
                    value = gap(seed + side)
                except (NumError, EvalError):
                    continue
                if not math.isfinite(value):
                    continue
                if value == 0:
                    return seed + side
                if (value < 0) != (centre < 0):
                    return self._bisect(gap, seed, seed + side)
            width *= 2
        return None

    @staticmethod
    def _bisect(gap: Callable[[float], float], a: float, b: float) -> float:
        low, high = (a, b) if a < b else (b, a)
        low_negative = gap(low) < 0
        for _ in range(MAX_PROBES):
            mid = (low + high) / 2
            if mid in (low, high):
                break
            if (gap(mid) < 0) == low_negative:
                low = mid
            else:
                high = mid
        return min(low, high, key=lambda x: abs(gap(x)))

    @staticmethod
    def _secant(gap: Callable[[float], float], seed: float) -> float | None:
        x0, x1 = seed, seed + max(abs(seed), 1.0) / 16
        try:
            f0, f1 = gap(x0), gap(x1)
            for _ in range(MAX_PROBES):
                if f1 == f0:
                    break
                x0, x1, f0 = x1, x1 - f1 * (x1 - x0) / (f1 - f0), f1
                f1 = gap(x1)
                if abs(f1) <= 1e-13:
                    return x1
        except (NumError, EvalError):
            return None
        return x1 if math.isfinite(x1) else None


_INTERNAL_CALLABLES = (AdFunction, PreludeFn, Composed, Partial, OperatorFn, Derivative, Inverse)


def _callable_label(fn: Any) -> str:
    if isinstance(fn, AdFunction):
        if not fn.name:
            return f"λ({', '.join(fn.param_spellings)})"
        return fn.display_name
    if isinstance(fn, PreludeFn):
        return f"\\{fn.name}"
    if isinstance(fn, Composed):
        return f"{_callable_label(fn.outer)} ∘ {_callable_label(fn.inner)}"
    if isinstance(fn, Partial):
        return _partial_text(fn)
    if isinstance(fn, OperatorFn):
        return fn.symbol
    if isinstance(fn, Derivative):
        return f"{_callable_label(fn.fn)}{'′' * fn.order}"
    if isinstance(fn, Inverse):
        paired = _INVERSES.get(id(fn.fn))
        if paired is not None:
            return _callable_label(paired)
        return f"{_callable_label(fn.fn)}⁻¹"
    return _show_callable(fn)[len("<py "):-1]


def _partial_text(p: Partial) -> str:
    holes = set(p.holes)
    parts = ["·" if i in holes else nshow(v) for i, v in enumerate(p.slots)]
    parts += [f"{k}={nshow(v)}" for k, v in p.kwargs.items()]
    return f"{_callable_label(p.fn)}({', '.join(parts)})"


class _InfiniteFold:
    """The convergence rule shared by the `\\sum`/`\\prod` binders and `\\fold` over an
    infinite input: feed each new partial, get the limit back once the partials plateau
    (or, for sums, the tail estimate is confirmed); a diverging or non-converging fold
    raises a `NumError` for the caller to place."""

    def __init__(self, label: str, estimate: bool):
        self.label = label
        self.estimator = _FoldTailEstimator() if estimate else None
        self.complex_estimator = _ComplexTailEstimator() if estimate else None
        self.previous: AdValue | None = None
        self.count = 0

    def observe(self, term: AdValue, acc: AdValue) -> AdValue | None:
        self.count += 1
        if not _finite(acc):
            raise NumError(f"{self.label} diverged: partial value is not finite")
        if self.previous is not None and _settled(self.previous, acc):
            return acc
        if self.estimator is not None:
            early = self._estimate(term, acc)
            if early is not None:
                return early
        self.previous = acc
        if self.count >= MAX_TERMS:
            raise NumError(f"{self.label} did not converge within {MAX_TERMS} terms")
        return None


    def _estimate(self, term: AdValue, acc: AdValue) -> AdValue | None:
        if isinstance(term, complex) or isinstance(acc, complex):
            if isinstance(term, float | complex) and isinstance(acc, float | complex):
                limit = self.complex_estimator.observe(complex(term), complex(acc))
                return None if limit is None else _inexact(limit)
            return None
        return self.estimator.observe(term, acc)


class LazySeq:
    """`\\map`/`\\filter`/`\\scan`/`\\zip`/`\\enumerate` over an infinite range or sequence:
    nothing runs until a consumer (`\\take`, a fold) iterates. Always unbounded — a filter
    that stops matching is cut off at MAX_TERMS elements rather than looping forever.
    A `zip` source is the tuple of its infinite arguments."""

    def __init__(self, kind: str, fn: Any, source: Any, seed: tuple = ()):
        self.kind, self.fn, self.source, self.seed = kind, fn, source, seed

    def __iter__(self):
        if self.kind == "map":
            for x in self.source:
                yield _invoke(self.fn, (x,))
            return
        if self.kind == "zip":
            for row in zip(*self.source):
                yield ArrayValue(row)
            return
        if self.kind == "enumerate":
            for i, x in enumerate(self.source, 1):
                yield ArrayValue((i, x))
            return
        if self.kind == "scan":
            acc, started = (self.seed[0], True) if self.seed else (None, False)
            for x in self.source:
                acc = _invoke(self.fn, (acc, x)) if started else x
                started = True
                yield acc
            return
        gap = 0
        for x in self.source:
            if _keeps(self.fn, x):
                gap = 0
                yield x
            else:
                gap += 1
                if gap >= MAX_TERMS:
                    raise NumError(f"\\filter found no match within {MAX_TERMS} elements")

    @staticmethod
    def _source_text(source: Any) -> str:
        return (source.text() if isinstance(source, LazySeq)
                else nshow(source)[len("<range "):-len(" (lazy, infinite)>")])

    def text(self) -> str:
        if self.kind == "zip":
            return f"\\zip({', '.join(map(self._source_text, self.source))})"
        if self.kind == "enumerate":
            return f"\\enumerate({self._source_text(self.source)})"
        source = self._source_text(self.source)
        seed = "".join(f", {nshow(v)}" for v in self.seed)
        return f"\\{self.kind}({_callable_label(self.fn)}, {source}{seed})"


def _is_infinite(value: Any) -> bool:
    return isinstance(value, LazySeq) or (isinstance(value, RangeValue) and value.end is None)


def _keeps(predicate: Any, x: Any) -> bool:
    keep = _invoke(predicate, (x,))
    if not isinstance(keep, bool):
        raise NumError(f"\\filter needs a boolean from its predicate, got {nshow(keep)}")
    return keep


def _elements(value: Any) -> Any:
    """The elements a range or collection iterates (tensors by outer slice), or
    None when the value is not iterable."""
    if isinstance(value, SymbolicSetValue):
        raise NumError("symbolic sets cannot be enumerated")
    if isinstance(value, RangeValue | LazySeq):
        return value
    if isinstance(value, TensorValue):
        return tn.slices(value)
    if isinstance(value, ArrayValue | SetValue):
        return value.items
    return None


def _finite_elements(value: Any, label: str) -> list:
    items = _elements(value)
    if items is None:
        raise NumError(f"{label} needs a range or collection, got {nshow(value)}")
    if _is_infinite(value):
        raise NumError(f"{label} cannot iterate an infinite range or sequence")
    return list(items)


def _rebuild(source: Any, results: list, label: str) -> Any:
    """Collect results in the kind of collection they came from."""
    if isinstance(source, TensorValue):
        if not results:
            raise NumError(f"{label} left no slices; a tensor cannot be empty")
        for r in results:
            if not isinstance(r, TensorValue):
                _reject_non_numeric(r)
        try:
            result = tn.stack(results)
            units.dimensions(result)
            return result
        except TensorError as e:
            raise NumError(f"{label}: {e.args[0]}") from None
    if isinstance(source, SetValue):
        return SetValue(_dedup(results))
    return ArrayValue(tuple(results))


def _takes(name: str, args: tuple, low: int, high: int, usage: str) -> None:
    if not low <= len(args) <= high:
        raise NumError(f"\\{name} takes {usage}")


def _lazy(kind: str, fn: Any, source: Any) -> LazySeq:
    if not callable(fn):
        raise NumError(f"{nshow(fn)} is not a function")
    return LazySeq(kind, fn, source)


def _take_call(*args: Any) -> Any:
    _takes("take", args, 2, 2, "a count and a collection")
    n, xs = args
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise NumError(f"\\take needs a non-negative exact integer count, got {nshow(n)}")
    items = _elements(xs)
    if items is None:
        raise NumError(f"\\take needs a range or collection, got {nshow(xs)}")
    return _rebuild(xs, list(islice(items, n)), "\\take")


def _map_call(*args: Any) -> Any:
    _takes("map", args, 2, 2, "a function and a collection")
    f, xs = args
    if _is_infinite(xs):
        return _lazy("map", f, xs)
    items = _finite_elements(xs, "\\map")
    return _rebuild(xs, [_invoke(f, (x,)) for x in items], "\\map")


def _filter_call(*args: Any) -> Any:
    _takes("filter", args, 2, 2, "a predicate and a collection")
    p, xs = args
    if _is_infinite(xs):
        return _lazy("filter", p, xs)
    kept = [x for x in _finite_elements(xs, "\\filter") if _keeps(p, x)]
    return _rebuild(xs, kept, "\\filter")


def _fold_infinite(f: Any, xs: Any, seed: list) -> Any:
    """`\\fold` over an infinite input: float-tier partials under the binders' convergence
    rule (`_InfiniteFold`); only `+` gets the sum tail estimate."""
    progress = _InfiniteFold("\\fold", estimate=f is OPERATORS["add"])
    items = iter(xs)
    acc = _as_inexact(seed[0]) if seed else _as_inexact(next(items))
    for x in items:
        x = _as_inexact(x)
        acc = _as_inexact(_invoke(f, (acc, x)))
        limit = progress.observe(x, acc)
        if limit is not None:
            return limit
    raise NumError("\\fold ran out of elements")


def _fold_call(*args: Any) -> Any:
    _takes("fold", args, 2, 3, "a function, a collection, and an optional seed")
    f, xs, *seed = args
    if _is_infinite(xs):
        return _fold_infinite(f, xs, seed)
    items = _finite_elements(xs, "\\fold")
    if seed:
        acc = seed[0]
    elif items:
        acc, items = items[0], items[1:]
    else:
        raise NumError("\\fold of an empty collection needs a seed")
    for x in items:
        acc = _invoke(f, (acc, x))
    return acc


def _scan_call(*args: Any) -> Any:
    _takes("scan", args, 2, 3, "a function, a collection, and an optional seed")
    f, xs, *seed = args
    if not callable(f):
        raise NumError(f"{nshow(f)} is not a function")
    if _is_infinite(xs):
        return LazySeq("scan", f, xs, tuple(seed))
    items = _finite_elements(xs, "\\scan")
    if not seed and not items:
        raise NumError("\\scan of an empty collection needs a seed")
    return _rebuild(xs, list(LazySeq("scan", f, items, tuple(seed))), "\\scan")


PRELUDE.update({
    "map": PreludeFn("map", _map_call),
    "filter": PreludeFn("filter", _filter_call),
    "fold": PreludeFn("fold", _fold_call),
    "take": PreludeFn("take", _take_call),
    "scan": PreludeFn("scan", _scan_call),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)


def _integral(v: AdValue, kind: str) -> AdValue:
    """`\\floor`/`\\ceil`/`\\trunc`/`\\round` of a real value: exact tiers give an exact
    integer, a float gives a float (non-finite floats pass through)."""
    _reject_non_numeric(v)
    if _is_complex(v):
        raise NumError(f"\\{kind} needs a real number, got {nshow(v)}")
    if isinstance(v, float):
        return float(_round_real(kind, Fraction(v))) if math.isfinite(v) else v
    if isinstance(v, int):
        return v
    if isinstance(v, Fraction):
        return _round_real(kind, v)
    sign = -1 if bool(v.expr < 0) else 1
    match kind:
        case "floor":
            return int(sympy.floor(v.expr))
        case "ceil":
            return int(sympy.ceiling(v.expr))
        case "trunc":
            return int(sympy.floor(v.expr) if sign > 0 else sympy.ceiling(v.expr))
        case _:
            return sign * int(sympy.floor(sign * v.expr + sympy.Rational(1, 2)))


def _round_real(kind: str, v: Fraction) -> int:
    n, d = v.numerator, v.denominator
    match kind:
        case "floor":
            return n // d
        case "ceil":
            return -(-n // d)
        case "trunc":
            return int(v)
        case _:
            return (1 if n >= 0 else -1) * ((2 * abs(n) + d) // (2 * d))


def _round_call(*args: AdValue) -> AdValue:
    _takes("round", args, 1, 2, "a value and optional digits: \\round(x, n)")
    x, *digits = args
    if not digits:
        return _integral(x, "round")
    n = _integer_exponent(digits[0]) if not isinstance(digits[0], bool) else None
    if n is None:
        raise NumError(f"\\round needs an exact integer digit count, got {nshow(digits[0])}")
    if isinstance(x, float) and math.isfinite(x):
        return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-n), rounding="ROUND_HALF_UP"))
    scale = Fraction(10) ** n
    return ndiv(_integral(nmul(x, scale), "round"), scale)


def _simplified(v: AdValue) -> AdValue:
    """An algebraic or RRA result simplified, back in the lowest tier that holds it."""
    if not isinstance(v, algebraic.Algebraic | rra.RRA):
        return v
    try:
        return _sympy_to_ad(rra.simplify(v), "value")
    except NumError:
        return v


def _abs_call(v: AdValue) -> AdValue:
    if isinstance(v, Quantity | UnitValue):
        return units.unary(v, _abs_call)
    if isinstance(v, TensorValue):
        return PRELUDE["det"](v)
    _reject_non_numeric(v)
    if isinstance(v, complex):
        return abs(v)
    if _is_complex(v):
        return _simplified(npow(nadd(nmul(_re_call(v), _re_call(v)),
                                     nmul(_im_call(v), _im_call(v))), Fraction(1, 2)))
    return nneg(v) if ncompare("lt", v, 0) else v


def _sign_call(v: AdValue) -> AdValue:
    _reject_non_numeric(v)
    if _is_complex(v):
        raise NumError(f"\\sign needs a real number, got {nshow(v)}")
    if isinstance(v, float):
        return v if math.isnan(v) else float((v > 0) - (v < 0))
    return (ncompare("gt", v, 0)) - (ncompare("lt", v, 0))


PRELUDE.update({
    "floor": PreludeFn("floor", lambda v: _integral(v, "floor")),
    "ceil": PreludeFn("ceil", lambda v: _integral(v, "ceil")),
    "trunc": PreludeFn("trunc", lambda v: _integral(v, "trunc")),
    "round": PreludeFn("round", _round_call),
    "abs": PreludeFn("abs", _abs_call),
    "sign": PreludeFn("sign", _sign_call),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)


MAX_FACTOR = 10**18
MAX_FIB = 1_000_000


def _exact_int(v: AdValue, label: str) -> int:
    n = _integer_exponent(v) if not isinstance(v, bool) else None
    if n is None:
        raise NumError(f"{label} needs an exact integer, got {nshow(v)}")
    return n


def ncongruent(a: AdValue, b: AdValue, modulus: AdValue) -> bool:
    a, b, modulus = (_exact_int(value, "congruence") for value in (a, b, modulus))
    if modulus == 0:
        raise NumError("congruence needs a nonzero modulus")
    return (a - b) % modulus == 0


def _congruent_call(*args: AdValue) -> bool:
    _takes("congruent", args, 3, 3, "three arguments: a, b, modulus")
    return ncongruent(*args)


def _exact_rational(v: AdValue, label: str) -> Fraction:
    if isinstance(v, bool) or not isinstance(v, int | Fraction):
        raise NumError(f"{label} needs an exact rational, got {nshow(v)}")
    return Fraction(v)


def _number_args(args: tuple, label: str) -> list[AdValue]:
    """Values given as arguments or as one collection: `\\gcd(12, 18)`, `\\gcd(⟨12, 18⟩)`."""
    items = list(args)
    if len(args) == 1 and _elements(args[0]) is not None:
        items = _finite_elements(args[0], label)
    if not items:
        raise NumError(f"{label} needs at least one rational")
    return items


def _rational_args(items: list[AdValue], label: str) -> list[Fraction]:
    return [_exact_rational(v, label) for v in items]


def _gaussian_pair(v: AdValue, label: str) -> tuple[Fraction, Fraction]:
    """A Gaussian rational as a (re, im) pair."""
    if isinstance(v, bool) or not isinstance(v, int | Fraction | Gaussian):
        raise NumError(f"{label} needs Gaussian rationals, got {nshow(v)}")
    re, im = (v.re, v.im) if isinstance(v, Gaussian) else (v, 0)
    return Fraction(re), Fraction(im)


def _gcd_call(*args: AdValue) -> AdValue:
    items = _number_args(args, "\\gcd")
    if any(isinstance(v, Gaussian) for v in items):
        return gauss.gcd_q(*(_gaussian_pair(v, "\\gcd") for v in items))
    qs = _rational_args(items, "\\gcd")
    return _normalize(Fraction(math.gcd(*(q.numerator for q in qs)),
                               math.lcm(*(q.denominator for q in qs))))


def _lcm_call(*args: AdValue) -> AdValue:
    items = _number_args(args, "\\lcm")
    if any(isinstance(v, Gaussian) for v in items):
        return gauss.lcm_q(*(_gaussian_pair(v, "\\lcm") for v in items))
    qs = _rational_args(items, "\\lcm")
    return _normalize(Fraction(math.lcm(*(q.numerator for q in qs)),
                               math.gcd(*(q.denominator for q in qs))))


def _divmod_call(*args: AdValue) -> ArrayValue:
    _takes("divmod", args, 2, 2, "a dividend and a divisor")
    a, b = args
    return ArrayValue((_integral(ndiv(a, b), "floor"), nmod(a, b)))


def _isprime_call(n: AdValue) -> bool:
    return bool(sympy.isprime(_exact_int(n, "\\isprime")))


def _factor_gaussian(n: Gaussian) -> ArrayValue:
    q = _gaussian_pair(n, "\\factor")
    d, ((wr, wi),) = gauss.scaled(q)
    if d > MAX_FACTOR or wr * wr + wi * wi > MAX_FACTOR:
        raise NumError(f"\\factor is limited to arguments up to {MAX_FACTOR}")
    return ArrayValue(tuple(ArrayValue((p, k)) for p, k in gauss.factor_q(*q)))


def _factor_call(n: AdValue, *, dimensions=None) -> ArrayValue | ExpressionValue:
    if isinstance(n, ExpressionValue | AdFunction):
        return _symbolic_factor(n, dimensions=dimensions)
    if dimensions is not None:
        raise NumError("dimension annotations require an expression or function")
    if isinstance(n, Gaussian):
        return _factor_gaussian(n)
    q = _exact_rational(n, "\\factor")
    if q <= 0:
        raise NumError(f"\\factor needs a positive rational, got {nshow(n)}")
    if max(q.numerator, q.denominator) > MAX_FACTOR:
        raise NumError(f"\\factor is limited to arguments up to {MAX_FACTOR}")
    exponents = {p: k for p, k in sympy.factorint(q.numerator).items()}
    exponents.update({p: -k for p, k in sympy.factorint(q.denominator).items()})
    return ArrayValue(tuple(ArrayValue((int(p), k)) for p, k in sorted(exponents.items())))


def _count_call(name: str, fn: Callable[[int, int], int]) -> PreludeFn:
    def call(*args: AdValue) -> int:
        _takes(name, args, 2, 2, "n and k")
        n, k = (_exact_int(v, f"\\{name}") for v in args)
        if n < 0 or k < 0:
            raise NumError(f"\\{name} needs non-negative integers")
        if n > MAX_FACTORIAL:
            raise NumError(f"\\{name} is limited to arguments up to {MAX_FACTORIAL}")
        return fn(n, k)
    return PreludeFn(name, call)


def _fib_call(n: AdValue) -> int:
    n = _exact_int(n, "\\fib")
    if n < 0:
        raise NumError(f"\\fib needs a non-negative integer, got {n}")
    if n > MAX_FIB:
        raise NumError(f"\\fib is limited to arguments up to {MAX_FIB}")
    return int(sympy.fibonacci(n))


_symbolic_factor = _rewrite_call("factor", sympy.factor).fn


PRELUDE.update({
    "simplify": _rewrite_call("simplify", sympy.simplify),
    "expand": _rewrite_call("expand", sympy.expand),
    "solve": PreludeFn("solve", _solve_call),
    "deriv": PreludeFn("deriv", _deriv_call),
    "grad": PreludeFn("grad", _grad_call),
    "jacobian": _matrix_derivative_call("jacobian"),
    "hessian": _matrix_derivative_call("hessian"),
    "tensor": PreludeFn("tensor", _tensor_call),
    "congruent": PreludeFn("congruent", _congruent_call),
    "gcd": PreludeFn("gcd", _gcd_call),
    "lcm": PreludeFn("lcm", _lcm_call),
    "divmod": PreludeFn("divmod", _divmod_call),
    "isprime": PreludeFn("isprime", _isprime_call),
    "factor": PreludeFn("factor", _factor_call),
    "choose": _count_call("choose", math.comb),
    "perm": _count_call("perm", math.perm),
    "fib": PreludeFn("fib", _fib_call),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)


def _binary_fn(name: str, float_fn: Callable, usage: str) -> Callable:
    """A two-argument exact function (`\\atan2`, `\\log`): exact and symbolic arguments
    go through the symbolic tier, anything it cannot hold through the RRA tier, and
    the float tier only when the value is not an established real."""
    def call(*args: AdValue) -> AdValue:
        _takes(name, args, 2, 2, usage)
        _reject_non_numeric(*args)
        if any(_is_complex(v) for v in args):
            raise NumError(f"\\{name} needs real arguments")
        if any(isinstance(v, float) for v in args):
            return float_fn(*(_to_float(v) for v in args))
        try:
            if not any(isinstance(v, (Algebraic, RRA)) for v in args):
                try:
                    return symbolic.apply(name, *args)
                except Unrepresentable:
                    pass
            return rra.apply(name, *args)
        except (DomainError, rra.DomainError) as e:
            raise NumError(e.args[0])
        except rra.Unrepresentable:
            return float_fn(*(_to_float(v) for v in args))
    return call


def _rational_log(b: AdValue, x: AdValue) -> Fraction | None:
    """`log_b x` when both are positive rationals whose prime factorizations are
    proportional (`\\log(1/2, 8)` is `-3`), else None."""
    if not all(isinstance(v, (int, Fraction)) and v > 0 for v in (b, x)) or b == 1:
        return None
    if max(Fraction(v).numerator * Fraction(v).denominator for v in (b, x)) > MAX_FACTOR:
        return None

    def exponents(v: int | Fraction) -> dict[int, int]:
        v = Fraction(v)
        top, bottom = sympy.factorint(v.numerator), sympy.factorint(v.denominator)
        return {p: top.get(p, 0) - bottom.get(p, 0) for p in top.keys() | bottom.keys()}

    eb, ex = exponents(b), exponents(x)
    pivot = next(p for p, e in eb.items() if e)
    ratio = Fraction(ex.get(pivot, 0), eb[pivot])
    if all(ex.get(p, 0) == ratio * eb.get(p, 0) for p in eb.keys() | ex.keys()):
        return ratio
    return None


_ln = _prelude_fn("ln", math.log)
_log_pair = _binary_fn("log", lambda b, x: math.log(x, b), "a base and a value: \\log(b, x)")


def _log_call(*args: AdValue) -> AdValue:
    if len(args) == 1:
        return _ln(*args)
    if len(args) == 2 and any(_is_complex(v) for v in args):
        _reject_non_numeric(*args)
        return ndiv(_ln(args[1]), _ln(args[0]))
    ratio = _rational_log(*args) if len(args) == 2 else None
    return _normalize(ratio) if ratio is not None else _log_pair(*args)


PRELUDE.update({
    "exp": _prelude_fn("exp", math.exp),
    "sinh": _prelude_fn("sinh", math.sinh),
    "cosh": _prelude_fn("cosh", math.cosh),
    "tanh": _prelude_fn("tanh", math.tanh),
    "asinh": _prelude_fn("asinh", math.asinh),
    "acosh": _prelude_fn("acosh", math.acosh),
    "atanh": _prelude_fn("atanh", math.atanh),
    "gamma": _prelude_fn("gamma", math.gamma),
    "erf": _prelude_fn("erf", math.erf),
    "atan2": PreludeFn("atan2", _binary_fn("atan2", math.atan2, "y and x: \\atan2(y, x)")),
    "log": PreludeFn("log", _log_call),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)

_INVERSE_PAIRS = (("sin", "asin"), ("cos", "acos"), ("tan", "atan"), ("exp", "ln"),
                  ("sinh", "asinh"), ("cosh", "acosh"), ("tanh", "atanh"))
_INVERSES = {id(PRELUDE[f]): PRELUDE[g] for f, g in _INVERSE_PAIRS} | \
            {id(PRELUDE[g]): PRELUDE[f] for f, g in _INVERSE_PAIRS}


def _values(args: tuple, label: str) -> list:
    """Values given as arguments or as one collection: `\\max(1, 5)`, `\\max(⟨1, 5⟩)`."""
    items = _finite_elements(args[0], label) if len(args) == 1 and _elements(args[0]) is not None \
        else list(args)
    if not items:
        raise NumError(f"{label} needs at least one value")
    return items


def _numbers(args: tuple, label: str) -> list:
    items = _values(args, label)
    _reject_non_numeric(*items)
    return items


def _sorted(items: list) -> list:
    return sorted(items, key=functools.cmp_to_key(
        lambda a, b: -1 if ncompare("lt", a, b) else 1 if ncompare("gt", a, b) else 0))


def _extreme(name: str, op: str) -> PreludeFn:
    def call(*args: AdValue) -> AdValue:
        best, *rest = _numbers(args, f"\\{name}")
        for v in rest:
            if ncompare(op, v, best):
                best = v
        return best
    return PreludeFn(name, call)


def _mean(items: list) -> AdValue:
    return ndiv(functools.reduce(nadd, items), len(items))


def _mean_call(*args: AdValue) -> AdValue:
    return _mean(_numbers(args, "\\mean"))


def _median_call(*args: AdValue) -> AdValue:
    items = _sorted(_numbers(args, "\\median"))
    mid = len(items) // 2
    return items[mid] if len(items) % 2 else _mean(items[mid - 1:mid + 1])


def _deviation(name: str, sample: bool) -> PreludeFn:
    def call(*args: AdValue) -> AdValue:
        items = _numbers(args, f"\\{name}")
        if sample and len(items) < 2:
            raise NumError(f"\\{name} needs at least two values")
        mean = _mean(items)
        spread = functools.reduce(nadd, (npow(nsub(v, mean), 2) for v in items))
        return npow(ndiv(spread, len(items) - sample), Fraction(1, 2))
    return PreludeFn(name, call)


def _sort_call(xs: AdValue) -> AdValue:
    items = _sorted(_finite_elements(xs, "\\sort"))
    return _rebuild(ArrayValue(()) if isinstance(xs, SetValue) else xs, items, "\\sort")


def _reverse_call(xs: AdValue) -> AdValue:
    if isinstance(xs, SetValue):
        raise NumError("\\reverse needs an ordered collection; a set has no order")
    return _rebuild(xs, _finite_elements(xs, "\\reverse")[::-1], "\\reverse")


def _tested(predicate: Any, x: Any, label: str) -> bool:
    result = _invoke(predicate, (x,))
    if not isinstance(result, bool):
        raise NumError(f"{label} needs a boolean from its predicate, got {nshow(result)}")
    return result


def _search(label: str, predicate: Any, xs: Any, stop_on: bool) -> bool:
    """The first element whose test equals `stop_on` ends `\\any`/`\\all`; an infinite
    input with no such element is undecided after MAX_TERMS elements."""
    items = _elements(xs)
    if items is None:
        raise NumError(f"{label} needs a range or collection, got {nshow(xs)}")
    for seen, x in enumerate(items, 1):
        if _tested(predicate, x, label) == stop_on:
            return True
        if seen >= MAX_TERMS:
            raise NumError(f"{label} undecided within {MAX_TERMS} elements")
    return False


def _any_call(*args: Any) -> bool:
    _takes("any", args, 2, 2, "a predicate and a collection")
    return _search("\\any", args[0], args[1], True)


def _all_call(*args: Any) -> bool:
    _takes("all", args, 2, 2, "a predicate and a collection")
    return not _search("\\all", args[0], args[1], False)


def _count_matches_call(*args: Any) -> int:
    _takes("count", args, 2, 2, "a predicate and a collection")
    p, xs = args
    return sum(_tested(p, x, "\\count") for x in _finite_elements(xs, "\\count"))


def _zip_call(*args: Any) -> Any:
    if len(args) < 2:
        raise NumError("\\zip takes two or more collections")
    if all(_is_infinite(xs) for xs in args):
        return LazySeq("zip", None, args)
    columns = [None if _is_infinite(xs) else _finite_elements(xs, "\\zip") for xs in args]
    length = min(len(c) for c in columns if c is not None)
    columns = [islice(xs, length) if c is None else c for xs, c in zip(args, columns)]
    return ArrayValue(tuple(ArrayValue(row) for row in zip(*columns)))


def _enumerate_call(xs: Any) -> Any:
    if _is_infinite(xs):
        return LazySeq("enumerate", None, xs)
    items = _finite_elements(xs, "\\enumerate")
    return ArrayValue(tuple(ArrayValue((i, x)) for i, x in enumerate(items, 1)))


PRELUDE.update({
    "min": _extreme("min", "lt"),
    "max": _extreme("max", "gt"),
    "mean": PreludeFn("mean", _mean_call),
    "median": PreludeFn("median", _median_call),
    "stdev": _deviation("stdev", sample=False),
    "sstdev": _deviation("sstdev", sample=True),
    "sort": PreludeFn("sort", _sort_call),
    "reverse": PreludeFn("reverse", _reverse_call),
    "any": PreludeFn("any", _any_call),
    "all": PreludeFn("all", _all_call),
    "count": PreludeFn("count", _count_matches_call),
    "zip": PreludeFn("zip", _zip_call),
    "enumerate": PreludeFn("enumerate", _enumerate_call),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)


def _conj_call(v: AdValue) -> AdValue:
    _reject_non_numeric(v)
    if isinstance(v, complex):
        return v.conjugate()
    return nsub(_re_call(v), nmul(_im_call(v), PRELUDE["i"])) if _is_complex(v) else v


def _arg_call(v: AdValue) -> AdValue:
    _reject_non_numeric(v)
    if isinstance(v, (int, Fraction)) and v == 0:
        raise NumError("\\arg is not defined at zero")
    return _simplified(PRELUDE["atan2"](_im_call(v), _re_call(v)))


PRELUDE.update({
    "conj": PreludeFn("conj", _conj_call),
    "arg": PreludeFn("arg", _arg_call),
    "polar": PreludeFn("polar", lambda *a: (_takes("polar", a, 2, 2, "a radius and an angle"), npolar(*a))[1]),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)


def _linalg(f: Callable, *args: Any) -> Any:
    try:
        return f(*args)
    except TensorError as e:
        raise NumError(e.args[0]) from e


def _validate_matrix(rows: list[list]) -> None:
    for row in rows:
        for value in row:
            if _is_inexact(value) and not cmath.isfinite(value):
                raise NumError("matrix elimination needs finite numeric entries")


def _numerical_matrix(name: str, rows: list[list], right: list[list] | None = None):
    _validate_matrix(rows)
    if right is not None:
        _validate_matrix(right)
    try:
        coefficients = [[_to_complex(v) for v in row] for row in rows]
        rhs = None if right is None else [[_to_complex(v) for v in row] for row in right]
    except (OverflowError, ValueError, TypeError) as error:
        raise NumError("matrix elimination cannot convert entries to finite floats") from error
    result = matrix_numeric.compute(name, coefficients, rhs)
    if isinstance(result, list):
        return [[_inexact(complex(v)) for v in row] for row in result]
    return result if isinstance(result, int) else _inexact(complex(result))


_SCALARS = linalg.Scalars(nadd, nsub, nmul, ndiv, lambda v: neq(v, 0),
                         _is_inexact, _validate_matrix, _numerical_matrix)


def _eigen_records(spaces: list[tuple], convert: Callable) -> ArrayValue:
    records = []
    for value, multiplicity, columns in spaces:
        n, k = len(columns[0]), len(columns)
        basis = TensorValue((n, k), tuple(convert(columns[c][r])
                                         for r in range(n) for c in range(k)))
        records.append(ArrayValue((convert(value), int(multiplicity), basis)))
    return ArrayValue(tuple(records))


def _exact_eig(t: TensorValue) -> ArrayValue:
    rows = linalg._square(t, "\\eig")
    spaces = eigen.exact([[value_to_sympy(v) for v in row] for row in rows])
    return _eigen_records(spaces, lambda v: _sympy_to_ad(v, "exact eigenvalue or eigenvector entry"))


def _eig_call(*args: AdValue) -> ArrayValue:
    from . import rewrite

    _takes("eig", args, 1, 1, "1 argument")
    t = args[0]
    if units.dimensions(t) != units.DIMENSIONLESS:
        raise NumError("dimensioned eigensystems are unsupported")
    t, _ = units.strip(t)
    rows = _linalg(linalg._square, t, "\\eig")
    _linalg(linalg._size, t.shape)
    for value in t.items:
        _reject_non_numeric(value)
    if any(_is_inexact(value) for value in t.items):
        try:
            converted = [[_to_complex(v) for v in row] for row in rows]
        except (OverflowError, ValueError, TypeError) as error:
            raise NumError("\\eig cannot convert entries to finite floats") from error
        return _eigen_records(_linalg(eigen.numerical, converted), _inexact)
    try:
        return _linalg(rewrite.run_limited, _exact_eig, t)
    except rewrite.RewriteError as error:
        raise NumError(f"\\eig {error}") from None


def _norm_call(v: AdValue) -> AdValue:
    if not isinstance(v, TensorValue):
        return _abs_call(v)
    v, dims = units.strip(v)
    total = 0
    for item in v.items:
        total = nadd(total, nmul(item, _conj_call(item)))
    return units.attach(npow(total, Fraction(1, 2)), dims)


def _dims(args: tuple, label: str) -> list[int]:
    return [_exact_int(d, label) for d in args]


def _reshape_call(t: AdValue, *dims: AdValue) -> AdValue:
    return _linalg(linalg.reshape, t, _dims(dims, "\\reshape"))


def _concat_call(*parts: AdValue) -> AdValue:
    _takes("concat", parts, 2, math.inf, "two or more tensors or arrays")
    result = _linalg(linalg.concat, list(parts))
    units.dimensions(result)
    return result


def _stack_call(*parts: AdValue) -> AdValue:
    _takes("stack", parts, 1, math.inf, "one or more numbers or equal-shape tensors")
    for part in parts:
        if not isinstance(part, TensorValue):
            _reject_non_numeric(part)
    result = _linalg(tn.stack, list(parts))
    units.dimensions(result)
    return result


def _fill_call(name: str, value: int) -> PreludeFn:
    return PreludeFn(name, lambda *dims: _linalg(linalg.filled, value, _dims(dims, f"\\{name}")))


def _matrix_fn(name: str, f: Callable, arity: int, scalars: bool = True) -> PreludeFn:
    def call(*args: AdValue) -> AdValue:
        _takes(name, args, arity, arity, f"{arity} argument{'s' * (arity > 1)}")
        stripped = [units.strip(v) for v in args]
        values = [value for value, _ in stripped]
        dims = [dimension for _, dimension in stripped]
        result = _linalg(f, _SCALARS, *values) if scalars else _linalg(f, *values)
        if name == "det":
            dimension = units.power(dims[0], args[0].shape[0])
        elif name == "inv":
            dimension = units.power(dims[0], -1)
        elif name == "linsolve":
            dimension = units.combine(dims[1], dims[0], -1)
        elif name in {"rank", "rref"}:
            dimension = units.DIMENSIONLESS
        elif len(dims) == 2:
            dimension = units.combine(*dims)
        else:
            dimension = dims[0]
        return units.attach(result, dimension)
    return PreludeFn(name, call)


PRELUDE.update({
    "eig": PreludeFn("eig", _eig_call),
    "det": _matrix_fn("det", linalg.det, 1),
    "inv": _matrix_fn("inv", linalg.inv, 1),
    "tr": _matrix_fn("tr", linalg.trace, 1),
    "rank": _matrix_fn("rank", linalg.rank, 1),
    "rref": _matrix_fn("rref", linalg.rref, 1),
    "linsolve": _matrix_fn("linsolve", linalg.linsolve, 2),
    "kron": _matrix_fn("kron", linalg.kron, 2),
    "outer": _matrix_fn("outer", linalg.outer, 2),
    "cross": _matrix_fn("cross", linalg.cross, 2),
    "eye": PreludeFn("eye", lambda n: _linalg(linalg.eye, _exact_int(n, "\\eye"))),
    "zeros": _fill_call("zeros", 0),
    "ones": _fill_call("ones", 1),
    "diag": _matrix_fn("diag", linalg.diag, 1, scalars=False),
    "norm": PreludeFn("norm", _norm_call),
    "reshape": PreludeFn("reshape", _reshape_call),
    "concat": PreludeFn("concat", _concat_call),
    "stack": PreludeFn("stack", _stack_call),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)


PRELUDE.update(units.catalogue())
PRELUDE.update({
    "convert": PreludeFn("convert", units.convert),
    "magnitude": PreludeFn("magnitude", units.extract),
    "unit": PreludeFn("unit", units.make_unit),
})
_PRELUDE_PROTECTED = frozenset(PRELUDE)


class Engine:
    """Everything lowered code calls into. Holds the user environment (a plain dict) and
    the compiled unit's span table; every method takes the span id of the node that
    emitted it so failures carry narrow spans. Formatted statement results accumulate in
    `outputs` in evaluation order — the REPL prints only the last, script mode echoes all
    (matching main.rs's run_and_echo vs repl.rs)."""

    def __init__(self, env: dict[str, Any], spans: Sequence[Span], definitions=None,
                 parent=None, modules: dict | None = None,
                 base_dir: str | None = None, import_chain: tuple[str, ...] = (),
                 quotes: dict[int, ExpressionValue] | None = None):
        self.env = env
        self.spans = spans
        self.definitions = definitions or {}
        self.quotes = quotes or {}
        self.parent = parent
        # The session's module registry (absolute path -> module environment) and the
        # directory relative to which `\import` resolves files. Both ride on the root
        # engine and are inherited by every child frame and imported module engine.
        self.modules = modules if modules is not None else {}
        self.base_dir = base_dir
        # Absolute paths of modules currently being evaluated up the import stack —
        # what a circular-import error names.
        self.import_chain = import_chain
        self.outputs: list[str] = []
        self.result: Any = None

    def _fail(self, msg: str, sid: int, *, domain: bool = False) -> NoReturn:
        raise EvalError(msg, self.spans[sid], domain=domain)

    def quote(self, sid: int) -> ExpressionValue:
        return self.quotes[sid]

    def eval_expr(self, value: Any, names: tuple[str, ...], values: tuple[Any, ...],
                  spellings: tuple[str | None, ...], sid: int) -> Any:
        for name, spelling in zip(names, spellings):
            if self._protected(name):
                self._fail(f"`{_display_name(name, spelling)}` is protected", sid)
        if isinstance(value, ArrayValue):
            def validate(part):
                if isinstance(part, ArrayValue):
                    for item in part.items:
                        validate(item)
                elif not isinstance(part, ExpressionValue):
                    self._fail("`\\eval` needs expression values at every array leaf", sid)
            validate(value)
            return ArrayValue(tuple(self.eval_expr(item, names, values, spellings, sid)
                                    for item in value.items))
        if not isinstance(value, ExpressionValue):
            self._fail("`\\eval` needs an expression value", sid)
        provided = dict(zip(names, values))
        for name, dimension in value.dimensions:
            binding = provided.get(name, self._lookup(name))
            if binding is not _MISSING and units.dimensions(binding) != dimension:
                self._fail(f"conflicting dimensions for {name}", sid)
        from .compiler import _compile_body, compile_expression

        body = (_compile_body(value.node, value.source) if value.statement_body
                else compile_expression(value.node, value.source))
        child = Engine(dict(zip(names, values)), body.spans, body.definitions, self,
                       self.modules, self.base_dir, self.import_chain, quotes=body.quotes)
        scope = {"_e": child}
        try:
            exec(body.code, scope)
        except EvalError as e:
            if e.source is None and value.source:
                e.source = value.source
            raise
        return scope["_result"]

    def lit(self, text: str, sid: int) -> AdValue:
        """A number literal's tier decision, lowered through the seam so the
        generated source never loads a bare name — exact decimals (`0.5` is
        the rational 1/2) have no source-safe Python literal. `parse_literal`
        cannot fail on lexer-valid text; the sid keeps the
        every-call-carries-a-span pattern."""
        return parse_literal(text)

    def _protected(self, name: str) -> bool:
        """Prelude names and reserved statement forms are protected everywhere. User
        bindings are immutable by the binding rule itself. Covers rebinding by `=`,
        function definition, and — at the definition/binder sites — parameters and loop
        variables. The one exception is `i`: the imaginary unit's spelling is the
        conventional loop-binder name, so it binds like any identifier and shadows
        the unit for both spellings (`i` and `\\i` read the one binding) — inside such
        a scope the unit is spelled `\\complex(0, 1)`."""
        if name in SHADOWABLE_PRELUDE:
            return False
        return name in _PRELUDE_PROTECTED or name in RESERVED_NAMES

    def _lookup(self, name: str) -> Any:
        """Walk the frame chain for `name`; the prelude sits outermost. Returns
        _MISSING instead of failing so the caller reports with its own span table —
        a parent engine's table is a different unit's and must never be indexed with
        this frame's span ids."""
        scope = self
        while scope is not None:
            if name in scope.env:
                return scope.env[name]
            scope = scope.parent
        return PRELUDE.get(name, _MISSING)

    def var(self, name: str, sid: int, spelling: str | None = None) -> AdValue:
        value = self._lookup(name)
        if value is _MISSING:
            self._fail(f"`{_display_name(name, spelling)}` is not bound", sid)
        return value

    def bref(self, name: str, sid: int, spelling: str | None = None) -> AdValue:
        label = _display_name(name, spelling)
        if name == "py":
            self._fail(f"`{label}` must be applied to a path: \\py(\"dotted.path\")", sid)
        if name == "import":
            self._fail(f"`{label}` reads an ad file: \\import(\"lib\") or "
                       "\\import(\"lib\": f)", sid)
        if name == "pyimport":
            self._fail(f"`{label}` binds Python members: "
                       "\\pyimport(\"math\": \\sqrt)", sid)
        if name == "infix":
            self._fail(f"`{label}` declares an operator at top level: "
                       "\\infix(11) \\blend(a,b) = a+b", sid)
        if name == "alias":
            self._fail(f"`{label}` declares short spellings at top level: "
                       "\\alias \\sum, σ", sid)
        if name == "dual":
            self._fail(f"`{label}` defines a name under two spellings: "
                       "\\dual \\alpha, α = 3.14", sid)
        if name == "let":
            self._fail(f"`{label}` binds a fresh name: \\let name = expr", sid)
        if name in ("expr", "eval"):
            self._fail(f"`{label}` needs a parenthesized argument", sid)
        if name in ("fn", "λ"):
            self._fail(f"`{label}` takes a parenthesized parameter list: \\λ(x) body "
                       "(ASCII spelling \\fn(x) body)", sid)
        value = self._lookup(name)
        if value is _MISSING:
            self._fail(f"`{label}` is not bound", sid)
        return value

    def define(self, name, params, sid, spelling=None, param_spellings=(), echo=True):
        param_names = _display_params(params, param_spellings)
        for p, display in zip(params, param_names):
            if self._protected(p):
                self._fail(f"`{display}` is protected", sid)
        fn = AdFunction(name, params, self.definitions[sid], self, spelling,
                        param_spellings)
        display_name = _display_name(name, spelling)
        if self._protected(name):
            self._fail(f"`{display_name}` is protected", sid)
        if self._lookup(name) is not _MISSING:
            self._fail(f"`{display_name}` is already bound", sid)
        self.env[name] = fn
        if echo:
            self.outputs.append(f"{display_name} = {nshow(fn)}")
        return fn

    def lambda_(self, params, sid, param_spellings=()):
        """`\\λ(params) body` / `\\fn(params) body` — an anonymous AdFunction closed
        over the defining frame. Parameters reject protected names exactly like
        `define`; there is no self-name to install (recursion goes through named
        defs or a fixpoint combinator), and the empty name is what nshow renders
        as `<λ(x)>`."""
        param_names = _display_params(params, param_spellings)
        for p, display in zip(params, param_names):
            if self._protected(p):
                self._fail(f"`{display}` is protected", sid)
        return AdFunction("", params, self.definitions[sid], self, "", param_spellings)

    def assign(self, name: str, value: AdValue, sid: int,
               echo: bool = False, spelling: str | None = None,
               fresh_only: bool = False) -> AdValue | bool:
        """`x = e` — declare-once-then-check, the one binding rule. A protected
        prelude name is rejected; a name already bound in the current frame compares
        by value (`1 = 1.0` is true — the tower, not the type); otherwise the name
        binds fresh into this frame. `\\let` passes `fresh_only=True`, so an existing
        current-frame binding is an error. Reads walk the chain, binds and compares
        stay frame-local, and nothing ever rebinds an existing binding. Silent in
        expression position (groups, bodies); statement-level lowering passes
        `echo=True` so the REPL/script transcript shows the outcome."""
        display_name = _display_name(name, spelling)
        if self._protected(name):
            self._fail(f"`{display_name}` is protected", sid)
        if name in self.env:
            if fresh_only:
                self._fail(f"`{display_name}` is already bound", sid)
            matches = neq(self.env[name], value)
            if echo:
                self.outputs.append("true" if matches else "false")
            return matches
        self.env[name] = value
        if echo:
            self.outputs.append(f"{display_name} = {nshow(value)}")
        return value

    def _compare(self, op, a, b, sid):
        return self._binop(lambda x, y: ncompare(op, x, y), a, b, sid)

    def lt(self, a, b, sid): return self._compare("lt", a, b, sid)
    def le(self, a, b, sid): return self._compare("le", a, b, sid)
    def gt(self, a, b, sid): return self._compare("gt", a, b, sid)
    def ge(self, a, b, sid): return self._compare("ge", a, b, sid)

    def range(self, start, second, end, sid):
        try:
            if any(isinstance(v, Quantity | UnitValue) for v in (start, second, end)):
                dimension = units.dimensions(start)
                if end is not None and units.dimensions(end) != dimension:
                    raise NumError("range endpoints must have matching dimensions")
                if second is not None:
                    raise NumError("stepped dimensioned ranges are unsupported")
                if _is_complex(start) or end is not None and _is_complex(end):
                    raise NumError("range bounds must be real numbers")
                return IntervalValue(start, units.attach(math.inf, dimension) if end is None else end)
            for name, value in (("start", start), ("end", end)):
                if value is None:
                    continue
                _reject_non_numeric(value)
                if _is_complex(value):
                    raise NumError("range bounds must be real numbers")
                if isinstance(value, float) and math.isnan(value):
                    raise NumError(f"range {name} must be a finite number or infinity")
            if any(isinstance(value, float) and math.isinf(value) for value in (start, end)):
                if second is not None:
                    raise NumError("infinite interval bounds take a plain range, not a stepped one")
                end = math.inf if end is None else end
                if neq(start, end):
                    raise NumError("interval endpoints cannot be equal infinities")
                return IntervalValue(start, end)
            if second is None:
                step = 1
            else:
                _reject_non_numeric(second)
                if _is_complex(second):
                    raise NumError("range bounds must be real numbers")
                step = nsub(second, start)
            if isinstance(step, float) and not math.isfinite(step):
                raise NumError("range step must be a finite number")
            if step == 0:
                raise NumError("range step cannot be zero")
            return RangeValue(start, step, end, second)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def _eval_bound(self, body: Any, bindings: dict[str, AdValue], label: str,
                    sid: int) -> AdValue:
        """Evaluate a compiled body once with the loop variable layered over a child
        frame. Scoping mirrors AdFunction.__call__: reads of other names fall through
        to the parent chain, writes stay local to this iteration."""
        child = Engine(bindings, body.spans, body.definitions, self,
                       self.modules, self.base_dir, self.import_chain, quotes=body.quotes)
        scope = {"_e": child}
        try:
            exec(body.code, scope)
        except EvalError:
            raise
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)
        except Exception as e:
            self._fail(f"{label} failed unexpectedly: {type(e).__name__}: {e}", sid)
        return scope["_result"]

    def fold(self, op_name: str, name: str, value: AdValue, sid: int,
             spelling: str | None = None, var_spelling: str | None = None) -> AdValue:
        """`\\sum(i=a..b) body` / `\\prod(...)`: iterate the bound RangeValue, evaluating
        the compiled body once per term in a fresh frame `{i: term}`. Finite ranges
        accumulate exactly at the lowest exact tier; lazy infinite ranges switch to the
        float tier and stop at the first of two exits — the consecutive-partial
        plateau (within CONVERGENCE_TOLERANCE, relatively scaled) or, for sums, a
        confirmed tail estimate (a shape-read limit plus a bounded claimed error,
        honored by a confirmation window) — erroring at MAX_TERMS rather than
        returning a misleading partial (docs/numerics.md). Products keep the
        plateau only (see _FoldTailEstimator)."""
        label = spelling or FOLD_LABELS.get(op_name, "\\sum")
        display_name = _display_name(name, var_spelling)
        if self._protected(name):
            self._fail(f"`{display_name}` is protected", sid)
        if isinstance(value, SymbolicSetValue):
            self._fail("symbolic sets cannot be enumerated", sid)
        items = _elements(value)
        if items is None:
            self._fail(f"{label} folds over a range or collection, got {nshow(value)}", sid)
        if op_name in ("and", "or"):
            return self._quantify(op_name == "or", name, items, _is_infinite(value), label, sid)
        fn = nmul if op_name == "mul" else nadd
        unit = 1 if op_name == "mul" else 0
        body = self.definitions[sid]
        acc: AdValue = unit
        infinite = _is_infinite(value)
        # Sums-only tail estimation (products keep the plateau — see
        # _FoldTailEstimator); finite folds never estimate.
        progress = _InfiniteFold(label, estimate=op_name == "add") if infinite else None
        first_term = True
        iterator = iter(items)
        while True:
            try:
                item = next(iterator)
                binding = _as_float(item) if infinite else item
            except StopIteration:
                break
            except NumError as e:
                self._fail(e.args[0], sid, domain=e.domain)
            term = self._eval_bound(body, {name: binding}, label, sid)
            if infinite and isinstance(term, TensorValue):
                self._fail(f"{label} over an infinite range needs numeric terms", sid)
            if infinite and isinstance(term, Quantity | UnitValue):
                self._fail("dimensioned infinite folds are unsupported", sid)
            if first_term and not infinite and op_name == "add":
                acc = term
            else:
                acc = self._binop(fn, acc, term, sid)
            first_term = False
            if progress is not None:
                try:
                    limit = progress.observe(term, acc)
                except NumError as e:
                    self._fail(e.args[0], sid, domain=e.domain)
                if limit is not None:
                    return limit
        return acc

    def _quantify(self, witness: bool, name: str, items: Any, infinite: bool, label: str,
                  sid: int) -> bool:
        """`∀`/`∃`: stop at the first body value equal to `witness` (`true` for `∃`, `false`
        for `∀`); an infinite domain with none is undecided after MAX_TERMS elements."""
        body = self.definitions[sid]
        iterator = iter(items)
        seen = 0
        while True:
            try:
                item = next(iterator)
            except StopIteration:
                return not witness
            except NumError as e:
                self._fail(e.args[0], sid, domain=e.domain)
            term = self._eval_bound(body, {name: item}, label, sid)
            if not isinstance(term, bool):
                self._fail(f"{label} needs a boolean body, got {nshow(term)}", sid)
            if term is witness:
                return witness
            seen += 1
            if infinite and seen >= MAX_TERMS:
                self._fail(f"{label} undecided within {MAX_TERMS} terms", sid)

    def limit(self, name: str, point_value: AdValue, sid: int,
              spelling: str | None = None, var_spelling: str | None = None) -> float | complex:
        """`\\lim(x=a) body`, numeric only: probe each side with geometrically shrinking
        steps — never evaluating at `a` itself; the ulp guard halts each side when a
        step would round back onto the anchor. A real anchor has two sides (right, left),
        a complex anchor eight rays: four at multiples of the golden angle and their opposites (the
        opposites cancel the first-order bias of the averaged estimate). Each side must stabilize within
        CONVERGENCE_TOLERANCE (same relatively-scaled plateau test as infinite folds)
        inside MAX_PROBES;
        sides stabilizing apart means the limit does not exist. Probes evaluate in the
        float tier like infinite-range folds (docs/numerics.md), a complex body value
        as a complex float."""
        if isinstance(point_value, Quantity | UnitValue):
            self._fail("dimensioned limits are unsupported", sid)
        label = spelling or "\\lim"
        display_name = _display_name(name, var_spelling)
        try:
            _reject_non_numeric(point_value)
            anchor = _as_inexact(point_value)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)
        if not _finite(anchor):
            self._fail(f"{label} approaches a finite point", sid)
        if self._protected(name):
            self._fail(f"`{display_name}` is protected", sid)
        body = self.definitions[sid]
        h = max(abs(anchor), 1.0) * 0.5**7  # start close enough that ~60 halvings pass any ulp floor
        directions = _RAYS if isinstance(anchor, complex) else (1.0, -1.0)
        estimates: list[float | complex] = []
        for direction in directions:  # right side first, then left
            step = h
            previous: float | complex | None = None
            estimate: float | complex | None = None
            converged = False
            for _ in range(MAX_PROBES):
                probe = anchor + direction * step
                if probe == anchor:
                    break  # step underflowed onto the anchor itself — never evaluate there
                raw = self._eval_bound(body, {name: probe}, label, sid)
                if isinstance(raw, Quantity | UnitValue):
                    self._fail("dimensioned limits are unsupported", sid)
                try:
                    estimate = _as_inexact(raw)
                except NumError as e:
                    self._fail(e.args[0], sid, domain=e.domain)
                if previous is not None and _settled(previous, estimate):
                    converged = True
                    break
                previous = estimate
                step *= 0.5
            if not converged:
                self._fail(f"{label} did not converge within {MAX_PROBES} probes", sid)
            estimates.append(estimate)
        if any(not _agree(estimates[0], other) for other in estimates[1:]):
            display_label = "limit" if label == "\\lim" else label
            self._fail(
                f"{display_label} does not exist: left and right estimates disagree", sid)
        total = estimates[0]
        for estimate in estimates[1:]:
            total = self._binop(nadd, estimate, total, sid)
        return _drop_stray_parts(self._binop(ndiv, total, len(estimates), sid))

    def diff(self, name: str, point_value: AdValue, sid: int,
             spelling: str | None = None, var_spelling: str | None = None,
             order: AdValue = 1) -> float | complex:
        """`\\diff(x=a) body`: the numeric derivative at `a` (`_ridders`); the body
        evaluates in a fresh frame holding only the loop variable, like `\\lim`."""
        label = spelling or "\\diff"
        if self._protected(name):
            self._fail(f"`{_display_name(name, var_spelling)}` is protected", sid)
        body = self.definitions[sid]
        try:
            _reject_non_numeric(point_value)
            return _numeric_derivative(
                lambda point: self._eval_bound(body, {name: point}, label, sid),
                point_value, order, label)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def graph(self, name: str, axis_spelling: str | None, label: str, target: Any,
              bound: Any, options: dict[str, Any], expression_mode: bool, sid: int,
              spelling: str | None = None) -> GraphValue:
        if self._protected(name):
            self._fail(f"`{_display_name(name, axis_spelling)}` is protected", sid)
        if not isinstance(bound, RangeValue) or bound.end is None or bound.second is not None:
            self._fail("\\graph takes a finite unstepped range a..b", sid)
        try:
            lo, hi = _as_float(bound.start), _as_float(bound.end)
            if isinstance(bound.start, bool) or isinstance(bound.end, bool) or not all(
                    math.isfinite(value) for value in (lo, hi)):
                raise NumError("\\graph bounds must be finite real scalars")
            tolerance_value = options.get("tol", DEFAULT_TOLERANCE)
            tolerance = _as_float(tolerance_value)
            if isinstance(tolerance_value, bool) or not math.isfinite(tolerance) or tolerance <= 0:
                raise NumError("\\graph tolerance must be finite and positive")
            maxpoints = _exact_int(options.get("maxpoints", DEFAULT_MAX_POINTS), "\\maxpoints")
            if maxpoints < INITIAL_POINTS:
                raise NumError(f"\\maxpoints must be at least {INITIAL_POINTS}")
            if not expression_mode and not callable(target):
                raise NumError("\\graph needs a callable or an expression using its axis")
        except NumError as error:
            self._fail(error.args[0], sid)
        body = self.definitions.get(sid)

        def evaluate(point):
            try:
                raw = (self._eval_bound(body, {name: point}, spelling or "\\graph", sid)
                       if expression_mode else self.app(target, (point,), {}, sid))
            except (NumError, EvalError) as error:
                if error.domain:
                    return None
                raise
            if isinstance(raw, bool | Quantity | UnitValue) or not isinstance(raw, _NUMERIC_TYPES):
                self._fail("\\graph samples must be real scalars", sid)
            if _is_complex(raw):
                return None
            try:
                value = _as_float(raw)
            except NumError:
                return None
            return value if math.isfinite(value) else None

        return sample_graph(evaluate, min(lo, hi), max(lo, hi), axis=name,
                            axis_spelling=_display_name(name, axis_spelling), label=label,
                            tolerance=tolerance, maxpoints=maxpoints)

    def integral(self, name: str, bound: AdValue | RangeValue | IntervalValue, sid: int,
                 spelling: str | None = None, var_spelling: str | None = None) -> float | complex:
        """Numeric integration over ranges or intervals; reversed bounds negate."""
        label = spelling or "\\int"
        if self._protected(name):
            self._fail(f"`{_display_name(name, var_spelling)}` is protected", sid)
        if not isinstance(bound, RangeValue | IntervalValue):
            self._fail(f"{label} integrates over a range a..b or a.., got {nshow(bound)}", sid)
        if isinstance(bound, RangeValue) and bound.second is not None:
            self._fail(f"{label} takes a plain range a..b, not a stepped one", sid)
        body = self.definitions[sid]
        try:
            start, dimension = units.parts(bound.start)
            end, end_dimension = units.parts(bound.end)
            if bound.end is not None and dimension != end_dimension:
                raise NumError("integral endpoints must have matching dimensions")
            lo = _as_float(start)
            hi = math.inf if bound.end is None else _as_float(end)
            for value, widened in ((start, lo), (end, hi)):
                if value is not None and not isinstance(value, float) and not math.isfinite(widened):
                    raise NumError(f"{label} bound is too large to widen to a finite float")
            sign = 1
            if hi < lo:
                lo, hi, sign = hi, lo, -1
            samples = _QuantitySamples(
                lambda point: self._eval_bound(body, {name: point}, label, sid), dimension)
            if hi == lo:
                samples(lo)
                return units.attach(0.0, units.combine(samples.output_dimensions, dimension))
            result = _quadrature(samples, lo, hi, label)
            return units.attach(-result if sign < 0 else result,
                                units.combine(samples.output_dimensions, dimension))
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def piecewise(self, conditions, values, otherwise, sid):
        """`{c: v; …}` — the first true condition's value; only that branch evaluates."""
        for condition, value in zip(conditions, values):
            holds = condition()
            if not isinstance(holds, bool):
                self._fail("piecewise condition must be boolean", sid)
            if holds:
                return _to_ad(value(), preserve_bool=True)
        if otherwise is None:
            self._fail("no piecewise case matched", sid)
        return _to_ad(otherwise(), preserve_bool=True)

    def set_builder(self, clauses, element_sid, sid):
        for name, spelling, part_sid in clauses:
            if name is not None and self._protected(name):
                self._fail(f"`{_display_name(name, spelling)}` is protected", part_sid)
        kept = []

        def visit(index, bindings):
            if index == len(clauses):
                kept.append(bindings[clauses[0][0]] if element_sid is None else
                            self._eval_bound(self.definitions[element_sid], bindings,
                                             "set-builder", element_sid))
                return
            name, spelling, part_sid = clauses[index]
            value = self._eval_bound(self.definitions[part_sid], bindings, "set-builder", part_sid)
            if name is None:
                if not isinstance(value, bool):
                    self._fail(f"set-builder guards must be boolean, got {nshow(value)}", part_sid)
                if value:
                    visit(index + 1, bindings)
                return
            if isinstance(value, SymbolicSetValue):
                self._fail("symbolic sets cannot be enumerated", part_sid)
            items = _elements(value)
            if items is None:
                self._fail(f"set-builder ranges over a range or collection, got {nshow(value)}", part_sid)
            if _is_infinite(value):
                self._fail("set-builder cannot range over an infinite range or sequence", part_sid)
            for item in items:
                visit(index + 1, {**bindings, name: item})

        try:
            visit(0, {})
            return SetValue(_dedup(kept))
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def tensor(self, items, row_length, sid):
        try:
            dimensions = [units.dimensions(v) for v in items]
            if dimensions and any(d != dimensions[0] for d in dimensions):
                raise NumError("tensor entries must have matching dimensions")
            for item in items:
                if not isinstance(item, TensorValue):
                    _reject_non_numeric(item)
            if row_length is None:
                return tn.stack(list(items))
            return tn.from_rows(list(items), row_length)
        except (NumError, TensorError) as e:
            self._fail(e.args[0], sid, domain=isinstance(e, NumError) and e.domain)

    def array(self, items, sid):
        return ArrayValue(tuple(items))

    def set_(self, items, sid):
        return SetValue(_dedup(items))

    def union(self, a, b, sid): return self._binop(nunion, a, b, sid)
    def intersect(self, a, b, sid): return self._binop(nintersect, a, b, sid)
    def setminus(self, a, b, sid): return self._binop(nsetminus, a, b, sid)
    def subseteq(self, a, b, sid): return self._binop(nsubseteq, a, b, sid)
    def notmember(self, value, collection, sid):
        return self._binop(nnotmember, value, collection, sid)
    def subset(self, a, b, sid): return self._binop(nsubset, a, b, sid)
    def supseteq(self, a, b, sid): return self._binop(nsupseteq, a, b, sid)
    def supset(self, a, b, sid): return self._binop(nsupset, a, b, sid)
    def ne(self, a, b, sid): return self._binop(nnotequal, a, b, sid)
    def eq(self, a, b, sid): return self._binop(neq, a, b, sid)
    def approx(self, a, b, sid): return self._binop(napprox, a, b, sid)
    def member(self, value, collection, sid): return self._binop(nmember, value, collection, sid)

    def _index_selector(self, item, length, sid):
        if item is None:
            return range(1, length + 1)
        if isinstance(item, RangeValue):
            bounds = (item.start, item.step, item.second, item.end)
            if any(isinstance(v, bool) or not isinstance(v, int)
                   for v in bounds if v is not None):
                self._fail("slice bounds and step must be exact integers", sid)
            for bound in (item.start, item.end):
                if bound is not None and not 1 <= bound <= length:
                    self._fail(f"slice bound {bound} out of range 1..{length}", sid)
            end = item.end if item.end is not None else (length if item.step > 0 else 1)
            return range(item.start, end + (1 if item.step > 0 else -1), item.step)
        if isinstance(item, bool) or not isinstance(item, int):
            self._fail(f"index must be an exact integer, got {nshow(item)}", sid)
        if not 1 <= item <= length:
            self._fail(f"index {item} out of range 1..{length}", sid)
        return item

    def index(self, head, items, sid, spelling=None):
        """1-based collection selection; numeric heads multiply by the bracketed tensor."""
        if isinstance(head, TensorValue):
            if len(items) > head.order:
                self._fail(f"{len(items)} indices for an order-{head.order} tensor", sid)
            selectors = tuple(self._index_selector(item, length, sid)
                              for item, length in zip(items, head.shape))
            try:
                return tn.index(head, selectors)
            except TensorError as e:
                self._fail(e.args[0], sid)
        if isinstance(head, SetValue | SymbolicSetValue):
            self._fail("sets are unordered and cannot be indexed", sid)
        if isinstance(head, ArrayValue):
            if len(items) != 1:
                self._fail("an array takes one index; chain `a[i][j]` for nested arrays", sid)
            i = self._index_selector(items[0], len(head.items), sid)
            if isinstance(i, range):
                return ArrayValue(tuple(head.items[j - 1] for j in i))
            return head.items[i - 1]
        if not isinstance(head, _NUMERIC_TYPES) or isinstance(head, bool):
            self._fail(f"{spelling or nshow(head)} is not indexable", sid)
        if any(item is None for item in items):
            self._fail("whole-axis selection needs a tensor or array", sid)
        return self.mul(head, self.tensor(items, None, sid), sid)

    def transpose(self, value, sid, glyph="'"):
        if callable(value) and not isinstance(value, TensorValue | ArrayValue | SetValue):
            if glyph != "'":
                self._fail("`ᵀ` transposes tensors; a function's derivative is `f'`", sid)
            order = value.order + 1 if isinstance(value, Derivative) else 1
            return Derivative(value.fn if isinstance(value, Derivative) else value, order)
        try:
            return ntranspose(value)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def dot(self, a, b, sid):
        return self._binop(ndot, a, b, sid)

    def times(self, a, b, sid):
        return self._binop(ntimes, a, b, sid)

    def otimes(self, a, b, sid):
        return self._binop(notimes, a, b, sid)

    def compose(self, f, g, sid):
        return self._binop(ncompose, f, g, sid)

    def op(self, name, sid):
        return OPERATORS[name]

    def partial(self, fn, slots, holes, kwargs, sid, spelling=None):
        """`f(a, _)`: fix some arguments now, take the rest later. The head must be a
        function — a partial never falls back to the product reading."""
        if not callable(fn):
            self._fail(f"{nshow(fn)} is not a function", sid)
        if isinstance(fn, AdFunction):
            if kwargs:
                self._fail("user-defined functions take positional arguments only", sid)
            if len(slots) != len(fn.params):
                self._fail(f"{spelling or fn.display_name} takes {len(fn.params)} "
                           f"arguments, got {len(slots)}", sid)
        return Partial(fn, tuple(slots), tuple(holes), kwargs)

    def if_expr(self, condition, then, otherwise, sid):
        """The ternary `c ? a : b` — the one conditional. Only the selected branch's
        thunk runs; the condition must be a boolean."""
        if not isinstance(condition, bool):
            self._fail("ternary condition must be boolean", sid)
        if condition:
            return _to_ad(then(), preserve_bool=True)
        if otherwise is None:
            self._fail("ternary condition was false and has no else branch", sid)
        return _to_ad(otherwise(), preserve_bool=True)

    def py(self, path: Any, sid: int, spelling: str | None = None) -> Any:
        """`\\py("dotted.path")` — resolve a Python dotted path to a callable. The
        argument must evaluate to a string (a literal or any string-valued
        expression); no other value names a path."""
        label = _display_name("py", spelling)
        if not isinstance(path, str):
            self._fail(f"`{label}` takes one string naming a dotted Python path", sid)
        obj = _resolve_dotted(path)
        if obj is _MISSING:
            self._fail(f"`{label}` cannot resolve `{path}`", sid)
        if not callable(obj):
            self._fail(f"`{path}` is not callable", sid)
        return obj

    def import_(self, path: Any, members: tuple[str, ...], sid: int,
                 member_spellings: tuple[str, ...] = ()) -> None:
        """`\\import("lib")` / `\\import("lib": f, \\g)` — evaluate an ad source file
        once per session in a fresh root environment and bind its top-level names into
        this environment. See the module docstring's "Modules and imports" for the
        full semantics: resolution, caching, cycles, closures, binding rules."""
        if not isinstance(path, str):
            self._fail("`\\import` takes one string literal naming an ad file", sid)
        resolved = self._resolve_ad_file(path, sid)
        chain = self.import_chain + (resolved,)
        if resolved in self.import_chain or self.modules.get(resolved) is _IMPORTING:
            self._fail(f"circular import: {' -> '.join(chain)}", sid)
        record = self.modules.get(resolved)
        if record is None:
            record = self._evaluate_module(resolved, path, sid)
        self._bind_imported(record, members, path, sid, member_spellings)

    def pyimport(self, path: Any, members: tuple[str, ...], sid: int,
                 member_spellings: tuple[str, ...] = ()) -> None:
        """`\\pyimport("math": \\sqrt, \\tau)` — resolve a Python module and bind the
        named members into this environment. Callables bind as callables (the `\\py`
        rule); every other member converts through the interop matrix or fails at the
        import's span. Member selection is mandatory (there is no module value to
        bind), and all members validate before any binds."""
        if not isinstance(path, str):
            self._fail(r"`\pyimport` takes one string literal naming a Python module", sid)
        if not members:
            self._fail(r'`\pyimport` binds members by name: \pyimport("math": \sqrt)', sid)
        module = _resolve_dotted(path)
        if module is _MISSING:
            self._fail(f"`\\pyimport` cannot resolve `{path}`", sid)
        if not isinstance(module, types.ModuleType):
            self._fail(f"`{path}` is not a Python module", sid)
        if len(set(members)) != len(members):
            self._fail("duplicate member in `\\pyimport`", sid)
        bound: list[tuple[str, Any]] = []
        for index, name in enumerate(members):
            display_name = _display_name(
                name, member_spellings[index] if index < len(member_spellings) else None)
            value = getattr(module, name, _MISSING)
            if value is _MISSING:
                self._fail(f"module `{path}` has no member `{display_name}`", sid)
            if self._protected(name):
                self._fail(f"`{display_name}` is protected", sid)
            if name in self.env:
                self._fail(f"`{display_name}` is already bound", sid)
            if callable(value):
                bound.append((name, value))
                continue
            try:
                bound.append((name, _to_ad(value)))
            except NumError as e:
                self._fail(f"member `{display_name}`: {e.args[0]}", sid)
        for name, value in bound:
            self.env[name] = value

    def _resolve_ad_file(self, path: str, sid: int) -> str:
        r"""The importing file's directory first, then the working directory; `".ad"`
        is appended unless the path already carries it. A path that instead resolves
        as a Python module gets a pointed hint — `\import` and `\pyimport` are
        deliberately separate semantics."""
        name = path if path.endswith(".ad") else f"{path}.ad"
        searched: list[str] = []
        for base in (self.base_dir, os.getcwd()):
            if base is None:
                continue
            candidate = os.path.abspath(os.path.join(base, name))
            if candidate in searched:
                continue
            searched.append(candidate)
            if os.path.isfile(candidate):
                return candidate
        if _resolve_dotted(path) is not _MISSING:
            self._fail(
                f"`{path}` resolves to a Python module; Python imports use "
                + r'`\pyimport("' + path + r'": \member)`', sid)
        self._fail(f"no such ad file `{name}` (searched {', '.join(searched)})", sid)

    def _evaluate_module(self, resolved: str, path: str, sid: int) -> dict:
        """Read, compile, and execute an ad module in a fresh root environment, then
        cache its environment in the session registry. `compile_source` is imported
        late — the driver pairs frontend and exec and sits above this seam, so a
        module-level import would be a cycle. Module outputs are discarded; a parse
        or evaluation failure inside the module fails at the import's span."""
        from .driver import compile_source
        from .parser import ParseError
        try:
            with open(resolved, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            self._fail(f"cannot read `{resolved}`: {e.strerror or e}", sid)
        try:
            unit = compile_source(source)
        except ParseError as e:
            self._fail(f"error in `{path}`: {e.msg}", sid)
        module_env: dict = {}
        engine = Engine(module_env, unit.spans, unit.definitions, None,
                        self.modules, os.path.dirname(resolved),
                        self.import_chain + (resolved,), quotes=unit.quotes)
        self.modules[resolved] = _IMPORTING
        g: dict = {"_e": engine}
        try:
            exec(unit.code, g)  # noqa: S102 - generated from our own AST only
        except EvalError as e:
            del self.modules[resolved]
            self._fail(f"error evaluating `{path}`: {e.msg}", sid)
        except Exception as e:
            del self.modules[resolved]
            self._fail(f"internal error evaluating `{path}`: {type(e).__name__}: {e}", sid)
        self.modules[resolved] = module_env
        return module_env

    def _bind_imported(self, module_env: dict, members: tuple[str, ...], path: str,
                       sid: int, member_spellings: tuple[str, ...] = ()) -> None:
        """Copy bindings out of a (cached) module environment: every top-level name,
        or only the selected members. Everything validates before anything binds, so
        a bad member leaves the environment untouched rather than partially
        imported. A name already bound to the *identical* cached value is a silent
        no-op (re-import), any other collision a typed error."""
        names = members if members else tuple(module_env)
        spellings = member_spellings if members else ()
        if len(set(names)) != len(names):
            self._fail("duplicate member in `\\import`", sid)
        for index, name in enumerate(names):
            display_name = _display_name(
                name, spellings[index] if index < len(spellings) else None)
            if name not in module_env:
                self._fail(f"`{display_name}` is not defined in `{path}`", sid)
            if self._protected(name):
                self._fail(f"`{display_name}` is protected", sid)
            if name in self.env and self.env[name] is not module_env[name]:
                self._fail(f"`{display_name}` is already bound", sid)
        for name in names:
            self.env[name] = module_env[name]

    def app(self, fn: Any, args: tuple[Any, ...], kwargs: dict[str, Any],
            sid: int, spelling: str | None = None) -> AdValue | str:
        """Postfix application `f(args, \\name=value…)` lowered to one seam call, with
        dynamic juxtaposition: a callable head applies; a non-callable head with exactly
        one positional argument and no kwargs falls back to the paper product
        (`x(y+1)` is `x*(y+1)`); any other non-callable shape fails at the call's span.
        The fallback means identical source can read as product or application depending
        on what the head is bound to — accepted deliberately (docs/grammar.md).
        Kwargs pass through to Python callables as native keyword arguments
        (`\\py("math.isclose")(1, 2, \\rel_tol=0.5)`); user-defined functions reject
        them — their parameters are positional."""
        if callable(fn):
            token = _CALL_ENGINE.set(self)
            try:
                return _invoke(fn, args, kwargs, spelling)
            except NumError as e:
                message = e.args[0]
                if isinstance(fn, PreludeFn):
                    message = _display_builtin_error(message, fn.name, spelling)
                self._fail(message, sid, domain=e.domain)
            finally:
                _CALL_ENGINE.reset(token)
        if not kwargs and len(args) == 1:
            return self.mul(fn, args[0], sid)
        self._fail(f"{nshow(fn)} is not a function", sid)

    def pow_app(self, fn: Any, exponent: AdValue, args: tuple[Any, ...],
                kwargs: dict[str, Any], sid: int, spelling: str | None = None) -> AdValue | str:
        """Function-power `f²(x)`: a callable head gives `f(x)^n`; any other head gives
        `(f^n)(x)`, keeping `x²(2)` a product."""
        if callable(fn):
            if isinstance(exponent, (int, Fraction, float)) and not isinstance(exponent, bool) \
                    and exponent < 0:
                inverse = self._inverse(fn, exponent, sid)
                return self.app(inverse, args, kwargs, sid, spelling)
            return self.pow(self.app(fn, args, kwargs, sid, spelling), exponent, sid)
        return self.app(self.pow(fn, exponent, sid), args, kwargs, sid, spelling)

    def _inverse(self, fn: Any, exponent: AdValue, sid: int) -> Callable:
        if exponent != -1:
            self._fail("only `⁻¹` denotes an inverse function", sid)
        if isinstance(fn, Inverse):
            return fn.fn
        return Inverse(fn)

    def _binop(self, f, a: AdValue, b: AdValue, sid: int) -> AdValue:
        try:
            return f(a, b)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def add(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(nadd, a, b, sid)

    def sub(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(nsub, a, b, sid)

    def mul(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(nmul, a, b, sid)

    def div(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(ndiv, a, b, sid)

    def congruent(self, a: AdValue, b: AdValue, modulus: AdValue, sid: int) -> bool:
        try:
            return ncongruent(a, b, modulus)
        except NumError as error:
            self._fail(error.args[0], sid)

    def mod(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(nmod, a, b, sid)

    def angle(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(npolar, a, b, sid)

    def iff(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(niff, a, b, sid)

    def lnot(self, a: AdValue, sid: int) -> AdValue:
        try:
            return nnot(a)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def logic(self, kind: str, left: AdValue, right: Callable, lsid: int, rsid: int) -> bool:
        """`∧ ∨ →`: the right operand's thunk runs only when the left does not decide."""
        symbol = OP_SYMBOLS[kind]
        if not isinstance(left, bool):
            self._fail(f"`{symbol}` needs boolean operands, got {nshow(left)}", lsid)
        decisive, result = _SHORT_CIRCUIT[kind]
        if left is decisive:
            return result
        value = right()
        if not isinstance(value, bool):
            self._fail(f"`{symbol}` needs boolean operands, got {nshow(value)}", rsid)
        return value

    def pow(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        if callable(a) and isinstance(b, (int, Fraction, float)) and not isinstance(b, bool) \
                and b < 0:
            return self._inverse(a, b, sid)
        return self._binop(npow, a, b, sid)

    def neg(self, a: AdValue, sid: int) -> AdValue:
        # Unary, so not _binop (which passes two operands) — same wrapping contract
        # though: a seam NumError becomes a spanned EvalError at this node's span.
        try:
            return nneg(a)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def fact(self, a: AdValue, sid: int) -> AdValue:
        try:
            return nfact(a)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def dfact(self, a: AdValue, sid: int) -> AdValue:
        try:
            return ndfact(a)
        except NumError as e:
            self._fail(e.args[0], sid, domain=e.domain)

    def out(self, v: AdValue | str, sid: int) -> str:
        result = f"= {nshow(v)}"
        self.outputs.append(result)
        return result
