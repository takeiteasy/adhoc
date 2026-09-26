import math

import pytest

from adhoc.driver import run_source
from adhoc.expression import show
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError


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
    assert num(r"\diff(x=0) x^2") == pytest.approx(0, abs=1e-9)


def test_diff_jump_does_not_converge():
    fails(r"\diff(x=0) x < 0 ? -1 : 1", "did not converge")


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
    assert num("f'(2)", env) == pytest.approx(12, abs=1e-8)
    assert num("f''(2)", env) == pytest.approx(12, abs=1e-5)
    assert ev("f'", env) == "= <fn f′>"
    assert ev("f''", env) == "= <fn f′′>"


def test_prime_on_builtins_lambdas_and_compositions():
    assert num(r"\sin'(0)") == pytest.approx(1, abs=1e-9)
    assert num(r"(x -> x^2)'(3)") == pytest.approx(6, abs=1e-8)
    assert num(r"(\sin ∘ \cos)'(0)") == pytest.approx(0, abs=1e-9)


def test_derivative_values_pass_around():
    env = {}
    run_source("f(x) = x^2", env)
    assert ev(r"\map(f', [1, 2])", env).startswith("= [1.99999999")


def test_third_derivative_is_an_error():
    env = {}
    run_source("f(x) = x^4", env)
    fails("f'''(1)", "above the second order", env)


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
    fails("f'(i)", "finite real point", env)


# --- quotes and reduction ---


def test_calculus_nodes_round_trip():
    assert roundtrip(r"\diff(x=1) x^2") == r"(\diff(x=1) (x ^ 2))"
    assert roundtrip("∂(x=1) x") == "(∂(x=1) x)"
    assert roundtrip(r"∫(x=0..1) x") == "(∫(x=(0..1)) x)"
    assert roundtrip("f''") == "f''"
    assert roundtrip("fᵀ") == "fᵀ"


def test_eval_of_a_quoted_derivative():
    assert num(r"q = \expr(\diff(x=a) x^2); \eval(q, a=3)") == pytest.approx(6, abs=1e-8)


def test_reduce_keeps_new_binders_capture_free():
    assert ev(r"\reduce(\expr((\fn(y) \int(x=0..1) x + y)(x)))") == \
        r"= \expr((\int(\reduce_a=(0..1)) (\reduce_a + x)))"
