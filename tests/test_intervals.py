import math
from pathlib import Path

import pytest

from adhoc.driver import run_source
from adhoc.expression import show
from adhoc.parser import parse_program
from adhoc.runtime import EvalError, IntervalValue, RangeValue


def ev(source, env=None):
    return run_source(source, {} if env is None else env)[-1]


def num(source):
    return complex(ev(source)[2:].replace("i", "j"))


@pytest.mark.parametrize("bounds, body, expected", [
    (r"-\inf..0", "e^x", 1),
    (r"-\inf..2", "e^(x-2)", 1),
    (r"-2..\inf", "e^(-x-2)", 1),
    (r"0..\inf", "e^(-x)", 1),
    (r"-\inf..\inf", "e^(-x^2)", math.sqrt(math.pi)),
    (r"-\inf..", "1/(1+x^2)", math.pi),
    (r"\inf..-\inf", "1/(1+x^2)", -math.pi),
    (r"0..-\inf", "e^x", -1),
    (r"\inf..0", "e^(-x)", -1),
    (r"-\inf..0", "i*e^x", 1j),
    (r"-\inf..\inf", "(1+i)*e^(-x^2)", (1+1j)*math.sqrt(math.pi)),
])
def test_infinite_integrals(bounds, body, expected):
    for spelling in (r"\int", "∫"):
        assert num(f"{spelling}(x={bounds}) {body}") == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize("body", ["1", "x/(1+x^2)", "x < 0 ? 1 : e^(-x)",
                                  "x < 0 ? e^x : 1"])
def test_whole_line_requires_both_tails_to_converge(body):
    with pytest.raises(EvalError, match="did not converge"):
        ev(r"∫(x=-\inf..\inf) " + body)


def test_reusable_bounds_and_local_binders():
    env = {}
    run_source("r = -\\inf..0\nx = 7\nf(a) = a\ng(a) = ∫(x=a) e^x", env)
    assert isinstance(env["r"], IntervalValue)
    assert ev("f(r)", env) == "= <interval -Inf..0>"
    assert ev("g(r)", env) == "= 1.0"
    assert ev("x", env) == "= 7"
    assert ev(r"(x ↦ x)(-\inf..0)", env) == "= <interval -Inf..0>"
    env["p"] = lambda value: value
    assert ev("p(r)", env) == "= <interval -Inf..0>"
    assert ev("∫(x=p(r)) e^x", env) == "= 1.0"


def test_interval_storage_equality_and_orientation():
    assert ev(r"r = -\inf..0; r = -\inf..0") == "true"
    assert ev(r"r = -\inf..0; r = 0..-\inf") == "false"
    assert ev(r"r = -\inf..; r = -\inf..\inf") == "true"
    assert ev(r"r = 0..\inf; r = 0..") == "false"
    assert ev(r"{-\inf..0, -\inf..0, 0..-\inf}") == (
        "= {<interval -Inf..0>, <interval 0..-Inf>}")
    assert ev(r"a = ⟨-\inf..0⟩; a[1]") == "= <interval -Inf..0>"
    assert num(r"a = ⟨-\inf..0⟩; ∫(x=a[1]) e^x") == pytest.approx(1)


def test_large_exact_endpoints_remain_finite_values():
    env = {}
    run_source(r"r = -\inf..10^1000; s = 10^1000..\inf", env)
    assert env["r"].end == env["s"].start == 10**1000
    assert ev(r"r = -\inf..10^1000", env) == "true"
    assert ev(r"r = 10^1000..\inf", env) == "false"
    assert ev(r"r = -\inf..1.", env) == "false"
    with pytest.raises(EvalError, match="too large to widen"):
        ev("∫(x=r) 1", env)


@pytest.mark.parametrize("bounds, value, expected", [
    (r"-\inf..0", "-0.5", True),
    (r"-\inf..0", "0", True),
    (r"-\inf..0", "0.5", False),
    (r"0..-\inf", "-0.5", True),
    (r"0..\inf", "0.5", True),
    (r"\inf..0", "0", True),
    (r"\inf..0", "-0.5", False),
    (r"-\inf..\inf", "π", True),
    (r"\inf..-\inf", "√2", True),
    (r"-\inf..0", "-10^1000", True),
    (r"0..\inf", "10^1000", True),
    (r"0. ..\inf", "10^1000", True),
    (r"-\inf..0.", "-10^1000", True),
    (r"-\inf..10^1000", "0.", True),
    (r"-\inf..\inf", r"\inf", False),
    (r"-\inf..\inf", r"-\inf", False),
    (r"-\inf..\inf", r"\nan", False),
    (r"-\inf..\inf", "i", False),
    (r"-\inf..\inf", r"\true", False),
    (r"-\inf..\inf", '"x"', False),
])
def test_real_interval_membership(bounds, value, expected):
    assert ev(f"{value} ∈ ({bounds})") == f"= {str(expected).lower()}"
    assert ev(f"{value} ∉ ({bounds})") == f"= {str(not expected).lower()}"


@pytest.mark.parametrize("source, message", [
    (r"\inf..\inf", "equal infinities"),
    (r"-\inf..-\inf", "equal infinities"),
    (r"\inf..", "equal infinities"),
    (r"-\inf..\nan", "range end"),
    (r"\nan..\inf", "range start"),
    (r"i..\inf", "real numbers"),
    (r"-\inf..i", "real numbers"),
    (r"-\inf,0..1", "plain range"),
    (r"0,1..\inf", "plain range"),
])
def test_invalid_interval_bounds(source, message):
    with pytest.raises(EvalError, match=message):
        ev(source)


@pytest.mark.parametrize("source, message", [
    (r"Σ(x=r) x", "range or collection"),
    (r"∀(x=r) x > 0", "range or collection"),
    (r"\map(\sin,r)", "range or collection"),
    (r"\fold(+,r)", "range or collection"),
    (r"{x ∈ r | x > 0}", "range or collection"),
    (r"\len(r)", "collection"),
    (r"r[1]", "not indexable"),
    (r"v = [1,2]; v[r]", "index"),
    (r"r+1", "numbers"),
])
def test_intervals_reject_sequence_operations(source, message):
    with pytest.raises(EvalError, match=message):
        ev(r"r = -\inf..0; " + source)


def test_existing_ranges_keep_progression_semantics():
    env = {}
    run_source("r = 0..; s = 0..1", env)
    assert isinstance(env["r"], RangeValue)
    assert isinstance(env["s"], RangeValue)
    assert ev("0.5 ∈ r", env) == "= false"
    assert ev("0.5 ∈ s", env) == "= false"
    assert ev("Σ(x=0..3) x", env) == "= 6"
    assert ev(r"\map(\sin,0..1)", env).startswith("= ⟨0, ")
    assert ev("∫(x=r) e^(-x)", env) == "= 1.0"


def test_interval_quotes_and_reduction():
    source = r"∫(x=-\inf..\inf) 1/(1+x^2)"
    shown = show(parse_program(source))
    assert show(parse_program(shown)) == shown
    assert num(r"q = \expr(∫(x=r) e^x); \eval(q,r=-\inf..0)") == pytest.approx(1)
    assert ev(r"\reduce(\expr((\fn(y) ∫(x=-\inf..0) e^x+y)(x)))") == (
        r"= \expr((∫(\reduce_a=((-\inf)..0)) ((e ^ \reduce_a) + x)))")


def test_interval_diagnostics_keep_byte_spans():
    source = r"π + ∫(x=-\inf..0) \foo"
    with pytest.raises(EvalError, match="not bound") as failure:
        ev(source)
    span = failure.value.span
    assert source.encode()[span.start:span.end] == b"\\foo"
    source = r"π + (-\inf..\nan)"
    with pytest.raises(EvalError, match="range end") as failure:
        ev(source)
    span = failure.value.span
    assert source.encode()[span.start:span.end] == b"-\\inf..\\nan"


def test_calculus_demo():
    source = Path(__file__).resolve().parents[1] / "demos" / "calculus.ad"
    assert run_source(source.read_text(), {})
