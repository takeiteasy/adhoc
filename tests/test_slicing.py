import pytest

from adhoc.driver import run_source
from adhoc.expression import show
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.syntax import Index, Range, WholeAxis
from adhoc.tex import node_tex


def ev(source):
    return run_source(source, {})[-1]


@pytest.mark.parametrize(("selector", "expected"), [
    ("2..3", "[2, 3]"),
    ("2..", "[2, 3, 4]"),
    ("..", "[1, 2, 3, 4]"),
    ("2..2", "[2]"),
    ("(1,3..4)", "[1, 3]"),
    ("(4,3..1)", "[4, 3, 2, 1]"),
    ("(4,2..)", "[4, 2]"),
    ("(1,3..)", "[1, 3]"),
    ("(2,10..4)", "[2]"),
])
def test_vector_slices(selector, expected):
    assert ev(f"v=[1,2,3,4]; v[{selector}]") == f"= {expected}"


@pytest.mark.parametrize(("selector", "expected", "shape"), [
    ("1,1..2", "[1, 2]", "[2]"),
    ("1..1,1..2", "[1, 2;]", "[1, 2]"),
    ("..,2", "[2, 4]", "[2]"),
    ("..,2..2", "[2; 4]", "[2, 1]"),
    ("2..2", "[3, 4;]", "[1, 2]"),
    ("..,..", "[1, 2; 3, 4]", "[2, 2]"),
    ("(2,1..1),(2,1..1)", "[4, 3; 2, 1]", "[2, 2]"),
])
def test_matrix_shapes_and_order(selector, expected, shape):
    source = f"m=[1,2;3,4]; t=m[{selector}]"
    assert ev(source + "; t") == f"= {expected}"
    assert ev(source + r"; \shape(t)") == f"= {shape}"


def test_higher_rank_and_chained_slices():
    source = "t=[[1,2;3,4],[5,6;7,8]]"
    assert ev(source + "; t[..,2,..]") == "= [3, 4; 7, 8]"
    assert ev(source + r"; \shape(t[1..1,..,2])") == "= [1, 2]"
    assert ev(source + "; t[..,2,..][2][1]") == "= 7"
    assert ev(source + "; t[2,1,2]") == "= 6"


def test_range_variables_and_exact_elements():
    assert ev("v=[1/3,√2,i]; r=2..; v[r]") == "= [1.4142135623731..., i]"
    assert ev("a=#[1,2,3,4]; r=4,2..; a[r]") == "= ⟨4, 2⟩"


def test_array_slices_preserve_values_and_nesting():
    source = 'a=#[1,[2,3],"four",#[5,6]]'
    assert ev(source + "; a[2..3]") == '= ⟨[2, 3], "four"⟩'
    assert ev(source + "; a[3..]") == '= ⟨"four", ⟨5, 6⟩⟩'
    assert ev(source + "; a[(4,2..)]") == "= ⟨⟨5, 6⟩, [2, 3]⟩"
    assert ev(source + "; a[2..4][3][1]") == "= 5"
    assert ev(source + "; a[2..2]") == "= ⟨[2, 3]⟩"


def test_empty_selection_rules():
    assert ev("a=#[1,2,3]; a[3..1]") == "= ⟨⟩"
    assert ev("a=#[]; a[..]") == "= ⟨⟩"
    for source in ("v=[1,2,3]; v[3..1]", "m=[1,2;3,4]; m[..,2..1]"):
        with pytest.raises(EvalError, match="tensor slice cannot be empty"):
            run_source(source, {})


@pytest.mark.parametrize("head", ["v=[1,2,3,4]", "v=#[1,2,3,4]"])
@pytest.mark.parametrize(("selector", "message"), [
    ("0..2", "slice bound 0 out of range"),
    ("2..5", "slice bound 5 out of range"),
    ("5..", "slice bound 5 out of range"),
    ("(1,4..5)", "slice bound 5 out of range"),
    ("(1,3..5)", "slice bound 5 out of range"),
    ("(4,3..0)", "slice bound 0 out of range"),
    ("1/2..3", "slice bounds and step must be exact integers"),
    ("1..3.", "slice bounds and step must be exact integers"),
    ("(1,2.5..4)", "slice bounds and step must be exact integers"),
    ("(1.,2..4)", "slice bounds and step must be exact integers"),
    ("(1,1..4)", "range step cannot be zero"),
    (r"\true", "index must be an exact integer"),
    (r"\true..3", "booleans are not numbers"),
])
def test_invalid_selectors(head, selector, message):
    with pytest.raises(EvalError, match=message):
        run_source(f"{head}; v[{selector}]", {})


def test_wrong_heads_and_selector_counts():
    for source, message in [
        ("v=[1,2]; v[..,1]", "2 indices for an order-1 tensor"),
        ("a=#[1,2]; a[..,1]", "an array takes one index"),
        ("s={1,2}; s[..]", "sets are unordered"),
        ('s="a"; s[..]', "is not indexable"),
        ("k=3; k[..]", "whole-axis selection needs a tensor or array"),
    ]:
        with pytest.raises(EvalError, match=message):
            run_source(source, {})
    assert ev("k=3; k[1,2]") == "= [3, 6]"


def test_selector_parser_and_rendering():
    node = parse_program("m[\n..,\n(1,3..5)\n]")
    assert isinstance(node, Index)
    assert isinstance(node.items[0], WholeAxis)
    assert isinstance(node.items[1], Range)
    assert show(node) == "m[.., (1,3..5)]"
    assert node_tex(parse_program("m[..,2]")) == r"m_{\ldots, 2}"
    for source in ("..", "v[..3]", "v[(..)]", "#[..]", "v[..+1]"):
        with pytest.raises(ParseError):
            parse_program(source)


def test_quoted_slicing_round_trips_and_evaluates():
    source = r"m=[1,2;3,4]; q=\expr(m[..,2])"
    assert ev(source + "; q") == r"= \expr(m[.., 2])"
    assert ev(source + r"; \eval(q)") == "= [2, 4]"
    assert ev(source + r"; r=\expr(m[..,2]); q=r") == "true"


def test_slice_errors_cover_index_expression():
    env = {}
    run_source("v=[1,2,3]", env)
    with pytest.raises(EvalError) as error:
        run_source("v[2..4]", env)
    assert error.value.span.start == 0
    assert error.value.span.end == 7
