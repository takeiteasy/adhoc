from fractions import Fraction

import pytest

from adhoc.driver import run_source
from adhoc.expression import ExpressionValue, show
from adhoc.lexer import InfixOp, tokenize
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError, NumError, ncongruent
from adhoc.span import Span
from adhoc.tex import node_tex


@pytest.mark.parametrize("operator", ["≡", r"\equiv", "=="])
@pytest.mark.parametrize("marker", ["mod", r"\mod"])
def test_spellings(operator, marker):
    assert run_source(f"17 {operator} 2 ({marker} 5)") == ["= true"]


@pytest.mark.parametrize("a,b,n,expected", [
    (17, 2, 5, True), (17, 3, 5, False), (-7, 2, 3, True),
    (7, -2, -3, True), (99, 0, 1, True), (99, 0, -1, True),
    (10**100 + 1, 1, 10**100, True), (Fraction(6, 1), 0, 3, True),
])
def test_exact_integer_semantics(a, b, n, expected):
    assert ncongruent(a, b, n) is expected


@pytest.mark.parametrize("source,expected", [
    ("17.0 ≡ 2 (mod 2^2+1)", True),
    ("a=17; b=2; n=5; a ≡ b (mod n)", True),
    ("f(x)=x+1\ng(x)=x-1\nf(16) ≡ g(3) (mod 5)", True),
    ("x=1; 12 ≡ 2(x+1) (mod 4)", True),
    ("17 ≡ (7 % 5) (mod 5)", True),
    ("x=2; 19 ≡ x² (mod 5)", True),
    ("m=1;o=2;d=3;n=5;f(x)=x\n30 ≡ f(1(mod n)) (mod 5)", True),
    ("a=[2,7]; 17 ≡ a[1] (mod 5)", True),
    ("17 ≡ Σ(i=1..2) i (mod 7)", True),
    ("17 ≡ 2 (mod (1 ≡ 1 (mod 3)) ? 5 : 7)", True),
    ("17 ≡ 2 (mod 5) ∧ 2<3", True),
    ("17 ≡ 2 (mod 5) ? 1=1 : 1=2", True),
    ("f(x)=x\n17 ≡ f(2+0) (mod f(5))", True),
    ("17 ≡ (2 + (1 ≡ 1 (mod 3) ? 0 : 1)) (mod 5)", True),
    (r"\congruent(17,2,5)", True),
    (r"\congruent(17,3,5)", False),
    (r"\all(\congruent(·,2,5), ⟨2,7,17⟩)", True),
    (r"\eval(\expr(x ≡ y (mod n)), x=17,y=2,n=5)", True),
    ("17 ≡\n2 (mod 5)", True),
])
def test_evaluation_contexts(source, expected):
    assert run_source(source)[-1] == f"= {str(expected).lower()}"


@pytest.mark.parametrize("value", ["1/2", "2e0", "i", r"\true", "[2]", "⟨2⟩", "{2}", r"\metre", '"2"'])
@pytest.mark.parametrize("position", range(3))
def test_rejects_nonintegers(value, position):
    operands = ["2", "2", "3"]
    operands[position] = value
    a, b, n = operands
    for source in (f"{a} ≡ {b} (mod {n})", f"\\congruent({a},{b},{n})"):
        with pytest.raises(EvalError, match="needs an exact integer"):
            run_source(source)


def test_zero_modulus_and_span():
    source = "2 ≡ 2 (mod 0)"
    with pytest.raises(EvalError, match="nonzero modulus") as failure:
        run_source(source)
    assert failure.value.span == Span(0, len(source.encode()))
    with pytest.raises(NumError, match="nonzero modulus"):
        ncongruent(2, 2, 0)


@pytest.mark.parametrize("source", [
    "1 ≡ 1 (mod 3) ≡ 1 (mod 3)", "1<2 ≡ 1 (mod 3)",
    "1 ≡ 1 (mod 3)=1", "1 ≡ 1 (mod 3)<2",
    "1 ≡ 1 (mod )", "1 ≡ 1 (mod 3,4)", "1 ≡ 1 (m o d 3)",
    "1 ≡ 1 (mod3)", r"(\equiv)",
])
def test_invalid_syntax(source):
    with pytest.raises(ParseError):
        parse_program(source)


@pytest.mark.parametrize("source", ["1 ≡ 1", "1 ≡ 1 (mod", "1 ≡ 1 (mod 3"])
def test_incomplete_input(source):
    with pytest.raises(IncompleteInput):
        parse_program(source)


@pytest.mark.parametrize("source", [r"\congruent(1,2)", r"\congruent(1,2,3,4)"])
def test_helper_arity(source):
    with pytest.raises(EvalError, match="three arguments"):
        run_source(source)


def test_quote_roundtrip_and_tex():
    node = parse_program(r"x+1 \equiv y (\mod n+2)")
    assert ExpressionValue(parse_program(show(node)), "") == ExpressionValue(node, "")
    assert node_tex(node) == r"x + 1 \equiv y \pmod{n + 2}"
    assert isinstance(tokenize("≡")[0], InfixOp)
    assert tokenize("π ≡ 3")[1].span == Span(3, 6)


def test_operands_evaluate_once_in_order():
    seen = []
    def record(value):
        seen.append(value)
        return value
    assert run_source("f(17) ≡ f(2) (mod f(5))", {"f": record}) == ["= true"]
    assert seen == [17, 2, 5]


def test_modulo_and_bare_letters_are_unchanged():
    assert run_source(r"17 \mod 5; 17 % 5") == ["= 2", "= 2"]
    assert run_source("m=2;o=3;d=4;mod")[-1] == "= 24"


def test_double_equal_alias_in_expression_contexts():
    assert run_source("p=17==2(mod 5); p")[-1] == "= true"
    assert run_source("f(x)=x==2(mod 5)\nf(17)")[-1] == "= true"
    assert run_source("17==2(mod 5) ∧ 2<3") == ["= true"]
    quote = run_source(r"\expr(17==2(mod 5))")[0][2:]
    assert "≡" in quote
    assert run_source(f"\\eval({quote})") == ["= true"]


@pytest.mark.parametrize("source", ["17==2", "17==2(mod 5)==2(mod 5)", "17==2(mod 5)=1", "(==)"])
def test_double_equal_alias_requires_suffix_and_does_not_chain(source):
    with pytest.raises(ParseError):
        parse_program(source)


def test_helper_and_operator_names_are_protected():
    for name in (r"\equiv", r"\congruent"):
        with pytest.raises(EvalError, match="protected"):
            run_source(f"\\let {name}=1")


def test_symbolic_rewriting_rejects_congruence():
    with pytest.raises(EvalError, match="cannot rewrite"):
        run_source(r"\simplify(\expr(x ≡ 2 (mod 5)))")
