# Numerics: the `num` seam

`src/num.rs` defines an opaque `AdNum` value and a fixed set of operations
(`nadd`, `nsub`, `nmul`, `ndiv`, `npow`, `nneg`, `neq`, `nshow`). `src/interp.rs` never calls a
Rust arithmetic operator directly on a value that came from user input — it only calls through
this seam.

## Why a seam

The design's full tower — bignum integers, bignum rationals, symbolic closed forms (`π`, `√n`,
...), algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback, see `DESIGN.md` — has
no single Rust builtin that covers it. If the interpreter called `+`/`*` directly, adding the
upper tiers later would mean retrofitting arithmetic dispatch through code that was never
written expecting it. Putting the seam in from the start costs a little now and avoids that
later.

## Phase 0 backing

`AdNum` is a three-way enum, backed by [`rug`](https://crates.io/crates/rug) (GMP/MPFR
bindings):

- `Int(rug::Integer)` — arbitrary precision, widens automatically.
- `Rat(rug::Rational)` — arbitrary-precision rational. `rug::Rational` auto-reduces but does
  not auto-collapse a denominator of `1` back to an integer type, so every constructor here
  does that explicitly (`normalize_rat`) — otherwise `nshow` would print `"1/1"` instead of
  `"1"`.
- `Float(rug::Float)` — the fallback once an operation can't stay exact (e.g. non-integer
  powers), at a fixed precision (`DEFAULT_FLOAT_PREC = 53` bits, a double-precision mantissa).

`npow` keeps an exact base exact for integer exponents (including negative ones — `2^-1` is
the exact rational `1/2`, and `0^-n` is a typed `NumError::DivisionByZero`, the same failure
as `1/0`, not a separate untyped error); a non-integer exponent falls to `Float`.

Every failure mode in this module is a typed `NumError`, not a generic error — that's what
lets the REPL and script driver catch "arithmetic failed" specifically and attach the
offending expression's span to it, rather than the whole call aborting.

## Display

Exact rationals display as `a/b` (`1/3` prints `1/3`, not `0.333...`) — the collapse step
above means `nshow` only ever sees a genuinely non-integer value on the `Rat` arm. Decimal
display is reserved for the RRA tier (phase 2): once a value needs RRA to represent at all,
it's no longer exact, so a decimal approximation is the honest display, obtained by
repeatedly requesting tighter tolerance until enough digits are provably stable. Showing an
*exact* rational through that same decimal machinery would be a category error — `1/3` never
leaves the rational tier, per the tower's own "stay at the lowest tier that remains exact"
rule, so it never needs RRA-style display in the first place.

`Float`'s own `Display` prints at full internal precision rather than shortest-round-trip
form (`1.0` would render as `"1.0000000000000000"`), so `nshow` instead converts through
`f64` — lossless at `DEFAULT_FLOAT_PREC`'s 53 bits — and formats through *that*, which is
shortest-round-trip and matches what a user expects (`"1.0"`, `"1.4142135623730951"`).

## What later phases add here

Symbolic closed forms, algebraic numbers, and the RRA fallback all become new cases inside
`AdNum` and this module's dispatch — `src/interp.rs` and everything above it is unaffected by
their addition, which is the entire point of the seam.
