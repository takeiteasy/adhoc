import pytest

from adhoc.compiler import compile_program
from adhoc.driver import compile_source, execute, run_source
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span


def last(src: str, env: dict | None = None,
         aliases: dict | None = None) -> str:
    """Mirror interp.rs's run(...).format(): only the final statement's result."""
    return run_source(src, env, aliases=aliases)[-1]


# --- ports of interp.rs's test suite ---


def test_arithmetic():
    assert last("1 + 2 * 3") == "= 7"


def test_unbound_var_error_message():
    with pytest.raises(EvalError) as e:
        run_source("x")
    assert e.value.msg == "`x` is not bound"


def test_force_reassign_spelling_is_gone():
    # `:=` was removed: a stray `:` dies at the lexer/parser boundary, not with the
    # old "`y` does not exist!" evaluation error.
    with pytest.raises(ParseError, match="unexpected token `:`"):
        run_source("y := 2")


def test_globals_are_single_assignment():
    # With the force spelling gone, a bound global can only be compared against —
    # a paper page doesn't reassign either. Iteration means fresh names.
    env: dict = {}
    assert last("x = 3", env) == "x = 3"
    assert last("x = 4", env) == "false"
    assert last("x = 3", env) == "true"
    # Statement groups flatten into plain statements — same declare-once-then-check.
    assert run_source("(x = 4; x)", env) == ["false", "= 3"]


def test_assign_binds_then_checks():
    env: dict = {}
    assert last("x = 3", env) == "x = 3"
    assert last("x = 4", env) == "false"
    assert last("x = 3", env) == "true"


def test_seq_threads_env_and_returns_last():
    env: dict = {}
    outs = run_source("a = 1; b = 2; a + b", env)
    assert outs == ["a = 1", "b = 2", "= 3"]
    assert last("a + b", env) == "= 3"


def test_backslash_ref_errors_unbound():
    with pytest.raises(EvalError) as e:
        run_source("\\bogus")
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
        run_source("\\bogus")
    assert e.value.span == Span(0, 6)


def test_span_narrowing_second_statement_only():
    with pytest.raises(EvalError) as e:
        run_source("a=1; y")
    assert e.value.span == Span(5, 6)


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
    with pytest.raises(ParseError):
        run_source("y := 5", env)  # the force spelling does not exist


def test_grammar_unicode_identifier():
    env: dict = {}
    assert last("α = 3", env) == "α = 3"
    assert env["α"] == 3


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


# --- prelude scope, protected names, the binding rule, booleans ---


def test_prelude_constants_are_bound():
    assert last("π") == "= 3.141592653589793"
    assert last("\\pi") == "= 3.141592653589793"
    assert last("e") == "= 2.718281828459045"


def test_unicode_and_ascii_prelude_names_share_one_value():
    # The sharing is a parse-time alias (π normalizes to \pi), not two prelude
    # keys — both spellings read one value, and neither can be rebound.
    assert last("π") == last("\\pi") == "= 3.141592653589793"
    with pytest.raises(EvalError, match="is protected"):
        run_source("π = 3")


def test_prelude_py_function_aliases():
    assert last("\\sqrt(2)") == "= 1.4142135623730951"
    assert last("\\sin(0)") == "= 0.0"
    assert last("\\cos(0)") == "= 1.0"
    assert last("\\ln(1)") == "= 0.0"
    # The aliases are the plain math.* callables themselves.
    assert last("\\sqrt") == "= <py math.sqrt>"
    # They compose with the rest of the language.
    out = last("\\lim(x=0) \\sin(x)/x")
    assert abs(float(out[2:]) - 1.0) <= 1e-9


def test_prelude_inf_and_nan_constants():
    # The non-finite floats, nameable at last: ordinary protected prelude values
    # with pinned IEEE semantics (docs/numerics.md).
    assert last("\\inf") == "= Inf"
    assert last("-\\inf") == "= -Inf"
    assert last("\\nan") == "= NaN"
    assert last("\\inf + 1") == "= Inf"
    assert last("1/\\inf") == "= 0.0"
    assert last("x = \\inf; x = \\inf") == "true"   # Inf equals itself (IEEE)
    assert last("x = \\nan; x = \\nan") == "false"  # NaN never equals itself (IEEE)
    with pytest.raises(EvalError, match="condition must be boolean"):
        run_source("\\if(\\nan, 1, 2)")             # no numeric truthiness
    for src in ["\\inf = 1", "\\nan = 1"]:
        with pytest.raises(EvalError, match="is protected"):
            run_source(src)


def test_prelude_names_cannot_be_rebound():
    for src in ["π = 3", "\\pi = 3", "e = 5", "\\true = \\false"]:
        with pytest.raises(EvalError) as e:
            run_source(src)
        assert "is protected" in e.value.msg, f"for {src}"


def test_prelude_names_cannot_be_shadowed_by_parameters():
    for src in ["f(π) = 1", "f(e) = 1", "\\fact(π) = 1"]:
        with pytest.raises(EvalError) as e:
            run_source(src)
        assert "is protected" in e.value.msg, f"for {src}"


def test_prelude_names_cannot_be_shadowed_by_locals():
    env: dict = {}
    run_source("f(x) = π = 1; x", env)  # definition succeeds; the body is never run
    with pytest.raises(EvalError) as e:
        run_source("f(5)", env)
    # The alias mechanism normalizes π to the canonical name; diagnostics echo it.
    assert e.value.msg == "`pi` is protected"


def test_prelude_names_cannot_be_binder_variables():
    with pytest.raises(EvalError, match="`pi` is protected"):
        run_source("\\sum(π=1..2) π")
    with pytest.raises(EvalError, match="`pi` is protected"):
        run_source("\\lim(π=0) π")


def test_prelude_names_are_not_in_the_user_env():
    env: dict = {}
    run_source("q = 1", env)
    assert dict(env) == {"q": 1}


def test_boolean_constants():
    assert last("\\true") == "= true"
    assert last("\\false") == "= false"
    env: dict = {}
    assert last("t = \\true", env) == "t = true"
    assert last("t", env) == "= true"
    assert last("x = 1 < 2", env) == "x = true"


def test_boolean_constants_drive_conditionals():
    assert last("\\if(\\true, 1, 2)") == "= 1"
    assert last("\\if(\\false, 1, 2)") == "= 2"
    assert last("\\if(1 < 2, 10, 20)") == "= 10"
    assert run_source("\\if(\\false, 1)") == []  # statement no-op


def test_unary_minus_on_a_boolean_reports_a_spanned_error():
    # Booleans are bindable now, so `-t` on a bound \true reaches nneg — the failure
    # must come back as the caret-pointed typed error, not an internal error.
    with pytest.raises(EvalError) as e:
        run_source("t = \\true; -t")
    assert e.value.msg == "booleans are not numbers"
    assert e.value.span == Span(11, 13)  # the `-t` node


def test_lim_body_producing_a_boolean_reports_a_spanned_error():
    # Same wrapping contract for the limit probes' float widening.
    with pytest.raises(EvalError) as e:
        run_source("\\lim(x=0) \\true")
    assert e.value.msg == "booleans are not numbers"
    assert e.value.span == Span(0, 15)  # the whole \lim node


def test_declaration_operators_are_gone():
    # ≡, the == alias, and \const no longer exist: everything is immutable by the
    # binding rule, so there is nothing left to declare.
    with pytest.raises(ParseError, match="unexpected character `≡`"):
        run_source("c ≡ 5")
    with pytest.raises(ParseError):
        run_source("k == 3")
    with pytest.raises(EvalError, match="not bound"):
        run_source("\\const + 1")


def test_binding_rule_is_the_tower_not_the_type():
    # The comparison is value-based: across the exact/float tiers, equal values
    # compare true; mixed kinds simply are not equal.
    env: dict = {}
    assert last("x = 1; x = 1.0", env) == "true"
    assert last("y = 0.5; y = 1/2", env) == "true"
    assert last('s = "a"; s = 1', env) == "false"
    assert last("t = \\true; t = 1", env) == "true"  # bools compare as Python ints


def test_group_cannot_overwrite_a_global():
    # A top-level group flattens into plain statements, so its `=` obeys the same
    # rule: bound name → compare. There is no force-rebind path left anywhere.
    env: dict = {}
    last("x = 5", env)
    assert run_source("(x = 6)", env) == ["false"]
    assert last("x", env) == "= 5"


def test_body_writes_shadow_and_stay_local():
    # Inside a body the same rule runs against the local frame: fresh `=` binds a
    # local (shadowing a global), a repeat compares locally, globals are never hit.
    env: dict = {}
    last("y = 10", env)
    assert run_source("f() = (y = 4; y = 4; y)", env) == ["f = <fn f()>"]
    assert last("f()", env) == "= 4"
    assert last("y", env) == "= 10"


def test_function_redefinition_errors():
    # Definitions are declarations: identity comparison would make a check
    # meaningless, so a bound name is an error, not a comparison.
    env: dict = {}
    run_source("\\double(x) = 2x", env)
    assert last("\\double(21)", env) == "= 42"
    with pytest.raises(EvalError, match="is already bound"):
        run_source("\\double(x) = 3x", env)
    with pytest.raises(EvalError, match="is protected"):
        run_source("\\sin(x) = x", env)


def test_multi_char_function_definitions_echo_single_sigil():
    # assign's _name_text already sigilates; the echoed line shows one backslash.
    assert run_source("\\fact(n) = n") == ["\\fact = <fn \\fact(n)>"]


# --- ternary `cond ? a : b` ---


def test_ternary_selects_lazily():
    # The unselected branch never evaluates — 1/0 would die if it did.
    assert last("1 > 0 ? 1 : 1/0") == "= 1"
    assert last("1 > 2 ? 1/0 : 5") == "= 5"


def test_ternary_condition_must_be_boolean():
    with pytest.raises(EvalError, match="condition must be boolean"):
        run_source("1 ? 2 : 3")


def test_ternary_inside_fold_body():
    assert last("\\sum(i=1..10) i > 5 ? i : 0") == "= 40"


# --- name aliases ---


def test_user_alias_drives_folds_and_reads():
    assert last("\\alias \\sum, σ; σ(i=1..4) i") == "= 10"


def test_alias_takes_effect_from_the_next_statement():
    # Declare-before-use: a use parsed before the declaration reads the raw
    # spelling, which no declaration retroactively renames.
    with pytest.raises(EvalError, match=r"`\\sum` is not bound"):
        run_source("σ = 5; \\alias \\sum, σ; σ")


def test_alias_bare_heads_report_usage():
    # `\alias`/`\dual` commit only before a name; anywhere else the head stays an
    # ordinary unbound name and evaluation reports the usage message.
    for head, usage in [("alias", "declares short spellings"),
                        ("dual", "two spellings")]:
        with pytest.raises(EvalError, match=usage):
            run_source(f"\\{head} + 1")


def test_dual_binds_one_name_under_two_spellings():
    out = run_source("\\dual \\alpha, α = 3.14; α + \\alpha")
    assert out[0] == "\\alpha = 3.14"
    assert out[-1] == "= 6.28"


def test_dual_check_goes_through_either_spelling():
    from adhoc.parser import ALIAS_SEED

    env: dict = {}
    aliases = dict(ALIAS_SEED)
    run_source("\\dual \\alpha, α = 3.14", env, aliases=aliases)
    # The alias map is session state like env: thread it and both spellings
    # compare against the one binding.
    assert last("α = 3.14", env, aliases=aliases) == "true"
    assert last("\\alpha = 2", env, aliases=aliases) == "false"


def test_dual_function_recurses_through_the_short_spelling():
    from adhoc.parser import ALIAS_SEED

    env: dict = {}
    aliases = dict(ALIAS_SEED)
    run_source("\\dual \\fact, φ(n) = n <= 1 ? 1 : n * φ(n - 1)", env, aliases=aliases)
    assert last("φ(5)", env, aliases=aliases) == "= 120"
