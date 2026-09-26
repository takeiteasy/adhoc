import pytest

from adhoc.driver import run_source
from adhoc.runtime import EvalError


def tex(src, env=None):
    text = run_source(src, {} if env is None else env)[-1]
    assert text.startswith('= "') and text.endswith('"')
    return text[3:-1].replace("\\\\", "\\")


def test_fractions_powers_and_roots():
    assert tex(r"\tex(\expr(x^2/2 + 1))") == r"\frac{x^{2}}{2} + 1"
    assert tex(r"\tex(\expr(\sqrt(x) + \root(y, 3)))") == r"\sqrt{x} + \sqrt[3]{y}"
    assert tex(r"\tex(\expr(-(x + 1)^2))") == r"-\left(x + 1\right)^{2}"


def test_juxtaposed_coefficients_and_parentheses():
    assert tex(r"\tex(\expr(2x))") == "2 x"
    assert tex(r"\tex(\expr(2 (x + 1)))") == r"2 \left(x + 1\right)"
    assert tex(r"\tex(\expr(a - (b - c)))") == r"a - \left(b - c\right)"
    assert tex(r"\tex(\expr(a - b - c))") == "a - b - c"


def test_names():
    assert tex(r"\tex(\expr(a₁ + α))") == r"a_{1} + \alpha"
    assert tex(r"\tex(\expr(x_ij))") == "x_{ij}"
    assert tex(r"\tex(\expr(\foo_bar))") == r"\mathrm{foo\_bar}"
    assert tex(r"\tex(π)") == r"\pi"


def test_functions_and_delimiters():
    assert tex(r"\tex(\expr(\sin(x) + \asin(y)))") == r"\sin\left(x\right) + \arcsin\left(y\right)"
    assert tex(r"\tex(\expr(|x| + ⌊y⌋))") == r"\left| x \right| + \left\lfloor y \right\rfloor"
    assert tex(r"\tex(\expr(\myfn(x, 1)))") == r"\operatorname{myfn}\left(x, 1\right)"


def test_binders():
    assert tex(r"\tex(\expr(Σ(i=1..n) i^2))") == r"\sum_{i=1}^{n} i^{2}"
    assert tex(r"\tex(\expr(\lim(x=0) \sin(x)/x))") == r"\lim_{x \to 0} \frac{\sin\left(x\right)}{x}"
    assert tex(r"\tex(\expr(∫(x=0..) e^(-x)))") == r"\int_{0}^{\infty} e^{-x} \, dx"
    assert tex(r"\tex(\expr(∂(x=1) x^2))") == r"\left.\frac{d}{dx}\left(x^{2}\right)\right|_{x=1}"
    assert tex(r"\tex(\expr(∀(x∈S) x > 0))") == r"\forall x \in S,\ x > 0"
    assert tex(r"\tex(\expr(2 * Σ(i=1..3) i))") == r"2 \left(\sum_{i=1}^{3} i\right)"


def test_cases_sets_and_lambdas():
    assert tex(r"\tex(\expr({x < 0: -x; x}))") == (
        r"\begin{cases} -x & \text{if } x < 0 \\ x & \text{otherwise} \end{cases}")
    assert tex(r"\tex(\expr(x > 0 ? 1 : 0))") == (
        r"\begin{cases} 1 & \text{if } x > 0 \\ 0 & \text{otherwise} \end{cases}")
    assert tex(r"\tex(\expr({x ∈ S | x > 1}))") == r"\{ x \in S \mid x > 1 \}"
    assert tex(r"\tex(\expr({x^2 | x ∈ S, x > 1}))") == r"\{ x^{2} \mid x \in S, x > 1 \}"
    assert tex(r"\tex(\expr(x ↦ x + 1))") == r"x \mapsto x + 1"
    assert tex(r"\tex(\expr((x, y) -> x))") == r"\left(x, y\right) \mapsto x"


def test_transpose_and_logic():
    assert tex(r"\tex(\expr(A'))") == "A'"
    assert tex(r"\tex(\expr(Aᵀ))") == r"A^{\mathsf{T}}"
    assert tex(r"\tex(\expr(a ∧ ¬b))") == r"a \land \lnot b"
    assert tex(r"\tex(\expr(x ≤ y))") == r"x \le y"


def test_values():
    assert tex(r"\tex(1/2)") == r"\frac{1}{2}"
    assert tex(r"\tex(-3/4)") == r"-\frac{3}{4}"
    assert tex(r"\tex(7)") == "7"
    assert tex(r"\tex(\sqrt(2))") == r"\sqrt{2}"
    assert tex(r"\tex([1, 2; 3, 4])") == r"\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}"
    assert tex(r"\tex([1, 2])") == r"\begin{pmatrix} 1 \\ 2 \end{pmatrix}"
    assert tex(r"\tex({1, 2})") == r"\{1, 2\}"
    assert tex(r"\tex(∅)") == r"\emptyset"
    assert tex(r"\tex(⟨1, 2⟩)") == r"\langle 1, 2 \rangle"
    assert tex(r"\tex(1..5)") == r"\{1, \ldots, 5\}"
    assert tex(r"\tex(\true)") == r"\text{true}"
    assert tex(r'\tex("a_b")') == r"\text{a\_b}"


def test_functions_render_with_their_bodies():
    env = {}
    run_source("f(x) = x^2 + 1", env)
    assert tex(r"\tex(f)", env) == r"f\left(x\right) = x^{2} + 1"
    assert tex(r"\tex(\fn(x) 2x)", env) == r"x \mapsto 2 x"


def test_the_result_is_an_ordinary_string():
    assert run_source(r'\tex(1/2) + "!"', {})[-1] == r'= "\\frac{1}{2}!"'


def test_unrenderable_values_are_typed_errors():
    with pytest.raises(EvalError):
        run_source('\\tex(\\py("math.sqrt"))', {})


def test_inverse_call_renders_as_inverse_function():
    assert tex(r"\tex(\expr((x ↦ 2x)⁻¹(6)))") == r"\left(x \mapsto 2 x\right)^{-1}\left(6\right)"
    assert tex(r"\tex(\expr(f⁻¹(y)))") == r"f^{-1}\left(y\right)"
    assert tex(r"\tex(\expr(\sin⁻¹(y)))") == r"\sin^{-1}\left(y\right)"
    assert tex(r"\tex(\expr(f²(y)))") == r"\left(f\left(y\right)\right)^{2}"
