//! Shared diagnostic-printing helpers for the REPL and script-mode drivers in this binary.
//! Both funnel through `adhoc::diagnostic::render`, which is what keeps REPL and script
//! error output in the same shape.

use adhoc::interp::EvalError;
use adhoc::parser::ParseError;

pub fn print_parse_error(source: &str, e: &ParseError) {
    print!("{}", adhoc::diagnostic::render(source, "ERROR!", e.msg(), e.span()));
}

pub fn print_eval_error(source: &str, e: &EvalError) {
    match e.span {
        Some(span) => print!("{}", adhoc::diagnostic::render(source, "ERROR!", &e.msg, span)),
        None => println!("< ERROR! {}", e.msg),
    }
}
