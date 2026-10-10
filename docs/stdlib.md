# Standard library

Prelude functions keep exact arguments exact and floats inexact. Function names
are protected: they cannot be rebound or shadowed. See
[numerics](numerics.md) for numeric tiers and the
[prelude](grammar.md#the-prelude) for constants and core functions.

## Complex

| Function or notation | Result | Example |
|---|---|---|
| `\conj(z)` | Complex conjugate | `\conj(3+4i)` → `3-4i` |
| `\arg(z)` | Angle in `(-π, π]`; error at zero | `\arg(-1)` → exact π |
| `\abs(z)`, `\|z\|` | Modulus | `\abs(3+4i)` → `5` |
| `\polar(r, θ)`, `r∠θ`, `r \angle θ` | `r·cos θ + r·sin θ·i` | `2∠(π/2)` → `2i` |
| `\re(z)`, `\im(z)` | Real or imaginary component | `\im(3+4i)` → `4` |

### Polar notation

`∠` binds looser than addition and tighter than comparisons:
`2∠π/2` means `2∠(π/2)`, and `2∠π/2 ≈ 2i` is `true`.
It cannot chain: `1∠2∠3` is a parse error.

| Form | Use |
|---|---|
| `(∠)` | Operator as a function value |
| `(2 ∠)`, `(∠ π)` | Fix the radius or angle |
| `2.∠1` | Float radius selects complex float arithmetic |

`\abs` and `\arg` simplify trigonometric identities: `\abs(2∠1)` is `2` and
`\arg(2∠3)` is `3`. Exact components display approximate digits when needed:
`1∠π/3` prints `0.5...+0.866025403784439...i`.[^polar-float]

## Aggregates

### Statistics

Statistics accept several arguments or one finite array, set, tensor or range.
Empty input is a typed error; sample deviation needs at least two values.
Ordering rejects complex values and booleans.

| Function | Result | Example |
|---|---|---|
| `\min(…)`, `\max(…)` | Smallest or largest value | `\max(⟨3, 1, 2⟩)` → `3` |
| `\mean(…)`, `\median(…)` | Mean or median; exact for exact inputs | `\mean(⟨1, 2, 4⟩)` → `7/3` |
| `\stdev(…)` | Population standard deviation | `\stdev(⟨1, 2⟩)` → `1/2` |
| `\sstdev(…)` | Sample standard deviation | `\sstdev(⟨1, 3⟩)^2` → `2` |

### Ordering and predicates

| Function | Result | Example |
|---|---|---|
| `\sort(xs)` | Ascending; a set returns an array | `\sort({3, 1, 2})` → `⟨1, 2, 3⟩` |
| `\reverse(xs)` | Reverse an ordered collection; sets are rejected | `\reverse(⟨1, 2, 3⟩)` → `⟨3, 2, 1⟩` |
| `\any(p, xs)` | Stop at the first true predicate result | `\any(\fn(x) x > 2, 1..5)` → `true` |
| `\all(p, xs)` | Stop at the first false predicate result | `\all(\fn(x) x > 0, 1..5)` → `true` |
| `\count(p, xs)` | Count matching elements | `\count(\fn(x) x % 2 ≠ 0, 1..10)` → `5` |

Predicates must return booleans. `\sort`, `\reverse` and `\count` require finite
input; empty collections produce empty results or a count of `0`.
For empty input, `\any` is `false` and `\all` is `true`.

`\any` and `\all` can search infinite inputs. They report a typed “undecided”
error if no deciding element appears within 2,000,000 elements.

### Zip and enumerate

| Function | Result | Example |
|---|---|---|
| `\zip(a, b, …)` | Array of rows, stopping at the shortest input | `\zip(⟨1, 2⟩, ⟨3, 4⟩)` → `⟨⟨1, 3⟩, ⟨2, 4⟩⟩` |
| `\enumerate(xs)` | Array of index–value pairs, starting at 1 | `\enumerate(⟨7, 8⟩)` → `⟨⟨1, 7⟩, ⟨2, 8⟩⟩` |

`\zip` requires at least two inputs and is lazy when all inputs are infinite.
With a finite input, it consumes only as many elements as the shortest finite
input supplies. `\enumerate` is lazy over infinite input.

```text
\take(2, \zip(1.., 2..))       ->  = ⟨⟨1, 2⟩, ⟨2, 3⟩⟩
\take(2, \enumerate(7..))      ->  = ⟨⟨1, 7⟩, ⟨2, 8⟩⟩
```

See [lazy sequences](grammar.md#infinite-ranges-and-lazy-sequences) for consumers.

## Number theory

| Function or operator | Result | Example |
|---|---|---|
| `a % b`, `a \mod b` | Floored remainder; supports rationals and symbolic reals | `-7 % 3` → `2` |
| `\gcd(…)`, `\lcm(…)` | GCD or LCM of exact rationals or Gaussian rationals | `\gcd(⟨12, 18⟩)` → `6` |
| `\divmod(a, b)` | `⟨⌊a/b⌋, a % b⟩` | `\divmod(-7, 3)` → `⟨-3, 2⟩` |
| `\isprime(n)` | Primality boolean for an exact integer | `\isprime(97)` → `true` |
| `\choose(n, k)` | Binomial coefficient | `\choose(5, 2)` → `10` |
| `\perm(n, k)` | Falling factorial | `\perm(5, 2)` → `20` |
| `\fib(n)` | Fibonacci number | `\fib(10)` → `55` |

`\choose` and `\perm` take non-negative exact integers, with `n ≤ 100000`.
`\fib` takes a non-negative exact integer up to `1000000`.

`%` and `\mod` share multiplicative precedence; `(%)` and `(\mod)` are their
function value. An exact zero divisor is a typed division-by-zero error;
a float modulo zero is `NaN`.

### GCD and LCM

Pass several values or one finite collection. Rational results are exact.
If any argument is Gaussian, all arguments must be Gaussian rationals
(including ordinary rational values); the result is the first-quadrant associate.[^gcd]

```text
\gcd(1/2, 1/3)       ->  = 1/6
\gcd(6, 3+3i)        ->  = 3+3i
\gcd(1/2+i, 1)       ->  = 1/2
```

### Factoring

`\factor` dispatches by argument kind:

| Input | Result | Bound |
|---|---|---|
| Positive rational | Array of prime–exponent pairs; denominator exponents are negative | Numerator and denominator ≤ 10¹⁸ |
| Nonzero Gaussian rational | First-quadrant prime–exponent pairs, sorted by norm; optional leading unit pair | Scaled numerator norm and denominator ≤ 10¹⁸ |
| Expression quote or function | Factored expression quote | [Symbolic rewrite limits](symbolic.md#limitations) |

A Gaussian factorization starts with `⟨unit, 1⟩` when its unit is not `1`.
Denominator prime exponents are negative.

```text
\factor(12/5)            ->  = ⟨⟨2, 2⟩, ⟨3, 1⟩, ⟨5, -1⟩⟩
\factor(2+2i)            ->  = ⟨⟨-i, 1⟩, ⟨1+i, 3⟩⟩
\factor((1+i)/2)         ->  = ⟨⟨i, 1⟩, ⟨1+i, -1⟩⟩
\factor(\expr(x^2 - 1))  ->  = \expr(((x + 1) * (x - 1)))
```

See [symbolic rewriting](symbolic.md) for factoring quotes and functions.

## Functions

| Function | Result | Example |
|---|---|---|
| `\exp(x)` | eˣ | `\exp(0)` → `1` |
| `\log(b, x)` | Base-`b` logarithm; complex arguments supported | `\log(2, 8)` → `3` |
| `\log(x)` | Natural logarithm, equivalent to `\ln(x)` | `\log(1)` → `0` |
| `\sinh`, `\cosh`, `\tanh` | Hyperbolic functions | `\cosh(0)` → `1` |
| `\asinh`, `\acosh`, `\atanh` | Inverse hyperbolic functions | `\atanh(0)` → `0` |
| `\atan2(y, x)` | Angle of the real point `(x, y)` | `\atan2(1, 1)` → exact π/4 |
| `\gamma(x)` | Gamma function; `x!` is `\gamma(x + 1)` | `\gamma(5)` → `24` |
| `\erf(x)` | Error function | `\erf(0)` → `0` |

Exact results retain a closed form where available: `\log(1/2, 8)` is `-3` and
`\gamma(1/2)` is `√π`. Other exact results use arbitrary precision, as with
`\sin(1)`. Complex logarithms use `\ln(x)/\ln(b)`.
`\atan2` requires real arguments; use `\arg` for a complex value.

Paired functions support `⁻¹` inverses: `\exp⁻¹` is `\ln` and `\sinh⁻¹` is
`\asinh`. Poles and other undefined points produce typed errors.
`\atan2` is the backslash name that permits a final digit.

## Rounding

| Function or notation | Result | Example |
|---|---|---|
| `\floor(x)`, `⌊x⌋` | Greatest integer ≤ x | `⌊-5/2⌋` → `-3` |
| `\ceil(x)`, `⌈x⌉` | Least integer ≥ x | `⌈\pi⌉` → `4` |
| `\trunc(x)` | Round toward zero | `\trunc(-5/2)` → `-2` |
| `\round(x)` | Nearest integer; ties away from zero | `\round(-5/2)` → `-3` |
| `\round(x, n)` | Round to `n` decimal places; negative `n` allowed | `\round(22/7, 2)` → `157/50` |
| `\abs(x)`, `\|x\|` | Scalar magnitude, complex modulus or [matrix determinant](#matrix-operations) | `\|3+4i\|` → `5` |
| `\sign(x)` | Sign: `-1`, `0` or `1` | `\sign(-\pi)` → `-1` |

Integer-rounding operations return exact integers for exact inputs.
Rounding to decimal places preserves exactness and can return a rational.
Rounding operations pass non-finite floats through. Complex arguments are typed
errors except for `\abs`. See [float semantics](numerics.md#float-semantics) for inexact rounding.

## Linear algebra

Matrices are order-2 tensors. Elimination preserves exactness for rational,
Gaussian and symbolic entries. Float matrices choose pivots by magnitude.[^pivot]

### Matrix operations

| Function | Result | Example |
|---|---|---|
| `\det(A)`, `\abs(A)`, `\|A\|` | Signed determinant of a square matrix | `\|[1, 2; 3, 4]\|` → `-2` |
| `\tr(A)` | Trace of a square matrix | `\tr([1, 2; 3, 4])` → `5` |
| `\inv(A)` | Inverse; singular matrices produce an error | `\inv([1, 2; 3, 4])` → `[-2, 1; 3/2, -1/2]` |
| `\linsolve(A, b)` | Solve `A x = b`; `b` is a vector or matrix of right-hand sides | `\linsolve([2, 1; 1, 3], [3, 5])` → `[4/5, 7/5]` |
| `\rank(A)`, `\rref(A)` | Rank or reduced row echelon form | `\rank([1, 2; 2, 4])` → `1` |
| `\eig(A)` | Array of eigenvalue, multiplicity and basis-matrix records | `\eig([5;])` → `⟨⟨5, 1, [1;]⟩⟩` |
| `\norm(x)`, `‖x‖` | Vector 2-norm, matrix Frobenius norm or scalar magnitude | `\norm([3, 4])` → `5` |

`\abs(A)` and `|A|` reject vectors, nonsquare matrices and higher-order tensors.
Use `‖A‖` for the matrix Frobenius norm.

`A⁻¹` is elementwise exponentiation. Use `\inv(A)` for matrix inversion.
See [eigenvalues and eigenvectors](eigen.md) for record indexing and exact/float
behavior, and [limitations](#limitations) for computation limits.

### Tensor construction and shape

| Function | Result | Example |
|---|---|---|
| `\eye(n)` | Identity matrix | `\eye(2)` → `[1, 0; 0, 1]` |
| `\zeros(n, …)`, `\ones(n, …)` | Filled tensor of the given dimensions | `\zeros(2, 3)` → `[0, 0, 0; 0, 0, 0]` |
| `\diag(v)`, `\diag(A)` | Vector to diagonal matrix; matrix to diagonal vector | `\diag([1, 2])` → `[1, 0; 0, 2]` |
| `\reshape(t, n, …)` | Same entries, new dimensions | `\reshape([1, 2, 3, 4], 2, 2)` → `[1, 2; 3, 4]` |
| `\concat(a, b, …)` | Join arrays or tensors with matching trailing shapes along the first axis | `\concat([1, 2], [3])` → `[1, 2, 3]` |
| `\stack(a, b, …)` | Numbers form a vector; equal-shape tensors gain an axis | `\stack([1, 2], [3, 4])` → `[1, 2; 3, 4]` |

`\eye`, `\zeros`, `\ones`, `\diag`, `\outer` and `\kron` limit constructed
tensors to 1,000,000 entries.

### Products

| Function or operator | Result | Example |
|---|---|---|
| `a × b`, `\cross(a, b)` | Cross product of length-3 vectors | `[1, 0, 0] × [0, 1, 0]` → `[0, 0, 1]` |
| `a ⊗ b`, `\outer(a, b)` | Tensor product; shapes concatenate | `[1, 2] ⊗ [3, 4]` → `[3, 4; 6, 8]` |
| `\kron(a, b)` | Kronecker product of two vectors or two matrices | `\kron([1, 2], [3, 4])` → `[3, 4, 6, 8]` |

`×` and `⊗` share multiplication precedence. With a scalar operand they multiply:
`2 × [1, 2]` is `[2, 4]`.

## Limitations

- Float elimination tests pivots against exact zero. Nearly singular float
  matrices can invert to huge values, and `\rank` can count round-off:
  [#5](https://github.com/takeiteasy/adhoc/issues/5).
- Exact `\eig` computations depend on symbolic solvability and the time budget;
  float eigenpairs do not certify multiplicity or independence. See
  [eigensystem limitations](eigen.md#limitations):
  [#6](https://github.com/takeiteasy/adhoc/issues/6).
- Complex-anchor `\lim` probes eight fixed rays. A body that vanishes on those
  angles can pass despite having no limit; finite probes cannot prove a limit.

[^polar-float]: `2.∠1` displays `1.0806046117362795+1.682941969615793i`.
    A float radius or angle selects the complex float tier; exact components
    remain exact despite decimal display.

[^gcd]: Rational GCD is the GCD of numerators divided by the LCM of denominators.
    Rational LCM is the LCM of numerators divided by the GCD of denominators.
    Gaussian results choose an equivalent associate in the first quadrant.

[^pivot]: Exact entries pivot on the first nonzero value. With a float or complex
    float entry, the pivot is the largest magnitude in its column. For example,
    `\inv([1e-20, 1; 1, 1])` remains accurate.
