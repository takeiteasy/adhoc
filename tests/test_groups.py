import pytest

from adhoc.driver import run_source
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import Assign, BackslashRef, Call, IfExpr, NumLit, Seq


def define(source):
    env = {}
    run_source(source, env)
    return env


# -- parenthesized statement groups: the multi-line statement form ------------


def test_group_shape_and_span():
    # The group is one Seq whose span covers its statements — the parentheses
    # themselves are pure grouping and stay out of every span.
    node = parse_program("(a = 1\na + 1)")
    assert isinstance(node, Seq)
    assert isinstance(node.statements[0], Assign)
    assert node.span == Span(1, 12)


def test_single_statement_group_unwraps():
    # One statement, no Seq wrapper, and the node keeps its own (inner) span.
    node = parse_program("(5)")
    assert node == NumLit(text="5", span=Span(1, 2))


def test_group_flattens_at_top_level_with_echoes():
    assert run_source("(a = 1\na + 1)", {}) == ["a = 1", "= 2"]


def test_group_value_is_its_last_statement():
    env = define("s = (1\n2)")
    assert run_source("s", env) == ["= 2"]


def test_group_as_function_body():
    env = define("f(x) = (\ny = x^2\ny + 1\n)")
    assert run_source("f(3)", env) == ["= 10"]


def test_groups_nest():
    assert run_source("(\na = (\n1\n2\n)\na + 1\n)", {}) == ["a = 2", "= 3"]


def test_unclosed_group_is_incomplete_input():
    with pytest.raises(IncompleteInput):
        parse_program("(1\n2")


def test_trailing_semicolon_before_close_is_tolerated():
    assert run_source("(1;)", {}) == ["= 1"]
    assert run_source("(1\n;\n)", {}) == ["= 1"]


def test_blank_lines_inside_a_group_are_free():
    # Blank lines separate nothing; at top level the group still flattens.
    assert run_source("(\n\n1\n\n\n2\n)", {}) == ["= 1", "= 2"]


def test_double_semicolon_inside_group_is_an_error():
    with pytest.raises(ParseError):
        parse_program("(1;; 2)")


def test_empty_group_is_an_error():
    with pytest.raises(ParseError, match="unexpected token"):
        parse_program("()")


def test_statements_need_a_separator_between_them():
    # `b = 2` abutting `a = 1` on the same line is juxtaposition then an error —
    # group statements are newline- or `;`-separated.
    with pytest.raises(ParseError):
        parse_program("(\na = 1 b = 2\n)")


def test_imports_are_rejected_inside_groups():
    with pytest.raises(ParseError, match="statements, not expressions"):
        parse_program('(\n\\import("lib")\n)')


def test_spelling_directives_are_rejected_inside_groups():
    # `\alias`/`\dual` are top-level directives; a group is not top level.
    with pytest.raises(ParseError, match="top-level directive"):
        parse_program("(\n\\alias \\sum, σ\n)")


def test_a_newline_separates_statements_inside_a_group():
    # The uniform rule inside parens too: where the expression is complete, the
    # line break separates statements — `(1\n2)` is two statements, never a
    # product.
    assert run_source("(1\n2)", {}) == ["= 1", "= 2"]


def test_same_line_adjacency_still_juxtaposes():
    # The newline is the separator, not the parenthesis: `(2 (3))` on one line
    # is the product it always was.
    assert run_source("(2 (3))", {}) == ["= 6"]


def test_arguments_need_commas_across_lines():
    # The same rule in argument lists: a newline ends the argument where the
    # expression is complete, so multi-line argument lists are comma-separated.
    with pytest.raises(ParseError):
        parse_program("f(1\n2)")
    assert run_source("f(1,\n2)", {"f": lambda a, b: a + b}) == ["= 3"]


def test_infinite_range_inside_group():
    # A committed range `1..` runs to the closing paren just like `,` `)` `;`
    # and EOF — across the line break.
    env = define("r = (\n1..\n)")
    assert run_source("r", env) == ["= <range 1.. (lazy, infinite)>"]


def test_range_folds_still_work_inside_groups():
    env = define("s = (\n\\sum(i=1..3) i^2\n)")
    assert run_source("s", env) == ["= 14"]


def test_expression_continues_across_lines_inside_a_group():
    # A line ending mid-expression continues onto the next line — the newline is
    # only a separator where a whole statement could end.
    assert run_source("(\nx = 1 +\n2\nx\n)", {}) == ["x = 3", "= 3"]


def test_operator_at_line_start_does_not_join_the_previous_statement():
    # The newline wins at a statement boundary: `+ 2` starting a line is a fresh
    # (erroneous) statement, never a continuation of the previous one.
    with pytest.raises(ParseError):
        parse_program("(\nx = 1\n+ 2\n)")


def test_former_block_markers_are_ordinary_names():
    # The `\begin`/`\if` block forms are gone: those spellings are ordinary
    # names now — bindable, and an unbound use fails at evaluation like any
    # other name.
    env = define("\\begin = 3")
    assert run_source("\\begin", env) == ["= 3"]
    with pytest.raises(EvalError, match="not bound"):
        run_source("\\if", {})
    node = parse_program("\\end(1)")
    assert isinstance(node, Call)
    assert isinstance(node.head, BackslashRef)
    assert node.head.name == "end"


# -- the ternary: the one conditional, with group branches --------------------


def test_ternary_is_lazy():
    # The untaken branch is never evaluated, so the unbound name never fails.
    assert run_source("1 > 2 ? \\nope : 5", {}) == ["= 5"]


def test_group_branch_evaluates_in_the_enclosing_frame():
    # A group as the selected branch: it runs for its bindings (frame-local,
    # like any statement list) and its value is the last statement's value.
    env = {}
    assert run_source("1 < 2 ? (x = 4\nx + 1) : 99", env) == ["= 5"]
    assert run_source("x", env) == ["= 4"]


def test_ternary_value_in_expression_position():
    env = define("y = 1 < 2 ? 7 : 9")
    assert run_source("y", env) == ["= 7"]


def test_missing_else_is_incomplete_input():
    # A ternary always needs its else: a missing `:` is the REPL's continuation
    # case, never a silent no-op conditional.
    with pytest.raises(IncompleteInput):
        parse_program("1 < 2 ? 1")
    with pytest.raises(IncompleteInput):
        parse_program("1 < 2 ?")


def test_nested_ternaries_select_the_first_true_branch():
    env = define("r = 1 > 2 ? 1 : 2 > 3 ? 2 : 3 > 2 ? 3 : 4")
    assert run_source("r", env) == ["= 3"]


def test_nested_ternaries_desugar_to_right_nested_ifexprs():
    node = parse_program("1 < 2 ? 1 : 2 < 3 ? 2 : 3")
    assert isinstance(node, IfExpr)
    assert isinstance(node.otherwise, IfExpr)


def test_ternary_conditions_must_be_boolean():
    with pytest.raises(EvalError, match="condition must be boolean"):
        run_source("0 ? 1 : 2")


def test_nested_ternaries_with_group_branches():
    env = define("r = 1 < 2 ? (2 < 3 ? 10 : 20) : 30")
    assert run_source("r", env) == ["= 10"]


def test_condition_continues_across_lines():
    # A multi-line condition continues mid-expression; the ternary's `?` and `:`
    # own their line breaks through the operand-position rule.
    env = define("r = 1 +\n1 < 3 ? 1 : 2")
    assert run_source("r", env) == ["= 1"]


def test_ternary_inside_fold_body():
    # The greedy fold body takes the whole ternary as its term expression.
    assert run_source("\\sum(i=1..4) i > 2 ? i : 0") == ["= 7"]


def test_ternary_recursion_factorial():
    env = define("\\fact(n) = n <= 1 ? 1 : n * \\fact(n - 1)")
    assert run_source("\\fact(5)", env) == ["= 120"]
