from fractions import Fraction

import pytest

from adhoc.driver import run_source
from adhoc.runtime import EvalError, neq, nshow
from adhoc.units import Quantity, catalogue, parts


def ev(source, env=None):
    return run_source(source, {} if env is None else env)[-1]


def value(source):
    env = {}
    run_source("q=" + source, env)
    return env["q"]


def fails(source, message):
    with pytest.raises(EvalError, match=message):
        run_source(source, {})


def test_exact_scales_and_conversions():
    assert ev(r"\magnitude(1000\metre,\kilometre)") == "= 1"
    assert ev(r"\convert(1000\metre,\kilometre)") == r"= 1*\kilometre"
    assert ev(r"\magnitude(1\gram,\kilogram)") == "= 1/1000"
    assert ev(r"\magnitude(1\newton,\kilogram*\metre/\second^2)") == "= 1"
    assert parts(value(r"0.1\metre+0.2\metre"))[0] == Fraction(3, 10)
    assert ev(r'\furlong=\unit("furlong",201.168\metre); \convert(201.168\metre,\furlong)') == r"= 1*\furlong"
    assert ev(r"m=2;s=3; m+s") == "= 5"


@pytest.mark.parametrize("source,message", [
    (r"2\metre+0", "matching dimensions"),
    (r"2\metre+3\second", "matching dimensions"),
    (r"2\metre<3\second", "matching dimensions"),
    (r"\convert(2\metre,\second)", "matching dimensions"),
    (r"\sin(2\metre)", "dimensionless"),
    (r"\ln(2\metre)", "dimensionless"),
    (r"\metre^0.5e0", "exact rational"),
    (r"2^\metre", "dimensionless"),
    (r'\unit("bad",-2\metre)', "positive"),
    (r'\unit("bad",2.\metre)', "exact"),
    (r'\unit("metre",2\metre)', "fresh"),
    (r'\py("float")(2\metre)', "explicit magnitude"),
])
def test_unit_errors(source, message):
    fails(source, message)


def test_quantity_arithmetic_and_rendering():
    assert ev(r"9.8\metre \per \second^2") == r"= 49/5*\metre*\second^(-2)"
    assert ev(r"\sqrt(4\metre^2)") == r"= 2*\metre"
    assert ev(r"\root(8\metre^3,3)") == r"= 2*\metre"
    assert ev(r"2\metre/\metre") == "= 2"
    assert ev(r"2\metre-2\metre") == r"= 0*\metre"
    assert ev(r"2\metre=200\centimetre") == "= true"
    assert ev(r"2\metre=2\second") == "= false"
    assert ev(r"2\metre≈200.\centimetre") == "= true"
    assert ev(r"\abs(-2\metre)") == r"= 2*\metre"
    assert ev(r"\sin(\pi/2*\radian)") == "= 1"
    assert "metre" in ev(r"\tex(2\metre/\second)")
    assert isinstance(value(r"0\metre"), Quantity)
    assert ev(r"\isfinite(2\metre)") == "= true"
    assert ev(r"\sum(i=1..3) i\metre") == r"= 6*\metre"


def test_tensor_unit_operations():
    assert ev(r"[1,2]*\metre @ [3,4]*\second") == r"= 11*\metre*\second"
    assert ev(r"\magnitude([1,2]*\metre,\centimetre)") == "= [100, 200]"
    assert ev(r"\diag([1,2]*\metre)") == r"= [1*\metre, 0*\metre; 0*\metre, 2*\metre]"
    assert ev(r"\det([1,2;3,4]*\metre)") == r"= -2*\metre^(2)"
    assert ev(r"\det([1,2;2,4]*\metre)") == r"= 0*\metre^(2)"
    assert ev(r"\rank([1,2;2,4]*\metre)") == "= 1"
    assert ev(r"\tr([1,2;3,4]*\metre)") == r"= 5*\metre"
    assert ev(r"\inv([2,0;0,4]*\metre)") == r"= [1/2*\metre^(-1), 0*\metre^(-1); 0*\metre^(-1), 1/4*\metre^(-1)]"
    assert ev(r"\linsolve([2,0;0,4]*\second,[6,8]*\metre)") == r"= [3*\metre*\second^(-1), 2*\metre*\second^(-1)]"
    assert ev(r"\norm([3,4]*\metre)") == r"= 5*\metre"
    assert ev(r"a=[1,2]*\metre; a[2]") == r"= 2*\metre"
    fails(r"[1\metre,2\second]", "matching dimensions")
    fails(r"[0,2\metre]", "matching dimensions")
    fails(r"\stack(1\metre,2\second)", "matching dimensions")


def test_symbolic_dimension_annotations():
    annotations = r"\dimensions=⟨⟨`(x),\metre⟩⟩"
    assert ev(r"\solve(`(x=2\metre),`(x)," + annotations + ")") == r"= {2*\metre}"
    assert ev(r"\eval(\simplify(`(x+2\metre)," + annotations + r"),x=3\metre)") == r"= 5*\metre"
    assert ev(r"\eval(\deriv(`(x^2),`(x)," + annotations + r"),x=3\metre)") == r"= 6*\metre"
    fails(r"\simplify(`(x+\second)," + annotations + ")", "matching dimensions")
    fails(r"\simplify(`(x+\metre))", "missing dimension annotation")
    fails(r"\simplify(`(x),\dimensions=⟨⟨`(x),\metre⟩,⟨`(x),\second⟩⟩)", "distinct names")
    fails(r"\eval(\simplify(`(x+\metre)," + annotations + r"),x=3\second)", "conflicting dimensions")


def test_dimensioned_system_solutions_and_families():
    assert ev(r"\solve(⟨`(x=2\metre),`(y=3\second)⟩,⟨`(x),`(y)⟩,\dimensions=⟨⟨`(x),\metre⟩,⟨`(y),\second⟩⟩)") == r"= {⟨2*\metre, 3*\second⟩}"
    env = {}
    run_source(r"s=\solve(`(x=x),`(x),\dimensions=⟨⟨`(x),\metre⟩⟩)", env)
    assert ev(r"2\metre ∈ s", env) == "= true"
    assert ev(r"2\second ∈ s", env) == "= false"
    run_source(r"r=\solve(`(\sin(x/\metre)=0),`(x),\dimensions=⟨⟨`(x),\metre⟩⟩)", env)
    assert ev(r"\pi*\metre ∈ r", env) == "= true"
    assert ev(r"\pi/2*\metre ∈ r", env) == "= false"
    assert "metre" in ev(r"\tex(r)", env)


def test_dimensioned_calculus():
    assert parts(value(r"\diff(x=2\metre) x^2"))[0] == pytest.approx(4)
    assert ev("f(x)=x^2\nf'(2\\metre)") == r"= 4*\metre"
    assert ev("f(x)=x^3\nf''(2\\metre)") == r"= 12*\metre"
    assert ev(r"\int(x=0\second..2\second) 3\metre/\second") == r"= 6.0*\metre"
    assert ev(r"\int(x=2\second..0\second) 3\metre/\second") == r"= -6.0*\metre"
    assert ev(r"\int(x=1\second..1\second) 3\metre/\second") == r"= 0.0*\metre"
    assert parts(value(r"\int(x=0\second..) \exp(-x/\second)*\metre/\second"))[0] == pytest.approx(1)
    fails(r"\int(x=0\metre..2\second) x", "matching dimensions")
    fails(r"\diff(x=0\metre) {x<0\metre: x; x*\second}", "dimensions change")


@pytest.mark.parametrize("source,message", [
    (r"\eig([1,0;0,2]*\metre)", "eigensystems are unsupported"),
    (r"\lim(x=2\metre) x", "limits are unsupported"),
    (r"\lim(x=2) x*\metre", "limits are unsupported"),
    (r"\sum(i=1..) \metre/i^2", "infinite folds are unsupported"),
    ("f(x)=x^2\nf⁻¹(2\\metre)", "inverse functions are unsupported"),
])
def test_deferred_unit_integrations(source, message):
    fails(source, message)


def test_symbolic_annotations_override_session_bindings():
    env = {}
    run_source(r"x=100\metre", env)
    assert ev(r"\solve(`(x=2\metre),`(x),\dimensions=⟨⟨`(x),\metre⟩⟩)", env) == r"= {2*\metre}"
    fails(r"\simplify(`(\pi),\dimensions=⟨⟨`(\pi),\metre⟩⟩)", "conflicting dimensions")


def test_symbolic_rewrite_operations_preserve_dimensions():
    for operation in ("simplify", "expand", "factor"):
        source = "\\" + operation + r"(`(x^2-4\metre^2),\dimensions=⟨⟨`(x),\metre⟩⟩)"
        assert ev(r"\eval(" + source + r",x=3\metre)") == r"= 5*\metre^(2)"
    assert ev(r"\eval(\deriv(`(x^2),`(x),2,\dimensions=⟨⟨`(x),\metre⟩⟩),x=3\metre)") == "= 2"
    assert ev(r"\eval(\simplify(`(x=2\metre),\dimensions=⟨⟨`(x),\metre⟩⟩),x=2\metre)") == "= true"
    env = {}
    run_source(r"g=\grad(`(x*y),⟨`(x),`(y)⟩,\dimensions=⟨⟨`(x),\metre⟩,⟨`(y),\second⟩⟩)", env)
    assert ev(r"\eval(g[1],x=2\metre,y=3\second)", env) == r"= 3*\second"
    assert ev(r"\eval(g[2],x=2\metre,y=3\second)", env) == r"= 2*\metre"


def test_unit_tiers_and_compound_conversion():
    from adhoc.gauss import Gaussian
    from adhoc.runtime import RRA, Symbolic
    assert isinstance(parts(value(r"(1+i)*\metre"))[0], Gaussian)
    assert isinstance(parts(value(r"\pi*\metre"))[0], Symbolic)
    assert isinstance(parts(value(r"(\pi+1)*\metre"))[0], RRA)
    assert isinstance(parts(value(r"1.\metre"))[0], float)
    converted = value(r"\convert(1\metre/\second,\kilometre/\second)")
    assert neq(converted, value(r"1\metre/\second"))
    assert ev(nshow(converted)) == r"= 1*\metre*\second^(-1)"
    assert ev(r"\norm(-2\metre)") == r"= 2*\metre"
    assert ev(r"\mean(1\metre,3\metre)") == r"= 2*\metre"
    assert ev(r"\min(1\metre,3\metre)") == r"= 1*\metre"


def test_tensor_products_slices_and_dimension_invariant():
    env = {}
    run_source(r"a=[1,2]*\metre; b=[3,4]*\second", env)
    assert ev("aᵀ", env) == r"= [1*\metre, 2*\metre]"
    assert ev("a[1..2]", env) == r"= [1*\metre, 2*\metre]"
    assert ev(r"\magnitude(\outer(a,b),\metre*\second)", env) == "= [3, 4; 6, 8]"
    assert ev(r"\magnitude(\kron(a,b),\metre*\second)", env) == "= [3, 4, 6, 8]"
    assert ev(r"\magnitude([1,0,0]*\metre × [0,1,0]*\second,\metre*\second)") == "= [0, 0, 1]"
    fails(r"\map(\fn(x) {x>1: x\metre; x\second},[1,2])", "matching dimensions")


def test_numeric_derivative_fallback_with_units():
    env = {}
    run_source(r"f(x)={x>0\metre: x^2; x^2}", env)
    result = value(r"\diff(x=2\metre,2) x^3")
    assert result.magnitude == pytest.approx(12)
    assert result.dimensions == catalogue()["metre"].dimensions
    output = ev(r"f'(2\metre)", env)
    assert output.endswith(r"*\metre")


def test_dimensionless_custom_unit_and_display():
    assert ev(r'\degree=\unit("degree",\pi/180); \magnitude(\pi,\degree)') == "= 180"
    assert ev(r'\degree=\unit("degree",\pi/180); \convert(\pi,\degree)') == r"= 180*\degree"
    assert ev(r'\degree=\unit("degree",\pi/180); \sin(90\degree)') == "= 1"
    for magnitude in ("1+i", "1+\\pi*i", "\\sin(1)+i"):
        shown = nshow(value("(" + magnitude + r")*\metre"))
        assert shown.startswith("(") and shown.endswith(r")*\metre")


@pytest.mark.parametrize("index", ["0", "-2", "1/2", "2."])
def test_dimensioned_roots_keep_existing_index_rules(index):
    fails(r"\root(4\metre^2," + index + ")", "positive exact integer")


def test_custom_unit_tex_escapes_underscores():
    from tests.test_tex import tex
    assert tex(r'\foot_unit=\unit("foot_unit",0.3048\metre); \tex(\foot_unit)') == r"\mathrm{foot\_unit}"
