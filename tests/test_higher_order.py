import pytest

from adhoc.driver import run_source
from adhoc.lexer import Placeholder, SetOp, tokenize
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import BinOp, BinOperator, Call, Hole

DEFS = "s(x) = x^2\nt(x) = x + 1\nf(a, b) = a - b\n"


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, message, env=None):
    with pytest.raises(EvalError, match=message) as e:
        run_source(src, {} if env is None else env)
    return e.value


def _only(program):
    statements = getattr(program, "statements", (program,))
    assert len(statements) == 1
    return statements[0]


def parse_fails(src, message):
    with pytest.raises(ParseError, match=message):
        parse_program(src)


# --- composition ---


def test_circ_lexes_as_set_style_operator():
    assert isinstance(tokenize("∘")[0], SetOp)
    assert tokenize("∘")[0].name == "circ"


def test_compose_parses_at_multiplicative_level():
    node = _only(parse_program("f ∘ g + h"))
    assert node.op is BinOperator.ADD
    assert isinstance(node.lhs, BinOp) and node.lhs.op is BinOperator.COMPOSE


def test_ascii_spelling_matches_unicode():
    assert ev(DEFS + r"(s \circ t)(2)") == ev(DEFS + "(s ∘ t)(2)") == "= 9"


def test_compose_applies_right_to_left_and_chains():
    assert ev(DEFS + "(s ∘ t)(2)") == "= 9"
    assert ev(DEFS + "(t ∘ s)(2)") == "= 5"
    assert ev(DEFS + "(t ∘ t ∘ t)(0)") == "= 3"


def test_compose_is_a_first_class_value():
    env = {}
    run_source(DEFS + "g = s ∘ t", env)
    assert ev("g(1)", env) == "= 4"
    assert ev("g", env) == "= <fn s ∘ t>"
    assert ev(r"\map(g, ⟨1, 2⟩)", env) == "= ⟨4, 9⟩"


def test_compose_with_python_and_lambda():
    assert ev(DEFS + r'(\py("math.sqrt") ∘ s)(3)') == "= 3.0"
    assert ev(DEFS + r"(s ∘ (\fn(x) x * 2))(3)") == "= 36"


def test_compose_needs_functions():
    fails("1 ∘ 2", "`∘` needs two functions")
    fails(DEFS + "s ∘ 3", "`∘` needs two functions")


def test_compose_arity_errors_point_at_the_call():
    err = fails(DEFS + "(s ∘ t)(1, 2)", "t takes 1 arguments, got 2")
    assert err.span is not None


def test_circ_is_reserved_like_other_infix_names():
    parse_fails(r"\circ", "infix operator")
    parse_fails(r"\alias \circ, c", "cannot be aliased")
    fails(r"\circ = 3", "protected")


# --- partial application ---


def test_placeholder_lexes():
    for ch in "_·⋅":
        assert isinstance(tokenize(ch)[0], Placeholder)


def test_hole_parses_as_call_argument():
    call = _only(parse_program("f(1, _)"))
    assert isinstance(call, Call) and isinstance(call.args[1], Hole)


def test_partial_fixes_first_or_second_argument():
    assert ev(DEFS + "f(10, _)(3)") == "= 7"
    assert ev(DEFS + "f(10, ·)(3)") == "= 7"
    assert ev(DEFS + "f(10, ⋅)(3)") == "= 7"
    assert ev(DEFS + "f(_, 3)(10)") == "= 7"


def test_partial_with_several_holes_fills_in_order():
    assert ev(DEFS + "f(_, _)(10, 3)") == "= 7"


def test_partial_is_a_value_and_displays():
    env = {}
    run_source(DEFS + "g = f(10, _)", env)
    assert ev("g", env) == "= <fn f(10, ·)>"
    assert ev("g(4)", env) == "= 6"
    assert ev(r"\map(g, [1, 2])", env) == "= [9, 8]"


def test_partial_over_python_callables_and_kwargs():
    assert ev(r'\py("pow")(_, 2)(5)') == "= 25"
    assert ev(r'\py("int")(_, \base=16)("ff")') == "= 255"


def test_partial_composes():
    assert ev(DEFS + "(f(_, 1) ∘ f(_, 1))(5)") == "= 3"


def test_partial_errors():
    fails(DEFS + "f(_)", "f takes 2 arguments, got 1")
    fails(DEFS + "f(1, _)(1, 2)", "takes 1 arguments, got 2")
    fails("x = 3\nx(_)", "3 is not a function")
    parse_fails("f(· + 1)", "`·` is a placeholder for a whole call argument")
    parse_fails("f(_ + 1)", "`_` is a placeholder for a whole call argument")
    parse_fails("f(x=_)", "unexpected token")
    parse_fails("_", "unexpected token")
    parse_fails(r"\py(_)", "cannot take a `·` placeholder")
    parse_fails(r"\arr(_)", "cannot take a `·` placeholder")


def test_hole_after_comma_is_not_a_stepped_range():
    assert ev(DEFS + "f(10, _)(2)") == "= 8"


# --- commas in lists separate items (no stepped range) ---


def test_range_after_a_comma_in_a_call_is_its_own_argument():
    assert ev(DEFS + r"\map(s, 1..3)") == "= ⟨1, 4, 9⟩"
    assert ev(r"\map(\fn(x) x^2, 1..3)") == "= ⟨1, 4, 9⟩"
    assert ev(DEFS + r"\fold(f, 1..3, 10)") == "= 4"


def test_stepped_range_in_a_list_needs_parentheses():
    assert ev(DEFS + r"\map(s, (1,3..7))") == "= ⟨1, 9, 25, 49⟩"


def test_comma_separates_items_in_literals_and_indexes():
    assert ev(r"\len(⟨1, 3..9⟩)") == "= 2"
    assert ev(r"\len({1, 3..9})") == "= 2"
    assert ev(r"\len(⟨1, (3,5..9)⟩)") == "= 2"
    assert ev("m = [1, 2; 3, 4]\nm[1, 2]") == "= 2"


def test_stepped_range_outside_lists_is_unchanged():
    assert ev("r = 1,3..10") == "r = <range 1,3..10>"
    assert ev(r"\sum(k=1,3..7) k") == "= 16"


def test_fold_binder_inside_a_list_keeps_its_stepped_range():
    assert ev(r"\map(\fn(x) x, ⟨\sum(k=1,3..7) k⟩)") == "= ⟨16⟩"


def test_quote_round_trips_compose_and_hole():
    env = {}
    assert ev(r"q = \expr(f ∘ g)", env) == r"q = \expr((f ∘ g))"
    assert ev(r"r = \expr(f(1, ·))", env) == r"r = \expr(f(1, ·))"


# --- \map ---


def test_map_keeps_the_collection_kind():
    assert ev(DEFS + r"\map(s, [1, 2, 3])") == "= [1, 4, 9]"
    assert ev(DEFS + r"\map(s, ⟨1, 2⟩)") == "= ⟨1, 4⟩"
    assert ev(DEFS + r"\map(s, {1, -1, 2})") == "= {1, 4}"
    assert ev(DEFS + r"\map(s, (1..3))") == "= ⟨1, 4, 9⟩"


def test_map_over_matrix_rows_restacks():
    assert ev(r"\map(\fn(r) r * 2, [1, 2; 3, 4])") == "= [2, 4; 6, 8]"


def test_map_result_must_restack_into_a_tensor():
    fails(r"\map(\fn(x) x > 1, [1, 2])", "booleans are not numbers")
    assert ev(r"\map(\fn(x) [x, x], [1, 2])") == "= [1, 1; 2, 2]"


def test_map_errors():
    fails(r"\map(1, ⟨1⟩)", "1 is not a function")
    fails(r"\map(\fn(x) x, 3)", r"\\map needs a range or collection, got 3")
    fails(r"\map(\fn(a, b) a, ⟨1⟩)", "takes 2 arguments, got 1")
    fails(r"\map(1)", r"\\map takes a function and a collection")
    fails(r"\map = 3", "protected")


def test_map_error_inside_the_function_keeps_its_own_span():
    err = fails(r"\map(\fn(x) 1/x, ⟨1, 0⟩)", "division by zero")
    assert err.span == Span(12, 15)


# --- \filter ---


def test_filter_keeps_the_collection_kind():
    assert ev(r"\filter(\fn(x) x > 1, [1, 2, 3])") == "= [2, 3]"
    assert ev(r"\filter(\fn(x) x > 1, ⟨1, 2, 3⟩)") == "= ⟨2, 3⟩"
    assert ev(r"\filter(\fn(x) x > 1, {1, 2, 3})") == "= {2, 3}"
    assert ev(r"\filter(\fn(x) x > 1, (1..3))") == "= ⟨2, 3⟩"


def test_filter_over_rows():
    assert ev(r"\filter(\fn(r) r[1] > 1, [1, 2; 3, 4])") == "= [3, 4;]"


def test_filter_empty_results():
    assert ev(r"\filter(\fn(x) x > 5, ⟨1, 2⟩)") == "= ⟨⟩"
    assert ev(r"\filter(\fn(x) x > 5, {1, 2})") == "= {}"
    fails(r"\filter(\fn(x) x > 5, [1, 2])", "tensor cannot be empty")


def test_filter_predicate_must_be_boolean():
    fails(r"\filter(\fn(x) 1, ⟨1⟩)", "needs a boolean from its predicate, got 1")


# --- \fold ---


def test_fold_without_seed_starts_from_the_first_element():
    assert ev(r"\fold(\fn(a, b) a + b, ⟨1, 2, 3⟩)") == "= 6"
    assert ev(r"\fold(\fn(a, b) a - b, ⟨10, 1, 2⟩)") == "= 7"  # left fold


def test_fold_with_seed():
    assert ev(r"\fold(\fn(a, b) a + b, ⟨1, 2, 3⟩, 10)") == "= 16"
    assert ev(r"\fold(\fn(a, b) a + b, ⟨⟩, 0)") == "= 0"
    assert ev(r"\fold(\fn(a, b) a ∪ {b}, {1, 2}, {})") == "= {1, 2}"


def test_fold_over_every_collection():
    assert ev(r"\fold(\fn(a, b) a + b, [1, 2; 3, 4])") == "= [4, 6]"
    assert ev(r"\fold(\fn(a, b) a * b, (1..5))") == "= 120"
    assert ev(r'\fold(\py("max"), {3, 9, 2})') == "= 9"


def test_fold_errors():
    fails(r"\fold(\fn(a, b) a, ⟨⟩)", "empty collection needs a seed")
    fails(r"\fold(\fn(a, b) a)", r"\\fold takes a function")
    fails(r"\fold(1, 2, 3, 4)", r"\\fold takes a function")


def test_prelude_names_are_protected():
    for name in ("map", "filter", "fold", "scan"):
        fails(rf"\{name} = 3", "protected")


def test_demo_script_runs():
    with open("demos/functions.ad", encoding="utf-8") as f:
        out = run_source(f.read(), {})
    assert out[-11:] == ["= 7", "= [1, 4, 9]", "= {2, 3}", "= 6", "= ⟨1, 2, 3⟩",
                         "= 55", "= [2, 3]", "= ⟨1, 2⟩", "= ⟨1, 4, 9⟩",
                         "= ⟨1, 3, 6, 10, 15, 21, 28, 36, 45, 55⟩", "= 3"]


# --- infinite ranges: lazy sequences and \take ---


def test_map_and_filter_over_an_infinite_range_are_lazy():
    env = {}
    assert ev(DEFS + r"q = \map(s, 1..)", env) == r"q = <seq \map(s, 1..)>"
    assert ev(r"\take(3, q)", env) == "= ⟨1, 4, 9⟩"
    assert ev(r"\take(2, \filter(\fn(x) x > 5, q))", env) == "= ⟨9, 16⟩"
    assert ev(r"\filter(\fn(x) x > 5, q)", env).startswith("= <seq \\filter(")


def test_lazy_sequence_is_reiterable_and_runs_nothing_until_consumed():
    env = {}
    ev(r"q = \map(\fn(x) 1/(x-1), 1..)", env)  # x=1 would divide by zero
    assert ev(r"\take(0, q)", env) == "= ⟨⟩"
    fails(r"\take(1, \map(\fn(x) 1/(x-1), 1..))", "division by zero")


def test_fold_binds_over_a_lazy_sequence_like_an_infinite_range():
    assert ev(r"\sum(k=\map(\fn(x) 1/x^2, 1..)) k").startswith("= 1.6449")
    fails(r"\sum(k=\map(\fn(x) [x], 1..)) k", "numbers")


def test_take_on_finite_collections_keeps_the_kind():
    assert ev(r"\take(2, [1, 2, 3])") == "= [1, 2]"
    assert ev(r"\take(2, ⟨1, 2, 3⟩)") == "= ⟨1, 2⟩"
    assert ev(r"\take(5, ⟨1, 2⟩)") == "= ⟨1, 2⟩"
    assert ev(r"\take(2, (1..10))") == "= ⟨1, 2⟩"
    assert ev(r"\take(3, (2,4..))") == "= ⟨2, 4, 6⟩"


def test_take_errors():
    fails(r"\take(-1, 1..)", "non-negative exact integer")
    fails(r"\take(1.5, 1..)", "non-negative exact integer")
    fails(r"\take(2, 3)", "needs a range or collection")
    fails(r"\take(1)", r"\\take takes a count and a collection")
    fails(r"\take = 3", "protected")


def test_lazy_errors():
    fails(r"\map(1, 1..)", "1 is not a function")
    fails(r"\take(2, \filter(\fn(x) x, 1..))", "needs a boolean")
    fails(r"\len(\map(\fn(x) x, 1..))", "needs a collection")


def test_filter_that_never_matches_stops_at_the_cap(monkeypatch):
    monkeypatch.setattr("adhoc.runtime.MAX_TERMS", 50)
    fails(r"\take(1, \filter(\fn(x) x < 0, 1..))", "no match within 50 elements")


def test_function_can_return_a_prelude_function():
    assert ev("h(x) = \\sqrt\nh(1)(9)") == "= 3"


# --- \fold over infinite input, \scan ---


def test_fold_over_infinite_input_converges_like_the_binder():
    assert ev(r"\fold(+, \map(\fn(x) 1/x^2, 1..))").startswith("= 1.64493406")


@pytest.mark.slow
def test_fold_product_over_infinite_input_plateaus():
    assert ev(r"\fold(*, \map(\fn(x) 1 + 1/x^2, 1..))").startswith("= 3.67607")
    assert ev(r"\fold(\fn(a, b) a, 1..)") == "= 1.0"


def test_fold_over_infinite_input_takes_a_seed():
    assert ev(r"\fold(+, \map(\fn(x) 1/2^x, 1..), 10)").startswith("= 10.99999999")


def test_fold_over_infinite_input_errors(monkeypatch):
    fails(r"\fold(*, 2..)", "diverged")
    fails(r"\fold(\fn(a, b) a < b, 1..)", "not numbers")
    fails(r"\fold(\fn(a, b) [a], 1..)", "operands must be numbers")
    monkeypatch.setattr("adhoc.runtime.MAX_TERMS", 50)
    fails(r"\fold(+, 1..)", "did not converge within 50 terms")


def test_scan_finite_keeps_the_kind():
    assert ev(r"\scan(+, ⟨1, 2, 3⟩)") == "= ⟨1, 3, 6⟩"
    assert ev(r"\scan(*, [1, 2, 3, 4])") == "= [1, 2, 6, 24]"
    assert ev(r"\scan(+, ⟨1, 2, 3⟩, 10)") == "= ⟨11, 13, 16⟩"
    assert ev(r"\scan(+, 1..4)") == "= ⟨1, 3, 6, 10⟩"


def test_scan_empty():
    assert ev(r"\scan(+, ⟨⟩, 5)") == "= ⟨⟩"
    fails(r"\scan(+, ⟨⟩)", "empty collection needs a seed")


def test_scan_over_infinite_input_is_lazy():
    env = {}
    assert ev(r"q = \scan(+, 1..)", env) == r"q = <seq \scan(+, 1..)>"
    assert ev(r"\take(4, q)", env) == "= ⟨1, 3, 6, 10⟩"
    assert ev(r"\take(3, \scan(+, 1.., 100))", env) == "= ⟨101, 103, 106⟩"
    assert ev(r"\scan(+, 1.., 100)", env) == r"= <seq \scan(+, 1.., 100)>"
    assert ev(r"\take(3, \scan(+, \map(\fn(x) x^2, 1..)))") == "= ⟨1, 5, 14⟩"


def test_scan_errors():
    fails(r"\scan(1, ⟨1, 2⟩)", "1 is not a function")
    fails(r"\scan(+)", r"\\scan takes a function")
    fails(r"\scan(+, 3)", "needs a range or collection")


def test_anonymous_lambda_label_shows_its_parameters():
    assert ev(r"\filter(\fn(x) x > 5, 1..)") == r"= <seq \filter(λ(x), 1..)>"
    assert ev(r"\map(\fn(a, b) a, 1..)") == r"= <seq \map(λ(a, b), 1..)>"
