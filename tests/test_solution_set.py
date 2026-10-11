import pytest
import sympy

from adhoc import rewrite
from adhoc.driver import run_source
from adhoc.runtime import EvalError
from adhoc.solution_set import SymbolicSetValue
from adhoc.tensor import SetValue


def ev(source, env=None):
    return run_source(source, {} if env is None else env)[-1]


def test_scalar_families_are_values_with_membership():
    env = {}
    run_source(r"s=\solve(`(\sin(x)=0))", env)
    assert isinstance(env["s"], SymbolicSetValue)
    assert "∈ ℤ" in ev("s", env) and "∪" in ev("s", env)
    for point in ["0", r"\pi", r"-3*\pi"]:
        assert ev(f"{point} ∈ s", env) == "= true"
    assert ev(r"\pi/2 ∈ s", env) == "= false"
    assert ev("1 ∉ s", env) == "= true"
    assert ev(r"\tex(s)", env).count(r"\\mathbb{Z}") == 2


def test_complex_exponential_family_and_real_root():
    env = {}
    run_source(r"s=\solve(`(e^x=5))", env)
    assert isinstance(env["s"], SymbolicSetValue)
    assert ev(r"\ln(5)+2*\pi*i ∈ s", env) == "= true"
    assert ev(r"\ln(6) ∈ s", env) == "= false"
    run_source(r'r=\solve(`(e^x=5), \domain="real")', env)
    assert isinstance(env["r"], SetValue)
    assert ev(r"\ln(5) ∈ r", env) == "= true"


@pytest.mark.parametrize("domain, display, tex", [
    ("complex", "ℂ", r"\\mathbb{C}"),
    ("real", "ℝ", r"\\mathbb{R}"),
])
def test_whole_domains(domain, display, tex):
    env = {}
    run_source(r' s=\solve(`(x=x), `(x), \domain="' + domain + '")', env)
    assert ev("s", env) == "= " + display
    assert tex in ev(r"\tex(s)", env)
    assert ev("2 ∈ s", env) == "= true"
    assert ev("i ∈ s", env) == ("= true" if domain == "complex" else "= false")


@pytest.mark.parametrize("source, expected", [
    (r'\solve(`(x^2+1), \domain="real")', "= {}"),
    (r'\solve(`(x^2-4), \domain="real")', "= {-2, 2}"),
    (r'\solve(`(x=x+1), `(x), \domain="real")', "= {}"),
    (r'\solve(`(x^2+1), \domain="complex")', "= {-i, i}"),
    (r'f(x)=x^2-4' + '\n' + r'\solve(f, \domain="real")', "= {-2, 2}"),
    (r'\solve(⟨`(x^2+1), `(y-x)⟩, ⟨`(x), `(y)⟩, \domain="real")', "= {}"),
    (r'\solve(⟨`(x^2-1), `(y-x)⟩, ⟨`(y), `(x)⟩, \domain="real")', "= {⟨-1, -1⟩, ⟨1, 1⟩}"),
    (r'\solve(⟨`(x^3-x), `(y-x)⟩, ⟨`(x), `(y)⟩, \domain="real")', "= {⟨-1, -1⟩, ⟨0, 0⟩, ⟨1, 1⟩}"),
    (r'\solve(⟨`(x^3-1), `(y-x)⟩, ⟨`(x), `(y)⟩, \domain="real")', "= {⟨1, 1⟩}"),
])
def test_domains_for_scalar_and_system_solves(source, expected):
    assert ev(source) == expected


def test_real_system_discards_nonreal_rows_before_uncertain_coordinates():
    assert ev(r'\solve(⟨`(x^2+1), `(y-a)⟩, ⟨`(x), `(y)⟩, \domain="real")') == "= {}"


@pytest.mark.parametrize("source, fragment", [
    (r'\solve(`(x), \domain="integer")', 'domain="complex" or domain="real"'),
    (r'\solve(`(x), \domain=1)', 'domain="complex" or domain="real"'),
    (r'\solve(`(x), \domain=\true)', 'domain="complex" or domain="real"'),
    (r'\solve(⟨`(x-a), `(y-2*x)⟩, ⟨`(x), `(y)⟩, \domain="real")', "cannot determine"),
    (r'\solve(⟨`(x+y-1)⟩, ⟨`(x), `(y)⟩, \domain="real")', "infinitely many"),
    (r'\solve(`(x+\sin(x)))', "closed form"),
    (r'\solve(`(\sin(x)-a), `(x), \domain="real")', "closed form"),
])
def test_solver_errors_have_spans(source, fragment):
    with pytest.raises(EvalError) as error:
        run_source(source, {})
    assert fragment in str(error.value)
    assert error.value.span is not None
    assert "internal error" not in str(error.value)


def test_free_parameters_stay_symbolic_and_binders_do_not_capture_them():
    env = {}
    run_source(r"s=\solve(`(\sin(x)-n), `(x))", env)
    assert "n₁ ∈ ℤ" in ev("s", env)
    before = ev("s", env)
    run_source("n=0", env)
    assert ev("s", env) == before
    with pytest.raises(EvalError, match="cannot determine membership"):
        run_source("0 ∈ s", env)


def test_scalar_domain_intersections_remain_symbolic():
    env = {}
    run_source(r's=\solve(`(x-a), `(x), \domain="real")', env)
    assert isinstance(env["s"], SymbolicSetValue)
    assert "ℝ" in ev("s", env) and "a" in ev("s", env)
    with pytest.raises(EvalError, match="cannot determine membership"):
        run_source("1 ∈ s", env)


def test_values_pass_through_functions_and_nested_collections():
    env = {}
    run_source(r"s=\solve(`(\sin(x))); f(t)=t" + '\n' + r"a=⟨f(s), {s}⟩", env)
    assert ev("a[1]=s", env) == "= true"
    assert ev("s ∈ a[2]", env) == "= true"
    assert r"\\mathbb{Z}" in ev(r"\tex(a)", env)
    assert ev(r"s=\solve(`(\sin(y)))", env) == "true"
    assert ev("s={0}", env) == "false"
    assert ev("{0}=s", env) == "= false"


def test_equality_normalizes_bound_names():
    n, k = sympy.Dummy("n", integer=True), sympy.Dummy("k", integer=True)
    a = SymbolicSetValue(sympy.ImageSet(sympy.Lambda(n, n*sympy.pi), sympy.S.Integers))
    b = SymbolicSetValue(sympy.ImageSet(sympy.Lambda(k, k*sympy.pi), sympy.S.Integers))
    assert a == b


def test_mixed_finite_and_infinite_union_renders():
    n = sympy.Dummy("n", integer=True)
    value = SymbolicSetValue(sympy.Union(sympy.FiniteSet(sympy.Rational(1, 2)),
        sympy.ImageSet(sympy.Lambda(n, n*sympy.pi), sympy.S.Integers)))
    assert "1 / 2" in value.render()
    assert "∪" in value.render()
    assert r"\frac{1}{2}" in value.render(tex=True)
    assert value.contains(0.5)


@pytest.mark.parametrize("operation, fragment", [
    (r"\len(s)", "length"), ("s[1]", "cannot be indexed"),
    ("s+s", "arithmetic"), ("s*2", "arithmetic"), ("s^2", "arithmetic"),
    ("s ∪ {0}", "does not support symbolic sets"),
    ("{0} ∩ s", "does not support symbolic sets"),
    ("s ∖ {0}", "does not support symbolic sets"),
    ("{0} ⊆ s", "does not support symbolic sets"),
    ("s ⊂ s", "does not support symbolic sets"),
    ("s ⊇ s", "does not support symbolic sets"),
    (r"\sum(x=s) x", "cannot be enumerated"),
    ("{x | x ∈ s}", "cannot be enumerated"),
    (r"\map(x ↦ x, s)", "cannot be enumerated"),
    (r"\take(1, s)", "cannot be enumerated"),
    ('"a" ∈ s', "needs a number"),
])
def test_symbolic_set_unsupported_operations(operation, fragment):
    env = {}
    run_source(r"s=\solve(`(\sin(x)))", env)
    with pytest.raises(EvalError) as error:
        run_source(operation, env)
    assert fragment in str(error.value)
    assert error.value.span is not None
    assert "internal error" not in str(error.value)


def test_conditions_nested_in_unions_remain_errors(worker_patch):
    x = sympy.Symbol("x")
    unresolved = sympy.Union(sympy.FiniteSet(0),
        sympy.ConditionSet(x, sympy.Eq(x+sympy.sin(x), 0), sympy.S.Reals))
    worker_patch("sympy", "solveset", unresolved, constant=True)
    with pytest.raises(EvalError, match="closed form"):
        run_source(r"\solve(`(x))", {})


def spin(*args):
    while True:
        pass


def test_membership_timeout(worker_patch, monkeypatch):
    env = {}
    run_source(r"s=\solve(`(\sin(x)))", env)
    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "0.05")
    worker_patch("sympy", "Set.contains", spin)
    with pytest.raises(EvalError, match="took longer than 0.05s"):
        run_source("0 ∈ s", env)


def test_real_system_checks_share_solver_timeout(worker_patch, monkeypatch):
    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "0.05")
    worker_patch("sympy", "simplify", spin)
    with pytest.raises(EvalError, match="took longer than 0.05s"):
        run_source(r'\solve(⟨`(x-1)⟩, ⟨`(x)⟩, \domain="real")', {})
