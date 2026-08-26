import pytest

from adhoc.compiler import compile_program
from adhoc.driver import compile_source, execute, run_source
from adhoc.parser import parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span


def last(src: str, env: dict | None = None) -> str:
    """Mirror interp.rs's run(...).format(): only the final statement's result."""
    return run_source(src, env)[-1]


# --- ports of interp.rs's test suite ---


def test_arithmetic():
    assert last("1 + 2 * 3") == "= 7"


def test_unbound_var_error_message():
    with pytest.raises(EvalError) as e:
        run_source("x")
    assert e.value.msg == "`x` is not bound"


def test_force_reassign_on_unbound_errors():
    with pytest.raises(EvalError) as e:
        run_source("y := 2")
    assert e.value.msg == "`y` does not exist!"


def test_assign_binds_then_checks():
    env: dict = {}
    assert last("x = 3", env) == "x = 3"
    assert last("x = 4", env) == "false"
    assert last("x = 3", env) == "true"


def test_force_reassign_rebinds():
    env: dict = {}
    last("x = 3", env)
    assert last("x := 4", env) == "x = 4"


def test_seq_threads_env_and_returns_last():
    env: dict = {}
    outs = run_source("a = 1; b = 2; a + b", env)
    assert outs == ["a = 1", "b = 2", "= 3"]
    assert last("a + b", env) == "= 3"


def test_backslash_ref_errors_unbound():
    with pytest.raises(EvalError) as e:
        run_source("\\pi")
    assert "not bound" in e.value.msg


def test_span_narrowing_unbound_var_in_addition():
    with pytest.raises(EvalError) as e:
        run_source("1 + x")
    assert e.value.span == Span(4, 5)


def test_span_narrowing_division_by_zero():
    with pytest.raises(EvalError) as e:
        run_source("2 + 1/0")
    assert e.value.span == Span(4, 7)


def test_span_narrowing_backslash_ref_is_sigil_inclusive():
    with pytest.raises(EvalError) as e:
        run_source("\\pi")
    assert e.value.span == Span(0, 3)


def test_span_narrowing_second_statement_only():
    with pytest.raises(EvalError) as e:
        run_source("a=1; y:=2")
    assert e.value.span == Span(5, 9)


def test_division_by_zero_keeps_repl_alive_via_typed_error():
    env: dict = {}
    with pytest.raises(EvalError) as e:
        run_source("1/0", env)
    assert e.value.msg == "division by zero"
    assert e.value.span is not None
    # The environment itself is unaffected — evaluation can continue.
    assert last("1 + 1", env) == "= 2"


# --- eval-side worked examples from parser.rs / tests/grammar.rs ---


def test_grammar_worked_examples_numeric():
    env: dict = {}
    checks = [
        ("1 + 2 * 3", "= 7"),
        ("(1 + 2) * 3", "= 9"),
        ("2^3^2", "= 512"),
        ("2^-1", "= 1/2"),
        ("-2^2", "= -4"),
    ]
    for src, expected in checks:
        assert last(src, env) == expected, f"for {src}"


def test_juxtaposition_precedence():
    env: dict = {}
    last("x = 2", env)
    assert last("1/2x", env) == "= 1/4"  # 1/(2x), not (1/2)x


def test_assignment_semantics_table():
    env: dict = {}
    assert last("x = 3", env) == "x = 3"  # unbound -> bind
    assert last("x = 4", env) == "false"  # bound, mismatched -> check
    assert last("x = 3", env) == "true"  # bound, matches -> check
    assert last("x := 4", env) == "x = 4"  # bound -> force rebind
    with pytest.raises(EvalError) as e:
        last("y := 5", env)
    assert e.value.msg == "`y` does not exist!"  # unbound -> error


def test_grammar_unicode_identifier():
    env: dict = {}
    assert last("π = 3", env) == "π = 3"
    assert env["π"] == 3


def test_exact_arithmetic_end_to_end():
    env: dict = {}
    assert last("1/3 + 1/3 + 1/3", env) == "= 1"
    assert last("(1+2)*3 - 10/4", env) == "= 13/2"


# --- compiled-unit properties ---


def test_one_generated_line_per_statement_and_line_spans():
    compiled = compile_source("a=1; a")
    lines = compiled.source.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("_e.assign('a', 1, ")
    assert lines[1].startswith("_e.out(_e.var('a', ")
    assert compiled.line_spans[1] == Span(0, 3)
    assert compiled.line_spans[2] == Span(5, 6)


def test_every_operation_routes_through_engine():
    compiled = compile_source("-2^2 * x")
    assert "_e." in compiled.source
    assert " ** " not in compiled.source and "*" not in compiled.source.replace("_e.", "")


def test_compile_from_ast_node_directly():
    node = parse_program("2 ^ 10")
    compiled = compile_program(node)
    assert execute(compiled, {}) == ["= 1024"]


def test_env_holds_only_user_variables():
    env: dict = {}
    run_source("q = 8", env)
    assert dict(env) == {"q": 8}


def test_env_persists_across_executions():
    env: dict = {}
    run_source("k = 5", env)
    assert last("k * k", env) == "= 25"


def test_float_literal_display_parity_through_driver():
    assert last("0.5 + 0.5") == "= 1.0"


def test_ranges_evaluate_display_and_can_be_bound():
    env: dict = {}
    assert last("r = 1,3..10", env) == "r = <range 1,3..10>"
    assert list(env["r"]) == [1, 3, 5, 7, 9]
    assert last("1..", env) == "= <range 1.. (lazy, infinite)>"


def test_range_runtime_errors_point_at_range():
    with pytest.raises(EvalError) as e:
        run_source("3,3..10")
    assert e.value.span == Span(0, 7)


def test_range_lowering_routes_through_engine():
    compiled = compile_source("1..3")
    assert "_e.range(" in compiled.source
    assert "range(" not in compiled.source.replace("_e.range(", "")
