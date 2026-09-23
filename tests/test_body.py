import pytest

from adhoc.driver import compile_source, execute, run_source
from adhoc.expression import ExpressionValue
from adhoc.output import render_eval_error
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import Seq


def test_named_body_preserves_all_statements_and_round_trips():
    env = {}
    run_source("f(x) = y = x + 1; y^2", env)
    assert run_source(r"q = \body(f)", env) == [
        r"q = \expr((y = (x + 1); (y ^ 2)))"
    ]
    assert isinstance(env["q"], ExpressionValue)
    assert isinstance(env["q"].node, Seq)
    assert run_source(r"\eval(q, x=3)", env) == ["= 16"]
    with pytest.raises(EvalError, match="`y` is not bound"):
        run_source("y", env)
    run_source(r"r = \expr((y = x + 1; y^2))", env)
    assert env["q"] == env["r"]


def test_reflected_body_uses_eval_scope_not_function_closure():
    env = {}
    run_source(r"\mk = \fn(n) \fn(x) x + n", env)
    run_source(r"\five = \mk(5)", env)
    run_source(r"q = \body(\five)", env)
    with pytest.raises(EvalError, match="`n` is not bound"):
        run_source(r"\eval(q, x=1)", env)
    assert run_source(r"\eval(q, x=1, n=10)", env) == ["= 11"]


def test_single_body_and_explicit_statement_quote_round_trip():
    env = {}
    run_source(r"g = \fn(z) z + 2", env)
    display = run_source(r"\body(g)", env)[0][2:]
    assert display == r"\expr(((z + 2);))"
    run_source(r"q = \body(g); r = " + display, env)
    assert env["q"] == env["r"]
    assert run_source(r"\eval(q, z=4)", env) == ["= 6"]
    assert run_source(r"\eval(\expr((a=2; a+3)))") == ["= 5"]
    assert run_source("\\eval(\\expr((a=2\na+3)))") == ["= 5"]
    assert run_source(r"\eval(\body(\eval(\expr(\fn(x) x+1))), x=2)") == ["= 3"]


def test_body_errors_are_typed_and_point_at_call():
    for source in (r"\body(2)", r"\body(\sqrt)", r'\body(\py("math.sqrt"))'):
        with pytest.raises(EvalError, match="needs a user-defined function") as failure:
            run_source(source)
        assert failure.value.span == Span(0, len(source.encode()))


def test_reflected_error_uses_original_source_and_spelling():
    source = r"\alias \alpha, α; f(x) = α + x"
    env = {}
    execute(compile_source(source), env)
    run_source(r"q = \body(f)", env)
    with pytest.raises(EvalError) as failure:
        run_source(r"\eval(q, x=1)", env)
    error = failure.value
    assert error.msg == "`α` is not bound"
    start = len(source[:source.index("α +")].encode())
    assert error.span == Span(start, start + len("α".encode()))
    assert error.source == source
    assert "α + x" in render_eval_error(r"\eval(q, x=1)", error)


def test_reflection_retains_source_spellings_and_ast_spans():
    source = r"\alias \alpha, α; f(α) = α + 1"
    env = {}
    execute(compile_source(source), env)
    run_source(r"q = \body(f)", env)
    assert r"α + 1" in run_source("q", env)[0]
    assert env["q"].node.statements[0].span.start == len(source[:source.index("α +")].encode())
