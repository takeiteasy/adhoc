"""The numeric seam plus the statement machinery the lowered code calls into.

Mirrors `num.rs` one-to-one (`nadd`/`nsub`/`nmul`/`ndiv`/`npow`/`nneg`/`neq`/`nshow`).
Values map onto Python natives — Int→`int`, Rat→`fractions.Fraction`, Float→`float` —
and arithmetic stays at the lowest tier that remains exact:

1. `int` — arbitrary precision natively.
2. `Fraction` — arbitrary precision rational; auto-normalized, and collapsed back to
   `int` whenever its denominator is 1, or display would print `"1/1"`-style values.
3. `float` — once an operation can't stay exact (float literal, non-integer exponent).

The `Engine` object is the seam's other half: every operation in generated code routes
through it carrying a span id, which is what keeps runtime-error spans narrow (a
sub-expression's failure points at the sub-expression, matching interp.rs's narrowing).
Statement-level bind-or-compare lives here too, since `=` never lowers to Python
assignment.

## Pinned divergences from the rug/MPFR backing (docs/numerics.md)

- Float division by ±0.0 yields signed infinity (NaN only for 0/0) — MPFR semantics;
  CPython's `/` would raise `ZeroDivisionError`.
- Float exponentiation overflow saturates to signed infinity — MPFR has unbounded
  exponent range; CPython raises `OverflowError`.
- Negative base with a fractional exponent yields NaN — MPFR semantics; CPython's `**`
  would silently return a `complex`.
- Display never uses scientific notation: the shortest-round-trip `repr` is expanded
  positionally, matching `f64`'s `Display` (`10000000000000000.0`, `0.0000001`).
"""

from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction
import math
from typing import Any, NoReturn

from .span import Span

AdValue = int | Fraction | float

DIVISION_BY_ZERO = "division by zero"

DEFAULT_FLOAT_PRECISION_BITS = 53


class NumError(Exception):
    """Typed numeric failure raised by the seam. Callers attach the offending
    expression's span to it rather than letting evaluation abort uncaught."""


def _is_float(v: AdValue) -> bool:
    return isinstance(v, float)


def _to_float(v: AdValue) -> float:
    return float(v)


def _normalize(x: Fraction) -> int | Fraction:
    """Collapse a denominator-1 rational back to an integer."""
    if x.denominator == 1:
        return int(x)
    return x


def nadd(a: AdValue, b: AdValue) -> AdValue:
    if _is_float(a) or _is_float(b):
        return _to_float(a) + _to_float(b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) + Fraction(b))
    return a + b


def nsub(a: AdValue, b: AdValue) -> AdValue:
    if _is_float(a) or _is_float(b):
        return _to_float(a) - _to_float(b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) - Fraction(b))
    return a - b


def nmul(a: AdValue, b: AdValue) -> AdValue:
    if _is_float(a) or _is_float(b):
        return _to_float(a) * _to_float(b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) * Fraction(b))
    return a * b


def ndiv(a: AdValue, b: AdValue) -> AdValue:
    if _is_float(a) or _is_float(b):
        return _fdiv(_to_float(a), _to_float(b))
    divisor = Fraction(b)
    if divisor == 0:
        raise NumError(DIVISION_BY_ZERO)
    return _normalize(Fraction(a) / divisor)


def _fdiv(fa: float, fb: float) -> float:
    """Float division under MPFR semantics: division by ±0.0 yields signed infinity
    (NaN only for 0/0), where CPython's `/` would raise ZeroDivisionError."""
    try:
        return fa / fb
    except ZeroDivisionError:
        if fa == 0:
            return math.nan
        sign = math.copysign(1.0, fa) * math.copysign(1.0, fb)
        return math.copysign(math.inf, sign)


def npow(a: AdValue, b: AdValue) -> AdValue:
    n = _integer_exponent(b)
    if n is not None:
        return _pow_exact_base(a, n)
    return _fpow(_to_float(a), _to_float(b))


def _integer_exponent(v: AdValue) -> int | None:
    """An exact integer value usable as an exponent, else None — decides whether an
    exact base can stay exact."""
    if isinstance(v, int):
        return v
    if isinstance(v, Fraction) and v.denominator == 1:
        return int(v)
    return None


def _pow_exact_base(a: AdValue, n: int) -> AdValue:
    if _is_float(a):
        # rug routed integer exponents on float bases through f64 as well.
        return _fpow(_to_float(a), float(n))
    base = Fraction(a)
    if n == 0:
        return 1
    if n > 0:
        return _normalize(base**n)
    # Negative integer exponent on an exact value: invert then raise. `0^-n` is the
    # same failure as `1/0` and must be reported the same way.
    if base == 0:
        raise NumError(DIVISION_BY_ZERO)
    return _normalize(Fraction(1) / base ** (-n))


def _fpow(base: float, exp: float) -> float:
    """Float power under MPFR semantics (see module divergences)."""
    if base < 0 and exp != math.floor(exp):
        return math.nan
    try:
        return base**exp
    except OverflowError:
        if base < 0 and math.isfinite(exp) and math.floor(exp) % 2 != 0:
            return -math.inf
        return math.inf
    except ZeroDivisionError:
        return math.inf  # 0.0 ** negative


def nneg(a: AdValue) -> AdValue:
    return -a


def neq(a: AdValue, b: AdValue) -> bool:
    if _is_float(a) or _is_float(b):
        return _to_float(a) == _to_float(b)
    return Fraction(a) == Fraction(b)


def nshow(v: AdValue) -> str:
    if isinstance(v, float):
        return _show_float(v)
    return str(v)


def _show_float(f: float) -> str:
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "-Inf" if f < 0 else "Inf"
    s = repr(f)  # shortest round-trip
    if "e" in s or "E" in s:
        s = format(Decimal(s), "f")
    if "." not in s:
        s += ".0"
    return s


def parse_literal(text: str) -> AdValue:
    """Parse a number literal's source text (digit+, optionally `.digit+`). A literal
    containing `.` is a float; otherwise an exact integer."""
    if "." in text:
        return float(text)
    return int(text)


class EvalError(Exception):
    """A runtime failure with its message and, when known, the offending span."""

    def __init__(self, msg: str, span: Span | None = None):
        super().__init__(msg)
        self.msg = msg
        self.span = span


class Engine:
    """Everything lowered code calls into. Holds the user environment (a plain dict) and
    the compiled unit's span table; every method takes the span id of the node that
    emitted it so failures carry narrow spans. Formatted statement results accumulate in
    `outputs` in evaluation order — the REPL prints only the last, script mode echoes all
    (matching main.rs's run_and_echo vs repl.rs)."""

    def __init__(self, env: dict[str, Any], spans: Sequence[Span]):
        self.env = env
        self.spans = spans
        self.outputs: list[str] = []

    def _fail(self, msg: str, sid: int) -> NoReturn:
        raise EvalError(msg, self.spans[sid])

    def var(self, name: str, sid: int) -> AdValue:
        try:
            return self.env[name]
        except KeyError:
            self._fail(f"`{name}` is not bound", sid)

    def bref(self, name: str, sid: int) -> AdValue:
        self._fail(f"`\\{name}` is not bound (phase 0 defines no builtins yet)", sid)

    def _binop(self, f, a: AdValue, b: AdValue, sid: int) -> AdValue:
        try:
            return f(a, b)
        except NumError as e:
            self._fail(e.args[0], sid)

    def add(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(nadd, a, b, sid)

    def sub(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(nsub, a, b, sid)

    def mul(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(nmul, a, b, sid)

    def div(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(ndiv, a, b, sid)

    def pow(self, a: AdValue, b: AdValue, sid: int) -> AdValue:
        return self._binop(npow, a, b, sid)

    def neg(self, a: AdValue, sid: int) -> AdValue:
        return nneg(a)

    def out(self, v: AdValue, sid: int) -> str:
        result = f"= {nshow(v)}"
        self.outputs.append(result)
        return result

    def assign(self, name: str, value: AdValue, sid: int) -> str:
        if name in self.env:
            matches = neq(self.env[name], value)
            result = "true" if matches else "false"
        else:
            self.env[name] = value
            result = f"{name} = {nshow(value)}"
        self.outputs.append(result)
        return result

    def reassign(self, name: str, value: AdValue, sid: int) -> str:
        if name not in self.env:
            self._fail(f"`{name}` does not exist!", sid)
        self.env[name] = value
        result = f"{name} = {nshow(value)}"
        self.outputs.append(result)
        return result
