import pytest

from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.span import Span
from adhoc.syntax import (
    Assign,
    BackslashRef,
    BinOp,
    BinOperator as B,
    Call,
    Fold,
    FuncDef,
    Limit,
    NumLit,
    Range,
    Seq,
    StrLit,
    UnOp,
    UnaryOperator,
    Var,
)


def shape(node):
    """A span-free structural snapshot, for comparing trees built from source spellings
    of different byte widths (`Σ` vs `\sum`)."""
    if not hasattr(node, "__dataclass_fields__"):
        return repr(node)
    return (
        type(node).__name__,
        {k: shape(v) for k, v in vars(node).items() if k != "span"},
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


def test_range_forms_and_spans():
    finite = parse_program("1..10")
    assert finite == Range(start=NumLit(text="1", span=Span(0, 1)), second=None,
                           end=NumLit(text="10", span=Span(3, 5)), span=Span(0, 5))
    infinite = parse_program("1,3..")
    assert isinstance(infinite, Range)
    assert infinite.second == NumLit(text="3", span=Span(2, 3))
    assert infinite.end is None
    assert infinite.span == Span(0, 5)


def test_range_has_lower_precedence_than_addition():
    left = parse_program("1 + 2..10")
    right = parse_program("1..10 + 2")
    assert isinstance(left, Range) and isinstance(left.start, BinOp)
    assert isinstance(right, Range) and isinstance(right.end, BinOp)


def test_range_is_non_associative():
    with pytest.raises(ParseError):
        parse_program("1..2..3")


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


# --- special forms: \sum / \prod / \lim folds and limits ---


def test_sum_finite_fold_ast_and_spans():
    node = parse_program("\\sum(i=1..10) i^2")
    assert node == Fold(
        op=B.ADD,
        var="i",
        rng=Range(start=NumLit(text="1", span=Span(7, 8)), second=None,
                  end=NumLit(text="10", span=Span(10, 12)), span=Span(7, 12)),
        body=BinOp(op=B.POW, lhs=Var(ch="i", span=Span(14, 15)),
                   rhs=NumLit(text="2", span=Span(16, 17)), span=Span(14, 17)),
        span=Span(0, 17),
    )


def test_prod_folds_with_mul():
    node = parse_program("\\prod(j=1..5) j")
    match node:
        case Fold(op=B.MUL, var="j", rng=Range(), body=Var(ch="j")):
            pass
        case _:
            pytest.fail(f"expected product fold, got {node!r}")


def test_unicode_and_ascii_folds_have_identical_structure():
    ascii_sum = parse_program("\\sum(i=1..3) i")
    unicode_sum = parse_program("Σ(i=1..3) i")
    ascii_prod = parse_program("\\prod(k=1..3) k")
    unicode_prod = parse_program("Π(k=1..3) k")
    assert shape(ascii_sum) == shape(unicode_sum)
    assert shape(ascii_prod) == shape(unicode_prod)


def test_infinite_binder_range_has_no_end():
    node = parse_program("\\sum(n=1..) n^2")
    match node:
        case Fold(rng=Range(second=None, end=None)):
            pass
        case _:
            pytest.fail(f"expected infinite binder range, got {node!r}")


def test_binder_accepts_step_form_ranges():
    node = parse_program("\\sum(k=1,3..9) k")
    match node:
        case Fold(rng=Range(start=NumLit(text="1"), second=NumLit(text="3"),
                            end=NumLit(text="9"))):
            pass
        case _:
            pytest.fail(f"expected stepped binder range, got {node!r}")


def test_fold_body_is_greedy_up_to_the_delimiter():
    node = parse_program("\\sum(i=1..2) i + 100")
    match node:
        case Fold(body=BinOp(op=B.ADD, lhs=Var(ch="i"), rhs=NumLit(text="100"))):
            pass
        case _:
            pytest.fail(f"expected greedy fold body over the addition, got {node!r}")


def test_enclosing_parentheses_end_the_fold_body_early():
    # Greedy body runs to the nearest delimiter: wrapping the fold lets the
    # `* 2` apply to the completed total rather than join the folded body.
    node = parse_program("(\\sum(i=1..2) i + 1) * 2")
    match node:
        case BinOp(op=B.MUL, lhs=Fold(op=B.ADD,
                                      body=BinOp(op=B.ADD, lhs=Var(ch="i"),
                                                 rhs=NumLit(text="1"))),
                   rhs=NumLit(text="2")):
            pass
        case _:
            pytest.fail(f"expected (fold + 1) * 2, got {node!r}")


def test_limit_ast_shape():
    node = parse_program("\\lim(x=0) f(x)")
    assert node == Limit(
        var="x",
        point=NumLit(text="0", span=Span(7, 8)),
        body=Call(head=Var(ch="f", span=Span(10, 11)), args=(Var(ch="x", span=Span(12, 13)),),
                  span=Span(10, 14)),
        span=Span(0, 14),
    )


def test_fold_requires_a_range_to_bind():
    with pytest.raises(ParseError) as e:
        parse_program("\\sum(i=1) i")
    assert "needs a range" in e.value.msg


def test_incomplete_special_forms_offer_continuation():
    for src in ["\\sum(i=", "\\sum(i=1", "\\sum(i=1..", "\\lim(x="]:
        with pytest.raises(IncompleteInput):
            parse_program(src)


def test_missing_body_after_closed_binder_is_incomplete():
    with pytest.raises(IncompleteInput):
        parse_program("\\sum(i=1..10)")


def test_non_binder_use_of_special_heads_stays_an_application():
    # The (ident = shape is what commits a special form; anything else keeps the
    # ordinary call path (and fails at evaluation like any other unbound name).
    node = parse_program("\\sum(2)")
    match node:
        case Call(head=BackslashRef(name="sum"), args=(NumLit(text="2"),)):
            pass
        case _:
            pytest.fail(f"expected ordinary application fallback, got {node!r}")
    node = parse_program("Σ(x)")
    assert isinstance(node, Call)
