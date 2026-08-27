import pytest

from adhoc.lexer import (
    Backslash,
    Caret,
    ColonEq,
    Comma,
    DotDot,
    Eq,
    Eof,
    Ident,
    IdenticalTo,
    LexError,
    LParen,
    Minus,
    Number,
    Plus,
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


def test_trailing_dot_number_errors():
    with pytest.raises(LexError) as e:
        tokenize("1.")
    assert "." in e.value.msg


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


def test_bare_backslash_errors():
    with pytest.raises(LexError) as e:
        tokenize("\\ ")
    assert "bare" in e.value.msg


def test_comments_are_discarded():
    assert kinds("-- hi\n1") == [Number, Eof]


def test_all_operator_kinds():
    assert kinds("+-*/^=:=();") == [
        Plus,
        Minus,
        Star,
        Slash,
        Caret,
        Eq,
        ColonEq,
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


# --- string literals (stage 5): escape-free, terminated by the next quote ---


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


def test_string_is_escape_free_ends_at_next_quote():
    tok = tokenize('"a+b*c"')[0]
    assert tok.text == "a+b*c"


def test_string_may_span_lines():
    toks = tokenize('"a\nb"')
    assert kinds('"a\nb"') == [Str, Eof]
    assert toks[0].text == "a\nb"
    assert toks[0].span == Span(0, 5)  # bytes, newline included


def test_unterminated_string_has_dedicated_error():
    with pytest.raises(UnterminatedString) as e:
        tokenize('"abc')
    assert e.value.span == Span(0, 4)  # open quote to EOF
    assert isinstance(e.value, LexError)


def test_comma_token():
    assert kinds(",") == [Comma, Eof]


def test_identical_to_token():
    # ≡ is a math symbol (not isalpha), so it gets an explicit token; spans stay bytes.
    toks = tokenize("π ≡ 3")
    assert [type(t) for t in toks] == [Ident, IdenticalTo, Number, Eof]
    assert toks[1].span == Span(3, 6)  # π is 2 bytes, space 1, ≡ is 3 bytes


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
