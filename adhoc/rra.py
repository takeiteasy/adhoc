"""The Recursive Real Arithmetic (RRA) fallback tier: the tier above algebraic
numbers (DESIGN.md, `## exact arithmetic (internals)`, tier 5). Backed by sympy,
but only the numeric seam (`adhoc/runtime.py`) dispatches into this module — it
computes with the tier's own values and the exact tiers below it, never with
values above the seam (docs/numerics.md).

## Value shape

Every other real: a real number with no symbolic closed form and no algebraic
representation — multi-term transcendental sums (`π + 1`, `π·√2`), reciprocals
of atoms (`1/π`), transcendental powers (`2^√2`), and closed-form-free function
results (`sin(1)`). Values are stored as the canonical sympy expression itself,
the same Expr-wrapper pattern as `adhoc/symbolic.py` and `adhoc/algebraic.py`:
sympy's automatic simplification produces the normal forms, so structural
equality on the stored expression decides the tier's equalities exactly — the
property ticket #41 (equality across the tower) relies on, with Richardson–Fitch
reserved for that ticket rather than this one.

The ticket's spelling — a real as a function `tolerance -> rational` — is
`approximate`/`to_function` below: the lower tiers' high-precision eval of the
stored expression, escalating sympy precision until successive evaluations agree
within the requested tolerance. No separate interval-refinement machinery, per
the design decision recorded on the ticket: sympy holds the series/continued-
fraction/iterative methods behind the seam.

## Tower order

The symbolic tier is tried first, the algebraic tier second — the seam
dispatches into `symbolic.combine` and `algebraic.combine` before this module,
and this module's `classify` is never asked about a value either lower tier
could hold in normal operation. Anything reaching here that is real and finite
is admitted: unlike the strict shapes below, this tier has no rejection of
form, only of domain. The float tier remains beneath as the explicitly-inexact
tier (float literals, float-argument calls, IEEE non-finite values) — an RRA
value mixed with a float still demotes to float, the fast O(1) path. The tier
is real-only: non-real results raise `DomainError`, and non-finite values keep
the exact tiers' domain-error contract (there is no exact-tier infinity).

## The gate

`classify` is the only admission route: a rational result collapses back to
`int`/`Fraction`, a real finite result is admitted, and anything else raises.
Two failure kinds, both internal — the seam converts them:

- `Unrepresentable` — sympy cannot establish the value as a real number (a free
  symbol, an expression of undecided reality that will not evaluate). The seam
  demotes it to the float tier.
- `DomainError` — the exact tiers have no infinity and there is no complex tier:
  non-finite values and non-real values. The seam turns the message into its
  typed `NumError` with the caller's span. (The float tier keeps its own pinned
  behavior for the same inputs.)

## Display

`show` prints 15 significant digits, expanded positionally, with a trailing
ellipsis — the same interim policy as the symbolic and algebraic tiers. The
iterative tolerance-tightening display is ticket #40's work, never this tier's.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import math

import sympy

# Significant digits shown before the ellipsis — the symbolic tier's policy
# (DESIGN.md display examples); ticket #40 governs RRA display tightening, not
# this tier.
DISPLAY_DIGITS = 15

# Precision-escalation budget for `approximate`: each step roughly doubles the
# working digits, so ten steps from a ~35-digit start covers absurd tolerances.
_MAX_APPROX_STEPS = 10


class Unrepresentable(Exception):
    """A result sympy cannot establish as a real number (a free symbol, an
    expression of undecided reality that will not evaluate). Internal: the seam
    demotes it to the float tier."""


class DomainError(Exception):
    """An exact-tier domain failure — the exact tiers have no infinity and there
    is no complex tier (non-finite values, non-real values such as `ln` of a
    negative RRA). Internal: the seam converts the message into its typed
    `NumError`."""


@dataclass(frozen=True, eq=False)
class RRA:
    """A real number beyond the symbolic and algebraic tiers, in canonical sympy
    form: the `tolerance -> rational` fallback. The expression is never a bare
    rational — those collapse back to exact before admission — and is always
    real and finite. Structural equality on the canonical form decides the
    tier's equalities exactly (Richardson–Fitch is ticket #41's work, not this
    tier's)."""

    expr: sympy.Expr

    def __float__(self) -> float:
        return float(self.expr)

    def __eq__(self, other) -> bool:
        # A gate-passing RRA value is irrational (rationals collapse before
        # admission), so it never equals a rational — the seam's neq() compares
        # exactly through structurally_equal() instead. The `.expr` duck-type
        # covers the symbolic and algebraic tiers without importing them (tiers
        # stay independent; only the seam dispatches across them).
        if isinstance(other, RRA) or isinstance(
            getattr(other, "expr", None), sympy.Expr
        ):
            return self.expr == other.expr
        if isinstance(other, int | Fraction):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.expr)

    # Rich comparisons decide exactly (sympy auto-evaluates relational
    # expressions between explicit numbers). RangeValue's iteration compares
    # bounds directly, so an RRA bound iterates like an exact one.
    def __lt__(self, other) -> bool:
        return _compare_reflected("lt", self, other)

    def __le__(self, other) -> bool:
        return _compare_reflected("le", self, other)

    def __gt__(self, other) -> bool:
        return _compare_reflected("gt", self, other)

    def __ge__(self, other) -> bool:
        return _compare_reflected("ge", self, other)


def _compare_reflected(op: str, a: RRA, b) -> bool:
    if isinstance(b, int | Fraction | RRA) or isinstance(
        getattr(b, "expr", None), sympy.Expr
    ):
        return compare(op, a, b)
    return NotImplemented


def _to_expr(v) -> sympy.Expr:
    """An exact, symbolic, algebraic or RRA ad number as a sympy expression
    (floats never reach the tier — the seam demotes them before dispatch). The
    `.expr` duck-type covers all three tier types without importing any of them
    — tiers stay independent and only the seam dispatches across them."""
    expr = getattr(v, "expr", None)
    if isinstance(expr, sympy.Expr):
        return expr
    if isinstance(v, Fraction):
        return sympy.Rational(v.numerator, v.denominator)
    return sympy.Integer(v)


def _check_domain(expr: sympy.Expr) -> None:
    """Reject non-finite and non-real values — zoo/oo/nan have no exact-tier
    representation, and there is no complex tier."""
    if expr.has(sympy.zoo, sympy.nan) or expr.is_finite is False:
        raise DomainError("the exact tiers have no infinity")
    if expr.is_real is False:
        raise DomainError("complex results are not supported")


def classify(expr: sympy.Expr) -> Fraction | RRA:
    """The tier's only admission gate: a rational result collapses back to exact
    (denominator 1 → `int`, matching the seam's own normalization), a real
    finite result is admitted, anything else raises Unrepresentable — or
    DomainError for non-real/non-finite values.

    The symbolic and algebraic tiers are tried first by the seam; this gate
    assumes that order and does not special-case their shapes. Admission
    requires sympy to positively establish reality (`is_real` strictly `True`)
    or a successful finite real evaluation when reality is undecided: anything
    else falls to the float tier rather than risk admitting something complex.
    """
    if expr.is_Rational:
        v = Fraction(int(expr.p), int(expr.q))
        return int(v) if v.denominator == 1 else v
    _check_domain(expr)
    if expr.is_real is True:
        return RRA(expr)
    # Undecided reality: probe with a finite-precision evaluation. A free
    # symbol (or anything that will not evaluate to a real number) raises or
    # comes back non-real, and stays Unrepresentable.
    try:
        probe = expr.evalf(30)
    except Exception:
        raise Unrepresentable(
            "not an established real number; the float tier approximates it"
        ) from None
    if probe.is_real is True and probe.is_finite is not False:
        return RRA(expr)
    raise Unrepresentable(
        "not an established real number; the float tier approximates it")


def combine(op: str, a, b) -> Fraction | RRA:
    """One RRA-tier binary operation (`add`/`sub`/`mul`/`div`/`pow`) over exact,
    symbolic, algebraic and/or RRA operands. sympy does the algebra and
    normalization; classify decides whether the result stays in the tier.
    Raises DomainError for `1/0`-shaped inputs (`div` by zero, `0⁻ⁿ`) with the
    seam's canonical message, and for fractional powers of negative bases (no
    complex tier — real-branch selection is ticket #42's work)."""
    x, y = _to_expr(a), _to_expr(b)
    if op == "div" and y == 0:
        raise DomainError("division by zero")
    if op == "pow" and x == 0 and y < 0:
        raise DomainError("division by zero")  # 0 to a negative power is 1/0
    raw = {"add": x + y, "sub": x - y, "mul": x * y, "div": x / y,
           "pow": x**y}[op]
    try:
        return classify(raw)
    except DomainError:
        if op == "pow":
            raise DomainError(
                "a negative number raised to a fractional power is not a real "
                "number") from None
        raise


def negate(a) -> Fraction | RRA:
    """Unary minus: negating a real stays one (rational collapse included — the
    gate decides)."""
    return classify(-_to_expr(a))


_TRIG_NOTE = "tan is undefined at odd multiples of pi/2"
_DOMAIN_MESSAGES = {
    "sqrt": "sqrt of a negative number is not a real number",
    "ln": "ln is defined only for positive numbers",
    "sin": "sin is not real-valued here",
    "cos": "cos is not real-valued here",
    "tan": _TRIG_NOTE,
}
_APPLY_FUNCS = {
    "sqrt": sympy.sqrt, "ln": sympy.log,
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
}


def apply(name: str, arg) -> Fraction | RRA:
    """One prelude function over an exact, symbolic, algebraic or RRA argument
    that the lower tiers could not hold (`\\sin(1)`, `\\ln(π + 1)`). sympy
    evaluates the call and anything real and finite is admitted; anything else
    raises Unrepresentable and the seam falls back to float. Domain failures
    carry the function's own message."""
    try:
        return classify(_APPLY_FUNCS[name](_to_expr(arg)))
    except DomainError:
        raise DomainError(_DOMAIN_MESSAGES[name]) from None


def approximate(v: RRA, tolerance: int | Fraction | float) -> Fraction:
    """The ticket's spelling made concrete: evaluate the stored expression to
    within `tolerance` and return the rational. sympy evaluates at escalating
    precision until two successive evaluations agree within half the tolerance
    — the shared plateau shape (`CONVERGENCE_TOLERANCE` spirit in
    `adhoc/runtime.py`: stabilize-or-error, never a misleading partial) with a
    caller-supplied tolerance rather than the fixed knob — and the agreed
    value's exact decimal expansion is returned, so the result is provably
    within the tolerance once the guard digits exceed it."""
    try:
        tol = Fraction(tolerance)
    except (ValueError, OverflowError, TypeError, ZeroDivisionError):
        raise DomainError("tolerance must be a positive finite number") from None
    if tol <= 0:
        raise DomainError("tolerance must be a positive finite number")
    expr = _to_expr(v)
    if tol >= 1:
        dps = 25
    else:
        f = float(tol)
        if f > 0:
            approx_digits = max(0, math.ceil(-math.log10(f)))
        else:
            # Tolerance underflows binary64: estimate decimal digits from the
            # denominator's bit length instead.
            approx_digits = math.ceil(tol.denominator.bit_length() * 0.30103)
        dps = approx_digits + 20
    previous: Fraction | None = None
    for _ in range(_MAX_APPROX_STEPS):
        current = Fraction(Decimal(str(expr.evalf(dps))))
        if previous is not None and abs(current - previous) <= tol / 2:
            return current
        previous = current
        dps = dps * 2 + 10
    raise DomainError(
        "could not approximate the value to the requested tolerance")


def to_function(v: RRA) -> Callable[[int | Fraction | float], Fraction]:
    """An RRA value as a `tolerance -> rational` function — the representation
    DESIGN.md names. `approximate` does the work; this is the calling shape."""
    return lambda tolerance: approximate(v, tolerance)


def structurally_equal(a, b) -> bool:
    """Exact equality within the exact + symbolic + algebraic + RRA tiers:
    canonical-form equality. Sound because every gate admits only canonical
    shapes — two values are equal iff their canonical expressions are, and a
    gate-passing RRA value never equals a rational.

    Open audit for ticket #41 (equality across the tower): like the algebraic
    tier, this assumes sympy's automatic simplification canonicalizes every
    equal pair identically. Richardson–Fitch lives in that ticket, not here.
    """
    return _to_expr(a) == _to_expr(b)


_RELATIONS = {
    "lt": sympy.Lt, "le": sympy.Le, "gt": sympy.Gt, "ge": sympy.Ge,
}


def compare(op: str, a, b) -> bool:
    """Exact ordering across the exact + symbolic + algebraic + RRA tiers:
    sympy decides relational expressions between explicit numbers, raising
    precision internally until the comparison is settled. The evalf fallback is
    defensive only — every gate-passing shape auto-evaluates."""
    rel = _RELATIONS[op](_to_expr(a), _to_expr(b))
    if isinstance(rel, sympy.logic.boolalg.Boolean):
        return bool(rel)
    diff = _to_expr(a) - _to_expr(b)  # unevaluated relational: decide the sign
    positive = diff.is_positive
    if positive is None:
        positive = bool(sympy.N(diff, 50) > 0)
    return {"lt": not positive, "le": not positive,
            "gt": bool(positive), "ge": bool(positive)}[op]


def from_sympy(value: sympy.Expr) -> Fraction | RRA:
    """The `\\py` boundary's half for sympy objects that neither the symbolic
    nor the algebraic tier admitted: real finite values convert, anything else
    is Unrepresentable (the seam names the type, never truncates)."""
    if not isinstance(value, sympy.Expr):
        raise Unrepresentable("not a sympy expression")
    return classify(value)


def show(s: RRA) -> str:
    """The RRA interim display: 15 significant digits, expanded positionally (no
    scientific notation — the float display's rule), trailing ellipsis. The
    value is exact; the digits are a truncation, not the value (`π + 1` shows
    as `4.14159265358979...`). Iterative tightening is ticket #40's work."""
    magnitude = sympy.N(abs(s.expr), DISPLAY_DIGITS + 10)
    d = Decimal(str(magnitude))
    with localcontext() as ctx:
        ctx.prec = 60
        # Quantize to the 15th significant digit (adjusted() is the exponent of
        # the most significant digit), then expand positionally.
        q = d.quantize(Decimal(1).scaleb(d.adjusted() - DISPLAY_DIGITS + 1))
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    sign = "-" if s.expr.is_negative else ""
    return f"{sign}{text}..."
