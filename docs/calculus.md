# Calculus

Derivatives, integrals and inverses: `\diff`, `\int`, `f'` and `f⁻¹`. They run in the float tier and
return a float (a complex float for a complex body), or a typed error when they do not
converge. `f'`, `f''` and `f⁻¹` are exact when the function body is symbolic (docs/symbolic.md).

| Form | Meaning |
|---|---|
| `\diff(x=a) body`, `∂(x=a) body` | derivative of `body` at `a` |
| `\int(x=a..b) body`, `∫(x=a..b) body` | integral of `body` over `[a, b]` |
| `\int(x=a..) body` | integral over `[a, ∞)` |
| `f'`, `f''`, `f'''`... | the derivatives of a function, as a function; exact where the body allows, numeric to order 2 |
| `f⁻¹` | the numeric inverse of a function, as a function |

```
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

`\diff` and `\int` are special forms like `\lim` (`docs/grammar.md`, `## Special forms`):
the first argument is a binding, the body extends over the rest of the expression, and the
variable scopes like a function parameter. `∂` and `∫` are aliases of the `\`-names.

## Derivatives

`\diff(x=a) body` never evaluates the body at `a` itself. It differences the body at
`a ± h` and extrapolates as `h` shrinks[^ridders]; it returns when the error estimate is
within `1e-9` (relatively scaled) and is otherwise a `did not converge` error. The anchor is
real; the body may be complex.

`f'`, `f''`, `f'''` and so on apply to any function value: a definition, a lambda, a composition, a prelude
function or a Python callable. At an exact point (an integer, fraction or Gaussian), a
one-parameter definition or lambda whose body bridges to sympy is differentiated exactly, once
per function, to any order: `f'(1/2)` is `3/4` for `x^3`. Anything else, and any float point,
is numeric, and only orders 1 and 2 exist there: `f''` uses second differences (tolerance `1e-6`) and does evaluate `f(a)`. Postfix `'` on a tensor is still the transpose, so `A'` is unchanged; `ᵀ` is
always the transpose and is an error on a function. The result of `f'` is an ordinary
function: it passes to `\map`, composes, and displays as `<fn f′>`.

## Integrals

`\int(x=a..b) body` integrates adaptively[^quadrature] until the summed error estimate is
within `1e-12` (scaled by the integrand's magnitude), or errors after 2,000 subintervals.
Endpoints are never evaluated, so `∫(x=0..1) 1/√x` is `2`. A reversed range negates
(`∫(x=1..0) x` is `-0.5`); a stepped range is an error. A diverging or slowly decaying
integrand on `a..` ends in `did not converge`.

## Inverses

`f⁻¹` on a function without a paired inverse (anything but `\sin`, `\exp` and the other
prelude pairs, which give `\asin`, `\ln`, …) is a function whose value at `y` is the root of
`f(x) = y` nearest `y`. When `f` is not one-to-one the nearest root wins, the larger real part
on a tie (`f(x) = x^2` gives `f⁻¹(4)` as `2`; `\solve` gives both, docs/symbolic.md). A `y` with no
preimage (`f⁻¹(-1)` for `x^2`) or a jump (`\floor⁻¹(2.5)`) is a `no value maps to` error.
`(f⁻¹)⁻¹` is `f`.

| Case | Result |
|---|---|
| user function with a body that solves exactly, exact `y` | exact root, `y` may be complex: `(x ↦ 2x)⁻¹(6)` is `3`, `f⁻¹(3+4i)` is `2+i` for `x^2` |
| any other function, or a float `y` | float root nearest `y`[^inverse], real `y` only |

## Limitations

| Limit | Ticket |
|---|---|
| Only finite bounds and `a..`; no `-\inf` or whole-line bounds | [#101](https://todo.sr.ht/~takeiteasy/adhoc/101) |
| Derivatives above the second order are an error | [#102](https://todo.sr.ht/~takeiteasy/adhoc/102) |
| `f⁻¹` returns one branch; no set-valued inverse | [#117](https://todo.sr.ht/~takeiteasy/adhoc/117) |
| `\diff` at a kink reads as the mean slope (`\diff(x=0) \|x\|` is `0.0`) | [#103](https://todo.sr.ht/~takeiteasy/adhoc/103) |

Symbolic derivatives and integrals are not built; `\simplify` and friends are in docs/symbolic.md.

[^ridders]: Ridders' method: central differences with a step shrinking by 1.4 per row,
    combined by Richardson extrapolation, keeping the entry with the smallest error
    estimate. The first step is `0.1·|a|` (`0.1` at `0`).
[^inverse]: A bracket grows outward from `y` until `f(x) − y` changes sign, then bisects; a
    tangent root falls back to a secant walk. The residual is checked before returning.
[^quadrature]: Globally adaptive Gauss–Kronrod (7 and 15 points): the panel with the largest
    error estimate bisects. An infinite range maps through `x = a + t/(1-t)`.
