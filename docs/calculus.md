# Calculus

`\diff` and `\int` compute numeric derivatives and integrals. Function derivatives
(`f'`, `f''`, …) and inverses (`f⁻¹`) use exact symbolic results when the body
supports them, otherwise numeric methods. Failure to converge is a typed error.

| Form | Meaning |
|---|---|
| `\diff(x=a) body`, `∂(x=a) body` | Numeric derivative at a real point |
| `\diff(x=a, n) body`, `∂(x=a, n) body` | Numeric derivative of positive integer order `n` |
| `\int(x=a..b) body`, `∫(x=a..b) body` | Numeric integral over `[a, b]` |
| `\int(x=a..) body` | Numeric integral over `[a, ∞)` |
| `\int(x=-\inf..b) body` | Numeric integral over `(-∞, b]` |
| `\int(x=-\inf..\inf) body`, `\int(x=-\inf..) body` | Numeric integral over the whole real line |
| `\int(x=r) body` | Integral over stored range or interval bounds |
| `f'`, `f''`, `f'''`, … | Derivative function; exact or numeric, subject to numeric convergence and resource limits |
| `f⁻¹` | Inverse function, returning one branch |

```text
\diff(x=1) \sin(x)          -> approximately 0.5403023058681387
∫(x=0..π) \sin(x)           ->  = 2.0
∫(x=0..) e^(-x)             ->  = 1.0
f(x) = x^3
f'(2)                       ->  = 12
f'(2.)                      -> approximately 12.0
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

`\diff(x=a, n)` differentiates to order `n`; omitting `n` means the first
derivative. The point and order evaluate once in the surrounding scope, before
the body binds `x`. The order must be a positive integer; booleans and float
orders such as `3.` are errors.

```text
\diff(x=1, 3) x^4           -> approximately 24.0
∂(x=0, 6) x^6              -> approximately 720.0
\diff(x=0) |x|             -> error: derivative does not exist
\diff(x=0, 2) x*|x|        -> error: derivative does not exist
```

Numeric differentiation compares independent left and right estimates of nearby
value limits and every derivative through order `n`. A converged disagreement
reports `derivative does not exist`; insufficient precision reports
`did not converge`. Central and one-sided estimates must also agree.[^ridders]

| Order | Relatively scaled tolerance | Evaluates at the anchor? |
|---|---|---|
| 1 | `1e-9` | No |
| 2 | `1e-6` | Yes |
| 3 and higher | `1e-3` | Even orders only |

These are numerical error estimates, not proofs of differentiability. Near-only
first-order probes cannot detect a value changed solely at the anchor. Oscillatory
bodies and rounding-sensitive higher derivatives may fail to converge even when
the mathematical derivative exists.

Each stencil has at most 32 points, and each numeric call allows at most 2,000 body
evaluations. One-sided stencils use `n+3` points, so numeric orders above 29 report
a typed resource-limit error before evaluating the body. Exact symbolic derivatives
are unaffected by these budgets.

### Function derivatives

Postfix `'` applies to definitions, lambdas, compositions, prelude functions
and Python callables. The result is an ordinary function: it maps, composes
and displays as `<fn f′>`.

| Function and argument | Method |
|---|---|
| One-parameter definition or lambda with a supported symbolic body; exact integer, rational or Gaussian point | Exact derivative, cached per function, to any order |
| Other function or float point | Numeric differences with the same tolerances, agreement checks and budgets as `\diff` |

For `f(x) = x^3`, `f'(1/2)` is exactly `3/4`.
See [symbolic rewriting](symbolic.md) for supported bodies and `\deriv`.

On tensors, `'` remains transpose. `ᵀ` always means transpose and is an error on
a function.

## Integrals

Adaptive integration stops when its summed error estimate is within `1e-12`,
scaled by the integrand's magnitude. It reports `did not converge` after 2,000
subintervals per finite interval or infinite tail.[^quadrature]

| Bound or body | Behavior |
|---|---|
| Finite endpoints | Endpoints are never evaluated |
| Reversed bounds | Negate the result |
| Upper-infinite `a..` | Integrate through a finite-interval transformation |
| Explicit infinite endpoints | Reusable, non-iterable [interval bounds](intervals.md) |
| Whole line | Split at zero; both tails must converge independently |
| Stepped range | Typed error |
| Divergent or slowly decaying body | Can exhaust the convergence budget |

For example, `∫(x=0..1) 1/√x` is approximately `2`, and
`∫(x=1..0) x` is `-0.5`. Symbolic integration is not implemented.

```text
r = -\inf..\inf
∫(x=r) 1/(1+x^2)            ->  = 3.141592653589793
∫(x=-\inf..0) e^x           ->  = 1.0
∫(x=0..-\inf) e^x           ->  = -1.0
```

Whole-line integration requires ordinary improper convergence. For example,
`∫(x=-\inf..\inf) x/(1+x^2)` reports `did not converge`; its tails do not
converge independently.

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
| `f⁻¹` returns one branch; no set-valued inverse | [#17](https://github.com/takeiteasy/adhoc/issues/17) |

[^ridders]: Cached finite-difference weights define symmetric central stencils
    and separate one-sided stencils without the anchor. Richardson extrapolation
    uses each stencil's error powers over ten rows, shrinking the step by 1.4
    per row. Each estimate retains the entry with the smallest error, including
    a floating-point rounding estimate. Agreement allows twice the applicable
    tolerance, scaled by `max(1, |left|, |right|)`; nearby value limits use `1e-9`.
    The initial step is `0.1·|a|`, or `0.1` at zero, doubled above order two.
    Samples are shared within a call; function bodies should be deterministic.

[^quadrature]: Globally adaptive Gauss–Kronrod uses 7- and 15-point rules and
    bisects the panel with the largest error estimate. Upper-infinite bounds map
    through `x = a + t/(1-t)`; lower-infinite bounds use `x = b - t/(1-t)`.
    Both transformations use Jacobian magnitude `1/(1-t)²` on `(0, 1)` and
    never sample the endpoints. Whole-line integration sums two independently
    converged tails split at zero; each has its own error estimate and budget.

[^inverse]: A bracket grows outward from `y` until `f(x) - y` changes sign, then
    bisects. A tangent root falls back to a secant walk. The residual is checked
    before returning.
