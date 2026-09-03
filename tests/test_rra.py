import math
from fractions import Fraction

import pytest
import sympy

from adhoc.algebraic import classify as alg_classify
from adhoc.driver import run_source
from adhoc.rra import DomainError as RRADomainError
from adhoc.rra import RRA, approximate, classify, get_precision, set_precision
from adhoc.rra import show as rra_show
from adhoc.rra import to_function
from adhoc.runtime import EvalError
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
    assert not neq(total, 4)  # this pair is unequal (π + 1 is not 4)
    assert not neq(total, Fraction(29, 7))
    assert not neq(total, nmul(PI_SYM, SQRT2))


def test_richardson_fitch_proves_hidden_identities():
    # sympy never simplifies `sin(1)^2 + cos(1)^2` to 1, so structural
    # equality misses it — the escalating-probe heuristic finds it, including
    # across the tiers (RRA vs exact int/Fraction).
    s1, c1 = PRELUDE["sin"](1), PRELUDE["cos"](1)
    assert isinstance(s1, RRA) and isinstance(c1, RRA)
    circle = nadd(nmul(s1, s1), nmul(c1, c1))
    assert isinstance(circle, RRA)
    assert neq(circle, 1)
    assert neq(circle, Fraction(1, 1))
    assert neq(1, circle)


def test_richardson_fitch_rejects_close_values():
    total = nadd(PI_SYM, 1)
    assert not neq(total, nadd(total, Fraction(1, 10**9)))
    assert not neq(total, nsub(total, Fraction(1, 10**13)))
    assert not neq(nadd(PI_SYM, 1), nadd(PI_SYM, 2))


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


def test_rra_check_assign_uses_richardson_fitch():
    # Statement-level `=` inherits neq: the circle identity compares true
    # though the value stays RRA (the fold never collapses it to 1).
    assert last("x = \\sin(1)^2 + \\cos(1)^2; x = 1") == "true"
    assert last("x = π + 1; x = π + 2") == "false"


@pytest.fixture(autouse=True)
def _reset_display_precision():
    before = get_precision()
    yield
    set_precision(before)


def test_tightening_proves_default_digits():
    # Iterative tightening agrees with the known expansions at the default
    # precision — two successive approximations must render identically.
    assert nshow(nadd(PI_SYM, 1)) == "4.14159265358979..."
    assert rra_show(nadd(PI_SYM, 1), 30) == \
        "4.14159265358979323846264338328..."
    assert rra_show(nadd(PI_SYM, 1), 30).startswith("4.14159265358979")


def test_prec_sets_session_precision():
    assert PRELUDE["prec"](5) == 5
    assert get_precision() == 5
    assert nshow(nadd(PI_SYM, 1)) == "4.1416..."
    assert PRELUDE["prec"](15) == 15
    assert nshow(nadd(PI_SYM, 1)) == "4.14159265358979..."


def test_prec_single_digit_and_longer():
    PRELUDE["prec"](1)
    assert nshow(nadd(PI_SYM, 1)) == "4..."
    assert nshow(nneg(nadd(PI_SYM, 1))) == "-4..."
    PRELUDE["prec"](30)
    assert nshow(nadd(PI_SYM, 1)) == \
        "4.14159265358979323846264338328..."


def test_prec_validation_is_typed():
    for bad in (0, -3, 1001, 1.5, True, "x"):
        with pytest.raises(NumError, match=r"\\prec takes an integer"):
            PRELUDE["prec"](bad)
    assert get_precision() == 15  # a rejected call changes nothing
    with pytest.raises(RRADomainError, match=r"\\prec takes an integer"):
        set_precision(0)
    with pytest.raises(RRADomainError, match=r"\\prec takes an integer"):
        rra_show(nadd(PI_SYM, 1), 0)


def test_prec_wrong_arity_is_typed_at_call_span():
    with pytest.raises(EvalError, match="prec"):
        last("\\prec()")
    with pytest.raises(EvalError, match="prec"):
        last("\\prec(5, 6)")
    with pytest.raises(EvalError, match=r"\\prec takes an integer"):
        last("\\prec(0)")
    with pytest.raises(EvalError, match=r"\\prec takes an integer"):
        last("\\prec(5.0)")


def test_prec_is_protected():
    with pytest.raises(EvalError, match="is protected"):
        last("\\prec = 5")
    assert last("\\prec") == "= <fn \\prec(x)>"


def test_prec_returns_bindable_int():
    assert run_source("x = \\prec(5)") == ["x = 5"]
    assert run_source("x = \\prec(5); x = 5") == ["x = 5", "true"]


def test_prec_applies_to_later_statements_parity():
    # One nshow path: a setting earlier in the same unit governs later
    # statements in REPL and script mode alike.
    assert run_source("\\prec(5); π + 1") == ["= 5", "= 4.1416..."]
    assert run_source("\\prec(5); x = π + 1") == ["= 5", "x = 4.1416..."]


def test_other_tiers_ignore_prec():
    PRELUDE["prec"](5)
    assert nshow(PI_SYM) == "3.14159265358979..."
    assert nshow(CBRT2) == "1.25992104989487..."
    assert nshow(4.1416) == "4.1416"
    assert nshow(Fraction(1, 3)) == "1/3"


def test_nshow_explicit_digits_override_only_that_call():
    total = nadd(PI_SYM, 1)
    assert nshow(total, 5) == "4.1416..."
    assert get_precision() == 15  # the session value is untouched
    assert nshow(total) == "4.14159265358979..."
    assert nshow(total, 30).startswith("4.14159265358979323846")


def test_large_precision_degrades_gracefully_never_errors():
    PRELUDE["prec"](100)
    text = nshow(ndiv(1, PI_SYM))
    assert text.endswith("...")
    assert text.startswith("0.31830988618379067153")
    assert len(text) > 100
