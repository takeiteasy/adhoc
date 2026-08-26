from adhoc.diagnostic import render
from adhoc.span import Span


def test_golden_caret_string():
    out = render("1 + * 2", "ERROR!", "unexpected token `*`", Span(4, 5))
    assert out == "< ERROR! unexpected token `*`\n    1 + * 2\n        ^\n"


def test_no_gutter_on_single_line():
    out = render("x", "ERROR!", "boom", Span(0, 1))
    assert ":" not in out


def test_gutter_on_multiline_source():
    out = render("a=1; y:=2\nnext", "ERROR!", "boom", Span(5, 9))
    assert "1: " in out


def test_unicode_caret_column():
    # π is 2 bytes, 1 char/column. The caret must point at `x`, which follows it, not two
    # columns after — a byte-offset caret would land one column too far right.
    src = "π + x"
    span = Span(5, 6)  # byte offsets: 'π'=0..2, ' '=2, '+'=3, ' '=4, 'x'=5..6
    out = render(src, "ERROR!", "unbound", span)
    caret_col = out.splitlines()[2].find("^")
    assert caret_col == 8  # 4-space indent + char column 4 within the line
