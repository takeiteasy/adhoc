import pytest

from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.span import Span
from adhoc.syntax import (
    Assign,
    BackslashRef,
    BinOp,
    BinOperator as B,
    Call,
    Compare,
    Fold,
    FuncDef,
    IfExpr,
    KwArg,
    Limit,
    NoOp,
    NumLit,
    Range,
    Seq,
    StrLit,
    UnOp,
    UnaryOperator,
    Var,
)


def shape(node):
    r"""A span-free structural snapshot, for comparing trees built from source spellings
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
    node = parse_program("x = 2")
    assert isinstance(node, Assign)
    assert node.name == "x"
    assert node.value == NumLit(text="2", span=Span(4, 5))
    assert node.span == Span(0, 5)


def test_force_reassign_spelling_is_gone():
    # `:=` was removed from the language: `:` is only the import member separator,
    # so a stray `:=` dies at the colon.
    with pytest.raises(ParseError, match="unexpected token `:`"):
        parse_program("x := 2")


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


def test_string_is_an_atom_in_expression_position():
    node = parse_program('1 + "a"')
    match node:
        case BinOp(op=B.ADD, lhs=NumLit(), rhs=StrLit(text="a")):
            assert node.rhs.span == Span(4, 7)  # the whole literal, quote to quote
        case _:
            pytest.fail(f"expected string operand, got {node!r}")


def test_string_concatenation_parses_as_addition():
    node = parse_program('"f" + "g"')
    match node:
        case BinOp(
            op=B.ADD, lhs=StrLit(text="f"), rhs=StrLit(text="g")
        ):
            pass
        case _:
            pytest.fail(f"expected string concatenation, got {node!r}")


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


# --- keyword arguments in argument lists ---


def test_kwarg_parses_into_kwarg_node():
    node = parse_program('\\py("math.isclose")(1, 2, \\rel_tol=0.5)')
    match node:
        case Call(
            head=Call(head=BackslashRef(name="py"),
                      args=(StrLit(text="math.isclose"),)),
            args=(NumLit(text="1"), NumLit(text="2")),
            kwargs=(KwArg(name="rel_tol", value=NumLit(text="0.5")),),
        ):
            # `\rel_tol=0.5` — the kwarg span covers name through value.
            assert node.kwargs[0].span == Span(26, 38)
        case _:
            pytest.fail(f"expected call with kwarg, got {node!r}")


def test_single_char_kwarg_needs_no_sigil():
    node = parse_program("f(x = 3)")
    assert isinstance(node, Call)
    assert node.args == ()
    assert node.kwargs == (KwArg(name="x", value=NumLit(text="3", span=Span(6, 7)),
                                 span=Span(2, 7)),)


def test_positional_and_kwarg_source_order_carries_no_meaning():
    node = parse_program("f(1,\\a=2,3)")
    assert isinstance(node, Call)
    assert node.args == (NumLit(text="1", span=Span(2, 3)), NumLit(text="3", span=Span(9, 10)))
    assert node.kwargs == (KwArg(name="a", value=NumLit(text="2", span=Span(7, 8)),
                                 span=Span(4, 8)),)


def test_string_kwarg_value():
    node = parse_program('f(\\mode="w")')
    assert isinstance(node, Call)
    assert node.args == ()
    assert node.kwargs == (KwArg(name="mode", value=StrLit(text="w", span=Span(8, 11)),
                                 span=Span(2, 11)),)


def test_duplicate_kwarg_is_a_parse_error():
    with pytest.raises(ParseError, match="duplicate keyword argument `a`"):
        parse_program("f(\\a=1, \\a=2)")


def test_py_rejects_kwargs():
    with pytest.raises(ParseError, match="`\\\\py` takes exactly one argument"):
        parse_program('\\py("math.sqrt", \\k=1)')


def test_if_rejects_kwargs():
    with pytest.raises(ParseError, match="`\\\\if` takes two or three arguments"):
        parse_program("\\if(1 < 2, 1, 0, \\k=1)")


def test_def_shape_parses_into_funcdef():
    node = parse_program("f(x, y) = x y")
    assert isinstance(node, FuncDef)
    assert node.name == "f"
    assert node.params == ("x", "y")
    assert isinstance(node.body, BinOp)
    assert node.span == Span(0, 13)


def test_def_force_spelling_is_gone():
    with pytest.raises(ParseError, match="unexpected token `:`"):
        parse_program("f(x) := x")


def test_def_attempt_with_non_ident_param_reparses_as_application():
    # `f(2)` is not a definition shape — it falls back to an application expression.
    node = parse_program("f(2)")
    assert isinstance(node, Call)
    assert not isinstance(node, FuncDef)


# --- the declaration operators are gone outright ---


def test_identical_to_char_is_a_lex_error():
    with pytest.raises(ParseError, match="unexpected character `≡`"):
        parse_program("x ≡ 5")


def test_double_eq_is_two_eq_tokens():
    # `k == 3` lexes as two `=`: the statement rule consumes the first, the second
    # is an unexpected token — there is no declaration spelling to fall into.
    with pytest.raises(ParseError, match="unexpected token `=`"):
        parse_program("x == 5")


def test_const_is_an_ordinary_unbound_name():
    # `\const` has no special form anymore: it parses as a `\`-name expression and
    # fails at evaluation like any unbound name.
    node = parse_program("\\const + 1")
    assert isinstance(node, BinOp)
    match node.lhs:
        case BackslashRef(name="const"):
            pass
        case _:
            pytest.fail(f"expected a BackslashRef, got {node.lhs!r}")


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


def test_non_binder_use_of_special_heads_is_a_usage_error():
    # Fold/limit heads are reserved special forms: a paren that is not the binder
    # shape is a usage error at the head, not an application of an unbound name.
    # Aliased spellings report their canonical name (Σ normalizes to \sum).
    for src, head in [("\\sum(2)", "\\sum"), ("Σ(x)", "\\sum"), ("\\lim(2)", "\\lim")]:
        with pytest.raises(ParseError, match="takes a binder as its first argument") as e:
            parse_program(src)
        assert head in e.value.msg
    # Without a paren there is no application to misread; the head is simply an
    # unbound name at evaluation.
    node = parse_program("\\sum")
    assert isinstance(node, BackslashRef) and node.name == "sum"


# --- ternary `cond ? a : b` ---


def test_ternary_desugars_to_ifexpr():
    node = parse_program("x > 0 ? 1 : -1")
    assert isinstance(node, IfExpr)
    assert isinstance(node.condition, Compare)
    assert node.then_branch == NumLit(text="1", span=node.then_branch.span)
    assert isinstance(node.otherwise, UnOp) and node.otherwise.op == UnaryOperator.NEG


def test_ternary_is_right_associative():
    node = parse_program("a > 0 ? 1 : b > 0 ? 2 : 3")
    assert isinstance(node, IfExpr)
    assert isinstance(node.otherwise, IfExpr)  # a ? 1 : (b ? 2 : 3)


def test_ternary_middle_closes_at_first_free_colon():
    node = parse_program("a > 0 ? b > 0 ? 1 : 2 : 3")
    middle = node.then_branch
    assert isinstance(middle, IfExpr) and isinstance(middle.otherwise, NumLit)
    assert isinstance(node.otherwise, NumLit)  # the `: 3` belongs to the outer form


def test_ternary_binds_looser_than_everything_else():
    # Condition parses at the full expression level; branches may be ranges.
    node = parse_program("1 + 1 > 1 ? 1..3 : 4..6")
    assert isinstance(node, IfExpr)
    assert isinstance(node.condition, Compare)
    assert isinstance(node.then_branch, Range) and isinstance(node.otherwise, Range)


def test_ternary_branches_are_lazy_ifexprs():
    # Same AST as \if, so parenthesized sequence branches work identically.
    node = parse_program("x > 0 ? (y = x^2; y + 1) : 0")
    assert isinstance(node, IfExpr)
    assert isinstance(node.then_branch, Seq)


def test_ternary_incomplete_at_eof_offers_continuation():
    for src in ["1 > 0 ? 2", "1 > 0 ? 2 :", "a > b ?"]:
        with pytest.raises(IncompleteInput):
            parse_program(src)


def test_ternary_missing_colon_is_a_parse_error():
    with pytest.raises(ParseError, match="expected `:`"):
        parse_program("1 > 0 ? 2 3 )")


def test_fold_body_extends_over_a_ternary():
    # The greedy fold body is parsed with the full expression grammar, so a
    # conditional needs no parens.
    node = parse_program("\\sum(i=1..10) i > 5 ? i : 0")
    assert isinstance(node, Fold)
    assert isinstance(node.body, IfExpr)


# --- name aliases (\alias / \dual) ---


def test_alias_directive_is_a_noop_and_normalizes_later_statements():
    node = parse_program("\\alias \\sum, σ; σ(i=1..3) i")
    assert isinstance(node, Seq)
    assert isinstance(node.statements[0], NoOp)
    fold = node.statements[1]
    assert isinstance(fold, Fold) and fold.op == B.ADD


def test_alias_onto_single_char_canonical_yields_var():
    node = parse_program("\\alias x, ξ; ξ + 1")
    assert isinstance(node, Seq)
    assert isinstance(node.statements[1], BinOp)
    lhs = node.statements[1].lhs
    assert isinstance(lhs, Var) and lhs.ch == "x"


def test_seed_aliases_normalize_without_a_directive():
    node = parse_program("π + Σ(i=1..1) Π(j=1..1) 1")
    match node:
        case BinOp(lhs=BackslashRef(name="pi")):
            pass
        case _:
            pytest.fail(f"π did not normalize to the canonical name: {node!r}")
    fold = node.rhs
    assert isinstance(fold, Fold)


def test_alias_requires_a_short_spelling():
    with pytest.raises(ParseError, match="at least one short spelling"):
        parse_program("\\alias \\sum")


def test_alias_short_must_be_single_character():
    with pytest.raises(ParseError, match="single-character"):
        parse_program("\\alias \\sum, \\total")


def test_alias_cannot_repurpose_a_protected_name():
    with pytest.raises(ParseError, match="`e` is protected"):
        parse_program("\\alias x, e")


def test_alias_conflict_with_another_canonical():
    with pytest.raises(ParseError, match="already an alias of `sum`"):
        parse_program("\\alias \\sum, σ; \\alias \\prod, σ")


def test_spelling_directives_are_top_level_only():
    with pytest.raises(ParseError, match="top-level directive"):
        parse_program("f(x) = (\\alias σ, \\sum; x)")
    with pytest.raises(ParseError, match="top-level directive"):
        parse_program("f(x) = (\\dual σ, ς = 1; x)")


def test_dual_var_defines_the_canonical_name():
    node = parse_program("\\dual \\alpha, α = 3.14")
    assert isinstance(node, Assign) and node.name == "alpha"


def test_dual_function_shares_params_and_body():
    node = parse_program("\\dual \\fact, φ(n) = n")
    assert isinstance(node, FuncDef) and node.name == "fact"
    assert node.params == ("n",)


def test_dual_needs_exactly_two_names():
    for src in ["\\dual \\alpha = 1", "\\dual \\alpha, α, β = 1"]:
        with pytest.raises(ParseError, match="exactly one short spelling"):
            parse_program(src)


def test_alias_map_writeback_is_atomic():
    from adhoc.parser import ALIAS_SEED

    session = dict(ALIAS_SEED)
    with pytest.raises(ParseError):
        parse_program("\\alias \\alpha, α; 1 +", session)
    assert "α" not in session  # failed parse leaves the session map untouched
    parse_program("\\alias \\alpha, α", session)
    assert session["α"] == "alpha"


def test_session_aliases_are_not_implicit():
    # A map only applies when passed: scripts and modules parse with the seed
    # alone, so a session alias never leaks across a unit boundary.
    node = parse_program("α")
    assert isinstance(node, Var) and node.ch == "α"
