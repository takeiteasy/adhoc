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


# --- superscript powers ---


@pytest.mark.parametrize("digit,value", list(zip("⁰¹²³⁴⁵⁶⁷⁸⁹", range(10))))
def test_every_superscript_digit(digit, value):
    assert ev(f"2{digit}") == f"= {2 ** value}"


def test_superscript_run_is_one_exponent():
    assert ev("2¹⁰") == "= 1024"
    assert ev("2⁻¹") == "= 1/2"
    assert ev("2⁻²") == "= 1/4"
    tok = tokenize("x⁻¹⁰")[1]
    assert (tok.text, tok.span.start, tok.span.end) == ("-10", 1, 1 + 3 + 2 + 3)


def test_superscript_precedence():
    assert ev("x = 3; 2x²") == "= 18"
    assert ev("x = 3; -x²") == "= -9"
    assert ev("2^3²") == "= 512"
    assert ev("√4²") == "= 4"
    assert ev("(1+2)²") == "= 9"
    assert ev("f(x) = x + 1\nf(2)²") == "= 9"
    assert ev("[1, 2; 3, 4]²") == "= [1, 4; 9, 16]"
    assert ev("[1, 2]²'") == "= [1, 4]"


def test_superscript_roundtrips_as_caret():
    assert roundtrip("2x²") == "(2 * (x ^ 2))"
    assert roundtrip("x⁻¹") == "(x ^ (-1))"


def test_lone_superscript_minus_is_a_lex_error():
    with pytest.raises(Exception, match="superscript digits"):
        tokenize("x⁻")


def test_caret_after_multibyte_glyph_points_at_the_error():
    with pytest.raises(ParseError) as e:
        parse_program("x² +")
    assert e.value.span.start == len("x² +".encode())


# --- factorial ---


def test_factorial_values():
    assert ev("5!") == "= 120"
    assert ev("0!") == "= 1"
    assert ev("4!") == "= 24"
    assert ev("(3!)!") == "= 720"
    assert ev("7‼") == "= 105"
    assert ev("8‼") == "= 384"
    assert ev("0‼") == "= 1"
    assert ev("7!!") == "= 105"
    assert ev("3!!") == "= 3"


def test_factorial_precedence():
    assert ev("2^3!") == "= 64"
    assert ev("3!^2") == "= 36"
    assert ev("-3!") == "= -6"
    assert ev("2 3!") == "= 12"
    assert ev("n = 3; 2n!") == "= 12"
    assert ev("(1+2)!") == "= 6"
    assert ev("f(x) = x + 1\nf(2)!") == "= 6"
    assert ev("3²!") == "= 362880"


def test_factorial_errors():
    fails(r"(-1)!", "non-negative integer")
    fails(r"2.5!", "non-negative integer")
    fails(r"1.!", "non-negative integer")
    fails(r"(1/2)!", "non-negative integer")
    fails(r'"a"!', "not numbers")
    fails(r"\true!", "booleans")
    fails(r"200000!", "limited to")


def test_bang_equals_gets_a_hint():
    with pytest.raises(Exception, match="not an operator"):
        tokenize("a != b")


def test_factorial_operator_values():
    assert ev(r"\map((!), ⟨1, 2, 3, 4⟩)") == "= ⟨1, 2, 6, 24⟩"
    assert ev(r"\map(‼, ⟨1, 2, 3, 4⟩)") == "= ⟨1, 2, 3, 8⟩"
    assert ev("(!)(4)") == "= 24"
    fails(r"(!)(1, 2)", "takes 1")


def test_factorial_roundtrip():
    assert roundtrip("(a+b)!") == "((a + b)!)"
    assert roundtrip("n‼") == "(n‼)"
    assert roundtrip("2^n!") == "(2 ^ (n!))"
    assert ev(r"\eval(\expr(n!), n=4)") == "= 24"


def test_factorial_error_span_is_the_postfix_node():
    with pytest.raises(EvalError) as e:
        run_source("x = 2.5\nx!", {})
    assert (e.value.span.start, e.value.span.end) == (8, 10)
