# Explicit plot data

`\series` stores coordinates or observations for plotting. Use explicit data for
bars and histograms, or to draw a line, scatter or step series without adaptive
sampling. Pass series to [`\plot`](plotting.md) for file or window output.

## Coordinates and values

```text
s = \series([0,1,2], [1,3,2], \type="step", \where="post")
\plot(s, \backend="file", \path="steps.svg")
```

Coordinate and value inputs are nonempty one-dimensional vectors or arrays of
equal length. Numbers must be finite real scalars; booleans, quantities and
complex values are errors. Coordinates retain input order. Numeric coordinates
support line, scatter, step and bar types. Categorical coordinates support bars.

## Bars

```text
b = \series(\arr("A","B"), [3,5], \type="bar", \label="Count")
\plot(b, \backend="file", \path="bars.svg")
```

Categorical coordinates are unique strings within each series. Categories align
in first-seen order across series; missing categories have no bar. Categorical
bars share axes only with other categorical bars and do not support a logarithmic
horizontal axis.

Several bar series draw side by side at each coordinate. Each requested group
width is divided by the number of bar series. Negative heights extend below zero.
Bars require explicit data rather than adaptive function samples.

## Histograms

```text
h = \series([1,2,2,3,4], \type="hist", \bins=10, \density=\true)
\plot(h, \backend="file", \path="hist.svg", \alpha=0.5)
```

Histogram input contains observations, rather than x/y coordinates. `\bins` is a
positive integer count or a vector/array of strictly increasing finite edges.
Without a supplied count, Matplotlib's configured histogram default applies.

Overlaid histograms require matching bin specifications. Count-based edges cover
the combined observations. Density normalizes each histogram independently;
observations outside explicit edges are excluded, and density requires at least
one observation inside the edges. Histograms retain Matplotlib's default opacity;
set `\alpha` to see overlapping distributions.

## Combining types

Numeric series share axes with sampled graphs and other numeric series. The
horizontal extent includes graph bounds, explicit data and bar/bin geometry.
Explicit `\xlim` and `\ylim` override automatic bounds.

Categorical bars combine only with categorical bars. Use separate plots when
numeric data and categories need different horizontal axes. Per-series settings
override the defaults supplied to `\plot`; see [styling controls](plotting.md#styling-controls).
