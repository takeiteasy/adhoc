"""Gaussian rationals: the lowest complex tier behind the numeric seam.

An exact complex number with rational components (`2+3i`, `1/2-1/3i`), the
complex analogue of `fractions.Fraction`: every operation on Gaussian
rationals stays exact by ordinary rational arithmetic, with no sympy
involved. Only the numeric seam (`adhoc/runtime.py`) and the exact tiers
(`adhoc/symbolic.py`, `adhoc/algebraic.py`, `adhoc/rra.py`) touch this
module — tiers import it for admission-collapse and operand conversion,
never the other way around (it depends on nothing in the package but
`fractions`, plus sympy for the one conversion helper, so no import cycle).

The invariant: the imaginary part is never zero. A vanishing imaginary
part collapses back to `int`/`Fraction` at every constructor (`make`), the
same way a denominator-1 rational collapses in `runtime._normalize` — so a
`Gaussian` value is always genuinely complex, and display never prints
`"2+0i"`. Components are normalized too (`Fraction` with denominator 1
becomes `int`), so `2+3i` prints as `2+3i`, not `2/1+3/1i`.

Arithmetic (`add`/`sub`/`mul`/`div`/`neg`/`pow_int`) is ordinary exact
rational component arithmetic accepting mixed `int`/`Fraction`/`Gaussian`
operands, mirroring the seam's exact paths: the numeric seam routes
Gaussian-involved combinations here directly (sympy stays for tier mixing),
and every result re-collapses through `make`, so `(2+2i)/(1+i)` is the
integer `2`, never `2+0i`.
"""

from dataclasses import dataclass
from fractions import Fraction

import sympy


@dataclass(frozen=True)
class Gaussian:
    """An exact complex number with `int`/`Fraction` components, imaginary
    part always nonzero (see `make` — construct through it, never directly,
    unless both facts already hold)."""

    re: int | Fraction
    im: int | Fraction


def _comp(v: int | Fraction) -> int | Fraction:
    """Normalize one component: a denominator-1 rational is an integer."""
    if isinstance(v, Fraction) and v.denominator == 1:
        return int(v)
    return v


def make(re: int | Fraction, im: int | Fraction) -> int | Fraction | Gaussian:
    """Build the collapsed form: a vanishing imaginary part returns the real
    part (itself normalized), anything else a normalized `Gaussian`."""
    if im == 0:
        return _comp(re)
    return Gaussian(_comp(re), _comp(im))


def to_sympy(g: Gaussian) -> sympy.Expr:
    """A Gaussian value as a sympy expression — what the exact tiers compute
    with (`int` carries numerator/denominator too, so one shape covers both
    component types)."""
    return (sympy.Rational(Fraction(g.re).numerator, Fraction(g.re).denominator)
            + sympy.I * sympy.Rational(Fraction(g.im).numerator,
                                       Fraction(g.im).denominator))


def show(g: Gaussian) -> str:
    """Exact display, no ellipsis (both components are rationals, printed
    whole): `2+3i`, `2-3i`, `3i`, `-3i`, `i`, `-i`, `1/2+1/3i`."""
    re_text = str(g.re)
    if g.re == 0:
        return _imag_text(g.im)
    if g.im == 1:
        return f"{re_text}+i"
    if g.im == -1:
        return f"{re_text}-i"
    sign = "+" if g.im > 0 else ""
    return f"{re_text}{sign}{g.im}i"


def _imag_text(im: int | Fraction) -> str:
    """The standalone imaginary part: `i`, `-i`, `3i`, `1/2i`."""
    if im == 1:
        return "i"
    if im == -1:
        return "-i"
    return f"{im}i"


def _parts(v: int | Fraction | Gaussian) -> tuple[int | Fraction,
                                                  int | Fraction]:
    """An operand as a (real, imaginary) component pair — a bare exact value
    is the pair (v, 0)."""
    if isinstance(v, Gaussian):
        return v.re, v.im
    return v, 0


def add(a, b) -> int | Fraction | Gaussian:
    """Exact complex addition; collapses through `make`."""
    ar, ai = _parts(a)
    br, bi = _parts(b)
    return make(ar + br, ai + bi)


def sub(a, b) -> int | Fraction | Gaussian:
    """Exact complex subtraction; collapses through `make`."""
    ar, ai = _parts(a)
    br, bi = _parts(b)
    return make(ar - br, ai - bi)


def mul(a, b) -> int | Fraction | Gaussian:
    """Exact complex multiplication (`a+bi)(c+di) = (ac-bd)+(ad+bc)i`); collapses
    through `make` (`(1+i)(1-i)` is the integer `2`)."""
    ar, ai = _parts(a)
    br, bi = _parts(b)
    return make(ar * br - ai * bi, ar * bi + ai * br)


def div(a, b) -> int | Fraction | Gaussian:
    """Exact complex division, rationalizing the denominator:
    `(a+bi)/(c+di) = ((ac+bd)+(bc-ad)i)/(c²+d²)`. A zero divisor — a bare
    exact `0`, since a `Gaussian` never vanishes — raises `ZeroDivisionError`,
    which the seam reports as its typed division-by-zero error."""
    ar, ai = _parts(a)
    br, bi = _parts(b)
    denom = br * br + bi * bi
    if denom == 0:
        raise ZeroDivisionError("division by zero")
    return make(Fraction(ar * br + ai * bi, denom),
                Fraction(ai * br - ar * bi, denom))


def neg(a) -> int | Fraction | Gaussian:
    """Exact complex negation; collapses through `make`."""
    ar, ai = _parts(a)
    return make(-ar, -ai)


def pow_int(a, n: int) -> int | Fraction | Gaussian:
    """Exact complex integer power by binary exponentiation; collapses
    through `make` (`i²` is the integer `-1`, `i⁰` is `1`). A negative
    exponent inverts the positive power; a zero base to a negative power
    raises `ZeroDivisionError` like `div`."""
    if n < 0:
        base = pow_int(a, -n)
        br, bi = _parts(base)
        denom = br * br + bi * bi
        if denom == 0:
            raise ZeroDivisionError("division by zero")
        return make(Fraction(br, denom), Fraction(-bi, denom))
    ar, ai = _parts(a)
    result_r: int | Fraction = 1
    result_i: int | Fraction = 0
    base_r, base_i = ar, ai
    while n > 0:
        if n & 1:
            result_r, result_i = (result_r * base_r - result_i * base_i,
                                  result_r * base_i + result_i * base_r)
        n >>= 1
        if n:
            base_r, base_i = (base_r * base_r - base_i * base_i,
                              2 * base_r * base_i)
    return make(result_r, result_i)
