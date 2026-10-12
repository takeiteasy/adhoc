# Plotting

`\plot` draws sampled functions and explicit data on shared axes. Select a file
or window, choose a graph type, and set figure or per-series styling. Plotting
returns its inputs and does not sample functions again.

## Destinations

| Call | Result |
|---|---|
| `\plot(g, \backend="file", \path="plot.svg")` | Write SVG, PNG or PDF, selected by extension |
| `\plot(g, \backend="window")` | Open a window and wait until it closes |

Relative paths start at the process's working directory. Parent directories must
exist. Existing files are protected; choose another path to export again. File
export works without a display and leaves the GUI backend unchanged. Failed
writes remove the partial file created by the call.[^files]

Windows use Matplotlib's configured GUI toolkit and require a desktop display.
A window call does not accept `\path`. `\backend` selects the destination, rather
than a toolkit.[^gui]

## Several curves

Pass several graphs to `\plot`, or sample several targets in one `\graph` call:

```text
g = \graph(\sin, \cos, x=0..2π)
h = \graph(x/4, x=0..2π)
\plot(g, h, \backend="file", \path="curves.svg", \legend=\true)
```

Graph bundles flatten in argument order. Each curve has its own color and one
legend entry, even when domain gaps split it into several segments. Graph-only
plots cover the union of sampling ranges. Graphs with different axis names
require an explicit `\xlabel`.

A single graph uses its source as the title and sampling variable as the
horizontal label. Multiple series have a blank title unless supplied. Legends
are off unless enabled. One input returns that same value; several inputs return
an array of the original arguments.

See [graph sampling](graph-sampling.md) for accuracy controls and gaps.

## Series and graph types

`\series` creates immutable, reusable data and presentation settings:

```text
g = \graph(x^2, x=-1..1)
s = \series(g, \type="scatter", \color="red", \label="Square")
\plot(s, \backend="file", \path="points.png")

p = \series([0,1,2], [1,3,2], \type="step", \where="post")
\plot(p, \backend="file", \path="steps.svg")
```

| Type | Input | Type-specific controls |
|---|---|---|
| `"line"` (default) | Sampled graph or explicit x/y data | Line style, width and markers |
| `"scatter"` | Sampled graph or explicit x/y data | Marker and marker size |
| `"step"` | Sampled graph or explicit x/y data | Line controls; `\where="pre"`, `"mid"` or `"post"` |
| `"bar"` | Explicit numeric or categorical x/y data | `\width`, default `0.8` |
| `"hist"` | Explicit observations | `\bins` and `\density` |

Use `\series(xs, ys, ...)` for explicit coordinates and values. Both inputs are
nonempty one-dimensional vectors or arrays of equal length. Numeric data must
be finite real scalars; booleans, quantities and complex values are errors.
Coordinates retain input order. Sampled lines and steps never connect across
graph breaks; isolated graph samples appear as points.

See [explicit plot data](plot-data.md) for grouped bars, categorical axes and
histogram binning.

## Styling controls

Figure settings belong to `\plot`. Series settings work in `\plot` as defaults
and in `\series` as overrides. A series's explicit setting takes priority.
Unknown options and controls incompatible with the resulting type are errors.

| Figure option | Value |
|---|---|
| `\title`, `\xlabel`, `\ylabel` | Plain strings; `""` clears a label |
| `\legend`, `\grid` | Boolean |
| `\figsize` | `[width,height]` in inches, both positive |
| `\dpi` | Positive dots per inch |
| `\xlim`, `\ylim` | Two distinct finite numbers; reversed limits reverse the axis |
| `\xscale`, `\yscale` | `"linear"` or `"log"` |

| Series option | Value |
|---|---|
| `\type` | A type from the table above |
| `\label` | Plain legend label; `""` suppresses the entry |
| `\color` | Matplotlib color, such as `"red"` or `"#336699"` |
| `\linestyle` | Matplotlib line style, such as `"-"`, `"--"` or `":"` |
| `\linewidth` | Positive width in points |
| `\marker` | Matplotlib marker, such as `"o"` or `"x"` |
| `\markersize` | Positive size in points; scatter converts it to area |
| `\alpha` | Opacity from `0` to `1` |
| `\where` | Step position: `"pre"`, `"mid"` or `"post"` |
| `\width` | Positive bar group width in horizontal coordinates |
| `\bins` | Positive integer count or increasing edges |
| `\density` | Boolean histogram normalization |

```text
\plot(g, \type="scatter", \backend="file", \path="styled.png",
      \title="Measurements", \xlabel="Time", \ylabel="Value",
      \figsize=[8,5], \dpi=150, \grid=\true)
```

Appearance, figure size, DPI and grid otherwise follow Matplotlib configuration.
Logarithmic axes mask nonpositive plotted coordinates without changing stored
data. Explicit limits on a log axis must be positive. Rendering settings are
scoped to the call and do not change global configuration.

Run `adhoc run demos/plot.ad` for a single export, or
`adhoc run demos/plot-series.ad` for styled curves, bars and histograms. Run them
in a directory without the output files.

## Limitations

| Limit | Ticket |
|---|---|
| Window plotting blocks the REPL | [#53](https://github.com/takeiteasy/adhoc/issues/53) |
| Terminal delivery, protocol detection and braille fallback | [#25](https://github.com/takeiteasy/adhoc/issues/25) |

Themes, stacked histograms and secondary axes have no language controls.

[^files]: The destination opens in exclusive binary creation mode. Export errors
    retain the plot call's source span. Cleanup covers caught failures and
    interruptions; forced termination can leave a partial file.

[^gui]: Matplotlib selects the toolkit through its configuration or `MPLBACKEND`.
    Installing Matplotlib does not guarantee a GUI toolkit or display. Automated
    tests check drawing, dispatch, blocking and cleanup without opening windows;
    a real window smoke test needs a desktop session.
