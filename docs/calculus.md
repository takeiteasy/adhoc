# Calculus

`\diff` and `\int` compute numeric derivatives and integrals. Function derivatives
(`f'`, `f''`, …) and inverses (`f⁻¹`) use exact symbolic results when the body
supports them, otherwise numeric methods. Failure to converge is a typed error.

| Form | Meaning |
|---|---|
| `\diff(x=a) body`, `∂(x=a) body` | Numeric derivative at a real point |
| `\int(x=a..b) body`, `∫(x=a..b) body` | Numeric integral over `[a, b]` |
| `\int(x=a..) body` | Numeric integral over `[a, ∞)` |
| `f'`, `f''`, `f'''`, … | Derivative function; exact to any order, numeric to order 2 |
| `f⁻¹` | Inverse function, returning one branch |

```text
\diff(x=1) \sin(x)          ->  = 0.5403023058681385
∫(x=0..π) \sin(x)           ->  = 2.0
∫(x=0..) e^(-x)             ->  = 1.0
f(x) = x^3
f'(2)                       ->  = 12
f'(2.)                      ->  = 11.999999999999986
f⁻¹(8)                      ->  = 2
(x ↦ 2x)⁻¹(6)               ->  = 3
```

## Binders

`\diff` and `\int` are [special forms](grammar.md#special-forms-folds-and-limits).
Their first parentheses bind a variable; the body extends over the rest of the
expression. The variable stays local, as a function parameter does. `∂` and `∫`
are name aliases of `\diff` and `\int`.

Numeric methods return floats or complex floats. The body may be complex;
`\diff` requires a real anchor.

## Derivatives

### Numeric binder

`\diff(x=a)` probes `a ± h` without evaluating at `a`. It shrinks the step and
extrapolates until the relatively scaled error estimate is within `1e-9`, or
reports `did not converge`.[^ridders]

### Function derivatives

Postfix `'` applies to definitions, lambdas, compositions, prelude functions
and Python callables. The result is an ordinary function: it maps, composes
and displays as `<fn f′>`.

| Function and argument | Method |
|---|---|
| One-parameter definition or lambda with a supported symbolic body; exact integer, rational or Gaussian point | Exact derivative, cached per function, to any order |
| Other function or float point, first derivative | Numeric differences; tolerance `1e-9` |
| Other function or float point, second derivative | Numeric second differences; tolerance `1e-6`; evaluates at the anchor |
| Numeric derivative above order 2 | Typed error |

For `f(x) = x^3`, `f'(1/2)` is exactly `3/4`.
See [symbolic rewriting](symbolic.md) for supported bodies and `\deriv`.

On tensors, `'` remains transpose. `ᵀ` always means transpose and is an error on
a function.

## Integrals

Adaptive integration stops when its summed error estimate is within `1e-12`,
scaled by the integrand's magnitude. It reports `did not converge` after 2,000
subintervals.[^quadrature]

| Bound or body | Behavior |
|---|---|
| Finite endpoints | Endpoints are never evaluated |
| Reversed bounds | Negate the result |
| Upper-infinite `a..` | Integrate through a finite-interval transformation |
| Stepped range | Typed error |
| Divergent or slowly decaying body | Can exhaust the convergence budget |

For example, `∫(x=0..1) 1/√x` is approximately `2`, and
`∫(x=1..0) x` is `-0.5`. Symbolic integration is not implemented.

## Inverses

Paired prelude functions return their paired inverse: `\sin⁻¹` is `\asin`,
`\exp⁻¹` is `\ln`, and so on.

Other inverses solve `f(x) = y` and return the root nearest `y`. If distances tie,
the root with the larger real part wins. For `f(x) = x^2`, `f⁻¹(4)` is `2`;
[solving](symbolic.md#solving) can return both roots. `(f⁻¹)⁻¹` is `f`.

| Function and argument | Result |
|---|---|
| User function with an exactly solvable body and exact `y` | Exact root; complex `y` supported |
| Other function or float `y` | Numeric root nearest `y`; real `y` required[^inverse] |
| No preimage or a jump | Typed “no value maps to” error |

`(x ↦ 2x)⁻¹(6)` is `3`. For `f(x) = x^2`, `f⁻¹(3+4i)` is `2+i` and
`f⁻¹(-1)` has no real preimage. `\floor⁻¹(2.5)` reports a jump error.

## Limitations

| Limit | Ticket |
|---|---|
| Integral bounds are finite or upper-infinite `a..`; no `-\inf` or whole-line bounds | [#8](https://github.com/takeiteasy/adhoc/issues/8) |
| Numeric derivatives above order 2 are errors; symbolic derivatives support higher orders | [#9](https://github.com/takeiteasy/adhoc/issues/9) |
| `f⁻¹` returns one branch; no set-valued inverse | [#17](https://github.com/takeiteasy/adhoc/issues/17) |
| `\diff` at a kink returns the mean slope: `\diff(x=0) \|x\|` is `0.0` | [#10](https://github.com/takeiteasy/adhoc/issues/10) |

[^ridders]: Ridders' method uses central differences with a step shrinking by
    1.4 per row, combined by Richardson extrapolation. It keeps the entry with
    the smallest error estimate. The initial step is `0.1·|a|`, or `0.1` at zero.

[^quadrature]: Globally adaptive Gauss–Kronrod uses 7- and 15-point rules and
    bisects the panel with the largest error estimate. An infinite range maps
    through `x = a + t/(1-t)`.

[^inverse]: A bracket grows outward from `y` until `f(x) - y` changes sign, then
    bisects. A tangent root falls back to a secant walk. The residual is checked
    before returning.
