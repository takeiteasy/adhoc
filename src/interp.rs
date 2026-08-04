//! Tree-walking evaluator. This is the durable engine — not a bootstrap slated for
//! replacement (see `docs/architecture.md`).
//!
//! Assignment semantics (the language's least ordinary rule):
//!
//! | form   | precondition   | behaviour              | printed        |
//! |--------|-----------------|-------------------------|----------------|
//! | `x = e`  | `x` unbound   | bind                    | `x = v`        |
//! | `x = e`  | `x` bound     | **compare** to current  | `true`/`false` |
//! | `x := e` | `x` bound     | rebind                  | `x = v`        |
//! | `x := e` | `x` unbound   | error                   | `` `x` does not exist! `` |
//! | bare `e` | —             | —                       | `= v`          |
//!
//! Span narrowing: `eval_expr`'s `BinOp` arm evaluates `lhs`/`rhs` *before* wrapping the
//! arithmetic call in an error-mapping step, so a sub-expression's own error (unbound
//! variable, nested division by zero) keeps its own narrower span; only the arithmetic
//! operation itself is tagged with the enclosing node's span.

use crate::ast::{BinOp, Node, NodeKind, UnOp};
use crate::num::{nadd, ndiv, nmul, nneg, npow, nsub, parse_literal, neq, nshow, AdNum};
use crate::span::Span;
use std::collections::HashMap;
use std::fmt;

pub type Env = HashMap<char, AdNum>;

#[derive(Debug, Clone, PartialEq)]
pub struct EvalError {
    pub msg: String,
    pub span: Option<Span>,
}

impl fmt::Display for EvalError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.msg)
    }
}

impl std::error::Error for EvalError {}

#[derive(Debug, Clone)]
pub enum EvalResult {
    Bind { name: char, value: AdNum },
    Check { matches: bool },
    Bare { value: AdNum },
}

impl EvalResult {
    pub fn format(&self) -> String {
        match self {
            EvalResult::Bind { name, value } => format!("{name} = {}", nshow(value)),
            EvalResult::Check { matches } => matches.to_string(),
            EvalResult::Bare { value } => format!("= {}", nshow(value)),
        }
    }
}

/// Run one statement (or a `Seq` of them), threading `env` and returning the last result.
pub fn run(env: &mut Env, node: &Node) -> Result<EvalResult, EvalError> {
    match &node.kind {
        NodeKind::Assign { name, force, value } => {
            let v = eval_expr(env, value)?;
            if *force {
                if env.contains_key(name) {
                    env.insert(*name, v.clone());
                    Ok(EvalResult::Bind { name: *name, value: v })
                } else {
                    Err(EvalError { msg: format!("`{name}` does not exist!"), span: Some(node.span) })
                }
            } else if let Some(existing) = env.get(name) {
                Ok(EvalResult::Check { matches: neq(existing, &v) })
            } else {
                env.insert(*name, v.clone());
                Ok(EvalResult::Bind { name: *name, value: v })
            }
        }
        NodeKind::Seq(statements) => {
            let mut last = None;
            for s in statements {
                last = Some(run(env, s)?);
            }
            Ok(last.expect("parser never produces an empty Seq"))
        }
        _ => Ok(EvalResult::Bare { value: eval_expr(env, node)? }),
    }
}

fn eval_expr(env: &mut Env, node: &Node) -> Result<AdNum, EvalError> {
    match &node.kind {
        NodeKind::NumLit(text) => Ok(parse_literal(text)),
        NodeKind::Var(c) => env
            .get(c)
            .cloned()
            .ok_or_else(|| EvalError { msg: format!("`{c}` is not bound"), span: Some(node.span) }),
        NodeKind::BackslashRef(name) => Err(EvalError {
            msg: format!("`\\{name}` is not bound (phase 0 defines no builtins yet)"),
            span: Some(node.span),
        }),
        NodeKind::UnOp { op, operand } => {
            let v = eval_expr(env, operand)?;
            match op {
                UnOp::Neg => Ok(nneg(&v)),
            }
        }
        NodeKind::BinOp { op, lhs, rhs } => {
            // Evaluated outside the error-wrapping step below, so an operand's own error
            // keeps its own (narrower) span.
            let l = eval_expr(env, lhs)?;
            let r = eval_expr(env, rhs)?;
            match op {
                BinOp::Add => Ok(nadd(&l, &r)),
                BinOp::Sub => Ok(nsub(&l, &r)),
                BinOp::Mul => Ok(nmul(&l, &r)),
                BinOp::Div => {
                    ndiv(&l, &r).map_err(|e| EvalError { msg: e.to_string(), span: Some(node.span) })
                }
                BinOp::Pow => {
                    npow(&l, &r).map_err(|e| EvalError { msg: e.to_string(), span: Some(node.span) })
                }
            }
        }
        NodeKind::Assign { .. } | NodeKind::Seq(_) => {
            unreachable!("Assign/Seq only appear as statements, handled in run()")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse_program;

    fn eval_program(src: &str, env: &mut Env) -> Result<EvalResult, EvalError> {
        let node = parse_program(src).unwrap();
        run(env, &node)
    }

    #[test]
    fn arithmetic() {
        let mut env = Env::new();
        assert_eq!(eval_program("1 + 2 * 3", &mut env).unwrap().format(), "= 7");
    }

    #[test]
    fn unbound_var_error_message() {
        let mut env = Env::new();
        let e = eval_program("x", &mut env).unwrap_err();
        assert_eq!(e.msg, "`x` is not bound");
    }

    #[test]
    fn force_reassign_on_unbound_errors() {
        let mut env = Env::new();
        let e = eval_program("y := 2", &mut env).unwrap_err();
        assert_eq!(e.msg, "`y` does not exist!");
    }

    #[test]
    fn assign_binds_then_checks() {
        let mut env = Env::new();
        assert_eq!(eval_program("x = 3", &mut env).unwrap().format(), "x = 3");
        assert_eq!(eval_program("x = 4", &mut env).unwrap().format(), "false");
        assert_eq!(eval_program("x = 3", &mut env).unwrap().format(), "true");
    }

    #[test]
    fn force_reassign_rebinds() {
        let mut env = Env::new();
        eval_program("x = 3", &mut env).unwrap();
        assert_eq!(eval_program("x := 4", &mut env).unwrap().format(), "x = 4");
    }

    #[test]
    fn seq_threads_env_and_returns_last() {
        let mut env = Env::new();
        let r = eval_program("a = 1; b = 2; a + b", &mut env).unwrap();
        assert_eq!(r.format(), "= 3");
    }

    #[test]
    fn backslash_ref_errors_unbound() {
        let mut env = Env::new();
        let e = eval_program("\\pi", &mut env).unwrap_err();
        assert!(e.msg.contains("not bound"));
    }

    #[test]
    fn span_narrowing_unbound_var_in_addition() {
        let mut env = Env::new();
        let e = eval_program("1 + x", &mut env).unwrap_err();
        assert_eq!(e.span, Some(Span::new(4, 5)));
    }

    #[test]
    fn span_narrowing_division_by_zero() {
        let mut env = Env::new();
        let e = eval_program("2 + 1/0", &mut env).unwrap_err();
        assert_eq!(e.span, Some(Span::new(4, 7)));
    }

    #[test]
    fn span_narrowing_backslash_ref_is_sigil_inclusive() {
        let mut env = Env::new();
        let e = eval_program("\\pi", &mut env).unwrap_err();
        assert_eq!(e.span, Some(Span::new(0, 3)));
    }

    #[test]
    fn span_narrowing_second_statement_only() {
        let mut env = Env::new();
        let e = eval_program("a=1; y:=2", &mut env).unwrap_err();
        assert_eq!(e.span, Some(Span::new(5, 9)));
    }

    #[test]
    fn division_by_zero_keeps_repl_alive_via_typed_error() {
        // The regression this closes: Julia HEAD's `1/0` threw an untyped exception the
        // REPL's catch didn't match, so it `rethrow`'d and killed the loop. Here it's a
        // typed, spanned `EvalError` the REPL can catch and recover from.
        let mut env = Env::new();
        let e = eval_program("1/0", &mut env).unwrap_err();
        assert_eq!(e.msg, "division by zero");
        assert!(e.span.is_some());
        // The env/interpreter itself is unaffected — evaluation can continue.
        assert_eq!(eval_program("1 + 1", &mut env).unwrap().format(), "= 2");
    }
}
