import pytest

from adhoc.driver import run_source
from adhoc.runtime import EvalError
from adhoc.tensor import ArrayValue


def ev(source, env=None):
    return run_source(source, {} if env is None else env)[-1]


def test_vector_function_jacobian_and_numeric_algebra():
    source = "f(x,y)=⟨x^2 y,x+y⟩\nj=\\jacobian(f)\n"
    assert ev(source + r'\tensor(\eval(j,x=2,y=3))') == '= [12, 4; 1, 1]'
    assert ev(source + r'\det(\tensor(\eval(j,x=2,y=3)))') == '= 8'


def test_jacobian_quotes_union_order_and_constant_outputs():
    assert ev(r'\tensor(\eval(\jacobian(⟨`(y^2),`(x y),`(7)⟩),x=2,y=3))') == '= [0, 6; 3, 2; 0, 0]'
    assert ev(r'\tensor(\eval(\jacobian(⟨`(x y)⟩,⟨`(y),`(x),`(z)⟩),x=2,y=3))') == '= [2, 3, 0;]'


def test_function_parameters_and_captured_nested_functions():
    source = 'a=3\ng(t)=a t^2\nf(y,x)=⟨g(x),y⟩\n'
    assert ev(source + r'\tensor(\eval(\jacobian(f),x=2,y=4))') == '= [0, 12; 1, 0]'
    assert ev('f(y,x)=x y\ng(y,x)=x+y\n' +
              r'\tensor(\eval(\jacobian(⟨f,g⟩),x=2,y=3))') == '= [2, 3; 1, 1]'


def test_mixed_inputs_require_names():
    source = 'f(x)=x^2\n'
    with pytest.raises(EvalError, match='explicit unknowns'):
        ev(source + r'\jacobian(⟨f,`(x)⟩)')
    assert ev(source + r'\tensor(\eval(\jacobian(⟨f,`(x)⟩,⟨`(x)⟩),x=3))') == '= [6; 1]'
    with pytest.raises(EvalError, match='explicit unknowns'):
        ev('f(x,y)=x+y\ng(y,x)=x y\n' + r'\jacobian(⟨f,g⟩)')


def test_hessian_order_symmetry_and_constant():
    assert ev(r'\tensor(\eval(\hessian(`(x^2 y+3y^2)),x=2,y=3))') == '= [6, 4; 4, 6]'
    assert ev(r'\tensor(\eval(\hessian(`(x^2 y),⟨`(y),`(x)⟩),x=2,y=3))') == '= [0, 4; 4, 6]'
    assert ev(r'\tensor(\eval(\hessian(`(7),⟨`(x)⟩),x=1))') == '= [0;]'
    assert ev('a=3\nf(x)=a x^3\n' + r'\tensor(\eval(\hessian(f),x=2))') == '= [36;]'


def test_dimensions_survive_each_derivative_and_evaluation():
    assert ev(r'\eval(\hessian(`(x^3),\dimensions=⟨⟨`(x),\metre⟩⟩),x=2\metre)') == '= ⟨⟨12*\\metre⟩⟩'
    assert ev('f(x)=⟨x^2,x⟩\n' + r'\eval(\jacobian(f,\dimensions=⟨⟨`(x),\metre⟩⟩),x=2\metre)') == '= ⟨⟨4*\\metre⟩, ⟨1⟩⟩'
    with pytest.raises(EvalError, match='conflicting dimensions'):
        ev(r'\eval(\hessian(`(x^3),\dimensions=⟨⟨`(x),\metre⟩⟩),x=2)')


@pytest.mark.parametrize('source, message', [
    (r'\jacobian(⟨⟩)', 'at least one output'),
    (r'\jacobian(⟨`(1)⟩)', 'no unknown'),
    (r'\hessian(`(1))', 'no unknown'),
    (r'\hessian(`(x),⟨⟩)', 'at least one unknown'),
    (r'\hessian(`(x),⟨`(x),`(x)⟩)', 'distinct'),
    (r'\jacobian(⟨`(x)⟩,`(x))', 'array of quoted names'),
    (r'\jacobian(⟨3⟩)', 'expression quote'),
    (r'\hessian(`(x=1))', 'equation'),
    (r'\jacobian(⟨⟨`(x)⟩⟩)', 'expression quote'),
    ('f(x)=x\n\\jacobian(f)', 'array-bodied'),
    ('f(x)=⟨⟨x⟩⟩\n\\jacobian(f)', 'arraylit'),
    ('f(x)=(a=x; ⟨a⟩)\n\\jacobian(f)', 'several statements'),
    ('f(x)=⟨f(x)⟩\n\\jacobian(f)', 'recursive'),
])
def test_calculus_errors(source, message):
    with pytest.raises(EvalError, match=message):
        ev(source)


def test_recursive_eval_isolates_statement_leaves_and_keeps_shape():
    env = {}
    assert ev(r'\eval(⟨`((a=1; a)),⟨`(x+1)⟩⟩,x=4)', env) == '= ⟨1, ⟨5⟩⟩'
    assert env == {}
    assert ev(r'\eval(⟨⟩)') == '= ⟨⟩'
    with pytest.raises(EvalError, match='every array leaf'):
        ev(r'\eval(⟨`(x),3⟩,x=1)')
    with pytest.raises(EvalError, match='protected'):
        ev(r'\eval(⟨`(x)⟩,\pi=1)')


def test_recursive_eval_retains_quote_source_and_byte_span():
    env = {}
    source = 'q=⟨`(α+1),⟨`(1/x)⟩⟩'
    run_source(source, env)
    with pytest.raises(EvalError) as failure:
        ev(r'\eval(q,α=1,x=0)', env)
    assert failure.value.source == source
    start = len(source[:source.index('1/x')].encode())
    assert failure.value.span.start == start
    assert failure.value.span.end == start + 3


@pytest.mark.parametrize('source, message', [
    (r'\tensor(1)', 'needs an array'),
    (r'\tensor(⟨⟩)', 'empty axis'),
    (r'\tensor(⟨⟨1⟩,⟨⟩⟩)', 'empty axis'),
    (r'\tensor(⟨⟨1⟩,⟨2,3⟩⟩)', 'different shapes'),
    (r'\tensor(⟨1,⟨2⟩⟩)', 'cannot mix'),
    (r'\tensor(⟨`(x)⟩)', 'numbers'),
    (r'\tensor(⟨\true⟩)', 'booleans'),
    (r'\tensor(⟨1\metre,1\second⟩)', 'dimensions'),
])
def test_tensor_conversion_errors(source, message):
    with pytest.raises(EvalError, match=message):
        ev(source)


def test_tensor_exact_numeric_and_higher_order_values():
    assert ev(r'\tensor(⟨1/2,\pi,1+i⟩)') == '= [1/2, 3.14159265358979..., 1+i]'
    assert ev(r'\tensor(⟨⟨⟨1,2⟩⟩,⟨⟨3,4⟩⟩⟩)') == '= [[1, 2;], [3, 4;]]'
    assert ev(r'\tensor(⟨1\metre,2\metre⟩)') == '= [1*\\metre, 2*\\metre]'


def test_original_gradient_remains_array_without_arithmetic():
    env = {}
    ev(r'g=\grad(`(x^2 y))', env)
    assert isinstance(env['g'], ArrayValue)
    with pytest.raises(EvalError, match='arrays do not support arithmetic'):
        ev('g+g', env)


def test_symbolic_calculus_demo():
    from pathlib import Path
    output = run_source(Path('demos/symbolic-calculus.ad').read_text(), {})
    assert output[-4:] == ['= 8',
                          r'h = ⟨⟨\expr((2 * y)), \expr((2 * x))⟩, ⟨\expr((2 * x)), \expr(6)⟩⟩',
                          '= [6, 4; 4, 6]', '= [12, 4]']


@pytest.mark.parametrize('operation', ['jacobian', 'hessian'])
def test_matrix_derivative_timeout_covers_expansion(operation, worker_patch, monkeypatch):
    from worker_helpers import spin
    worker_patch('adhoc.rewrite', '_bridge_function', spin)
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', '0.1')
    body = '⟨x^2⟩' if operation == 'jacobian' else 'x^2'
    with pytest.raises(EvalError, match='took longer than 0.1s'):
        ev(f'f(x)={body}\n\\{operation}(f)')
