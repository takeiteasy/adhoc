import pytest

from adhoc.driver import run_source
from adhoc.runtime import EvalError


def ev(src):
    return run_source(src, {})[-1]


def fails(src, message):
    with pytest.raises(EvalError, match=message):
        run_source(src, {})


# --- rounding ---


@pytest.mark.parametrize("src, out", [
    (r"\floor(5/2)", "= 2"), (r"\floor(-5/2)", "= -3"),
    (r"\ceil(5/2)", "= 3"), (r"\ceil(-5/2)", "= -2"),
    (r"\trunc(5/2)", "= 2"), (r"\trunc(-5/2)", "= -2"),
    (r"\round(5/2)", "= 3"), (r"\round(-5/2)", "= -3"), (r"\round(7/3)", "= 2"),
    (r"\floor(\pi)", "= 3"), (r"\ceil(\pi)", "= 4"), (r"\trunc(-\pi)", "= -3"),
    (r"\round(\sqrt(2) * 10)", "= 14"),
    (r"\round(22/7, 2)", "= 157/50"), (r"\round(1234, -2)", "= 1200"),
    (r"\floor(4)", "= 4"),
])
def test_rounding_stays_exact(src, out):
    assert ev(src) == out


def test_rounding_passes_non_finite_floats_through():
    assert ev(r"\floor(\inf)") == "= Inf"
    assert ev(r"\round(-\inf)") == "= -Inf"


def test_rounding_rejects_complex_and_non_numbers():
    fails(r"\floor(1+i)", "needs a real number")
    fails(r"\round(1, 1/2)", "integer digit count")
    fails(r"\ceil(\true)", "booleans are not numbers")


@pytest.mark.parametrize("src, out", [
    (r"\abs(-3)", "= 3"), (r"\abs(-7/2)", "= 7/2"), (r"\abs(3+4i)", "= 5"),
    (r"\abs(-\pi)", "= 3.14159265358979..."), (r"\abs(0)", "= 0"),
    (r"\sign(-\pi)", "= -1"), (r"\sign(0)", "= 0"), (r"\sign(9/2)", "= 1"),
])
def test_abs_and_sign(src, out):
    assert ev(src) == out


def test_abs_of_a_gaussian_with_irrational_modulus_is_algebraic():
    assert ev(r"\abs(1+i) * \abs(1+i)") == "= 2"


def test_sign_rejects_complex():
    fails(r"\sign(1+i)", "needs a real number")
