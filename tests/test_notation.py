import pytest

from adhoc.driver import run_source
from adhoc.lexer import Ident, tokenize
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.expression import show


def ev(src):
    return run_source(src, {})[-1]


def fails(src, message):
    with pytest.raises(EvalError, match=message):
        run_source(src, {})


def roundtrip(src):
    shown = show(parse_program(src))
    assert show(parse_program(shown)) == shown
    return shown


# --- subscripted names ---


def test_subscript_lexes_as_one_identifier_with_byte_span():
    x, y = tokenize("x₁ y")[:2]
    assert (x.ch, x.span.start, x.span.end) == ("x₁", 0, 4)
    assert (y.ch, y.span.start) == ("y", 5)
    assert tokenize("a₂₃")[0].ch == "a₂₃"


def test_subscripted_names_are_distinct_variables():
    assert ev("x = 1; x₁ = 2; x₂ = 3; x + x₁ + x₂") == "= 6"
    assert ev("x₁ = 2; x₁") == "= 2"


def test_subscripted_names_work_as_parameters_and_display():
    assert ev("f(x₁) = x₁ + 1\nf(2)") == "= 3"
    assert ev("x₁ = 4") == "x₁ = 4"
    assert "x₁" in roundtrip("f(x₁) = x₁ + 1") and "\\x" not in roundtrip("x₁ + 1")


def test_subscripted_name_juxtaposes_and_takes_alias():
    assert ev("x₁ = 2; 3x₁") == "= 6"
    assert ev("\\alias \\sum, σ₁; σ₁(i=1..3) i") == "= 6"


def test_subscript_digit_alone_is_a_lex_error():
    with pytest.raises(Exception, match="unexpected character"):
        tokenize("₁")
