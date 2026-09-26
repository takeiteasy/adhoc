"""Linear algebra on tensor values: elimination (det, inverse, solve, rank, rref),
constructors, and products.

Like `tensor.contract`, no arithmetic on user values happens here — `runtime.py` passes in
the scalar operations as a `Scalars`, so every entry combines through the numeric seam.
"""

from dataclasses import dataclass
from math import prod
from typing import Any, Callable

from .tensor import ArrayValue, TensorError, TensorValue, show_shape

MAX_ITEMS = 1_000_000


@dataclass(frozen=True)
class Scalars:
    """The seam operations linear algebra needs. `larger(a, b)` compares magnitudes and
    `inexact(v)` marks floats and complex floats, which are pivoted by size."""

    add: Callable
    sub: Callable
    mul: Callable
    div: Callable
    is_zero: Callable
    larger: Callable
    inexact: Callable


def _from_rows(rows: list[list]) -> TensorValue:
    return TensorValue((len(rows), len(rows[0])), tuple(v for row in rows for v in row))


def _rows(t: Any, name: str) -> list[list]:
    if not isinstance(t, TensorValue) or t.order != 2:
        raise TensorError(f"{name} needs a matrix")
    cols = t.shape[1]
    return [list(t.items[r * cols:(r + 1) * cols]) for r in range(t.shape[0])]


def _square(t: Any, name: str) -> list[list]:
    rows = _rows(t, name)
    if len(rows) != len(rows[0]):
        raise TensorError(f"{name} needs a square matrix, got shape {show_shape(t.shape)}")
    return rows


def _pick(s: Scalars, rows: list[list], r: int, c: int, by_size: bool) -> int | None:
    candidates = [i for i in range(r, len(rows)) if not s.is_zero(rows[i][c])]
    if not candidates:
        return None
    if not by_size:
        return candidates[0]
    best = candidates[0]
    for i in candidates[1:]:
        if s.larger(rows[i][c], rows[best][c]):
            best = i
    return best


def _eliminate(s: Scalars, rows: list[list], width: int) -> tuple[list[list], list[int], Any]:
    """Gauss-Jordan over the first `width` columns (the rest ride along). Returns the reduced
    rows, the pivot columns, and the product of the pivots with the sign of the row swaps —
    the determinant when every column pivoted."""
    # TODO: float pivots are tested against exact zero; a tolerance for near-singular
    # float matrices needs a design decision (ticket #98)
    rows = [list(row) for row in rows]
    by_size = any(s.inexact(v) for row in rows for v in row)
    pivots: list[int] = []
    det: Any = 1
    r = 0
    for c in range(width):
        if r == len(rows):
            break
        p = _pick(s, rows, r, c, by_size)
        if p is None:
            continue
        if p != r:
            rows[r], rows[p] = rows[p], rows[r]
            det = s.sub(0, det)
        pivot = rows[r][c]
        det = s.mul(det, pivot)
        rows[r] = [s.div(v, pivot) for v in rows[r]]
        for i in range(len(rows)):
            factor = rows[i][c]
            if i != r and not s.is_zero(factor):
                rows[i] = [s.sub(v, s.mul(factor, w)) for v, w in zip(rows[i], rows[r])]
        pivots.append(c)
        r += 1
    return rows, pivots, det


def det(s: Scalars, t: Any) -> Any:
    rows = _square(t, "\\det")
    _, pivots, product = _eliminate(s, rows, len(rows))
    return product if len(pivots) == len(rows) else 0


def inv(s: Scalars, t: Any) -> TensorValue:
    rows = _square(t, "\\inv")
    n = len(rows)
    augmented = [row + [1 if i == j else 0 for j in range(n)] for i, row in enumerate(rows)]
    reduced, pivots, _ = _eliminate(s, augmented, n)
    if len(pivots) < n:
        raise TensorError("\\inv of a singular matrix")
    return _from_rows([row[n:] for row in reduced])


def linsolve(s: Scalars, a: Any, b: Any) -> TensorValue:
    """Solve `A x = b` for a vector or matrix `b`; `A` must be square and nonsingular."""
    rows = _square(a, "\\linsolve")
    n = len(rows)
    if not isinstance(b, TensorValue) or b.order not in (1, 2) or b.shape[0] != n:
        raise TensorError(f"\\linsolve needs a right-hand side with {n} rows")
    right = [[x] for x in b.items] if b.order == 1 else _rows(b, "\\linsolve")
    reduced, pivots, _ = _eliminate(s, [row + rhs for row, rhs in zip(rows, right)], n)
    if len(pivots) < n:
        raise TensorError("\\linsolve of a singular matrix")
    solution = [row[n:] for row in reduced]
    if b.order == 1:
        return TensorValue((n,), tuple(row[0] for row in solution))
    return _from_rows(solution)


def rank(s: Scalars, t: Any) -> int:
    return len(_eliminate(s, _rows(t, "\\rank"), t.shape[1])[1])


def rref(s: Scalars, t: Any) -> TensorValue:
    return _from_rows(_eliminate(s, _rows(t, "\\rref"), t.shape[1])[0])


def trace(s: Scalars, t: Any) -> Any:
    rows = _square(t, "\\tr")
    total = rows[0][0]
    for i in range(1, len(rows)):
        total = s.add(total, rows[i][i])
    return total


def _size(shape: tuple[int, ...]) -> int:
    n = prod(shape)
    if n > MAX_ITEMS:
        raise TensorError(f"a tensor of {n} entries is over the limit of {MAX_ITEMS}")
    return n


def filled(value: Any, dims: list[int]) -> TensorValue:
    if not dims or any(d < 1 for d in dims):
        raise TensorError("dimensions must be positive integers")
    return TensorValue(tuple(dims), (value,) * _size(tuple(dims)))


def eye(n: int) -> TensorValue:
    if n < 1:
        raise TensorError("\\eye needs a positive size")
    _size((n, n))
    return TensorValue((n, n), tuple(1 if i == j else 0 for i in range(n) for j in range(n)))


def diag(t: Any) -> TensorValue:
    """A vector becomes a diagonal matrix, a matrix gives its diagonal."""
    if isinstance(t, TensorValue) and t.order == 1:
        n = t.shape[0]
        _size((n, n))
        return TensorValue((n, n), tuple(t.items[i] if i == j else 0
                                         for i in range(n) for j in range(n)))
    rows = _rows(t, "\\diag")
    return TensorValue((min(t.shape),), tuple(rows[i][i] for i in range(min(t.shape))))


def outer(s: Scalars, a: Any, b: Any) -> TensorValue:
    """Tensor product: the shapes concatenate."""
    if not (isinstance(a, TensorValue) and isinstance(b, TensorValue)):
        raise TensorError("\\outer needs two tensors")
    shape = a.shape + b.shape
    _size(shape)
    return TensorValue(shape, tuple(s.mul(x, y) for x in a.items for y in b.items))


def kron(s: Scalars, a: Any, b: Any) -> TensorValue:
    if not (isinstance(a, TensorValue) and isinstance(b, TensorValue)
            and a.order == b.order and a.order in (1, 2)):
        raise TensorError("\\kron needs two vectors or two matrices")
    if a.order == 1:
        return TensorValue((a.shape[0] * b.shape[0],), outer(s, a, b).items)
    ma, na = a.shape
    mb, nb = b.shape
    _size((ma * mb, na * nb))
    items = tuple(s.mul(a.items[i * na + j], b.items[k * nb + l])
                  for i in range(ma) for k in range(mb) for j in range(na) for l in range(nb))
    return TensorValue((ma * mb, na * nb), items)


def cross(s: Scalars, a: Any, b: Any) -> TensorValue:
    if not all(isinstance(v, TensorValue) and v.shape == (3,) for v in (a, b)):
        raise TensorError("a cross product needs two vectors of length 3")
    (a1, a2, a3), (b1, b2, b3) = a.items, b.items
    return TensorValue((3,), (s.sub(s.mul(a2, b3), s.mul(a3, b2)),
                              s.sub(s.mul(a3, b1), s.mul(a1, b3)),
                              s.sub(s.mul(a1, b2), s.mul(a2, b1))))


def reshape(t: Any, dims: list[int]) -> TensorValue:
    if not isinstance(t, TensorValue):
        raise TensorError("\\reshape needs a tensor")
    if not dims or any(d < 1 for d in dims):
        raise TensorError("dimensions must be positive integers")
    if prod(dims) != len(t.items):
        raise TensorError(f"cannot reshape {show_shape(t.shape)} into {show_shape(tuple(dims))}")
    return TensorValue(tuple(dims), t.items)


def concat(parts: list) -> Any:
    """Join along the first axis: tensors of one trailing shape, or arrays."""
    if all(isinstance(p, ArrayValue) for p in parts):
        return ArrayValue(tuple(item for p in parts for item in p.items))
    if not all(isinstance(p, TensorValue) for p in parts):
        raise TensorError("\\concat needs tensors, or arrays")
    if any(p.shape[1:] != parts[0].shape[1:] for p in parts):
        raise TensorError("\\concat needs tensors of the same shape past the first axis")
    return TensorValue((sum(p.shape[0] for p in parts),) + parts[0].shape[1:],
                       tuple(item for p in parts for item in p.items))
