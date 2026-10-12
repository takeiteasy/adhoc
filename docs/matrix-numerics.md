# Matrix numerics

Float matrices share an SVD-based numerical rank across `\rank`, `\rref`,
`\det`, `\inv` and `\linsolve`. Exact coefficient matrices use exact pivots.

## Selecting arithmetic

| Coefficient matrix | Computation |
|---|---|
| Exact entries only | Scalar arithmetic through the exact numeric tiers |
| Any float or complex float | Whole matrix converted to finite floats; NumPy SVD |

The right-hand side does not select the arithmetic or affect rank classification.
Exact coefficients retain exact pivot tests even with a float right-hand side.
Nonfinite inputs and mixed matrices with entries outside float range produce
typed errors at the call site. Unit handling follows the
[standard matrix operations](stdlib.md#linear-algebra).

## Rank and singularity

Numerical rank counts singular values strictly above a relative
machine-precision threshold.[^threshold] Classification uses only coefficient
rows and columns. It is independent of `\prec` and has no user setting.

```text
\rank([1e-10, 1.; 0., 1e-10])  -- 1
\rank([1., 1e-10; 1e-10, 0.])  -- 1: columns reversed
```

For square matrices, every operation uses the same full-rank test:

| Classification | Determinant | Inverse and solve |
|---|---|---|
| Numerically singular | Exact zero | Singular-matrix error |
| Full rank | Float or complex float | Float or complex-float entries |

Full-rank inverse and solve use the SVD factors with residual refinement.
Right-hand sides can be vectors or matrices. Numerical results with nonfinite
entries produce an error. A full-rank determinant outside float range, including
underflow to zero, produces a range error rather than a singularity result.[^scaling]

## RREF

Float RREF reduces the row space retained by SVD, with columns in their original
order. It returns the input shape, with exactly `\rank(A)` nonzero rows and zero
rows at the bottom. Its entries are approximate, including when printed as `1.0`.

The retained basis is reduced without a second rank cutoff. All-zero input
columns remain zero. A reduction that loses a required pivot or produces
nonfinite entries gives a typed error. Exact RREF follows exact elimination.

## Limitations

- Singular values close to the threshold can fall on either side because of
  rounding or backend differences. SVD classification does not certify exact
  rank or solution accuracy: [#22](https://github.com/takeiteasy/adhoc/issues/22).
- Rank is invariant under row and column permutations in exact arithmetic;
  floating results near the threshold need not be identical.
- Tiny early RREF pivots can amplify error. Reclassifying the returned RREF
  can give a different numerical rank, despite its specified nonzero-row count.
- Float conversion, normalization and SVD can lose tiny components. RREF
  coefficients and pivot positions are sensitive to those losses.
- Inverse and solve permit finite underflowed components. Residual refinement
  does not certify forward accuracy for ill-conditioned matrices.

[^threshold]: For an `m×n` matrix with largest singular value `σmax`, retain
    `σ > σmax × max(m, n) × ε`, where `ε = 2^-52`. The all-zero matrix has rank
    zero without an SVD. See NumPy's
    [rank convention](https://numpy.org/doc/stable/reference/generated/numpy.linalg.matrix_rank.html).

[^scaling]: Coefficients are normalized by a power of two based on their largest
    absolute real or imaginary component. Each right-hand-side column is scaled
    independently; results are restored using binary exponents. The determinant
    combines the phases of the SVD factors and logarithms of their singular values.
    Refinement accepts residual-reducing corrections, up to eight iterations.
