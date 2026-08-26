"""Caret-pointing diagnostic rendering. Takes `(source, label, message, span)` rather than
an error value, so the REPL and script mode share it unchanged.

Spans are byte offsets; this module is the one place that converts them to *character*
columns for display — `π` is 2 bytes and 1 column, and getting that conversion wrong
misplaces every caret after a unicode character on the line.

Column model is character count, not display width: a genuinely full-width or combining
identifier character will make the caret land slightly off. Accepted — see
docs/language.md — rather than taking a unicode-width dependency for a case that
essentially never arises in a calculator.
"""

from .span import Span


def _byte_to_char_map(source: str) -> dict[int, int]:
    """Map byte offsets to character indices, including one past the last byte."""
    mapping: dict[int, int] = {}
    byte_off = 0
    for char_idx, ch in enumerate(source):
        mapping[byte_off] = char_idx
        byte_off += len(ch.encode("utf-8"))
    mapping[byte_off] = len(source)
    return mapping


def render(source: str, label: str, message: str, span: Span) -> str:
    """Render a caret-pointing diagnostic to a string, e.g.:

        < ERROR! unexpected token `*`
            1 + * 2
                ^

    4-space indent; tabs in the source line are expanded to single spaces so columns stay
    aligned; the caret is `^` followed by `span_len - 1` tildes, clamped to the line; a
    `N: ` line-number gutter appears only when `source` contains a newline.
    """
    b2c = _byte_to_char_map(source)
    start_c = b2c[span.start]
    end_c = b2c[span.end]

    line_no = source.count("\n", 0, start_c) + 1
    line_start = source.rfind("\n", 0, start_c) + 1
    newline = source.find("\n", line_start)
    line_end = newline if newline != -1 else len(source)

    multiline = "\n" in source
    prefix = f"{line_no}: " if multiline else ""

    line_text = source[line_start:line_end].replace("\t", " ")

    col = start_c - line_start
    line_char_len = len(line_text)
    clamped_end = min(end_c, line_end)
    span_len_chars = max(clamped_end - start_c, 1) if clamped_end > start_c else 1
    span_len_chars = min(span_len_chars, max(line_char_len - col, 1))

    out = f"< {label} {message}\n"
    out += f"    {prefix}{line_text}\n"
    out += "    "
    out += " " * (len(prefix) + col)
    out += "^"
    out += "~" * (span_len_chars - 1)
    out += "\n"
    return out
