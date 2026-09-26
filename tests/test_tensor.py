import pytest

from adhoc.driver import run_source
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.syntax import BinOp, BinOperator, Index, TensorLit, Transpose


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, message, env=None):
    with pytest.raises(EvalError, match=message):
        run_source(src, {} if env is None else env)


def test_literals_display_round_trip():
    assert ev("[1, 2, 3]") == "= [1, 2, 3]"
    assert ev("[1, 2; 3, 4]") == "= [1, 2; 3, 4]"
    assert ev("[1; 2; 3]") == "= [1; 2; 3]"
    assert ev("[1, 2;]") == "= [1, 2;]"
    assert ev("[[1, 2; 3, 4], [5, 6; 7, 8]]") == "= [[1, 2; 3, 4], [5, 6; 7, 8]]"
    assert ev("[[1, 2], [3, 4]]") == "= [1, 2; 3, 4]"


def test_display_output_parses_back_to_an_equal_value():
    for src in ["[1, 2, 3]", "[1; 2]", "[1, 2;]", "[[1, 2; 3, 4], [5, 6; 7, 8]]"]:
        env = {}
        run_source(f"t = {src}", env)
        shown = ev("t", env)[2:]
        assert run_source(f"u = {shown}", env) == [f"u = {shown}"]
        assert ev("t = u", env) == "true"


def test_entries_keep_their_exact_tiers():
    assert ev("[1/2, 0.5, 2.]") == "= [1/2, 1/2, 2.0]"
    assert ev("[√2, 1/3] * 3") == "= [4.24264068711929..., 1]"
    assert ev("[i, 1] * i") == "= [-1, i]"


def test_entries_must_be_numbers():
    fails('["a", 1]', "strings are not numbers")
    fails(r"[\true]", "booleans are not numbers")
    fails("[1, [2, 3]]", "cannot mix numbers and tensors")
    fails("[[1, 2], [3]]", "different shapes")


def test_shape_errors_at_parse_time():
    with pytest.raises(ParseError, match="empty tensor"):
        parse_program("[]")
    with pytest.raises(ParseError, match="different lengths"):
        parse_program("[1, 2; 3]")
    fails("[[1, 2]; [3, 4]]", "`;` rows hold numbers")


def test_elementwise_algebra_and_broadcast():
    env = {}
    run_source("m = [1, 2; 3, 4]", env)
    assert ev("m + m", env) == "= [2, 4; 6, 8]"
    assert ev("m - 1", env) == "= [0, 1; 2, 3]"
    assert ev("1 - m", env) == "= [0, -1; -2, -3]"
    assert ev("2m", env) == "= [2, 4; 6, 8]"
    assert ev("m * m", env) == "= [1, 4; 9, 16]"
    assert ev("m / 2", env) == "= [1/2, 1; 3/2, 2]"
    assert ev("m / m", env) == "= [1, 1; 1, 1]"
    assert ev("m ^ 2", env) == "= [1, 4; 9, 16]"
    assert ev("2 ^ [1, 2, 3]", env) == "= [2, 4, 8]"
    assert ev("-m", env) == "= [-1, -2; -3, -4]"


def test_shape_mismatch_is_a_spanned_error():
    fails("[1, 2] + [1, 2, 3]", "shape mismatch 2 vs 3")
    fails("[1, 2; 3, 4] + [1, 2, 3, 4]", "shape mismatch 2x2 vs 4")
    fails("[1, 2] / [1, 0]", "division by zero")


def test_tensors_reject_non_numeric_operands_and_ordering():
    fails('[1, 2] + "a"', "strings are not numbers")
    fails("[1, 2] < [3, 4]", "operands must be numbers")


def test_contraction():
    assert ev("[1, 2] @ [3, 4]") == "= 11"
    assert ev(r"[1, 2] \contract [3, 4]") == "= 11"
    assert ev("[1, 2; 3, 4] @ [5, 6; 7, 8]") == "= [19, 22; 43, 50]"
    assert ev("[1, 2; 3, 4] @ [1, 1]") == "= [3, 7]"
    assert ev("[1, 1] @ [1, 2; 3, 4]") == "= [4, 6]"
    assert ev("[1; 2] @ [3, 4;]") == "= [3, 4; 6, 8]"
    assert ev("2 @ [1, 2]") == "= [2, 4]"
    assert ev("2 @ 3") == "= 6"
    fails("[1, 2, 3] @ [1, 2]", "cannot contract shape 3 with 2")
    fails("[1; 2] @ [3, 4]", "cannot contract shape 2x1 with 2")


def test_contraction_keeps_exactness():
    assert ev("[√2, 1] @ [√2, 1]") == "= 3"


def test_transpose():
    env = {}
    run_source("m = [1, 2, 3; 4, 5, 6]", env)
    assert ev("m'", env) == "= [1, 4; 2, 5; 3, 6]"
    assert ev("m''", env) == "= [1, 2, 3; 4, 5, 6]"
    assert ev(r"\transpose(m)", env) == "= [1, 4; 2, 5; 3, 6]"
    assert ev("[1, 2]'") == "= [1, 2]"
    assert ev("[1; 2]'") == "= [1, 2;]"
    assert ev("[[1, 2; 3, 4], [5, 6; 7, 8]]'").startswith("= [[1, 5;")
    fails("3'", "transpose needs a tensor")
    fails(r"\transpose(3)", "transpose needs a tensor")


def test_indexing_is_one_based():
    env = {}
    run_source("v = [10, 20, 30]", env)
    run_source("m = [1, 2; 3, 4]", env)
    assert ev("v[1]", env) == "= 10"
    assert ev("v[3]", env) == "= 30"
    assert ev("m[2, 1]", env) == "= 3"
    assert ev("m[1]", env) == "= [1, 2]"
    assert ev("m[2][2]", env) == "= 4"
    assert ev("m'[1]", env) == "= [1, 3]"
    assert ev("v[1 + 1]", env) == "= 20"
    run_source("t = [[1, 2; 3, 4], [5, 6; 7, 8]]", env)
    assert ev("t[2][1, 2]", env) == "= 6"
    assert ev("t[2, 1, 2]", env) == "= 6"


def test_index_errors():
    env = {}
    run_source("v = [10, 20, 30]", env)
    fails("v[4]", "index 4 out of range 1..3", env)
    fails("v[0]", "index 0 out of range 1..3", env)
    fails("v[1/2]", "index must be an exact integer", env)
    fails("v[1.]", "index must be an exact integer", env)
    fails("v[1, 2]", "2 indices for an order-1 tensor", env)


def test_index_error_span_covers_the_index_expression():
    with pytest.raises(EvalError) as e:
        run_source("v = [1, 2]\n1 + v[5]", {})
    assert (e.value.span.start, e.value.span.end) == (15, 19)


def test_non_indexable_head_multiplies():
    env = {}
    run_source("k = 3", env)
    assert ev("k[1, 2]", env) == "= [3, 6]"
    fails('s = "a"; s[1]', "is not indexable")
    fails(r"\sin[1]", "is not indexable")


def test_literal_heads_are_not_indexable_names():
    assert ev("2[1, 2]") == "= [2, 4]"
    fails("[1, 2][1]", "shape mismatch 2 vs 1")
    fails("([1, 2])[1]", "shape mismatch 2 vs 1")


def test_equality_check():
    env = {}
    run_source("m = [1, 2; 3, 4]", env)
    assert ev("m = [1, 2; 3, 4]", env) == "true"
    assert ev("m = [1, 2; 3, 5]", env) == "false"
    assert ev("m = [1, 2, 3, 4]", env) == "false"
    assert ev("m = 1", env) == "false"
    assert ev("t = [1/2]; t = [0.5]") == "true"


def test_len_and_shape():
    assert ev(r"\len([1, 2, 3])") == "= 3"
    assert ev(r"\len([1, 2; 3, 4; 5, 6])") == "= 3"
    assert ev(r"\shape([1, 2, 3; 4, 5, 6])") == "= [2, 3]"
    assert ev(r"\shape([1, 2])") == "= [2]"
    fails(r"\len(3)", "needs a collection")
    fails(r"\shape(3)", "needs a tensor")


def test_folds_bind_over_tensors():
    assert ev(r"\sum(x=[1, 2, 3]) x^2") == "= 14"
    assert ev(r"\prod(x=[1, 2, 3, 4]) x") == "= 24"
    assert ev(r"\sum(r=[1, 2; 3, 4]) r") == "= [4, 6]"
    assert ev(r"\sum(r=[1, 2; 3, 4]) r[2]") == "= 6"
    fails(r"\sum(x=3) x", "folds over a range or collection")


def test_infinite_fold_rejects_tensor_terms():
    fails(r"\sum(i=1..) [i]", "needs numeric terms")


def test_functions_and_lambdas_carry_tensors():
    env = {}
    run_source("f(v) = v @ v", env)
    assert ev("f([3, 4])", env) == "= 25"
    assert ev(r"(\fn(m) m')([1; 2])") == "= [1, 2;]"


def test_bindings_echo_and_immutability():
    env = {}
    assert run_source("t = [1, 2]", env) == ["t = [1, 2]"]
    assert run_source("t = [1, 2]", env) == ["true"]


def test_parse_shapes():
    match parse_program("[1, 2; 3, 4]"):
        case TensorLit(row_length=2, items=items):
            assert len(items) == 4
        case other:
            raise AssertionError(other)
    match parse_program("m[1, 2]'"):
        case Transpose(operand=Index(items=(_, _))):
            pass
        case other:
            raise AssertionError(other)
    match parse_program("a @ b * c"):
        case BinOp(op=BinOperator.MUL, lhs=BinOp(op=BinOperator.DOT)):
            pass
        case other:
            raise AssertionError(other)


def test_newlines_inside_brackets():
    assert ev("[1,\n 2,\n 3]") == "= [1, 2, 3]"
    assert ev("[1, 2;\n 3, 4\n]") == "= [1, 2; 3, 4]"
    env = {}
    run_source("v = [1, 2]", env)
    assert ev("v[\n2\n]", env) == "= 2"


def test_a_new_line_starting_with_a_bracket_is_a_new_statement():
    assert run_source("v = [1, 2]\n[3, 4]", {}) == ["v = [1, 2]", "= [3, 4]"]


def test_incomplete_brackets_offer_continuation():
    for src in ["[1, 2", "[1, 2,", "[1;", "[1, 2;\n3", "v = [1", "[[1, 2]"]:
        with pytest.raises(IncompleteInput):
            parse_program(src)
    with pytest.raises(IncompleteInput):
        parse_program("v[1")


def test_contract_is_infix_only():
    with pytest.raises(ParseError, match="infix operator"):
        parse_program(r"\contract")
    with pytest.raises(IncompleteInput):
        parse_program(r"2 \contract")
    fails(r"\contract = 3", "protected")


def test_quotes_holding_tensors_round_trip():
    env = {}
    run_source(r"q = \expr([1, 2; 3, 4] @ [x; 1])", env)
    shown = ev("q", env)[2:]
    assert shown == r"\expr(([1, 2; 3, 4] @ [x; 1]))"
    run_source(f"r = {shown}", env)
    assert ev("q = r", env) == "true"
    assert ev(r"\eval(q, x=5)", env) == "= [7; 19]"


def test_reduce_walks_inside_tensor_literals():
    out = ev(r"\reduce(\expr([(\fn(x) x + 1)(2), 5]))")
    assert out == r"= \expr([(2 + 1), 5])"


def test_rows_inside_bodies_lambdas_and_branches():
    env = {}
    run_source("f(x) = [x, 1; 2, x]", env)
    assert ev("f(3)", env) == "= [3, 1; 2, 3]"
    assert ev(r"(\fn(x) [x; 1])(2)") == "= [2; 1]"
    assert ev(r"\true ? [1; 2] : [3; 4]") == "= [1; 2]"
    assert ev(r"\eval(\expr((a = [1; 2]; a[2])))") == "= [2]"


def test_cdot_is_an_ordinary_name():
    assert ev(r"\cdot = 3") == r"\cdot = 3"


def test_middot_is_not_an_operator():
    for src in ["2 · 3", "(·)", "[1, 2] ⋅ [3, 4]"]:
        with pytest.raises(ParseError):
            parse_program(src)


def test_contraction_is_an_operator_value_and_section():
    assert ev(r"\fold((@), ⟨[1, 2], [3, 4]⟩)") == "= 11"
    assert ev(r"(\contract)([1, 2], [3, 4])") == "= 11"
    assert ev("(@ [1, 1])([1, 2; 3, 4])") == "= [3, 7]"
    assert ev("([1, 2] @)([3, 4])") == "= 11"
    assert ev(r"\expr((@)(·, [1, 2]))") == r"= \expr((@)(·, [1, 2]))"
