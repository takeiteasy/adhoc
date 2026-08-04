//! The numeric seam. `interp.rs` never calls `+`/`*`/... on a value that came from user
//! input — only through the functions here. Everything else in the crate is required to
//! treat `AdNum` as opaque and go through `nadd`/`nsub`/`nmul`/`ndiv`/`npow`/`nneg`/`neq`/
//! `nshow`.
//!
//! Three tiers, in increasing generality, and arithmetic stays at the lowest tier that
//! remains exact:
//!
//! 1. `Int` — arbitrary-precision integer (`rug::Integer`).
//! 2. `Rat` — arbitrary-precision rational (`rug::Rational`). `rug::Rational` auto-reduces
//!    but does not auto-*collapse* to an integer when the denominator is 1 — every
//!    constructor here demotes a denominator-1 `Rat` back to `Int` (`normalize_rat`), or
//!    `nshow` would print `"1/1"`.
//! 3. `Float` — arbitrary-precision float (`rug::Float`), used once a float literal or a
//!    non-integer exponent forces inexactness.
//!
//! `DEFAULT_FLOAT_PREC` is 53 bits — a double-precision mantissa. This is *not* the same
//! as `f64` (MPFR at 53 bits has unbounded exponent range and no subnormals), but at this
//! precision the value round-trips losslessly through `f64`, which is what `nshow` relies
//! on for display (see below). Raising this constant later, when phase 3's Recursive Real
//! Arithmetic tier needs more precision, does not change anything else in this module.

use rug::ops::Pow;
use rug::{Float, Integer, Rational};
use std::cmp::Ordering;
use std::fmt;

pub const DEFAULT_FLOAT_PREC: u32 = 53;

#[derive(Debug, Clone)]
pub enum AdNum {
    Int(Integer),
    Rat(Rational),
    Float(Float),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NumError {
    DivisionByZero,
}

impl fmt::Display for NumError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            NumError::DivisionByZero => write!(f, "division by zero"),
        }
    }
}

impl std::error::Error for NumError {}

fn new_float(v: f64) -> Float {
    Float::with_val(DEFAULT_FLOAT_PREC, v)
}

fn is_float(n: &AdNum) -> bool {
    matches!(n, AdNum::Float(_))
}

fn is_zero(n: &AdNum) -> bool {
    match n {
        AdNum::Int(i) => i.cmp0() == Ordering::Equal,
        AdNum::Rat(r) => r.numer().cmp0() == Ordering::Equal,
        AdNum::Float(f) => f.is_zero(),
    }
}

fn to_rational(n: &AdNum) -> Rational {
    match n {
        AdNum::Int(i) => Rational::from(i.clone()),
        AdNum::Rat(r) => r.clone(),
        AdNum::Float(_) => unreachable!("to_rational called on an AdNum::Float"),
    }
}

fn to_float(n: &AdNum) -> Float {
    match n {
        AdNum::Int(i) => Float::with_val(DEFAULT_FLOAT_PREC, i),
        AdNum::Rat(r) => Float::with_val(DEFAULT_FLOAT_PREC, r),
        AdNum::Float(f) => f.clone(),
    }
}

/// Collapse a `Rational` back to `Int` when its denominator is 1. Every constructor that
/// produces a `Rational` from arithmetic must route through this.
fn normalize_rat(r: Rational) -> AdNum {
    if r.denom() == &1 {
        AdNum::Int(r.numer().clone())
    } else {
        AdNum::Rat(r)
    }
}

/// If `n` is an exact integer value (an `Int`, or a `Rat` with denominator 1), return it
/// as an `Integer`. Used by `npow` to decide whether an exponent keeps the result exact.
fn as_integer_exponent(n: &AdNum) -> Option<Integer> {
    match n {
        AdNum::Int(i) => Some(i.clone()),
        AdNum::Rat(r) if r.denom() == &1 => Some(r.numer().clone()),
        _ => None,
    }
}

pub fn nadd(a: &AdNum, b: &AdNum) -> AdNum {
    if is_float(a) || is_float(b) {
        AdNum::Float(to_float(a) + to_float(b))
    } else if matches!(a, AdNum::Rat(_)) || matches!(b, AdNum::Rat(_)) {
        normalize_rat(to_rational(a) + to_rational(b))
    } else {
        match (a, b) {
            (AdNum::Int(x), AdNum::Int(y)) => AdNum::Int(Integer::from(x + y)),
            _ => unreachable!(),
        }
    }
}

pub fn nsub(a: &AdNum, b: &AdNum) -> AdNum {
    if is_float(a) || is_float(b) {
        AdNum::Float(to_float(a) - to_float(b))
    } else if matches!(a, AdNum::Rat(_)) || matches!(b, AdNum::Rat(_)) {
        normalize_rat(to_rational(a) - to_rational(b))
    } else {
        match (a, b) {
            (AdNum::Int(x), AdNum::Int(y)) => AdNum::Int(Integer::from(x - y)),
            _ => unreachable!(),
        }
    }
}

pub fn nmul(a: &AdNum, b: &AdNum) -> AdNum {
    if is_float(a) || is_float(b) {
        AdNum::Float(to_float(a) * to_float(b))
    } else if matches!(a, AdNum::Rat(_)) || matches!(b, AdNum::Rat(_)) {
        normalize_rat(to_rational(a) * to_rational(b))
    } else {
        match (a, b) {
            (AdNum::Int(x), AdNum::Int(y)) => AdNum::Int(Integer::from(x * y)),
            _ => unreachable!(),
        }
    }
}

pub fn ndiv(a: &AdNum, b: &AdNum) -> Result<AdNum, NumError> {
    if is_float(a) || is_float(b) {
        return Ok(AdNum::Float(to_float(a) / to_float(b)));
    }
    if is_zero(b) {
        return Err(NumError::DivisionByZero);
    }
    Ok(normalize_rat(to_rational(a) / to_rational(b)))
}

pub fn npow(a: &AdNum, b: &AdNum) -> Result<AdNum, NumError> {
    if let Some(n) = as_integer_exponent(b) {
        return npow_int(a, n);
    }
    // Non-integer exponent: no exact tier applies, fall to float.
    Ok(AdNum::Float(to_float(a).pow(to_float(b))))
}

fn npow_int(a: &AdNum, n: Integer) -> Result<AdNum, NumError> {
    if is_float(a) {
        // rug::Float::pow wants an integer exponent type it knows about; f64 covers the
        // range any real exponent here will take.
        let exp = n.to_f64();
        return Ok(AdNum::Float(to_float(a).pow(exp)));
    }
    match n.cmp0() {
        Ordering::Equal => Ok(AdNum::Int(Integer::from(1))),
        Ordering::Greater => {
            let base = to_rational(a);
            let exp: u32 = n.to_u32().expect("exponent too large to represent");
            Ok(normalize_rat(base.pow(exp)))
        }
        Ordering::Less => {
            // Negative integer exponent on an exact value: invert then raise. `0^-n` is
            // the same failure as `1/0` and must be reported the same way — this is the
            // explicit guard the Julia port only reached incidentally through `ndiv`.
            if is_zero(a) {
                return Err(NumError::DivisionByZero);
            }
            let base = to_rational(a);
            let pos_exp: u32 = (-n).to_u32().expect("exponent too large to represent");
            Ok(normalize_rat(base.pow(pos_exp).recip()))
        }
    }
}

pub fn nneg(a: &AdNum) -> AdNum {
    match a {
        AdNum::Int(i) => AdNum::Int(-i.clone()),
        AdNum::Rat(r) => AdNum::Rat(-r.clone()),
        AdNum::Float(f) => AdNum::Float(-f.clone()),
    }
}

pub fn neq(a: &AdNum, b: &AdNum) -> bool {
    if is_float(a) || is_float(b) {
        to_float(a) == to_float(b)
    } else {
        to_rational(a) == to_rational(b)
    }
}

pub fn nshow(a: &AdNum) -> String {
    match a {
        AdNum::Int(i) => i.to_string(),
        AdNum::Rat(r) => format!("{}/{}", r.numer(), r.denom()),
        AdNum::Float(f) => show_float(f),
    }
}

/// `rug::Float`'s own `Display` prints at full internal precision (e.g. `1.0` renders as
/// `"1.0000000000000000"`, and large magnitudes get imprecise trailing digits in
/// scientific notation) — it is not shortest-round-trip output. At `DEFAULT_FLOAT_PREC`
/// (53 bits) a value converts to `f64` losslessly, so format through `f64`'s `Display`
/// instead, which *is* shortest-round-trip, and append a trailing `.0` when Rust's
/// formatter would otherwise omit the decimal point entirely (`1.0f64` prints as `"1"`).
fn show_float(f: &Float) -> String {
    if f.is_nan() {
        return "NaN".to_string();
    }
    if f.is_infinite() {
        return if f.is_sign_negative() { "-Inf".to_string() } else { "Inf".to_string() };
    }
    let v = f.to_f64();
    let s = format!("{v}");
    if s.contains('.') || s.contains('e') {
        s
    } else {
        format!("{s}.0")
    }
}

/// Parse a numeric literal's source text (as produced by the lexer: `digit+` optionally
/// followed by `.digit+`) into an `AdNum`. A literal containing `.` is a float; otherwise
/// it's parsed as an exact bignum integer.
pub fn parse_literal(text: &str) -> AdNum {
    if text.contains('.') {
        let v: f64 = text.parse().expect("lexer only emits well-formed number text");
        AdNum::Float(new_float(v))
    } else {
        let i = Integer::parse(text).expect("lexer only emits well-formed number text");
        AdNum::Int(Integer::from(i))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn int(n: i64) -> AdNum {
        AdNum::Int(Integer::from(n))
    }
    fn rat(n: i64, d: i64) -> AdNum {
        AdNum::Rat(Rational::from((n, d)))
    }

    #[test]
    fn exact_rational_sum_collapses_to_integer() {
        let a = rat(1, 3);
        let sum = nadd(&nadd(&a, &a), &a);
        assert_eq!(nshow(&sum), "1");
        assert!(matches!(sum, AdNum::Int(_)));
    }

    #[test]
    fn integer_division_collapses() {
        let r = ndiv(&int(6), &int(2)).unwrap();
        assert_eq!(nshow(&r), "3");
        assert!(matches!(r, AdNum::Int(_)));
    }

    #[test]
    fn npow_negative_integer_exponent_is_exact() {
        let r = npow(&int(2), &int(-1)).unwrap();
        assert_eq!(nshow(&r), "1/2");
    }

    #[test]
    fn division_by_zero_is_typed() {
        assert_eq!(ndiv(&int(1), &int(0)).unwrap_err(), NumError::DivisionByZero);
    }

    #[test]
    fn zero_to_negative_power_is_typed_division_by_zero() {
        assert_eq!(npow(&int(0), &int(-1)).unwrap_err(), NumError::DivisionByZero);
    }

    #[test]
    fn neq_compares_exact_values() {
        assert!(neq(&rat(1, 2), &rat(2, 4)));
        assert!(!neq(&int(1), &int(2)));
    }

    #[test]
    fn display_matches_pinned_forms() {
        assert_eq!(nshow(&rat(1, 2)), "1/2");
        assert_eq!(nshow(&rat(1, 3)), "1/3");
        assert_eq!(nshow(&int(2)), "2");
        assert_eq!(nshow(&int(7)), "7");
    }

    #[test]
    fn float_display_parity() {
        let one = AdNum::Float(new_float(1.0));
        assert_eq!(nshow(&nadd(&AdNum::Float(new_float(0.5)), &AdNum::Float(new_float(0.5)))), "1.0");
        assert_eq!(nshow(&one), "1.0");
        let sqrt2 = AdNum::Float(new_float(2.0f64.sqrt()));
        assert_eq!(nshow(&sqrt2), "1.4142135623730951");
    }
}
