//! Parity checks lifted from `docs/grammar.md`'s worked examples and assignment-semantics
//! table, plus the float-display and unicode-identifier pins the old Common Lisp suite
//! carried (`grammar-float-parity`, `grammar-unicode-identifier`) that the Julia tree never
//! had — their absence is part of why Julia's `1/0` REPL crash went unnoticed.

use adhoc::interp::{run, Env};
use adhoc::num::{nadd, npow, nshow, AdNum};
use adhoc::parser::parse_program;
use rug::{Float, Integer};

fn ev(env: &mut Env, src: &str) -> String {
    let node = parse_program(src).unwrap();
    run(env, &node).unwrap().format()
}

#[test]
fn precedence_worked_examples() {
    let mut env = Env::new();
    assert_eq!(ev(&mut env, "x = 2"), "x = 2");
    assert_eq!(ev(&mut env, "1/2x"), "= 1/4"); // 1/(2x), not (1/2)x
    assert_eq!(ev(&mut env, "2x^2"), "= 8"); // 2*(x^2), not (2x)^2
    assert_eq!(ev(&mut env, "-2^2"), "= -4"); // unary minus looser than ^
    assert_eq!(ev(&mut env, "2^-1"), "= 1/2");
    assert_eq!(ev(&mut env, "2^3^2"), "= 512"); // right-associative
    assert_eq!(ev(&mut env, "1 + 2*3"), "= 7");
    assert_eq!(ev(&mut env, "(1+2)*3"), "= 9");
}

#[test]
fn assignment_semantics_table() {
    let mut env = Env::new();
    assert_eq!(ev(&mut env, "x = 3"), "x = 3"); // unbound -> bind
    assert_eq!(ev(&mut env, "x = 4"), "false"); // bound, mismatched -> check
    assert_eq!(ev(&mut env, "x = 3"), "true"); // bound, matches -> check
    assert_eq!(ev(&mut env, "x := 4"), "x = 4"); // bound -> force rebind
    let node = parse_program("y := 5").unwrap();
    let err = run(&mut env, &node).unwrap_err();
    assert_eq!(err.msg, "`y` does not exist!"); // unbound -> error
}

#[test]
fn grammar_float_parity() {
    let a = AdNum::Float(Float::with_val(53, 0.5));
    let b = AdNum::Float(Float::with_val(53, 0.5));
    assert_eq!(nshow(&nadd(&a, &b)), "1.0");

    let two = AdNum::Int(Integer::from(2));
    let half = AdNum::Float(Float::with_val(53, 0.5));
    assert_eq!(nshow(&npow(&two, &half).unwrap()), "1.4142135623730951");
}

#[test]
fn grammar_unicode_identifier() {
    let mut env = Env::new();
    assert_eq!(ev(&mut env, "\u{3c0} = 3"), "\u{3c0} = 3");
}
