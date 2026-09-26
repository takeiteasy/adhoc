import pytest

from adhoc.driver import run_source
from adhoc.parser import ParseError
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


# --- elementary and special functions ---


@pytest.mark.parametrize("src, out", [
    (r"\exp(0)", "= 1"), (r"\ln(\exp(3))", "= 3"), (r"\exp⁻¹(\e)", "= 1"),
    (r"\sinh(0)", "= 0"), (r"\cosh(0)", "= 1"), (r"\asinh(0)", "= 0"),
    (r"\acosh(1)", "= 0"), (r"\atanh(0)", "= 0"), (r"\sinh⁻¹(0)", "= 0"),
    (r"\gamma(5)", "= 24"), (r"\erf(0)", "= 0"),
    (r"\log(2, 8)", "= 3"), (r"\log(1/2, 8)", "= -3"), (r"\log(8, 1/2)", "= -1/3"),
    (r"\log(4, 8)", "= 3/2"), (r"\log(6, 36)", "= 2"),
    (r"\log(1)", "= 0"), (r"\atan2(0, -1) - \pi", "= 0"), (r"\atan2(1, 1) * 4 - \pi", "= 0"),
])
def test_exact_functions(src, out):
    assert ev(src) == out


def test_functions_without_a_closed_form_are_held_precisely():
    assert ev(r"\tanh(1)").startswith("= 0.7615941559557")
    assert ev(r"\erf(1)").startswith("= 0.8427007929497")
    assert ev(r"\log(2, 6)").startswith("= 2.5849625007211")


@pytest.mark.parametrize("src, message", [
    (r"\atanh(1)", "not defined"), (r"\gamma(0)", "not defined"), (r"\gamma(-1)", "not defined"),
    (r"\atan2(0, 0)", "origin"), (r"\log(1, 5)", "base other than 1"),
    (r"\log(0)", "positive"), (r"\atan2(1)", "takes"), (r"\atan2(1+i, 1)", "real arguments"),
    (r"\log(1, 2, 3)", "takes"),
])
def test_function_errors(src, message):
    fails(src, message)


def test_atan2_lexes_as_one_name_only_before_a_call_or_space():
    assert ev(r"\atan(1) 2 - \pi/2") == "= 0"
    assert ev(r"\atan2 (1, 1) * 4 - \pi") == "= 0"


def test_factorial_of_a_non_integer_is_gamma():
    assert ev(r"(1/2)! * 2 - \sqrt(\pi)") == "= 0"
    assert ev(r"(-1/2)! - \sqrt(\pi)") == "= 0"
    assert ev(r"(1/2)!") == ev(r"\gamma(3/2)")
    fails(r"(-2)!", "non-negative integer")


# --- aggregates ---


@pytest.mark.parametrize("src, out", [
    (r"\min(3, 1, 2)", "= 1"), (r"\max(⟨3, 1, 2⟩)", "= 3"), (r"\max(1/2, 0.75)", "= 3/4"),
    (r"\min(\pi, 3)", "= 3"), (r"\max({2, 9})", "= 9"), (r"\min(1..5)", "= 1"),
    (r"\mean(⟨1, 2, 4⟩)", "= 7/3"), (r"\mean(1, 2, 3)", "= 2"),
    (r"\median(⟨5, 1, 3⟩)", "= 3"), (r"\median(⟨4, 1, 3, 2⟩)", "= 5/2"),
    (r"\stdev(⟨2, 4, 4, 4, 5, 5, 7, 9⟩)", "= 2"), (r"\stdev(⟨1, 2⟩)", "= 1/2"),
    (r"\sstdev(⟨1, 3⟩) ^ 2", "= 2"),
    (r"\sort(⟨3, 1, 2⟩)", "= ⟨1, 2, 3⟩"), (r"\sort({3, 1, 2})", "= ⟨1, 2, 3⟩"),
    (r"\sort([3, 1, 2])", "= [1, 2, 3]"), (r"\sort(⟨1/2, 0.25, \pi⟩)", "= ⟨1/4, 1/2, 3.14159265358979...⟩"),
    (r"\reverse(⟨1, 2, 3⟩)", "= ⟨3, 2, 1⟩"), (r"\reverse([1, 2, 3])", "= [3, 2, 1]"),
    (r"\zip(⟨1, 2, 3⟩, ⟨4, 5⟩)", "= ⟨⟨1, 4⟩, ⟨2, 5⟩⟩"),
    (r"\enumerate(⟨7, 8⟩)", "= ⟨⟨1, 7⟩, ⟨2, 8⟩⟩"),
    (r"\count(\fn(x) x % 2 ≠ 0, 1..10)", "= 5"), (r"\count(\fn(x) x > 0, ⟨⟩)", "= 0"),
    (r"\any(\fn(x) x > 2, ⟨1, 2, 3⟩)", "= true"), (r"\all(\fn(x) x > 2, ⟨1, 2, 3⟩)", "= false"),
    (r"\any(\fn(x) x > 2, ⟨⟩)", "= false"), (r"\all(\fn(x) x > 2, ⟨⟩)", "= true"),
])
def test_aggregates(src, out):
    assert ev(src) == out


def test_any_and_all_search_infinite_ranges():
    assert ev(r"\any(\fn(x) x > 100, 1..)") == "= true"
    assert ev(r"\all(\fn(x) x < 5, 1..)") == "= false"


def test_any_and_all_short_circuit():
    assert ev(r"\any(\fn(x) 1 / (x - 2) > 0, ⟨3, 2⟩)") == "= true"


@pytest.mark.parametrize("src, message", [
    (r"\mean(⟨⟩)", "at least one"), (r"\max()", "at least one"),
    (r"\sstdev(⟨1⟩)", "at least two"), (r"\min(1, \true)", "booleans"),
    (r"\sort(⟨1, 1+i⟩)", "not ordered"), (r"\reverse({1, 2})", "no order"),
    (r"\any(\fn(x) x, ⟨1⟩)", "boolean"), (r"\zip(⟨1⟩)", "two or more"),
    (r"\sort(1..)", "infinite"), (r"\enumerate(5)", "range or collection"),
    (r"\count(\fn(x) x > 0, 1..)", "infinite"),
])
def test_aggregate_errors(src, message):
    fails(src, message)


# --- complex ---


@pytest.mark.parametrize("src, out", [
    (r"\conj(3+4i)", "= 3-4i"), (r"\conj(5)", "= 5"), (r"\conj(1+i) * (1+i)", "= 2"),
    (r"\arg(3)", "= 0"), (r"\arg(i) * 2 - \pi", "= 0"), (r"\arg(-1) - \pi", "= 0"),
    (r"\arg(1+i) * 4 - \pi", "= 0"),
    (r"\polar(2, \pi/2)", "= 2i"), (r"2∠(\pi/2)", "= 2i"), (r"2∠\pi/2", "= 2i"),
    (r"1 \angle \pi", "= -1"), (r"3∠0", "= 3"), (r"(∠)(2, \pi)", "= -2"),
    (r"(2 ∠)(\pi)", "= -2"), (r"(∠ \pi)(3)", "= -3"), (r"\map((∠ 0), ⟨1, 2⟩)", "= ⟨1, 2⟩"),
    (r"2∠\pi/2 ≈ 2i", "= true")
])
def test_complex(src, out):
    assert ev(src) == out


def test_angle_is_non_associative_and_looser_than_addition():
    with pytest.raises(ParseError, match="unexpected token"):
        ev(r"1∠2∠3")
    assert ev(r"\re(1∠(\pi/2) + \pi/2)") == "= -1"


@pytest.mark.parametrize("src, message", [
    (r"\arg(0)", "not defined at zero"), (r"\polar(1+i, 0)", "real numbers"),
    (r"\polar(1)", "takes"), (r"\conj(\true)", "booleans"),
])
def test_complex_errors(src, message):
    fails(src, message)
