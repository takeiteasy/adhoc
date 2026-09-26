# Standard library

Prelude functions. Exact arguments stay exact where a tier can hold them; floats stay on
the float tier. Every name is protected: it cannot be rebound or shadowed.

## Complex

| Function | Result | Example |
|---|---|---|
| `\conj(z)` | complex conjugate | `\conj(3+4i)` -> `3-4i` |
| `\arg(z)` | angle in `(-π, π]`, an error at zero | `\arg(-1)` -> `π` |
| `\abs(z)` `\|z\|` | modulus (see Rounding) | `\abs(3+4i)` -> `5` |
| `\polar(r, θ)` `r∠θ` `r \angle θ` | `r·cos θ + r·sin θ·i` | `2∠(π/2)` -> `2i` |
| `\re(z)` `\im(z)` | components | `\im(3+4i)` -> `4` |

`∠` binds looser than `+` and tighter than comparison, so `2∠π/2` is `2∠(π/2)` and
`2∠π/2 ≈ 2i` is `true`. It does not chain: `1∠2∠3` is a parse error. `(∠)` is its function
value, and `(2 ∠)` and `(∠ π)` are sections. A float radius or angle gives a complex float:
`2.∠1` is `1.0806046117362795+1.682941969615793i`.

`\abs` and `\arg` simplify trig identities in their result, so `\abs(2∠1)` is `2` and
`\arg(2∠3)` is `3`. The components of `r∠θ` for a non-special angle stay decimal-displayed
(`1∠π/3` shows `0.5...+0.866025403784439...i`).

## Aggregates

Each takes several arguments or one collection (array, set, tensor, range) unless noted.

| Function | Result | Example |
|---|---|---|
| `\min(…)` `\max(…)` | smallest, largest | `\max(⟨3, 1, 2⟩)` -> `3` |
| `\mean(…)` `\median(…)` | exact where the inputs are | `\mean(⟨1, 2, 4⟩)` -> `7/3` |
| `\stdev(…)` `\sstdev(…)` | population and sample deviation | `\stdev(⟨1, 2⟩)` -> `1/2` |
| `\sort(xs)` | ascending; a set gives an array | `\sort({3, 1, 2})` -> `⟨1, 2, 3⟩` |
| `\reverse(xs)` | reversed; a set is an error | `\reverse(⟨1, 2, 3⟩)` -> `⟨3, 2, 1⟩` |
| `\any(p, xs)` `\all(p, xs)` | short-circuit tests with a predicate | `\all(\fn(x) x > 0, 1..5)` -> `true` |
| `\count(p, xs)` | elements satisfying `p` | `\count(\fn(x) x % 2 ≠ 0, 1..10)` -> `5` |
| `\zip(a, b, …)` | array of tuples, cut to the shortest; lazy when every argument is infinite | `\zip(⟨1, 2⟩, ⟨3, 4⟩)` -> `⟨⟨1, 3⟩, ⟨2, 4⟩⟩` |
| `\enumerate(xs)` | `⟨⟨1, x₁⟩, ⟨2, x₂⟩, …⟩`, 1-based like indexing; lazy over an infinite input | `\enumerate(⟨7, 8⟩)` -> `⟨⟨1, 7⟩, ⟨2, 8⟩⟩` |

Ordering rejects complex values and booleans. Empty input is a typed error, except that
`\any` of nothing is `false`, `\all` is `true` and `\count` is `0`. `\any` and `\all` also
search infinite ranges and give a typed "undecided" error after 2,000,000 elements;
the other aggregates need finite input.

## Number theory

| Function | Result | Example |
|---|---|---|
| `a % b`, `a \mod b` | floored modulo; rationals and symbolic reals work | `-7 % 3` -> `2` |
| `\gcd(a, b, …)` `\lcm(…)` | arguments or one collection of exact rationals; gcd is the gcd of numerators over the lcm of denominators, lcm the reverse. With a Gaussian value among them, all must be Gaussian rationals and the result is the associate in the first quadrant | `\gcd(⟨12, 18⟩)` -> `6`, `\gcd(1/2, 1/3)` -> `1/6`, `\gcd(6, 3+3i)` -> `3+3i`, `\gcd(1/2+i, 1)` -> `1/2` |
| `\divmod(a, b)` | `⟨⌊a/b⌋, a % b⟩` | `\divmod(-7, 3)` -> `⟨-3, 2⟩` |
| `\isprime(n)` | boolean | `\isprime(97)` -> `true` |
| `\factor(q)` | positive rational as `⟨p, exponent⟩` pairs, denominator primes negative; numerator and denominator up to 10¹⁸ | `\factor(12/5)` -> `⟨⟨2, 2⟩, ⟨3, 1⟩, ⟨5, -1⟩⟩` |
| `\factor(z)` | nonzero Gaussian rational, numerator norm and denominator up to 10¹⁸: first-quadrant primes sorted by norm, denominator primes negative, led by `⟨unit, 1⟩` when the unit is not 1 | `\factor(2+2i)` -> `⟨⟨-i, 1⟩, ⟨1+i, 3⟩⟩`, `\factor((1+i)/2)` -> `⟨⟨i, 1⟩, ⟨1+i, -1⟩⟩` |
| `\choose(n, k)` `\perm(n, k)` | binomial and falling factorial, `n ≤ 100000` | `\choose(5, 2)` -> `10` |
| `\fib(n)` | Fibonacci number, `n ≤ 1000000` | `\fib(10)` -> `55` |

`%` sits at the multiplicative level; `\mod` is the same operator, and `(%)` and `(\mod)`
are its function value. `%` by zero is `division by zero`; a float modulo by `0.0` is `NaN`.

## Functions

| Function | Result | Example |
|---|---|---|
| `\exp(x)` | eˣ | `\exp(0)` -> `1` |
| `\log(b, x)` | logarithm of `x` in base `b`, complex arguments included (`\ln(x)/\ln(b)`); `\log(x)` is `\ln(x)` | `\log(2, 8)` -> `3` |
| `\sinh \cosh \tanh` | hyperbolics | `\cosh(0)` -> `1` |
| `\asinh \acosh \atanh` | inverse hyperbolics | `\atanh(0)` -> `0` |
| `\atan2(y, x)` | angle of the real point `(x, y)`; use `\arg` for a complex value | `\atan2(1, 1)` -> `π/4` |
| `\gamma(x)` | Γ; `x!` is `\gamma(x + 1)` | `\gamma(5)` -> `24` |
| `\erf(x)` | error function | `\erf(0)` -> `0` |

Exact arguments stay exact where a closed form exists (`\log(1/2, 8)` is `-3`,
`\gamma(1/2)` is `√π`); otherwise the value is held to arbitrary precision, like `\sin(1)`.
`\exp`, `\sin` and the other paired functions have `⁻¹` inverses (`\exp⁻¹` is `\ln`,
`\sinh⁻¹` is `\asinh`). Poles and other undefined points are typed errors.
`\atan2` is the one `\`-name that ends in a digit.

## Rounding

| Function | Result | Example |
|---|---|---|
| `\floor(x)` `⌊x⌋` | greatest integer ≤ x | `⌊-5/2⌋` -> `-3` |
| `\ceil(x)` `⌈x⌉` | least integer ≥ x | `⌈\pi⌉` -> `4` |
| `\trunc(x)` | toward zero | `\trunc(-5/2)` -> `-2` |
| `\round(x)` | nearest integer, ties away from zero | `\round(-5/2)` -> `-3` |
| `\round(x, n)` | round to `n` decimal digits (`n` may be negative) | `\round(22/7, 2)` -> `157/50` |
| `\abs(x)` `\|x\|` | magnitude; on a complex value, the modulus | `\|3+4i\|` -> `5` |
| `\sign(x)` | `-1`, `0` or `1` | `\sign(-\pi)` -> `-1` |

Exact and symbolic arguments give exact integers; non-finite floats pass through.
Complex arguments are a typed error, except for `\abs`.

## Linear algebra

Matrices are order-2 tensors. Elimination is exact on the rational, Gaussian and symbolic
tiers; a float or complex-float matrix is pivoted by size.[^pivot]

| Function | Result | Example |
|---|---|---|
| `\det(A)` `\tr(A)` | determinant, trace of a square matrix | `\det([1, 2; 3, 4])` -> `-2` |
| `\inv(A)` | inverse; a singular matrix is an error | `\inv([1, 2; 3, 4])` -> `[-2, 1; 3/2, -1/2]` |
| `\linsolve(A, b)` | `x` with `A x = b`; `b` is a vector or a matrix of right-hand sides | `\linsolve([2, 1; 1, 3], [3, 5])` -> `[4/5, 7/5]` |
| `\rank(A)` `\rref(A)` | matrix rank, reduced row echelon form | `\rank([1, 2; 2, 4])` -> `1` |
| `\eye(n)` | identity | `\eye(2)` -> `[1, 0; 0, 1]` |
| `\zeros(n, …)` `\ones(n, …)` | filled tensor of the given dimensions | `\zeros(2, 3)` -> `[0, 0, 0; 0, 0, 0]` |
| `\diag(v)` `\diag(A)` | a vector gives a diagonal matrix, a matrix gives its diagonal | `\diag([1, 2])` -> `[1, 0; 0, 2]` |
| `\norm(x)` `‖x‖` | 2-norm of a vector, Frobenius norm of a matrix, `\abs` of a number | `\norm([3, 4])` -> `5` |
| `a × b` `\cross(a, b)` | cross product of two length-3 vectors | `[1, 0, 0] × [0, 1, 0]` -> `[0, 0, 1]` |
| `a ⊗ b` `\outer(a, b)` | tensor product, shapes concatenate | `[1, 2] ⊗ [3, 4]` -> `[3, 4; 6, 8]` |
| `\kron(a, b)` | Kronecker product of two vectors or two matrices | `\kron([1, 2], [3, 4])` -> `[3, 4, 6, 8]` |
| `\reshape(t, n, …)` | same entries, new dimensions | `\reshape([1, 2, 3, 4], 2, 2)` -> `[1, 2; 3, 4]` |
| `\concat(a, b, …)` | join along the first axis; tensors of one trailing shape, or arrays | `\concat([1, 2], [3])` -> `[1, 2, 3]` |
| `\stack(a, b, …)` | numbers make a vector, equal-shape tensors gain an axis | `\stack([1, 2], [3, 4])` -> `[1, 2; 3, 4]` |

`×` and `⊗` sit at the `*` level and fall back to `*` when an operand is a scalar
(`2 × [1, 2]` is `[2, 4]`). `A⁻¹` is elementwise like every `^` on a tensor; use `\inv`.
Tensors are limited to 1,000,000 entries when built by `\eye`, `\zeros`, `\ones`, `\diag`,
`\outer` and `\kron`.

[^pivot]: Exact entries pivot on the first nonzero. If any entry is a float, each pivot is the
    largest magnitude in its column, so `\inv([1e-20, 1; 1, 1])` stays accurate.

## Limitations

- Float elimination tests pivots against exact zero, so a nearly singular float matrix
  inverts to huge values and `\rank` counts round-off — [#98](https://todo.sr.ht/~takeiteasy/adhoc/98).
- No `\eig` — [#99](https://todo.sr.ht/~takeiteasy/adhoc/99).
- `\lim` with a complex anchor probes eight rays, so a body that vanishes on all of them (`\im((x - a)^4)/\abs(x - a)^4`) reads as a limit — [#97](https://todo.sr.ht/~takeiteasy/adhoc/97).
