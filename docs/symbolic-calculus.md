# Symbolic calculus arrays

`\grad`, `\jacobian` and `\hessian` return arrays of expression quotes.
Evaluate them at a point with `\eval`, then use `\tensor` for numeric vector
and matrix operations.

## Operations

| Call | Input | Result |
|---|---|---|
| `\grad(e[, names])` | Scalar quote or scalar function | Array of first partials |
| `\jacobian(v[, names])` | Flat array of scalar quotes/functions, or array-bodied function | Array of rows of first partials |
| `\hessian(e[, names])` | Scalar quote or scalar function | Array of rows of second partials |

Jacobian rows follow output order; columns follow variable order:
`J[i][j]` represents the derivative of output `i` with respect to variable `j`.
Hessian rows and columns follow the same variable order.
Array indexing is 1-based and uses one bracket pair per level.

```text
f(x, y) = ⟨x^2 y, x+y⟩
j = \jacobian(f)
\tensor(\eval(j, x=2, y=3))     -> = [12, 4; 1, 1]
\det(\tensor(\eval(j, x=2, y=3))) -> = 8

h = \hessian(`(x^2 y+3y^2))
\tensor(\eval(h, x=2, y=3))     -> = [6, 4; 4, 6]
```

## Variable selection

Functions use parameter order. Quotes use the sorted union of free names.
An explicit nonempty array of distinct quoted names selects and orders variables:

```text
\tensor(\eval(\jacobian(⟨`(x y)⟩, ⟨`(y), `(x), `(z)⟩), x=2, y=3))
    -> = [2, 3, 0;]
```

An absent variable gives a zero derivative. Constant quotes require explicit
names; constant functions retain their parameters. Arrays mixing quotes and
functions, or functions with different parameter lists, require explicit names.

Array-bodied functions have one expression body containing a flat array of
scalar expressions. Captured numeric bindings and supported nested scalar
function calls follow [symbolic rewriting](symbolic.md#inputs).

## Evaluation and conversion

`\eval` accepts nested arrays with quotes at every leaf and preserves their
structure. Bindings are evaluated once and shared as inputs to separate child
frames; statement quotes keep their assignments local. Errors retain the source
and span of the failing quote.

`\tensor` accepts rectangular nested numeric arrays with no empty axes.
Ragged structure, quotes, booleans and incompatible dimensions are errors.
Exact numbers remain exact. Matching dimensioned entries produce a dimensioned
tensor. Arrays themselves have no arithmetic.

## Dimensions and limits

`\jacobian` and `\hessian` accept `\dimensions` annotations using the
[dimension annotation rules](symbolic.md#dimension-annotations).
Each derivative quote retains its annotations. Jacobian entries have output
units divided by the column variable's units; Hessian entries divide by both
selected variables' units. Entries may have different units; evaluation keeps
those quantities in arrays, and tensor conversion requires matching dimensions.

Each complete gradient, Jacobian or Hessian shares one
[symbolic time limit](symbolic.md#time-limit), including function expansion and
all components.

## Limitations

Symbolic arrays have no vector algebra. Numeric algebra requires evaluation
and explicit tensor conversion. Recursive calls, statement-bodied symbolic
functions and unsupported nested dimensioned calls follow the
[symbolic limitations](symbolic.md#limitations).
