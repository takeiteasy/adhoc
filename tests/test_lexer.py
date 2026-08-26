import pytest

from adhoc.lexer import (
    Backslash,
    Caret,
    ColonEq,
    Eq,
    Eof,
    Ident,
    LexError,
    LParen,
    Minus,
    Number,
    Plus,
    RParen,
    Semi,
    Slash,
    Star,
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


def test_unknown_backslash_name_errors():
    with pytest.raises(LexError) as e:
        tokenize("\\bogus")
    assert "unknown" in e.value.msg


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
