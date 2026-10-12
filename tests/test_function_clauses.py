from fractions import Fraction

import pytest

from adhoc.driver import compile_source, run_source
from adhoc.expression import ExpressionValue, show
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import Derivative, EvalError, Inverse
from adhoc.span import Span
from adhoc.symbolic_worker import snapshot
from adhoc.syntax import BinderPattern, FuncDef, LiteralPattern


def test_factorial_clauses_and_expression_equality():
    env = {}
    assert run_source("f(0) = 1\nf(n) = n*f(n-1)\nf(5)\n(f(0)=1)", env) == [
        "f = <fn f/1; 1 clauses>", "f = <fn f/1; 2 clauses>", "= 120", "= true",
    ]
    assert env["f"].arity == 1


def test_patterns_are_explicit_and_bind_only_names():
    node = parse_program('f(-2, x, "a", \\true) = x')
    assert isinstance(node, FuncDef)
    assert node.params == ("x",)
    assert [type(p) for p in node.patterns] == [
        LiteralPattern, BinderPattern, LiteralPattern, LiteralPattern,
    ]


@pytest.mark.parametrize("pattern, argument", [
    ("0", "0."), ("0.5", "1/2"), ("-2", "-2."), ("+2", "2."),
    ("-0.25", "-1/4"), ("1e3", "1000"), ('"hello"', '"hello"'),
    (r"\true", r"\true"), (r"\false", r"\false"),
])
def test_literal_matching_uses_value_equality(pattern, argument):
    env = {}
    run_source(f"f({pattern}) = 7\nf(x) = 9", env)
    assert run_source(f"f({argument})", env) == ["= 7"]


def test_boolean_patterns_do_not_match_numbers():
    env = {}
    run_source("f(\\true)=7\nf(1)=9\nf(x)=11", env)
    assert run_source(r"f(\true); f(1); f(\false)", env) == ["= 7", "= 9", "= 11"]
    run_source("g(0)=1\ng(x)=2", env)
    assert run_source(r"g(\false)", env) == ["= 2"]


def test_order_duplicates_catchall_and_zero_argument_clauses():
    env = {}
    run_source("f(0)=1\nf(0)=2\nf(x)=3\nf(1)=4\ng()=5\ng()=6", env)
    assert run_source("f(0); f(1); f(2); g()", env) == ["= 1", "= 3", "= 3", "= 5"]


def test_clause_local_names_and_enclosing_bindings():
    env = {}
    run_source("x=100\ny=10\nf(0,x)=y+x\nf(a,b)=c=a+b; c", env)
    assert run_source("f(0,2); f(1,2); x", env) == ["= 12", "= 3", "= 100"]
    assert "a" not in env and "b" not in env and "c" not in env


def test_arguments_evaluate_once_and_unselected_bodies_do_not_run():
    calls = []

    def record(value):
        calls.append(value)
        return value

    env = {"record": record}
    run_source("f(0)=1/0\nf(1)=7\nf(x)=\\missing", env)
    assert run_source(r"f(\record(1))", env) == ["= 7"]
    assert calls == [1]
    with pytest.raises(EvalError, match="division by zero"):
        run_source("f(0)", env)


def test_no_match_and_wrong_call_arity_point_at_call():
    env = {}
    run_source("f(0)=1", env)
    for call, message in [("f(2)", "no matching clause"), ("f()", "takes 1 arguments")]:
        with pytest.raises(EvalError, match=message) as failure:
            run_source(call, env)
        assert failure.value.span == Span(0, len(call))


@pytest.mark.parametrize("source, message", [
    ("f(x,x)=1", "binders must be distinct"),
    ("f(x+1)=1", "patterns must be names or literals"),
    ("f(1/2)=1", "patterns must be names or literals"),
    ("f([x,y])=1", "patterns must be names or literals"),
    ("f(⟨x,y⟩)=1", "patterns must be names or literals"),
])
def test_invalid_patterns_are_parse_errors(source, message):
    with pytest.raises(ParseError, match=message):
        compile_source(source)


def test_canonical_duplicate_binders_and_protected_names():
    with pytest.raises(ParseError, match="binders must be distinct"):
        compile_source(r"\alias \alpha, α; f(α,\alpha)=1")
    for source in ("f(e)=1", r"f(\pi)=1", r"\sin(x)=1"):
        with pytest.raises(EvalError, match="protected"):
            run_source(source)


def test_addition_validation_is_atomic_and_has_definition_span():
    env = {}
    run_source("f(0)=1", env)
    fn = env["f"]
    for source, message in [("f(x,y)=2", "clauses take 1 arguments"),
                            ("f(e)=2", "protected"),
                            (r"\let f(x)=2", "already bound")]:
        with pytest.raises(EvalError, match=message) as failure:
            run_source(source, env)
        assert failure.value.span == Span(0, len(source))
        assert len(fn.clauses) == 1 and fn.revision == 0
    run_source("f(n)=n", env)
    assert env["f"] is fn and fn.revision == 1


def test_fresh_only_first_patterned_clause():
    env = {}
    run_source("\\let f(0)=1\nf(n)=n", env)
    assert run_source("f(0); f(5)", env) == ["= 1", "= 5"]


def test_live_aliases_partials_composition_and_higher_order_calls():
    env = {}
    run_source("f(0,x)=x\ng=f\np=f(2,·)\nh(x)=x+1\nc=h∘p", env)
    run_source("f(n,x)=n+x", env)
    assert run_source("g(2,3); p(3); c(3); \\map(p,⟨1,2⟩)", env) == [
        "= 5", "= 5", "= 6", "= ⟨3, 4⟩",
    ]
    with pytest.raises(EvalError, match="positional arguments only"):
        run_source("f(n=2,x=3)", env)
    with pytest.raises(EvalError, match="takes 2 arguments"):
        run_source("f(·)", env)


def test_additions_through_aliases_enclosing_scopes_and_recursion_are_rejected():
    env = {}
    run_source("f(0)=1\ng=f\nh()=(f(x)=2\n)\nr(n)=(r(x)=2\n)", env)
    for source in ("g(x)=2", "h()", "r(1)"):
        with pytest.raises(EvalError, match="already bound"):
            run_source(source, env)
    assert len(env["f"].clauses) == 1


def test_canonical_spelling_alias_and_dual_definition():
    env, aliases = {}, {}
    run_source(r"\dual \fact, φ(0)=1", env, aliases=aliases)
    run_source(r"\fact(n)=n*φ(n-1)", env, aliases=aliases)
    assert run_source("φ(5)", env, aliases=aliases) == ["= 120"]
    assert run_source(r"\fact", env, aliases=aliases) == [r"= <fn φ/1; 2 clauses>"]


def test_nested_clauses_capture_their_defining_call():
    env = {}
    run_source("f(a)=(\ng(0)=a\ng(n)=n+g(n-1)\ng\n)", env)
    run_source("h=f(10)\nk=f(20)", env)
    assert run_source("h(3); k(3)", env) == ["= 16", "= 26"]
    assert "g" not in env


def test_imported_clauses_dispatch_but_cannot_be_extended(tmp_path):
    module = tmp_path / "clauses.ad"
    module.write_text("f(0)=1\nf(n)=n*f(n-1)\n")
    env, modules = {}, {}
    run_source(r'\import("clauses")', env, modules=modules, base_dir=str(tmp_path))
    assert run_source("f(5)", env) == ["= 120"]
    with pytest.raises(EvalError, match="already bound"):
        run_source("f(x)=2", env)
    run_source(r'\import("clauses")', env, modules=modules, base_dir=str(tmp_path))


def test_selected_body_error_retains_original_source_and_spelling():
    source = "f(0)=1\nf(α)=\\missing+α"
    env = {}
    run_source(source, env)
    with pytest.raises(EvalError, match="not bound") as failure:
        run_source("f(2)", env)
    start = len(source[:source.index(r"\missing")].encode())
    assert failure.value.span == Span(start, start + len(r"\missing"))
    assert failure.value.source == source


def test_statement_quote_roundtrip_and_execution():
    env = {}
    run_source('q=\\expr((f(0)=1\nf(n)=n*f(n-1)\nf(5)))', env)
    assert run_source(r"\eval(q)", env) == ["= 120"]
    rendered = run_source("q", env)[0][2:]
    run_source("r=" + rendered, env)
    assert env["r"] == env["q"]
    assert run_source(r"\eval(r)", env) == ["= 120"]
    node = parse_program(r"\let f(-2)=3")
    assert ExpressionValue(parse_program(show(node)), "", True) == ExpressionValue(node, "", True)


def test_multiline_pattern_head_and_body():
    env = {}
    run_source("f(\n0,\nx)= (y=x+1\ny)\nf(a,b)=a+b", env)
    assert run_source("f(0,3); f(2,3)", env) == ["= 4", "= 5"]


@pytest.mark.parametrize("definition", ["f(0)=1", "f(x)=x^2\nf(y)=y"])
def test_body_and_symbolic_operations_reject_unsupported_clauses(definition):
    env = {}
    run_source(definition, env)
    assert snapshot(env["f"]).symbolic_supported is False
    for expression in (r"\body(f)", r"\deriv(f)", r"\simplify(f)",
                       r"\jacobian(f)", r"f⁻¹(1,\all=\true)"):
        with pytest.raises(EvalError, match="single clause with name parameters"):
            run_source(expression, env)


def test_tex_renders_every_clause_in_order():
    env = {}
    run_source("f(0)=1\nf(n)=n+2", env)
    expected = r'"\\begin{aligned} f\\left(0\\right) &= 1 \\\\ f\\left(n\\right) &= n + 2 \\end{aligned}"'
    assert run_source(r"\tex(f)", env) == ["= " + expected]


def test_derivative_and_inverse_caches_refresh_after_addition():
    env = {}
    run_source("f(x)=x^2", env)
    derivative, inverse = Derivative(env["f"], 1), Inverse(env["f"])
    assert derivative(2) == 4
    assert inverse(4) == 2
    assert derivative._symbolic is not None
    run_source("f(y)=y", env)
    assert abs(derivative(2) - 4) < 1e-8
    assert abs(inverse(4) - 2) < 1e-8
    assert derivative._symbolic is None
    assert inverse._solved[1] == []


def test_symbolic_dependency_cache_refresh_and_nested_rejection():
    env = {}
    run_source("f(x)=x^2\ng(x)=f(x)+1", env)
    derivative = Derivative(env["g"], 1)
    assert derivative(Fraction(1, 2)) == 1
    run_source("f(y)=y", env)
    assert abs(derivative(Fraction(1, 2)) - 1) < 1e-8
    assert derivative._symbolic is None
    with pytest.raises(EvalError, match="single clause with name parameters"):
        run_source(r"\deriv(g)", env)


def test_boolean_spelling_alias_is_a_literal_pattern():
    env, aliases = {}, {}
    run_source(r"\alias \true, τ; f(τ)=7", env, aliases=aliases)
    run_source("f(x)=9", env, aliases=aliases)
    assert run_source(r"f(τ); f(1)", env, aliases=aliases) == ["= 7", "= 9"]


def test_numeric_calculus_and_graph_sampling_dispatch_clauses():
    from adhoc.graph import GraphValue

    env = {}
    run_source("f(0)=0\nf(x)=x^2", env)
    assert float(run_source("f'(2)", env)[0][2:]) == pytest.approx(4)
    assert float(run_source(r"\int(x=0..1) f(x)", env)[0][2:]) == pytest.approx(1/3)
    run_source(r"g=\graph(f,x=-1..1)", env)
    assert isinstance(env["g"], GraphValue)
    assert env["g"].complete


def test_failed_addition_to_nonfunction_and_anonymous_alias():
    env = {}
    run_source("x=2\nf=\\fn(n) n", env)
    for definition in ("x(n)=n", "f(n)=n+1"):
        with pytest.raises(EvalError, match="already bound"):
            run_source(definition, env)
    assert run_source("x; f(3)", env) == ["= 2", "= 3"]
