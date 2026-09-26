import pytest

from adhoc.driver import run_source
from adhoc.lexer import SetOp, tokenize
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.syntax import BinOp, BinOperator, Compare, CompareOperator, SetLit


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, message, env=None):
    with pytest.raises(EvalError, match=message):
        run_source(src, {} if env is None else env)


def test_literals_dedupe_in_first_seen_order():
    assert ev("{1, 2, 3}") == "= {1, 2, 3}"
    assert ev("{3, 1, 3, 2}") == "= {3, 1, 2}"
    assert ev("{}") == "= {}"
    assert ev("{1/2, 0.5, 2/4}") == "= {1/2}"
    assert ev('{1, "a", [1, 2], ⟨1⟩, {2}}') == '= {1, "a", [1, 2], ⟨1⟩, {2}}'


def test_dedup_uses_value_equality():
    assert ev("{1, 1., 1.0}") == "= {1}"
    assert ev("{[1, 2], [1, 2], [2, 1]}") == "= {[1, 2], [2, 1]}"
    assert ev("{{1, 2}, {2, 1}}") == "= {{1, 2}}"
    assert ev("{⟨1, 2⟩, ⟨2, 1⟩}") == "= {⟨1, 2⟩, ⟨2, 1⟩}"
    assert ev("{√2, 2^(1/2)}") == "= {1.4142135623731...}"
    assert ev('{"a", "a"}') == '= {"a"}'


def test_nan_never_dedupes():
    assert ev(r"\len({\nan, \nan})") == "= 2"


def test_ascii_and_unicode_spellings_agree():
    for uni, ascii_ in [("∪", r"\cup"), ("∩", r"\cap"), ("∖", r"\setminus")]:
        assert ev(f"{{1, 2, 3}} {uni} {{2, 3, 4}}") == ev(f"{{1, 2, 3}} {ascii_} {{2, 3, 4}}")
    assert ev("2 ∈ {1, 2}") == ev(r"2 \in {1, 2}") == "= true"
    assert ev("{1} ⊆ {1, 2}") == ev(r"{1} \subseteq {1, 2}") == "= true"


def test_set_operations():
    assert ev("{1, 2, 3} ∪ {3, 4}") == "= {1, 2, 3, 4}"
    assert ev("{1, 2, 3} ∩ {2, 3, 4}") == "= {2, 3}"
    assert ev("{1, 2, 3} ∖ {2}") == "= {1, 3}"
    assert ev(r"{1, 2, 3} \setminus {4}") == "= {1, 2, 3}"
    assert ev("{1, 2} ∩ {3}") == "= {}"
    assert ev("{1, 2} ∪ {}") == "= {1, 2}"
    assert ev(r"{1, 2} \cup {2, 3} \cup {5}") == "= {1, 2, 3, 5}"
    assert ev("{1, 2, 3} ∖ {1} ∖ {2}") == "= {3}"


def test_membership_and_subset_are_booleans():
    assert ev("2 ∈ {1, 2, 3}") == "= true"
    assert ev(r"2 \in {1, 2, 3}") == "= true"
    assert ev("4 ∈ {1, 2, 3}") == "= false"
    assert ev("[1, 2] ∈ {[1, 2]}") == "= true"
    assert ev('"a" ∈ {"a"}') == "= true"
    assert ev("1 ∈ {1.}") == "= true"
    assert ev("{1, 2} ⊆ {1, 2, 3}") == "= true"
    assert ev(r"{1, 2, 3} \subseteq {1, 2}") == "= false"
    assert ev("{} ⊆ {1}") == "= true"
    assert ev("{1, 2} ⊆ {2, 1}") == "= true"


def test_membership_is_a_condition():
    assert ev("2 ∈ {1, 2} ? 10 : 20") == "= 10"
    assert ev("5 ∈ {1, 2} ? 10 : 20") == "= 20"


def test_precedence():
    assert ev("{1} ∪ {2} ∩ {2, 3}") == "= {1, 2}"
    assert ev("1 + 1 ∈ {2}") == "= true"
    assert ev("{1, 2} ∪ {3} ⊆ {1, 2, 3}") == "= true"
    assert ev("({1, 2} ∖ {1}) ∪ {9}") == "= {2, 9}"


def test_operator_type_errors():
    fails("{1} ∪ 2", "needs two sets")
    fails("1 ∩ {1}", "needs two sets")
    fails("⟨1⟩ ∖ {1}", "needs two sets")
    fails("{1} ⊆ [1]", "needs two sets")
    fails("1 ∈ ⟨1, 2⟩", "needs a set on the right")
    fails("1 ∈ 1", "needs a set on the right")


def test_no_arithmetic_indexing_or_ordering():
    env = {}
    run_source("s = {1, 2}", env)
    for src in ["s + s", "s + 1", "2s", "-s", "s * s", "s ^ 2", "s @ s"]:
        fails(src, "sets do not support arithmetic", env)
    fails("s < s", "sets do not support arithmetic", env)
    fails("s[1]", "sets are unordered and cannot be indexed", env)
    fails("[{1}]", "sets do not support arithmetic")


def test_equality_ignores_order():
    env = {}
    run_source("s = {1, 2, 3}", env)
    assert ev("s = {3, 2, 1}", env) == "true"
    assert ev("s = {1, 2}", env) == "false"
    assert ev("s = {1, 2, 4}", env) == "false"
    assert ev("s = ⟨1, 2, 3⟩", env) == "false"
    assert ev("t = {{1, 2}}; t = {{2, 1}}") == "true"


def test_binding_echo_and_immutability():
    env = {}
    assert run_source("s = {2, 1}", env) == ["s = {2, 1}"]
    assert run_source("s = {1, 2}", env) == ["true"]


def test_len_and_fold_iteration():
    assert ev(r"\len({1, 2, 2, 3})") == "= 3"
    assert ev(r"\sum(x={1, 2, 3, 3}) x^2") == "= 14"
    assert ev(r"\prod(x={2, 3}) x") == "= 6"
    assert ev(r"\sum(x={1, 2} ∪ {3}) x") == "= 6"


def test_sets_pass_through_functions_and_lambdas():
    env = {}
    run_source(r"f(a, b) = a ∩ b", env)
    assert ev("f({1, 2}, {2, 3})", env) == "= {2}"
    assert ev(r"(\fn(s) 1 ∈ s)({1})") == "= true"


def test_infix_names_are_not_values():
    for name in ["cup", "cap", "setminus", "in", "subseteq"]:
        with pytest.raises(ParseError, match="infix operator"):
            parse_program(f"\\{name}")
        fails(f"\\{name} = 3", "protected")
    with pytest.raises(IncompleteInput):
        parse_program(r"{1} \cup")


def test_parse_shapes():
    match parse_program("{1, 2}"):
        case SetLit(items=(_, _)):
            pass
        case other:
            raise AssertionError(other)
    match parse_program(r"a \cup b ∩ c"):
        case BinOp(op=BinOperator.UNION, rhs=BinOp(op=BinOperator.INTERSECT)):
            pass
        case other:
            raise AssertionError(other)
    match parse_program(r"x \in s"):
        case Compare(op=CompareOperator.IN):
            pass
        case other:
            raise AssertionError(other)
    match parse_program("a ⊆ b"):
        case Compare(op=CompareOperator.SUBSETEQ):
            pass
        case other:
            raise AssertionError(other)


def test_lexing():
    tokens = [t for t in tokenize("∪∩∖∈⊆") if isinstance(t, SetOp)]
    assert [t.name for t in tokens] == ["cup", "cap", "setminus", "in", "subseteq"]


def test_newlines_and_continuation():
    assert ev("{1,\n 2\n}") == "= {1, 2}"
    for src in ["{1, 2", "{", "{1,"]:
        with pytest.raises(IncompleteInput):
            parse_program(src)


def test_quotes_round_trip():
    env = {}
    run_source(r"q = \expr({x, 1} ∪ {2} ∖ {3})", env)
    shown = ev("q", env)[2:]
    assert shown == r"\expr((({x, 1} ∪ {2}) ∖ {3}))"
    run_source(f"r = {shown}", env)
    assert ev("q = r", env) == "true"
    assert ev(r"\eval(q, x=7)", env) == "= {7, 1, 2}"
    assert ev(r"\reduce(\expr({(\fn(x) x)(1)}))") == r"= \expr({1})"
    assert ev(r"\eval(\expr(x ∈ {1, 2}), x=2)") == "= true"


def test_newlines_inside_braces_do_not_make_a_statement_quote():
    assert ev("\\expr(({1,\n2}))") == ev(r"\expr(({1, 2}))") == r"= \expr({1, 2})"


def test_infix_names_cannot_be_aliased():
    with pytest.raises(ParseError, match="cannot be aliased"):
        parse_program(r"\alias \cup, u")
