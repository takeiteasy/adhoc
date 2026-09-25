"""Tensor structure: shape bookkeeping, indexing, transpose, and contraction.

No arithmetic on user values happens here — `runtime.py` (the numeric seam) passes in the
scalar operations, so every element combines through `nadd`/`nmul`/... like any other
number. Items are stored flat, row-major, next to their shape.
"""

from dataclasses import dataclass
from itertools import product
from math import prod
from typing import Any, Callable


class TensorError(Exception):
    """A shape or index failure; the seam re-raises it as a spanned `NumError`."""


@dataclass(frozen=True)
class TensorValue:
    shape: tuple[int, ...]
    items: tuple[Any, ...]

    @property
    def rank(self) -> int:
        return len(self.shape)


def _strides(shape: tuple[int, ...]) -> list[int]:
    strides = [1] * len(shape)
    for k in range(len(shape) - 2, -1, -1):
        strides[k] = strides[k + 1] * shape[k + 1]
    return strides


def stack(parts: list) -> TensorValue:
    """`[a, b, c]`: scalars make a vector; equal-shape tensors stack into one more axis."""
    tensors = [isinstance(p, TensorValue) for p in parts]
    if not any(tensors):
        return TensorValue((len(parts),), tuple(parts))
    if not all(tensors):
        raise TensorError("a tensor literal cannot mix numbers and tensors")
    if any(p.shape != parts[0].shape for p in parts):
        raise TensorError("tensor literal entries have different shapes")
    return TensorValue((len(parts),) + parts[0].shape,
                       tuple(item for p in parts for item in p.items))


def from_rows(items: list, row_length: int) -> TensorValue:
    """`[a, b; c, d]`: scalar rows of one length make a matrix."""
    if any(isinstance(item, TensorValue) for item in items):
        raise TensorError("`;` rows hold numbers; nest `[...]` for higher ranks")
    return TensorValue((len(items) // row_length, row_length), tuple(items))


def index(t: TensorValue, indices: tuple[int, ...]) -> Any:
    """1-based index into the leading axes; fewer indices than axes gives a sub-tensor."""
    if len(indices) > t.rank:
        raise TensorError(f"{len(indices)} indices for a rank-{t.rank} tensor")
    offset = 0
    for axis, (i, stride) in enumerate(zip(indices, _strides(t.shape))):
        if not 1 <= i <= t.shape[axis]:
            raise TensorError(f"index {i} out of range 1..{t.shape[axis]}")
        offset += (i - 1) * stride
    rest = t.shape[len(indices):]
    if not rest:
        return t.items[offset]
    return TensorValue(rest, t.items[offset:offset + prod(rest)])


def slices(t: TensorValue) -> list:
    """The outer slices: scalars of a vector, sub-tensors of anything higher."""
    return [index(t, (i,)) for i in range(1, t.shape[0] + 1)]


def transpose(t: TensorValue) -> TensorValue:
    """Reverse the axes; a vector is unchanged."""
    if t.rank < 2:
        return t
    shape = t.shape[::-1]
    strides = _strides(t.shape)[::-1]
    items = tuple(t.items[sum(i * s for i, s in zip(idx, strides))]
                  for idx in product(*(range(n) for n in shape)))
    return TensorValue(shape, items)


def map1(f: Callable, t: TensorValue) -> TensorValue:
    return TensorValue(t.shape, tuple(f(item) for item in t.items))


def map2(f: Callable, a: Any, b: Any) -> TensorValue:
    """Elementwise `f`; a scalar operand broadcasts, two tensors need equal shapes."""
    if not isinstance(b, TensorValue):
        return TensorValue(a.shape, tuple(f(item, b) for item in a.items))
    if not isinstance(a, TensorValue):
        return TensorValue(b.shape, tuple(f(a, item) for item in b.items))
    if a.shape != b.shape:
        raise TensorError(f"shape mismatch {_show_shape(a.shape)} vs {_show_shape(b.shape)}")
    return TensorValue(a.shape, tuple(f(x, y) for x, y in zip(a.items, b.items)))


def contract(mul: Callable, add: Callable, a: TensorValue, b: TensorValue) -> Any:
    """Contract the last axis of `a` with the first axis of `b`."""
    k = a.shape[-1]
    if b.shape[0] != k:
        raise TensorError(f"cannot contract shape {_show_shape(a.shape)} "
                          f"with {_show_shape(b.shape)}")
    rows = prod(a.shape[:-1])
    cols = prod(b.shape[1:])
    items = []
    for i in range(rows):
        for j in range(cols):
            total = mul(a.items[i * k], b.items[j])
            for l in range(1, k):
                total = add(total, mul(a.items[i * k + l], b.items[l * cols + j]))
            items.append(total)
    shape = a.shape[:-1] + b.shape[1:]
    return TensorValue(shape, tuple(items)) if shape else items[0]


def _show_shape(shape: tuple[int, ...]) -> str:
    return "x".join(str(n) for n in shape)
