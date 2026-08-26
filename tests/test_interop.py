"""Stage-5 interop surface: the `\\py` escape hatch, postfix application, literal
strings, and the Python↔ad conversion matrix.

Strings are literals, not values (docs/grammar.md): they pass through call boundaries,
print display-only when a call returns one, and are rejected everywhere a value would be
expected. The rewrite plan's exit criterion lives here as test_exit_criterion.
"""

import pytest

from adhoc.driver import compile_source, run_source
from adhoc.runtime import EvalError
from adhoc.span import Span


def last(src: str, env: dict | None = None) -> str:
    return run_source(src, env)[-1]


# --- exit criterion + application ---


def test_exit_criterion():
    assert last('\\py("math.sqrt")(2)') == "= 1.4142135623730951"


def test_bind_callable_then_apply():
    env: dict = {}
    assert last('s = \\py("math.sqrt")', env) == "s = <py math.sqrt>"
    assert last("s", env) == "= <py math.sqrt>"
    assert last("s(4)", env) == "= 2.0"


def test_zero_arg_call():
    # int() takes no arguments and returns 0.
    assert last('\\py("int")()') == "= 0"


def test_call_result_composes_into_arithmetic():
    assert last('\\py("math.sqrt")(16) / 2') == "= 2.0"


def test_number_literal_parens_stay_multiplication_end_to_end():
    env: dict = {}
    last("x = 3", env)
    assert last("2(x)", env) == "= 6"  # 2 * x, never an application of a literal


# --- conversion matrix: Python -> ad ---


def test_bool_becomes_int():
    assert last('\\py("bool")(1)') == "= 1"
    assert last('\\py("bool")(0)') == "= 0"


def test_fraction_passthrough_stays_exact():
    assert last('\\py("fractions.Fraction")(1, 3)') == "= 1/3"


def test_decimal_converts_exactly():
    assert last('\\py("decimal.Decimal")("0.1")') == "= 1/10"


def test_str_return_is_display_only():
    out = last('\\py("str")("hello")')
    assert out == '= "hello"'


def test_string_argument_passes_to_python_as_native_str():
    assert last('\\py("len")("hello")') == "= 5"


def test_none_return_rejects():
    with pytest.raises(EvalError) as e:
        run_source('\\py("random.seed")()')
    assert e.value.msg == "the call returned nothing"


def test_complex_return_rejects():
    with pytest.raises(EvalError) as e:
        run_source('\\py("complex")(1, 1)')
    assert e.value.msg == "complex results are not supported"


def test_unsupported_type_return_rejects():
    with pytest.raises(EvalError) as e:
        run_source('\\py("dict")()')
    assert "cannot convert a returned dict" in e.value.msg


def test_callee_exception_maps_to_call_span():
    with pytest.raises(EvalError) as e:
        run_source('\\py("math.sqrt")(-1)')
    assert "ValueError" in e.value.msg
    assert e.value.span == Span(0, 20)


# --- \py resolution failures ---


def test_unresolvable_path_errors_with_span():
    with pytest.raises(EvalError) as e:
        run_source('\\py("no.such.module.attr")')
    assert "cannot resolve" in e.value.msg
    assert e.value.span == Span(0, 26)


def test_non_callable_path_errors():
    with pytest.raises(EvalError) as e:
        run_source('\\py("math.pi")')
    assert "`math.pi` is not callable" in e.value.msg


def test_non_string_argument_errors():
    with pytest.raises(EvalError) as e:
        run_source("\\py(2)")
    assert "takes one string literal" in e.value.msg


def test_bare_py_hints_at_application():
    with pytest.raises(EvalError) as e:
        run_source("\\py")
    assert "must be applied" in e.value.msg


# --- strings are literals, not values ---


def test_bare_string_statement_produces_no_output():
    assert run_source('"hidden note"') == []
    assert run_source('"a"; 1 + 1') == ["= 2"]


def test_string_cannot_be_assigned():
    with pytest.raises(EvalError) as e:
        run_source('x = \\py("os.getcwd")()')
    assert "strings cannot be assigned" in e.value.msg


def test_string_cannot_be_force_reassigned():
    env: dict = {}
    run_source("x = 1", env)
    with pytest.raises(EvalError) as e:
        run_source('x := \\py("os.getcwd")()', env)
    assert "strings cannot be assigned" in e.value.msg


def test_transient_string_in_arithmetic_is_typed_error():
    with pytest.raises(EvalError) as e:
        run_source('\\py("chr")(65) + 1')
    assert e.value.msg == "strings are not numbers"


def test_applying_a_string_result_falls_into_typed_product_error():
    # `"q"` is not callable, one argument -> fallback multiplication -> typed seam error.
    with pytest.raises(EvalError) as e:
        run_source('\\py("str")("q")(1)')
    assert e.value.msg == "strings are not numbers"


def test_unterminated_string_is_incomplete_not_fatal():
    from adhoc.parser import IncompleteInput, parse_program

    with pytest.raises(IncompleteInput):
        parse_program('"abc')


# --- applying non-callables ---


def test_dynamic_fallback_multiplies_for_non_callable_heads():
    # The paper reading survives: a non-callable head with exactly one argument is
    # juxtaposed multiplication, decided at evaluation by what the head holds.
    env: dict = {}
    run_source("x = 3", env)
    assert last("x(2)", env) == "= 6"
    assert last("x(1 + 2)", env) == "= 9"
    assert last("2(x)", env) == "= 6"  # number-headed: never even parsed as a call


def test_unbound_call_head_still_reports_binding_error():
    with pytest.raises(EvalError) as e:
        run_source("z(2)")
    assert e.value.msg == "`z` is not bound"


def test_noncallable_head_with_wrong_arity_still_errors():
    env: dict = {}
    run_source("x = 3", env)
    for src in ["x()", "x(2, 3)"]:
        with pytest.raises(EvalError) as e:
            run_source(src, env)
        assert e.value.msg == "3 is not a function"


# --- reserved definitions ---


def test_func_def_evaluates_to_reserved_error():
    with pytest.raises(EvalError) as e:
        run_source("f(x) = x + 1")
    assert e.value.msg == "function definitions are not implemented yet (reserved for phase 1)"


# --- compiled-unit invariants survive the new statements ---


def test_string_statement_lowers_to_pass_keeping_line_table_aligned():
    compiled = compile_source('"c"; 1')
    lines = compiled.source.splitlines()
    assert lines[0] == "pass"
    assert len(lines) == 2
    assert compiled.line_spans[1] == Span(0, 3)
    assert compiled.line_spans[2] == Span(5, 6)
    assert run_source('"c"; 1') == ["= 1"]
