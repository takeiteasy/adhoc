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


# --- modulo ---


@pytest.mark.parametrize("src, out", [
    (r"-7 % 3", "= 2"), (r"7 % -3", "= -2"), (r"7/2 % 1", "= 1/2"),
    (r"5 \mod 3", "= 2"), (r"(%)(9, 4)", "= 1"), (r"2 * 7 % 4", "= 2"),
    (r"(\mod)(10, 4)", "= 2"), (r"\map((%)(·, 3), ⟨4, 5, 6⟩)", "= ⟨1, 2, 0⟩"),
    (r"[5, 7] % 3", "= [2, 1]"),
])
def test_modulo_is_floored(src, out):
    assert ev(src) == out


def test_modulo_of_a_symbolic_real_stays_exact():
    assert ev(r"(\pi + 1) % 1 + 3 - \pi") == "= 0"


def test_modulo_errors():
    fails(r"5 % 0", "division by zero")
    fails(r"(1+i) % 2", "needs real numbers")
    assert ev(r"\inf % 3") == "= NaN"


# --- number theory ---


@pytest.mark.parametrize("src, out", [
    (r"\gcd(12, 18)", "= 6"), (r"\gcd(⟨12, 18, 30⟩)", "= 6"), (r"\gcd(-4, 6)", "= 2"),
    (r"\lcm(4, 6)", "= 12"), (r"\lcm({2, 3, 4})", "= 12"),
    (r"\divmod(-7, 3)", "= ⟨-3, 2⟩"), (r"\divmod(7/2, 1)", "= ⟨3, 1/2⟩"),
    (r"\isprime(97)", "= true"), (r"\isprime(1)", "= false"), (r"\isprime(-7)", "= false"),
    (r"\factor(360)", "= ⟨2, 2, 2, 3, 3, 5⟩"), (r"\factor(1)", "= ⟨⟩"),
    (r"\factor(97)", "= ⟨97⟩"),
    (r"\choose(5, 2)", "= 10"), (r"\choose(2, 5)", "= 0"), (r"\perm(5, 2)", "= 20"),
    (r"\fib(0)", "= 0"), (r"\fib(10)", "= 55"), (r"\fib(100)", "= 354224848179261915075"),
])
def test_number_theory(src, out):
    assert ev(src) == out


@pytest.mark.parametrize("src, message", [
    (r"\gcd(1/2, 3)", "exact integer"), (r"\gcd()", "at least one"),
    (r"\gcd(\true, 2)", "exact integer"), (r"\factor(0)", "positive integer"),
    (r"\factor(10^19)", "limited"), (r"\choose(-1, 2)", "non-negative"),
    (r"\perm(5)", "takes"), (r"\fib(-1)", "non-negative"), (r"\isprime(1/2)", "exact integer"),
])
def test_number_theory_errors(src, message):
    fails(src, message)
