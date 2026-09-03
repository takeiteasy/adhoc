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
structural identity is the fast equality path, and Richardson–Fitch
(`equal` below: escalating `approximate` probes on the difference, equal
while indistinguishable from zero) decides the pairs sympy never
simplifies (`sin(1)^2+cos(1)^2` vs `1`).

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

`show` prints the session precision's significant digits (default 15, tunable
via the seam's `\\prec` setting), expanded positionally, with a trailing
ellipsis — the same interim policy as the symbolic and algebraic tiers, but
with iteratively tightened tolerance behind it: successive `approximate`
observations at tightening tolerances must agree to the full target before
those digits print, otherwise the longest agreed prefix prints (graceful
degrade, never a display error).
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import math

import sympy

# Default significant digits shown before the ellipsis — the symbolic tier's
# policy (DESIGN.md display examples). Tunable at runtime through the seam's
# `\prec` setting; `show` reads the session value below, never this constant
# directly.
DISPLAY_DIGITS = 15

# Bounds for the `\prec` display-precision setting (significant digits).
MIN_PRECISION_DIGITS = 1
MAX_PRECISION_DIGITS = 1000

# Session display precision for this tier (significant digits). Module-global
# so the single `nshow` path serves REPL and script mode identically; tests
# save/restore it around cases that change it.
_PRECISION_DIGITS = DISPLAY_DIGITS

# Outer tightening budget for `show`: successive `approximate` observations at
# tightening tolerances (each ~1000x tighter) must agree to the full target.
# Six rounds from a 2-guard start covers ordinary values in 2-3 rounds; the
# rest is headroom for rounding-boundary cases before graceful degrade.
_MAX_SHOW_ROUNDS = 6

# Precision-escalation budget for `approximate`: each step roughly doubles the
# working digits, so ten steps from a ~35-digit start covers absurd tolerances.
_MAX_APPROX_STEPS = 10


def get_precision() -> int:
    """Current session display precision for this tier (significant digits)."""
    return _PRECISION_DIGITS


def set_precision(n: int) -> int:
    """Set the session display precision, validating the `\\prec` range.

    Accepts an exact integer (bools rejected — they are not numeric operands
    anywhere in the language); anything else or anything outside
    `MIN_PRECISION_DIGITS..MAX_PRECISION_DIGITS` raises `DomainError`, which
    the seam converts to its typed `NumError` at the call's span."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise DomainError("\\prec takes an integer 1..1000")
    if not MIN_PRECISION_DIGITS <= n <= MAX_PRECISION_DIGITS:
        raise DomainError("\\prec takes an integer 1..1000")
    global _PRECISION_DIGITS
    _PRECISION_DIGITS = n
    return n


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
    real and finite. Language equality is `equal` below (Richardson–Fitch);
    Python `==` stays structural on purpose (an RF-based `__eq__` would break
    the hash contract for equal-valued different-expression pairs)."""

    expr: sympy.Expr

    def __float__(self) -> float:
        return float(self.expr)

    def __eq__(self, other) -> bool:
        # Structural on purpose (see class docstring): the seam's neq()
        # compares through equal(), which can find RF-equal pairs like
        # `sin(1)^2+cos(1)^2` vs `1` that must keep different hashes. The
        # `.expr` duck-type covers the symbolic and algebraic tiers without
        # importing them (tiers stay independent; only the seam dispatches
        # across them).
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
    """Canonical-form equality across the tiers: the fast path `equal` tries
    first (two values are equal when their canonical expressions match, and a
    structurally identical pair never needs a probe). Kept as its own
    function for the seam's fast path and for tests."""
    return _to_expr(a) == _to_expr(b)


# Richardson–Fitch probe tolerances (ticket #41): the difference of two
# RRA-involved values is evaluated at escalating precision and treated as
# equal while indistinguishable from zero. Three probes from the seam's
# convergence scale down to 1e-50 balance confidence against cost — a
# heuristic relying on Schanuel's conjecture, an accepted limitation rather
# than a proof.
_RF_TOLERANCES: tuple[Fraction, ...] = (
    Fraction(1, 10**12),
    Fraction(1, 10**30),
    Fraction(1, 10**50),
)


def equal(a, b) -> bool:
    """Richardson–Fitch equality for any RRA-involved pair (RRA vs RRA, RRA
    vs symbolic/algebraic/exact): structural identity first, an exact shortcut
    when the difference simplifies to a rational, otherwise escalating
    `approximate` probes on the difference — equal iff it stays within each
    tolerance, unequal at the first distinguishable probe. Total: probe
    failures (undecided reality, approximation budget) report unequal, never
    raise. A float operand never reaches here — the seam demotes float
    equality to the float tier before dispatch."""
    xa, xb = _to_expr(a), _to_expr(b)
    if xa == xb:
        return True
    diff = xa - xb
    if diff == 0:
        return True
    if diff.is_Rational:
        return False  # nonzero rational difference, decided exactly
    probe = RRA(diff)
    for tol in _RF_TOLERANCES:
        try:
            q = approximate(probe, tol)
        except Exception:
            return False
        if abs(q) > tol:
            return False
    return True


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


def _format_digits(value: Fraction, digits: int) -> str:
    """Render a rational approximation to `digits` significant digits,
    expanded positionally (no scientific notation — the float display's rule).
    No ellipsis; the caller adds it. Rounding follows the shared quantize
    policy (half-even via the local context)."""
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    mag = abs(value)
    with localcontext() as ctx:
        ctx.prec = max(60, digits + 20)
        d = Decimal(mag.numerator) / Decimal(mag.denominator)
        # Quantize to the target significant digit (adjusted() is the exponent
        # of the most significant digit), then expand positionally.
        q = d.quantize(Decimal(1).scaleb(d.adjusted() - digits + 1))
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{sign}{text}"


def _stable_prefix(a: str, b: str) -> str:
    """Longest common leading text of two formatted numbers, trimmed to a
    valid numeric prefix (no dangling sign or decimal point). Every digit in
    the shared prefix rendered identically from two ~1000x-apart tolerances,
    so it is the proved-stable run — used only for graceful degrade when
    full-target agreement never arrives."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    prefix = a[:i].rstrip(".")
    if prefix in ("", "-", "+"):
        return ""
    return prefix


def show(s: RRA, digits: int | None = None) -> str:
    """The RRA display: session-precision significant digits, expanded
    positionally (no scientific notation — the float display's rule), trailing
    ellipsis. The value is exact; the digits are a truncation, not the value
    (`π + 1` shows as `4.14159265358979...` at the default precision).

    Iterative tightening: successive `approximate` observations at tightening
    tolerances (each ~1000x tighter, from a 2-digit guard) must render
    identically to the full target before those digits print. When no two
    successive observations agree within the round budget, the longest agreed
    prefix prints instead — degrade, never a display error. An explicit
    `digits` overrides the session precision for that call only (the seam's
    `nshow` threading); out-of-range values raise `DomainError`."""
    if digits is None:
        target = _PRECISION_DIGITS
    else:
        if isinstance(digits, bool) or not isinstance(digits, int):
            raise DomainError("\\prec takes an integer 1..1000")
        if not MIN_PRECISION_DIGITS <= digits <= MAX_PRECISION_DIGITS:
            raise DomainError("\\prec takes an integer 1..1000")
        target = digits
    previous_text: str | None = None
    previous_approx: Fraction | None = None
    best_prefix = ""
    for round_ in range(_MAX_SHOW_ROUNDS):
        guard = 2 + 3 * round_
        tol = Fraction(1, 10 ** (target + guard))
        try:
            current = approximate(s, tol)
        except DomainError:
            break
        text = _format_digits(current, target)
        if previous_text is not None and text == previous_text:
            return f"{text}..."
        if previous_text is not None:
            prefix = _stable_prefix(previous_text, text)
            if len(prefix) > len(best_prefix):
                best_prefix = prefix
        previous_text, previous_approx = text, current
    if best_prefix and any(ch.isdigit() for ch in best_prefix):
        return f"{best_prefix}..."
    if previous_text:
        return f"{previous_text}..."
    # Unreachable in practice (`approximate` fails only on domain errors the
    # gate already excludes); fall back to a single high-precision evalf
    # rather than raising out of display.
    magnitude = sympy.N(abs(s.expr), target + 10)
    d = Decimal(str(magnitude))
    with localcontext() as ctx:
        ctx.prec = max(60, target + 20)
        q = d.quantize(Decimal(1).scaleb(d.adjusted() - target + 1))
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    sign = "-" if previous_approx is not None and previous_approx < 0 else (
        "-" if s.expr.is_negative else "")
    return f"{sign}{text}..."
