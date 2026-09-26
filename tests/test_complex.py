"""The numeric type surface (ticket #42): exact decimals, the trailing-dot
float marker, the exact complex tower, and the odd-root real branch — at the
driver level, the way the language presents them."""

import math

import pytest
from fractions import Fraction

from adhoc.driver import run_source
from adhoc.runtime import EvalError


def last(src: str, env: dict | None = None) -> str:
    return run_source(src, env)[-1]


# --- literal tiers ---


def test_decimals_are_exact():
    assert last("0.1 + 0.2") == "= 3/10"
    assert last("0.5") == "= 1/2"
    assert last(".25 * 4") == "= 1"
    assert last("2.0") == "= 2"  # whole-value decimals collapse
    assert last("1/3") == "= 1/3"  # int/int stays the exact rational


def test_float_spellings():
    # The trailing-dot marker and any exponent form are the float tier.
    assert last("1.") == "= 1.0"
    assert last("0.5e0 + 0.5e0") == "= 1.0"
    assert last("1.5e3") == "= 1500.0"
    assert last("2e3") == "= 2000.0"
    assert last("2e") == "= 5.43656365691809..."  # no exponent digits: 2*e


# --- the imaginary unit and Gaussian arithmetic ---


def test_imaginary_unit_prelude():
    assert last("i") == "= i"
    assert last("\\i") == "= i"
    assert last("i*i") == "= -1"
    assert last("i^3") == "= -i"
    assert last("i^4") == "= 1"
    assert last("1/i") == "= -i"


def test_gaussian_arithmetic_stays_exact():
    assert last("(2+3i) + (1+4i)") == "= 3+7i"
    assert last("(2+3i) - (2+3i)") == "= 0"
    assert last("(1+i)(1-i)") == "= 2"  # collapses to the real integer
    assert last("(2+2i)/(1+i)") == "= 2"
    assert last("1/(2+i)") == "= 2/5-1/5i"
    assert last("-(2+3i)") == "= -2-3i"
    assert last("(1+i)^10") == "= 32i"


def test_gaussian_display_forms():
    assert last("2+3i") == "= 2+3i"
    assert last("2-3i") == "= 2-3i"
    assert last("3i") == "= 3i"
    assert last("-3i") == "= -3i"
    assert last("1/2+1/3*i") == "= 1/2+1/3i"  # 1/3i would parse as 1/(3i)
    assert last("0.5 + 0.25i") == "= 1/2+1/4i"


def test_gaussian_never_equals_a_real():
    env: dict = {}
    run_source("v = 2+3i", env)
    assert last("v = 2+3i", env) == "true"
    assert last("v = 2", env) == "false"  # the right side is just 2
    run_source("w = i", env)
    assert last("w = 1", env) == "false"
    assert last("w = w", env) == "true"


# --- complex values across the tiers ---


def test_symbolic_complex_values():
    assert last("\\ln(-1)") == "= 3.14159265358979...i"
    assert last("\\sqrt(-2)") == "= 1.4142135623731...i"
    assert last("√(-1)") == "= i"
    assert last("(π*i)^2") == "= -9.86960440108936..."  # -π², real again
    assert last("\\sqrt(-2)*\\sqrt(-2)") == "= -2"


def test_algebraic_complex_values():
    assert last("(1+i)^0.5") == "= 1.09868411346781...+0.455089860562227...i"
    env: dict = {}
    run_source("z = (1+i)^0.5", env)
    assert last("z = \\complex(1, 1)^0.5", env) == "true"
    run_source("w = (1+i)^2", env)
    assert last("w = 2i", env) == "true"


def test_rra_complex_values():
    assert last("\\sin(1+i)") == "= 1.29845758141598...+0.634963914784736...i"
    # sin(2z) = 2 sin(z) cos(z), decided by Richardson–Fitch on the complex
    # difference (the residual scales below every probe tolerance).
    env: dict = {}
    run_source("d = \\sin(1+i)*\\cos(1+i) - \\sin(2+2i)/2", env)
    assert last("d = 0", env) == "true"
    assert last("\\re(\\sin(1+i))") == "= 1.29845758141598..."
    assert last("\\im(\\sin(1+i))") == "= 0.634963914784736..."


def test_complex_constructor():
    assert last("\\complex(2, 3)") == "= 2+3i"
    assert last("\\complex(2, 0)") == "= 2"  # vanishing imaginary collapses
    assert last("\\complex(0.5, 0.25)") == "= 1/2+1/4i"  # decimal literals are exact
    assert last("\\complex(1., 2.)") == "= 1.0+2.0i"
    assert last("\\complex(1., 0)") == "= 1.0"
    with pytest.raises(EvalError, match="two components"):
        last("\\complex(1)")
    with pytest.raises(EvalError, match="real components"):
        last("\\complex(i, 1)")


def test_re_and_im_projections():
    assert last("\\re(2+3i)") == "= 2"
    assert last("\\im(2+3i)") == "= 3"
    assert last("\\re(i)") == "= 0"
    assert last("\\im(π*i)") == "= 3.14159265358979..."
    assert last("\\re(π*i)") == "= 0"
    assert last("\\im(1.)") == "= 0.0"  # a float stays on its tier
    assert last("\\re(1.)") == "= 1.0"


# --- the odd-root real branch ---


def test_odd_root_real_branch():
    assert last("(-8)^(1/3)") == "= -2"
    assert last("(-8)^(2/3)") == "= 4"
    assert last("(-8)^(5/3)") == "= -32"
    assert last("(-1/8)^(1/3)") == "= -1/2"
    assert last("(-2)^(1/2)") == "= 1.4142135623731...i"
    assert last("(-2.)^(1/2)") == "= 1.4142135623730951i"
    assert last("(-8.)^(1/3)") == "= -2.0"  # exact odd-denominator exponent: real root
    assert last("(-8.)^(1/3.)").startswith("= 1.0000000000000002+1.7320508075688772i")


# --- complex-float tier, no complex ordering ---


def test_complex_float_arithmetic():
    assert last("1. + i") == "= 1.0+1.0i"
    assert last("i * 2.") == "= 2.0i"
    assert last("(1.+i)*(1.-i)") == "= 2.0"  # zero imaginary part collapses to a float
    assert last("(1.+i)^2") == "= 2.0i"
    assert last("(1.+i)^-1") == "= 0.5-0.5i"
    assert last("-(1.+i)") == "= -1.0-1.0i"
    assert last("(1.+i)/2") == "= 0.5+0.5i"
    assert last("(1.+i)/0.") == "= Inf+Infi"
    assert last("\\sqrt(-2) + 1.") == "= 1.0+1.4142135623730951i"


def test_complex_float_equality():
    env: dict = {}
    run_source("w = i", env)
    assert last("w = 1.", env) == "false"
    run_source("z = 1.+i", env)
    assert last("z = 1.+i", env) == "true"
    assert last("z = 1+i", env) == "true"
    assert last("z = 1.+2.i", env) == "false"
    assert last("1.+i ≈ 1+i") == "= true"


def test_complex_float_projections():
    assert last("\\re(3.+4.i)") == "= 3.0"
    assert last("\\im(3.+4.i)") == "= 4.0"
    assert last("\\abs(3.+4.i)") == "= 5.0"
    assert last("\\conj(3.+4.i)") == "= 3.0-4.0i"
    assert last("\\arg(1.+1.i)").startswith("= 0.785398")


def test_polar_with_float_inputs():
    assert last("2.∠1") == "= 1.0806046117362795+1.682941969615793i"
    assert last("2∠1.") == last("2.∠1")
    assert last("\\polar(2., \\pi/2)").endswith("+2.0i") or last("\\polar(2., \\pi/2)") == "= 2.0i"


def test_float_functions_take_the_complex_principal_value():
    assert last("\\sqrt(-2.)") == "= 1.4142135623730951i"
    assert last("\\ln(-1.)") == "= 3.141592653589793i"
    assert last("\\asin(2.)").startswith("= 1.5707963267948966+1.31695789692481")
    assert last("\\sin(1.+i)").startswith("= 1.29845758141597")
    assert last("\\exp(3.i)").startswith("= -0.9899924966004454+0.1411200080598672i")
    with pytest.raises(EvalError, match="math domain error"):
        last("\\ln(0.)")


def test_complex_ordering_is_typed():
    with pytest.raises(EvalError, match="complex values are not ordered"):
        last("i < 3")
    with pytest.raises(EvalError, match="complex values are not ordered"):
        last("3 <= π*i")
    with pytest.raises(EvalError, match="range bounds must be real"):
        last("r = i..3")
    with pytest.raises(EvalError, match="range bounds must be real"):
        last("r = 0..i")


# --- the `i` shadowing rule ---


def test_i_shadows_like_any_identifier():
    env: dict = {}
    assert last("i = 5", env) == "i = 5"
    assert last("i", env) == "= 5"
    assert last("\\i", env) == "= 5"  # both spellings read the one binding
    assert last("i*i", env) == "= 25"
    # The shadow lifts with the scope: a fresh session reads the unit again.
    assert last("i + i") == "= 2i"


def test_i_shadows_in_binders_and_params():
    assert last("\\sum(i=1..3) i") == "= 6"
    env: dict = {}
    run_source("f(i) = i*i", env)
    assert last("f(3)", env) == "= 9"
    assert last("(\\λ(i) i+i)(7)") == "= 14"
    # Inside the shadow, the unit is spelled through the constructor.
    assert last("\\sum(i=1..2) i + \\complex(0, 1)") == "= 3+2i"


def test_other_prelude_names_stay_protected():
    with pytest.raises(EvalError, match="is protected"):
        last("π = 4")
    with pytest.raises(EvalError, match="is protected"):
        last("f(π) = π")


# --- the \py boundary ---


def test_python_complex_crosses_as_complex_float():
    assert last('\\py("complex")(0, 1)') == "= 1.0i"
    assert last('\\py("complex")(1.5, -0.25)') == "= 1.5-0.25i"
    assert last('\\py("complex")(2, 0)') == "= 2.0"
    assert last('\\py("complex")(0, \\py("float")("inf"))') == "= Infi"


# --- seam-level shape checks ---


def test_seam_complex_tiers():
    from adhoc.gauss import Gaussian
    from adhoc.runtime import nshow, npow, nadd, nmul
    from adhoc.symbolic import Symbolic
    from adhoc.algebraic import Algebraic
    from adhoc.rra import RRA

    i = Gaussian(0, 1)
    assert isinstance(nmul(nadd(1, i), i), Gaussian)
    assert nshow(Gaussian(Fraction(1, 2), Fraction(-1, 3))) == "1/2-1/3i"
    # (1+i)^(1/2) is algebraic complex; sin(1+i) is RRA complex.
    assert isinstance(npow(nadd(1, i), Fraction(1, 2)), Algebraic)
    from adhoc.runtime import PRELUDE
    assert isinstance(PRELUDE["sin"](nadd(1, i)), RRA)
    # π*i is symbolic (pure-imaginary with a recognized real shape).
    assert isinstance(nmul(PRELUDE["pi"], i), Symbolic)


# --- exact modulus and argument of trig-built values (ticket #91) ---


@pytest.mark.parametrize("src, out", [
    (r"\abs(2∠1)", "= 2"), (r"\abs(1∠π/7)", "= 1"), (r"\abs(5∠π/7)", "= 5"),
    (r"\abs(1∠π/3)", "= 1"), (r"\abs(3+4i)", "= 5"),
    (r"\arg(2∠1)", "= 1"), (r"\arg(2∠3)", "= 3"), (r"\arg(2∠-2)", "= -2"),
    (r"\arg(1∠π/7) - π/7", "= 0"),
])
def test_polar_modulus_and_argument_are_exact(src, out):
    assert last(src) == out


def test_abs_of_an_unsimplifiable_complex_stays_approximate():
    assert last(r"\abs(π+e i)") == "= 4.15435440231331..."



# --- complex values in infinite folds, \lim and \log ---


def _value(src: str) -> complex:
    return complex(last(src).removeprefix("= ").replace("i", "j").replace("...", ""))


@pytest.mark.parametrize("src, expected", [
    (r"\sum(n=1..) i/n^2", 1j * math.pi ** 2 / 6),
    (r"\sum(n=1..) (i/2)^n", (-1 + 2j) / 5),
    (r"\sum(n=1..) (1/2)^n + i/n^2", 1 + 1j * math.pi ** 2 / 6),
    (r"\prod(n=1..) (1 + i/2^n)", 0.6698396443906053 + 0.952483346135851j),
    (r"\fold((+), \map(\λ(n) i/2^n, 1..), 0)", 1j),
    (r"\sum(n=1..) i/2^5 * 0^n", 0),
])
def test_infinite_folds_take_complex_terms(src, expected):
    assert abs(_value(src) - expected) <= 1e-8


def test_a_diverging_complex_sum_is_a_typed_error():
    with pytest.raises(EvalError, match="did not converge|diverged"):
        last(r"\sum(n=1..) i")


@pytest.mark.parametrize("src, expected", [
    (r"\lim(x=0) \sin(x)/x + i", 1 + 1j),
    (r"\lim(x=0) i*x", 0),
    (r"\lim(x=i) x^2", -1),
    (r"\lim(x=1+i) x", 1 + 1j),
])
def test_lim_takes_complex_bodies_and_anchors(src, expected):
    assert abs(_value(src) - expected) <= 1e-8


def test_lim_complex_anchor_diagonal_rays_are_probed():
    with pytest.raises(EvalError, match="does not exist"):
        last(r"\lim(x=i) \re(x - i)*\im(x - i)/\abs(x - i)^2")


def test_lim_drops_stray_tiny_parts():
    assert complex(last(r"\lim(x=1+i) x^2")[2:].replace("i", "j")) == pytest.approx(2j, abs=1e-12)
    assert float(last(r"\lim(x=i) x^2")[2:]) == pytest.approx(-1.0, abs=1e-12)


def test_lim_complex_anchor_rays_that_disagree_have_no_limit():
    with pytest.raises(EvalError, match="does not exist"):
        last(r"\lim(x=i) \re(x - i)/\abs(x - i)")


@pytest.mark.parametrize("src, expected", [
    (r"\log(2, i)", "= 2.2661800709136...i"), (r"\log(i, 2)", "= -0.441271200305303...i"),
    (r"\log(i, i)", "= 1"), (r"\log(2., i)", "= 2.266180070913597i"),
])
def test_log_takes_complex_arguments(src, expected):
    assert last(src) == expected


def test_log_of_a_complex_value_with_base_one_is_division_by_zero():
    with pytest.raises(EvalError, match="division by zero"):
        last(r"\log(1, i)")


def test_atan2_stays_real_only():
    with pytest.raises(EvalError, match="real arguments"):
        last(r"\atan2(1, i)")


@pytest.mark.parametrize("n", [4, 8])
def test_lim_complex_anchor_harmonics_do_not_vanish_on_the_probe_rays(n):
    with pytest.raises(EvalError, match="does not exist"):
        last(rf"\lim(x=i) \im((x - i)^{n})/\abs(x - i)^{n}")
