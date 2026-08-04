//! `adhoc` — the `ad` calculator language.
//!
//! This crate is the language: lexer, parser, AST, numeric seam, interpreter, and the
//! diagnostic renderer they all share. The `adhoc` binary (`src/main.rs`) is a thin CLI
//! shell on top of it — REPL loop and script-file driver — and depends on this library
//! like any other consumer would.

pub mod ast;
pub mod diagnostic;
pub mod interp;
pub mod lexer;
pub mod num;
pub mod parser;
pub mod span;
