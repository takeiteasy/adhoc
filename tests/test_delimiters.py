import pytest

from adhoc.driver import run_source
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import BackslashRef, BinOp, BinOperator, Call


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def parse_fails(src, message):
    with pytest.raises(ParseError, match=message):
        parse_program(src)


def test_each_delimiter_form():
    assert ev("|-3|") == "= 3"
    assert ev("⌊-5/2⌋") == "= -3"
    assert ev("⌈-5/2⌉") == "= -2"
    assert ev("⌈π⌉") == "= 4"
    assert ev("‖[3, 4]‖") == "= 5"
    assert ev("∥[3, 4]∥") == "= 5"
    assert ev("|3+4i|") == "= 5"


def test_delimited_forms_are_the_function_calls():
    for src, name in [("|x|", "abs"), ("⌊x⌋", "floor"), ("⌈x⌉", "ceil"), ("‖x‖", "norm")]:
        call = parse_program(src)
        assert isinstance(call, Call)
        assert isinstance(call.head, BackslashRef) and call.head.name == name
        assert call.span.start == 0 and call.span.end == len(src.encode())


def test_norm_of_a_complex_vector_uses_the_modulus():
    env = {}
    run_source("n = ‖[1, i]‖", env)
    assert ev("n = √2", env) == "true"


def test_bars_nest_and_juxtapose():
    assert ev("|1 - |2 - 5||") == "= 2"
    assert ev("|2||3|") == "= 6"
    assert ev("2|3|") == "= 6"
    assert ev("|3|2") == "= 6"
    assert ev("‖[1, i]‖‖[3, 4]‖ ≈ 5√2") == "= true"
    assert ev("|3 ‖[3, 4]‖ - 20|") == "= 5"


def test_bars_of_one_glyph_close_on_the_innermost():
    node = parse_program("|a||b|")
    assert isinstance(node, BinOp) and node.op is BinOperator.MUL
    assert all(isinstance(side, Call) for side in (node.lhs, node.rhs))


def test_brackets_reset_the_bar_rule():
    assert ev("|\\max(2 |3|, 1)|") == "= 6"
    assert ev("[|-1|, |-2|]") == "= [1, 2]"


def test_trailers_and_juxtaposition_after_a_closer():
    assert ev("|-3|²") == "= 9"
    assert ev("|3|!") == "= 6"
    assert ev("⌊3/2⌋²") == "= 1"
    assert ev("2⌊3/2⌋") == "= 2"
    assert ev("⌊3/2⌋⌈3/2⌉") == "= 2"


def test_delimited_forms_inside_definitions_and_sections():
    env = {}
    run_source("f(x) = |x - 1|", env)
    assert ev("f(-3)", env) == "= 4"
    assert ev("\\map(\\fn(x) ⌊x⌋, [1.5, 2.5])") == "= [1, 2]"
    assert ev("(+ |-2|)(1)") == "= 3"


def test_mismatched_and_stray_delimiters():
    parse_fails("⌋", "unexpected token `⌋`")
    parse_fails("⌊3⌉", "expected `⌋`, found `⌉`")
    parse_fails("⌊|3⌋|", "expected `\\|`, found `⌋`")
    parse_fails("(1 |2)|", "expected `\\|`, found `\\)`")


def test_unclosed_delimiters_are_incomplete_input():
    for src in ["|3", "⌊3", "‖[3, 4]", "1 + |", "⌈"]:
        with pytest.raises(IncompleteInput):
            parse_program(src)


def test_a_delimited_line_break_continues():
    assert ev("⌊\n3/2\n⌋") == "= 1"


@pytest.mark.parametrize("matrix, expected", [
    ("[1, 2; 3, 4]", "= -2"),
    ("[1, 2; 2, 4]", "= 0"),
    ("[-5;]", "= -5"),
    ("[1/2, 1; 1, 3]", "= 1/2"),
    ("[i, 0; 0, 1]", "= i"),
    ("[√2, 1; 1, √2]", "= 1"),
    ("[0, 2.; 1, 0]", "= -2.0"),
])
def test_matrix_bars_and_abs_return_the_signed_determinant(matrix, expected):
    assert ev(f"\\det({matrix})") == expected
    assert ev(f"|{matrix}|") == expected
    assert ev(f"\\abs({matrix})") == expected


def test_matrix_bars_in_functions_quotes_and_products():
    env = {}
    run_source("a = [1, 2; 3, 4]; f(x) = |x|", env)
    assert ev("|a|", env) == "= -2"
    assert ev("f(a)", env) == "= -2"
    assert ev("f(-3)", env) == "= 3"
    assert ev("|a||a|", env) == "= 4"
    assert ev("||a||", env) == "= 2"
    assert ev("\\eval(\\expr(|a|))", env) == "= -2"
    assert ev("‖a‖ ≈ √30", env) == "= true"


@pytest.mark.parametrize("tensor, message", [
    ("[1, 2]", "needs a matrix"),
    ("[1, 2, 3; 4, 5, 6]", "square matrix, got shape 2x3"),
    ("[[1, 2; 3, 4], [5, 6; 7, 8]]", "needs a matrix"),
])
@pytest.mark.parametrize("form", ["|{}|", "\\abs({})"])
def test_abs_rejects_invalid_tensor_shapes_at_the_call(tensor, message, form):
    call = form.format(tensor)
    source = f"π + {call}"
    with pytest.raises(EvalError, match=message) as error:
        run_source(source, {})
    assert error.value.span == Span(len("π + ".encode()), len(source.encode()))
