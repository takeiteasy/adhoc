import pytest

from adhoc.driver import run_source
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.span import Span
from adhoc.syntax import Assign, NumLit, Range, Seq


def define(source):
    env = {}
    run_source(source, env)
    return env


def test_block_shape_and_span():
    # The Seq span covers the whole block, delimiters included — unlike a
    # parenthesized group, where the delimiters are pure grouping.
    node = parse_program("\\begin a = 1; a + 1 \\end")
    assert isinstance(node, Seq)
    assert isinstance(node.statements[0], Assign)
    assert node.span == Span(0, 24)


def test_single_statement_block_unwraps():
    # Same rule as parenthesized groups: one statement, no Seq wrapper, and the
    # node keeps its own (inner) span.
    node = parse_program("\\begin 5 \\end")
    assert node == NumLit(text="5", span=Span(7, 8))


def test_block_flattens_at_top_level_with_echoes():
    assert run_source("\\begin a = 1; a + 1 \\end", {}) == ["a = 1", "= 2"]


def test_block_value_is_its_last_statement():
    env = define("s = \\begin 1; 2 \\end")
    assert run_source("s", env) == ["= 2"]


def test_block_as_function_body():
    env = define("f(x) = \\begin y = x^2; y + 1 \\end")
    assert run_source("f(3)", env) == ["= 10"]


def test_block_as_if_branch_is_lazy():
    # The untaken branch is never evaluated, so the unbound name never fails.
    assert run_source("\\if(1 < 2, \\begin a = 5; a * 2 \\end, \\nope)", {}) == ["= 10"]


def test_blocks_nest():
    assert run_source("\\begin a = \\begin 1; 2 \\end; a + 1 \\end", {}) == \
        ["a = 2", "= 3"]


def test_stray_end_is_a_parse_error():
    with pytest.raises(ParseError, match="no block is open here"):
        parse_program("\\end")
    with pytest.raises(ParseError, match="no block is open here"):
        parse_program("(\\end)")


def test_unclosed_begin_is_incomplete_input():
    with pytest.raises(IncompleteInput):
        parse_program("\\begin 1; 2")


def test_trailing_semicolon_before_end_is_tolerated():
    assert run_source("\\begin 1; \\end", {}) == ["= 1"]


def test_double_semicolon_inside_block_is_an_error():
    with pytest.raises(ParseError):
        parse_program("\\begin 1;; 2 \\end")


def test_imports_are_rejected_inside_blocks():
    with pytest.raises(ParseError, match="statements, not expressions"):
        parse_program('\\begin \\import("lib") \\end')


def test_spelling_directives_are_rejected_inside_blocks():
    # `\alias`/`\dual` are top-level directives; a block is not top level.
    with pytest.raises(ParseError, match="top-level directive"):
        parse_program("\\begin \\alias \\sum, σ \\end")


def test_end_is_never_a_juxtaposed_factor():
    # Regression: the block terminator must stop implicit multiplication rather
    # than being swallowed as a factor (`a + 1 \end` is `a + 1`, then `\end`).
    assert run_source("\\begin a = 1; a + 1 \\end", {}) == ["a = 1", "= 2"]


def test_block_is_an_expression_factor():
    # A block juxtaposed after a number multiplies through, like a paren group.
    assert run_source("2 \\begin 3 \\end", {}) == ["= 6"]


def test_infinite_range_inside_block():
    # The `\end` terminates the range just like `,` `)` `;` and EOF.
    env = define("r = \\begin 1.. \\end")
    assert run_source("r", env) == ["= <range 1.. (lazy, infinite)>"]


def test_block_marker_is_not_bindable():
    with pytest.raises(ParseError):
        parse_program("\\begin = 3")


def test_block_range_folds_still_work_inside_blocks():
    env = define("s = \\begin \\sum(i=1..3) i^2 \\end")
    assert run_source("s", env) == ["= 14"]
