# Infinite interval bounds

`a..b` creates a reusable, non-iterable interval when either endpoint is
infinite. Intervals supply bounds to [numeric integration](calculus.md#integrals)
and support real membership.

```text
r = -\inf..\inf             ->  r = <interval -Inf..Inf>
∫(x=r) 1/(1+x^2)             ->  = 3.141592653589793
0.5 ∈ r                      ->  = true
```

## Construction

| Form | Value |
|---|---|
| `-\inf..b` | Interval from negative infinity to `b` |
| `a..\inf` | Interval from `a` to positive infinity |
| `-\inf..\inf`, `-\inf..` | Whole-line interval |
| `b..-\inf`, `\inf..a`, `\inf..-\inf` | Reversed interval; integration negates |
| `a..b` with finite endpoints | Existing arithmetic progression |
| `a..` with a finite start | Existing lazy arithmetic progression |

Endpoints are real numbers. NaN, equal infinite endpoints and stepped infinite
bounds are typed errors. Omitting the upper endpoint means positive infinity,
so `\inf..` is an error.

## Membership and values

`∈` tests finite real membership between the endpoints, regardless of
orientation. It includes a finite boundary. Infinite values, NaN, non-real
numbers and non-numeric values are not members; `∉` gives the opposite result.

```text
-0.5 ∈ (-\inf..0)            ->  = true
0 ∈ (0..-\inf)               ->  = true
\inf ∈ (-\inf..\inf)         ->  = false
0.5 ∈ (0..1)                 ->  = false
0.5 ∈ (0..\inf)              ->  = true
```

Finite and open arithmetic progressions keep their term-based membership rules.

Intervals pass through functions and can be stored as array or set elements.
Equality compares ordered endpoints; reversing an interval changes its value.
`-\inf..` equals `-\inf..\inf`. An interval is distinct from a progression,
so `0..\inf` does not equal `0..`.

Intervals do not iterate. Folds, quantifiers, collection transforms, indexing,
length and arithmetic on an interval produce typed errors.

`\tex(r)` renders interval notation, with open infinite endpoints and closed
finite endpoints. Rendering preserves endpoint order.
