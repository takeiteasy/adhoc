import math
from fractions import Fraction

import pytest
import sympy

from adhoc.algebraic import Algebraic, classify
from adhoc.driver import run_source
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


def alg(expr):
    """Admit a sympy expression through the algebraic gate — the only route
    tests use to build algebraic values, mirroring what the seam does."""
    return classify(expr)


def sym(expr):
    """Admit a sympy expression through the symbolic gate."""
    return sym_classify(expr)


SQRT2 = sym(sympy.sqrt(2))
CBRT2 = alg(sympy.Integer(2) ** sympy.Rational(1, 3))
CBRT4 = alg(sympy.Integer(4) ** sympy.Rational(1, 3))


def last(src: str) -> str:
    """Only the final statement's result, mirroring test_driver.py."""
    return run_source(src)[-1]


def test_fractional_powers_without_closed_form_stay_algebraic():
    # The tier's headline: `2^(1/3)` and `2^(1/4)` have no coefficient×atom
    # form but are real algebraic — they stay exact instead of falling to
    # the float tier.
    cbrt2 = npow(2, Fraction(1, 3))
    assert isinstance(cbrt2, Algebraic)
    assert cbrt2 == CBRT2
    fourth = npow(2, Fraction(1, 4))
    assert isinstance(fourth, Algebraic)
    # The ticket's example: (√2)^(1/2) arrives as 2^(1/4), identically stored.
    assert npow(SQRT2, Fraction(1, 2)) == fourth


def test_algebraic_powers_collapse_back_to_exact():
    # `2^(1/3)^3` recognizes and collapses to the exact integer 2; perfect
    # powers through the algebraic tier collapse the same way.
    assert npow(CBRT2, 3) == 2 and type(npow(CBRT2, 3)) is int
    assert npow(8, Fraction(1, 3)) == 2  # perfect cube still collapses
    assert npow(CBRT2, 2) == CBRT4  # `2^(2/3)` stores identically to `4^(1/3)`


def test_algebraic_arithmetic_stays_exact():
    # Sums and products beyond the single-term shape stay algebraic:
    # `√2 + 2^(1/3)` and `2^(1/3) + 2^(2/3)` have no symbolic closed form.
    total = nadd(SQRT2, CBRT2)
    assert isinstance(total, Algebraic)
    assert total == alg(sympy.sqrt(2) + sympy.Integer(2) ** sympy.Rational(1, 3))
    assert isinstance(nadd(CBRT2, CBRT4), Algebraic)
    assert isinstance(nmul(CBRT2, CBRT2), Algebraic)
    assert isinstance(nsub(CBRT4, CBRT2), Algebraic)
    assert isinstance(ndiv(CBRT2, CBRT4), Algebraic)
    assert isinstance(nadd(CBRT2, 1), Algebraic)
    assert isinstance(ndiv(1, CBRT2), Algebraic)
    assert isinstance(nneg(nadd(CBRT2, CBRT4)), Algebraic)


def test_transcendental_results_fall_to_float():
    # π-bearing sums/products and `2^√2` (Gelfond–Schneider) are transcendental
    # — not algebraic — so the float tier (the RRA stand-in) approximates them.
    assert isinstance(nadd(PI_SYM, CBRT2), float)
    assert isinstance(nmul(PI_SYM, CBRT2), float)
    assert isinstance(npow(2, SQRT2), float)
    assert nadd(PI_SYM, CBRT2) == math.pi + 2 ** (1 / 3)


def test_algebraic_display_is_truncated_digits_plus_ellipsis():
    assert nshow(CBRT2) == "1.25992104989487..."
    assert nshow(npow(2, Fraction(1, 4))) == "1.18920711500272..."
    assert nshow(nneg(CBRT2)) == "-1.25992104989487..."
    assert nshow(nadd(CBRT2, CBRT4)) == "2.84732210186307..."


def test_algebraic_exact_tier_domain_errors_are_typed():
    # No complex tier and no exact-tier infinity: fractional powers of negative
    # bases stay typed NumErrors (the float tier would yield NaN), and `0⁻ⁿ`
    # stays the same failure as `1/0`. Real-branch selection for odd roots is
    # ticket #42's work, not this tier's.
    with pytest.raises(NumError, match="not a real number"):
        npow(-2, Fraction(1, 2))
    with pytest.raises(NumError, match=DIVISION_BY_ZERO):
        npow(0, Fraction(-1, 2))
    with pytest.raises(NumError, match=DIVISION_BY_ZERO):
        ndiv(CBRT2, 0)


def test_algebraic_equality_is_exact():
    assert neq(CBRT2, npow(2, Fraction(1, 3)))
    assert neq(npow(CBRT2, 2), CBRT4)
    assert neq(npow(SQRT2, Fraction(1, 2)), npow(2, Fraction(1, 4)))
    assert not neq(CBRT2, 2)  # an algebraic never equals a rational
    assert not neq(CBRT2, Fraction(5, 4))
    assert not neq(CBRT2, CBRT4)


def test_algebraic_ordering_is_exact():
    eng = Engine({}, (Span(0, 0),))
    assert eng.lt(CBRT2, Fraction(3, 2), 0)
    assert eng.gt(CBRT4, CBRT2, 0)
    assert eng.lt(npow(2, Fraction(1, 4)), SQRT2, 0)
    assert eng.ge(CBRT2, CBRT2, 0)


def test_algebraic_float_side_compares_approximately():
    # A float operand drags the comparison to the float tier.
    assert neq(CBRT2, 2 ** (1 / 3))
    assert not neq(CBRT2, 1.26)


def test_as_float_widens_algebraic_reals():
    assert _as_float(CBRT2) == 2 ** (1 / 3)


def test_prelude_sqrt_recognizes_algebraic_forms():
    # Only `sqrt` routes algebraic arguments through the gate (`sin`/`ln` of a
    # nonzero algebraic are transcendental — straight to the float tier).
    assert PRELUDE["sqrt"](CBRT2) == alg(sympy.Integer(2) ** sympy.Rational(1, 6))
    assert isinstance(PRELUDE["sin"](CBRT2), float)
    assert isinstance(PRELUDE["ln"](CBRT2), float)
    with pytest.raises(NumError, match="not a real number"):
        PRELUDE["sqrt"](nsub(0, CBRT4))


def test_to_ad_admits_real_algebraic_sympy_values():
    assert _to_ad(sympy.Integer(2) ** sympy.Rational(1, 3)) == CBRT2
    with pytest.raises(NumError, match="cannot convert"):
        _to_ad(sympy.pi + sympy.Integer(2) ** sympy.Rational(1, 3))


def test_algebraic_exact_arithmetic():
    assert last("2^(1/3)") == "= 1.25992104989487..."
    assert last("(√2)^(1/2)") == "= 1.18920711500272..."
    assert last("x = 2^(1/3); x^3") == "= 2"
    assert last("x = 2^(1/3); x = 2^(1/3)") == "true"
    assert last("x = 2^(1/3); x = 2") == "false"
    assert last("2^(1/3) < 3/2") == "= true"
    assert last("\\sqrt(2^(1/3))") == "= 1.12246204830937..."
