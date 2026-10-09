# Collection slicing

Tensors and arrays accept ranges in index brackets. Indices are 1-based;
range endpoints are inclusive when reached. Bare `..` selects a whole axis.

## Selectors

| Selector | Meaning |
|---|---|
| `2` | One entry; removes a tensor axis |
| `2..4` | Entries 2 through 4; retains a tensor axis |
| `2..` | Entry 2 through the end |
| `..` | The whole axis |
| `(1,3..7)` | Entries 1, 3, 5, 7 |
| `(4,3..)` | Entries 4, 3, 2, 1 |

Stepped ranges use parentheses because commas in brackets separate axes.
Range-valued variables also work: `r=2..; v[r]`.
Open ranges stop at the collection boundary in their step direction.[^ranges]

## Tensor shapes

Integer selectors remove axes. Range selectors retain them, including axes of
length one. Omitted trailing axes remain whole.

```
m = [1, 2; 3, 4]
m[1,1..2]       -> [1, 2]       -- shape [2]
m[1..1,1..2]    -> [1, 2;]      -- shape [1, 2]
m[..,2]         -> [2, 4]       -- shape [2]
m[..,2..2]      -> [2; 4]       -- shape [2, 1]
m[2..2]         -> [3, 4;]      -- shape [1, 2]
```

## Arrays

An array takes one selector. A range returns an array, preserving element order
and types. Chain brackets to select inside a nested value.

```
a = #[1, [2, 3], "four"]
a[2..]          -> ⟨[2, 3], "four"⟩
a[2..2][1][2]   -> 3
a[3..1]         -> ⟨⟩
```

## Bounds and errors

Range bounds and steps must be exact integers; booleans and floats are rejected.
The start and explicit endpoint must lie within the axis, even when the step
does not reach the endpoint. Bounds are never clipped. The second term defines
the step and need not itself be within the axis.

For a length-4 vector, `v[(1,4..5)]` fails because endpoint 5 is out of bounds;
`v[(2,10..4)]` selects only entry 2. Zero steps are errors.

Empty selections return empty arrays; empty tensor slices are errors.
`a[..]` works when `a` is empty. Bare `..` is only a complete index selector;
`..3`, `(..)`, and standalone `..` are not expressions.

[^ranges]: Slices use the existing [range rules](grammar.md#ranges). Plain `4..1`
    has step +1 and selects nothing; descending ranges require a second term.
    Selection computes a finite extent without iterating an infinite range.
