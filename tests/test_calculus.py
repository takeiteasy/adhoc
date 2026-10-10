import math

import pytest

from adhoc.driver import run_source
from adhoc.expression import show
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc import runtime


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def num(src, env=None):
    text = ev(src, env)
    assert text.startswith("= ")
    return complex(text[2:].replace("i", "j")) if "i" in text else float(text[2:])


def fails(src, message, env=None):
    with pytest.raises(EvalError, match=message):
        run_source(src, {} if env is None else env)


def roundtrip(src):
    shown = show(parse_program(src))
    assert show(parse_program(shown)) == shown
    return shown


# --- \diff ---


def test_diff_of_smooth_functions():
    assert num(r"\diff(x=1) \sin(x)") == pytest.approx(math.cos(1), abs=1e-9)
    assert num("∂(x=2) x^3") == pytest.approx(12, abs=1e-8)
    assert num(r"\diff(x=0) e^x") == pytest.approx(1, abs=1e-9)
    assert num(r"\diff(x=0.001) √x") == pytest.approx(1 / (2 * math.sqrt(0.001)), rel=1e-8)


def test_diff_of_a_complex_body():
    assert num(r"\diff(x=1) x*i") == pytest.approx(1j, abs=1e-9)


def test_diff_never_evaluates_at_the_anchor():
    probes = []

    def body(x):
        assert x != 0
        probes.append(x)
        return x * x

    assert num(r"\diff(x=0) f(x)", {"f": body}) == pytest.approx(0, abs=1e-9)
    assert any(x < 0 for x in probes) and any(x > 0 for x in probes)


@pytest.mark.parametrize("body", [r"|x|", "x < 0 ? 2x : x", "x < 0 ? -1 : 1"])
def test_diff_rejects_kinks_and_jumps(body):
    fails(r"\diff(x=0) " + body, "derivative does not exist")
    fails("f(x) = " + body + "\nf'(0.)", "derivative does not exist")


@pytest.mark.parametrize("order, body", [(2, "x*|x|"), (3, "|x|"), (3, "|x|^3"),
                                         (4, "x*|x|"), (5, "x < 0 ? -1 : 1")])
def test_higher_derivatives_check_lower_orders(order, body):
    fails(rf"\diff(x=0, {order}) " + body, "derivative does not exist")


@pytest.mark.parametrize("order", range(3, 7))
def test_numeric_higher_derivatives_of_polynomials(order):
    expected = math.factorial(order + 1)
    assert num(rf"\diff(x=1, {order}) x^{order + 1}") == pytest.approx(expected, rel=1e-3)
    assert num(rf"∂(x=0, {order}) x^{order}") == pytest.approx(math.factorial(order), rel=1e-3)
    primes = "'" * order
    assert num(f"f(x) = (y = x; y^{order + 1})\nf{primes}(1)") == pytest.approx(expected, rel=1e-3)
    assert num(f"f(x) = x^{order + 1}\nf{primes}(1.)") == pytest.approx(expected, rel=1e-3)


@pytest.mark.parametrize("order", range(3, 7))
def test_numeric_higher_derivatives_of_trigonometric_functions(order):
    expected = math.sin(1 + order * math.pi / 2)
    assert num(rf"\diff(x=1, {order}) \sin(x)") == pytest.approx(expected, abs=1e-3)
    assert num(r"\sin" + "'" * order + "(1)") == pytest.approx(expected, abs=1e-3)


def test_higher_derivatives_support_complex_bodies_and_zero_results():
    assert num(r"∂(x=1, 3) i*x^4") == pytest.approx(24j, abs=1e-3)
    assert num(r"\diff(x=0, 3) x^4") == pytest.approx(0, abs=1e-3)
    assert num(r"\diff(x=0, 6) \cos(x)") == pytest.approx(-1, abs=1e-3)


def test_diff_order_and_point_use_the_outer_scope_once():
    calls = []

    def point():
        calls.append("point")
        return 1

    def order():
        calls.append("order")
        return 3

    assert num(r"\diff(x=a(), n()) x^4", {"a": point, "n": order}) == pytest.approx(24, abs=1e-3)
    assert calls == ["point", "order"]
    env = {"x": 3}
    assert num(r"∂(x=1, x) x^4", env) == pytest.approx(24, abs=1e-3)
    assert env["x"] == 3


@pytest.mark.parametrize("order", ["0", "-1", "1.", "3/2", r"\true", "i", '"three"'])
def test_diff_rejects_invalid_orders(order):
    fails(rf"\diff(x=0, {order}) x^3", "positive integer")


def test_diff_resource_limits_precede_body_evaluation(monkeypatch):
    def body(x):
        pytest.fail("oversized stencil evaluates the body")

    fails(r"\diff(x=0, 30) f(x)", "32-point resource limit", {"f": body})
    fails(r"\diff(x=0, 10^100) f(x)", "32-point resource limit", {"f": body})
    fails(r"\sin" + "'" * 30 + "(0)", "32-point resource limit")
    monkeypatch.setattr(runtime, "MAX_DIFF_SAMPLES", 3)
    fails(r"\diff(x=0) x^2", "3-evaluation resource limit")


def test_diff_reports_nonfinite_bodies_and_unrepresentable_spacing():
    fails(r"\diff(x=0) \inf", "body is not finite")
    fails(r"\diff(x=0) 1/x", "did not converge")
    fails(r"\diff(x=5e-324) x", "spacing is not representable")
    fails(r"\diff(x=1e100, 4) 1", "scale is not representable")


def test_first_order_ignores_an_isolated_anchor_value():
    assert num(r"\diff(x=0) f(x)", {"f": lambda x: 99 if x == 0 else x}) == pytest.approx(1)


def test_numeric_diff_preserves_written_alias_and_error_span():
    source = "∂(x=0) |x|"
    with pytest.raises(EvalError, match="∂: derivative does not exist") as error:
        run_source(source)
    assert error.value.span == parse_program(source).span


def test_diff_uses_the_written_spelling_and_binder_rules():
    fails(r"\diff(π=1) π", "`π` is protected")
    fails(r"∂(x=i) x", r"∂ needs a finite real point")


def test_diff_usage_errors():
    with pytest.raises(ParseError, match=r"\\diff takes a binder"):
        parse_program(r"\diff(1)")
    with pytest.raises(ParseError, match=r"\\int takes a binder"):
        parse_program(r"\int(1)")


# --- \int ---


def test_int_of_smooth_functions():
    assert num(r"∫(x=0..π) \sin(x)") == pytest.approx(2, abs=1e-11)
    assert num(r"\int(x=0..1) x^2") == pytest.approx(1 / 3, abs=1e-12)
    assert num(r"\int(x=0..1) \sin(x)/x") == pytest.approx(0.9460830703671830, abs=1e-11)


def test_int_endpoint_singularity_and_infinite_range():
    assert num(r"∫(x=0..1) 1/√x") == pytest.approx(2, abs=1e-9)
    assert num(r"∫(x=0..) e^(-x)") == pytest.approx(1, abs=1e-11)
    assert num(r"∫(x=1..) 1/x^2") == pytest.approx(1, abs=1e-10)


def test_int_reversed_and_empty_ranges():
    assert num(r"∫(x=1..0) x") == pytest.approx(-0.5, abs=1e-12)
    assert num(r"∫(x=2..2) x") == 0


def test_int_of_a_complex_body():
    assert num(r"∫(x=0..1) x*i") == pytest.approx(0.5j, abs=1e-12)


def test_int_errors():
    fails(r"∫(x=1..) 1", "did not converge")
    fails(r"\int(x=1,3..9) x", "plain range")
    fails(r"\int(x=5) x", "integrates over a range")
    fails(r"\int(x=0..1) x > 0", "numbers")
    fails(r"\int(π=0..1) π", "protected")


# --- f' and f'' ---


def test_prime_on_a_function_is_the_derivative():
    env = {}
    run_source("f(x) = x^3", env)
    assert ev("f'(2)", env) == "= 12"
    assert ev("f''(2)", env) == "= 12"
    assert num("f'(2.)", env) == pytest.approx(12, abs=1e-8)
    assert num("f''(2.)", env) == pytest.approx(12, abs=1e-5)
    assert ev("f'", env) == "= <fn f′>"
    assert ev("f''", env) == "= <fn f′′>"


def test_prime_on_builtins_lambdas_and_compositions():
    assert num(r"\sin'(0)") == pytest.approx(1, abs=1e-9)
    assert num(r"(x -> x^2)'(3)") == pytest.approx(6, abs=1e-8)
    assert num(r"(\sin ∘ \cos)'(0)") == pytest.approx(0, abs=1e-9)


def test_derivative_values_pass_around():
    env = {}
    run_source("f(x) = x^2", env)
    assert ev(r"\map(f', [1, 2])", env) == "= [2, 4]"
    assert ev(r"\map(f', [1., 2.])", env).startswith("= [1.99999999")


def test_prime_is_exact_at_exact_points_only_for_bridgeable_bodies():
    env = {}
    run_source("f(x) = x^3\ng(x) = (y = x; y^3)", env)
    assert ev("f'(1/2)", env) == "= 3/4"
    assert ev("f'(i)", env) == "= -3"
    assert ev("g'(2)", env).startswith("= 11.99999")
    assert ev(r"(x ↦ \sin(x))'(0)", env) == "= 1"


def test_third_derivative_is_exact_or_numeric():
    env = {}
    run_source("f(x) = x^4\ng(x) = (y = x; y^4)", env)
    assert ev("f'''(1)", env) == "= 24"
    assert ev("f''''(1)", env) == "= 24"
    assert ev("f'''", env) == "= <fn f′′′>"
    assert num("f'''(1.)", env) == pytest.approx(24, abs=1e-3)
    assert num("g'''(1)", env) == pytest.approx(24, abs=1e-3)
    assert num(r"\sin'''(1)", env) == pytest.approx(-math.cos(1), abs=1e-3)


def test_prime_on_tensors_still_transposes():
    assert ev("m = [1, 2; 3, 4]; m'") == "= [1, 3; 2, 4]"
    assert ev("m = [1, 2; 3, 4]; mᵀ") == "= [1, 3; 2, 4]"
    assert ev("m = [1, 2; 3, 4]; m'(2)") == "= [2, 6; 4, 8]"


def test_transpose_glyph_on_a_function_is_an_error():
    env = {}
    run_source("f(x) = x", env)
    fails("fᵀ", "transposes tensors", env)


def test_derivative_arity_and_point_errors():
    env = {}
    run_source("f(x) = x", env)
    fails("f'(1, 2)", "takes 1 argument", env)
    fails(r"\sin'(i)", "finite real point", env)


# --- quotes and reduction ---


def test_calculus_nodes_round_trip():
    assert roundtrip(r"\diff(x=1) x^2") == r"(\diff(x=1) (x ^ 2))"
    assert roundtrip("∂(x=1) x") == "(∂(x=1) x)"
    assert roundtrip(r"\diff(x=1, 3) x^4") == r"(\diff(x=1, 3) (x ^ 4))"
    assert roundtrip("∂(x=1, n) x") == "(∂(x=1, n) x)"
    assert roundtrip(r"∫(x=0..1) x") == "(∫(x=(0..1)) x)"
    assert roundtrip("f''") == "f''"
    assert roundtrip("fᵀ") == "fᵀ"


def test_eval_of_a_quoted_derivative():
    assert num(r"q = \expr(\diff(x=a) x^2); \eval(q, a=3)") == pytest.approx(6, abs=1e-8)
    assert num(r"q = \expr(∂(x=a, n) x^4); \eval(q, a=1, n=3)") == pytest.approx(24, abs=1e-3)


def test_reduce_keeps_new_binders_capture_free():
    assert ev(r"\reduce(\expr((\fn(y) \int(x=0..1) x + y)(x)))") == \
        r"= \expr((\int(\reduce_a=(0..1)) (\reduce_a + x)))"
