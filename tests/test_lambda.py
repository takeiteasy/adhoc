import pytest

from adhoc.driver import run_source
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import BinOp, BinOperator as B, Call, Lambda, NumLit, Var


def define(source):
    env = {}
    run_source(source, env)
    return env


def shape(node):
    if not hasattr(node, "__dataclass_fields__"):
        return repr(node)
    return (
        type(node).__name__,
        {k: shape(v) for k, v in vars(node).items() if k != "span"},
    )


def test_lambda_shape():
    node = parse_program("\\fn(x) x + 1")
    assert isinstance(node, Lambda)
    assert node.params == ("x",)
    assert isinstance(node.body, BinOp) and node.body.op is B.ADD


def test_unicode_and_ascii_spellings_are_the_same_node():
    assert shape(parse_program("\\fn(x) x + 1")) == shape(parse_program("\\λ(x) x + 1"))


def test_zero_argument_lambda():
    node = parse_program("\\fn() 42")
    assert node.params == ()
    assert node.body == NumLit(text="42", span=Span(6, 8))


def test_body_extends_greedily_to_the_enclosing_delimiter():
    # In an argument list the comma ends the body: the lambda is one argument.
    node = parse_program("k(\\fn(x) x + 1, 2)")
    assert isinstance(node, Call)
    assert isinstance(node.args[0], Lambda)
    assert isinstance(node.args[0].body, BinOp)
    assert node.args[1] == NumLit(text="2", span=Span(16, 17))


def test_parenthesized_lambda_is_a_call_head():
    node = parse_program("(\\fn(x) x)(5)")
    assert isinstance(node, Call)
    assert isinstance(node.head, Lambda)


def test_lambda_takes_a_body_not_an_assignment():
    with pytest.raises(ParseError, match="a lambda takes a body, not `=`"):
        parse_program("\\fn(x) = 3")


def test_bare_lambda_head_reports_usage_at_evaluation():
    with pytest.raises(EvalError, match="parenthesized parameter list"):
        run_source("\\fn", {})


def test_application_on_a_parenthesized_lambda():
    assert run_source("(\\fn(x) x)(5)", {}) == ["= 5"]
    assert run_source("(\\fn(x) x + 1)(4)", {}) == ["= 5"]


def test_zero_argument_application():
    env = define("k = \\fn() 42")
    assert run_source("k()", env) == ["= 42"]


def test_lambdas_display_as_lambda():
    assert run_source("\\inc = \\fn(x) x + 1", {}) == ["\\inc = <λ(x)>"]
    assert run_source("\\dbl = \\λ(x) 2x", {}) == ["\\dbl = <λ(x)>"]


def test_lambda_binding_checks_by_identity():
    env = define("g = \\fn(x) x")
    assert run_source("g = g", env) == ["true"]


def test_lambdas_read_the_enclosing_scope():
    env = define("m = 10")
    run_source("\\add = \\fn(x) x + m", env)
    assert run_source("\\add(5)", env) == ["= 15"]


def test_closures_capture_the_defining_scope():
    env = define("\\mk = \\fn(n) \\fn(x) x + n")
    run_source("\\five = \\mk(5)", env)
    assert run_source("\\five(1)", env) == ["= 6"]


def test_lambda_arity_is_checked():
    with pytest.raises(EvalError, match="λ takes 1 arguments, got 0"):
        run_source("(\\fn(x) x)()", {})
    with pytest.raises(EvalError, match="λ takes 2 arguments, got 1"):
        run_source("(\\fn(x, y) x)(1)", {})


def test_lambdas_reject_keyword_arguments():
    env = define("k = \\fn(x) x")
    with pytest.raises(EvalError, match="positional arguments only"):
        run_source("k(1, \\a=2)", env)


def test_lambda_parameters_reject_protected_names():
    with pytest.raises(EvalError, match="`pi` is protected"):
        run_source("\\fn(π) π", {})


def test_body_errors_carry_their_own_span():
    # The span is relative to the defining unit's source: `x + "a"` inside
    # `\add = \fn(x) x + "a"`.
    env = define(r'\add = \fn(x) x + "a"')
    with pytest.raises(EvalError, match="strings are not numbers") as error:
        run_source("\\add(1)", env)
    assert error.value.span == Span(14, 21)


def test_church_numerals_end_to_end():
    env = {}
    run_source("\\zero = \\fn(f) \\fn(x) x", env)
    run_source("\\succ = \\fn(n) \\fn(f) \\fn(x) f(n(f)(x))", env)
    run_source("\\plus = \\fn(m) \\fn(n) \\fn(f) \\fn(x) m(f)(n(f)(x))", env)
    run_source("\\two = \\plus(\\succ(\\zero))(\\succ(\\zero))", env)
    run_source("\\three = \\succ(\\two)", env)
    assert run_source("\\two(\\fn(v) v + 1)(0)", env) == ["= 2"]
    assert run_source("\\three(\\fn(v) v + 1)(0)", env) == ["= 3"]
    assert run_source("\\zero(\\fn(v) v + 1)(0)", env) == ["= 0"]
    assert run_source("\\three(\\succ)(\\zero)(\\fn(v) v + 1)(0)", env) == ["= 3"]


def test_z_combinator_gives_eager_recursion():
    env = {}
    run_source("\\Z = \\fn(f) (\\fn(x) f(\\fn(v) x(x)(v)))(\\fn(x) f(\\fn(v) x(x)(v)))",
               env)
    run_source("\\fact = \\Z(\\fn(g) \\fn(n) n <= 1 ? 1 : n * g(n - 1))", env)
    assert run_source("\\fact(5)", env) == ["= 120"]


def test_lambda_body_can_be_a_block():
    # `\begin … \end` gives the body an explicit extent and multiple statements;
    # after `\end` the unit may continue.
    env = define("\\twice = \\fn(f) \\begin g = \\fn(x) f(f(x)); g \\end")
    assert run_source("\\twice(\\fn(v) v * 3)(7)", env) == ["= 63"]


def test_nested_lambdas_stay_greedy_without_blocks():
    # Right-associative greedy nesting: each lambda's body is the rest of the
    # expression, so the Church encoding needs no delimiters at all.
    env = define("\\zero = \\fn(f) \\fn(x) x")
    run_source("\\succ = \\fn(n) \\fn(f) \\fn(x) f(n(f)(x))", env)
    run_source("\\one = \\succ(\\zero)", env)
    assert run_source("\\one(\\fn(v) v + 1)(0)", env) == ["= 1"]
