# Plotting

`\plot` renders sampled graph data with Matplotlib. Choose a file or a window
explicitly; rendering returns the same graph value and does not sample again.

## Destinations

| Call | Result |
|---|---|
| `\plot(g, \backend="file", \path="plot.svg")` | Write an SVG file |
| `\plot(g, \backend="file", \path="plot.png")` | Write a PNG file |
| `\plot(g, \backend="file", \path="plot.pdf")` | Write a PDF file |
| `\plot(g, \backend="window")` | Open a window and wait until it closes |

```text
g = \graph(1/x, x=-1..1)
\plot(g, \backend="file", \path="plot.svg")
```

The graph's connected segments remain separate, including breaks in incomplete
graphs. Isolated samples appear as points. The horizontal axis uses the sampling
variable's spelling, and the title uses the source label as plain text.
See [graph sampling](graph-sampling.md) for accuracy controls and gaps.

## Files

The filename extension selects SVG, PNG or PDF, ignoring case. Relative paths
start at the process's working directory, including when running a script from
another directory. Parent directories must exist. Existing files are protected:
choose another path to export again.

File export works without a display and does not change the GUI backend. Failed
writes remove the partial file created by that call.[^files]

Run `adhoc run demos/plot.ad` from a directory without an existing `plot.svg` to
try the export example.

## Windows

Window plots use Matplotlib's configured GUI backend. The script or REPL waits
until the window closes. A headless session or unavailable GUI toolkit produces
an error; use file output over SSH when a display is unavailable.[^gui]

`\backend` chooses the destination (`file` or `window`), rather than a Matplotlib
GUI toolkit. Window calls do not accept `\path`. Both destinations require graph
data from `\graph`; unknown options are errors.

## Limitations

| Limit | Ticket |
|---|---|
| Window plotting blocks the REPL | [#53](https://github.com/takeiteasy/adhoc/issues/53) |
| Styling uses Matplotlib defaults without per-call controls | [#54](https://github.com/takeiteasy/adhoc/issues/54) |
| Terminal delivery, protocol detection and braille fallback | [#25](https://github.com/takeiteasy/adhoc/issues/25) |
| Several curves on shared axes | [#26](https://github.com/takeiteasy/adhoc/issues/26) |

[^files]: The destination is opened in exclusive binary creation mode, and the
    format is passed explicitly to Matplotlib. Export errors retain the plot
    call's source span. Cleanup applies to caught failures and interruptions;
    forced process termination can leave a partial file.

[^gui]: Matplotlib selects the toolkit through its configuration or `MPLBACKEND`.
    Installing Matplotlib does not guarantee that a GUI toolkit or display is
    available. A real window smoke test needs a desktop session; automated tests
    check drawing, dispatch, blocking and cleanup without opening windows.
