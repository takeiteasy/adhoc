import pytest

from adhoc.driver import run_source
from adhoc.runtime import EvalError


def define(source):
    env = {}
    run_source(source, env)
    return env


def test_function_definition_and_application():
    env = define("f(x) = x^2 + 1")
    assert run_source("f(3)", env) == ["= 10"]


def test_multi_statement_function_body_returns_last_value():
    env = define("f(a, b) = c = ab; cc")
    assert run_source("f(3, 4)", env) == ["= 144"]
    with pytest.raises(EvalError, match="`c` is not bound"):
        run_source("c", env)


def test_function_parameters_and_writes_are_local():
    env = define("x = 100")
    run_source("f(x) = y = x + 1; y", env)
    assert run_source("f(4)", env) == ["= 5"]
    assert run_source("x", env) == ["= 100"]
    with pytest.raises(EvalError, match="`y` is not bound"):
        run_source("y", env)


def test_functions_are_first_class_and_displayable():
    env = define("f(x) = x + 1")
    assert run_source("g = f", env) == ["g = <fn f(x)>"]
    assert run_source("g(4)", env) == ["= 5"]
    assert run_source("f = f", env) == ["true"]


def test_function_arity_is_checked():
    env = define("f(x, y) = x + y")
    for source in ("f(1)", "f(1, 2, 3)"):
        with pytest.raises(EvalError) as error:
            run_source(source, env)
        assert error.value.msg.startswith("f takes 2 arguments")


def test_recursive_factorial():
    env = define("f(n) = n <= 1 ? 1 : n * f(n - 1)")
    assert run_source("f(5)", env) == ["= 120"]


def test_escaped_names_support_multi_character_functions():
    env = define("\\fact(n) = n <= 1 ? 1 : n * \\fact(n - 1)")
    assert run_source("\\fact(5)", env) == ["= 120"]
    assert run_source("\\fact", env) == ["= <fn \\fact(n)>"]


def test_escaped_names_support_multi_character_variables():
    env = {}
    assert run_source("\\bar = 100", env) == ["\\bar = 100"]
    assert run_source("\\foo = 200", env) == ["\\foo = 200"]
    assert run_source("\\foobar = \\foo\\bar", env) == ["\\foobar = 20000"]
    assert run_source("\\foobar", env) == ["= 20000"]


def test_function_locals_bind_once():
    # The binding rule is frame-local but immutable: a repeat `=` on a bound local
    # compares (silently inside a body), never rebinds — fresh names carry new values.
    env = define("f() = x = 1; x = 1; x")
    assert run_source("f()", env) == ["= 1"]
    env = define("g() = x = 1; x = 2; x")
    assert run_source("g()", env) == ["= 1"]  # the mismatch compares false, binds nothing


def test_piecewise_function_and_lazy_branch():
    env = define("m(x) = x >= 0 ? x : -x")
    assert run_source("m(-5)", env) == ["= 5"]
    assert run_source("m(5)", env) == ["= 5"]


def test_ternary_is_lazy():
    # Only the selected branch evaluates; the untaken branch's unbound name
    # never fails.
    env = {}
    assert run_source("1 > 2 ? \\nope : 7", env) == ["= 7"]


def test_group_branch_is_lazy_and_binds_into_the_frame():
    # A parenthesized group is the multi-statement branch: it evaluates in the
    # frame it lands in (binds are frame-local), and its value is the last
    # statement's value.
    env = {}
    assert run_source("1 < 2 ? (x = 4\nx + 1) : 99", env) == ["= 5"]
    assert run_source("x", env) == ["= 4"]
    assert run_source("1 > 2 ? (x = 9\nx) : 11", env) == ["= 11"]
    assert run_source("x", env) == ["= 4"]


def test_comparisons_return_booleans_and_reject_arithmetic():
    env = {}
    assert run_source("1 < 2", env) == ["= true"]
    assert run_source("2 >= 2", env) == ["= true"]
    with pytest.raises(EvalError, match="booleans are not numbers"):
        run_source("(1 < 2) + 1", env)
