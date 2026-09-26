import pytest

from adhoc import runtime
from adhoc.driver import run_source
from adhoc.expression import show
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError


def ev(src):
    return run_source(src, {})[-1]


def fails(src, message):
    with pytest.raises(EvalError, match=message):
        run_source(src, {})


def roundtrip(src):
    shown = show(parse_program(src))
    assert show(parse_program(shown)) == shown
    return shown


@pytest.mark.parametrize("src, out", [
    (r"\true ∧ \false", "= false"), (r"\true ∧ \true", "= true"),
    (r"\false ∨ \true", "= true"), (r"\false ∨ \false", "= false"),
    (r"¬\true", "= false"), (r"¬¬\true", "= true"), (r"\not \false", "= true"),
    (r"\true → \false", "= false"), (r"\false → \true", "= true"),
    (r"\false → \false", "= true"), (r"\true ↔ \true", "= true"), (r"\true ↔ \false", "= false"),
    (r"\true \and \false", "= false"), (r"\false \or \true", "= true"),
    (r"\false \implies \true", "= true"), (r"\true \iff \false", "= false"),
    (r"1 < 2 ∧ 2 < 3", "= true"), (r"1 ∈ {1, 2} ∨ 5 ∈ 1..3", "= true"),
])
def test_connectives(src, out):
    assert ev(src) == out


def test_short_circuit_skips_the_right_operand():
    assert ev("x = 0\nx ≠ 0 ∧ 1/x > 2") == "= false"
    assert ev(r"\true ∨ 1/0 > 1") == "= true"
    assert ev(r"\false → 1/0 > 1") == "= true"
    fails(r"\true ∧ 1/0 > 1", "division by zero")


def test_operands_must_be_booleans():
    fails(r"1 ∧ \true", "needs boolean operands, got 1")
    fails(r"\false ∨ 2", "needs boolean operands, got 2")
    fails(r"\false ↔ 0", "needs boolean operands")
    fails(r"¬1", "needs boolean operands")
    fails(r"\false ∨ 3", "needs boolean operands")


def test_operand_error_span_is_the_operand():
    with pytest.raises(EvalError) as e:
        run_source(r"\true ∧ 2", {})
    assert (e.value.span.start, e.value.span.end) == (10, 11)  # bytes: `∧` is three


def test_precedence_and_associativity():
    assert roundtrip(r"a ∨ b ∧ c") == "(a ∨ (b ∧ c))"
    assert roundtrip(r"a ∧ b ∨ c") == "((a ∧ b) ∨ c)"
    assert roundtrip(r"¬a ∧ b") == "((¬a) ∧ b)"
    assert roundtrip(r"¬a < b") == "(¬(a < b))"
    assert roundtrip(r"a → b → c") == "(a → (b → c))"
    assert roundtrip(r"a ∨ b → c ↔ d") == "(((a ∨ b) → c) ↔ d)"
    assert roundtrip(r"a ∨ b ∨ c") == "((a ∨ b) ∨ c)"
    assert roundtrip(r"x > 0 ∧ x < 5 → y ≠ 0") == "(((x > 0) ∧ (x < 5)) → (y ≠ 0))"
    assert ev(r"\false → \false → \false") == "= true"
    assert ev(r"\true ∨ \false ∧ \false") == "= true"


def test_iff_does_not_chain():
    with pytest.raises(ParseError, match="does not chain"):
        parse_program(r"a ↔ b ↔ c")
    assert ev(r"(\true ↔ \true) ↔ \true") == "= true"


def test_connectives_bind_looser_than_ranges_and_the_ternary_reads_them():
    assert ev(r"\true ∧ 1 < 2 ? 10 : 20") == "= 10"
    assert roundtrip(r"a ∧ b ? 1 : 2") == "((a ∧ b) ? 1 : 2)"


@pytest.mark.parametrize("src, out", [
    (r"∀(x=1..5) x > 0", "= true"), (r"∀(x=1..5) x > 1", "= false"),
    (r"∃(x=1..5) x > 4", "= true"), (r"∃(x={1, 2}) x > 4", "= false"),
    (r"∀(x=⟨⟩) x > 4", "= true"), (r"∃(x=⟨⟩) x > 4", "= false"),
    (r"∀(x=[1, 2, 3]) x > 0", "= true"),
    (r"\forall(x=1..3) x > 0", "= true"), (r"\exists(x=1..3) x > 2", "= true"),
    (r"∀(x=1..3) ∃(y=1..3) x + y > 3", "= true"),
    (r"∀(x=1..3) x > 0 ∧ x < 4", "= true"),
    (r"∃(n=1..) n^2 > 1000", "= true"), (r"∀(n=1..) n < 10", "= false"),
    (r"∃(n=1,3..) n > 100", "= true"),
])
def test_quantifiers(src, out):
    assert ev(src) == out


def test_quantifier_body_must_be_boolean():
    fails(r"∀(x=1..3) 5", "needs a boolean body, got 5")
    fails(r"∃(x=1..3) x", "needs a boolean body")


def test_quantifier_domain_must_be_a_collection():
    fails(r"∀(x=5) x > 0", "range or collection")


def test_quantifier_over_an_infinite_domain_is_undecided_at_the_budget(monkeypatch):
    monkeypatch.setattr(runtime, "MAX_TERMS", 50)
    fails(r"∀(n=1..) n > 0", "undecided within 50")
    fails(r"∃(n=1..) n < 0", "undecided within 50")


def test_quantifier_shadowing_and_protected_binder():
    assert ev("x = 7\n(∃(x=1..3) x > 2) ∧ x > 6") == "= true"
    fails(r"∀(e=1..3) e > 0", "protected")


def test_connectives_as_values():
    assert ev(r"(∧)(\true, \false)") == "= false"
    assert ev(r"(∨)(\false, \true)") == "= true"
    assert ev(r"(→)(\true, \false)") == "= false"
    assert ev(r"(↔)(\true, \true)") == "= true"
    assert ev(r"(¬)(\true)") == "= false"
    assert ev(r"(\and)(\true, \true)") == "= true"
    assert ev(r"\fold(∧, ⟨\true, \false⟩)") == "= false"
    assert ev(r"\fold(∨, ⟨\false, \true⟩)") == "= true"
    assert ev(r"\map((¬), ⟨\true, \false⟩)") == "= ⟨false, true⟩"


def test_connective_values_evaluate_both_operands():
    fails(r"(∧)(\false, 1/0 > 1)", "division by zero")
    fails(r"(∧)(1, \true)", "needs boolean operands")


def test_sections():
    assert ev(r"(\true ∧)(\false)") == "= false"
    assert ev(r"(∧ \true)(\true)") == "= true"
    assert ev(r"\filter((∨ \true), ⟨\true⟩)") == "= ⟨true⟩"
    assert ev(r"(¬ \true)") == "= false"
    assert ev(r"(∧ 1 < 2)(\true)") == "= true"


def test_display_and_quote_roundtrip():
    assert roundtrip(r"\true ∧ ¬\false") == r"(\true ∧ (¬\false))"
    assert roundtrip(r"∀(x=1..3) x > 0") == "(∀(x=(1..3)) (x > 0))"
    assert roundtrip(r"\exists(x={1, 2}) x ≠ 1") == r"(\exists(x={1, 2}) (x ≠ 1))"
    assert ev(r"\eval(\expr(\true ∧ p), p=\false)") == "= false"
    assert ev(r"\eval(\expr(∀(x=1..3) x > k), k=0)") == "= true"
    assert ev(r"\eval(\expr(¬p), p=\false)") == "= true"


def test_infix_names_are_not_values_or_atoms():
    with pytest.raises(ParseError, match="infix operator"):
        parse_program(r"\and")
    with pytest.raises(ParseError, match="prefix operator"):
        parse_program(r"1 + \not")
    fails(r"\and = 3", "protected")


def test_glyph_and_ascii_spellings_are_one_operator():
    assert run_source("g = (∧)\ng = (\\and)", {})[-1] == "true"
