import re

import pytest

from adhoc.driver import run_source
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.syntax import BackslashRef, Call, OpRef

DEFS = "s(x) = x^2\n"


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, message):
    with pytest.raises(EvalError, match=re.escape(message)) as e:
        run_source(src, {})
    return e.value


def parse_fails(src, message):
    with pytest.raises(ParseError, match=message):
        parse_program(src)


@pytest.mark.parametrize("src, expected", [
    (r"\fold(+, 1..10)", "= 55"),
    (r"\fold(*, 1..5)", "= 120"),
    (r"\fold(-, ⟨10, 3⟩)", "= 7"),
    (r"\fold(/, ⟨12, 3⟩)", "= 4"),
    (r"\fold(^, ⟨2, 3⟩)", "= 8"),
    (r"\map(-, [1, 2])", "= [-1, -2]"),
    (r"\map(√, [4, 9])", "= [2, 3]"),
    (r"\fold(∪, ⟨{1}, {2}⟩)", "= {1, 2}"),
    (r"\fold(\cup, ⟨{1}, {2}⟩)", "= {1, 2}"),
    (r"\fold(∩, ⟨{1, 2}, {2, 3}⟩)", "= {2}"),
    (r"\fold(∖, ⟨{1, 2, 3}, {2}⟩)", "= {1, 3}"),
    (r"\fold(·, ⟨[1, 2], [3, 4]⟩)", "= 11"),
    (r"\fold(\cdot, ⟨[1, 2], [3, 4]⟩)", "= 11"),
    (r"\filter((<)(_, 3), ⟨1, 2, 3, 4⟩)", "= ⟨1, 2⟩"),
    (r"\filter((>=)(_, 3), ⟨1, 2, 3, 4⟩)", "= ⟨3, 4⟩"),
    (r"\map((∈)(_, {1, 2}), ⟨1, 3⟩)", "= ⟨true, false⟩"),
    (r"(⊆)({1}, {1, 2})", "= true"),
    (r"(<=)(1, 1)", "= true"),
])
def test_operator_as_function_value(src, expected):
    assert ev(src) == expected


def test_operator_binds_and_applies():
    env = {}
    assert ev("g = (+)", env) == "g = <fn +>"
    assert ev("g(1, 2)", env) == "= 3"
    assert ev("g = (+)", env) == "true"


def test_operators_are_singletons_across_spellings():
    env = {}
    ev("g = (∪)", env)
    assert ev(r"g = (\cup)", env) == "true"


def test_minus_negates_or_subtracts():
    assert ev("(-)(5)") == "= -5"
    assert ev("(-)(5, 2)") == "= 3"


def test_operators_compose():
    assert ev(DEFS + "((-) ∘ s)(2)") == "= -4"
    assert ev(DEFS + "(s ∘ (-))(2)") == "= 4"
    assert ev(DEFS + "((√) ∘ s)(3)") == "= 3"


def test_display():
    assert ev("(+)") == "= <fn +>"
    assert ev(DEFS + "(-) ∘ s") == "= <fn - ∘ s>"
    assert ev("(+)(_, 1)") == "= <fn +(_, 1)>"


def test_partial_of_an_operator():
    assert ev("(+)(_, 1)(4)") == "= 5"
    assert ev(r"\map((*)(2, _), [1, 2, 3])") == "= [2, 4, 6]"


def test_operator_value_errors():
    err = fails("(+)(1)", "`+` takes 2 arguments, got 1")
    assert err.span.start == 0
    fails(r"\map(<, ⟨1⟩)", "`<` takes 2 arguments, got 1")
    fails(r"\fold(∪, ⟨1, 2⟩)", "`∪` needs two sets")
    fails(r"\fold(<, ⟨1, 2, 3⟩)", "booleans are not numbers")
    fails("(+)(1, 2, 3)", "takes 2 arguments, got 3")


def test_operators_are_positional_only():
    fails("(+)(1, x=2)", "positional arguments only")


def test_parse_shapes():
    call = parse_program(r"\fold(+, xs)")
    assert isinstance(call, Call) and isinstance(call.args[0], OpRef)
    assert call.args[0].name == "add"
    radical = parse_program(r"\map(√, xs)")
    assert isinstance(radical.args[0], BackslashRef) and radical.args[0].name == "sqrt"


@pytest.mark.parametrize("src", ["g = +", "f(+ 1)", "+", r"\cup", "(+ 1)", "(1 +)"])
def test_bare_operators_stay_errors(src):
    with pytest.raises(ParseError):
        parse_program(src)


def test_negation_and_calls_still_parse():
    assert ev("f(x) = x\nf(-1)") == "= -1"
    assert ev("f(a, b) = a - b\nf(2, -1)") == "= 3"
    assert ev("(-1)") == "= -1"
    assert ev("(1 + 2)") == "= 3"


def test_quote_round_trips():
    env = {}
    assert ev(r"q = \expr(\fold(+, ⟨1, 2⟩))", env) == r"q = \expr(\fold((+), ⟨1, 2⟩))"
    assert ev(r"\eval(q)", env) == "= 3"


def test_reduce_leaves_operator_values_alone():
    assert ev(r"\reduce(\expr(\fold(+, ⟨1, 2⟩)))") == r"= \expr(\fold((+), ⟨1, 2⟩))"
