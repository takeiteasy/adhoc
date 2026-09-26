# Standard library

Prelude functions. Exact arguments stay exact where a tier can hold them; floats stay on
the float tier. Every name is protected: it cannot be rebound or shadowed.

## Number theory

| Function | Result | Example |
|---|---|---|
| `a % b`, `a \mod b` | floored modulo; rationals and symbolic reals work | `-7 % 3` → `2` |
| `\gcd(a, b, …)` `\lcm(…)` | arguments or one collection of exact integers | `\gcd(⟨12, 18⟩)` → `6` |
| `\divmod(a, b)` | `⟨⌊a/b⌋, a % b⟩` | `\divmod(-7, 3)` → `⟨-3, 2⟩` |
| `\isprime(n)` | boolean | `\isprime(97)` → `true` |
| `\factor(n)` | prime factors with repetition, up to 10¹⁸ | `\factor(360)` → `⟨2, 2, 2, 3, 3, 5⟩` |
| `\choose(n, k)` `\perm(n, k)` | binomial and falling factorial, `n ≤ 100000` | `\choose(5, 2)` → `10` |
| `\fib(n)` | Fibonacci number, `n ≤ 1000000` | `\fib(10)` → `55` |

`%` sits at the multiplicative level; `\mod` is the same operator, and `(%)` and `(\mod)`
are its function value. `%` by zero is `division by zero`; a float modulo by `0.0` is `NaN`.

## Functions

| Function | Result | Example |
|---|---|---|
| `\exp(x)` | eˣ | `\exp(0)` → `1` |
| `\log(b, x)` | logarithm of `x` in base `b`; `\log(x)` is `\ln(x)` | `\log(2, 8)` → `3` |
| `\sinh \cosh \tanh` | hyperbolics | `\cosh(0)` → `1` |
| `\asinh \acosh \atanh` | inverse hyperbolics | `\atanh(0)` → `0` |
| `\atan2(y, x)` | angle of the point `(x, y)` | `\atan2(1, 1)` → `π/4` |
| `\gamma(x)` | Γ; `x!` is `\gamma(x + 1)` | `\gamma(5)` → `24` |
| `\erf(x)` | error function | `\erf(0)` → `0` |

Exact arguments stay exact where a closed form exists (`\log(1/2, 8)` is `-3`,
`\gamma(1/2)` is `√π`); otherwise the value is held to arbitrary precision, like `\sin(1)`.
`\exp`, `\sin` and the other paired functions have `⁻¹` inverses (`\exp⁻¹` is `\ln`,
`\sinh⁻¹` is `\asinh`). Poles and other undefined points are typed errors.
`\atan2` is the one `\`-name that ends in a digit.

## Rounding

| Function | Result | Example |
|---|---|---|
| `\floor(x)` | greatest integer ≤ x | `\floor(-5/2)` → `-3` |
| `\ceil(x)` | least integer ≥ x | `\ceil(\pi)` → `4` |
| `\trunc(x)` | toward zero | `\trunc(-5/2)` → `-2` |
| `\round(x)` | nearest integer, ties away from zero | `\round(-5/2)` → `-3` |
| `\round(x, n)` | round to `n` decimal digits (`n` may be negative) | `\round(22/7, 2)` → `157/50` |
| `\abs(x)` | magnitude; on a complex value, the modulus | `\abs(3+4i)` → `5` |
| `\sign(x)` | `-1`, `0` or `1` | `\sign(-\pi)` → `-1` |

Exact and symbolic arguments give exact integers; non-finite floats pass through.
Complex arguments are a typed error, except for `\abs`.
