import pytest

from adhoc.driver import run_source
from adhoc.expression import show
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.syntax import Piecewise, SetBuilder, SetLit


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, message):
    with pytest.raises(EvalError, match=message):
        run_source(src, {})


def roundtrip(src):
    shown = show(parse_program(src))
    assert show(parse_program(shown)) == shown
    return shown


# --- piecewise ---


def test_piecewise_definition():
    env = {}
    run_source("f(x) = {x < 0: -x; x}", env)
    assert ev("f(-3)", env) == "= 3"
    assert ev("f(4)", env) == "= 4"


def test_piecewise_without_otherwise_and_no_match():
    assert ev("{1 < 2: 10}") == "= 10"
    fails("{1 > 2: 10}", "no piecewise case matched")


def test_piecewise_clauses_on_lines():
    env = {}
    run_source("s(x) = {x < 0: -1; x > 0: 1; 0}", env)
    assert [ev(f"s({n})", env) for n in (-5, 0, 7)] == ["= -1", "= 0", "= 1"]
    assert isinstance(parse_program("{x < 0: -1\nx > 0: 1\n0}"), Piecewise)


def test_piecewise_is_lazy_and_needs_boolean_conditions():
    assert ev("{1 < 2: 1; 1/0}") == "= 1"
    assert ev("{1 > 2: 1/0; 5}") == "= 5"
    fails("{1: 2; 3}", "must be boolean")


def test_ternary_inside_a_set_is_unchanged():
    assert isinstance(parse_program("{1 < 2 ? 3 : 4}"), SetLit)
    assert ev("{1 < 2 ? 3 : 4}") == "= {3}"


def test_piecewise_round_trips_and_quotes():
    assert roundtrip("{x < 0: -x; x}") == "{(x < 0): (-x); x}"
    assert ev(r"\eval(\expr({x < 0: -x; x}), x=-2)") == "= 2"


# --- set-builder ---


def test_filter_form():
    assert ev("{x ∈ 1..10 | x^2 < 50}") == "= {1, 2, 3, 4, 5, 6, 7}"
    assert ev("{x ∈ {1, 2, 3, 4} | x % 2 < 1}") == "= {2, 4}"


def test_map_form_and_guards():
    assert ev("{x^2 | x ∈ 1..4}") == "= {1, 4, 9, 16}"
    assert ev("{x^2 | x ∈ 1..4, x > 1}") == "= {4, 9, 16}"
    assert ev("{x ∈ 1..10 | x > 2, x < 5}") == "= {3, 4}"
    assert ev("{x % 3 | x ∈ 1..9}") == "= {1, 2, 0}"


def test_builder_domains_and_scoping():
    assert ev("{x ∈ ⟨1, 5, 9⟩ | x > 2}") == "= {5, 9}"
    assert ev("{x ∈ [1, 2, 3] | x > 1}") == "= {2, 3}"
    env = {}
    run_source("k = 2", env)
    assert ev("{x*k | x ∈ 1..3}", env) == "= {2, 4, 6}"
    assert ev("{x ∈ 1..3 | x < 2}", env) == "= {1}"
    with pytest.raises(EvalError):
        ev("x", env)


def test_bars_inside_a_builder():
    assert ev("{|x| | x ∈ {-1, 1, 2}}") == "= {1, 2}"
    assert ev("{x ∈ {-3, 1} | |x| > 2}") == "= {-3}"
    assert ev("{2*|-3|, 1}") == "= {6, 1}"


def test_builder_errors():
    fails("{x ∈ 1.. | x > 1}", "infinite")
    fails("{x ∈ 5 | x > 1}", "range or collection")
    fails("{x ∈ 1..3 | x}", "must be boolean")
    fails("{π ∈ 1..3 | π > 1}", "protected")
    with pytest.raises(ParseError, match="binder"):
        parse_program("{a |b|}")
    with pytest.raises(IncompleteInput):
        parse_program("{x ∈ 1..3 |")


def test_builder_round_trips():
    assert roundtrip("{x ∈ S | x > 1}") == "{x ∈ S | (x > 1)}"
    assert roundtrip("{x^2 | x ∈ S, x > 1}") == "{(x ^ 2) | x ∈ S, (x > 1)}"
    assert isinstance(parse_program("{x ∈ S | x > 1}"), SetBuilder)


def test_reduce_renames_a_captured_builder_variable():
    shown = ev(r"\reduce(\expr((\fn(y) {x ∈ S | x > y})(x)))")
    assert shown == r"= \expr({\reduce_a ∈ S | (\reduce_a > x)})"
