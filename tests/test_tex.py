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


def test_equation_quotes_render_both_sides():
    assert tex(r"\tex(`(x^2=4))") == "x^{2} = 4"
    assert tex(r"\tex(\expr((x+1)/2 = \sqrt(y)))") == r"\frac{x + 1}{2} = \sqrt{y}"


@pytest.mark.parametrize("source, expected", [
    (r"\expand(`((x+1)^2=y))", "x^{2} + 2 x + 1 = y"),
    (r"\simplify(`(x+x=y+y))", "2 x = 2 y"),
    (r"\factor(`(x^2-1=y))", r"\left(x + 1\right) \cdot \left(x - 1\right) = y"),
])
def test_rewritten_equations_render_both_sides(source, expected):
    assert tex(r"\tex(" + source + ")") == expected


def test_nested_equality_conditions_render_at_comparison_precedence():
    assert tex(r"\tex(\expr((x=3) ∧ (y<4)))") == r"x = 3 \land y < 4"


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
    assert tex(r"\tex(\expr(|A|))") == r"\left| A \right|"
    assert tex(r"\tex(\expr(\myfn(x, 1)))") == r"\operatorname{myfn}\left(x, 1\right)"


def test_binders():
    assert tex(r"\tex(\expr(Σ(i=1..n) i^2))") == r"\sum_{i=1}^{n} i^{2}"
    assert tex(r"\tex(\expr(\lim(x=0) \sin(x)/x))") == r"\lim_{x \to 0} \frac{\sin\left(x\right)}{x}"
    assert tex(r"\tex(\expr(∫(x=0..) e^(-x)))") == r"\int_{0}^{\infty} e^{-x} \, dx"
    assert tex(r"\tex(\expr(∂(x=1) x^2))") == r"\left.\frac{d}{dx}\left(x^{2}\right)\right|_{x=1}"
    assert tex(r"\tex(\expr(∂(x=1, 3) x^4))") == r"\left.\frac{d^{3}}{dx^{3}}\left(x^{4}\right)\right|_{x=1}"
    assert tex(r"\tex(\expr(∂(x=a, n) x))") == r"\left.\frac{d^{n}}{dx^{n}}\left(x\right)\right|_{x=a}"
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


@pytest.mark.parametrize("bounds, expected", [
    (r"-\inf..0", r"\left(-\infty, 0\right]"),
    (r"0..\inf", r"\left[0, \infty\right)"),
    (r"-\inf..", r"\left(-\infty, \infty\right)"),
    (r"\inf..-\inf", r"\left(\infty, -\infty\right)"),
    (r"0..-\inf", r"\left[0, -\infty\right)"),
])
def test_interval_values(bounds, expected):
    assert tex(r"\tex(" + bounds + ")") == expected


def test_infinite_integral_quote():
    assert tex(r"\tex(\expr(∫(x=-\inf..\inf) e^(-x^2)))") == (
        r"\int_{-\infty}^{\infty} e^{-x^{2}} \, dx")


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
    assert tex(r"\tex(\expr(f²(y)))") == r"f^{2}\left(y\right)"


@pytest.mark.parametrize("source, expected", [
    (r"\sin²(x)", r"\sin^{2}\left(x\right)"),
    (r"\cos³(x+1)", r"\cos^{3}\left(x + 1\right)"),
    (r"f²(y)", r"f^{2}\left(y\right)"),
    (r"\myfn²(x, \a=1)", r"\operatorname{myfn}^{2}\left(x, a = 1\right)"),
    (r"(x ↦ 2x)²(y)", r"\left(x \mapsto 2 x\right)^{2}\left(y\right)"),
    (r"(f ∘ g)²(y)", r"\left(f \circ g\right)^{2}\left(y\right)"),
    (r"\sin(x)^2", r"\sin\left(x\right)^{2}"),
    (r"(2+1)²(x+1)", r"\left(2 + 1\right)^{2} \cdot \left(x + 1\right)"),
    (r"2/(2+1)²(x+1)", r"\frac{2}{\left(2 + 1\right)^{2} \cdot \left(x + 1\right)}"),
])
def test_powered_heads(source, expected):
    assert tex(r"\tex(\expr(" + source + "))") == expected


@pytest.mark.parametrize("source, expected", [
    (r"x²(3)", r"x^{2} \cdot 3"),
    (r"x⁻¹(3)", r"x^{-1} \cdot 3"),
    (r"x²(y+1)", r"x^{2} \cdot \left(y + 1\right)"),
    (r"(x+1)²(3)", r"\left(x + 1\right)^{2} \cdot 3"),
    (r"2*x²(3)", r"2 \left(x^{2} \cdot 3\right)"),
    (r"(x²(3))^2", r"\left(x^{2} \cdot 3\right)^{2}"),
    (r"\sin²(x²(3))", r"\sin^{2}\left(x^{2} \cdot 3\right)"),
])
def test_numeric_head_powers(source, expected):
    env = {}
    run_source("x=2", env)
    assert tex(r"\tex(\expr(" + source + "))", env) == expected


def test_scope_applies_to_aliases_and_higher_order_tex_calls():
    env = {}
    run_source(r"t=\tex; x=2", env)
    assert tex(r"t(`(x²(3)))", env) == r"x^{2} \cdot 3"
    run_source("f(x)=t(`(x²(3)))", env)
    assert tex("f(4)", env) == r"x^{2} \cdot 3"
    assert r"x^{2} \\cdot 3" in run_source(r"\map(t, ⟨`(x²(3))⟩)", env)[-1]


def test_function_rendering_uses_defining_scope_and_masks_parameters():
    env = {}
    run_source("x=2; a=3\nf(x)=x²(3)+a²(4)", env)
    assert tex(r"\tex(f)", env) == r"f\left(x\right) = x^{2}\left(3\right) + a^{2} \cdot 4"
    run_source(r"g(a)=\tex(f)", env)
    assert tex("g(x ↦ x)", env) == r"f\left(x\right) = x^{2}\left(3\right) + a^{2} \cdot 4"


@pytest.mark.parametrize("source, expected", [
    (r"x ↦ x²(3)", r"x \mapsto x^{2}\left(3\right)"),
    (r"Σ(x=1..3) x²(3)", r"\sum_{x=1}^{3} x^{2}\left(3\right)"),
    (r"\lim(x=0) x²(3)", r"\lim_{x \to 0} x^{2}\left(3\right)"),
    (r"∫(x=0..1) x²(3)", r"\int_{0}^{1} x^{2}\left(3\right) \, dx"),
    (r"∂(x=1) x²(3)", r"\left.\frac{d}{dx}\left(x^{2}\left(3\right)\right)\right|_{x=1}"),
    (r"{x²(3) | x ∈ 1..3}", r"\{ x^{2}\left(3\right) \mid x \in \{1, \ldots, 3\} \}"),
])
def test_binders_mask_outer_bindings(source, expected):
    env = {}
    run_source("x=2", env)
    assert tex(r"\tex(`(" + source + "))", env) == expected


def test_rendering_does_not_invoke_heads_arguments_or_exponents():
    called = []

    def side_effect(*args):
        called.append(args)
        return 2

    env = {"f": side_effect}
    assert tex(r"\tex(`(f²(f(1))))", env) == r"f^{2}\left(f\left(1\right)\right)"
    assert tex(r"\tex(`((f(1))²(f(2))))", env) == r"f\left(1\right)^{2} \cdot f\left(2\right)"
    assert tex(r"\tex(`(fᶠ⁽¹⁾(f(2))))", env) == r"f^{f\left(1\right)}\left(f\left(2\right)\right)"
    assert called == []


def test_tex_scope_is_reset_after_a_call():
    from adhoc.parser import parse_program
    from adhoc.tex import node_tex
    env = {}
    run_source("x=2", env)
    assert tex(r"\tex(`(x²(3)))", env) == r"x^{2} \cdot 3"
    assert node_tex(parse_program("x²(3)")) == r"x^{2}\left(3\right)"
