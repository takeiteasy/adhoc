"""Immutable plot series, shared Matplotlib drawing and destination delivery."""

from dataclasses import dataclass
import math
from numbers import Real
from pathlib import Path

from .graph import GraphCollectionValue, GraphValue
from .tensor import ArrayValue


SERIES_OPTIONS = frozenset({"type", "label", "color", "linestyle", "linewidth", "marker",
                            "markersize", "alpha", "where", "width", "bins", "density"})
FIGURE_OPTIONS = frozenset({"title", "xlabel", "ylabel", "legend", "grid", "figsize", "dpi",
                            "xlim", "ylim", "xscale", "yscale"})
TYPE_OPTIONS = {
    "line": {"linestyle", "linewidth", "marker", "markersize"},
    "scatter": {"marker", "markersize"},
    "step": {"linestyle", "linewidth", "marker", "markersize", "where"},
    "bar": {"width"},
    "hist": {"bins", "density"},
}
COMMON_OPTIONS = {"type", "label", "color", "alpha"}


@dataclass(frozen=True)
class SeriesValue:
    graph: GraphValue | None
    x: tuple[float | str, ...] | None
    y: tuple[float, ...]
    options: tuple[tuple[str, object], ...]


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def _vector(value, name):
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{name} must be a nonempty one-dimensional vector or array")
    return tuple(value)


def _freeze(value):
    return tuple(_freeze(item) for item in value) if isinstance(value, (list, tuple)) else value


def _options(options, allowed):
    unknown = options.keys() - allowed
    if unknown:
        raise TypeError(f"unknown plot option: {sorted(unknown)[0]}")
    result = dict(options)
    for name in {"title", "xlabel", "ylabel", "label"} & result.keys():
        if not isinstance(result[name], str):
            raise TypeError(f"{name} must be a string")
    for name in {"legend", "grid", "density"} & result.keys():
        if not isinstance(result[name], bool):
            raise TypeError(f"{name} must be a boolean")
    for name in {"linewidth", "markersize", "width", "dpi"} & result.keys():
        result[name] = _number(result[name], name, positive=True)
    if "alpha" in result:
        result["alpha"] = _number(result["alpha"], "alpha")
        if not 0 <= result["alpha"] <= 1:
            raise ValueError("alpha must be between 0 and 1")
    for name in {"figsize", "xlim", "ylim"} & result.keys():
        values = _vector(result[name], name)
        if len(values) != 2:
            raise ValueError(f"{name} requires two numbers")
        result[name] = tuple(_number(v, name, positive=name == "figsize") for v in values)
        if name != "figsize" and result[name][0] == result[name][1]:
            raise ValueError(f"{name} limits must be distinct")
    for name in {"xscale", "yscale"} & result.keys():
        if result[name] not in ("linear", "log"):
            raise ValueError(f"{name} must be linear or log")
    if "type" in result and result["type"] not in TYPE_OPTIONS:
        raise ValueError("type must be line, scatter, step, bar or hist")
    if "where" in result and result["where"] not in ("pre", "mid", "post"):
        raise ValueError("where must be pre, mid or post")
    if "bins" in result:
        bins = result["bins"]
        if isinstance(bins, int) and not isinstance(bins, bool):
            if bins < 1:
                raise ValueError("bins must be a positive integer")
        else:
            bins = tuple(_number(v, "bins") for v in _vector(bins, "bins"))
            if len(bins) < 2 or any(a >= b for a, b in zip(bins, bins[1:])):
                raise ValueError("bin edges must be strictly increasing")
            result["bins"] = bins
    if "color" in result and isinstance(result["color"], (list, tuple)):
        result["color"] = tuple(_number(v, "color") for v in result["color"])
    if "linestyle" in result and isinstance(result["linestyle"], (list, tuple)):
        offset, pattern = result["linestyle"]
        result["linestyle"] = (_number(offset, "linestyle"),
                               tuple(_number(v, "linestyle", positive=True) for v in pattern))
    return {name: _freeze(value) for name, value in result.items()}


def series(*args, **options) -> SeriesValue:
    options = _options(options, SERIES_OPTIONS)
    if len(args) == 1 and isinstance(args[0], GraphValue):
        result = SeriesValue(args[0], None, (), tuple(options.items()))
    elif len(args) == 1 and options.get("type") == "hist":
        values = tuple(_number(v, "histogram observations")
                       for v in _vector(args[0], "histogram observations"))
        result = SeriesValue(None, None, values, tuple(options.items()))
    elif len(args) == 2:
        x, y = _vector(args[0], "x coordinates"), _vector(args[1], "y values")
        if len(x) != len(y):
            raise ValueError("x coordinates and y values must have equal lengths")
        if all(isinstance(v, str) for v in x):
            if options.get("type") != "bar":
                raise ValueError("categorical coordinates require type=\"bar\"")
            if len(set(x)) != len(x):
                raise ValueError("categorical coordinates must be unique")
        else:
            x = tuple(_number(v, "x coordinates") for v in x)
        result = SeriesValue(None, x, tuple(_number(v, "y values") for v in y),
                             tuple(options.items()))
    else:
        raise TypeError("series requires one graph, x/y data, or observations with type=\"hist\"")
    _validate_series(result, options)
    _appearance(options)
    return result


def _validate_series(value, options):
    kind = options.get("type", "line")
    invalid = options.keys() - COMMON_OPTIONS - TYPE_OPTIONS[kind]
    if invalid:
        raise ValueError(f"{sorted(invalid)[0]} is not supported for {kind} series")
    if value.graph is not None and kind in {"bar", "hist"}:
        raise ValueError(f"{kind} requires explicit data, not adaptive graph samples")
    if value.graph is None:
        observations = value.x is None
        if observations != (kind == "hist"):
            raise ValueError("hist requires observations; other types require x/y data")
        if value.x and isinstance(value.x[0], str) and kind != "bar":
            raise ValueError("categorical coordinates require bar series")


def _histogram_edges(histograms):
    import matplotlib
    import numpy as np

    bins = [settings.get("bins", matplotlib.rcParams["hist.bins"])
            for _, settings in histograms]
    if any(spec != bins[0] for spec in bins[1:]):
        raise ValueError("overlaid histograms require matching bins")
    return np.histogram_bin_edges([v for value, _ in histograms for v in value.y], bins=bins[0])


def _prepare(inputs, options):
    defaults = {key: value for key, value in options.items() if key in SERIES_OPTIONS}
    result = []
    flattened = (item for value in inputs
                 for item in (value.graphs if isinstance(value, GraphCollectionValue) else (value,)))
    for value in flattened:
        if isinstance(value, GraphValue):
            value = SeriesValue(value, None, (), ())
        if not isinstance(value, SeriesValue):
            raise TypeError("plot requires graph data from \\graph or explicit \\series data")
        settings = defaults | dict(value.options)
        _validate_series(value, settings)
        _appearance(settings)
        result.append((value, settings))
    if not result:
        raise TypeError("plot requires at least one graph or series")
    categories = [value for value, _ in result if value.x and isinstance(value.x[0], str)]
    if categories and len(categories) != len(result):
        raise ValueError("categorical bars can only share axes with categorical bars")
    if categories and options.get("xscale") == "log":
        raise ValueError("categorical axes do not support log scale")
    names = {value.graph.axis_spelling for value, _ in result if value.graph is not None}
    if len(names) > 1 and "xlabel" not in options:
        raise ValueError("graphs with different axis names require xlabel")
    for axis in ("x", "y"):
        if options.get(axis + "scale") == "log" and axis + "lim" in options:
            if min(options[axis + "lim"]) <= 0:
                raise ValueError(f"{axis}lim must be positive on a log scale")
    histograms = [(value, settings) for value, settings in result
                  if settings.get("type", "line") == "hist"]
    edges = _histogram_edges(histograms) if histograms else None
    for value, settings in histograms:
        if settings.get("density", False) and not any(edges[0] <= v <= edges[-1] for v in value.y):
            raise ValueError("density requires observations inside the bin edges")
    return result, edges


def _appearance(settings):
    from matplotlib.colors import is_color_like
    from matplotlib.lines import Line2D
    from matplotlib.markers import MarkerStyle

    if "color" in settings and not is_color_like(settings["color"]):
        raise ValueError("color must be a valid Matplotlib color")
    if "marker" in settings:
        MarkerStyle(settings["marker"])
    if "linestyle" in settings:
        Line2D([], [], linestyle=settings["linestyle"])


def draw(graph, axes, **options) -> None:
    """Draw curves and explicit series on the same axes for every destination."""
    inputs = graph if isinstance(graph, tuple) else (graph,)
    options = _options(options, FIGURE_OPTIONS | SERIES_OPTIONS)
    prepared = _prepare(inputs, options)
    _draw(prepared, axes, options)


def _draw(prepared, axes, options):
    import matplotlib

    prepared, edges = prepared
    categories = dict.fromkeys(x for value, _ in prepared if value.x
                               for x in value.x if isinstance(x, str))
    positions = {key: index for index, key in enumerate(categories)}
    bars = [(value, settings) for value, settings in prepared
            if settings.get("type", "line") == "bar"]
    colors = matplotlib.rcParams["axes.prop_cycle"].by_key().get("color", ["C0"])
    handles, labels = [], []
    bar_slot = 0
    bar_widths = [settings.get("width", 0.8) / len(bars) for _, settings in bars]
    bar_left = -sum(bar_widths) / 2
    for index, (value, settings) in enumerate(prepared):
        kind = settings.get("type", "line")
        label = settings.get("label", value.graph.label if value.graph else f"Series {index + 1}")
        style = {key: item for key, item in settings.items()
                 if key in {"color", "alpha", "linestyle", "linewidth", "marker", "markersize"}}
        style.setdefault("color", colors[index % len(colors)])
        handle = None
        if kind == "hist":
            _, _, patches = axes.hist(value.y, bins=edges, density=settings.get("density", False),
                                      **style)
            handle = patches[0]
        elif kind == "bar":
            width = bar_widths[bar_slot]
            bar_slot += 1
            x = [positions[v] if categories else v for v in value.x]
            x = [v + bar_left + width / 2 for v in x]
            bar_left += width
            handle = axes.bar(x, value.y, width=width, **style)
        else:
            segments = value.graph.segments if value.graph else (tuple(zip(value.x, value.y)),)
            for segment in segments:
                x, y = zip(*segment)
                if kind == "scatter":
                    scatter_style = dict(style)
                    if "markersize" in scatter_style:
                        scatter_style["s"] = scatter_style.pop("markersize") ** 2
                    artist = axes.scatter(x, y, **scatter_style)
                else:
                    line_style = dict(style)
                    if len(segment) == 1:
                        line_style.setdefault("marker", "o")
                    if kind == "step":
                        artist, = axes.step(x, y, **line_style,
                                            **({"where": settings["where"]} if "where" in settings else {}))
                    else:
                        artist, = axes.plot(x, y, **line_style)
                if handle is None:
                    handle = artist
        if handle is not None and label:
            handles.append(handle)
            labels.append(label)
    if categories:
        axes.set_xticks(list(positions.values()), list(positions), parse_math=False)
    graphs = [value.graph for value, _ in prepared if value.graph is not None]
    single_graph = len(prepared) == 1 and bool(graphs)
    axes.set_title(options.get("title", graphs[0].label if single_graph else ""), parse_math=False)
    axes.set_xlabel(options.get("xlabel", graphs[0].axis_spelling if graphs else ""), parse_math=False)
    axes.set_ylabel(options.get("ylabel", ""), parse_math=False)
    if "grid" in options:
        axes.grid(options["grid"])
    if options.get("legend", False) and handles:
        legend = axes.legend(handles, labels)
        for text in legend.texts:
            text.set_parse_math(False)
    for axis in ("x", "y"):
        if axis + "scale" in options:
            getattr(axes, "set_" + axis + "scale")(options[axis + "scale"])
        if axis + "lim" in options:
            getattr(axes, "set_" + axis + "lim")(*options[axis + "lim"])
    if "xlim" not in options and len(graphs) == len(prepared):
        lo, hi = min(g.bounds[0] for g in graphs), max(g.bounds[1] for g in graphs)
        if lo != hi:
            if options.get("xscale") == "log":
                positive = [x for g in graphs for x, y in g.samples if x > 0 and y is not None]
                if positive:
                    axes.set_xlim(min(positive), max(positive))
            else:
                axes.set_xlim(lo, hi)
    elif "xlim" not in options and graphs:
        lo, hi = axes.get_xlim()
        bounds = [x for g in graphs for x in g.bounds
                  if options.get("xscale") != "log" or x > 0]
        if bounds:
            axes.set_xlim(min(lo, *bounds), max(hi, *bounds))


def _file(prepared, path: Path, format: str, options) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(**{key: value for key, value in options.items() if key in {"figsize", "dpi"}})
    FigureCanvasAgg(figure)
    try:
        _draw(prepared, figure.subplots(), options)
        stream = path.open("xb")
        try:
            with stream:
                figure.savefig(stream, format=format)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    finally:
        figure.clear()


def _window(prepared, options) -> None:
    from matplotlib import pyplot

    figure = None
    try:
        try:
            kwargs = {key: value for key, value in options.items() if key in {"figsize", "dpi"}}
            figure, axes = pyplot.subplots(**kwargs)
        except Exception as error:
            raise ValueError("window plotting requires an available Matplotlib GUI backend; "
                             f"use backend=\"file\" in a headless session: {error}") from error
        if figure.canvas.required_interactive_framework is None:
            raise ValueError("window plotting requires an available Matplotlib GUI backend; "
                             "use backend=\"file\" in a headless session")
        _draw(prepared, axes, options)
        # TODO: blocking REPL; integrate GUI event handling for responsive input (#53).
        pyplot.show(block=True)
    finally:
        if figure is not None:
            pyplot.close(figure)


def plot(*graphs, backend: str, path: str | None = None, **options):
    options = _options(options, FIGURE_OPTIONS | SERIES_OPTIONS)
    prepared = _prepare(graphs, options)
    if not isinstance(backend, str):
        raise TypeError("plot backend must be a string")
    if backend == "term":
        raise ValueError("terminal plotting is not implemented; choose file or window")
    if backend not in {"file", "window"}:
        raise ValueError("plot backend must be file or window")
    if backend == "window" and path is not None:
        raise ValueError("window plotting does not accept a path")
    if backend == "file":
        if not isinstance(path, str) or not path:
            raise ValueError("file plotting requires a nonempty string path")
        destination = Path(path)
        format = destination.suffix.lower().lstrip(".")
        if format not in {"svg", "png", "pdf"}:
            raise ValueError("plot file extension must be .svg, .png or .pdf")

    import matplotlib

    with matplotlib.rc_context({"text.usetex": False, "interactive": False}):
        if backend == "file":
            _file(prepared, destination, format, options)
        else:
            _window(prepared, options)
    return graphs[0] if len(graphs) == 1 else ArrayValue(tuple(graphs))
