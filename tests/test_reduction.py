import pytest

from adhoc.driver import run_source
from adhoc.expression import ExpressionValue
from adhoc.parser import parse_program
from adhoc.reduction import ReduceError, reduce_expression
from adhoc.runtime import EvalError
from adhoc.span import Span


def test_reduce_beta_and_evaluate_result():
    env = {}
    assert run_source(r"q = \reduce(\expr((\fn(x, y) x + y)(1, 2)))", env) == [
        r"q = \expr((1 + 2))"
    ]
    assert run_source(r"\eval(q)", env) == ["= 3"]
    assert run_source(r"\reduce(\expr((\fn() 7)()))") == [r"= \expr(7)"]


def test_reduce_uses_normal_order_and_reaches_full_normal_form():
    source = r"\reduce(\expr((\fn(x) 1)((\fn(z) z(z))(\fn(z) z(z)))))"
    assert run_source(source) == [r"= \expr(1)"]
    assert run_source(r"\reduce(\expr(\fn(x) (\fn(y) y)(x)))") == [
        r"= \expr((\fn(x) x))"
    ]


def test_reduce_avoids_capture_and_keeps_free_names():
    env = {}
    display = run_source(r"q = \reduce(\expr((\fn(x) \fn(y) x)(y)))", env)[0]
    assert display == r"q = \expr((\fn(\reduce_a) y))"
    run_source(r"r = \expr(\fn(\reduce_a) y)", env)
    assert env["q"] == env["r"]
    assert run_source(r"\eval(q, y=3)(5)", env) == ["= 3"]


def test_reduce_preserves_outer_binders_and_source_spellings():
    assert run_source(r"\reduce(\expr(\fn(y) (\fn(x) \fn(y) x)(y)))") == [
        r"= \expr((\fn(y) (\fn(\reduce_a) y)))"
    ]
    source = r"\alias \arg, ξ; \reduce(\expr((\fn(ξ) ξ)(2)))"
    assert run_source(source) == [r"= \expr(2)"]
    assert run_source(r"\reduce(\expr((\fn(x) \fn(y) x)(\reduce_a)))") == [
        r"= \expr((\fn(y) \reduce_a))"
    ]


def test_reduced_term_retains_the_quote_source_and_spans():
    source = r"q = \reduce(\expr((\fn(x) x+y)(2)))"
    env = {}
    run_source(source, env)
    with pytest.raises(EvalError, match="`y` is not bound") as failure:
        run_source(r"\eval(q)", env)
    assert failure.value.source == source
    assert failure.value.span == Span(source.index("y"), source.index("y") + 1)


def test_reduce_traverses_expressions_and_respects_other_binders():
    assert run_source(r"\reduce(\expr(1 + (\fn(x) x + 2)(3)))") == [
        r"= \expr((1 + (3 + 2)))"
    ]
    assert run_source(r"\reduce(\expr((\fn(x) \sum(i=1..2) x+i)(i)))") == [
        r"= \expr((\sum(\reduce_a=(1..2)) (i + \reduce_a)))"
    ]
    assert run_source(r"\reduce(\expr(\expr((\fn(x) x)(2))))") == [
        r"= \expr(\expr((\fn(x) x)(2)))"
    ]


def test_reduce_rejects_invalid_terms_at_call_span():
    sources = [
        (r"\reduce(2)", "needs an expression value"),
        (r"\reduce(\expr((x=1; x)))", "needs an expression quote"),
        (r"\reduce(\expr((\fn(x) x)()))", "lambda takes 1 arguments, got 0"),
        (r"\reduce(\expr((\fn(x) x)(x=2)))", "keyword arguments"),
    ]
    for source, message in sources:
        with pytest.raises(EvalError, match=message) as failure:
            run_source(source)
        assert failure.value.span == Span(0, len(source.encode()))

    source = r"\fn(x) (y=1; x)"
    with pytest.raises(ReduceError, match="without statements"):
        reduce_expression(ExpressionValue(parse_program(source), source))


def test_reduce_has_a_typed_step_cap():
    source = r"\reduce(\expr((\fn(x) x(x))(\fn(x) x(x))))"
    with pytest.raises(EvalError, match="exceeded 10000 beta steps") as failure:
        run_source(source)
    assert failure.value.span == Span(0, len(source.encode()))


def test_church_numeral_reduces_and_matches_eager_application():
    two = r"(\fn(f) \fn(x) f(f(x)))"
    term = rf"{two}(\fn(v) v+1)(0)"
    env = {}
    assert run_source(rf"q = \reduce(\expr({term}))", env) == [
        r"q = \expr(((0 + 1) + 1))"
    ]
    assert run_source(r"\eval(q)", env) == run_source(term, env) == ["= 2"]
