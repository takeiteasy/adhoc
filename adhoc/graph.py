"""Adaptive sampling of float coordinates; user evaluation stays in the runtime."""

from dataclasses import dataclass
import heapq
import math
from collections.abc import Callable

DEFAULT_TOLERANCE = 0.001
DEFAULT_MAX_POINTS = 4097
INITIAL_POINTS = 33
MAX_DEPTH = 24


@dataclass(frozen=True)
class GraphBreak:
    start: float
    end: float
    reason: str


@dataclass(frozen=True)
class GraphValue:
    axis: str
    axis_spelling: str
    label: str
    bounds: tuple[float, float]
    samples: tuple[tuple[float, float | None], ...]
    breaks: tuple[GraphBreak, ...]
    evaluations: int
    tolerance: float
    maxpoints: int
    complete: bool
    stopping_reasons: tuple[str, ...]

    @property
    def segments(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        """Connected finite samples, excluding every invalid or unresolved interval."""
        result, current = [], []
        index = 0
        for x, y in self.samples:
            if y is None:
                if current:
                    result.append(tuple(current))
                    current = []
                continue
            if current:
                previous = current[-1][0]
                while index < len(self.breaks) and self.breaks[index].end <= previous:
                    index += 1
                if index < len(self.breaks):
                    gap = self.breaks[index]
                    if previous < gap.end and x > gap.start:
                        result.append(tuple(current))
                        current = []
            current.append((x, y))
        if current:
            result.append(tuple(current))
        return tuple(result)


@dataclass(frozen=True)
class GraphCollectionValue:
    graphs: tuple[GraphValue, ...]


def _coordinate(lo: float, hi: float, fraction: float) -> float:
    return min(hi, max(lo, lo * (1 - fraction) + hi * fraction))


def sample(evaluate: Callable[[float], float | None], lo: float, hi: float, *,
           axis: str, axis_spelling: str, label: str,
           tolerance: float = DEFAULT_TOLERANCE,
           maxpoints: int = DEFAULT_MAX_POINTS) -> GraphValue:
    cache: dict[float, float | None] = {}
    breaks: list[GraphBreak] = []
    reasons: set[str] = set()
    pending: list[tuple[float, float, float, int]] = []

    def probe(x):
        if x not in cache:
            cache[x] = evaluate(x)
        return cache[x]

    def points(a, b):
        return (a, *(_coordinate(a, b, t) for t in (0.25, 0.5, 0.75)), b)

    def stop(a, b, reason):
        breaks.append(GraphBreak(a, b, reason))
        reasons.add(reason)

    def assess(a, b, depth):
        # TODO: finite probes miss narrow features; add feature-aware seeds (#52).
        coordinates = points(a, b)
        needed = set(coordinates) - cache.keys()
        if len(cache) + len(needed) > maxpoints:
            stop(a, b, "budget")
            return
        values = tuple(probe(x) for x in coordinates)
        if all(y is None for y in values):
            breaks.append(GraphBreak(a, b, "invalid"))
            return
        if len(set(coordinates)) < 5:
            stop(a, b, "precision")
            return
        if any(y is None for y in values):
            error = math.inf
        else:
            scale = max(1.0, *(abs(y) for y in values))
            left, right = values[0] / scale, values[-1] / scale
            error = max(abs(y / scale - (left * (1 - t) + right * t))
                        for t, y in zip((0.25, 0.5, 0.75), values[1:-1]))
        if error <= tolerance:
            return
        if depth >= MAX_DEPTH:
            stop(a, b, "depth")
            return
        heapq.heappush(pending, (-error, a, b, depth))

    if lo == hi:
        if probe(lo) is None:
            breaks.append(GraphBreak(lo, hi, "invalid"))
    else:
        seeds = sorted({lo, hi, *(_coordinate(lo, hi, i / (INITIAL_POINTS - 1))
                                  for i in range(1, INITIAL_POINTS - 1))})
        for x in seeds:
            probe(x)
        for a, b in zip(seeds, seeds[1:]):
            assess(a, b, 0)
        while pending:
            _, a, b, depth = heapq.heappop(pending)
            middle = _coordinate(a, b, 0.5)
            needed = set(points(a, middle) + points(middle, b)) - cache.keys()
            if len(cache) + len(needed) > maxpoints:
                stop(a, b, "budget")
                continue
            assess(a, middle, depth + 1)
            assess(middle, b, depth + 1)

    merged: list[GraphBreak] = []
    for gap in sorted(breaks, key=lambda gap: (gap.start, gap.end)):
        if merged and merged[-1].end == gap.start and merged[-1].reason == gap.reason:
            previous = merged.pop()
            gap = GraphBreak(previous.start, gap.end, gap.reason)
        merged.append(gap)
    return GraphValue(axis, axis_spelling, label, (lo, hi), tuple(sorted(cache.items())),
                      tuple(merged), len(cache), tolerance, maxpoints,
                      not reasons, tuple(sorted(reasons)))
