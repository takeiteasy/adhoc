import pytest

from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.span import Span
from adhoc.syntax import (
    Assign,
    BackslashRef,
    BinOp,
    BinOperator as B,
    Call,
    FuncDef,
    NumLit,
    Seq,
    StrLit,
    UnOp,
    UnaryOperator,
    Var,
)


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


# --- stage 5: strings, application, function definitions ---


def test_bare_string_statement_is_a_node():
    node = parse_program('"note"')
    assert isinstance(node, StrLit)
    assert node.text == "note"
    assert node.span == Span(0, 6)


def test_string_in_expression_is_parse_error_at_opening_quote():
    with pytest.raises(ParseError) as e:
        parse_program('1 + "a"')
    assert e.value.span == Span(4, 7)  # the whole literal, quote to quote


def test_string_inside_arithmetic_arg_still_errors():
    # A string may be a whole call argument, never an operand within one.
    with pytest.raises(ParseError):
        parse_program('\\py("f" + "g")')


def test_application_with_var_head():
    node = parse_program("f(x)")
    match node:
        case Call(head=Var(ch="f"), args=(Var(ch="x"),)):
            assert node.span == Span(0, 4)
        case _:
            pytest.fail(f"expected application, got {node!r}")


def test_application_chains_on_backslash_head():
    node = parse_program('\\py("math.sqrt")(2)')
    match node:
        case Call(
            head=Call(head=BackslashRef(name="py"), args=(StrLit(text="math.sqrt"),)),
            args=(NumLit(text="2"),),
        ):
            pass
        case _:
            pytest.fail(f"expected chained \\py application, got {node!r}")


def test_number_headed_parens_still_juxtapose():
    node = parse_program("2(x+1)")
    match node:
        case BinOp(op=B.MUL, lhs=NumLit(text="2"), rhs=BinOp(op=B.ADD)):
            pass
        case _:
            pytest.fail(f"expected juxtaposed multiplication, got {node!r}")


def test_name_headed_parens_always_parse_as_calls():
    # Structure is static: `name(` builds a Call node, never a product. Whether that
    # call applies or falls back to multiplication is decided at evaluation
    # (dynamic juxtaposition — docs/grammar.md).
    node = parse_program("x(y+1)")
    assert isinstance(node, Call)
    assert isinstance(node.head, Var)


def test_call_binds_tighter_than_pow():
    node = parse_program("f(x)^2")
    match node:
        case BinOp(op=B.POW, lhs=Call(), rhs=NumLit(text="2")):
            pass
        case _:
            pytest.fail(f"expected (f(x))^2, got {node!r}")


def test_unary_minus_over_call():
    node = parse_program("-f(x)")
    match node:
        case UnOp(op=UnaryOperator.NEG, operand=Call()):
            pass
        case _:
            pytest.fail(f"expected -(f(x)), got {node!r}")


def test_zero_arg_call():
    node = parse_program("f()")
    assert isinstance(node, Call)
    assert node.args == ()
    assert node.span == Span(0, 3)


def test_def_shape_parses_into_funcdef():
    node = parse_program("f(x, y) = x y")
    assert isinstance(node, FuncDef)
    assert node.name == "f"
    assert node.params == ("x", "y")
    assert node.force is False
    assert isinstance(node.body, BinOp)
    assert node.span == Span(0, 13)


def test_def_force_spelling():
    node = parse_program("f(x) := x")
    assert isinstance(node, FuncDef)
    assert node.force is True


def test_def_attempt_with_non_ident_param_reparses_as_application():
    # `f(2)` is not a definition shape — it falls back to an application expression.
    node = parse_program("f(2)")
    assert isinstance(node, Call)
    assert not isinstance(node, FuncDef)


def test_incomplete_def_offers_continuation():
    for src in ["f(x) =", "f(x", "f("]:
        with pytest.raises(IncompleteInput):
            parse_program(src)


def test_py_arity_enforced_at_parse_time():
    with pytest.raises(ParseError) as e:
        parse_program('\\py("a", "b")(1)')
    assert "\\py" in e.value.msg and "one argument" in e.value.msg
    with pytest.raises(ParseError):
        parse_program("\\py()")
