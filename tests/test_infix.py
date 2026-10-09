import pytest

from adhoc.driver import compile_source, run_source
from adhoc.expression import show
from adhoc.lexer import CustomOp, LexError, tokenize
from adhoc.parser import INFIX_LEVELS, IncompleteInput, ParseError, parse_program
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.syntax import Call, Seq


def test_glyph_token_has_utf8_span():
    token = tokenize('π ⊕ 2')[1]
    assert isinstance(token, CustomOp)
    assert token.ch == '⊕'
    assert token.describe == '`⊕`'
    assert token.span == Span(3, 6)
    with pytest.raises(LexError):
        tokenize('◇')


@pytest.mark.parametrize('level', sorted(INFIX_LEVELS))
def test_custom_operators_associate_left_at_every_level(level):
    assert run_source(f'\\infix({level}) ⊕(a,b)=a-b\n10 ⊕ 3 ⊕ 2')[-1] == '= 5'


@pytest.mark.parametrize(('level', 'expression', 'expected'), [
    (11, '2 + 3 ⊕ 4*5', '= 25'),
    (12, '2 + 3 ⊕ 4*5', '= 37'),
    (12, '2 ⊕ 3x', '= 14'),
    (15, '2 ⊕ 3^2', '= 25'),
    (15, '2^3 ⊕ 2', '= 32'),
    (15, '-2 ⊕ 3', '= -5'),
    (15, '2 ⊕ -3', '= -1'),
    (11, '1..2 ⊕ 2', '= <range 1..4>'),
])
def test_precedence_interactions(level, expression, expected):
    assert run_source(f'x=4\n\\infix({level}) ⊕(a,b)=a+b\n{expression}')[-1] == expected


def test_mixed_implication_keeps_right_association():
    node = parse_program(r'\infix(4) \mix(a,b)=a+b' + '\n' + r'1 → 2 \mix 3')
    assert isinstance(node, Seq)
    assert isinstance(node.statements[-1].rhs, Call)


@pytest.mark.parametrize('expression', ['1 ⊕ 2 < 3', '1 < 2 ⊕ 3'])
def test_nonassociative_builtin_requires_parentheses(expression):
    with pytest.raises(ParseError, match='parenthesize'):
        parse_program(r'\infix(9) ⊕(a,b)=a+b' + '\n' + expression)


def test_pair_is_one_ordinary_function():
    source = r'''\infix(11) \blend, ⊕(a,b)=a+b
f = ⊕
f = \blend
\blend(2,3)
⊕(2,3)
\map(⊕(·,2), ⟨1,2⟩)
'''
    assert run_source(source)[1:] == [
        'f = <fn \\blend(a, b)>', 'true', '= 5', '= 5', '= ⟨3, 4⟩'
    ]


def test_recursion_and_local_bindings():
    source = r'''\infix(11) \repeat, ⊕(a,b)=b <= 0 ? 0 : a + (a ⊕ (b-1))
3 ⊕ 4
'''
    assert run_source(source)[-1] == '= 12'
    with pytest.raises(EvalError, match='not bound'):
        run_source(source + '\na')


def test_quote_reflection_and_tex_use_calls():
    source = r'''\infix(11) \blend, ⊕(a,b)=a+b
q=\expr(2 ⊕ 3)
\eval(q)
\eval(\reduce(q))
\tex(q)
\body(\blend)
'''
    outputs = run_source(source)
    assert outputs[2:4] == ['= 5', '= 5']
    assert 'blend' in outputs[4]
    node = parse_program(source).statements[1].value.body
    assert show(node) == '⊕(2, 3)'


@pytest.mark.parametrize('declaration', [
    r'\infix(2) ⊕(a,b)=a+b',
    r'\infix(7) ⊕(a,b)=a+b',
    r'\infix(16) ⊕(a,b)=a+b',
    r'\infix(11.0) ⊕(a,b)=a+b',
    r'\infix(-11) ⊕(a,b)=a+b',
    r'\infix(11) x(a,b)=a+b',
    r'\infix(11) +(a,b)=a+b',
    r'\infix(11) \sin(a,b)=a+b',
    r'\infix(11) \alias(a,b)=a+b',
    r'\infix(11) ⊕(a)=a',
    r'\infix(11) ⊕(a,a)=a',
    r'\infix(11) ⊕(a,b,c)=a',
    r'\infix(11) ⊕, ⊙(a,b)=a+b',
    r'\infix(11) \blend, x(a,b)=a+b',
    r'\infix(11) \blend, ⊕, ⊙(a,b)=a+b',
    r'f()=\infix(11) ⊕(a,b)=a+b',
    r'(\infix(11) ⊕(a,b)=a+b)',
])
def test_invalid_declarations_do_not_register(declaration):
    operators = {}
    with pytest.raises(ParseError):
        parse_program(declaration, operators=operators)
    assert operators == {}


def test_duplicate_spellings_are_rejected():
    operators = {}
    parse_program(r'\infix(11) \blend, ⊕(a,b)=a+b', operators=operators)
    for declaration in [r'\infix(12) \blend(a,b)=a+b', r'\infix(12) ⊕(a,b)=a+b']:
        with pytest.raises(ParseError, match='already declared'):
            parse_program(declaration, operators=operators)


def test_parse_failure_and_incomplete_input_are_atomic():
    operators = {}
    for source in [r'\infix(11) ⊕(a,b)=', r'\infix(11) ⊕(a,b)=a+b' + '\n(']:
        with pytest.raises(IncompleteInput):
            parse_program(source, operators=operators)
        assert operators == {}
    with pytest.raises(ParseError):
        parse_program(r'\infix(11) ⊕(a,b)=a+b' + '\n;;', operators=operators)
    assert operators == {}


def test_driver_session_and_runtime_failure():
    env, operators = {}, {}
    run_source(r'\infix(11) \blend, ⊕(a,b)=a+b', env, operators=operators)
    assert run_source('2 ⊕\n3', env, operators=operators) == ['= 5']
    with pytest.raises(EvalError, match='already bound'):
        run_source(r'\infix(11) \blend, ⊙(a,b)=a+b', env)
    with pytest.raises(EvalError):
        run_source(r'\infix(11) ⊙(a,b)=a+b' + '\n1/0', env, operators=operators)
    assert run_source('2 ⊙ 3', env, operators=operators) == ['= 5']
    with pytest.raises(EvalError, match='takes 2 arguments'):
        run_source(r'\blend(1)', env, operators=operators)


def test_undeclared_operator_diagnostic_span():
    with pytest.raises(ParseError, match='undeclared operator') as failure:
        compile_source('⊕(1,2)')
    assert failure.value.span == Span(0, 3)


def test_import_keeps_operator_syntax_local(tmp_path):
    (tmp_path / 'ops.ad').write_text(r'\infix(11) \blend, ⊕(a,b)=a+b' + '\n' + r'v=2 ⊕ 3')
    operators = {}
    assert run_source(r'\import("ops")' + '\n' + r'\blend(2,3)',
                      base_dir=str(tmp_path), operators=operators) == ['= 5']
    assert operators == {}
    with pytest.raises(ParseError, match='undeclared operator'):
        run_source(r'\import("ops")' + '\n⊕(2,3)', base_dir=str(tmp_path))


def test_alias_conflicts_and_operator_alias_directives_are_rejected():
    for source in [
        r'\alias \blend, β' + '\n' + r'\infix(11) \blend(a,b)=a+b',
        r'\infix(11) \blend(a,b)=a+b' + '\n' + r'\alias \blend, β',
        r'\infix(11) \blend(a,b)=a+b' + '\n' + r'\dual \blend, β(a,b)=a+b',
    ]:
        aliases, operators = {}, {}
        with pytest.raises(ParseError):
            parse_program(source, aliases, operators)
        assert aliases == operators == {}


def test_custom_operands_are_eager_and_builtin_logic_stays_lazy():
    assert run_source(r'\true ∨ (1/0)') == ['= true']
    assert run_source(r'\false ∧ (1/0)') == ['= false']
    with pytest.raises(EvalError, match='division by zero'):
        run_source(r'\infix(5) ⊕(a,b)=a' + '\n' + r'\true ⊕ (1/0)')


def test_quote_round_trip_and_reflected_custom_call():
    env, operators = {}, {}
    run_source(r'\infix(11) \blend, ⊕(a,b)=a+b' + '\n' + r'q=\expr(2 ⊕ 3)',
               env, operators=operators)
    assert run_source(show(env['q'].node), env, operators=operators) == ['= 5']
    assert run_source(r'f(x)=x ⊕ 2' + '\n' + r'\eval(\body(f), x=3)',
                      env, operators=operators)[-1] == '= 5'
    with pytest.raises(EvalError, match='positional arguments only'):
        run_source(r'\blend(b=3,a=2)', env, operators=operators)


def test_import_does_not_inherit_callers_operator_syntax(tmp_path):
    (tmp_path / 'bad.ad').write_text('v=1 ⊕ 2')
    env, operators = {}, {}
    run_source(r'\infix(11) ⊕(a,b)=a+b', env, operators=operators)
    with pytest.raises(EvalError, match='undeclared operator'):
        run_source(r'\import("bad")', env, base_dir=str(tmp_path), operators=operators)


def test_large_precedence_has_typed_diagnostic():
    with pytest.raises(ParseError, match='precedence must be'):
        parse_program('\\infix(' + '9' * 5000 + ') ⊕(a,b)=a+b')


def test_custom_sections_are_deferred():
    with pytest.raises(ParseError):
        parse_program(r'\infix(11) ⊕(a,b)=a+b' + '\n(2 ⊕)')
    with pytest.raises(EvalError):
        run_source(r'\infix(11) ⊕(a,b)=a+b' + '\n(⊕ 2)')
