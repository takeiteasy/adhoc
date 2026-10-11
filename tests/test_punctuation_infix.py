import pytest

from adhoc.diagnostic import render
from adhoc.driver import run_source
from adhoc.expression import show
from adhoc.lexer import CustomOp, GreaterEq, Minus, Number, Star, TokenBuffer, tokenize
from adhoc.parser import IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span


PAIR = r'\infix(11) \blend, <+>(a,b)=a+b' + '\n'


def test_declared_longest_match_and_utf8_spans():
    tokens = tokenize('π<+>2*-3>=0', operators={'<+', '<+>'})
    assert tokens[1] == CustomOp(ch='<+>', span=Span(2, 5))
    assert [type(token) for token in tokens[2:-1]] == [Number, Star, Minus, Number, GreaterEq, Number]
    assert tokenize('< + >', operators={'<+>'})[0].describe == '`<`'


def test_registration_invalidates_buffered_lookahead():
    tokens = TokenBuffer('π<+>2')
    assert tokens[2].describe == '`+`'
    tokens.operators = {'<+>'}
    tokens.reset(1)
    assert tokens[0].describe == '`π`'
    assert tokens[1] == CustomOp(ch='<+>', span=Span(2, 5))
    assert tokens[2].text == '2'


@pytest.mark.parametrize('spelling', ['<+>', '++', '**', '//', '%%', '@@', '^^', '><', '&&', '~', '&'])
def test_punctuation_declarations_and_compact_use(spelling):
    source = f'\\infix(11) {spelling}(a,b)=a+b\n2{spelling}3*4'
    assert run_source(source)[-1] == '= 14'


def test_overlapping_declarations_match_longest_and_remain_left_associative():
    source = r'''\infix(11) ~(a,b)=a-b
\infix(11) ~~(a,b)=a+b
\infix(12) ~~~(a,b)=a*b
20~2~~~3~~4~1
'''
    assert run_source(source)[-1] == '= 17'


def test_paired_punctuation_is_one_function_and_supports_quotes():
    env, operators = {}, {}
    outputs = run_source(PAIR + r'''f=<+>
f=\blend
<+>(2,3)
\map(<+>(·,2), ⟨1,2⟩)
q=\expr(2<+>3)
\eval(q)
\eval(\reduce(q))
g(x)=x<+>2
\eval(\body(g),x=3)
''', env, operators=operators)
    assert outputs[2:5] == ['true', '= 5', '= ⟨3, 4⟩']
    assert outputs[6:8] == ['= 5', '= 5']
    assert outputs[-1] == '= 5'
    assert show(env['q'].node) == '<+>(2, 3)'
    assert run_source(show(env['q'].node), env, operators=operators) == ['= 5']
    assert operators == {r'\blend': ('blend', 11), '<+>': ('blend', 11)}


def test_punctuation_recursion_uses_its_own_registration():
    source = r'\infix(11) <+>(a,b)=b<=0 ? 0 : a+(a<+>(b-1))' + '\n3<+>4'
    assert run_source(source)[-1] == '= 12'


def test_existing_syntax_and_strings_are_unaffected():
    source = PAIR + r'''2*-3
2+-3
3!!
2<=3
3>=2
\expr(x -> x+1)
"<+> -- ->" = "<+> -- ->"
2<+>3--<+> ignored
1..2<+>2
⌊2.5⌋
|2-5|
'''
    outputs = run_source(source)
    assert outputs[1:6] == ['= -6', '= -1', '= 3', '= true', '= true']
    assert outputs[-5:] == ['= true', '= 5', '= <range 1..4>', '= 2', '= 3']


@pytest.mark.parametrize('spelling', [
    '+', '-', '*', '/', '^', '%', '@', '<', '>', '<=', '>=', '--', '->',
    '<-->', '+->', '!=', '!!', '<=>', '..', ':', '?', '$', '|', '[+]', '{+}',
])
def test_reserved_punctuation_has_a_typed_diagnostic_and_does_not_register(spelling):
    operators = {}
    source = f'\\infix(11) {spelling}(a,b)=a+b'
    with pytest.raises(ParseError, match='reserved or invalid punctuation') as failure:
        parse_program(source, operators=operators)
    start = len(r'\infix(11) ')
    assert failure.value.span == Span(start, start + len(spelling))
    assert operators == {}


@pytest.mark.parametrize('suffix', ['', '\n(', '\n;;', '\n"unfinished'])
def test_incomplete_and_failed_parses_leave_both_registries_unchanged(suffix):
    aliases, operators = {}, {}
    source = r'\alias \beta, β' + '\n' + PAIR
    source += suffix if suffix else r'\infix(11) ~~(a,b)='
    with pytest.raises(ParseError):
        parse_program(source, aliases, operators)
    assert aliases == operators == {}


def test_punctuation_sessions_and_runtime_failure():
    env, operators = {}, {}
    run_source(PAIR, env, operators=operators)
    assert run_source('2<+>\n3', env, operators=operators) == ['= 5']
    with pytest.raises(IncompleteInput):
        parse_program('2<+>', operators=operators)
    with pytest.raises(EvalError, match='division by zero'):
        run_source(r'\infix(11) ~~(a,b)=a+b' + '\n1/0', env, operators=operators)
    assert run_source('2~~3', env, operators=operators) == ['= 5']
    with pytest.raises(ParseError, match='already declared'):
        parse_program(PAIR, operators=operators)


def test_imported_punctuation_stays_local(tmp_path):
    (tmp_path / 'ops.ad').write_text(PAIR + 'v=2<+>3\n')
    operators = {}
    assert run_source(r'\import("ops")' + '\n' + r'\blend(2,3)',
                      base_dir=str(tmp_path), operators=operators) == ['= 5']
    assert operators == {}
    with pytest.raises(ParseError):
        parse_program('2<+>3', operators=operators)
    (tmp_path / 'bad.ad').write_text('v=2<+>3\n')
    env = {}
    run_source(PAIR, env, operators=operators)
    with pytest.raises(EvalError):
        run_source(r'\import("bad")', env, base_dir=str(tmp_path), operators=operators)


def test_undeclared_new_punctuation_points_to_its_written_spelling():
    with pytest.raises(ParseError, match='undeclared operator `&`') as failure:
        parse_program('π & 2')
    assert failure.value.span == Span(3, 4)
    assert '^' in render('π & 2', 'ERROR', failure.value.msg, failure.value.span)
