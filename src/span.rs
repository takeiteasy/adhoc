//! Source spans shared by every stage: lexer tokens, AST nodes, and diagnostics.
//!
//! Offsets are **bytes**, 0-based, half-open (`[start, end)`), into the original source
//! string — so `&source[span.start as usize..span.end as usize]` always slices correctly.
//! `diagnostic::render` is the one place that converts byte offsets to character *columns*
//! for display; nothing else should need to.

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Span {
    pub start: u32,
    pub end: u32,
}

impl Span {
    pub fn new(start: u32, end: u32) -> Self {
        debug_assert!(start <= end, "span start must not exceed end");
        Span { start, end }
    }

    /// A zero-width span at `pos` — used for `:eof` tokens and other point locations.
    pub fn point(pos: u32) -> Self {
        Span { start: pos, end: pos }
    }

    /// The smallest span covering both `self` and `other`.
    pub fn to(self, other: Span) -> Span {
        Span::new(self.start.min(other.start), self.end.max(other.end))
    }

    pub fn slice(self, source: &str) -> &str {
        &source[self.start as usize..self.end as usize]
    }
}
