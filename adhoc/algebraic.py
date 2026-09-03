"""The algebraic-number tier: the tier above symbolic closed forms (DESIGN.md,
`## exact arithmetic (internals)`, tier 4). Backed by sympy, but only the numeric
seam (`adhoc/runtime.py`) dispatches into this module — it computes with the tier's
own values and the exact tiers below it, never with values above the seam
(docs/numerics.md).

## Value shape

A real algebraic number that has no symbolic-tower closed form: roots of
rational-coefficient polynomials beyond the coefficient×atom shape
(`2^(1/3)`, `2^(1/4)`, `√2 + 2^(1/3)`, `(√2)^(1/2)` which arrives as `2^(1/4)`).
Values are stored as the canonical sympy expression itself, the same
Expr-wrapper pattern as `adhoc/symbolic.py`: sympy's automatic simplification
produces the normal forms (`2^(1/3)^3` is `2`, `2^(1/3)^2` stores identically to
`4^(1/3)`, `(√2)^(1/2)` stores identically to `2^(1/4)`), so structural
identity is the fast equality path, with a minimal-polynomial fallback for
the pairs sympy never canonicalizes (`(1+√2)^2` vs `3+2√2`: the difference
of two real algebraics is algebraic, so `minpoly(a-b) == x` decides it).

Minimal-polynomial + isolating-interval is the classic representation the ticket
names; here sympy holds that representation behind the seam (its `RootOf` forms
carry exactly polynomial + interval) rather than a hand-rolled struct. The seam
never inspects it directly: admission, minimization (rational collapse) and
high-precision approximation all go through this module's gate.

## Tower order

The symbolic tier is tried first — the seam dispatches into `symbolic.combine`
before this module, and this module's `classify` is never asked about a
coefficient×atom form in normal operation. Anything transcendental (`π + 1`,
`π·√2`, `1/π`, `2^√2`) is not algebraic and raises `Unrepresentable`: the seam
tries the RRA tier next, which holds every real. The tier is real-only: non-real results raise `DomainError`, and
real odd roots of negatives keep the exact tiers' `DomainError` contract (the
principal branch is complex; selecting the real branch is ticket #42's complex-
surface work, not this tier's).

## The gate

`classify` is the only admission route: a rational result collapses back to
`int`/`Fraction`, a real algebraic result is admitted, and anything else raises.
Two failure kinds, both internal — the seam converts them:

- `Unrepresentable` — a real, finite value that is not algebraic (`π + 1`,
  `2^√2`, `sin(1)`). The seam demotes it to the float tier.
- `DomainError` — the exact tiers have no infinity and there is no complex tier:
  non-finite values and non-real values (`√` of a negative, `(-2)^(1/2)`). The
  seam turns the message into its typed `NumError` with the caller's span. (The
  float tier keeps its own pinned behavior for the same inputs.)

## Display

`show` prints 15 significant digits, expanded positionally, with a trailing
ellipsis — the same policy as the symbolic tier (ticket #40's iterative
tightening and `\\prec(n)` apply to the RRA tier only, never here).
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction

import sympy

# Significant digits shown before the ellipsis — the symbolic tier's policy
# (DESIGN.md display examples); ticket #40 governs RRA display, not this tier.
DISPLAY_DIGITS = 15


class Unrepresentable(Exception):
    """A real, finite result that is not algebraic (`π + 2^(1/3)`, `2^√2`).
    Internal: the seam tries the RRA tier next, which holds every real."""


class DomainError(Exception):
    """An exact-tier domain failure — the exact tiers have no infinity and there
    is no complex tier (non-finite values, `√` of a negative, fractional powers
    of negative bases). Internal: the seam converts the message into its typed
    `NumError`."""


@dataclass(frozen=True, eq=False)
class Algebraic:
    """A real algebraic number in canonical sympy form. The expression is never
    a bare rational — those collapse back to exact before admission — and is
    always real and finite. Language equality is `structurally_equal`
    (structural fast path plus minimal-polynomial fallback); Python `==`
    stays structural on purpose (a minpoly-based `__eq__` would break the
    hash contract for equal-valued different-expression pairs)."""

    expr: sympy.Expr

    def __float__(self) -> float:
        return float(self.expr)

    def __eq__(self, other) -> bool:
        # A gate-passing algebraic is irrational, so it never equals a rational
        # — the seam's neq() compares exactly through structurally_equal().
        # The `.expr` duck-type covers the symbolic tier without importing it
        # (tiers stay independent; only the seam dispatches across them).
        if isinstance(other, Algebraic) or isinstance(
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
    # bounds directly, so an algebraic bound iterates like an exact one.
    def __lt__(self, other) -> bool:
        return _compare_reflected("lt", self, other)

    def __le__(self, other) -> bool:
        return _compare_reflected("le", self, other)

    def __gt__(self, other) -> bool:
        return _compare_reflected("gt", self, other)

    def __ge__(self, other) -> bool:
        return _compare_reflected("ge", self, other)


def _compare_reflected(op: str, a: Algebraic, b) -> bool:
    if isinstance(b, int | Fraction | Algebraic) or isinstance(
        getattr(b, "expr", None), sympy.Expr
    ):
        return compare(op, a, b)
    return NotImplemented


def _to_expr(v) -> sympy.Expr:
    """An exact, symbolic or algebraic ad number as a sympy expression (floats
    never reach the tier — the seam demotes them before dispatch). The `.expr`
    duck-type covers both tier types without importing either — tiers stay
    independent and only the seam dispatches across them."""
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


def classify(expr: sympy.Expr) -> Fraction | Algebraic:
    """The tier's only admission gate: a rational result collapses back to exact
    (denominator 1 → `int`, matching the seam's own normalization —
    `2^(1/3)^3` is the integer `2` again), a real algebraic result is admitted,
    anything else raises Unrepresentable — or DomainError for non-real/
    non-finite values.

    The symbolic tier is tried first by the seam; this gate assumes that order
    and does not special-case coefficient×atom forms. Admission requires
    sympy to positively establish both algebraicity and reality
    (`is_algebraic`/`is_real` strictly `True`): an undecided value falls to the
    float tier rather than risk admitting something transcendental or complex.
    """
    if expr.is_Rational:
        v = Fraction(int(expr.p), int(expr.q))
        return int(v) if v.denominator == 1 else v
    _check_domain(expr)
    if expr.is_algebraic is True and expr.is_real is True:
        return Algebraic(expr)
    raise Unrepresentable(
        "not a real algebraic number; the RRA tier holds it")


def combine(op: str, a, b) -> Fraction | Algebraic:
    """One algebraic-tier binary operation (`add`/`sub`/`mul`/`div`/`pow`) over
    exact, symbolic and/or algebraic operands. sympy does the algebra and
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


def negate(a) -> Fraction | Algebraic:
    """Unary minus: negating a real algebraic stays one (rational collapse
    included — the gate decides)."""
    return classify(-_to_expr(a))


_DOMAIN_MESSAGES = {
    "sqrt": "sqrt of a negative number is not a real number",
}


def apply(name: str, arg) -> Fraction | Algebraic:
    """One prelude function over an exact, symbolic or algebraic argument. Only
    `sqrt` routes here (per the tower plan: `sin`/`cos`/`tan`/`ln` of a nonzero
    algebraic are transcendental, so the seam sends those straight to the float
    tier rather than paying for a gate that cannot admit them). A result that
    stays algebraic (`\\sqrt(2^(1/3))` is `2^(1/6)`) is admitted; anything else
    raises Unrepresentable and the seam falls back to float. Domain failures
    carry the function's own message."""
    if name != "sqrt":
        raise Unrepresentable(f"{name} of an algebraic is not algebraic")
    try:
        return classify(sympy.sqrt(_to_expr(arg)))
    except DomainError:
        raise DomainError(_DOMAIN_MESSAGES[name]) from None


def structurally_equal(a, b) -> bool:
    """Exact equality within the exact + symbolic + algebraic tiers:
    canonical-form equality with a minimal-polynomial fallback. The fast path
    is structural (`2^(1/3)^2` and `4^(1/3)` store identically, and a
    gate-passing algebraic never equals a rational); when sympy's automatic
    simplification leaves equal values stored differently (e.g. `(1+√2)^2`
    vs `3+2√2`), the difference of two real algebraics is itself algebraic,
    so equality is decided by its minimal polynomial (`minpoly(a-b) == x`
    iff `a == b`). A minimal-polynomial failure (transcendental difference
    across the symbolic/algebraic boundary) means unequal, never a raise."""
    xa, xb = _to_expr(a), _to_expr(b)
    if xa == xb:
        return True
    diff = xa - xb
    if diff == 0:
        return True
    try:
        return sympy.minimal_polynomial(
            diff, sympy.Symbol("x")) == sympy.Symbol("x")
    except Exception:
        return False


_RELATIONS = {
    "lt": sympy.Lt, "le": sympy.Le, "gt": sympy.Gt, "ge": sympy.Ge,
}


def compare(op: str, a, b) -> bool:
    """Exact ordering across the exact + symbolic + algebraic tiers: sympy
    decides relational expressions between explicit numbers, raising precision
    internally until the comparison is settled. The evalf fallback is defensive
    only — every gate-passing shape auto-evaluates."""
    rel = _RELATIONS[op](_to_expr(a), _to_expr(b))
    if isinstance(rel, sympy.logic.boolalg.Boolean):
        return bool(rel)
    diff = _to_expr(a) - _to_expr(b)  # unevaluated relational: decide the sign
    positive = diff.is_positive
    if positive is None:
        positive = bool(sympy.N(diff, 50) > 0)
    return {"lt": not positive, "le": not positive,
            "gt": bool(positive), "ge": bool(positive)}[op]


def from_sympy(value: sympy.Expr) -> Fraction | Algebraic:
    """The `\\py` boundary's half for sympy objects that the symbolic tier did
    not admit: real algebraic values convert, anything else is Unrepresentable
    (the seam names the type, never truncates)."""
    if not isinstance(value, sympy.Expr):
        raise Unrepresentable("not a sympy expression")
    return classify(value)


def show(s: Algebraic) -> str:
    """The algebraic display: 15 significant digits, expanded positionally (no
    scientific notation — the float display's rule), trailing ellipsis. The
    value is exact; the digits are a truncation, not the value (`2^(1/3)` shows
    as `1.25992104989487...`)."""
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
