import pytest

from adhoc.span import Span


def test_point_is_zero_width():
    assert Span.point(3) == Span(3, 3)


def test_to_covers_both():
    assert Span(4, 6).to(Span(1, 5)) == Span(1, 6)
    assert Span(0, 2).to(Span(2, 9)) == Span(0, 9)


def test_spans_are_immutable():
    with pytest.raises(Exception):
        Span(0, 1).start = 5


def test_start_may_not_exceed_end():
    with pytest.raises(ValueError):
        Span(5, 4)
