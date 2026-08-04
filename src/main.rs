//! `adhoc` CLI: a thin shell over the `adhoc` library. `adhoc` with no arguments runs the
//! REPL; `adhoc run script.ad` runs a script file through the same grammar.

mod output;
mod repl;

use adhoc::ast::NodeKind;
use adhoc::interp::{run, EvalError, Env};
use adhoc::parser::parse_program;
use output::{print_eval_error, print_parse_error};
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        None => {
            repl::run_repl();
            ExitCode::SUCCESS
        }
        Some("run") => match args.get(1) {
            Some(path) => run_script(path),
            None => {
                eprintln!("usage: adhoc run <script.ad>");
                ExitCode::FAILURE
            }
        },
        Some(other) => {
            eprintln!("adhoc: unrecognized argument `{other}`");
            eprintln!("usage: adhoc | adhoc run <script.ad>");
            ExitCode::FAILURE
        }
    }
}

/// Script mode shares the REPL's grammar and `output`'s diagnostic printing, but the
/// driver is deliberately different, not reused: the whole file is one source (so a
/// caret's line-number gutter is meaningful), an unterminated statement at EOF
/// (`ParseError::IncompleteInput`) is just a hard parse error — there is no continuation
/// prompt to offer a file — and a blank line between statements carries no meaning (unlike
/// the REPL, where it cancels a pending multi-line statement).
fn run_script(path: &str) -> ExitCode {
    let source = match std::fs::read_to_string(path) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("adhoc: cannot read `{path}`: {e}");
            return ExitCode::FAILURE;
        }
    };

    let node = match parse_program(&source) {
        Ok(node) => node,
        Err(e) => {
            print_parse_error(&source, &e);
            return ExitCode::FAILURE;
        }
    };

    let mut env = Env::new();
    match run_and_echo(&mut env, &node) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            print_eval_error(&source, &e);
            ExitCode::FAILURE
        }
    }
}

/// Print one `< ...` line per top-level statement, matching the REPL's per-line output —
/// `parse_program` collapses a `;`-separated file into a single top-level `Seq`, but each
/// element of it is a statement in its own right.
fn run_and_echo(env: &mut Env, node: &adhoc::ast::Node) -> Result<(), EvalError> {
    if let NodeKind::Seq(statements) = &node.kind {
        for stmt in statements {
            println!("< {}", run(env, stmt)?.format());
        }
    } else {
        println!("< {}", run(env, node)?.format());
    }
    Ok(())
}
