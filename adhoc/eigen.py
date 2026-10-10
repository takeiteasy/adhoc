"""Exact and numerical eigensystems on backend scalar values."""

import numpy as np
import sympy

from .tensor import TensorError


def exact(rows: list[list[sympy.Expr]]) -> list[tuple]:
    matrix = sympy.Matrix(rows)
    if any(value.is_finite is not True for value in matrix):
        raise TensorError("\\eig needs finite numeric entries")
    try:
        spaces = matrix.eigenvects(error_when_incomplete=True)
    except (NotImplementedError, sympy.matrices.exceptions.MatrixError) as error:
        raise TensorError("\\eig cannot compute this exact eigensystem") from error
    if sum(multiplicity for _, multiplicity, _ in spaces) != matrix.rows:
        raise TensorError("\\eig cannot compute a complete exact eigensystem")
    result = []
    for value, multiplicity, basis in spaces:
        if not basis:
            raise TensorError("\\eig cannot compute a complete exact eigensystem")
        columns = []
        for vector in basis:
            pivot = next(entry for entry in vector if entry != 0)
            columns.append([sympy.cancel(entry / pivot) for entry in vector])
        result.append((value, multiplicity, columns))
    return result


def numerical(rows: list[list[complex]]) -> list[tuple]:
    matrix = np.asarray(rows, dtype=np.complex128)
    if not np.isfinite(matrix).all():
        raise TensorError("\\eig needs finite numeric entries")
    try:
        values, vectors = np.linalg.eig(matrix)
    except np.linalg.LinAlgError as error:
        raise TensorError("\\eig numerical computation did not converge") from error
    result = []
    for value, vector in zip(values, vectors.T):
        vector = vector / np.linalg.norm(vector)
        index = int(np.argmax(np.abs(vector)))
        pivot = vector[index]
        vector = vector * (pivot.conjugate() / abs(pivot))
        vector[index] = abs(pivot)
        if not np.isfinite(value) or not np.isfinite(vector).all():
            raise TensorError("\\eig numerical result is not finite")
        result.append((complex(value), 1, [[complex(entry) for entry in vector]]))
    return result
