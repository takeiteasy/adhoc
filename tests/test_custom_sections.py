import pytest

from adhoc.diagnostic import render
from adhoc.driver import compile_source, run_source
from adhoc.expression import show
from adhoc.parser import INFIX_LEVELS, IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import BackslashRef, Call, Hole


SPELLINGS = [r'\blend', '⊕', '<+>']


def declaration(spelling, level=11, body='a-b'):
    return f'\\infix({level}) {spelling}(a,b)={body}\n'


@pytest.mark.parametrize('spelling', SPELLINGS)
@pytest.mark.parametrize('level', sorted(INFIX_LEVELS))
def test_sections_at_every_declared_level_and_spelling(spelling, level):
    source = declaration(spelling, level)
    assert run_source(source + f'(2 {spelling})(3)')[-1] == '= -1'
    assert run_source(source + f'({spelling} 2)(3)')[-1] == '= 1'
    assert run_source(source + f'({spelling})(2,3)')[-1] == '= -1'


@pytest.mark.parametrize('spelling', SPELLINGS)
@pytest.mark.parametrize(('level', 'tighter'), [(3, 4), (4, 5), (5, 6), (6, 9), (9, 10), (10, 11), (11, 12), (12, 15)])
def test_right_section_accepts_tighter_custom_operand(spelling, level, tighter):
    source = declaration(spelling, level) + declaration('⊙', tighter, 'a+b')
    assert run_source(source + f'({spelling} 2 ⊙ 3)(10)')[-1] == '= 5'
    assert run_source(source + f'(2 ⊙ 3 {spelling})(10)')[-1] == '= -5'


@pytest.mark.parametrize('level', sorted(INFIX_LEVELS))
def test_left_section_keeps_custom_left_association(level):
    source = declaration('⊕', level)
    assert run_source(source + '(10 ⊕ 3 ⊕)(2)')[-1] == '= 5'


@pytest.mark.parametrize(('level', 'expression'), [
    (3, r'(\true ↔ \false ⊕)'),
    (3, r'(\true ⊕ \false ↔)'),
    (9, '(1 < 2 ⊕)'),
    (9, '(1 ⊕ 2 <)'),
    (10, '(1 ∠ 2 ⊕)'),
    (10, '(1 ⊕ 2 ∠)'),
])
def test_mixed_nonassociative_sections_require_parentheses(level, expression):
    with pytest.raises(ParseError, match='parenthesize'):
        parse_program(declaration('⊕', level) + expression)


@pytest.mark.parametrize('spelling', SPELLINGS)
@pytest.mark.parametrize(('level', 'expression'), [
    (11, '({op} 1 + 2)'),
    (12, '({op} 1 + 2)'),
    (12, '(1 + 2 {op})'),
    (15, '({op} 2^3)'),
    (15, '(-2 {op})'),
    (11, '(1; 2 {op})'),
])
def test_invalid_section_operands_have_parentheses_diagnostics(spelling, level, expression):
    with pytest.raises(ParseError, match='parenthesize'):
        parse_program(declaration(spelling, level) + expression.format(op=spelling))


@pytest.mark.parametrize('spelling', SPELLINGS)
def test_calls_take_priority_over_sections_even_with_spaces(spelling):
    source = declaration(spelling)
    assert run_source(source + f'({spelling}(2,3))')[-1] == '= -1'
    assert run_source(source + f'({spelling} (2,3))')[-1] == '= -1'
    assert run_source(source + f'({spelling}(·,2))(3)')[-1] == '= 1'
    with pytest.raises(EvalError, match='takes 2 arguments, got 1'):
        run_source(source + f'({spelling} (2+3))')
    assert run_source(source + f'{spelling}(·,(2+3))(10)')[-1] == '= 5'


@pytest.mark.parametrize('spelling', SPELLINGS)
def test_nested_sections_and_ordinary_function_values(spelling):
    source = declaration(spelling)
    assert run_source(source + f'(({spelling} 2)(5) {spelling})(1)')[-1] == '= 2'
    assert run_source(source + f'({spelling} 2*({spelling} 3)(5))(10)')[-1] == '= 6'
    assert run_source(source + f'f={spelling}\nf={spelling}\nf(4,2)')[1:] == [
        f'f = <fn {spelling}(a, b)>', 'true', '= 2'
    ]
    assert run_source(source + f'\\map(({spelling} 2), ⟨1,2,3⟩)')[-1] == '= ⟨-1, 0, 1⟩'


@pytest.mark.parametrize('spelling', SPELLINGS)
def test_quote_round_trip_reduction_and_reflected_body(spelling):
    env, operators = {}, {}
    source = declaration(spelling) + f'q=\\expr(({spelling} 2))\nr=\\expr((2 {spelling}))\n'
    run_source(source, env, operators=operators)
    for name, args, expected in [('q', '·, 2', '= 1'), ('r', '2, ·', '= -1')]:
        text = show(env[name].node)
        assert text == f'{spelling}({args})'
        assert run_source(text + '(3)', env, operators=operators) == [expected]
        assert run_source(f'\\eval({name})(3)', env, operators=operators) == [expected]
        assert run_source(f'\\eval(\\reduce({name}))(3)', env, operators=operators) == [expected]
    assert run_source(f'f(x)=({spelling} x)\n\\eval(\\body(f),x=2)(3)',
                      env, operators=operators)[-1] == '= 1'
    assert run_source(r'\tex(q)', env, operators=operators)[-1].startswith('= "')
    node = env['q'].node
    assert isinstance(node, Call) and isinstance(node.head, BackslashRef)
    assert isinstance(node.args[0], Hole)
    assert node.head.spelling == spelling


def test_section_fixed_operand_and_head_are_captured_once():
    events = []
    env = {'tick': lambda: events.append('tick') or 2}
    operators = {}
    run_source(declaration('⊕') + r'f=(⊕ \tick())', env, operators=operators)
    assert events == ['tick']
    env['⊕'] = lambda a, b: 999
    assert run_source('f(5)\nf(7)', env, operators=operators) == ['= 3', '= 5']
    assert events == ['tick']
    with pytest.raises(EvalError, match='division by zero'):
        run_source('(⊕ 1/0)', env, operators=operators)


def test_paired_spellings_share_partial_head_and_preserve_display():
    source = r'\infix(11) \blend, <+>(a,b)=a-b' + '\n'
    env = {}
    outputs = run_source(source + r'''f=(<+> 2)
g=(\blend 2)
f(5)
g(5)
q=\expr((<+> 2))
r=\expr((\blend 2))
''', env)
    assert outputs[1:3] == [r'f = <fn \blend(·, 2)>', r'g = <fn \blend(·, 2)>']
    assert env['f'].fn is env['g'].fn is env['blend']
    assert outputs[3:5] == ['= 3', '= 3']
    assert outputs[-2:] == [r'q = \expr(<+>(·, 2))', r'r = \expr(\blend(·, 2))']


@pytest.mark.parametrize('spelling', SPELLINGS)
@pytest.mark.parametrize('expression', ['({op} 2', '(2 {op}'])
def test_unclosed_custom_sections_are_incomplete(spelling, expression):
    operators = {}
    parse_program(declaration(spelling), operators=operators)
    previous = dict(operators)
    with pytest.raises(IncompleteInput):
        parse_program(expression.format(op=spelling), operators=operators)
    assert operators == previous


def test_undeclared_section_spelling_has_its_own_span():
    with pytest.raises(ParseError, match='undeclared operator') as failure:
        compile_source('(⊕ 2)')
    assert failure.value.span == Span(1, 4)


def test_section_diagnostic_uses_written_spelling_and_utf8_columns():
    source = declaration('⊕', 12) + '(1 + 2 ⊕)'
    with pytest.raises(ParseError, match='parenthesize') as failure:
        compile_source(source)
    assert '⊕' in failure.value.msg
    start = len(source[:source.rindex('⊕')].encode('utf-8'))
    assert failure.value.span == Span(start, start + 3)
    assert '^' in render(source, 'ERROR', failure.value.msg, failure.value.span)


def test_custom_name_matching_builtin_engine_key_uses_declared_precedence():
    source = declaration(r'\member', 11)
    assert run_source(source + r'(\member 2*3)(10)')[-1] == '= 4'
    with pytest.raises(ParseError, match='parenthesize'):
        parse_program(source + r'(\member 2+3)')


def test_section_reports_a_declared_but_unbound_function():
    env, operators = {}, {}
    with pytest.raises(EvalError, match='division by zero'):
        run_source('1/0\n' + declaration('<+>'), env, operators=operators)
    with pytest.raises(EvalError, match=r'`<\+>` is not bound'):
        run_source('(<+> 2)', env, operators=operators)


def test_custom_sections_enforce_ordinary_partial_arity():
    source = declaration('⊕')
    with pytest.raises(EvalError, match='takes 1 arguments, got 2'):
        run_source(source + '(⊕ 2)(3,4)')
