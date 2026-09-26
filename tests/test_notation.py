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
    with pytest.raises(Exception, match="needs a letter before it"):
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
    assert (tok.span.start, tok.span.end) == (1, 1 + 3 + 2 + 3)
    assert [t.span.start for t in tok.tokens[:2]] == [1, 4]


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
    with pytest.raises(Exception, match="needs digits or letters"):
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


# --- roots ---


def test_cube_and_fourth_roots():
    assert ev("∛8") == "= 2"
    assert ev("∛-8") == "= -2"
    assert ev("∜16") == "= 2"
    assert ev("∛(-27)") == "= -3"
    assert ev("∛2") == "= 1.25992104989487..."
    assert ev("∛2.") == "= 1.2599210498948732"


def test_root_precedence_matches_sqrt():
    assert ev("2∛8") == "= 4"
    assert ev("∛2^3") == "= 2"
    assert ev("x = 27; ∛x²") == "= 9"


def test_root_prelude_function():
    assert ev(r"\root(32, 5)") == "= 2"
    assert ev(r"\root(9, 1)") == "= 9"
    fails(r"\root(8, 0)", "positive exact integer")
    fails(r"\root(8, 1.5)", "positive exact integer")
    fails(r"\root(8)", "takes a value and a root index")
    fails(r'\root("a", 3)', "not numbers")


def test_root_is_protected_and_operator_valued():
    fails(r"\let \root = 3", "protected")
    assert ev(r"\map((∛), [1, 8])") == "= [1, 2]"
    assert ev(r"\map(∜, ⟨16, 81⟩)") == "= ⟨2, 3⟩"
    assert ev("(∛)(27)") == "= 3"


def test_root_quotes_print_as_the_prelude_call():
    assert roundtrip("∛x + ∜y") == r"(\root(x, 3) + \root(y, 4))"
    assert ev(r"\eval(\expr(∛x), x=8)") == "= 2"


# --- comparison glyphs ---


def test_le_ge_glyphs_are_the_ascii_operators():
    assert ev("1 ≤ 2") == "= true"
    assert ev("2 ≤ 1") == "= false"
    assert ev("2 ≥ 2") == "= true"
    assert ev("1 ≥ 2") == "= false"
    assert ev("1 ≤ 2 ? 5 : 6") == "= 5"
    assert ev("\\filter((≤ 2), ⟨1, 2, 3⟩)") == "= ⟨1, 2⟩"
    assert ev("(≥)(3, 2)") == "= true"


def test_le_ge_spans_use_byte_lengths():
    le = tokenize("a ≤ b")[1]
    assert (le.span.start, le.span.end) == (2, 5)


def test_not_equal():
    assert ev("2 ≠ 3") == "= true"
    assert ev("2 ≠ 2.") == "= false"
    assert ev("1/2 ≠ 0.5") == "= false"
    assert ev("{1, 2} ≠ {2, 1}") == "= false"
    assert ev('"a" ≠ "b"') == "= true"
    assert ev('"a" ≠ 1') == "= true"
    assert ev(r"\nan ≠ \nan") == "= true"
    assert ev(r"2 \neq 3") == "= true"
    assert ev("2 ≠ 3 ? 1 : 0") == "= 1"


def test_approx():
    assert ev("1e-1 + 2e-1 ≈ 3e-1") == "= true"
    assert ev("1e-13 ≈ 0") == "= true"
    assert ev("1 ≈ 1.001") == "= false"
    assert ev("π ≈ 3.14159265358979") == "= true"
    assert ev("(1+i) ≈ (1+i)") == "= true"
    assert ev("(1+i) ≈ (1.0000000001+i)") == "= true"
    assert ev("(1+i) ≈ (1+2i)") == "= false"
    assert ev(r"\nan ≈ \nan") == "= false"
    assert ev(r"\inf ≈ \inf") == "= true"
    assert ev(r"1 \approx 1") == "= true"


def test_approx_rejects_non_numbers():
    fails('"a" ≈ "a"', "not numbers")
    fails("{1} ≈ {1}", "sets do not support")
    fails("[1, 2] ≈ [1, 2]", "operands must be numbers")


def test_new_comparison_operators_are_reserved_and_operator_valued():
    fails(r"\let \neq = 3", "protected")
    assert ev("(≠)(1, 2)") == "= true"
    assert ev(r"\map((≈ 1), ⟨1, 2⟩)") == "= ⟨true, false⟩"
    assert ev("g = (≠); g = (\\neq)") == "true"


def test_comparison_glyphs_roundtrip():
    assert roundtrip("a ≠ b") == "(a ≠ b)"
    assert roundtrip(r"a \approx b") == "(a ≈ b)"
    assert roundtrip("a ≤ b") == "(a <= b)"


# --- set extras ---


def test_not_in():
    assert ev("3 ∉ {1, 2}") == "= true"
    assert ev("2 ∉ {1, 2}") == "= false"
    assert ev(r"2 \notin {1, 2}") == "= false"
    assert ev(r"\filter(\fn(x) x ∉ {2}, ⟨1, 2, 3⟩)") == "= ⟨1, 3⟩"
    assert ev("(∉ {2})(3)") == "= true"


def test_subset_and_superset_family():
    assert ev("{1} ⊂ {1, 2}") == "= true"
    assert ev("{1, 2} ⊂ {1, 2}") == "= false"
    assert ev(r"{1} \subset {1, 2}") == "= true"
    assert ev("{1, 2} ⊇ {1, 2}") == "= true"
    assert ev("{1, 2} ⊇ {3}") == "= false"
    assert ev(r"{1, 2} \supseteq {1}") == "= true"
    assert ev("{1, 2} ⊃ {1}") == "= true"
    assert ev("{1, 2} ⊃ {1, 2}") == "= false"
    assert ev(r"{1, 2} \supset {1}") == "= true"
    assert ev("∅ ⊂ {1}") == "= true"
    fails("1 ⊂ {1}", "needs two sets")
    fails("{1} ⊇ 1", "needs two sets")


def test_empty_set():
    assert ev("∅") == "= {}"
    assert ev(r"\emptyset") == "= {}"
    assert ev("s = {}; s = ∅") == "true"
    assert ev(r"\len(∅)") == "= 0"
    assert ev("∅ ∪ {1}") == "= {1}"
    fails("∅ = 3", "protected")
    fails(r"\let \emptyset = 3", "protected")


def test_membership_in_arrays():
    assert ev('2 ∈ ⟨1, 2, 3⟩') == "= true"
    assert ev('4 ∉ ⟨1, 2, 3⟩') == "= true"
    assert ev('"a" ∈ ⟨1, "a"⟩') == "= true"
    assert ev("[1, 2] ∈ ⟨[1, 2]⟩") == "= true"


def test_membership_in_ranges():
    assert ev("3 ∈ (1..5)") == "= true"
    assert ev("3 ∈ 1..5") == "= true"
    assert ev("4 ∉ 1..3") == "= true"
    assert ev("5 ∈ 1,3..9") == "= true"
    assert ev("1000000 ∈ 1..") == "= true"
    assert ev("(∈ 1..5)(3)") == "= true"
    assert ev("(∉ 1,3..9)(4)") == "= true"


def test_membership_range_operand_keeps_other_comparisons_and_lists():
    fails("3 < 1..5", "booleans are not numbers")
    assert ev("\\arr(1 ∈ 1..3, 9)") == "= ⟨true, 9⟩"
    assert roundtrip("3 ∈ 1..5") == "(3 ∈ (1..5))"
    assert ev("6 ∈ (1..5)") == "= false"
    assert ev("0 ∈ (1..5)") == "= false"
    assert ev("2.5 ∈ (1..5)") == "= false"
    assert ev("4 ∈ (1,3..9)") == "= false"
    assert ev("5 ∈ (1,3..9)") == "= true"
    assert ev("10 ∈ (10,8..1)") == "= true"
    assert ev("9 ∈ (10,8..1)") == "= false"
    assert ev("1 ∈ (10,8..1)") == "= false"
    assert ev("1000000 ∈ (1..)") == "= true"
    assert ev("0 ∈ (1..)") == "= false"
    assert ev("1/2 ∈ (0,1/2..2)") == "= true"
    assert ev("3 ∉ (1..2)") == "= true"
    assert ev('"a" ∈ (1..3)') == "= false"
    assert ev("i ∈ (1..3)") == "= false"
    assert ev("1.5 ∈ (0.5,1.5..3.5)") == "= true"
    assert ev("2. ∈ (1.,1.5..3.)") == "= true"


def test_membership_still_rejects_other_right_operands():
    fails("1 ∈ 1", "needs a set, array, or range")
    fails("1 ∉ [1, 2]", "needs a set, array, or range")


def test_set_extras_roundtrip_and_operator_values():
    assert roundtrip("a ∉ b") == "(a ∉ b)"
    assert roundtrip(r"a \subset b") == "(a ⊂ b)"
    assert roundtrip("a ⊇ b") == "(a ⊇ b)"
    assert roundtrip("a ⊃ b") == "(a ⊃ b)"
    assert ev("(∉)(1, {2})") == "= true"
    assert ev("(⊂)({1}, {1, 2})") == "= true"
    fails(r"\let \notin = 1", "protected")


# --- script letters, ASCII subscripts, function power ---


def test_subscript_letters_are_names():
    assert ev("xᵢ = 2; xⱼ = 3; xᵢ + xⱼ") == "= 5"
    assert ev("f(xᵢ) = xᵢ + 1\nf(2)") == "= 3"
    assert tokenize("aᵢⱼ")[0].ch == "aᵢⱼ"
    assert tokenize("x₁ₐ")[0].ch == "x₁ₐ"


def test_bare_subscript_letter_is_a_lex_error():
    with pytest.raises(Exception, match="needs a letter before it"):
        tokenize("ᵢ")


def test_bare_superscript_letter_is_a_parse_error():
    with pytest.raises(ParseError):
        parse_program("ⁿ")


def test_ascii_subscript_spelling():
    tok = tokenize("x_1")[0]
    assert (tok.ch, tok.spelling, tok.span.end) == ("x₁", "x_1", 3)
    assert tokenize("x_ij")[0].ch == "xᵢⱼ"
    assert ev("x_1 = 2; x₁") == "= 2"
    assert ev("x₁ = 2; x_1 + 1") == "= 3"
    assert roundtrip("x_1 + 1") == "(x_1 + 1)"


def test_placeholder_underscore_is_unchanged():
    assert ev("f(x, y) = x - y\ng = f(5, _)\ng(2)") == "= 3"
    with pytest.raises(ParseError):
        parse_program("x_q")


def test_superscript_expression_exponents():
    assert ev("n = 3; 2ⁿ") == "= 8"
    assert ev("n = 3; 2ⁿ⁻¹") == "= 4"
    assert ev("n = 3; 2⁽ⁿ⁺¹⁾") == "= 16"
    assert ev("n = 2; k = 3; 2ⁿᵏ") == "= 64"
    assert ev("n = 2; 2⁻ⁿ") == "= 1/4"


def test_superscript_run_reads_a_float_exponent():
    assert ev("1¹ᵉ³") == "= 1.0"


def test_superscript_error_span_covers_glyphs():
    with pytest.raises(ParseError) as e:
        parse_program("xⁿ⁺")
    assert e.value.span.start >= 1


def test_transpose_glyph():
    assert ev("A = [1, 2; 3, 4]; Aᵀ") == ev("A = [1, 2; 3, 4]; A'")
    assert ev("A = [1, 2; 3, 4]; Aᵀ²") == ev("A = [1, 2; 3, 4]; (A')²")
    assert roundtrip("Aᵀ") == "A'"


def test_function_power():
    assert ev("\\sin²(1)") == ev("\\sin(1)^2")
    assert ev("f(x) = x + 1\nf²(2)") == "= 9"


def test_function_power_on_a_number_is_still_a_product():
    assert ev("x = 3; x²(2)") == "= 18"


def test_function_inverse_notation_is_a_typed_error():
    fails("f(x) = x + 1\nf⁻¹(2)", "no inverse")


def test_function_power_roundtrips():
    assert roundtrip("\\sin²(x)") == "\\sin²(x)"
    assert roundtrip("f⁽ⁿ⁺¹⁾(x)") == "fⁿ⁺¹(x)"
    assert roundtrip("f²(x, y)") == "f²(x, y)"


def test_function_power_falls_back_to_caret_when_exponent_has_no_glyphs():
    from adhoc.span import Span
    from adhoc.syntax import PowCall, Var
    sp = Span(0, 0)
    node = PowCall(head=Var(ch="f", span=sp), exponent=Var(ch="q", span=sp),
                   args=(Var(ch="x", span=sp),), span=sp)
    assert show(node) == "(f(x) ^ q)"


def test_inverse_trig_functions():
    assert ev("\\asin(1/2)") == ev("π/6")
    assert ev("\\acos(1)") == "= 0"
    assert ev("\\atan(1)") == ev("π/4")
    assert ev("\\sin(\\asin(1/3))") == "= 1/3"
    assert ev("\\asin(2)") == ev("\\asin(2)")
    fails("\\asin(2.)", "math domain error")


def test_function_inverse_notation_maps_prelude_trig():
    assert ev("\\sin⁻¹(1/2)") == ev("\\asin(1/2)")
    assert ev("\\cos⁻¹(0)") == ev("\\acos(0)")
    assert ev("\\asin⁻¹(1/2)") == ev("\\sin(1/2)")
    assert ev("\\sin⁻¹") == ev("\\asin")
    assert ev("\\sin^(-1)") == ev("\\asin")


def test_only_minus_one_is_an_inverse():
    fails("\\sin⁻²(1)", "only `⁻¹`")
    fails("f(x) = x + 1\nf⁻²(2)", "only `⁻¹`")




def test_inverse_follows_the_function_value():
    assert ev("g(f) = f⁻¹(1/2)\ng(\\sin)") == ev("\\asin(1/2)")
    fails("g(f) = f⁻¹(2)\nh(x) = x + 1\ng(h)", "no inverse")
