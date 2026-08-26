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


# --- folds and limits (tickets: sigma/pi finite and infinite folds, \lim) ---


def test_finite_folds_accumulate_exactly():
    env: dict = {}
    checks = [
        ("\\sum(i=1..10) i^2", "= 385"),
        ("\\prod(j=1..5) j", "= 120"),
        ("\\sum(i=1,3..7) i", "= 16"),
        ("\\sum(i=1..4) i*0.5", "= 5.0"),  # float literal promotes the term tier
    ]
    for src, expected in checks:
        assert last(src, env) == expected, f"for {src}"


def test_empty_ranges_fold_to_identity():
    assert last("\\sum(i=5..4) i") == "= 0"
    assert last("\\prod(i=5..4) i") == "= 1"


def test_unicode_fold_spellings_evaluate_identically():
    env: dict = {}
    ascii_out = last("\\sum(i=1..10) i^2", env)
    unicode_out = last("Σ(i=1..10) i^2", env)
    assert ascii_out == unicode_out == "= 385"


def test_fold_loop_variable_scopes_like_a_parameter():
    env: dict = {"k": 99}
    assert last("\\sum(i=1..3) i*k", env) == "= 594"
    # The loop variable never leaks; the outer binding is untouched.
    assert set(env) == {"k"}
    with pytest.raises(EvalError, match="`i` is not bound"):
        run_source("i", {})


def test_infinite_geometric_sum_converges_to_one():
    out = last("\\sum(i=1..) 1/2^i")
    assert out.startswith("= ")
    assert abs(float(out[2:]) - 1.0) <= 1e-9


def test_infinite_zeta_demo_converges_within_display_precision():
    out = last("\\sum(i=1..) 1/i^2")
    assert abs(float(out[2:]) - 1.6449340668482264) <= 1e-5


def test_infinite_product_demo():
    # prod_{i>=1} (1 + 1/i^2) = sinh(pi)/pi ~ 3.67607791
    out = last("\\prod(i=1..) (1 + 1/i^2)")
    assert abs(float(out[2:]) - 3.676077910377989) <= 1e-4


def test_non_converging_infinite_fold_errors_at_the_cap(monkeypatch):
    import adhoc.runtime as runtime
    monkeypatch.setattr(runtime, "MAX_TERMS", 50)
    with pytest.raises(EvalError) as e:
        run_source("\\sum(i=1..) i")
    assert e.value.msg == "\\sum did not converge within 50 terms"
    assert e.value.span == Span(0, 13)


def test_infinite_fold_hitting_nan_errors_immediately():
    with pytest.raises(EvalError) as e:
        run_source("\\sum(i=1..) 0.0/0.0")
    assert e.value.msg == "\\sum diverged: partial value is not finite"


def test_limit_of_polynomial():
    out = last("\\lim(x=2) x^2 + 3x")
    assert abs(float(out[2:]) - 10.0) <= 1e-9


def test_limit_approximates_from_both_sides_symmetrically():
    out = last("\\lim(t=0.5) t*t - 2t")
    assert abs(float(out[2:]) + 0.75) <= 1e-9


def test_limit_never_evaluates_the_body_at_the_anchor():
    # Probes never bind the loop variable to the anchor itself: if one did,
    # `x/x` would raise division-by-zero at x=0 instead of returning 1.
    assert last("\\lim(x=0) x/x") == "= 1.0"


def test_jump_discontinuity_reports_a_missing_limit():
    with pytest.raises(EvalError) as e:
        run_source("\\lim(x=0) \\if(x < 0, -1, 1)")
    assert e.value.msg == "limit does not exist: left and right estimates disagree"
    assert e.value.span == Span(0, 27)


def test_pole_never_stabilizes_and_reports_non_convergence():
    with pytest.raises(EvalError) as e:
        run_source("\\lim(x=0) 1/x")
    assert "\\lim did not converge within" in e.value.msg


def test_fold_and_limit_lower_through_engine_calls():
    compiled = compile_source("\\sum(i=1..2) i; \\lim(x=1) x")
    assert "_e.fold(" in compiled.source
    assert "_e.limit(" in compiled.source
    assert compiled.definitions  # both bodies compiled alongside
