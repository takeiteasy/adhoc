//! Caret-pointing diagnostic rendering. Takes `(source, label, message, span)` rather than
//! an error value, so the REPL and script mode (`main.rs`) share it unchanged.
//!
//! Spans are byte offsets; this module is the one place that converts them to *character*
//! columns for display — `π` is 2 bytes and 1 column, and getting that conversion wrong
//! misplaces every caret after a unicode character on the line.
//!
//! Column model is character count, not display width: a genuinely full-width or
//! combining identifier character will make the caret land slightly off, since char count
//! isn't terminal columns for those. Accepted — see `docs/language.md` — rather than taking
//! a `unicode-width` dependency for a case that essentially never arises in a calculator.

use crate::span::Span;

/// Byte offset -> 0-based character offset within `source`.
fn char_offset(source: &str, byte_offset: usize) -> usize {
    source[..byte_offset].chars().count()
}

/// `(line_start, line_end)` byte offsets (line_end exclusive of the newline) and the
/// 1-based line number containing `byte_offset`.
fn line_bounds(source: &str, byte_offset: usize) -> (usize, usize, usize) {
    let mut line_no = 1usize;
    let mut line_start = 0usize;
    for (i, ch) in source.char_indices() {
        if i >= byte_offset {
            break;
        }
        if ch == '\n' {
            line_no += 1;
            line_start = i + 1;
        }
    }
    let line_end = source[line_start..]
        .find('\n')
        .map(|off| line_start + off)
        .unwrap_or(source.len());
    (line_start, line_end, line_no)
}

/// Render a caret-pointing diagnostic to a string, e.g.:
///
/// ```text
/// < ERROR! unexpected token `*`
///     1 + * 2
///         ^
/// ```
///
/// 4-space indent; tabs in the source line are expanded to single spaces so columns stay
/// aligned; the caret is `^` followed by `span_len - 1` tildes, clamped to the line; a
/// `N: ` line-number gutter appears only when `source` contains a newline.
pub fn render(source: &str, label: &str, message: &str, span: Span) -> String {
    let start = span.start as usize;
    let end = span.end as usize;
    let (line_start, line_end, line_no) = line_bounds(source, start);
    let multiline = source.contains('\n');
    let prefix = if multiline { format!("{line_no}: ") } else { String::new() };

    let line_text: String =
        source[line_start..line_end].chars().map(|c| if c == '\t' { ' ' } else { c }).collect();

    let col = char_offset(source, start) - char_offset(source, line_start);
    let line_char_len = line_text.chars().count();
    let clamped_end = end.min(line_end);
    let span_len_chars = if clamped_end > start {
        (char_offset(source, clamped_end) - char_offset(source, start)).max(1)
    } else {
        1
    };
    let span_len_chars = span_len_chars.min(line_char_len.saturating_sub(col).max(1));

    let mut out = String::new();
    out.push_str(&format!("< {label} {message}\n"));
    out.push_str(&format!("    {prefix}{line_text}\n"));
    out.push_str("    ");
    out.push_str(&" ".repeat(prefix.chars().count() + col));
    out.push('^');
    out.push_str(&"~".repeat(span_len_chars - 1));
    out.push('\n');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn golden_caret_string() {
        let src = "1 + * 2";
        let span = Span::new(4, 5);
        let out = render(src, "ERROR!", "unexpected token `*`", span);
        assert_eq!(out, "< ERROR! unexpected token `*`\n    1 + * 2\n        ^\n");
    }

    #[test]
    fn no_gutter_on_single_line() {
        let out = render("x", "ERROR!", "boom", Span::new(0, 1));
        assert!(!out.contains(':'));
    }

    #[test]
    fn gutter_on_multiline_source() {
        let out = render("a=1; y:=2\nnext", "ERROR!", "boom", Span::new(5, 9));
        assert!(out.contains("1: "));
    }

    #[test]
    fn unicode_caret_column() {
        // `π` is 2 bytes, 1 char/column. Error should point at `x`, which follows it,
        // not two columns after — a byte-offset caret would land one column too far right.
        let src = "\u{3c0} + x";
        // byte offsets: 'π'=0..2, ' '=2, '+'=3, ' '=4, 'x'=5..6
        let span = Span::new(5, 6);
        let out = render(src, "ERROR!", "unbound", span);
        let lines: Vec<&str> = out.lines().collect();
        let caret_col = lines[2].find('^').unwrap();
        // "    " (4) + "π + x" -> caret should align under 'x', char column 4 (0-based) within the line.
        assert_eq!(caret_col, 4 + 4);
    }
}
