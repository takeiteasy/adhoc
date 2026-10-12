"""Matplotlib graph drawing and destination delivery."""

from pathlib import Path

from .graph import GraphValue


def draw(graph: GraphValue, axes) -> None:
    """Draw sampled segments onto axes shared by every destination."""
    for segment in graph.segments:
        x, y = zip(*segment)
        axes.plot(x, y, color="C0", marker="o" if len(segment) == 1 else None)
    axes.set_xlabel(graph.axis_spelling, parse_math=False)
    axes.set_title(graph.label, parse_math=False)
    if graph.bounds[0] != graph.bounds[1]:
        axes.set_xlim(*graph.bounds)


def _file(graph: GraphValue, path: Path, format: str) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure()
    FigureCanvasAgg(figure)
    try:
        draw(graph, figure.subplots())
        stream = path.open("xb")
        try:
            with stream:
                figure.savefig(stream, format=format)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    finally:
        figure.clear()


def _window(graph: GraphValue) -> None:
    from matplotlib import pyplot

    figure = None
    try:
        try:
            figure, axes = pyplot.subplots()
        except Exception as error:
            raise ValueError("window plotting requires an available Matplotlib GUI backend; "
                             f"use backend=\"file\" in a headless session: {error}") from error
        if figure.canvas.required_interactive_framework is None:
            raise ValueError("window plotting requires an available Matplotlib GUI backend; "
                             "use backend=\"file\" in a headless session")
        draw(graph, axes)
        pyplot.show(block=True)
    finally:
        if figure is not None:
            pyplot.close(figure)


def plot(graph: GraphValue, *, backend: str, path: str | None = None) -> GraphValue:
    if not isinstance(graph, GraphValue):
        raise TypeError("plot requires graph data from \\graph")
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
            _file(graph, destination, format)
        else:
            _window(graph)
    return graph
