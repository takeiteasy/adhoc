import math
from dataclasses import FrozenInstanceError

import pytest

from adhoc import graph as sampling, runtime
from adhoc.driver import compile_source, run_source
from adhoc.expression import show
from adhoc.graph import GraphValue
from adhoc.parser import ParseError, parse_program
from adhoc.span import Span
from adhoc.syntax import Graph, free_names


def graph(source, env=None):
    env = {} if env is None else env
    run_source('g = ' + source, env)
    return env['g']


def sample(fn, lo=0.0, hi=1.0, **options):
    return sampling.sample(fn, lo, hi, axis='x', axis_spelling='x', label='f', **options)


def assert_breaks_disconnect(value):
    for segment in value.segments:
        for left, right in zip(segment, segment[1:]):
            assert not any(left[0] < gap.end and right[0] > gap.start for gap in value.breaks)


@pytest.mark.parametrize('source', [
    r'\graph(x^2, x=-1..1)',
    r'\graph((x ↦ x^2), x=-1..1)',
    r'\graph(f, x=-1..1)',
    r'\graph(f(x), x=-1..1)',
])
def test_callable_and_expression_sampling(source):
    env = {}
    run_source('f(x) = x^2', env)
    value = graph(source, env)
    assert isinstance(value, GraphValue)
    assert value.complete
    assert value.bounds == (-1.0, 1.0)
    assert value.samples[0] == (-1.0, 1.0)
    assert value.samples[-1] == (1.0, 1.0)
    assert all(y == pytest.approx(x*x) for x, y in value.samples)
    assert len(value.segments) == 1
    assert value.evaluations == len(value.samples)


def test_existing_axis_binding_is_shadowed_only_in_samples():
    env = {}
    run_source('x = 7; a = 2', env)
    value = graph(r'\graph(a*x, x=0..x)', env)
    assert value.samples[-1] == (7.0, 14.0)
    assert env['x'] == 7
    assert set(env) == {'x', 'a', 'g'}


def test_bounds_options_and_callable_are_evaluated_once():
    calls = []
    def factory():
        calls.append('factory')
        return runtime.PRELUDE['sin']
    def bound():
        calls.append('bound')
        return 1
    def tolerance():
        calls.append('tol')
        return 0.001
    def budget():
        calls.append('budget')
        return 129
    value = graph(r'\graph(f(), x=0..b(), \tol=t(), \maxpoints=m())',
                  {'f': factory, 'b': bound, 't': tolerance, 'm': budget})
    assert calls == ['factory', 'bound', 'tol', 'budget']
    assert value.complete


@pytest.mark.parametrize('target, expected', [
    (r'(x ↦ x^2)', False),
    (r'(y ↦ x*y)', True),
    (r'\sum(x=1..3) x', False),
    (r'\sum(y=1..3) x*y', True),
    (r'\sum(x=1..x) x', True),
    (r'\diff(x=1) x^2', False),
    (r'\int(x=0..1) x', False),
    (r'\lim(x=0) x', False),
    (r'\expr(x)', False),
    (r'(x = 2; x^2)', False),
    (r'(y = x; y^2)', True),
    (r'{x | x ∈ 1..3}', False),
    (r'{x*y | y ∈ 1..3}', True),
    (r'\graph(x^2, x=0..1)', False),
])
def test_axis_inference_respects_lexical_scope(target, expected):
    node = parse_program(r'\graph(' + target + ', x=0..1)')
    assert isinstance(node, Graph)
    assert node.expression_modes == (expected,)
    assert ('x' in free_names(node.targets[0])) is expected


@pytest.mark.parametrize('target', [r"f'", r'f ∘ f', r'\sin', r'f(·)'])
def test_higher_order_callables(target):
    env = {}
    run_source('f(x) = x^2', env)
    value = graph(r'\graph(' + target + ', x=1..2)', env)
    assert value.complete
    assert all(y is not None for _, y in value.samples)


def test_aliases_and_subscript_axis_keep_source_spelling():
    aliases = {}
    env = {}
    run_source(r'\alias \graph, γ; g = γ(x₁^2, x₁=0..1)', env, aliases=aliases)
    value = env['g']
    assert value.axis_spelling == 'x₁'
    assert value.samples[-1] == (1.0, 1.0)
    assert show(parse_program(r'\graph(x₁^2, x₁=0..1)')).startswith(r'\graph(')


def test_reversed_stored_and_equal_ranges():
    env = {}
    run_source('r = 2..-2', env)
    value = graph(r'\graph(x, x=r)', env)
    assert value.bounds == (-2.0, 2.0)
    seen = []
    value = graph(r'\graph(f, x=2..2)', {'f': lambda x: seen.append(x) or x*x})
    assert seen == [2.0]
    assert value.samples == ((2.0, 4.0),)
    assert value.complete


def test_adaptive_curvature_refines_and_tolerance_controls_detail():
    coarse = sample(lambda x: math.exp(-1000*(x-0.4)**2), tolerance=0.01)
    fine = sample(lambda x: math.exp(-1000*(x-0.4)**2), tolerance=0.0001)
    assert coarse.complete and fine.complete
    assert fine.evaluations > coarse.evaluations > 129
    spacing_near_peak = [b[0]-a[0] for a, b in zip(fine.samples, fine.samples[1:])
                         if 0.35 < a[0] < 0.45]
    spacing_far_away = [b[0]-a[0] for a, b in zip(fine.samples, fine.samples[1:]) if a[0] < 0.1]
    assert min(spacing_near_peak) < min(spacing_far_away)


def test_quarter_points_detect_midpoint_aliasing():
    value = sample(lambda x: math.sin(64*math.pi*x), tolerance=0.01)
    assert value.evaluations > 129
    assert max(y for _, y in value.samples) > 0.9


def test_sampling_is_deterministic_cached_and_within_budget():
    seen = []
    def fn(x):
        seen.append(x)
        return math.sin(200*x)
    first = sample(fn, maxpoints=257)
    second = sample(lambda x: math.sin(200*x), maxpoints=257)
    assert first == second
    assert len(seen) == len(set(seen)) == first.evaluations <= 257
    assert not first.complete
    assert 'budget' in first.stopping_reasons
    assert_breaks_disconnect(first)


@pytest.mark.parametrize('source', [
    r'\graph(1/x, x=-1..1)',
    r'\graph(\ln(x), x=0..1)',
    r'\graph(\sqrt(x), x=-1..1)',
    r'\graph(x < 0 ? -1 : 1, x=-1..1)',
    r'\graph(1/(x-0.3), x=0..1)',
])
def test_discontinuities_and_invalid_endpoints_are_disconnected(source):
    value = graph(source)
    assert value.breaks
    assert any(y is not None for _, y in value.samples)
    assert_breaks_disconnect(value)


@pytest.mark.parametrize('target', [r'\sqrt(-1)', r'\nan', r'\inf', r'\ln(0)', '1/0'])
def test_wholly_invalid_domains_return_empty_segments(target):
    value = graph(r'\graph((x ↦ ' + target + '), x=0..1)')
    assert value.complete
    assert value.segments == ()
    assert all(y is None for _, y in value.samples)
    assert [(gap.start, gap.end, gap.reason) for gap in value.breaks] == [(0.0, 1.0, 'invalid')]


def test_invalid_equal_bounds_return_a_gap():
    value = graph(r'\graph(1/x, x=0..0)')
    assert value.samples == ((0.0, None),)
    assert value.complete and not value.segments


def test_depth_and_float_precision_limits(monkeypatch):
    monkeypatch.setattr(sampling, 'MAX_DEPTH', 0)
    value = sample(lambda x: x*x, tolerance=1e-12)
    assert not value.complete
    assert value.stopping_reasons == ('depth',)
    assert_breaks_disconnect(value)
    value = sample(lambda x: x, 1.0, math.nextafter(1.0, math.inf))
    assert not value.complete
    assert value.stopping_reasons == ('precision',)
    assert value.evaluations == 2


def test_huge_finite_coordinates_and_values_do_not_overflow_sampler():
    value = sample(lambda x: x, -1e308, 1e308)
    assert value.complete
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in value.samples)
    assert value.samples[0] == (-1e308, -1e308)
    assert value.samples[-1] == (1e308, 1e308)


@pytest.mark.parametrize('source', [
    r'\graph(x, x=0..)', r'\graph(x, x=-\inf..1)',
    r'\graph(x, x=(0,0.1..1))', r'\graph(x, x=\nan..1)',
    r'\graph(x, x=0..i)', r'\graph(x, x=0\metre..1\metre)',
    r'\graph(x, x=\true..1)', r'\graph(x, x=0..1, \tol=0)',
    r'\graph(x, x=0..1, \tol=-1)', r'\graph(x, x=0..1, \tol=\inf)',
    r'\graph(x, x=0..1, \tol=\nan)', r'\graph(x, x=0..1, \tol=\true)',
    r'\graph(x, x=0..1, \tol=i)', r'\graph(x, x=0..1, \tol=1\metre)',
    r'\graph(x, x=0..1, \maxpoints=32)', r'\graph(x, x=0..1, \maxpoints=33.)',
    r'\graph(x, x=0..1, \maxpoints=\true)', r'\graph(x, x=0..1, \maxpoints=100.5)',
    r'\graph(3, x=0..1)', r'\graph((x ↦ [x]), x=0..1)',
    r'\graph((x ↦ "bad"), x=0..1)', r'\graph((x ↦ \true), x=0..1)',
    r'\graph((x ↦ x\metre), x=0..1)',
])
def test_invalid_ranges_options_and_results_fail(source):
    with pytest.raises(runtime.EvalError):
        graph(source)


@pytest.mark.parametrize('source', [
    r'\graph()', r'\graph(x)', r'\graph(x, x=0..1, y=0..1)',
    r'\graph(x, x=0..1, \mode="real")', r'\graph(x, x=0..1, \tol=1, \tol=2)',
    r'\graph(·, x=0..1)', r'\graph(x, \axis=0..1)',
])
def test_invalid_call_shapes_are_parse_errors(source):
    with pytest.raises(ParseError):
        parse_program(source)


def test_small_budget_preserves_unchecked_intervals_as_breaks():
    value = graph(r'\graph(x, x=0..1, \maxpoints=33)')
    assert value.evaluations == 33
    assert not value.complete
    assert value.stopping_reasons == ('budget',)
    assert [(gap.start, gap.end) for gap in value.breaks] == [(0.0, 1.0)]
    assert all(len(segment) == 1 for segment in value.segments)


@pytest.mark.parametrize('source', [r'\graph(y+x, x=0..1)', r'\graph(f, x=0..1)'])
def test_unbound_names_and_arity_errors_keep_spans(source):
    env = {}
    run_source('f(x,y) = x+y', env)
    with pytest.raises(runtime.EvalError) as raised:
        graph(source, env)
    assert raised.value.span is not None
    assert not raised.value.domain


@pytest.mark.parametrize('exception', [ValueError, TypeError, RuntimeError])
def test_unexpected_python_errors_propagate(exception):
    def fn(x):
        raise exception('programming error')
    with pytest.raises(runtime.EvalError, match='programming error') as raised:
        graph(r'\graph(f, x=0..1)', {'f': fn})
    assert not raised.value.domain


def test_python_division_by_zero_is_a_gap():
    value = graph(r'\graph(f, x=-1..1)', {'f': lambda x: 1/x})
    assert (0.0, None) in value.samples
    assert_breaks_disconnect(value)


def test_domain_categories_preserve_diagnostics():
    source = 'α = 1; 1/0'
    with pytest.raises(runtime.EvalError, match='division by zero') as raised:
        run_source(source)
    assert raised.value.domain
    assert raised.value.span == Span(len('α = 1; '.encode()), len(source.encode()))
    with pytest.raises(runtime.EvalError, match='ValueError') as raised:
        run_source(r'\ln(0.)')
    assert raised.value.domain


@pytest.mark.parametrize('source', [
    r'\graph(x^2, x=0..1)',
    r'\graph(\sin, t=0..\pi, \tol=0.0001, \maxpoints=1000)',
])
def test_quote_roundtrip_eval_and_tex(source):
    shown = show(parse_program(source))
    assert show(parse_program(shown)) == shown
    assert run_source(r'\tex(\expr(' + source + '))')[0].startswith('= "')
    value = graph(r'\eval(\expr(' + source + '))')
    assert isinstance(value, GraphValue)


def test_tex_masks_axis_but_resolves_outer_bounds():
    output = run_source(r'x = 9; a = 2; \tex(\expr(\graph(x^2, x=0..a)))')[-1]
    assert 'x^{2}' in output
    assert '9^{2}' not in output
    assert '2' in output


def test_beta_reduction_preserves_graph_binder_and_avoids_capture():
    env = {}
    run_source(r'q = \reduce(\expr((y ↦ \graph(x+y, x=0..1))(x)))', env)
    quoted = env['q']
    shown = show(quoted.node)
    assert show(parse_program(shown)) == shown
    value = graph(r'\eval(q, x=3)', env)
    assert value.samples[0][1] == 3.0
    assert value.samples[-1][1] == 4.0


def test_graph_value_is_immutable_and_preserved_by_internal_calls():
    env = {}
    value = graph(r'\graph(x, x=0..1)', env)
    with pytest.raises(FrozenInstanceError):
        value.complete = False
    run_source('f(a) = a\nh = f(g)', env)
    assert env['h'] is value
    assert run_source('g', env)[0] == '= <graph x=0.0..1.0; 129 samples; 0 gaps; complete>'


def test_compiler_lowers_to_span_carrying_engine_call():
    compiled = compile_source(r'\graph(x^2, x=0..1)')
    assert '_e.graphs(' in compiled.source
    assert len(compiled.definitions) == 1
    assert compiled.spans[0] == Span(0, len(r'\graph(x^2, x=0..1)'))


@pytest.mark.parametrize('source, binding, expected', [
    (r"\reduce(\expr((y ↦ \graph(x₁+y, x₁=0..1))(x₁)))", 'x₁ = 3', (3.0, 4.0)),
    (r"\reduce(\expr((y ↦ \graph(y, x=0..1))(x)))", 'x(t) = 2t', (0.0, 2.0)),
    (r"\reduce(\expr(\graph((y ↦ 3)(x), x=0..1)))", '', (3.0, 3.0)),
])
def test_reduced_graph_roundtrip_preserves_inferred_mode(source, binding, expected):
    env = {}
    if binding:
        run_source(binding, env)
    run_source('q = ' + source, env)
    shown = show(env['q'].node)
    original = graph(r'\eval(q)', env)
    env.pop('g')
    reparsed = graph(shown, env)
    assert original.samples == reparsed.samples
    assert (original.samples[0][1], original.samples[-1][1]) == expected


def test_graph_demo_runs_through_cli():
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run([sys.executable, '-m', 'adhoc', 'run',
                             str(Path(__file__).resolve().parents[1] / 'demos' / 'graph.ad')],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'incomplete: budget' in result.stdout
    assert 'incomplete: depth' in result.stdout
    assert 'ERROR' not in result.stdout


def test_multiple_targets_keep_independent_samples_and_budgets():
    from adhoc.graph import GraphCollectionValue

    calls = []
    env = {'f': lambda x: calls.append(x) or x * x}
    value = graph(r'\graph(f, 1/x, x=-1..1, \maxpoints=129)', env)
    assert isinstance(value, GraphCollectionValue)
    first, second = value.graphs
    assert first.evaluations == len(calls) == 129
    assert second.evaluations <= 129
    assert first.bounds == second.bounds == (-1.0, 1.0)
    assert not first.breaks
    assert second.breaks
    assert len(set(calls)) == len(calls)
    assert_breaks_disconnect(second)
    with pytest.raises(FrozenInstanceError):
        value.graphs = ()
    assert run_source('g', env) == ['= <graphs; 2 curves>']


def test_multiple_targets_evaluate_shared_inputs_once_before_sampling():
    seen = []
    env = {
        'f': lambda: seen.append('f') or env['u'],
        'h': lambda: seen.append('h') or env['v'],
        'p': lambda x: seen.append('probe') or x,
        'b': lambda: seen.append('bound') or 1,
        't': lambda: seen.append('tol') or 0.001,
        'm': lambda: seen.append('maxpoints') or 129,
    }
    run_source('u(x) = p(x)', env)
    run_source('v(x) = x*x', env)
    value = graph(r'\graph(f(), h(), x=0..b(), \tol=t(), \maxpoints=m())', env)
    assert seen[:5] == ['f', 'h', 'bound', 'tol', 'maxpoints']
    assert all(seen.count(name) == 1 for name in ('f', 'h', 'bound', 'tol', 'maxpoints'))
    assert len(value.graphs) == 2


def test_multi_graph_scope_alias_quote_and_tex():
    env, aliases = {}, {}
    run_source(r'\alias \graph, γ; x = 99; a = 2; g = γ(x+a, (t ↦ t^2), x=0..1)',
               env, aliases=aliases)
    assert env['g'].graphs[0].samples[0] == (0.0, 2.0)
    assert env['g'].graphs[1].samples[-1] == (1.0, 1.0)
    assert env['x'] == 99
    source = r'\graph(x+a, \sin, x=0..1)'
    assert free_names(parse_program(source)) == {'a', 'sin'}
    value = graph(source, env)
    reparsed = graph(show(parse_program(source)), env)
    assert reparsed == value
    assert graph(r'\eval(\expr(' + source + '))', env) == value
    tex = run_source(r'\tex(\expr(' + source + '))', env)[-1]
    assert 'graph' in tex and 'sin' in tex


@pytest.mark.parametrize('source, binding', [
    (r'\reduce(\expr((y ↦ \graph(x+y, \sin, x=0..1))(x)))', 'x = 3'),
    (r'\reduce(\expr((y ↦ \graph(y, x^2, x=0..1))(x)))', 'x(t) = 2t'),
    (r'\reduce(\expr(\graph((y ↦ 3)(x), x^2, x=0..1)))', ''),
])
def test_multi_graph_reduction_preserves_each_target_mode(source, binding):
    env = {}
    run_source('q = ' + source, env)
    if binding:
        run_source(binding, env)
    original = graph(r'\eval(q)', env)
    reparsed = graph(show(env['q'].node), env)
    assert original == reparsed
