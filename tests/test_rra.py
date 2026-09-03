import math
from fractions import Fraction

import pytest
import sympy

from adhoc.algebraic import classify as alg_classify
from adhoc.driver import run_source
from adhoc.rra import DomainError as RRADomainError
from adhoc.rra import RRA, approximate, classify, to_function
from adhoc.runtime import (
    DIVISION_BY_ZERO,
    PRELUDE,
    Engine,
    NumError,
    _as_float,
    _to_ad,
    nadd,
    ndiv,
    neq,
    nneg,
    nmul,
    npow,
    nshow,
    nsub,
)
from adhoc.span import Span
from adhoc.symbolic import PI as PI_SYM
from adhoc.symbolic import classify as sym_classify


def rra(expr):
    """Admit a sympy expression through the RRA gate — the only route tests use
    to build RRA values directly, mirroring what the seam does."""
    return classify(expr)


def sym(expr):
    """Admit a sympy expression through the symbolic gate."""
    return sym_classify(expr)


def alg(expr):
    """Admit a sympy expression through the algebraic gate."""
    return alg_classify(expr)


SQRT2 = sym(sympy.sqrt(2))
CBRT2 = alg(sympy.Integer(2) ** sympy.Rational(1, 3))


def last(src: str) -> str:
    """Only the final statement's result, mirroring test_driver.py."""
    return run_source(src)[-1]


def test_beyond_algebraic_results_stay_rra():
    # The tier's headline: multi-term transcendental sums, reciprocals of atoms
    # and transcendental powers have no symbolic closed form and are not
    # algebraic — they stay exact as tolerance->rational functions instead of
    # falling to the float tier.
    assert isinstance(nadd(PI_SYM, 1), RRA)
    assert isinstance(nmul(PI_SYM, SQRT2), RRA)
    assert isinstance(ndiv(1, PI_SYM), RRA)
    assert isinstance(nadd(PI_SYM, CBRT2), RRA)


def test_transcendental_powers_stay_rra():
    # `2^√2` (Gelfond–Schneider) is transcendental — real, so the RRA tier
    # holds it.
    result = npow(2, SQRT2)
    assert isinstance(result, RRA)
    assert result == rra(sympy.Integer(2) ** sympy.sqrt(2))


def test_rra_arithmetic_stays_rra():
    total = nadd(PI_SYM, 1)
    assert isinstance(nadd(total, total), RRA)
    assert isinstance(nsub(total, CBRT2), RRA)  # `(π + 1) − π` collapses to 1
    assert isinstance(nmul(total, 2), RRA)
    assert isinstance(ndiv(total, 3), RRA)
    assert isinstance(nadd(total, CBRT2), RRA)
    assert isinstance(nneg(total), RRA)


def test_exact_results_collapse_back_down():
    # Pointwise sympy evaluation re-gates from the top: `(π + 1) − π`
    # simplifies to 1 before any gate sees it, so exact results collapse
    # instead of sticking at the top tier.
    total = nadd(PI_SYM, 1)
    assert nsub(total, PI_SYM) == 1 and type(nsub(total, PI_SYM)) is int
    assert ndiv(total, total) == 1 and type(ndiv(total, total)) is int
    assert npow(total, 0) == 1 and type(npow(total, 0)) is int


def test_rra_display_is_truncated_digits_plus_ellipsis():
    assert nshow(nadd(PI_SYM, 1)) == "4.14159265358979..."
    assert nshow(nmul(PI_SYM, SQRT2)) == "4.44288293815837..."
    assert nshow(ndiv(1, PI_SYM)) == "0.318309886183791..."
    assert nshow(npow(2, SQRT2)) == "2.66514414269023..."
    assert nshow(nneg(nadd(PI_SYM, 1))) == "-4.14159265358979..."


def test_rra_exact_tier_domain_errors_are_typed():
    # No complex tier and no exact-tier infinity: fractional powers of negative
    # bases stay typed NumErrors (the float tier would yield NaN), and `1/0`
    # shapes stay the same failure as `1/0`.
    with pytest.raises(NumError, match="not a real number"):
        npow(-2, Fraction(1, 2))
    with pytest.raises(NumError, match=DIVISION_BY_ZERO):
        npow(0, Fraction(-1, 2))
    with pytest.raises(NumError, match=DIVISION_BY_ZERO):
        ndiv(nadd(PI_SYM, 1), 0)
    with pytest.raises(NumError, match="defined only for positive"):
        PRELUDE["ln"](nneg(nadd(PI_SYM, 1)))


def test_rra_equality_is_exact():
    total = nadd(PI_SYM, 1)
    assert neq(total, nadd(PI_SYM, 1))
    assert neq(total, rra(sympy.pi + 1))
    assert not neq(total, 4)  # an RRA value never equals a rational
    assert not neq(total, Fraction(29, 7))
    assert not neq(total, nmul(PI_SYM, SQRT2))


def test_rra_ordering_is_exact():
    eng = Engine({}, (Span(0, 0),))
    total = nadd(PI_SYM, 1)
    assert eng.lt(total, 5, 0)
    assert eng.gt(total, 4, 0)
    assert eng.gt(nmul(PI_SYM, SQRT2), total, 0)
    assert eng.ge(total, total, 0)


def test_rra_float_side_compares_approximately():
    # A float operand drags the comparison to the float tier.
    assert neq(nadd(PI_SYM, 1), 4.141592653589793)
    assert not neq(nadd(PI_SYM, 1), 4.14)


def test_as_float_widens_rra_reals():
    assert abs(_as_float(nadd(PI_SYM, 1)) - (math.pi + 1)) <= 1e-15


def test_approximate_evaluates_to_within_tolerance():
    # The ticket's spelling: give an error bound, get a rational within it.
    total = nadd(PI_SYM, 1)
    approx = approximate(total, Fraction(1, 10**10))
    assert isinstance(approx, Fraction)
    assert abs(float(approx) - (math.pi + 1)) <= 1e-10
    tighter = approximate(total, Fraction(1, 10**25))
    assert abs(float(tighter) - (math.pi + 1)) <= 1e-15
    with pytest.raises(RRADomainError, match="tolerance must be"):
        approximate(total, 0)
    with pytest.raises(RRADomainError, match="tolerance must be"):
        approximate(total, Fraction(-1, 1000))


def test_to_function_is_tolerance_to_rational():
    total = nadd(PI_SYM, 1)
    f = to_function(total)
    approx = f(Fraction(1, 1000))
    assert isinstance(approx, Fraction)
    assert abs(float(approx) - (math.pi + 1)) <= 1e-3


def test_prelude_transcendental_builtins_stay_rra():
    # Closed-form-free calls of exact arguments are real, so the RRA tier holds
    # them; float arguments stay entirely on the float tier.
    assert isinstance(PRELUDE["sin"](1), RRA)
    assert isinstance(PRELUDE["ln"](CBRT2), RRA)
    assert PRELUDE["sqrt"](SQRT2) == alg(
        sympy.Integer(2) ** sympy.Rational(1, 4))  # `\sqrt(√2)` is `2^(1/4)`
    assert PRELUDE["sin"](1.0) == math.sin(1.0)
    assert isinstance(PRELUDE["sin"](1.0), float)


def test_to_ad_admits_real_sympy_values():
    assert _to_ad(sympy.pi + 1) == nadd(PI_SYM, 1)
    assert isinstance(_to_ad(sympy.pi + 1), RRA)
    with pytest.raises(NumError, match="cannot convert"):
        _to_ad(sympy.Symbol("x"))


def test_rra_exact_arithmetic():
    assert last("π + 1") == "= 4.14159265358979..."
    assert last("2^√2") == "= 2.66514414269023..."
    assert last("x = π + 1; x = π + 1") == "true"
    assert last("x = π + 1; x = 4") == "false"
    assert last("π + 1 > 4") == "= true"
    assert last("(π + 1) - π") == "= 1"
