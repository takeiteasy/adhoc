import pytest

from adhoc.driver import run_source
from adhoc.runtime import EvalError


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, fragment):
    with pytest.raises(EvalError) as error:
        run_source(src, {})
    assert fragment in str(error.value)


def test_simplify_expand_factor_return_quotes():
    assert ev(r"\simplify(\expr((x^2 - 1)/(x - 1)))") == r"= \expr((x + 1))"
    assert ev(r"\simplify(\expr(\sin(x)^2 + \cos(x)^2))") == r"= \expr(1)"
    assert ev(r"\expand(\expr((x + 1)^2))") == r"= \expr((((x ^ 2) + (2 * x)) + 1))"
    assert ev(r"\factor(\expr(x^2 - 1))") == r"= \expr(((x + 1) * (x - 1)))"


def test_numeric_factor_is_unchanged():
    assert ev(r"\factor(12)") == "= ⟨⟨2, 2⟩, ⟨3, 1⟩⟩"


def test_rewritten_quotes_evaluate():
    env = {}
    run_source(r"q = \expand(\expr((x + 1)^2))", env)
    assert run_source(r"\eval(q, x=3)", env) == ["= 16"]


def test_names_keep_their_spelling():
    assert ev(r"\simplify(\expr(α + α))") == r"= \expr((2 * α))"
    assert ev(r"\simplify(\expr(\foo + \foo))") == r"= \expr((2 * \foo))"
    assert ev(r"\simplify(\expr(\pi + \pi))") == r"= \expr((2 * \pi))"


def test_function_input_uses_closure_bindings():
    assert ev("f(x) = x + x\n\\simplify(f)") == r"= \expr((2 * x))"
    assert ev("a = 3\nf(x) = a x + x\n\\simplify(f)") == r"= \expr((4 * x))"
    assert ev("\\simplify(i ↦ i + i)") == r"= \expr((2 * i))"


def test_undefined_function_calls_stay_symbolic():
    assert ev(r"\simplify(\expr(g(x) + g(x)))") == r"= \expr((2 * g(x)))"


def test_solve_quadratic_and_complex_roots():
    assert ev(r"\solve(\expr(x^2 - 4))") == "= {-2, 2}"
    assert ev(r"\solve(\expr(x^2 + 1))") == "= {-i, i}"
    assert ev(r"\solve(\expr(x^2 + x + 1))").count("i") == 2
    assert ev(r"\solve(\expr(x - 1 - x + 1 + x^2))") == "= {0}"


def test_solve_with_no_solutions_is_the_empty_set():
    assert ev("f(x) = 1\n\\solve(f)") == "= {}"


def test_solve_takes_a_function_and_a_quoted_unknown():
    assert ev("f(x) = x^2 - 9\n\\solve(f)") == "= {-3, 3}"
    assert ev(r"\solve(\expr(a x - b), \expr(x))") == r"= {\expr((b / a))}"
    assert ev(r"\solve(\expr(a x - b), \expr(a))") == r"= {\expr((b / x))}"


def test_solve_irrational_roots_are_values():
    assert ev(r"\solve(\expr(x^2 - 2))") == "= {-1.4142135623731..., 1.4142135623731...}"


def test_solve_errors():
    fails(r"\solve(\expr(a x - b))", "needs the unknown")
    fails(r"\solve(\expr(1 + 0 x), \expr(2))", "quoted name")
    fails(r"\solve(\expr(\sin(x)))", "infinitely many")
    fails(r"\solve(\expr(x + \sin(x)))", "closed form")
    fails(r"\solve(\expr(x - x))", "no unknown")
    fails(r"\solve(2)", "expression quote")


def test_unsupported_constructs_name_themselves():
    fails(r"\expand(\expr(x < 1))", "cannot rewrite compare")
    fails(r"\simplify(\expr({1, 2}))", "cannot rewrite setlit")


def test_statement_quotes_and_multi_statement_functions_are_rejected():
    fails("f(x) = (y = x; y + 1)\n\\simplify(f)", "several statements")
    fails(r"\simplify(\expr((y = 1; y)))", "statement")


@pytest.mark.parametrize("src, expected", [
    ("f(x) = x^3\nf⁻¹(8)", "= 2"),
    ("f(x) = x + 1\nf⁻¹(2)", "= 1"),
    ("(x ↦ 2x)⁻¹(6)", "= 3"),
    ("f(x) = x^2\nf⁻¹(4)", "= 2"),
    ("f(x) = x^2\nf⁻¹(3+4i)", "= 2+i"),
])
def test_inverse_is_exact_when_the_body_solves(src, expected):
    assert ev(src) == expected


def test_inverse_exact_irrational_root():
    assert ev("f(x) = x^2\nf⁻¹(2)") == "= 1.4142135623731..."


def test_inverse_falls_back_to_floats():
    assert float(ev("f(x) = x + \\sin(x)\nf⁻¹(1)")[2:]) == pytest.approx(0.5109734293885692)
    assert ev("f(x) = x^3\nf⁻¹(8.)") == "= 2.0"
    fails("f(x) = x^2\nf⁻¹(-1)", "no value maps")


def test_inverse_solves_once_per_function():
    env = {}
    run_source("f(x) = x^3\ng = f⁻¹", env)
    assert run_source(r"\sum(k=1..3) g(k^3)", env) == ["= 6"]
