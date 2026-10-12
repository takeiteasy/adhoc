import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
from matplotlib import pyplot
from matplotlib.figure import Figure
from PIL import Image

from adhoc.driver import run_source
from adhoc.plot import draw, plot
from adhoc.runtime import EvalError
from adhoc.span import Span


def graph(source=r"\graph(x^2, x=-1..1)"):
    env = {}
    run_source("g = " + source, env)
    return env["g"]


@pytest.mark.parametrize("format", ["svg", "png", "pdf", "SVG"])
def test_export_formats_through_language(tmp_path, monkeypatch, format):
    monkeypatch.chdir(tmp_path)
    env = {"g": graph()}
    run_source(r'v = \plot(g, \backend="file", \path="plot.' + format + '")', env)
    assert env["v"] is env["g"]
    path = tmp_path / ("plot." + format)
    if format.lower() == "svg":
        root = ET.parse(path).getroot()
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert env["g"].label.encode() in path.read_bytes()
    elif format == "png":
        with Image.open(path) as image:
            image.load()
            assert image.format == "PNG"
            assert image.width > 0 and image.height > 0
    else:
        assert path.read_bytes().startswith(b"%PDF-")
        assert path.read_bytes().rstrip().endswith(b"%%EOF")


@pytest.mark.parametrize("source", [
    r"\graph(x^2, x=-1..1)",
    r"\graph(1/x, x=-1..1)",
    r"\graph(x, x=0..1, \maxpoints=33)",
    r"\graph(x, x=2..2)",
    r"\graph(\sqrt(x), x=-2..-1)",
])
def test_draw_preserves_segments_and_labels(source):
    value = graph(source)
    figure = Figure()
    axes = figure.subplots()
    draw(value, axes)
    assert len(axes.lines) == len(value.segments)
    for line, segment in zip(axes.lines, value.segments):
        assert list(zip(*line.get_data())) == list(segment)
        assert line.get_color() == "C0"
        if len(segment) == 1:
            assert line.get_marker() == "o"
    assert axes.get_xlabel() == value.axis_spelling
    assert axes.get_title() == value.label
    assert not axes.title.get_parse_math()
    if value.bounds[0] != value.bounds[1]:
        assert axes.get_xlim() == value.bounds


@pytest.mark.parametrize("arguments, message", [
    ('1, \\backend="file", \\path="plot.svg"', "graph data"),
    ('g', "backend"),
    ('g, \\backend=1', "string"),
    ('g, \\backend="other"', "file or window"),
    ('g, \\backend="term"', "not implemented"),
    ('g, \\backend="file"', "path"),
    ('g, \\backend="file", \\path=1', "string path"),
    ('g, \\backend="file", \\path=""', "nonempty"),
    ('g, \\backend="file", \\path="plot"', "extension"),
    ('g, \\backend="file", \\path="plot.jpeg"', "extension"),
    ('g, \\backend="window", \\path="plot.svg"', "does not accept"),
    ('g, \\backend="file", \\path="plot.svg", \\dpi=200', "dpi"),
    ('g, g, \\backend="window"', "positional"),
])
def test_invalid_calls_have_source_spans(arguments, message):
    source = r"\plot(" + arguments + ")"
    with pytest.raises(EvalError, match=message) as error:
        run_source(source, {"g": graph()})
    assert error.value.span == Span(0, len(source.encode()))


def test_existing_file_is_preserved(tmp_path):
    path = tmp_path / "plot.svg"
    path.write_bytes(b"keep this file")
    with pytest.raises(FileExistsError):
        plot(graph(), backend="file", path=str(path))
    assert path.read_bytes() == b"keep this file"


def test_missing_directory_error_has_call_span(tmp_path):
    source = r'\plot(g, \backend="file", \path=p)'
    with pytest.raises(EvalError, match="FileNotFoundError") as error:
        run_source(source, {"g": graph(), "p": str(tmp_path / "missing" / "plot.svg")})
    assert error.value.span == Span(0, len(source.encode()))
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("failure", [OSError("write failed"), KeyboardInterrupt()])
def test_failed_export_removes_partial_file_and_closes_stream(tmp_path, monkeypatch, failure):
    streams = []

    def fail(figure, stream, **kwargs):
        streams.append(stream)
        stream.write(b"partial")
        raise failure

    monkeypatch.setattr(Figure, "savefig", fail)
    path = tmp_path / "plot.svg"
    with pytest.raises(type(failure)):
        plot(graph(), backend="file", path=str(path))
    assert not path.exists()
    assert streams[0].closed


def test_export_does_not_change_gui_backend_or_resample(tmp_path):
    import matplotlib

    seen = []
    env = {"f": lambda x: seen.append(x) or x * x}
    run_source(r"g = \graph(f, x=-1..1)", env)
    count = len(seen)
    backend = matplotlib.get_backend()
    figures = pyplot.get_fignums()
    plot(env["g"], backend="file", path=str(tmp_path / "plot.svg"))
    assert len(seen) == count
    assert matplotlib.get_backend() == backend
    assert pyplot.get_fignums() == figures


@pytest.mark.parametrize("failure", [None, RuntimeError("show failed"), KeyboardInterrupt()])
def test_window_blocks_and_closes_owned_figure(monkeypatch, failure):
    value = graph(r"\graph(1/x, x=-1..1)")
    figure = Figure()
    axes = figure.subplots()
    figure.canvas.required_interactive_framework = "tk"
    calls = []
    closed = []
    monkeypatch.setattr(pyplot, "subplots", lambda: (figure, axes))
    monkeypatch.setattr(pyplot, "close", closed.append)

    def show(*, block):
        calls.append(block)
        assert len(axes.lines) == len(value.segments)
        if failure is not None:
            raise failure

    monkeypatch.setattr(pyplot, "show", show)
    if failure is None:
        assert plot(value, backend="window") is value
    else:
        with pytest.raises(type(failure)):
            plot(value, backend="window")
    assert calls == [True]
    assert closed == [figure]


def test_headless_window_errors_and_closes_figure(monkeypatch):
    figure = Figure()
    closed = []
    monkeypatch.setattr(pyplot, "subplots", lambda: (figure, figure.subplots()))
    monkeypatch.setattr(pyplot, "close", closed.append)
    monkeypatch.setattr(pyplot, "show", lambda **kwargs: pytest.fail("headless show"))
    with pytest.raises(EvalError, match="GUI backend"):
        run_source(r'\plot(g, \backend="window")', {"g": graph()})
    assert closed == [figure]


def test_unavailable_gui_backend_has_actionable_error(monkeypatch):
    def unavailable():
        raise ImportError("GUI toolkit unavailable")

    monkeypatch.setattr(pyplot, "subplots", unavailable)
    with pytest.raises(EvalError, match="GUI backend.*headless.*toolkit unavailable"):
        run_source(r'\plot(g, \backend="window")', {"g": graph()})


def test_runtime_import_does_not_import_matplotlib():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import adhoc.runtime; "
         "assert 'matplotlib' not in sys.modules"], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_export_demo_through_cli(tmp_path):
    demo = Path(__file__).resolve().parents[1] / "demos" / "plot.ad"
    result = subprocess.run(
        [sys.executable, "-m", "adhoc", "run", str(demo)], cwd=tmp_path,
        env={**os.environ, "MPLBACKEND": "Agg"}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "plot.svg").exists()
    assert "<graph" in result.stdout
