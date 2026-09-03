"""The symbolic closed-form tier: the first tier above exact rationals (DESIGN.md,
`## exact arithmetic (internals)`, tier 3). Backed by sympy, but only the numeric
seam (`adhoc/runtime.py`) dispatches into this module — it computes with the tier's
own values and the exact tiers, never with values above the seam (docs/numerics.md).

## Value shape

A symbolic real is a **rational coefficient times exactly one recognized atom** —
the strict shape the DESIGN tier list names:

- `πⁿ` — `π` itself and integer powers (`π·π` is `π²`, kept exact);
- `√r` — square root of a positive rational, normalized by sympy (`√8` is `2√2`,
  `√(1/2)` is `√2/2`);
- `eʳ` — Euler's number to a nonzero rational power (`e` is `e¹`);
- `ln r` — natural log of a positive rational other than 1;
- `sin(π·r)`, `cos(π·r)`, `tan(π·r)` — the trig atoms of the tier list, plus `cos`
  (a deliberate extension of the list): sympy auto-evaluates table angles
  (`sin(π/2)` is `1`, `tan(π/4)` is `1`, `sin(π/3)` is `√3/2`) and leaves the rest
  symbolic (`sin(π/7)` stays a trig atom).

Values are stored as the canonical sympy expression itself: sympy's automatic
simplification produces exactly these normal forms (`√2·√3` is `√6`, `(√2)²` is `2`,
`π − π` is `0`, `e^(1/2)·e^(1/2)` is `e`), so structural equality on the stored
expression decides the tier's equalities exactly.

## The gate

`classify` is the only admission route: a rational result collapses back to
`int`/`Fraction`, a coefficient×atom result is admitted, and anything else raises.
Two failure kinds, both internal — the seam converts them:

- `Unrepresentable` — a real, finite value with no recognized closed form
  (`π + 1/3`, `π·√2`, `1/π`, `2^(1/3)`). The strict single-term shape cannot hold
  it, so the seam tries the algebraic tier next, then the RRA tier — only a
  value of undecided reality reaches the float tier.
- `DomainError` — the exact tiers have no infinity and there is no complex tier:
  `√` of a negative, `ln(0)`, `tan(π/2)`, `0⁻ⁿ`. The seam turns the message into
  its typed `NumError` with the caller's span. (The float tier keeps its own
  pinned behavior for the same inputs — NaN for fractional powers of negatives,
  `math.*`'s ValueError for domain errors.)

## Display

`show` prints 15 significant digits, expanded positionally (no scientific
notation, matching the float display), with a trailing ellipsis: the value is
exact, the digits are a truncation, not the value (`π` shows as
`3.14159265358979...`).
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction

import sympy
import sympy.core.numbers as _symnums

# Significant digits shown before the ellipsis (DESIGN.md display examples).
DISPLAY_DIGITS = 15


class Unrepresentable(Exception):
    """A real, finite symbolic-tier result with no recognized coefficient×atom
    closed form (`π + 1/3`, `π·√2`, `2^(1/3)`). Internal: the seam tries the
    algebraic tier next, then the RRA tier."""


class DomainError(Exception):
    """An exact-tier domain failure — the exact tiers have no infinity and there
    is no complex tier (`√` of a negative, `ln(0)`, `tan(π/2)`, `0⁻ⁿ`). Internal:
    the seam converts the message into its typed `NumError`."""


@dataclass(frozen=True, eq=False)
class Symbolic:
    """A symbolic real in canonical sympy form. The expression is always a rational
    coefficient times one recognized atom (never a bare rational — those collapse
    back to exact before admission), real and finite. Structural equality on the
    canonical form decides the tier's equalities exactly."""

    expr: sympy.Expr

    def __float__(self) -> float:
        return float(self.expr)

    def __eq__(self, other) -> bool:
        # A gate-passing atom is irrational, so it never equals a rational — the
        # seam's neq() compares exactly through structurally_equal() instead.
        if isinstance(other, Symbolic):
            return self.expr == other.expr
        if isinstance(other, int | Fraction):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.expr)

    # Rich comparisons decide exactly (sympy auto-evaluates relational expressions
    # between explicit numbers). RangeValue's iteration compares bounds directly,
    # so a symbolic bound iterates like an exact one.
    def __lt__(self, other) -> bool:
        return _compare_reflected("lt", self, other)

    def __le__(self, other) -> bool:
        return _compare_reflected("le", self, other)

    def __gt__(self, other) -> bool:
        return _compare_reflected("gt", self, other)

    def __ge__(self, other) -> bool:
        return _compare_reflected("ge", self, other)


def _compare_reflected(op: str, a: Symbolic, b) -> bool:
    if not isinstance(b, int | Fraction | Symbolic):
        return NotImplemented
    return compare(op, a, b)


# Gate-verified prelude constants: `π` and `e` are symbolic reals, not floats.
PI = Symbolic(sympy.pi)
E = Symbolic(sympy.E)


def _to_expr(v: int | Fraction | Symbolic) -> sympy.Expr:
    """An exact or symbolic ad number as a sympy expression (floats never reach
    the tier — the seam demotes them before dispatch). The `.expr` duck-type
    also covers algebraic-tier values (`adhoc/algebraic.py`) without importing
    that module — tiers stay independent and only the seam dispatches across
    them."""
    if isinstance(v, Symbolic):
        return v.expr
    if isinstance(v, Fraction):
        return sympy.Rational(v.numerator, v.denominator)
    expr = getattr(v, "expr", None)
    if isinstance(expr, sympy.Expr):
        return expr
    return sympy.Integer(v)


def _check_domain(expr: sympy.Expr) -> None:
    """Reject non-finite and non-real values — zoo/oo/nan have no exact-tier
    representation, and there is no complex tier."""
    if expr.has(sympy.zoo, sympy.nan) or expr.is_finite is False:
        raise DomainError("the exact tiers have no infinity")
    if expr.is_real is False:
        raise DomainError("complex results are not supported")


def _is_atom(expr: sympy.Expr) -> bool:
    """The recognized symbolic reals: πⁿ (n a positive integer), √r (r > 0
    rational), eʳ (r ≠ 0 rational), ln r (r > 0, r ≠ 1 rational), and the trig
    atoms sin(π·r)/cos(π·r)/tan(π·r) for rational r. sympy's auto-normalization
    guarantees these are canonical."""
    if isinstance(expr, _symnums.Pi):
        return True  # π itself — the πⁿ atom with n = 1
    if isinstance(expr, sympy.Pow):
        base, exp = expr.args
        if isinstance(base, _symnums.Pi):
            return isinstance(exp, sympy.Integer) and exp >= 1
        return exp == sympy.Rational(1, 2) and isinstance(base, sympy.Rational) \
            and base > 0
    if isinstance(expr, sympy.exp | _symnums.Exp1):  # eʳ; E is exp(1)
        (arg,) = expr.args or (sympy.Integer(1),)
        return isinstance(arg, sympy.Rational) and arg != 0
    if isinstance(expr, sympy.log):
        (arg,) = expr.args
        return isinstance(arg, sympy.Rational) and arg > 0 and arg != 1
    if isinstance(expr, sympy.sin | sympy.cos | sympy.tan):
        (arg,) = expr.args
        return isinstance(arg / sympy.pi, sympy.Rational)
    return False


def classify(expr: sympy.Expr) -> Fraction | Symbolic:
    """The tier's only admission gate: a rational result collapses back to exact
    (denominator 1 → `int`, matching the seam's own normalization — `√2·√2` is
    the integer `2` again), a coefficient×atom result is admitted as-is (the
    coefficient rides inside the sympy form), anything else raises
    Unrepresentable — or DomainError for non-real/non-finite values."""
    if expr.is_Rational:
        v = Fraction(int(expr.p), int(expr.q))
        return int(v) if v.denominator == 1 else v
    _check_domain(expr)
    coeff, rest = expr.as_coeff_Mul()
    if isinstance(coeff, sympy.Rational) and coeff != 0 and _is_atom(rest):
        return Symbolic(expr)
    raise Unrepresentable(
        "no recognized closed form; the upper tiers hold it")


def combine(op: str, a: int | Fraction | Symbolic,
            b: int | Fraction | Symbolic) -> Fraction | Symbolic:
    """One symbolic-tier binary operation (`add`/`sub`/`mul`/`div`/`pow`) over
    exact and/or symbolic operands. sympy does the algebra and normalization;
    classify decides whether the result stays in the tier. Raises DomainError for
    `1/0`-shaped inputs (`div` by zero, `0⁻ⁿ`) with the seam's canonical message,
    and for fractional powers of negative bases (no complex tier)."""
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


def negate(a: int | Fraction | Symbolic) -> Fraction | Symbolic:
    """Unary minus: negating a coefficient×atom form stays one."""
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


def apply(name: str, arg: int | Fraction | Symbolic) -> Fraction | Symbolic:
    """One prelude function over an exact or symbolic argument (`\\sqrt(2)`,
    `\\sin(π/3)`, `\\ln(2)`): sympy evaluates exact closed forms
    (`sin(π/3)` is `√3/2`, `tan(π/4)` collapses to `1`), and anything without a
    recognized closed form (`\\sin(1)`) raises Unrepresentable — the prelude
    wrapper falls back to the float tier. Domain failures carry the function's
    own message."""
    try:
        return classify(_APPLY_FUNCS[name](_to_expr(arg)))
    except DomainError:
        raise DomainError(_DOMAIN_MESSAGES[name]) from None


def structurally_equal(a: int | Fraction | Symbolic,
                       b: int | Fraction | Symbolic) -> bool:
    """Exact equality within the exact + symbolic tiers: canonical-form equality.
    Sound because the gate admits only canonical shapes — two values are equal
    iff their canonical expressions are (`√8` and `2√2` store identically), and a
    gate-passing atom never equals a rational."""
    return _to_expr(a) == _to_expr(b)


_RELATIONS = {
    "lt": sympy.Lt, "le": sympy.Le, "gt": sympy.Gt, "ge": sympy.Ge,
}


def compare(op: str, a: int | Fraction | Symbolic,
            b: int | Fraction | Symbolic) -> bool:
    """Exact ordering across the exact + symbolic tiers: sympy decides relational
    expressions between explicit numbers (`π < 22/7` is decided exactly, not
    float-compared), raising precision internally until the comparison is
    settled. The evalf fallback is defensive only — every gate-passing shape
    auto-evaluates."""
    rel = _RELATIONS[op](_to_expr(a), _to_expr(b))
    if isinstance(rel, sympy.logic.boolalg.Boolean):
        return bool(rel)
    diff = _to_expr(a) - _to_expr(b)  # unevaluated relational: decide the sign
    positive = diff.is_positive
    if positive is None:
        positive = bool(sympy.N(diff, 50) > 0)
    return {"lt": not positive, "le": not positive,
            "gt": bool(positive), "ge": bool(positive)}[op]


def from_sympy(value: sympy.Expr) -> Fraction | Symbolic:
    """The `\\py` boundary's half for sympy objects: values crossing back into ad
    go through the same gate the tier admits by — recognized closed forms convert,
    anything else is Unrepresentable (the seam names the type, never truncates)."""
    if not isinstance(value, sympy.Expr):
        raise Unrepresentable("not a sympy expression")
    return classify(value)


def show(s: Symbolic) -> str:
    """The symbolic display: 15 significant digits, expanded positionally (no
    scientific notation — the float display's rule), trailing ellipsis. The value
    is exact; the digits are a truncation, not the value (`π` shows as
    `3.14159265358979...`)."""
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
