import pytest

from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.span import Span
from adhoc.syntax import Assign, BinOp, BinOperator as B, NumLit, Seq, UnOp, UnaryOperator, Var


def test_incomplete_input_variants():
    for src in ["(1 + 2", "1 +", "2 ^", "x ="]:
        with pytest.raises(IncompleteInput):
            parse_program(src)


def test_trailing_semicolons_do_not_trigger_incomplete_input():
    assert parse_program("1;") is not None
    assert parse_program("2;") is not None


def test_power_is_right_associative():
    node = parse_program("2^3^2")
    match node:
        case BinOp(op=B.POW, lhs=NumLit(text="2"), rhs=BinOp(op=B.POW)):
            pass
        case _:
            pytest.fail(f"expected right-associated pow chain, got {node!r}")


def test_unary_minus_binds_looser_than_pow():
    node = parse_program("-2^2")
    match node:
        case UnOp(op=UnaryOperator.NEG, operand=BinOp(op=B.POW)):
            pass
        case _:
            pytest.fail(f"expected -(2^2), got {node!r}")


def test_negative_exponent_parses():
    node = parse_program("2^-1")
    match node:
        case BinOp(
            op=B.POW, lhs=NumLit(text="2"), rhs=UnOp(op=UnaryOperator.NEG, operand=NumLit(text="1"))
        ):
            pass
        case _:
            pytest.fail(f"expected 2^(-1), got {node!r}")


def test_juxtaposition_binds_tighter_than_division():
    node = parse_program("1/2x")
    match node:
        case BinOp(
            op=B.DIV,
            lhs=NumLit(text="1"),
            rhs=BinOp(op=B.MUL, lhs=NumLit(text="2"), rhs=Var(ch="x")),
        ):
            pass
        case _:
            pytest.fail(f"expected 1/(2x), got {node!r}")


def test_juxtaposition_is_left_associative():
    node = parse_program("2xy")
    match node:
        case BinOp(
            op=B.MUL,
            lhs=BinOp(op=B.MUL, lhs=NumLit(text="2"), rhs=Var(ch="x")),
            rhs=Var(ch="y"),
        ):
            pass
        case _:
            pytest.fail(f"expected (2*x)*y, got {node!r}")


def test_assign_node_fields():
    node = parse_program("x := 2")
    assert isinstance(node, Assign)
    assert node.name == "x"
    assert node.force is True
    assert node.value == NumLit(text="2", span=Span(5, 6))
    assert node.span == Span(0, 6)


def test_seq_splits_and_joins_spans():
    node = parse_program("a=1; b=2; a+b")
    assert isinstance(node, Seq)
    assert len(node.statements) == 3
    assert node.span == Span(0, 13)


def test_paren_does_not_retag_span():
    # The `(expr)` atom returns the inner node unchanged — its span stays the inner
    # expression's, not paren-inclusive.
    node = parse_program("(1+2)")
    assert isinstance(node, BinOp)
    assert node.span == Span(1, 4)


def test_unexpected_token_error_message_and_span():
    with pytest.raises(ParseError) as e:
        parse_program("1 + * 2")
    assert e.value.msg == "unexpected token `*`"
    assert e.value.span == Span(4, 5)


def test_expect_error_message():
    with pytest.raises(ParseError) as e:
        parse_program("(1;)")
    assert e.value.msg == "expected `)`, found `;`"


def test_lex_errors_surface_as_parse_errors():
    with pytest.raises(ParseError) as e:
        parse_program("$")
    assert not isinstance(e.value, IncompleteInput)
    assert e.value.msg == "unexpected character `$`"
