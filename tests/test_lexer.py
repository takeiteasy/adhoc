import pytest

from adhoc.lexer import (
    Backslash,
    Caret,
    Colon,
    Comma,
    DotDot,
    Eq,
    Eof,
    Ident,
    LexError,
    LParen,
    Minus,
    Newline,
    Number,
    Plus,
    Question,
    Radical,
    RParen,
    Semi,
    Slash,
    Star,
    Str,
    UnterminatedString,
    tokenize,
)
from adhoc.span import Span


def kinds(src):
    return [type(t) for t in tokenize(src)]


def idents(src):
    return [t.ch for t in tokenize(src) if isinstance(t, Ident)]


def test_numbers():
    assert kinds("42") == [Number, Eof]
    assert kinds("3.14") == [Number, Eof]


def test_trailing_dot_number_is_a_float_marker():
    # `1.` is the explicit float literal (float 1.0); a second dot is still
    # the range operator (ticket #42).
    tokens = tokenize("1.")
    assert [type(t).__name__ for t in tokens] == ["Number", "Eof"]
    assert tokens[0].text == "1."
    tokens = tokenize("1..10")
    assert [type(t).__name__ for t in tokens] == ["Number", "DotDot", "Number",
                                                  "Eof"]
    assert tokens[0].text == "1"


def test_decimal_and_exponent_literals():
    tokens = tokenize("0.5 .5 5e-1 1.5e3")
    assert [t.text for t in tokens if type(t).__name__ == "Number"] == [
        "0.5", ".5", "5e-1", "1.5e3"]
    # `2e` stays juxtaposition (`2*e`), never a broken float.
    tokens = tokenize("2e")
    assert [type(t).__name__ for t in tokens] == ["Number", "Ident", "Eof"]
    assert tokens[0].text == "2"


def test_ascii_and_unicode_idents():
    assert idents("ab π") == ["a", "b", "π"]


def test_backslash_names():
    toks = tokenize("\\pi")
    assert isinstance(toks[0], Backslash)
    assert toks[0].name == "pi"
    assert toks[0].span == Span(0, 3)


def test_user_defined_backslash_names_lex_cleanly():
    toks = tokenize("\\bogus")
    assert isinstance(toks[0], Backslash)
    assert toks[0].name == "bogus"


def test_underscores_continue_backslash_names():
    # `_` joins multi-character names (`\rel_tol`) but cannot start one — a bare
    # `_` outside a `\`-name stays an unexpected character.
    toks = tokenize("\\rel_tol 1")
    assert isinstance(toks[0], Backslash)
    assert toks[0].name == "rel_tol"
    assert toks[0].span == Span(0, 8)


def test_bare_underscore_is_still_unexpected():
    with pytest.raises(LexError) as e:
        tokenize("_")
    assert "unexpected character" in e.value.msg


def test_bare_backslash_errors():
    with pytest.raises(LexError) as e:
        tokenize("\\ ")
    assert "bare" in e.value.msg


def test_comments_are_discarded():
    # The comment eats to end of line; the newline itself is still a token.
    assert kinds("-- hi\n1") == [Newline, Number, Eof]


def test_newlines_outside_parens_are_tokens():
    assert kinds("1\n2") == [Number, Newline, Number, Eof]
    assert kinds("1\n\n\n2") == [Number, Newline, Newline, Newline, Number, Eof]


def test_newlines_inside_parens_are_tokens():
    # Newlines are tokens everywhere; the parser decides between separator and
    # operand-position continuation.
    assert kinds("(1\n2)") == [LParen, Number, Newline, Number, RParen, Eof]
    assert kinds("f(1,\n2)") == [
        Ident,
        LParen,
        Number,
        Comma,
        Newline,
        Number,
        RParen,
        Eof,
    ]


def test_all_operator_kinds():
    assert kinds("+-*/^=:();") == [
        Plus,
        Minus,
        Star,
        Slash,
        Caret,
        Eq,
        Colon,
        LParen,
        RParen,
        Semi,
        Eof,
    ]


def test_unexpected_char_errors():
    with pytest.raises(LexError):
        tokenize("$")


def test_eof_token_is_zero_width_at_end():
    (last,) = (t for t in tokenize("x") if isinstance(t, Eof))
    assert last.span == Span(1, 1)


def test_unicode_ident_spans_are_byte_offsets():
    # π is one character but two UTF-8 bytes; spans stay in bytes.
    toks = [t for t in tokenize("π+π") if isinstance(t, Ident)]
    assert toks[0].span == Span(0, 2)
    assert toks[1].span == Span(3, 5)


# --- string literals (stage 5): four escapes, terminated by the next quote ---


def test_string_literal_token_and_span():
    toks = tokenize('"hello world"')
    assert kinds('"hello world"') == [Str, Eof]
    assert toks[0].text == "hello world"
    assert toks[0].span == Span(0, 13)


def test_empty_string():
    tok = tokenize('""')[0]
    assert isinstance(tok, Str)
    assert tok.text == ""
    assert tok.span == Span(0, 2)


def test_string_ends_at_next_quote_plain_chars_pass_through():
    tok = tokenize('"a+b*c"')[0]
    assert tok.text == "a+b*c"


def test_string_may_span_lines():
    toks = tokenize('"a\nb"')
    assert kinds('"a\nb"') == [Str, Eof]
    assert toks[0].text == "a\nb"
    assert toks[0].span == Span(0, 5)  # bytes, newline included


def test_string_escapes_decode():
    tok = tokenize('"a\\"b\\\\c\\n\\td"')[0]
    assert tok.text == 'a"b\\c\n\td'


def test_string_span_covers_raw_source_not_decoded_text():
    # The span stays in raw bytes — backslashes included — while text is decoded:
    # source `"a\"b"` is 6 bytes but decodes to 3 characters.
    tok = tokenize('"a\\"b"')[0]
    assert tok.text == 'a"b'
    assert tok.span == Span(0, 6)


def test_string_escape_span_stays_bytes_with_unicode():
    # π is 2 UTF-8 bytes: source `"\tπ"` is 6 bytes, decodes to 2 characters.
    tok = tokenize('"\\tπ"')[0]
    assert tok.text == "\tπ"
    assert tok.span == Span(0, 6)


def test_string_unknown_escape_errors():
    with pytest.raises(LexError) as e:
        tokenize('"a\\qb"')
    assert "unknown string escape" in e.value.msg
    assert e.value.span == Span(2, 4)  # backslash + the offending letter


def test_trailing_backslash_is_unterminated():
    with pytest.raises(UnterminatedString) as e:
        tokenize('"abc\\')
    assert e.value.span == Span(0, 5)  # open quote to EOF


def test_escaped_quote_can_still_be_unterminated():
    # `\"` does not close the literal, so `"abc\"` never terminates.
    with pytest.raises(UnterminatedString) as e:
        tokenize('"abc\\"')
    assert e.value.span == Span(0, 6)


def test_unterminated_string_has_dedicated_error():
    with pytest.raises(UnterminatedString) as e:
        tokenize('"abc')
    assert e.value.span == Span(0, 4)  # open quote to EOF
    assert isinstance(e.value, LexError)


def test_comma_token():
    assert kinds(",") == [Comma, Eof]


def test_identical_to_char_is_unexpected():
    # ≡ has no token anymore: the declaration operator is gone outright.
    with pytest.raises(LexError) as e:
        tokenize("π ≡ 3")
    assert "unexpected character `≡`" in e.value.msg
    assert e.value.span == Span(3, 6)  # π is 2 bytes, space 1, ≡ is 3 bytes


def test_double_eq_is_two_eq_tokens():
    # `==` is no alias — two adjacent `=` lex as two tokens; a lone `=` stays Eq.
    assert kinds("x == 5") == [Ident, Eq, Eq, Number, Eof]
    assert kinds("x = 5")[1] is Eq


def test_range_token_and_decimal_disambiguation():
    toks = tokenize("1..2 1.25")
    assert [type(t) for t in toks] == [Number, DotDot, Number, Number, Eof]
    assert toks[1].span == Span(1, 3)
    assert toks[3].text == "1.25"


def test_py_name_lexes_generically():
    # There is no known-name table in the lexer: every \name lexes the same way,
    # and it is the parser/prelude that gives names meaning.
    toks = tokenize("\\py")
    assert isinstance(toks[0], Backslash)
    assert toks[0].name == "py"


def test_question_token():
    # The ternary's opening mark is a plain single-char token; `:` needs no new
    # lexing (it already lexes as Colon for imports) and fuses with nothing.
    assert kinds("a ? b : c") == [Ident, Question, Ident, Colon, Ident, Eof]
    assert kinds("? :") == [Question, Colon, Eof]


def test_radical_token():
    # `√` is a math symbol, not a letter (`isalpha` is False) — its own token, and
    # the parser's prefix rule is what gives it meaning. Byte spans, like every
    # token: `√` is three UTF-8 bytes.
    toks = tokenize("√2")
    assert [type(t) for t in toks] == [Radical, Number, Eof]
    assert toks[0].span == Span(0, 3)
    assert kinds("√") == [Radical, Eof]
