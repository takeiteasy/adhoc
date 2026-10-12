# Graph sampling

`\graph` samples a real function or expression over a finite range and returns
immutable graph data. It refines curved regions and preserves gaps around
undefined points. The result is data for plotting; see [limitations](#limitations)
for rendering and export.

## Forms

| Form | Samples |
|---|---|
| `\graph(f, x=a..b)` | A one-argument callable |
| `\graph(x^2, x=a..b)` | An expression using the axis variable |
| `\graph((x ↦ 3), x=a..b)` | A constant function |
| `\graph(f, t=r)` | A callable over a stored range, with axis label `t` |

```text
f(x) = x^2
g = \graph(f, x=-1..1)
g                            -> = <graph x=-1.0..1.0; 129 samples; 0 gaps; complete>
\graph(x^2, x=-1..1)          -> the same sampled coordinates
\graph(1/x, x=-1..1)          -> graph data with a break around zero
```

The axis name is one letter, optionally subscripted. A free reference to that
name in the first argument selects expression sampling, even if the name is
already bound outside the call. Each probe binds it in a fresh local frame;
other names read through to the surrounding scope. Lambda parameters and nested
calculus or collection binders mask their own variables; quoted syntax does not
read names. An argument with no free axis reference must evaluate to a callable.
For dynamic quoted evaluation, bind the axis in an explicit lambda.

Bounds, options and callable expressions evaluate once in the surrounding scope.
Bounds must be finite real scalars in an unstepped range. Reversed bounds sample
in ascending order; equal bounds evaluate once. Sampling uses float arguments
and float coordinates, including when endpoints are exact numbers.

## Accuracy and cost

| Option | Default | Accepted values |
|---|---|---|
| `\tol` | `0.001` | Finite positive real scalar, excluding booleans |
| `\maxpoints` | `4097` | Exact integer of at least 33, excluding booleans |

```text
\graph(\sin, x=0..2π, \tol=0.0001, \maxpoints=8193)
\graph(x, x=0..1, \maxpoints=33)  -> incomplete graph with unchecked intervals
```

Sampling starts with 33 evenly spaced coordinates including both endpoints.
It checks midpoint and quarter-point departures from straight-line interpolation,
then refines intervals whose local relative error exceeds `\tol`.[^adaptive]
Each distinct float coordinate evaluates at most once. Evaluation order is
deterministic but does not move monotonically along the axis; sampled functions
should be deterministic.

A `complete` result satisfies the sampling heuristic. An `incomplete` result
retains its samples and marks unchecked or unresolved intervals as breaks.
Its summary reports `budget`, `depth` or `precision` stopping reasons.[^limits]

## Gaps and errors

| Sample result | Behavior |
|---|---|
| Finite real number | Keep the coordinate and float value |
| Mathematical domain failure | Gap |
| Non-real number, infinity or NaN | Gap |
| Boolean, collection, string or quantity | Error |
| Unbound name, wrong arity or unexpected exception | Error with source span |

Mixed valid and invalid intervals refine to locate domain boundaries. Intervals
whose five probes are invalid remain gaps. Domain boundaries may leave small
unresolved intervals and an incomplete status. A wholly invalid sampled domain
returns a complete graph with no connected segments.

Built-in numeric domain failures retain a category through runtime error wrapping.
Python division-by-zero and overflow failures also produce gaps. Arbitrary Python
`ValueError` exceptions propagate as errors.

## Backend data

`adhoc.graph.GraphValue` stores the axis name and spelling, source label, normalized
bounds, ordered `(x, y)` samples, breaks, evaluation count, settings, completion
flag and stopping reasons. An absent `y` marks an invalid sample. Each break has
`start`, `end` and `reason` fields. The `segments` property returns connected finite
sample runs; it never joins across a break.

Graph values bind to names, pass through functions and display compact summaries.
Quoted graph calls round-trip through expression display and render with `\tex`.

## Limitations

| Limit | Ticket |
|---|---|
| Narrow features and oscillations can evade finite probing; completion is not a proof of continuity or accuracy | [#52](https://github.com/takeiteasy/adhoc/issues/52) |
| Complex and dimensioned axes or outputs | [Graphing](https://github.com/takeiteasy/adhoc/issues/30) |
| Terminal rendering | [#25](https://github.com/takeiteasy/adhoc/issues/25) |
| Several curves on shared axes | [#26](https://github.com/takeiteasy/adhoc/issues/26) |
| File export | [#27](https://github.com/takeiteasy/adhoc/issues/27) |

[^adaptive]: Interpolation error is the maximum departure at the midpoint and
    quarter points divided by `max(1, absolute values of the five probes)`.
    Initial intervals are checked before adaptive refinement. A priority queue
    refines the greatest error first, breaking ties by coordinate. Mixed
    valid/invalid intervals have highest priority. Samples are cached by their
    float coordinate; adjacent breaks with the same reason merge.

[^limits]: Each initial interval permits 24 levels of bisection. Refinement also
    stops when quarter-point coordinates are no longer distinct floats. The
    evaluation budget includes initial coordinates, interior checks and invalid
    samples. Limits apply per graph call; they do not interrupt an individual
    function evaluation.
