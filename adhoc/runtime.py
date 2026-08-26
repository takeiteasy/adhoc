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

## Strings and the `\\py` boundary

Strings are literals, not ad values (docs/grammar.md). They never enter the environment;
the only place one exists at runtime is transiently, as a native `str` produced by a call.
The conversion matrix (`_to_ad`) is therefore deliberately small:

- bool → int (true becomes 1), int/float/Fraction pass through, `numbers.Rational`
  collapses to Fraction/int, other `numbers.Real` widens to float, Decimal converts
  exactly via Fraction.
- `str` is display-only: printable by `out`, rejected by assignment and arithmetic.
- complex, None, and everything else (lists, dicts, ...) are span-pointed rejections —
  no silent truncation.

`Engine.py` resolves a dotted path like `math.sqrt` (longest importable module prefix,
then attributes) and requires the result to be callable. This is a full-trust escape
hatch by design: a script that can call `\\py` can do anything Python can.

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
import importlib
import math
import numbers
from typing import Any, NoReturn

from .span import Span

AdValue = int | Fraction | float

DIVISION_BY_ZERO = "division by zero"
STRINGS_NOT_NUMBERS = "strings are not numbers"
NOT_A_NUMBER = "operands must be numbers"

DEFAULT_FLOAT_PRECISION_BITS = 53

_NUMERIC_TYPES = (int, float, Fraction)


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


def _reject_non_numeric(*vals: AdValue) -> None:
    """Guard the arithmetic seam against everything that is not an ad number — a
    transient string (literals, not values) or a bound callable reaching an operator.
    The failure must stay a spanned NumError, never a TypeError escaping the engine."""
    for v in vals:
        if isinstance(v, str):
            raise NumError(STRINGS_NOT_NUMBERS)
        if not isinstance(v, _NUMERIC_TYPES):
            raise NumError(NOT_A_NUMBER)


def nadd(a: AdValue, b: AdValue) -> AdValue:
    _reject_non_numeric(a, b)
    if _is_float(a) or _is_float(b):
        return _to_float(a) + _to_float(b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) + Fraction(b))
    return a + b


def nsub(a: AdValue, b: AdValue) -> AdValue:
    _reject_non_numeric(a, b)
    if _is_float(a) or _is_float(b):
        return _to_float(a) - _to_float(b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) - Fraction(b))
    return a - b


def nmul(a: AdValue, b: AdValue) -> AdValue:
    _reject_non_numeric(a, b)
    if _is_float(a) or _is_float(b):
        return _to_float(a) * _to_float(b)
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        return _normalize(Fraction(a) * Fraction(b))
    return a * b


def ndiv(a: AdValue, b: AdValue) -> AdValue:
    _reject_non_numeric(a, b)
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
    _reject_non_numeric(a, b)
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
    _reject_non_numeric(a)
    return -a


def neq(a: AdValue, b: AdValue) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        # Unreachable through assignment (strings are rejected before compare); kept
        # defensive: a string only ever equals itself.
        return a is b if isinstance(a, str) and isinstance(b, str) else False
    if not isinstance(a, _NUMERIC_TYPES) or not isinstance(b, _NUMERIC_TYPES):
        return a is b  # callables and other exotics compare by identity
    if _is_float(a) or _is_float(b):
        return _to_float(a) == _to_float(b)
    return Fraction(a) == Fraction(b)


def nshow(v: AdValue | str) -> str:
    if isinstance(v, str):
        return _show_str(v)
    if callable(v) and not isinstance(v, _NUMERIC_TYPES):
        return _show_callable(v)
    if isinstance(v, float):
        return _show_float(v)
    return str(v)


def _show_str(s: str) -> str:
    """Display-only strings print quoted and round-trippable — they can never be bound,
    so this is purely a transcript rendering."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _show_callable(fn: Any) -> str:
    """Bound callables print as `<py module.qualname>` where the object carries one."""
    mod = getattr(fn, "__module__", None)
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
    if name:
        prefix = f"{mod}." if mod else ""
        return f"<py {prefix}{name}>"
    return f"<py {type(fn).__name__}>"


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


_MISSING = object()


def _resolve_dotted(path: str) -> Any:
    """Resolve `math.sqrt`-style paths: import the longest importable module prefix,
    then walk attributes over the rest. Bare names (`int`, `len`) resolve against
    `builtins`. Returns _MISSING when unresolvable."""
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr, _MISSING)
            if obj is _MISSING:
                return _MISSING
        return obj
    import builtins

    return getattr(builtins, path, _MISSING)


def _to_ad(value: Any) -> Any:
    """The Python→ad half of the interop conversion matrix (see module docstring).
    Raises NumError with a matrix-specific message on everything without an ad
    representation; the caller attaches the call's span."""
    if value is None:
        raise NumError("the call returned nothing")
    if isinstance(value, bool):  # before int — bool is an int subclass
        return int(value)
    if isinstance(value, int | float | Fraction):
        return value
    if isinstance(value, Decimal):
        return _normalize(Fraction(value))
    if isinstance(value, numbers.Rational):
        # Two-arg construction normalizes; the single-Rational-arg form copies
        # numerator/denominator verbatim on py3.12+.
        return _normalize(Fraction(int(value.numerator), int(value.denominator)))
    if isinstance(value, str):
        # Display-only: printable by out(), rejected by assign and arithmetic.
        return value
    if isinstance(value, complex):
        raise NumError("complex results are not supported")
    if isinstance(value, numbers.Real):
        return float(value)
    raise NumError(f"cannot convert a returned {type(value).__name__} to an ad value")


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
        if name == "py":
            self._fail('`\\py` must be applied to a path: \\py("dotted.path")', sid)
        self._fail(f"`\\{name}` is not bound", sid)

    def reserved(self, sid: int) -> NoReturn:
        """The parsed-but-unimplemented definition shape `f(x) = body` lowers here."""
        self._fail("function definitions are not implemented yet (reserved for phase 1)", sid)

    def py(self, path: Any, sid: int) -> Any:
        """`\\py("dotted.path")` — resolve a Python dotted path to a callable. The
        argument must be a string literal; strings cannot be bound, so no other arg
        shape can ever name a path."""
        if not isinstance(path, str):
            self._fail("`\\py` takes one string literal naming a dotted Python path", sid)
        obj = _resolve_dotted(path)
        if obj is _MISSING:
            self._fail(f"`\\py` cannot resolve `{path}`", sid)
        if not callable(obj):
            self._fail(f"`{path}` is not callable", sid)
        return obj

    def app(self, fn: Any, args: tuple[Any, ...], sid: int) -> AdValue | str:
        """Postfix application `f(args)` lowered to one seam call. Arguments are already
        native ad values (or literal strs headed for Python); the result converts back
        through the matrix. Failures point at the whole call node's span."""
        if isinstance(fn, str):
            # A display-only string applied as a function — same rejection rule as
            # everywhere else a transient string tries to act like a value.
            self._fail(f"{nshow(fn)} is not a function", sid)
        if not callable(fn):
            self._fail(f"{nshow(fn)} is not a function", sid)
        try:
            result = fn(*args)
        except NumError:
            raise
        except EvalError:
            raise
        except Exception as e:
            name = getattr(fn, "__name__", None) or "<callable>"
            self._fail(f"{name}: {type(e).__name__}: {e}", sid)
        try:
            return _to_ad(result)
        except NumError as e:
            self._fail(e.args[0], sid)

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

    def out(self, v: AdValue | str, sid: int) -> str:
        result = f"= {nshow(v)}"
        self.outputs.append(result)
        return result

    def _check_assignable(self, value: AdValue | str, sid: int) -> None:
        # Strings are literals, not values: they print (display-only) but never bind.
        if isinstance(value, str):
            self._fail("strings cannot be assigned — they are literals, not values", sid)

    def assign(self, name: str, value: AdValue, sid: int) -> str:
        self._check_assignable(value, sid)
        if name in self.env:
            matches = neq(self.env[name], value)
            result = "true" if matches else "false"
        else:
            self.env[name] = value
            result = f"{name} = {nshow(value)}"
        self.outputs.append(result)
        return result

    def reassign(self, name: str, value: AdValue, sid: int) -> str:
        self._check_assignable(value, sid)
        if name not in self.env:
            self._fail(f"`{name}` does not exist!", sid)
        self.env[name] = value
        result = f"{name} = {nshow(value)}"
        self.outputs.append(result)
        return result
