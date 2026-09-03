"""The numeric type surface (ticket #42): exact decimals, the trailing-dot
float marker, the exact complex tower, and the odd-root real branch — at the
driver level, the way the language presents them."""

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
    assert last("\\complex(0.5, 0.25)") == "= 1/2+1/4i"
    assert last("\\complex(1., 2.)") == "= 1+2i"  # floats read as their decimals
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
    assert last("(-2.)^(1/2)") == "= NaN"  # the float tier keeps its pin


# --- no complex-float tier, no complex ordering ---


def test_complex_float_mixing_is_typed():
    with pytest.raises(EvalError, match="do not mix with floats"):
        last("1. + i")
    with pytest.raises(EvalError, match="do not mix with floats"):
        last("i * 2.")
    with pytest.raises(EvalError, match="do not mix with floats"):
        last("\\sqrt(-2) + 1.")
    env: dict = {}
    run_source("w = i", env)
    assert last("w = 1.", env) == "false"  # equality is defined, and false


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


def test_python_complex_crosses_exactly():
    assert last('\\py("complex")(0, 1)') == "= i"
    assert last('\\py("complex")(1.5, -0.25)') == "= 3/2-1/4i"
    with pytest.raises(EvalError, match="non-finite complex"):
        last('\\py("complex")(0, \\py("float")("inf"))')


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
