//! REPL driver. Binary-only — the language itself (lexer/parser/interp/diagnostic) lives
//! in the `adhoc` library; this module is glue: prompt, history, multi-line continuation,
//! error recovery.
//!
//! History is the one thing kept from the old Common Lisp readline subsystem — `rustyline`
//! gives editing/history/unicode in-process, so the fd-0 invariant, `setlocale` CFFI call,
//! `--has-readline` probe, and `rlwrap` fallback none of them need to exist here.
//!
//! Multi-line continuation: `> ` when nothing is pending, `. ` while continuing. A
//! `ParseError::IncompleteInput` buffers the line for the next round (joined with `\n`);
//! ad's whitespace is insignificant, so nothing else could ever close an unclosed
//! continuation — hence a **blank line cancels** the pending statement rather than being
//! swallowed as whitespace.

use crate::output::{print_eval_error, print_parse_error};
use adhoc::interp::{run, Env};
use adhoc::lexer::{tokenize, TokenKind};
use adhoc::parser::{parse_program, ParseError};
use rustyline::error::ReadlineError;
use rustyline::DefaultEditor;
use std::io::{IsTerminal, Write};
use std::path::PathBuf;

fn history_path() -> PathBuf {
    if let Ok(p) = std::env::var("ADHOC_HISTORY") {
        return PathBuf::from(p);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(".adhoc_history")
}

/// A blank line, or a line that lexes down to nothing but `--comment` text — i.e. only the
/// sentinel `:eof` token comes out of tokenizing it.
fn is_empty_source(source: &str) -> bool {
    matches!(tokenize(source), Ok(toks) if toks.len() == 1 && toks[0].kind == TokenKind::Eof)
}

enum Input {
    Line(String),
    Eof,
    Interrupted,
}

/// Abstracts over rustyline (interactive TTY) and plain stdin reads (piped input, or
/// rustyline unavailable) behind one read call.
enum Reader {
    Rustyline(Box<DefaultEditor>),
    Stdin,
}

impl Reader {
    fn read(&mut self, prompt: &str) -> Input {
        match self {
            Reader::Rustyline(ed) => match ed.readline(prompt) {
                Ok(line) => {
                    let _ = ed.add_history_entry(line.as_str());
                    Input::Line(line)
                }
                Err(ReadlineError::Eof) => Input::Eof,
                Err(ReadlineError::Interrupted) => Input::Interrupted,
                Err(_) => Input::Eof,
            },
            Reader::Stdin => {
                print!("{prompt}");
                let _ = std::io::stdout().flush();
                let mut buf = String::new();
                match std::io::stdin().read_line(&mut buf) {
                    Ok(0) => Input::Eof,
                    Ok(_) => {
                        if buf.ends_with('\n') {
                            buf.pop();
                            if buf.ends_with('\r') {
                                buf.pop();
                            }
                        }
                        Input::Line(buf)
                    }
                    Err(_) => Input::Eof,
                }
            }
        }
    }
}

pub fn run_repl() {
    let hist_path = history_path();
    // Piped/non-interactive stdin (scripts feeding the REPL, or this binary under test):
    // rustyline still *constructs* successfully but silently drops prompt output rather
    // than erroring, so detecting this by "did rustyline fail to initialize" doesn't work.
    // Check the terminal directly and use the plain-stdin reader whenever it isn't one.
    let mut reader = if std::io::stdin().is_terminal() {
        match DefaultEditor::new() {
            Ok(mut ed) => {
                let _ = ed.load_history(&hist_path);
                Reader::Rustyline(Box::new(ed))
            }
            Err(_) => Reader::Stdin,
        }
    } else {
        Reader::Stdin
    };

    let mut env = Env::new();
    let mut pending = String::new();

    loop {
        let prompt = if pending.is_empty() { "> " } else { ". " };
        match reader.read(prompt) {
            Input::Eof => {
                if !pending.is_empty() {
                    // Re-parse the buffered statement so its (still incomplete) diagnostic
                    // renders instead of exiting silently mid-statement.
                    if let Err(e) = parse_program(&pending) {
                        print_parse_error(&pending, &e);
                    }
                }
                println!();
                break;
            }
            Input::Interrupted => {
                pending.clear();
                continue;
            }
            Input::Line(line) => {
                if !pending.is_empty() && line.trim().is_empty() {
                    pending.clear();
                    println!("-- input cancelled");
                    continue;
                }
                if pending.is_empty() && line.trim().is_empty() {
                    continue;
                }

                let source = if pending.is_empty() { line.clone() } else { format!("{pending}\n{line}") };

                if pending.is_empty() && is_empty_source(&source) {
                    continue;
                }

                match parse_program(&source) {
                    Ok(node) => {
                        pending.clear();
                        match run(&mut env, &node) {
                            Ok(result) => println!("< {}", result.format()),
                            Err(e) => print_eval_error(&source, &e),
                        }
                    }
                    Err(ParseError::IncompleteInput { .. }) => {
                        pending = source;
                    }
                    Err(e) => {
                        pending.clear();
                        print_parse_error(&source, &e);
                    }
                }
            }
        }
    }

    if let Reader::Rustyline(ed) = &mut reader {
        let _ = ed.save_history(&hist_path);
    }
}
