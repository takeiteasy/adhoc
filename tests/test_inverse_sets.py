import multiprocessing

import pytest

from adhoc import rewrite
from adhoc.driver import run_source
from adhoc.runtime import EvalError, nmul
from adhoc.solution_set import SymbolicSetValue


def ev(source, env=None):
    return run_source(source, {} if env is None else env)[-1]


@pytest.mark.parametrize("source, expected", [
    ("f(x)=x^2\nf⁻¹(4, \\all=\\true)", "= {-2, 2}"),
    ("f(x)=x^2\nf⁻¹(0, \\all=\\true)", "= {0}"),
    ("f(x)=x^2\nf⁻¹(-1, \\all=\\true)", "= {-i, i}"),
    ("f(x)=x^2\nf⁻¹(-1, \\all=\\true, \\domain=\"real\")", "= {}"),
    ("f(x)=x^2\nf⁻¹(3+4i, \\all=\\true)", "= {-2-i, 2+i}"),
    (r"(x ↦ 2x)⁻¹(3, \all=\true)", "= {3/2}"),
    ("f(x)=x^2\ng=f⁻¹\ng(4, \\all=\\true)", "= {-2, 2}"),
    ("f(x)=x^2\nf⁻¹(4, \\all=\\false)", "= 2"),
    (r"\sin⁻¹(1/2, \all=\false)", "= 0.523598775598299..."),
    ("g=\\sin⁻¹\ng(0)", "= 0"),
    (r"(\sin⁻¹)⁻¹(0)", "= 0"),
    (r"\sqrt⁻¹(2, \all=\true)", "= {4}"),
    (r"\sqrt⁻¹(-1, \all=\true)", "= {}"),
    (r"\ln⁻¹(0, \all=\true)", "= {1}"),
    (r"\log⁻¹(0, \all=\true)", "= {1}"),
    (r'\exp⁻¹(1, \all=\true, \domain="real")', "= {0}"),
])
def test_inverse_modes(source, expected):
    assert ev(source) == expected


def test_all_preimages_retain_exact_irrational_roots():
    env = {}
    run_source("f(x)=x^2\ns=f⁻¹(2, \\all=\\true)", env)
    assert len(env["s"].items) == 2
    assert all(nmul(root, root) == 2 for root in env["s"].items)


@pytest.mark.parametrize("head", [r"\sin", r"f", r"g"])
def test_periodic_preimages_membership_and_tex(head):
    env = {}
    run_source("f(x)=\\sin(x)\ng=\\sin⁻¹", env)
    call = head if head == "g" else head + "⁻¹"
    run_source("s=" + call + r"(0, \all=\true)", env)
    assert isinstance(env["s"], SymbolicSetValue)
    assert ev(r"\pi ∈ s", env) == "= true"
    assert ev(r"\pi/2 ∈ s", env) == "= false"
    assert r"\mathbb{Z}" in ev(r"\tex(s)", env)


def test_constant_function_preimages_are_whole_domain_or_empty():
    assert ev("f(x)=2\nf⁻¹(2, \\all=\\true)") == "= ℂ"
    assert ev("f(x)=2\nf⁻¹(2, \\all=\\true, \\domain=\"real\")") == "= ℝ"
    assert ev("f(x)=2\nf⁻¹(3, \\all=\\true)") == "= {}"


def test_float_target_uses_the_solution_set_path():
    env = {}
    run_source("f(x)=x^2\ns=f⁻¹(4., \\all=\\true)", env)
    assert sorted(float(root) for root in env["s"].items) == [-2., 2.]


@pytest.mark.parametrize("source, fragment", [
    ("f(x)=x\nf⁻¹(1, \\all=1)", "all needs a boolean"),
    ("f(x)=x\nf⁻¹(1, \\domain=\"real\")", "domain requires all=true"),
    ("f(x)=x\nf⁻¹(1, \\all=\\true, \\domain=\"integer\")", 'domain="complex" or domain="real"'),
    ("f(x)=x\nf⁻¹(1, \\all=\\true, \\domain=1)", 'domain="complex" or domain="real"'),
    ("f(x)=x\nf⁻¹(\\all=\\true)", "takes 1 argument"),
    ("f(x)=x\nf⁻¹(1, 2, \\all=\\true)", "takes 1 argument"),
    ("f(x)=x\nf⁻¹(\\true, \\all=\\true)", "number"),
    ("f(x)=x\nf⁻¹(1\\metre, \\all=\\true)", "dimensioned inverse"),
    ("f(x)=x*\\metre\nf⁻¹(1, \\all=\\true)", "dimensioned inverse"),
    ("g(x)=x*\\metre\nf(x)=g(x)\nf⁻¹(1, \\all=\\true)", "nested dimensioned"),
    ("f(x)=x\nf⁻¹(\\inf, \\all=\\true)", "finite"),
    ("f(x,y)=x+y\nf⁻¹(1, \\all=\\true)", "one-parameter"),
    ("f(x)=(y=x; y)\nf⁻¹(1, \\all=\\true)", "several statements"),
    (r"\floor⁻¹(1, \all=\true)", "supported elementary"),
    (r'\py("math.sin")⁻¹(0, \all=\true)', "supported elementary"),
    ("f(x)=x\n(f ∘ f)⁻¹(1, \\all=\\true)", "supported elementary"),
    ("f(x)=x+\\sin(x)\nf⁻¹(1, \\all=\\true)", "closed form"),
    ("f(x)=x\nf⁻¹(1, \\all=\\true, \\other=1)", "unexpected keyword"),
])
def test_invalid_or_unsupported_inverse_requests(source, fragment):
    with pytest.raises(EvalError) as failure:
        run_source(source, {})
    assert fragment in str(failure.value)


def test_unresolved_branch_never_returns_a_partial_set(monkeypatch):
    import sympy
    x = sympy.Symbol("x")
    unresolved = sympy.Union(sympy.FiniteSet(0),
                            sympy.ConditionSet(x, sympy.Eq(x + sympy.sin(x), 0), sympy.S.Reals))
    monkeypatch.setattr(rewrite.sympy, "solveset", lambda *args: unresolved)
    with pytest.raises(EvalError, match="closed form"):
        ev("f(x)=x\nf⁻¹(0, \\all=\\true)")


def spin(*args, **kwargs):
    while True:
        pass


@pytest.mark.parametrize("operation", ["bridge", "solve"])
def test_all_preimages_timeout_covers_expansion_and_solving(monkeypatch, operation):
    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "0.1")
    if operation == "bridge":
        monkeypatch.setattr(rewrite, "_bridge_function", spin)
    else:
        monkeypatch.setattr(rewrite.sympy, "solveset", spin)
    with pytest.raises(EvalError, match="took longer than 0.1s"):
        ev("f(x)=x^2\nf⁻¹(4, \\all=\\true)")
    assert not multiprocessing.active_children()


@pytest.mark.parametrize("operation", [r"\solve(f)", r"\simplify(f)", r"\deriv(f)", r"\grad(f)"])
def test_function_rewrites_include_expansion_in_timeout(monkeypatch, operation):
    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "0.1")
    monkeypatch.setattr(rewrite, "_bridge_function", spin)
    with pytest.raises(EvalError, match="took longer than 0.1s"):
        ev("f(x)=x\n" + operation)
    assert not multiprocessing.active_children()
