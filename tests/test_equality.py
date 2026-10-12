import pytest

from adhoc.driver import run_source
from adhoc.expression import ExpressionValue, show
from adhoc.parser import IncompleteInput, ParseError, _Parser, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import Assign, Equation, FuncDef, Seq


@pytest.mark.parametrize("source, expected", [
    ("1+2=3", "= true"),
    ("2^3=9", "= false"),
    ("0.1+0.2=3/10", "= true"),
    ("1.=1", "= true"),
    ("√2√2=2", "= true"),
    ('"hi"="hi"', "= true"),
    ('"hi"=3', "= false"),
    ("⟨1,2⟩=⟨1,2⟩", "= true"),
    ("⟨1,2⟩=⟨2,1⟩", "= false"),
    ("[1,2]=[1,2]", "= true"),
    ("[1,2]=[1,2;]", "= false"),
    ("{1,2}={2,1}", "= true"),
    (r"(\true=\true)", "= true"),
    ("1=1 ∧ 2=3", "= false"),
    ("1=2 ∨ 3=3", "= true"),
    ("¬1=2", "= true"),
    ("(1<2)=\\true", "= true"),
    ("1=(2=2)", "= true"),
    (r"1=2 ∧ \missing=3", "= false"),
    ("1=1 ? 10 : 1/0", "= 10"),
    ("{1=2: 10; 1=1: 20; 30}", "= 20"),
    (r"∀(x=1..3) x=x", "= true"),
    (r"\sum(i=1..3) i=2 ? i : 0", "= 2"),
])
def test_value_equality_and_conditions(source, expected):
    assert run_source(source, {})[-1] == expected


def test_issue_example_and_equality_without_binding():
    env = {}
    assert run_source("x=3; (x^2=9) ? 10 : 20", env) == ["x = 3", "= 10"]
    assert run_source("(x=4)", env) == ["= false"]
    assert env["x"] == 3
    with pytest.raises(EvalError, match="`y` is not bound"):
        run_source("(y=4)", env)
    assert "y" not in env


def test_binding_and_definition_priority():
    env = {}
    assert run_source("x=3; x=3; x=4; p=x=3", env) == [
        "x = 3", "true", "false", "p = true",
    ]
    assert env["p"] is True
    assert run_source("f(x)=(x=3)\nf(3)\n(f(4)=\\false)", env) == [
        "f = <fn f(x)>", "= true", "= true",
    ]
    assert isinstance(parse_program("f(x)=3"), FuncDef)
    assert isinstance(parse_program("(f(e)=3)"), Equation)


def test_named_and_positional_equality_arguments():
    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return 10

    env = {"record": record, "x": 3}
    assert run_source(r"\record(p=x=3); \record((x=3)); \record(x=3)", env) == [
        "= 10", "= 10", "= 10",
    ]
    assert calls == [((), {"p": True}), ((True,), {}), ((), {"x": 3})]
    assert env["x"] == 3
    assert run_source(r"\eval(`(p), p=x=3)", env) == ["= true"]


@pytest.mark.parametrize("source, kind", [
    ("(x=3)", Equation),
    ("(\nx=3)", Equation),
    ("(x=\n3)", Equation),
    ("(x=1+\n2)", Equation),
    ("(x=3;)", Assign),
    ("(x=3\n)", Assign),
    ("(x=3; x)", Seq),
    ("(x=3\nx)", Seq),
    ("(x=1=2;)", Assign),
    (r"(\let x=3)", Assign),
    ("(f(x)=3\n)", FuncDef),
])
def test_parenthesized_expression_or_statement_group(source, kind):
    assert isinstance(parse_program(source), kind)


def test_statement_groups_keep_binding_effects():
    env = {}
    assert run_source("(x=3;); (x=3); (x=4\n)", env) == [
        "x = 3", "= true", "false",
    ]
    assert env["x"] == 3


@pytest.mark.parametrize("source", [
    "1=2=3", "(x=1=2)", "(x=\n1=2)", "1<2=3", "1=2<3",
    "1≠2=3", "1=2≠3", "1∈{1}=\\true",
    "(1=2=)", r"\expr(x=2=3)",
])
def test_comparisons_do_not_chain(source):
    with pytest.raises(ParseError, match="does not chain"):
        parse_program(source)


@pytest.mark.parametrize("source", ["(=)", "(= 3)", "(3 =)", r"\map(=, ⟨1⟩)"])
def test_equality_operator_values_and_sections_are_excluded(source):
    with pytest.raises(ParseError):
        parse_program(source)


@pytest.mark.parametrize("source", ["1=", "(1=", "1=1 ?"])
def test_incomplete_equality_continues_in_the_repl(source):
    with pytest.raises(IncompleteInput):
        parse_program(source)


def test_equality_evaluates_each_side_once_in_order():
    calls = []

    def record(value):
        calls.append(value)
        return value

    assert run_source(r"(\record(1)=\record(2))", {"record": record}) == ["= false"]
    assert calls == [1, 2]


def test_equality_errors_keep_operand_spans_and_source():
    source = "(α=3)"
    with pytest.raises(EvalError) as failure:
        run_source(source, {})
    assert failure.value.span == Span(1, 3)
    source = r"q=\expr((α=3) ∧ \true)"
    env = {}
    run_source(source, env)
    with pytest.raises(EvalError) as failure:
        run_source(r"\eval(q)", env)
    start = len(source[:source.index("α")].encode())
    assert failure.value.span == Span(start, start + 2)
    assert failure.value.source == source


@pytest.mark.parametrize("source", [
    "(x=3)", "(x=3) ∧ (y=4)", "(x^2=9) ? 10 : 20",
    "f((x=3))", "p=x=3", "f(p=x=3)",
    "(x=3;)", "(x=3;) + 1", "f((x=3;))", "(x=3; x)",
    "f(x)=(x=3)", "f(x)=y=x", "f(x)=(y=x; y)",
    r"\expr(x=3)", r"\expr((x=3) ∧ (y=4))",
    r"\expr(\true ∧ \false = \false)",
    r"\expr((x=3;))", r"\expr((f(x)=3" + "\n))",
])
def test_equality_and_statement_display_round_trip(source):
    node = parse_program(source)
    displayed = parse_program(show(node))
    assert ExpressionValue(node, source) == ExpressionValue(displayed, show(node))


@pytest.mark.parametrize("quote", [
    r"\expr(\true ∧ \false = \false)",
    r"\expr((\true ∧ \false = \false))",
    r"\expr(\true ? 1 : 2 = 1)",
    "\\expr((x=1+\n2))",
    "\\expr((1<2=\n\\true))",
    "\\expr((1<\n2=\\true))",
])
def test_equation_quotes_preserve_full_sides_and_newline_continuations(quote):
    node = parse_program(quote)
    assert isinstance(node.body, Equation)
    assert not node.statement_body
    assert run_source(r"\eval(" + quote + ", x=3)", {}) == ["= true"]


def test_nested_quoted_equality_and_solver_inputs():
    assert run_source(r"\eval(\expr((x=3) ∧ (y=4)), x=3, y=4)", {}) == ["= true"]
    assert run_source(r"\solve(\expr((x^2=9)))", {}) == ["= {-3, 3}"]
    assert run_source(r"\eval(\expr((x=3; x)))", {}) == ["= 3"]


@pytest.mark.parametrize("closing", [")", ");"])
def test_nested_comparison_errors_do_not_reparse_exponentially(monkeypatch, closing):
    original = _Parser.expr
    calls = 0

    def bounded_expression(parser):
        nonlocal calls
        calls += 1
        assert calls <= 100
        return original(parser)

    monkeypatch.setattr(_Parser, "expr", bounded_expression)
    with pytest.raises(ParseError, match="does not chain"):
        parse_program("(" * 24 + "1=2=3" + closing * 24)


def test_equality_and_custom_comparison_precedence():
    source = r"\infix(9) \same(a,b)=(a=b)" + "\n"
    assert run_source(source + r"(1 \same 1)=\true", {})[-1] == "= true"
    with pytest.raises(ParseError, match="does not chain"):
        parse_program(source + r"1=2 \same 3")
