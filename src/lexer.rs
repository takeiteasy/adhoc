//! Tokenizer. Whitespace-insensitive, single-character (ASCII or unicode) identifiers,
//! `--` line comments, and the `\`-name convention: every language-defined name longer
//! than one character takes a `\` sigil.
//!
//! A `\`-token always lexes cleanly if the name is in [`KNOWN_BACKSLASH_NAMES`] and fails,
//! if at all, at eval time as an unbound name — not at the lexer as an unknown token.
//! Unrecognized `\`-names remain a lex error, which is what catches typos.

use crate::span::Span;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub enum TokenKind {
    Number,
    Ident(char),
    /// Bare name, sigil stripped (`"pi"` for `\pi`).
    Backslash(String),
    Plus,
    Minus,
    Star,
    Slash,
    Caret,
    Eq,
    ColonEq,
    LParen,
    RParen,
    Semi,
    Eof,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Token {
    pub kind: TokenKind,
    pub text: String,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LexError {
    pub msg: String,
    pub span: Span,
}

impl fmt::Display for LexError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.msg)
    }
}

impl std::error::Error for LexError {}

pub const KNOWN_BACKSLASH_NAMES: &[&str] = &[
    "pi", "sum", "prod", "sqrt", "cup", "cap", "in", "subseteq", "setminus", "circ", "lim",
    "const", "arr", "expr", "if", "otherwise", "sin", "cos", "tan", "ln", "solve", "simplify",
    "expand", "factor", "eval", "body", "map", "fold", "filter", "graph", "infix", "and", "or",
    "not",
];

pub fn tokenize(src: &str) -> Result<Vec<Token>, LexError> {
    let chars: Vec<(usize, char)> = src.char_indices().collect();
    let n = chars.len();
    let mut tokens = Vec::new();
    let mut i = 0usize;

    // Byte offset one past the last character — where `end` lands when a scan runs to EOF.
    let eof_off = src.len();

    while i < n {
        let (pos, c) = chars[i];

        if c.is_whitespace() {
            i += 1;
            continue;
        }

        if c == '-' && i + 1 < n && chars[i + 1].1 == '-' {
            i += 2;
            while i < n && chars[i].1 != '\n' {
                i += 1;
            }
            continue;
        }

        if c.is_ascii_digit() {
            let mut j = i;
            while j < n && chars[j].1.is_ascii_digit() {
                j += 1;
            }
            // Only consume `.` if a digit follows — `1.` lexes as `1` then errors on `.`.
            if j < n && chars[j].1 == '.' && j + 1 < n && chars[j + 1].1.is_ascii_digit() {
                j += 1;
                while j < n && chars[j].1.is_ascii_digit() {
                    j += 1;
                }
            }
            let end = if j < n { chars[j].0 } else { eof_off };
            let text = src[pos..end].to_string();
            tokens.push(Token { kind: TokenKind::Number, text, span: Span::new(pos as u32, end as u32) });
            i = j;
            continue;
        }

        if c == '\\' {
            let mut j = i + 1;
            while j < n && chars[j].1.is_alphabetic() {
                j += 1;
            }
            let end = if j < n { chars[j].0 } else { eof_off };
            let name = if j > i + 1 { src[chars[i + 1].0..end].to_string() } else { String::new() };
            let span = Span::new(pos as u32, end as u32);
            if name.is_empty() {
                return Err(LexError { msg: "bare `\\` with no name following".to_string(), span });
            }
            if !KNOWN_BACKSLASH_NAMES.contains(&name.as_str()) {
                return Err(LexError { msg: format!("unknown \\-name `\\{name}`"), span });
            }
            tokens.push(Token { kind: TokenKind::Backslash(name.clone()), text: name, span });
            i = j;
            continue;
        }

        if c.is_alphabetic() {
            let end = pos + c.len_utf8();
            tokens.push(Token {
                kind: TokenKind::Ident(c),
                text: c.to_string(),
                span: Span::new(pos as u32, end as u32),
            });
            i += 1;
            continue;
        }

        if c == ':' {
            if i + 1 < n && chars[i + 1].1 == '=' {
                let end = chars[i + 1].0 + 1;
                tokens.push(Token {
                    kind: TokenKind::ColonEq,
                    text: ":=".to_string(),
                    span: Span::new(pos as u32, end as u32),
                });
                i += 2;
                continue;
            }
            return Err(LexError {
                msg: "unexpected character `:`".to_string(),
                span: Span::new(pos as u32, (pos + 1) as u32),
            });
        }

        let single = match c {
            '+' => Some(TokenKind::Plus),
            '-' => Some(TokenKind::Minus),
            '*' => Some(TokenKind::Star),
            '/' => Some(TokenKind::Slash),
            '^' => Some(TokenKind::Caret),
            '=' => Some(TokenKind::Eq),
            '(' => Some(TokenKind::LParen),
            ')' => Some(TokenKind::RParen),
            ';' => Some(TokenKind::Semi),
            _ => None,
        };
        if let Some(kind) = single {
            let end = pos + c.len_utf8();
            tokens.push(Token { kind, text: c.to_string(), span: Span::new(pos as u32, end as u32) });
            i += 1;
            continue;
        }

        return Err(LexError {
            msg: format!("unexpected character `{c}`"),
            span: Span::new(pos as u32, (pos + c.len_utf8()) as u32),
        });
    }

    tokens.push(Token {
        kind: TokenKind::Eof,
        text: String::new(),
        span: Span::point(eof_off as u32),
    });
    Ok(tokens)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn kinds(src: &str) -> Vec<TokenKind> {
        tokenize(src).unwrap().into_iter().map(|t| t.kind).collect()
    }

    #[test]
    fn numbers() {
        assert_eq!(kinds("42"), vec![TokenKind::Number, TokenKind::Eof]);
        assert_eq!(kinds("3.14"), vec![TokenKind::Number, TokenKind::Eof]);
        // `1.` — the dot isn't consumed without a following digit, so `1` lexes cleanly
        // and the lone `.` then fails as an unexpected character.
        let err = tokenize("1.").unwrap_err();
        assert!(err.msg.contains('.'));
    }

    #[test]
    fn ascii_and_unicode_idents() {
        let toks = tokenize("ab \u{3c0}").unwrap();
        let idents: Vec<char> = toks
            .iter()
            .filter_map(|t| if let TokenKind::Ident(c) = t.kind { Some(c) } else { None })
            .collect();
        assert_eq!(idents, vec!['a', 'b', '\u{3c0}']);
    }

    #[test]
    fn backslash_names() {
        let toks = tokenize("\\pi").unwrap();
        assert_eq!(toks[0].kind, TokenKind::Backslash("pi".to_string()));
        assert_eq!(toks[0].span, Span::new(0, 3));
    }

    #[test]
    fn unknown_backslash_name_errors() {
        let e = tokenize("\\bogus").unwrap_err();
        assert!(e.msg.contains("unknown"));
    }

    #[test]
    fn bare_backslash_errors() {
        let e = tokenize("\\ ").unwrap_err();
        assert!(e.msg.contains("bare"));
    }

    #[test]
    fn comments_are_discarded() {
        assert_eq!(kinds("-- hi\n1"), vec![TokenKind::Number, TokenKind::Eof]);
    }

    #[test]
    fn all_operator_kinds() {
        assert_eq!(
            kinds("+-*/^=:=();"),
            vec![
                TokenKind::Plus,
                TokenKind::Minus,
                TokenKind::Star,
                TokenKind::Slash,
                TokenKind::Caret,
                TokenKind::Eq,
                TokenKind::ColonEq,
                TokenKind::LParen,
                TokenKind::RParen,
                TokenKind::Semi,
                TokenKind::Eof,
            ]
        );
    }

    #[test]
    fn unexpected_char_errors() {
        assert!(tokenize("$").is_err());
    }

    #[test]
    fn eof_token_is_zero_width_at_end() {
        let toks = tokenize("x").unwrap();
        assert_eq!(toks.last().unwrap().span, Span::new(1, 1));
    }
}
