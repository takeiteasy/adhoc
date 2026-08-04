//! The AST: a typed Rust enum, not an s-expression list. The Common Lisp attempt used
//! s-expressions on the reasoning that a later symbolic-algebra phase (`\expr`/`\eval`/
//! `\body`) could quote and rewrite the AST with ordinary list operations — but that's a
//! Lisp-ism, and doesn't transfer: Rust enums quote and rewrite fine via match-and-rebuild.
//!
//! Every node carries its own `Span`, tagged at construction time by the parser (see
//! `parser.rs` for why *at construction*, not on the way out of each `parse_*` call,
//! matters for parenthesized expressions).

use crate::span::Span;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    Pow,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnOp {
    Neg,
}

#[derive(Debug, Clone)]
pub struct Node {
    pub kind: NodeKind,
    pub span: Span,
}

#[derive(Debug, Clone)]
pub enum NodeKind {
    NumLit(String),
    Var(char),
    BackslashRef(String),
    BinOp { op: BinOp, lhs: Box<Node>, rhs: Box<Node> },
    UnOp { op: UnOp, operand: Box<Node> },
    Assign { name: char, force: bool, value: Box<Node> },
    Seq(Vec<Node>),
}

impl Node {
    pub fn new(kind: NodeKind, span: Span) -> Self {
        Node { kind, span }
    }
}
