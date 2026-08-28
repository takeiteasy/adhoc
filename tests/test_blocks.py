import pytest

from adhoc.driver import run_source
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import Assign, IfExpr, NumLit, Range, Seq


def define(source):
    env = {}
    run_source(source, env)
    return env


# -- `\begin … \end`: strict line structure -----------------------------------


def test_block_shape_and_span():
    # The Seq span covers the whole block, delimiters included — unlike a
    # parenthesized group, where the delimiters are pure grouping.
    node = parse_program("\\begin\na = 1\na + 1\n\\end")
    assert isinstance(node, Seq)
    assert isinstance(node.statements[0], Assign)
    assert node.span == Span(0, 23)


def test_single_statement_block_unwraps():
    # Same rule as parenthesized groups: one statement, no Seq wrapper, and the
    # node keeps its own (inner) span.
    node = parse_program("\\begin\n5\n\\end")
    assert node == NumLit(text="5", span=Span(7, 8))


def test_block_flattens_at_top_level_with_echoes():
    assert run_source("\\begin\na = 1\na + 1\n\\end", {}) == ["a = 1", "= 2"]


def test_block_value_is_its_last_statement():
    env = define("s = \\begin\n1\n2\n\\end")
    assert run_source("s", env) == ["= 2"]


def test_block_as_function_body():
    env = define("f(x) = \\begin\ny = x^2\ny + 1\n\\end")
    assert run_source("f(3)", env) == ["= 10"]


def test_block_requires_a_newline_after_begin():
    # Strict line structure: `\begin` on one line, the body on the next.
    with pytest.raises(ParseError, match="must be followed by a newline"):
        parse_program("\\begin a = 1 \\end")


def test_end_must_start_its_own_line():
    with pytest.raises(ParseError, match="own line"):
        parse_program("\\begin\na = 1\nb = 2\\end")


def test_blocks_nest():
    assert run_source("\\begin\na = \\begin\n1\n2\n\\end\na + 1\n\\end", {}) == \
        ["a = 2", "= 3"]


def test_stray_end_is_a_parse_error():
    with pytest.raises(ParseError, match="no block is open here"):
        parse_program("\\end")
    with pytest.raises(ParseError, match="no block is open here"):
        parse_program("(\\end)")


def test_unclosed_begin_is_incomplete_input():
    with pytest.raises(IncompleteInput):
        parse_program("\\begin\n1\n2")


def test_trailing_semicolon_before_end_is_tolerated():
    assert run_source("\\begin\n1;\n\\end", {}) == ["= 1"]
    assert run_source("\\begin\n1\n;\n\\end", {}) == ["= 1"]


def test_blank_lines_inside_a_block_are_free():
    # Blank lines separate nothing; at top level the block still flattens.
    assert run_source("\\begin\n\n1\n\n\n2\n\\end", {}) == ["= 1", "= 2"]


def test_double_semicolon_inside_block_is_an_error():
    with pytest.raises(ParseError):
        parse_program("\\begin\n1;; 2\n\\end")


def test_statements_need_a_separator_between_them():
    # `b = 2` abutting `a = 1` on the same line is juxtaposition then an error —
    # block statements are newline- or `;`-separated.
    with pytest.raises(ParseError):
        parse_program("\\begin\na = 1 b = 2\n\\end")


def test_imports_are_rejected_inside_blocks():
    with pytest.raises(ParseError, match="statements, not expressions"):
        parse_program('\\begin\n\\import("lib")\n\\end')


def test_spelling_directives_are_rejected_inside_blocks():
    # `\alias`/`\dual` are top-level directives; a block is not top level.
    with pytest.raises(ParseError, match="top-level directive"):
        parse_program("\\begin\n\\alias \\sum, σ\n\\end")


def test_end_is_never_a_juxtaposed_factor():
    # Regression: the block terminator must stop implicit multiplication rather
    # than being swallowed as a factor (`a + 1 \end` is `a + 1`, then `\end`).
    assert run_source("\\begin\na = 1\na + 1\n\\end", {}) == ["a = 1", "= 2"]


def test_block_is_an_expression_factor():
    # A block juxtaposed after a number multiplies through, like a paren group —
    # the block itself still spans lines; only its extent is line-structured.
    assert run_source("2 \\begin\n3\n\\end", {}) == ["= 6"]


def test_infinite_range_inside_block():
    # The `\end` terminates the range just like `,` `)` `;` and EOF — across the
    # line break, since the range is committed once `..` is seen.
    env = define("r = \\begin\n1..\n\\end")
    assert run_source("r", env) == ["= <range 1.. (lazy, infinite)>"]


def test_block_marker_is_not_bindable():
    with pytest.raises(ParseError):
        parse_program("\\begin = 3")


def test_reserved_markers_cannot_be_aliased():
    # Regression: `\alias \begin, b` used to slip through the prelude-only
    # protection; the parser-reserved set now guards spelling declarations.
    for src in ["\\alias \\begin, b", "\\alias \\if, i", "\\alias \\end, e",
                "\\dual \\else, ε = 1"]:
        with pytest.raises(ParseError, match="reserved"):
            parse_program(src)


def test_reserved_markers_cannot_name_functions():
    # `\end` never even reaches the def speculation — the stray-marker guard
    # catches it first; either way the definition cannot parse.
    with pytest.raises(ParseError):
        parse_program("\\end(x) = x")


def test_block_range_folds_still_work_inside_blocks():
    env = define("s = \\begin\n\\sum(i=1..3) i^2\n\\end")
    assert run_source("s", env) == ["= 14"]


def test_expression_continues_across_lines_inside_a_block():
    # A line ending mid-expression continues onto the next line — the newline is
    # only a separator where a whole statement could end. (At top level the block
    # itself flattens, so `x = 3` echoes.)
    assert run_source("\\begin\nx = 1 +\n2\nx\n\\end", {}) == ["x = 3", "= 3"]


def test_operator_at_line_start_does_not_join_the_previous_statement():
    # The newline wins at a statement boundary: `+ 2` starting a line is a fresh
    # (erroneous) statement, never a continuation of the previous one.
    with pytest.raises(ParseError):
        parse_program("\\begin\nx = 1\n+ 2\n\\end")


# -- `\if` blocks --------------------------------------------------------------


def test_if_block_branches_lazily():
    # The untaken branch is never evaluated, so the unbound name never fails.
    assert run_source("\\if 1 > 2\n\\nope\n\\else\n5\n\\end", {}) == []


def test_if_block_statement_position_is_silent():
    # A block `\\if` never echoes; its bindings land in the enclosing frame.
    env = {}
    assert run_source("\\if 1 < 2\nx = 4\nx + 1\n\\else\n99\n\\end", env) == []
    assert run_source("x", env) == ["= 4"]


def test_if_block_value_in_expression_position():
    env = define("y = \\if 1 < 2\n7\n\\else\n9\n\\end")
    assert run_source("y", env) == ["= 7"]


def test_if_block_without_else_is_a_statement_noop_when_false():
    env = {}
    assert run_source("x = 3\n\\if x > 4\nx = 99\n\\end\nx", env) == ["x = 3", "= 3"]
    assert run_source("\\if 1 < 2\n7\n\\end", env) == []


def test_if_block_without_else_errors_in_expression_position_when_false():
    with pytest.raises(EvalError, match="no otherwise branch"):
        run_source("y = \\if 1 > 2\n1\n\\end")


def test_elseif_chain_selects_the_first_true_branch():
    env = {}
    run_source("""
\\if 1 > 2
r = 1
\\elseif 2 > 3
r = 2
\\elseif 3 > 2
r = 3
\\else
r = 4
\\end
""", env)
    assert run_source("r", env) == ["= 3"]


def test_else_catches_everything_false():
    env = define("r = \\if 1 > 2\n1\n\\elseif 2 > 3\n2\n\\else\n4\n\\end")
    assert run_source("r", env) == ["= 4"]


def test_if_block_desugars_to_nested_ifexprs():
    # (shape check: the outer node is block-formed; its otherwise is the inner one)
    node = parse_program("\\if 1 < 2\n1\n\\elseif 2 < 3\n2\n\\else\n3\n\\end")
    assert isinstance(node, IfExpr) and node.block_form
    assert isinstance(node.otherwise, IfExpr) and node.otherwise.block_form


def test_if_conditions_must_be_boolean():
    with pytest.raises(EvalError, match="condition must be boolean"):
        run_source("\\if 0\n1\n\\else\n2\n\\end")


def test_nested_if_blocks():
    env = define("r = \\if 1 < 2\n\\if 2 < 3\n10\n\\else\n20\n\\end\n\\else\n30\n\\end")
    assert run_source("r", env) == ["= 10"]


def test_if_block_condition_ends_at_the_newline():
    # The condition is exactly the expression before the line break; the branch
    # body starts below. A multi-line condition continues mid-expression.
    env = define("r = \\if 1 +\n1 < 3\n1\n\\else\n2\n\\end")
    assert run_source("r", env) == ["= 1"]


def test_stray_branch_markers_are_parse_errors():
    with pytest.raises(ParseError, match="is open here"):
        parse_program("\\elseif 1 < 2\n1\n\\end")
    with pytest.raises(ParseError, match="is open here"):
        parse_program("\\else")
    with pytest.raises(ParseError, match="is open here"):
        parse_program("\\begin\n\\else\n\\end")


def test_if_block_markers_need_their_own_lines():
    with pytest.raises(ParseError, match="ends the line"):
        parse_program("\\if 1 < 2\n1\n\\else 2\n\\end")
    with pytest.raises(ParseError, match="own line"):
        parse_program("\\if 1 < 2\n1\n\\else\n2\\end")


def test_empty_if_branch_is_an_error():
    with pytest.raises(ParseError, match="expected a statement"):
        parse_program("\\if 1 < 2\n\\else\n2\n\\end")
    with pytest.raises(ParseError, match="expected a statement"):
        parse_program("\\if 1 < 2\n1\n\\else\n\\end")


def test_unclosed_if_block_is_incomplete_input():
    with pytest.raises(IncompleteInput):
        parse_program("\\if 1 < 2\n1")
    with pytest.raises(IncompleteInput):
        parse_program("\\if 1 < 2")
    with pytest.raises(IncompleteInput):
        parse_program("\\if 1 < 2\n1\n\\else")


def test_if_block_as_function_body():
    env = define("m(x) = \\if x >= 0\nx\n\\else\n-x\n\\end")
    assert run_source("m(-5)", env) == ["= 5"]
    assert run_source("m(5)", env) == ["= 5"]


def test_if_block_recursion_factorial():
    env = define("\\fact(n) = \\if n <= 1\n1\n\\else\nn * \\fact(n - 1)\n\\end")
    assert run_source("\\fact(5)", env) == ["= 120"]


def test_string_through_if_block_branches():
    # In expression position the if block's value is the selected branch's last
    # statement — a string binds like any value.
    assert run_source('s = \\if 1 < 2\n"yes"\n\\else\n"no"\n\\end') == ['s = "yes"']


def test_if_block_inside_fold_body():
    # The greedy fold body takes the whole if block as its term expression.
    assert run_source("\\sum(i=1..4) \\if i > 2\ni\n\\else\n0\n\\end") == ["= 7"]
