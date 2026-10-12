"""SVD-based matrix operations on finite backend float values."""

import math

import numpy as np

from .tensor import TensorError


def _array(rows: list[list]) -> np.ndarray:
    values = np.asarray(rows, dtype=np.complex128)
    if not np.isfinite(values).all():
        raise TensorError("matrix elimination cannot convert entries to finite floats")
    return values.real.copy() if not np.any(values.imag) else values


def _ldexp(values: np.ndarray, exponent) -> np.ndarray:
    if np.iscomplexobj(values):
        result = np.empty_like(values)
        result.real = np.ldexp(values.real, exponent)
        result.imag = np.ldexp(values.imag, exponent)
        return result
    return np.ldexp(values, exponent)


def _exponent(values: np.ndarray) -> int:
    scale = max(float(np.max(np.abs(values.real))), float(np.max(np.abs(values.imag))))
    return math.frexp(scale)[1]


def _finite(values: np.ndarray, name: str) -> np.ndarray:
    if not np.isfinite(values).all():
        raise TensorError(f"\\{name} numerical result is not finite")
    return values


def _rref(matrix: np.ndarray, basis: np.ndarray, rank: int) -> np.ndarray:
    rows = basis[:rank].copy()
    rows[:, np.all(matrix == 0, axis=0)] = 0
    pivots = []
    for column in range(matrix.shape[1]):
        row = len(pivots)
        if row == rank:
            break
        pivot_row = row + int(np.argmax(np.abs(rows[row:, column])))
        if rows[pivot_row, column] == 0:
            continue
        rows[[row, pivot_row]] = rows[[pivot_row, row]]
        rows[row] /= rows[row, column]
        rows[row, column] = 1
        for other in range(rank):
            if other != row:
                rows[other] -= rows[other, column] * rows[row]
                rows[other, column] = 0
        pivots.append(column)
    if len(pivots) != rank:
        raise TensorError("\\rref numerical reduction lost a required pivot")
    result = np.zeros(matrix.shape, dtype=matrix.dtype)
    result[:rank] = _finite(rows, "rref")
    result[result == 0] = 0
    return result


def _solve(matrix: np.ndarray, u: np.ndarray, singular: np.ndarray,
           vh: np.ndarray, right: np.ndarray, exponent: int, name: str) -> np.ndarray:
    right_exponents = np.array([_exponent(right[:, column])
                                for column in range(right.shape[1])])
    normalized = _ldexp(right, -right_exponents)

    def apply(rhs):
        return vh.conj().T @ ((u.conj().T @ rhs) / singular[:, None])

    result = apply(normalized)
    residual = normalized - matrix @ result
    # Residual refinement preserves small entries lost in SVD factor cancellation.
    for _ in range(8):
        candidate = result + apply(residual)
        next_residual = normalized - matrix @ candidate
        improved = np.max(np.abs(next_residual), axis=0) < np.max(np.abs(residual), axis=0)
        if not np.any(improved):
            break
        result[:, improved] = candidate[:, improved]
        residual[:, improved] = next_residual[:, improved]
    return _finite(_ldexp(result, right_exponents - exponent), name)


def _det(u: np.ndarray, singular: np.ndarray, vh: np.ndarray, exponent: int):
    left_sign, left_log = np.linalg.slogdet(u)
    right_sign, right_log = np.linalg.slogdet(vh)
    sign = left_sign * right_sign
    logarithm = math.fsum([float(left_log), float(right_log),
                          *(math.log(float(value)) for value in singular),
                          len(singular) * exponent * math.log(2)])
    if sign == 0 or not np.isfinite(logarithm):
        raise TensorError("\\det numerical computation failed for a full-rank matrix")

    def component(value):
        if value == 0:
            return 0.0
        try:
            return math.copysign(math.exp(logarithm + math.log(abs(value))), value)
        except OverflowError as error:
            raise TensorError("\\det is outside float range") from error

    result = complex(component(sign.real), component(sign.imag))
    if result == 0:
        raise TensorError("\\det is outside float range")
    return result


def compute(name: str, rows: list[list], right: list[list] | None = None):
    matrix = _array(rows)
    rhs = None if right is None else _array(right)
    if not np.any(matrix):
        if name in {"rank", "det"}:
            return 0
        if name == "rref":
            return matrix.tolist()
        raise TensorError(f"\\{name} of a singular matrix")
    exponent = _exponent(matrix)
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        normalized = _ldexp(matrix, -exponent)
        try:
            u, singular, vh = np.linalg.svd(normalized, full_matrices=False)
        except np.linalg.LinAlgError as error:
            raise TensorError("matrix SVD numerical computation did not converge") from error
        if not all(np.isfinite(value).all() for value in (u, singular, vh)):
            raise TensorError("matrix SVD numerical result is not finite")
        cutoff = float(singular[0]) * max(matrix.shape) * np.finfo(float).eps
        rank = int(np.count_nonzero(singular > cutoff))
        if name == "rank":
            return rank
        if name == "rref":
            return _rref(normalized, vh, rank).tolist()
        if rank < matrix.shape[0]:
            if name == "det":
                return 0
            raise TensorError(f"\\{name} of a singular matrix")
        if name == "det":
            return _det(u, singular, vh, exponent)
        if name == "inv":
            rhs = np.eye(matrix.shape[0])
        return _solve(normalized, u, singular, vh, rhs, exponent, name).tolist()
