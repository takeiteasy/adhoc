//! Recursive-descent / precedescedence-climbing parser over the token stream, matching the
//! precedence table in `docs/grammar.md`:
//!
//! ```text
//! program    ::= statement (";" statement)* ;
//! statement  ::= identifier ("=" | ":=") expr
//!              | expr ;
//! expr       ::= additive ;
//! additive   ::= multiplicative (("+" | "-") multiplicative)* ;
//! multiplicative
//!            ::= juxtaposed (("*" | "/") juxtaposed)* ;
//! juxtaposed ::= unary unary* ;              (* implicit multiplication *)
//! unary      ::= "-" unary | power ;
//! power      ::= atom ("^" unary)? ;         (* right-associative *)
//! atom       ::= number | identifier | "\"-name | "(" expr ")" ;
//! ```
//!
//! `power`'s exponent recurses into `unary`, not `power` — that's what makes `2^-1` parse
//! (unary minus binds inside the exponent) and `2^3^2` right-associate. The base of `^` is
//! a bare `atom`, so `-2^2` is `-(2^2)`.
//!
//! Spans are tagged at each node's *construction* site, not on the way out of each
//! `parse_*` call: `parse_atom`'s `(expr)` branch returns the inner node unchanged, and
//! tagging on unwind would clobber that inner node's own (narrower) span with the
//! paren-inclusive one.

use crate::ast::{BinOp, Node, NodeKind, UnOp};
use crate::lexer::{tokenize, LexError, Token, TokenKind};
use crate::span::Span;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub enum ParseError {
    Unexpected { msg: String, span: Span },
    /// The unexpected token was `:eof` — signals the REPL should offer a continuation
    /// prompt rather than reporting a hard error. A subtype in spirit, not in Rust's type
    /// system: callers that only care about "parsing failed" can still match this arm
    /// alongside `Unexpected` and get the same `msg`/`span` fields.
    IncompleteInput { msg: String, span: Span },
}

impl ParseError {
    pub fn msg(&self) -> &str {
        match self {
            ParseError::Unexpected { msg, .. } | ParseError::IncompleteInput { msg, .. } => msg,
        }
    }
    pub fn span(&self) -> Span {
        match self {
            ParseError::Unexpected { span, .. } | ParseError::IncompleteInput { span, .. } => *span,
        }
    }
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.msg())
    }
}

impl std::error::Error for ParseError {}

impl From<LexError> for ParseError {
    fn from(e: LexError) -> Self {
        ParseError::Unexpected { msg: e.msg, span: e.span }
    }
}

struct Parser {
    tokens: Vec<Token>,
    pos: usize,
}

impl Parser {
    fn peek(&self) -> &Token {
        &self.tokens[self.pos]
    }

    fn peek2(&self) -> &Token {
        &self.tokens[(self.pos + 1).min(self.tokens.len() - 1)]
    }

    fn advance(&mut self) -> Token {
        let t = self.tokens[self.pos].clone();
        if self.pos + 1 < self.tokens.len() {
            self.pos += 1;
        }
        t
    }

    fn error_at_current(&self, msg: String) -> ParseError {
        let tok = self.peek();
        if tok.kind == TokenKind::Eof {
            ParseError::IncompleteInput { msg, span: tok.span }
        } else {
            ParseError::Unexpected { msg, span: tok.span }
        }
    }

    fn expect(&mut self, kind: &TokenKind, what: &str) -> Result<Token, ParseError> {
        if &self.peek().kind == kind {
            Ok(self.advance())
        } else {
            let found = describe(&self.peek().kind);
            Err(self.error_at_current(format!("expected {what}, found {found}")))
        }
    }

    fn is_atom_starter(&self) -> bool {
        matches!(
            self.peek().kind,
            TokenKind::Number | TokenKind::Ident(_) | TokenKind::Backslash(_) | TokenKind::LParen
        )
    }

    // program ::= statement (";" statement)* ;
    fn parse_program(&mut self) -> Result<Node, ParseError> {
        let mut statements = vec![self.parse_statement()?];
        while self.peek().kind == TokenKind::Semi {
            self.advance();
            if self.peek().kind == TokenKind::Eof {
                break;
            }
            statements.push(self.parse_statement()?);
        }
        if !matches!(self.peek().kind, TokenKind::Eof) {
            let found = describe(&self.peek().kind);
            return Err(self.error_at_current(format!("unexpected token {found}")));
        }
        if statements.len() == 1 {
            Ok(statements.pop().unwrap())
        } else {
            let span = statements[0].span.to(statements[statements.len() - 1].span);
            Ok(Node::new(NodeKind::Seq(statements), span))
        }
    }

    // statement ::= identifier ("=" | ":=") expr | expr ;
    fn parse_statement(&mut self) -> Result<Node, ParseError> {
        if let TokenKind::Ident(name) = self.peek().kind {
            let op_kind = self.peek2().kind.clone();
            if op_kind == TokenKind::Eq || op_kind == TokenKind::ColonEq {
                let ident_tok = self.advance();
                let force = self.advance().kind == TokenKind::ColonEq;
                let value = self.parse_expr()?;
                let span = ident_tok.span.to(value.span);
                return Ok(Node::new(NodeKind::Assign { name, force, value: Box::new(value) }, span));
            }
        }
        self.parse_expr()
    }

    fn parse_expr(&mut self) -> Result<Node, ParseError> {
        self.parse_additive()
    }

    // additive ::= multiplicative (("+" | "-") multiplicative)* ;
    fn parse_additive(&mut self) -> Result<Node, ParseError> {
        let mut lhs = self.parse_multiplicative()?;
        loop {
            let op = match self.peek().kind {
                TokenKind::Plus => BinOp::Add,
                TokenKind::Minus => BinOp::Sub,
                _ => break,
            };
            self.advance();
            let rhs = self.parse_multiplicative()?;
            let span = lhs.span.to(rhs.span);
            lhs = Node::new(NodeKind::BinOp { op, lhs: Box::new(lhs), rhs: Box::new(rhs) }, span);
        }
        Ok(lhs)
    }

    // multiplicative ::= juxtaposed (("*" | "/") juxtaposed)* ;
    fn parse_multiplicative(&mut self) -> Result<Node, ParseError> {
        let mut lhs = self.parse_juxtaposed()?;
        loop {
            let op = match self.peek().kind {
                TokenKind::Star => BinOp::Mul,
                TokenKind::Slash => BinOp::Div,
                _ => break,
            };
            self.advance();
            let rhs = self.parse_juxtaposed()?;
            let span = lhs.span.to(rhs.span);
            lhs = Node::new(NodeKind::BinOp { op, lhs: Box::new(lhs), rhs: Box::new(rhs) }, span);
        }
        Ok(lhs)
    }

    // juxtaposed ::= unary unary* ; (implicit multiplication) — note `-` is deliberately
    // excluded from ATOM_STARTERS, so `a - b` parses as subtraction, never `a * (-b)`.
    fn parse_juxtaposed(&mut self) -> Result<Node, ParseError> {
        let mut lhs = self.parse_unary()?;
        while self.is_atom_starter() {
            let rhs = self.parse_unary()?;
            let span = lhs.span.to(rhs.span);
            lhs = Node::new(NodeKind::BinOp { op: BinOp::Mul, lhs: Box::new(lhs), rhs: Box::new(rhs) }, span);
        }
        Ok(lhs)
    }

    // unary ::= "-" unary | power ;
    fn parse_unary(&mut self) -> Result<Node, ParseError> {
        if self.peek().kind == TokenKind::Minus {
            let minus = self.advance();
            let operand = self.parse_unary()?;
            let span = minus.span.to(operand.span);
            return Ok(Node::new(NodeKind::UnOp { op: UnOp::Neg, operand: Box::new(operand) }, span));
        }
        self.parse_power()
    }

    // power ::= atom ("^" unary)? ; right-associative, exponent recurses into `unary`.
    fn parse_power(&mut self) -> Result<Node, ParseError> {
        let base = self.parse_atom()?;
        if self.peek().kind == TokenKind::Caret {
            self.advance();
            let exp = self.parse_unary()?;
            let span = base.span.to(exp.span);
            return Ok(Node::new(NodeKind::BinOp { op: BinOp::Pow, lhs: Box::new(base), rhs: Box::new(exp) }, span));
        }
        Ok(base)
    }

    // atom ::= number | identifier | "\"-name | "(" expr ")" ;
    fn parse_atom(&mut self) -> Result<Node, ParseError> {
        let tok = self.peek().clone();
        match tok.kind {
            TokenKind::Number => {
                self.advance();
                Ok(Node::new(NodeKind::NumLit(tok.text), tok.span))
            }
            TokenKind::Ident(c) => {
                self.advance();
                Ok(Node::new(NodeKind::Var(c), tok.span))
            }
            TokenKind::Backslash(name) => {
                self.advance();
                Ok(Node::new(NodeKind::BackslashRef(name), tok.span))
            }
            TokenKind::LParen => {
                self.advance();
                let inner = self.parse_expr()?;
                self.expect(&TokenKind::RParen, "`)`")?;
                // Deliberately not retagged with the paren-inclusive span — see module docs.
                Ok(inner)
            }
            _ => {
                let found = describe(&tok.kind);
                Err(self.error_at_current(format!("unexpected token {found}")))
            }
        }
    }
}

fn describe(kind: &TokenKind) -> String {
    match kind {
        TokenKind::Number => "a number".to_string(),
        TokenKind::Ident(c) => format!("`{c}`"),
        TokenKind::Backslash(name) => format!("`\\{name}`"),
        TokenKind::Plus => "`+`".to_string(),
        TokenKind::Minus => "`-`".to_string(),
        TokenKind::Star => "`*`".to_string(),
        TokenKind::Slash => "`/`".to_string(),
        TokenKind::Caret => "`^`".to_string(),
        TokenKind::Eq => "`=`".to_string(),
        TokenKind::ColonEq => "`:=`".to_string(),
        TokenKind::LParen => "`(`".to_string(),
        TokenKind::RParen => "`)`".to_string(),
        TokenKind::Semi => "`;`".to_string(),
        TokenKind::Eof => "end of input".to_string(),
    }
}

/// Tokenize and parse a complete program from source text.
pub fn parse_program(src: &str) -> Result<Node, ParseError> {
    let tokens = tokenize(src)?;
    let mut parser = Parser { tokens, pos: 0 };
    parser.parse_program()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interp::{run, Env};
    use crate::num::nshow;

    #[test]
    fn grammar_worked_examples_numeric() {
        let mut env = Env::new();
        let check = |src: &str, expected: &str, env: &mut Env| {
            let node = parse_program(src).unwrap();
            let r = run(env, &node).unwrap();
            assert_eq!(r.format(), expected, "for {src}");
        };
        check("1 + 2 * 3", "= 7", &mut env);
        check("(1 + 2) * 3", "= 9", &mut env);
        check("2^3^2", "= 512", &mut env);
        check("2^-1", "= 1/2", &mut env);
        check("-2^2", "= -4", &mut env);
        let _ = nshow; // used indirectly via EvalResult::format in interp tests
    }

    #[test]
    fn juxtaposition_precedence() {
        let mut env = Env::new();
        run(&mut env, &parse_program("x = 2").unwrap()).unwrap();
        let node = parse_program("1/2x").unwrap();
        let r = run(&mut env, &node).unwrap();
        // 1/(2x) = 1/4, not (1/2)x = 1
        assert_eq!(r.format(), "= 1/4");
    }

    #[test]
    fn backslash_names_parse_but_are_unbound() {
        let node = parse_program("\\pi").unwrap();
        let mut env = Env::new();
        let err = run(&mut env, &node).unwrap_err();
        assert!(err.msg.contains("not bound"));
    }

    #[test]
    fn incomplete_input_variants() {
        assert!(matches!(parse_program("(1 + 2"), Err(ParseError::IncompleteInput { .. })));
        assert!(matches!(parse_program("1 +"), Err(ParseError::IncompleteInput { .. })));
        assert!(matches!(parse_program("2 ^"), Err(ParseError::IncompleteInput { .. })));
        assert!(matches!(parse_program("x ="), Err(ParseError::IncompleteInput { .. })));
    }

    #[test]
    fn trailing_semicolons_do_not_trigger_incomplete_input() {
        assert!(parse_program("1;").is_ok());
        assert!(parse_program("2;").is_ok());
    }
}
