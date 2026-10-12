import pytest

from adhoc.driver import run_source
from adhoc.parser import ParseError
from adhoc.runtime import EvalError, NumError, PRELUDE
from adhoc.span import Span
from adhoc.units import DIMENSIONLESS, Quantity, UnitValue


@pytest.mark.parametrize("value,tier,exact", [
    ("0", "integer", True),
    ("2^100", "integer", True),
    ("1/3", "rational", True),
    ("0.5", "rational", True),
    ("2+3i", "gaussian", True),
    ("π", "symbolic", True),
    ("πi", "symbolic", True),
    ("2^(1/3)", "algebraic", True),
    ("1+√2i", "algebraic", True),
    ("π+1", "rra", True),
    (r"\sin(1+i)", "rra", True),
    ("1.", "float", False),
    ("5e-1", "float", False),
    (r"\inf", "float", False),
    (r"-\inf", "float", False),
    (r"\nan", "float", False),
    ("1.+i", "complex-float", False),
    (r"\complex(\inf, 1.)", "complex-float", False),
    (r"\complex(1., \nan)", "complex-float", False),
])
def test_numeric_tiers(value, tier, exact):
    assert run_source(f"\\tier({value})") == [f'= "{tier}"']
    assert run_source(f"\\exact({value})") == [f"= {str(exact).lower()}"]


@pytest.mark.parametrize("value,tier", [
    ("√2 * √2", "integer"),
    ("6/3", "integer"),
    ("(2+3i)(2-3i)", "integer"),
    ("π-π+1/3", "rational"),
    (r"\complex(1., 0.)", "float"),
    ("π+1.", "float"),
])
def test_tier_of_evaluated_result(value, tier):
    assert run_source(f"\\tier({value})") == [f'= "{tier}"']


def test_introspection_preserves_the_stored_value_and_display_precision():
    env = {}
    run_source("x=π+1", env)
    value = env["x"]
    before = run_source("x", env)
    assert run_source(r"\exact(x); \tier(x)", env) == ['= true', '= "rra"']
    assert env["x"] is value
    assert run_source("x", env) == before


@pytest.mark.parametrize("name", ["exact", "tier"])
@pytest.mark.parametrize("value", [
    r"\true", r"\false", '"1"', "⟨1⟩", "{1}", "[1]",
    "1..3", "1..", r"\sin", r"\fn(x) x", r"\expr(x+1)",
    r"\metre", r"2\metre",
])
def test_rejected_values_and_call_span(name, value):
    call = f"\\{name}({value})"
    source = f"1 + {call}"
    with pytest.raises(EvalError, match="needs a numeric scalar") as failure:
        run_source(source)
    assert failure.value.span == Span(4, len(source.encode()))


@pytest.mark.parametrize("name", ["exact", "tier"])
@pytest.mark.parametrize("value", [
    Quantity(1, DIMENSIONLESS), UnitValue("scalar", 1, DIMENSIONLESS),
])
def test_dimensionless_wrappers_are_not_implicitly_unwrapped(name, value):
    with pytest.raises(NumError, match="needs a numeric scalar"):
        PRELUDE[name](value)


@pytest.mark.parametrize("name", ["exact", "tier"])
@pytest.mark.parametrize("arguments", ["", "1,2", "\\v=1", "1,\\v=2"])
def test_invalid_call_shape(name, arguments):
    with pytest.raises(EvalError, match="TypeError"):
        run_source(f"\\{name}({arguments})")


@pytest.mark.parametrize("name", ["exact", "tier"])
@pytest.mark.parametrize("source", [
    "\\{name}=1", "f(\\{name})=1", "\\let \\{name}=1",
])
def test_names_are_protected(name, source):
    with pytest.raises((EvalError, ParseError), match="protected|redefin|already bound"):
        run_source(source.format(name=name))


def test_higher_order_calls_preserve_booleans_and_strings():
    assert run_source(r"\map(\exact, ⟨1, 0.5, π+1, 1., 1.+i⟩)") == [
        "= ⟨true, true, true, false, false⟩"
    ]
    assert run_source(r"\map(\tier, ⟨1, 0.5, π+1, 1., 1.+i⟩)") == [
        '= ⟨"integer", "rational", "rra", "float", "complex-float"⟩'
    ]
    assert run_source(r"\all(\exact, ⟨1, π, π+1⟩)") == ["= true"]


def test_explicit_quantity_magnitude_extraction():
    assert run_source(r"\exact(\magnitude(2\metre, \metre))") == ["= true"]
    assert run_source(r"\tier(\magnitude(2.\metre, \metre))") == ['= "float"']
