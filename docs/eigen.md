# Eigenvalues and eigenvectors

`\eig(A)` returns right eigenvectors and eigenvalues of a square matrix.
Exact matrices preserve the numeric tower; any float entry selects numerical
computation for the whole matrix.

## Result records

The result is an array of `⟨eigenvalue, multiplicity, basis matrix⟩` records.
Vectors occupy columns of the basis matrix. Record order and the choice of
basis within a repeated eigenspace are unspecified.

| Input | Records | Multiplicity | Basis matrix |
|---|---|---|---|
| Exact | One per distinct eigenvalue | Algebraic multiplicity | `n×k`, with `k` independent eigenvectors |
| Contains a float | One per computed eigenpair | Always `1`; one numerical result | `n×1`, one approximate vector |

An exact matrix can have fewer independent eigenvectors than its size:

```text
\eig([1, 1; 0, 1])
< = ⟨⟨1, 2, [1; 0]⟩⟩
```

Here the eigenvalue `1` occurs twice in the characteristic polynomial, but its
eigenspace has only one basis vector. Generalised eigenvectors are not returned.

## Indexing and checking

Arrays and tensors use 1-based indexing. Select a basis column with a range
selector on its rows:

```text
a = [1, 1; 0, 1]
x = \eig(a)
l = x[1][1]
b = x[1][3]
v = b[..,1]
w = a @ v
w = l v
< true
```

`x[1][2]` is the multiplicity. `\shape(b)[2]` is the number of basis vectors.
Run [the eigen demo](../demos/eigen.ad) with `adhoc run demos/eigen.ad`.

## Exact and float behavior

Exact entries include rational, Gaussian, symbolic, algebraic and RRA values.
Eigenvalues and vector entries pass through the existing numeric admission
gates, retaining exact expressions, including polynomial roots without radical
formulas. Non-algebraic results use the symbolic or RRA tier; unsupported exact
computations produce an error rather than a float fallback.

An exact basis vector has its first nonzero entry scaled to `1`.
Exact computation, normalization and value conversion share the symbolic
time limit.[^timeout]

Numerical computation uses NumPy. Results are floats or complex floats,
including results from mixed exact/float matrices. Each vector has unit norm;
its largest-magnitude component is positive real, with the first component
chosen on a tie. Zero imaginary components collapse to real floats.

Inputs must be square matrices of finite numbers. Booleans, strings, arrays,
nonfinite values and entries that cannot convert to finite floats are errors.
The constructed-tensor limit is 1,000,000 entries; `\eig` checks the matrix's
`n²` size before computation. Numerical nonconvergence and nonfinite results
are typed errors at the call site.

## Limitations

- Exact eigensystems depend on symbolic solvability and the time budget.
  Higher-degree roots can require a larger budget:
  [#6](https://github.com/takeiteasy/adhoc/issues/6).
- Float records do not certify algebraic multiplicity or eigenspace dimension.
  Nearby roots are not merged, and defective matrices can return dependent
  vectors. The result does not guarantee a diagonalising matrix.
- Bases for repeated eigenvalues can differ across backend versions, even
  with fixed vector scaling. Float checks require residual tolerances.

[^timeout]: `ADHOC_SYMBOLIC_TIMEOUT` sets the time limit in seconds (default `5`).
    A nonpositive value disables it. The existing worker mechanism also runs
    without a time limit on platforms without `fork`.
