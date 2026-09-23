import pytest

from adhoc.driver import compile_source, execute, run_source
from adhoc.expression import ExpressionValue
from adhoc.output import render_eval_error
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span


def test_quote_forms_capture_without_evaluation():
    env = {}
    assert run_source(r"q = \expr(x^2 - 4); r = `(x^2 - 4)", env) == [
        r"q = \expr(((x ^ 2) - 4))", r"r = \expr(((x ^ 2) - 4))"
    ]
    assert isinstance(env["q"], ExpressionValue)
    assert env["q"] == env["r"]
    assert run_source(r"\eval(q, x=3)", env) == ["= 5"]


def test_eval_reads_current_scope_and_binding_values_use_caller_scope():
    env = {}
    assert run_source(r"x=10; y=4; q=\expr(x+y)", env)[-1].startswith("q = ")
    assert run_source(r"\eval(q)", env) == ["= 14"]
    assert run_source(r"\eval(q, x=y+1, y=x)", env) == ["= 15"]
    assert env["x"] == 10 and env["y"] == 4


def test_eval_expression_and_string_result():
    assert run_source(r'\eval(\expr("hi"))') == ['= "hi"']
    assert run_source(r"\eval(`(2+3))") == ["= 5"]
    assert run_source(r"\eval(\expr(\fn(x) x+1))(2)") == ["= 3"]


def test_quote_display_round_trips_with_structure_and_spellings():
    sources = [
        r"\expr((x+1)^2)", r"\expr(π+1)", r"\expr(\sum(i=1..3) i)",
        r"\expr(\fn(x) x+1)", r"\expr(x ? 1 : 2)",
        r"\expr(\eval(\expr(x+1), x=2))",
    ]
    for source in sources:
        env = {}
        display = run_source(source, env)[0][2:]
        run_source("q = " + source, env)
        run_source("r = " + display, env)
        assert env["q"] == env["r"]


def test_expression_equality_ignores_spans_and_alias_spelling():
    env = {}
    assert run_source(r"q = \expr(π+1); q = \expr(\pi + 1)", env)[-1] == "true"
    assert run_source(r"q = \expr(π+2)", env) == ["false"]


def test_quote_rejects_statements_and_eval_rejects_bad_arguments():
    for source in (r"\expr(x=2; x+1)", r"`(x=2)"):
        with pytest.raises(ParseError):
            parse_program(source)
    with pytest.raises(ParseError, match="one expression value"):
        parse_program(r"\eval()")
    with pytest.raises(EvalError, match="needs an expression value"):
        run_source(r"\eval(2)")
    with pytest.raises(EvalError, match="protected"):
        run_source(r"\eval(\expr(\pi), \pi=3)")
    assert run_source(r"\eval(\expr(i), i=5)") == ["= 5"]


def test_eval_errors_point_to_original_quote_source():
    source = r"q = \expr(1/x)"
    env = {}
    execute(compile_source(source), env)
    with pytest.raises(EvalError) as failure:
        run_source(r"\eval(q, x=0)", env)
    error = failure.value
    assert error.span == Span(source.index("1/x"), source.index("1/x") + 3)
    assert error.source == source
    assert "1/x" in render_eval_error(r"\eval(q, x=0)", error)


def test_quote_inside_function_and_fold_uses_its_source():
    env = {}
    run_source(r"f(x)=\expr(x+1)", env)
    assert run_source(r"\eval(f(2), x=4)", env) == ["= 5"]
    assert run_source(r"\sum(i=1..2) \eval(\expr(i), i=i)") == ["= 3"]
