//! Binary-level REPL tests, driven through piped stdin/stdout against the built `adhoc`
//! binary. Piped (non-TTY) stdin routes through the plain-stdin reader (`repl.rs`), which
//! is what makes the prompt sequence observable at all — see the comment in
//! `repl::run_repl` about why TTY detection, not "did rustyline fail to construct", picks
//! the reader.

use std::io::{Read, Write};
use std::process::{Command, Stdio};

fn run_repl_with_input(input: &str) -> String {
    let mut child = Command::new(env!("CARGO_BIN_EXE_adhoc"))
        .env("ADHOC_HISTORY", std::env::temp_dir().join("adhoc_test_history"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("failed to start adhoc");

    child.stdin.take().unwrap().write_all(input.as_bytes()).unwrap();

    let mut out = String::new();
    child.stdout.take().unwrap().read_to_string(&mut out).unwrap();
    child.wait().unwrap();
    out
}

#[test]
fn continuation_prompt_sequence() {
    // `(1 + 2` is incomplete -> `. ` continuation prompt; a blank line then cancels it,
    // returning to `> `. Find each prompt in turn, searching forward from the last match,
    // so the assertion is about ordering, not exact byte layout around them.
    let out = run_repl_with_input("(1 + 2\n\n");
    let first = out.find("> ").expect("initial `> ` prompt");
    let second = out[first + 2..].find(". ").expect("continuation `. ` prompt") + first + 2;
    let third = out[second + 2..].find("> ").expect("post-cancel `> ` prompt");
    assert!(first < second && second < second + 2 + third);
    assert!(out.contains("-- input cancelled"));
}

#[test]
fn semicolon_terminated_statements_do_not_continue() {
    let out = run_repl_with_input("1;\n2;\n");
    assert!(out.contains("< = 1"));
    assert!(out.contains("< = 2"));
    // Neither `1;` nor `2;` should ever show a continuation prompt.
    assert!(!out.contains(". "));
}

#[test]
fn eof_mid_statement_reports_diagnostic() {
    let out = run_repl_with_input("(1 + 2");
    assert!(out.contains("ERROR"));
}

#[test]
fn division_by_zero_recovers_instead_of_crashing() {
    // The HEAD regression this closes: Julia's `1/0` threw an untyped exception the REPL's
    // catch didn't match, so the loop died. Here it must render a caret and keep going.
    let out = run_repl_with_input("1/0\n1 + 1\n");
    assert!(out.contains("division by zero"));
    assert!(out.contains("^~~"));
    assert!(out.contains("< = 2"));
}
