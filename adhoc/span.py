"""Source spans shared by every stage: lexer tokens, AST nodes, and diagnostics.

Offsets are **bytes**, 0-based, half-open (`[start, end)`), into the original source
string. Python string indexing is character-based, so a byte span must never be applied
directly as a slice — `diagnostic.render` is the one place that converts byte offsets to
character columns for display, and everything else treats spans as opaque.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    start: int
    end: int

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError(f"span start {self.start} exceeds end {self.end}")

    @classmethod
    def point(cls, pos: int) -> "Span":
        """A zero-width span at `pos` — used for EOF tokens and other point locations."""
        return cls(pos, pos)

    def to(self, other: "Span") -> "Span":
        """The smallest span covering both `self` and `other`."""
        return Span(min(self.start, other.start), max(self.end, other.end))
