from dataclasses import FrozenInstanceError
import math

import matplotlib
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
import pytest
from PIL import Image

from adhoc.driver import run_source
from adhoc.graph import GraphCollectionValue
from adhoc.plot import SeriesValue, draw, plot, series
from adhoc.runtime import EvalError
from adhoc.span import Span
from adhoc.tensor import ArrayValue


def evaluate(source):
    env = {}
    run_source('v = ' + source, env)
    return env['v']


def axes_for(*values, **options):
    axes = Figure().subplots()
    draw(tuple(values), axes, **options)
    return axes


def test_bundle_and_separate_graphs_flatten_in_order(tmp_path):
    bundle = evaluate(r'\graph(x, 1/x, x=-1..1)')
    other = evaluate(r'\graph(x^2, x=-2..2)')
    assert isinstance(bundle, GraphCollectionValue)
    axes = axes_for(bundle, other, legend=True)
    colors = [to_rgba(line.get_color()) for line in axes.lines]
    count = len(bundle.graphs[0].segments)
    gaps = len(bundle.graphs[1].segments)
    assert len(set(colors[:count])) == 1
    assert len(set(colors[count:count+gaps])) == 1
    assert colors[0] != colors[count] != colors[-1]
    assert axes.get_xlim() == (-2, 2)
    assert axes.get_title() == ''
    assert len(axes.get_legend().texts) == 3
    assert plot(bundle, backend='file', path=str(tmp_path / 'one.svg')) is bundle
    result = plot(bundle, other, backend='file', path=str(tmp_path / 'two.svg'))
    assert isinstance(result, ArrayValue)
    assert result.items == (bundle, other)


def test_series_overrides_plot_defaults_and_is_immutable():
    value = evaluate(r'\series(\graph(1/x, x=-1..1), \type="step", \color="red",'
                     r' \where="post", \label="$literal$")')
    assert isinstance(value, SeriesValue)
    with pytest.raises(FrozenInstanceError):
        value.options = ()
    axes = axes_for(value, type='scatter', color='blue', legend=True)
    assert not axes.collections
    assert all(line.get_drawstyle() == 'steps-post' for line in axes.lines)
    assert all(to_rgba(line.get_color()) == to_rgba('red') for line in axes.lines)
    assert [text.get_text() for text in axes.get_legend().texts] == ['$literal$']
    assert not axes.get_legend().texts[0].get_parse_math()


@pytest.mark.parametrize('kind', ['line', 'scatter', 'step'])
def test_sampled_plot_types_preserve_gaps_and_singletons(kind):
    graph = evaluate(r'\graph(1/x, x=-1..1)')
    axes = axes_for(graph, type=kind)
    if kind == 'scatter':
        assert len(axes.collections) == len(graph.segments)
        for artist, segment in zip(axes.collections, graph.segments):
            assert artist.get_offsets().tolist() == [list(pair) for pair in segment]
    else:
        assert len(axes.lines) == len(graph.segments)
        for artist, segment in zip(axes.lines, graph.segments):
            assert list(zip(*artist.get_data())) == list(segment)
    point = evaluate(r'\graph(x, x=2..2)')
    singleton = axes_for(point, type=kind)
    if kind != 'scatter':
        assert singleton.lines[0].get_marker() == 'o'


def test_explicit_series_and_exact_numbers():
    value = evaluate(r'\series([0,1/2,1], [\sqrt(2),2,3], \marker="o", \linewidth=1/2)')
    axes = axes_for(value)
    assert axes.lines[0].get_xdata().tolist() == [0, 0.5, 1]
    assert axes.lines[0].get_ydata()[0] == pytest.approx(math.sqrt(2))
    assert axes.lines[0].get_linewidth() == 0.5
    assert axes.lines[0].get_marker() == 'o'
    scatter = axes_for(value.graph or series([0,1], [2,3]), type='scatter', markersize=4)
    assert scatter.collections[0].get_sizes().tolist() == [16]


def test_categorical_bars_align_and_group():
    first = evaluate(r'\series(\arr("B","A"), [2,3], \type="bar")')
    second = evaluate(r'\series(\arr("A","C"), [5,7], \type="bar")')
    axes = axes_for(first, second, legend=True)
    assert [tick.get_text() for tick in axes.get_xticklabels()] == ['B', 'A', 'C']
    centers = [patch.get_x() + patch.get_width()/2 for patch in axes.patches]
    assert centers == pytest.approx([-0.2, 0.8, 1.2, 2.2])
    assert [patch.get_height() for patch in axes.patches] == [2,3,5,7]
    assert all(patch.get_width() == pytest.approx(0.4) for patch in axes.patches)
    assert len(axes.get_legend().texts) == 2


def test_numeric_bars_are_grouped_and_do_not_clip():
    first = series([0,1], [2,3], type='bar', width=0.6)
    second = series([0,1], [4,5], type='bar', width=0.6)
    axes = axes_for(first, second)
    assert [p.get_x() + p.get_width()/2 for p in axes.patches] == pytest.approx([-0.15,0.85,0.15,1.15])
    assert axes.get_xlim()[0] < -0.3 and axes.get_xlim()[1] > 1.3
    graph = evaluate(r'\graph(x, x=-2..2)')
    combined = axes_for(graph, series([5], [3], type='bar'))
    assert combined.get_xlim()[0] <= -2
    assert combined.get_xlim()[1] > 5.4


def test_histograms_share_edges_density_and_opacity():
    first = series([0,1,2], type='hist', bins=2, density=True, alpha=0.5)
    second = series([3,4], type='hist', bins=2, density=True)
    axes = axes_for(first, second)
    assert [p.get_x() for p in axes.patches] == pytest.approx([0,2,0,2])
    for patches in (axes.patches[:2], axes.patches[2:]):
        assert sum(p.get_height()*p.get_width() for p in patches) == pytest.approx(1)
    assert axes.patches[0].get_alpha() == 0.5
    assert axes.patches[2].get_alpha() is None
    explicit = series([0,1,2,3], type='hist', bins=[0,1,3])
    edges = axes_for(explicit)
    assert [p.get_width() for p in edges.patches] == [1,2]
    assert [p.get_height() for p in edges.patches] == [1,3]


def test_figure_controls_and_png_dimensions(tmp_path):
    path = tmp_path / 'styled.png'
    env = {'p': str(path)}
    run_source(r'g = \graph(x^2, x=1..10); v = \plot(g, \backend="file", \path=p,'
               r' \figsize=[4,3], \dpi=80, \title="$plain$", \xlabel="Time",'
               r' \ylabel="Value", \grid=\true, \xscale="log", \yscale="log",'
               r' \xlim=[10,1], \ylim=[1,100])', env)
    assert env['v'] is env['g']
    with Image.open(path) as image:
        assert image.size == (320,240)
    axes = axes_for(env['g'], title='$plain$', xlabel='Time', ylabel='Value', grid=True,
                    xscale='log', yscale='log', xlim=[10,1], ylim=[1,100])
    assert axes.get_xlim() == (10,1)
    assert axes.get_ylim() == (1,100)
    assert axes.get_xscale() == axes.get_yscale() == 'log'
    assert axes.get_xlabel() == 'Time' and axes.get_ylabel() == 'Value'
    assert axes.get_title() == '$plain$' and not axes.title.get_parse_math()
    assert any(line.get_visible() for line in axes.get_xgridlines())


def test_axis_names_require_override():
    first = evaluate(r'\graph(x, x=0..1)')
    second = evaluate(r'\graph(t^2, t=0..2)')
    with pytest.raises(ValueError, match='xlabel'):
        axes_for(first, second)
    assert axes_for(first, second, xlabel='Time').get_xlabel() == 'Time'


@pytest.mark.parametrize('source', [
    r'\series([0], [1,2])', r'\series([0], \arr(\true))', r'\series([0], [i])',
    r'\series([0], [\inf])', r'\series([0], [1\metre])', r'\series([[0,1]], [2])',
    r'\series(\arr(), \arr(), \type="bar")',
    r'\series(\arr("A","A"), [1,2], \type="bar")',
    r'\series(\arr("A"), [1], \type="line")', r'\series(\arr("A",2), [1,2], \type="bar")',
    r'\series([1,2])', r'\series([1,2], [3,4], \type="hist")',
    r'\series(\graph(x, x=0..1), \type="bar")',
    r'\series([1,2], \type="hist", \bins=0)',
    r'\series([1,2], \type="hist", \bins=2.)',
    r'\series([1,2], \type="hist", \bins=[0,0,2])',
    r'\series([1,2], \type="hist", \density=1)',
    r'\series([0], [1], \type="scatter", \linestyle="--")',
    r'\series([0], [1], \unknown=2)',
])
def test_invalid_series_have_source_spans(source):
    with pytest.raises(EvalError) as error:
        run_source(source)
    assert error.value.span == Span(0, len(source.encode()))


@pytest.mark.parametrize('options', [
    {'type': 'pie'}, {'figsize': [0,3]}, {'dpi': 0}, {'alpha': 2}, {'legend': 1},
    {'grid': 'yes'}, {'title': 1}, {'linewidth': -1}, {'markersize': math.inf},
    {'xlim': [1,1]}, {'ylim': [1]}, {'xscale': 'symlog'}, {'xscale': 'log', 'xlim': [-1,1]},
    {'color': 'invalid-color'}, {'marker': 'invalid-marker'}, {'linestyle': 'invalid-style'},
    {'type': 'step', 'where': 'invalid'}, {'type': 'line', 'width': 1},
])
def test_invalid_plot_options_do_not_create_files(tmp_path, options):
    path = tmp_path / 'invalid.svg'
    graph = evaluate(r'\graph(x, x=0..1)')
    with pytest.raises((TypeError, ValueError)):
        plot(graph, backend='file', path=str(path), **options)
    assert not path.exists()


def test_incompatible_series_and_histograms_are_rejected(tmp_path):
    category = series(['A'], [1], type='bar')
    numeric = series([0], [1], type='bar')
    with pytest.raises(ValueError, match='categorical'):
        axes_for(category, numeric)
    with pytest.raises(ValueError, match='log'):
        axes_for(category, xscale='log')
    with pytest.raises(ValueError, match='matching bins'):
        axes_for(series([1,2], type='hist', bins=2), series([3,4], type='hist', bins=3))
    with pytest.raises(ValueError, match='inside the bin edges'):
        plot(series([3,4], type='hist', bins=[0,1], density=True), backend='file',
             path=str(tmp_path / 'density.svg'))
    assert not (tmp_path / 'density.svg').exists()


def test_matplotlib_defaults_are_scoped(tmp_path):
    value = series([1,2], [2,3], type='step')
    with matplotlib.rc_context({'figure.figsize': [7,4], 'figure.dpi': 90, 'axes.grid': True}):
        before = dict(matplotlib.rcParams)
        axes = axes_for(value)
        assert axes.lines[0].get_drawstyle() == 'steps-pre'
        assert axes.get_legend() is None
        assert any(line.get_visible() for line in axes.get_xgridlines())
        plot(value, backend='file', path=str(tmp_path / 'defaults.png'), grid=False, dpi=50)
        assert dict(matplotlib.rcParams) == before
        with Image.open(tmp_path / 'defaults.png') as image:
            assert image.size == (350,200)


def test_styled_window_uses_common_drawing_and_closes(monkeypatch):
    from matplotlib import pyplot

    figure = Figure()
    axes = figure.subplots()
    figure.canvas.required_interactive_framework = 'tk'
    created, shown, closed = [], [], []

    def create(**kwargs):
        created.append(kwargs)
        return figure, axes

    def show(*, block):
        shown.append(block)
        assert len(axes.lines) == 1
        assert len(axes.collections) == 1
        assert axes.get_title() == 'Window'
        assert len(axes.get_legend().texts) == 2

    monkeypatch.setattr(pyplot, 'subplots', create)
    monkeypatch.setattr(pyplot, 'show', show)
    monkeypatch.setattr(pyplot, 'close', closed.append)
    first = series([0,1], [1,2], label='Line')
    second = series([0,1], [2,3], type='scatter', label='Points')
    plot(first, second, backend='window', title='Window', figsize=[5,3], dpi=80, legend=True)
    assert created == [{'figsize': (5.0,3.0), 'dpi': 80.0}]
    assert shown == [True] and closed == [figure]


def test_invalid_density_does_not_open_a_window(monkeypatch):
    from matplotlib import pyplot

    monkeypatch.setattr(pyplot, 'subplots', lambda **kw: pytest.fail('invalid plot opened window'))
    value = series([3,4], type='hist', bins=[0,1], density=True)
    with pytest.raises(ValueError, match='inside the bin edges'):
        plot(value, backend='window')


def test_mixed_plot_does_not_resample_or_change_gui_backend(tmp_path):
    from matplotlib import pyplot

    seen = []
    env = {'f': lambda x: seen.append(x) or x*x}
    run_source(r'g = \graph(f, x=-1..1)', env)
    count = len(seen)
    backend = matplotlib.get_backend()
    figures = pyplot.get_fignums()
    value = series(env['g'], type='scatter')
    histogram = series([1,2,3], type='hist')
    plot(value, histogram, backend='file', path=str(tmp_path / 'mixed.svg'))
    assert len(seen) == count
    assert matplotlib.get_backend() == backend
    assert pyplot.get_fignums() == figures


def test_log_axes_leave_stored_samples_unchanged():
    value = evaluate(r'\graph(x, x=-1..1)')
    before = value.samples
    axes = axes_for(value, xscale='log', yscale='log')
    assert axes.get_xlim()[0] > 0
    assert list(zip(*axes.lines[0].get_data())) == list(before)
    assert value.samples is before


def test_grouped_bars_support_repeated_series_and_different_widths():
    first = series([0], [2], type='bar', width=0.4)
    second = series([0], [3], type='bar', width=0.8)
    axes = axes_for(first, second)
    left, right = axes.patches
    assert left.get_x() + left.get_width() == pytest.approx(right.get_x())
    assert left.get_x() == pytest.approx(-(right.get_x()+right.get_width()))
    repeated = axes_for(first, first)
    assert repeated.patches[0].get_x() < repeated.patches[1].get_x()


def test_series_colors_and_dash_patterns_are_immutable():
    value = evaluate(r'\series([0,1], [2,3], \color=[1,0,0], \linestyle=\arr(0,[3,2]))')
    settings = dict(value.options)
    assert settings['color'] == (1,0,0)
    assert settings['linestyle'] == (0,(3,2))
    axes = axes_for(value)
    assert to_rgba(axes.lines[0].get_color()) == to_rgba('red')
    marker = series([0,1], [2,3], marker=[[0,0], [1,0], [0,1], [0,0]])
    assert dict(marker.options)['marker'] == ((0,0), (1,0), (0,1), (0,0))
    assert len(axes_for(marker).lines) == 1


def test_series_demo_through_cli(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    demo = Path(__file__).resolve().parents[1] / 'demos' / 'plot-series.ad'
    result = subprocess.run([sys.executable, '-m', 'adhoc', 'run', str(demo)], cwd=tmp_path,
                            env={**os.environ, 'MPLBACKEND': 'Agg'}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all((tmp_path / name).exists() for name in ('curves.svg', 'steps.png', 'bars.svg', 'hist.svg'))
