import pytest

from adhoc.driver import run_source
from adhoc.lexer import HashBracket, LAngle, LexError, RAngle, tokenize
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.syntax import ArrayLit, Index


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, message, env=None):
    with pytest.raises(EvalError, match=message):
        run_source(src, {} if env is None else env)


def test_three_spellings_are_one_value():
    assert ev("⟨1, [1, 2], 3.5⟩") == "= ⟨1, [1, 2], 7/2⟩"
    assert ev("#[1, [1, 2], 3.5]") == "= ⟨1, [1, 2], 7/2⟩"
    assert ev(r"\arr(1, [1, 2], 3.5)") == "= ⟨1, [1, 2], 7/2⟩"


def test_arrays_are_ragged_and_heterogeneous():
    assert ev(r'⟨1, "a", \true, ⟨2, 3⟩, \fn(x) x⟩') == '= ⟨1, "a", true, ⟨2, 3⟩, <λ(x)>⟩'
    assert ev("⟨[1, 2], [3]⟩") == "= ⟨[1, 2], [3]⟩"
    assert ev("⟨√2, 1/3⟩") == "= ⟨1.4142135623731..., 1/3⟩"


def test_empty_arrays():
    assert ev("⟨⟩") == "= ⟨⟩"
    assert ev("#[]") == "= ⟨⟩"
    assert ev(r"\arr()") == "= ⟨⟩"
    assert ev(r"\len(⟨⟩)") == "= 0"


def test_indexing_is_one_based_and_chains():
    env = {}
    run_source("a = ⟨1, [10, 20], ⟨5, 6⟩⟩", env)
    assert ev("a[1]", env) == "= 1"
    assert ev("a[2]", env) == "= [10, 20]"
    assert ev("a[2][2]", env) == "= 20"
    assert ev("a[3][1]", env) == "= 5"
    assert ev("a[1 + 1][1]", env) == "= 10"


def test_index_errors():
    env = {}
    run_source("a = ⟨1, 2⟩", env)
    fails("a[3]", "index 3 out of range 1..2", env)
    fails("a[0]", "index 0 out of range 1..2", env)
    fails("a[1/2]", "index must be an exact integer", env)
    fails("a[1, 2]", "an array takes one index", env)


def test_literal_heads_do_not_index():
    fails("⟨1, 2⟩[1]", "arrays do not support arithmetic")
    fails(r"\arr(1, 2)[1]", "arrays do not support arithmetic")


def test_no_implied_algebra():
    env = {}
    run_source("a = ⟨1, 2⟩", env)
    for src in ["a + a", "a + 1", "1 - a", "2a", "a * a", "a / 2", "a ^ 2", "-a", "a · a"]:
        fails(src, "arrays do not support arithmetic", env)
    fails("a < a", "arrays do not support arithmetic", env)
    fails("[1, ⟨2⟩]", "arrays do not support arithmetic")
    fails("a'", "transpose needs a tensor", env)


def test_equality_is_ordered_and_elementwise():
    env = {}
    run_source("a = ⟨1, [1, 2], ⟨3⟩⟩", env)
    assert ev("a = ⟨1, [1, 2], ⟨3⟩⟩", env) == "true"
    assert ev("a = ⟨1, [1, 2], ⟨4⟩⟩", env) == "false"
    assert ev("a = ⟨[1, 2], 1, ⟨3⟩⟩", env) == "false"
    assert ev("a = ⟨1⟩", env) == "false"
    assert ev("a = [1, 2, 3]", env) == "false"
    assert ev("t = ⟨1/2⟩; t = ⟨0.5⟩") == "true"


def test_binding_echoes_and_is_immutable():
    env = {}
    assert run_source("a = #[1, 2]", env) == ["a = ⟨1, 2⟩"]
    assert run_source(r"a = \arr(1, 2)", env) == ["true"]


def test_len_and_fold_iteration():
    assert ev(r"\len(⟨1, [1, 2], 3⟩)") == "= 3"
    assert ev(r"\sum(x=⟨1, 2, 3⟩) x^2") == "= 14"
    assert ev(r"\prod(x=#[2, 3, 4]) x") == "= 24"
    assert ev(r"\sum(x=⟨[1, 2], [3, 4]⟩) x") == "= [4, 6]"


def test_fold_over_an_array_of_non_numbers_fails_at_the_term():
    fails(r'\sum(x=⟨1, "a"⟩) x', "strings are not numbers")


def test_arrays_pass_through_functions():
    env = {}
    run_source("f(a) = a[2]", env)
    assert ev("f(⟨1, 2, 3⟩)", env) == "= 2"
    assert ev(r"(\fn(a) \len(a))(#[1, 2])") == "= 2"


def test_parse_shapes():
    assert isinstance(parse_program("⟨1, 2⟩"), ArrayLit)
    assert isinstance(parse_program("#[1, 2]"), ArrayLit)
    match parse_program(r"\arr(1, 2)"):
        case ArrayLit(items=(_, _)):
            pass
        case other:
            raise AssertionError(other)
    match parse_program("a[1][2]"):
        case Index(head=Index()):
            pass
        case other:
            raise AssertionError(other)
    with pytest.raises(ParseError, match="positional"):
        parse_program(r"\arr(1, \a=2)")


def test_lexing():
    kinds = [type(t) for t in tokenize("⟨#[⟩")]
    assert kinds[:3] == [LAngle, HashBracket, RAngle]
    with pytest.raises(LexError):
        tokenize("# [1]")


def test_newlines_and_continuation():
    assert ev("⟨1,\n 2\n⟩") == "= ⟨1, 2⟩"
    for src in ["⟨1, 2", "#[1,", "\\arr(1", "⟨"]:
        with pytest.raises(IncompleteInput):
            parse_program(src)


def test_quotes_round_trip():
    env = {}
    run_source(r"q = \expr(⟨x, [1, 2]⟩)", env)
    shown = ev("q", env)[2:]
    assert shown == r"\expr(⟨x, [1, 2]⟩)"
    run_source(f"r = {shown}", env)
    assert ev("q = r", env) == "true"
    assert ev(r"\eval(q, x=7)", env) == "= ⟨7, [1, 2]⟩"
    assert ev(r"\reduce(\expr(⟨(\fn(x) x)(1)⟩))") == r"= \expr(⟨1⟩)"


def test_arr_is_reserved():
    fails(r"\arr = 1", "protected")
