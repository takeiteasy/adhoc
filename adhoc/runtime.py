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

## Convergence

Approximate iteration has exactly one mechanism (docs/numerics.md): drive observations
until successive ones differ by at most `CONVERGENCE_TOLERANCE`, otherwise error at the
cap (`MAX_TERMS` for fold terms, `MAX_PROBES` for `\\lim` probes) rather than return a
possibly-misleading partial result. Two features ride it: `\\sum`/`\\prod` over a lazy
infinite range (limit of partial sums/products) and `\\lim(x=a)` (two-sided shrinking-step
probing that never evaluates at `a`). Both operate in the float tier — exact tiers would
either stall plateau detection behind exponentially-growing rationals or make the
tolerance meaningless — while finite folds accumulate exactly like any other expression.

## Strings and the `\\py` boundary

Strings are ad values (docs/grammar.md): they bind, display, concatenate with `+`, and
compare equal only to other strings. The conversion matrix (`_to_ad`) is deliberately
small:

- bool → int (true becomes 1), int/float/Fraction pass through, `numbers.Rational`
  collapses to Fraction/int, other `numbers.Real` widens to float, Decimal converts
  exactly via Fraction.
- `str` passes through as the value it already is — printable by `out`, bindable,
  concatenable; rejected by every other arithmetic operator.
- complex, None, and everything else (lists, dicts, ...) are span-pointed rejections —
  no silent truncation.

`Engine.py` resolves a dotted path like `math.sqrt` (longest importable module prefix,
then attributes) and requires the result to be callable. This is a full-trust escape
hatch by design: a script that can call `\\py` can do anything Python can.

## Modules and imports

Two statement-level forms, two semantics (a module value and dotted attribute access do
not exist in the grammar — identifiers are one character):

- `\\import("lib")` reads an ad source file, evaluates it once per session in a fresh
  root environment, and binds its top-level names into the importing environment (all
  of them, or only the members after `:`). Resolution searches the importing file's
  directory first, then the working directory. The session's module registry (shared by
  every engine in a session) caches each module by absolute path, so re-imports re-copy
  cached bindings instead of re-evaluating; a file currently being evaluated is a
  circular-import error. Imported functions keep the module's environment as their
  closure — their reads of module globals stay live — while the copied values are
  snapshots. Bindings land as fresh ordinary bindings: a protected or already-bound
  name (identical cached value excepted) is a typed error.
- `\\pyimport("math": \\sqrt, \\tau)` resolves a Python module and binds the named
  members. Member selection is mandatory. Callables bind as callables (the `\\py`
  rule); every other member converts through the interop matrix or fails at the
  import's span. The usual binding rules apply: a protected or already-bound name is a
  typed error.

## The prelude

A built-in scope present in every session (`PRELUDE` below): constants (`\\pi`,
`e`, `\\inf`, `\\nan`, `\\true`, `\\false`) and py-function aliases (`\\sin`, `\\cos`,
`\\tan`, `\\ln`, `\\sqrt` — plain `math.*` callables, float tier; symbolic closed forms
are phase 2).
Unicode spellings of prelude names (`π`, `Σ`, `Π`) are not separate keys: the parser's
alias map normalizes them to the canonical `\\`-name before evaluation, so `π` and
`\\pi` are one name, not two (docs/grammar.md, `## Name aliases`). Prelude names
are permanently protected — they can never be rebound or shadowed, so a parameter,
local, or binder named like a prelude entry is a redefinition error.

## Bindings

One rule everywhere (`Engine.assign`): `x = e` binds a fresh name into the current
frame, or compares by value against a name already bound in that frame (echoing
`true`/`false`; `1 = 1.0` is true — the tower, not the type). Reads walk the frame
chain, binds and compares stay frame-local, and no operation ever rebinds an existing
binding — the language has no reassignment spelling and no declaration operator.
Function definitions (`Engine.define`) are declarations: a protected or already-visible
name is an error.

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
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import importlib
import math
import numbers
import os
import types
from typing import Any, NoReturn

from .span import Span

AdValue = int | Fraction | float | bool | str

DIVISION_BY_ZERO = "division by zero"
STRINGS_NOT_NUMBERS = "strings are not numbers"
NOT_A_NUMBER = "operands must be numbers"

DEFAULT_FLOAT_PRECISION_BITS = 53

# Convergence knobs — the one approximate-iteration mechanism shared by infinite-range
# Σ/Π folds and `\lim` (see module docstring and docs/numerics.md).
CONVERGENCE_TOLERANCE = 1e-12
EXACT_CONVERGENCE_TOLERANCE = Fraction(1, 10**12)
MAX_TERMS = 2_000_000
MAX_PROBES = 200

FOLD_LABELS = {"add": "\\sum", "mul": "\\prod"}

_NUMERIC_TYPES = (int, float, Fraction)

# The prelude scope: built-in constants and py-function aliases, present in every
# session (see the module docstring). `\ln` is natural log (math.log); the function
# aliases are the float-tier `math.*` callables themselves — the symbolic tier will
# replace these bindings in place, users never rebind them.
PRELUDE: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
    "nan": math.nan,
    "true": True,
    "false": False,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "ln": math.log,
    "sqrt": math.sqrt,
}

_PRELUDE_PROTECTED = frozenset(PRELUDE)


@dataclass(frozen=True)
class RangeValue:
    """A lazy arithmetic progression; `end=None` denotes an infinite range."""

    start: AdValue
    step: AdValue
    end: AdValue | None
    second: AdValue | None = None

    def __iter__(self):
        current = self.start
        if self.end is None:
            while True:
                yield current
                current = nadd(current, self.step)
        elif self.step > 0:
            while current <= self.end:
                yield current
                current = nadd(current, self.step)
        else:
            while current >= self.end:
                yield current
                current = nadd(current, self.step)


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
    string value (a full value, but never a numeric operand; `+` concats before this
    guard runs) or a bound callable reaching an operator. The failure must stay a
    spanned NumError, never a TypeError escaping the engine."""
    for v in vals:
        if isinstance(v, bool):
            raise NumError("booleans are not numbers")
        if isinstance(v, str):
            raise NumError(STRINGS_NOT_NUMBERS)
        if not isinstance(v, _NUMERIC_TYPES):
            raise NumError(NOT_A_NUMBER)


def nadd(a: AdValue, b: AdValue) -> AdValue:
    if isinstance(a, str) and isinstance(b, str):
        return a + b  # string + string concatenates; mixed never coerces
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
        # Value equality for string×string (the re-assignment check binds no names, so
        # this is its only equality surface — the language has no == operator); a
        # string is never equal to a non-string.
        return a == b if isinstance(a, str) and isinstance(b, str) else False
    if not isinstance(a, _NUMERIC_TYPES) or not isinstance(b, _NUMERIC_TYPES):
        return a is b  # callables and other exotics compare by identity
    if _is_float(a) or _is_float(b):
        return _to_float(a) == _to_float(b)
    return Fraction(a) == Fraction(b)


def nshow(v: AdValue | str) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, AdFunction):
        if not v.name:
            return f"<λ({', '.join(v.params)})>"
        label = f"\\{v.name}" if len(v.name) > 1 else v.name
        return f"<fn {label}({', '.join(v.params)})>"
    if isinstance(v, str):
        return _show_str(v)
    if isinstance(v, RangeValue):
        start = nshow(v.start)
        middle = f",{nshow(v.second)}" if v.second is not None else ""
        end = "" if v.end is None else nshow(v.end)
        suffix = " (lazy, infinite)" if v.end is None else ""
        return f"<range {start}{middle}..{end}{suffix}>"
    if callable(v) and not isinstance(v, _NUMERIC_TYPES):
        return _show_callable(v)
    if isinstance(v, float):
        return _show_float(v)
    return str(v)


def _show_str(s: str) -> str:
    """Strings print quoted and round-trippable: the `\"`/`\\\\` escaping the lexer
    decodes is exactly what this emits, so a displayed string can be read back."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _show_callable(fn: Any) -> str:
    """Bound callables print as `<py module.qualname>` where the object carries one."""
    mod = getattr(fn, "__module__", None)
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
    if name:
        prefix = f"{mod}." if mod else ""
        return f"<py {prefix}{name}>"
    return f"<py {type(fn).__name__}>"


def _name_text(name: str) -> str:
    return name if len(name) == 1 else f"\\{name}"


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


def _as_float(value: AdValue) -> float:
    """Widen an ad number to the float tier for approximate iteration (infinite-range
    folds and `\\lim` probes). Non-numerics are rejected with the seam's typed error so
    the caller can attach a span."""
    _reject_non_numeric(value)
    try:
        return float(value)
    except OverflowError:
        raise NumError("value too large to widen to float")


def _settled(previous: AdValue, current: AdValue) -> bool:
    """The shared plateau test for every approximate iteration (infinite Σ/Π partials,
    `\\lim` probes): the magnitude of change since the last observation is within the
    convergence tolerance. A non-finite float delta never settles."""
    if isinstance(previous, float) or isinstance(current, float):
        delta = float(previous) - float(current)
        return math.isfinite(delta) and abs(delta) <= CONVERGENCE_TOLERANCE
    delta = nsub(previous, current)
    return -EXACT_CONVERGENCE_TOLERANCE <= Fraction(delta) <= EXACT_CONVERGENCE_TOLERANCE


def _agree(left: float, right: float) -> bool:
    """The `\\lim` two-sided agreement test, sized off the same tolerance: each side
    stops within CONVERGENCE_TOLERANCE of its own plateau — up to that far from the
    true limit even for a perfectly smooth body — so legitimate estimates may sit as
    much as 2× the tolerance apart. Anything wider is a genuine disagreement."""
    return abs(left - right) <= 2 * CONVERGENCE_TOLERANCE


class EvalError(Exception):
    """A runtime failure with its message and, when known, the offending span."""

    def __init__(self, msg: str, span: Span | None = None):
        super().__init__(msg)
        self.msg = msg
        self.span = span


_MISSING = object()
_IMPORTING = object()  # module-registry marker: evaluation in progress (cycle guard)


class AdFunction:
    def __init__(self, name, params, body, closure):
        self.name, self.params, self.body, self.closure = name, params, body, closure

    def __call__(self, *args):
        if len(args) != len(self.params):
            # Anonymous functions (name "") report the λ spelling.
            raise EvalError(f"{self.name or 'λ'} takes {len(self.params)} arguments, "
                            f"got {len(args)}")
        frame = dict(zip(self.params, args))
        if self.name:
            frame[self.name] = self
        child = Engine(frame, self.body.spans, self.body.definitions, self.closure,
                       self.closure.modules,
                       self.closure.base_dir, self.closure.import_chain)
        try:
            scope = {"_e": child}
            exec(self.body.code, scope)
        except EvalError:
            raise
        return scope["_result"]


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
    if isinstance(value, AdFunction):
        return value
    if isinstance(value, RangeValue):
        return value
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
        # Already an ad value: bindable, concatenable, printable.
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

    def __init__(self, env: dict[str, Any], spans: Sequence[Span], definitions=None,
                 parent=None, modules: dict | None = None,
                 base_dir: str | None = None, import_chain: tuple[str, ...] = ()):
        self.env = env
        self.spans = spans
        self.definitions = definitions or {}
        self.parent = parent
        # The session's module registry (absolute path -> module environment) and the
        # directory relative to which `\import` resolves files. Both ride on the root
        # engine and are inherited by every child frame and imported module engine.
        self.modules = modules if modules is not None else {}
        self.base_dir = base_dir
        # Absolute paths of modules currently being evaluated up the import stack —
        # what a circular-import error names.
        self.import_chain = import_chain
        self.outputs: list[str] = []
        self.result: Any = None

    def _fail(self, msg: str, sid: int) -> NoReturn:
        raise EvalError(msg, self.spans[sid])

    def _protected(self, name: str) -> bool:
        """Prelude names are protected everywhere — the only protected set, since
        user bindings are immutable by the binding rule itself. Covers rebinding by
        `=`, function definition, and — at the definition/binder sites — parameters
        and loop variables, so a protected name can never be shadowed."""
        return name in _PRELUDE_PROTECTED

    def _lookup(self, name: str) -> Any:
        """Walk the frame chain for `name`; the prelude sits outermost. Returns
        _MISSING instead of failing so the caller reports with its own span table —
        a parent engine's table is a different unit's and must never be indexed with
        this frame's span ids."""
        scope = self
        while scope is not None:
            if name in scope.env:
                return scope.env[name]
            scope = scope.parent
        return PRELUDE.get(name, _MISSING)

    def var(self, name: str, sid: int) -> AdValue:
        value = self._lookup(name)
        if value is _MISSING:
            self._fail(f"`{name}` is not bound", sid)
        return value

    def bref(self, name: str, sid: int) -> AdValue:
        if name == "py":
            self._fail(r'`\py` must be applied to a path: \py("dotted.path")', sid)
        if name == "if":
            self._fail("`\\if` is a block: \\if condition NL branch NL [\\elseif … NL] "
                       "[\\else … NL] \\end", sid)
        if name == "import":
            self._fail(r'`\import` reads an ad file: \import("lib") or \import("lib": f)', sid)
        if name == "pyimport":
            self._fail(r'`\pyimport` binds Python members: \pyimport("math": \sqrt)', sid)
        if name == "alias":
            self._fail("`\\alias` declares short spellings at top level: \\alias \\sum, σ", sid)
        if name == "dual":
            self._fail("`\\dual` defines a name under two spellings: \\dual \\alpha, α = 3.14", sid)
        if name in ("fn", "λ"):
            self._fail("a lambda takes a parenthesized parameter list: \\λ(x) body "
                       "(ASCII spelling \\fn(x) body)", sid)
        value = self._lookup(name)
        if value is _MISSING:
            self._fail(f"`\\{name}` is not bound", sid)
        return value

    def define(self, name, params, sid):
        # Parameters bind into the call frame exactly like assignments, so a protected
        # parameter would shadow a prelude name — rejected at definition.
        for p in params:
            if self._protected(p):
                self._fail(f"`{p}` is protected", sid)
        fn = AdFunction(name, params, self.definitions[sid], self)
        # Definitions are declarations: the name must be fresh and unprotected.
        # Identity comparison would make a check meaningless anyway.
        if self._protected(name):
            self._fail(f"`{name}` is protected", sid)
        if self._lookup(name) is not _MISSING:
            self._fail(f"`{name}` is already bound", sid)
        self.env[name] = fn
        # _name_text sigilates multi-character names, so the echoed line needs no
        # further rebranding.
        result = f"{_name_text(name)} = {nshow(fn)}"
        self.outputs.append(result)
        return result

    def lambda_(self, params, sid):
        """`\\λ(params) body` / `\\fn(params) body` — an anonymous AdFunction closed
        over the defining frame. Parameters reject protected names exactly like
        `define`; there is no self-name to install (recursion goes through named
        defs or a fixpoint combinator), and the empty name is what nshow renders
        as `<λ(x)>`."""
        for p in params:
            if self._protected(p):
                self._fail(f"`{p}` is protected", sid)
        return AdFunction("", params, self.definitions[sid], self)

    def assign(self, name: str, value: AdValue, sid: int,
               echo: bool = False) -> AdValue | bool:
        """`x = e` — declare-once-then-check, the one binding rule. A protected
        prelude name is rejected; a name already bound in the current frame compares
        by value (`1 = 1.0` is true — the tower, not the type); otherwise the name
        binds fresh into this frame. Reads walk the chain, binds and compares stay
        frame-local, and nothing ever rebinds an existing binding. Silent in
        expression position (groups, bodies); statement-level lowering passes
        `echo=True` so the REPL/script transcript shows the outcome."""
        if self._protected(name):
            self._fail(f"`{name}` is protected", sid)
        if name in self.env:
            matches = neq(self.env[name], value)
            if echo:
                self.outputs.append("true" if matches else "false")
            return matches
        self.env[name] = value
        if echo:
            self.outputs.append(f"{_name_text(name)} = {nshow(value)}")
        return value

    def _compare(self, op, a, b, sid):
        try:
            _reject_non_numeric(a, b)
            if isinstance(a, float) or isinstance(b, float):
                a, b = float(a), float(b)
            else:
                a, b = Fraction(a), Fraction(b)
            return {"lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[op]
        except NumError as e:
            self._fail(e.args[0], sid)

    def lt(self, a, b, sid): return self._compare("lt", a, b, sid)
    def le(self, a, b, sid): return self._compare("le", a, b, sid)
    def gt(self, a, b, sid): return self._compare("gt", a, b, sid)
    def ge(self, a, b, sid): return self._compare("ge", a, b, sid)

    def range(self, start, second, end, sid):
        try:
            _reject_non_numeric(start)
            if second is None:
                step = 1
            else:
                _reject_non_numeric(second)
                step = nsub(second, start)
            if end is not None:
                _reject_non_numeric(end)
                # A non-finite endpoint would iterate forever (or never start) in
                # the finite-range loop; `a..` is the language's infinite form.
                if isinstance(end, float) and not math.isfinite(end):
                    raise NumError(
                        "range end must be a finite number (`a..` is the infinite "
                        "range form)")
            if isinstance(step, float) and not math.isfinite(step):
                raise NumError("range step must be a finite number")
            if isinstance(start, float) and not math.isfinite(start):
                raise NumError("range start must be a finite number")
            if step == 0:
                raise NumError("range step cannot be zero")
            return RangeValue(start, step, end, second)
        except NumError as e:
            self._fail(e.args[0], sid)

    def _eval_bound(self, body: Any, bindings: dict[str, AdValue], label: str,
                    sid: int) -> AdValue:
        """Evaluate a compiled body once with the loop variable layered over a child
        frame. Scoping mirrors AdFunction.__call__: reads of other names fall through
        to the parent chain, writes stay local to this iteration."""
        child = Engine(bindings, body.spans, body.definitions, self,
                       self.modules, self.base_dir, self.import_chain)
        scope = {"_e": child}
        try:
            exec(body.code, scope)
        except EvalError:
            raise
        except NumError as e:
            self._fail(e.args[0], sid)
        except Exception as e:
            self._fail(f"{label} failed unexpectedly: {type(e).__name__}: {e}", sid)
        return scope["_result"]

    def fold(self, op_name: str, name: str, value: AdValue, sid: int) -> AdValue:
        """`\\sum(i=a..b) body` / `\\prod(...)`: iterate the bound RangeValue, evaluating
        the compiled body once per term in a fresh frame `{i: term}`. Finite ranges
        accumulate exactly at the lowest exact tier; lazy infinite ranges switch to the
        float tier and stop when successive partials stabilize within
        CONVERGENCE_TOLERANCE — erroring at MAX_TERMS rather than returning a misleading
        partial (docs/numerics.md).
        
        Improvement note: a plateau in consecutive partials can stop marginally early
        for bodies whose value approaches 0 (the remaining tail then exceeds the
        tolerance); a tail-aware or relative stopping rule would tighten that."""
        label = FOLD_LABELS.get(op_name, "\\sum")
        # The loop variable binds like a parameter: a protected name is a
        # redefinition error, never a shadow.
        if self._protected(name):
            self._fail(f"`{name}` is protected", sid)
        if not isinstance(value, RangeValue):
            self._fail(f"{label} folds over a range, got {nshow(value)}", sid)
        fn = nmul if op_name == "mul" else nadd
        unit = 1 if op_name == "mul" else 0
        body = self.definitions[sid]
        acc: AdValue = unit
        infinite = value.end is None
        previous: AdValue | None = None
        count = 0
        for item in value:
            binding = _as_float(item) if infinite else item
            term = self._eval_bound(body, {name: binding}, label, sid)
            acc = self._binop(fn, acc, term, sid)
            count += 1
            if infinite:
                if not math.isfinite(acc):
                    self._fail(f"{label} diverged: partial value is not finite", sid)
                if previous is not None and _settled(previous, acc):
                    return acc
                previous = acc
                if count >= MAX_TERMS:
                    self._fail(f"{label} did not converge within {MAX_TERMS} terms", sid)
        return acc

    def limit(self, name: str, point_value: AdValue, sid: int) -> float:
        """`\\lim(x=a) body`, numeric only: probe both sides with geometrically shrinking
        steps — never evaluating at `a` itself; the ulp guard halts each side when a
        step would round back onto the anchor. Each side must stabilize within
        CONVERGENCE_TOLERANCE (same plateau test as infinite folds) inside MAX_PROBES;
        sides stabilizing apart means the limit does not exist. Probes evaluate in the
        float tier like infinite-range folds (docs/numerics.md)."""
        try:
            _reject_non_numeric(point_value)
        except NumError as e:
            self._fail(e.args[0], sid)
        anchor = _as_float(point_value)
        if not math.isfinite(anchor):
            self._fail("\\lim approaches a finite point", sid)
        if self._protected(name):
            self._fail(f"`{name}` is protected", sid)
        body = self.definitions[sid]
        h = max(abs(anchor), 1.0) * 0.5**7  # start close enough that ~60 halvings pass any ulp floor
        estimates: list[float] = []
        for sign in (1.0, -1.0):  # right side first, then left
            previous: float | None = None
            estimate: float | None = None
            converged = False
            for _ in range(MAX_PROBES):
                probe = anchor + sign * h
                if probe == anchor:
                    break  # step underflowed onto the anchor itself — never evaluate there
                raw = self._eval_bound(body, {name: probe}, "\\lim", sid)
                try:
                    estimate = _as_float(raw)
                except NumError as e:
                    self._fail(e.args[0], sid)
                if previous is not None and _settled(previous, estimate):
                    converged = True
                    break
                previous = estimate
                h *= 0.5
            if not converged:
                self._fail(f"\\lim did not converge within {MAX_PROBES} probes", sid)
            estimates.append(estimate)
        left, right = estimates[1], estimates[0]
        if not _agree(left, right):
            self._fail("limit does not exist: left and right estimates disagree", sid)
        mid = self._binop(nadd, left, right, sid)
        return self._binop(ndiv, mid, 2, sid)

    def if_expr(self, condition, then, otherwise, sid):
        if not isinstance(condition, bool):
            self._fail("\\if condition must be boolean", sid)
        if condition:
            return _to_ad(then())
        if otherwise is None:
            self._fail("\\if condition was false and has no otherwise branch", sid)
        return _to_ad(otherwise())

    def if_stmt(self, condition, then, otherwise, sid):
        """Statement-position `\\if` block: always silent — the selected branch's
        thunks run for their effects (bindings, comparisons), no value is echoed."""
        if not isinstance(condition, bool):
            self._fail("\\if condition must be boolean", sid)
        if condition:
            then()
        elif otherwise is not None:
            otherwise()

    def py(self, path: Any, sid: int) -> Any:
        """`\\py("dotted.path")` — resolve a Python dotted path to a callable. The
        argument must evaluate to a string (a literal or any string-valued
        expression); no other value names a path."""
        if not isinstance(path, str):
            self._fail("`\\py` takes one string naming a dotted Python path", sid)
        obj = _resolve_dotted(path)
        if obj is _MISSING:
            self._fail(f"`\\py` cannot resolve `{path}`", sid)
        if not callable(obj):
            self._fail(f"`{path}` is not callable", sid)
        return obj

    def import_(self, path: Any, members: tuple[str, ...], sid: int) -> None:
        """`\\import("lib")` / `\\import("lib": f, \\g)` — evaluate an ad source file
        once per session in a fresh root environment and bind its top-level names into
        this environment. See the module docstring's "Modules and imports" for the
        full semantics: resolution, caching, cycles, closures, binding rules."""
        if not isinstance(path, str):
            self._fail("`\\import` takes one string literal naming an ad file", sid)
        resolved = self._resolve_ad_file(path, sid)
        chain = self.import_chain + (resolved,)
        if resolved in self.import_chain or self.modules.get(resolved) is _IMPORTING:
            self._fail(f"circular import: {' -> '.join(chain)}", sid)
        record = self.modules.get(resolved)
        if record is None:
            record = self._evaluate_module(resolved, path, sid)
        self._bind_imported(record, members, path, sid)

    def pyimport(self, path: Any, members: tuple[str, ...], sid: int) -> None:
        """`\\pyimport("math": \\sqrt, \\tau)` — resolve a Python module and bind the
        named members into this environment. Callables bind as callables (the `\\py`
        rule); every other member converts through the interop matrix or fails at the
        import's span. Member selection is mandatory (there is no module value to
        bind), and all members validate before any binds."""
        if not isinstance(path, str):
            self._fail(r"`\pyimport` takes one string literal naming a Python module", sid)
        if not members:
            self._fail(r'`\pyimport` binds members by name: \pyimport("math": \sqrt)', sid)
        module = _resolve_dotted(path)
        if module is _MISSING:
            self._fail(f"`\\pyimport` cannot resolve `{path}`", sid)
        if not isinstance(module, types.ModuleType):
            self._fail(f"`{path}` is not a Python module", sid)
        if len(set(members)) != len(members):
            self._fail("duplicate member in `\\pyimport`", sid)
        bound: list[tuple[str, Any]] = []
        for name in members:
            value = getattr(module, name, _MISSING)
            if value is _MISSING:
                self._fail(f"module `{path}` has no member `{_name_text(name)}`", sid)
            if self._protected(name):
                self._fail(f"`{_name_text(name)}` is protected", sid)
            if name in self.env:
                self._fail(f"`{_name_text(name)}` is already bound", sid)
            if callable(value):
                bound.append((name, value))
                continue
            try:
                bound.append((name, _to_ad(value)))
            except NumError as e:
                self._fail(f"member `{_name_text(name)}`: {e.args[0]}", sid)
        for name, value in bound:
            self.env[name] = value

    def _resolve_ad_file(self, path: str, sid: int) -> str:
        r"""The importing file's directory first, then the working directory; `".ad"`
        is appended unless the path already carries it. A path that instead resolves
        as a Python module gets a pointed hint — `\import` and `\pyimport` are
        deliberately separate semantics."""
        name = path if path.endswith(".ad") else f"{path}.ad"
        searched: list[str] = []
        for base in (self.base_dir, os.getcwd()):
            if base is None:
                continue
            candidate = os.path.abspath(os.path.join(base, name))
            if candidate in searched:
                continue
            searched.append(candidate)
            if os.path.isfile(candidate):
                return candidate
        if _resolve_dotted(path) is not _MISSING:
            self._fail(
                f"`{path}` resolves to a Python module; Python imports use "
                + r'`\pyimport("' + path + r'": \member)`', sid)
        self._fail(f"no such ad file `{name}` (searched {', '.join(searched)})", sid)

    def _evaluate_module(self, resolved: str, path: str, sid: int) -> dict:
        """Read, compile, and execute an ad module in a fresh root environment, then
        cache its environment in the session registry. `compile_source` is imported
        late — the driver pairs frontend and exec and sits above this seam, so a
        module-level import would be a cycle. Module outputs are discarded; a parse
        or evaluation failure inside the module fails at the import's span."""
        from .driver import compile_source
        from .parser import ParseError
        try:
            with open(resolved, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            self._fail(f"cannot read `{resolved}`: {e.strerror or e}", sid)
        try:
            unit = compile_source(source)
        except ParseError as e:
            self._fail(f"error in `{path}`: {e.msg}", sid)
        module_env: dict = {}
        engine = Engine(module_env, unit.spans, unit.definitions, None,
                        self.modules, os.path.dirname(resolved),
                        self.import_chain + (resolved,))
        self.modules[resolved] = _IMPORTING
        g: dict = {"_e": engine}
        try:
            exec(unit.code, g)  # noqa: S102 - generated from our own AST only
        except EvalError as e:
            del self.modules[resolved]
            self._fail(f"error evaluating `{path}`: {e.msg}", sid)
        except Exception as e:
            del self.modules[resolved]
            self._fail(f"internal error evaluating `{path}`: {type(e).__name__}: {e}", sid)
        self.modules[resolved] = module_env
        return module_env

    def _bind_imported(self, module_env: dict, members: tuple[str, ...], path: str,
                       sid: int) -> None:
        """Copy bindings out of a (cached) module environment: every top-level name,
        or only the selected members. Everything validates before anything binds, so
        a bad member leaves the environment untouched rather than partially
        imported. A name already bound to the *identical* cached value is a silent
        no-op (re-import), any other collision a typed error."""
        names = members if members else tuple(module_env)
        if len(set(names)) != len(names):
            self._fail("duplicate member in `\\import`", sid)
        for name in names:
            if name not in module_env:
                self._fail(f"`{_name_text(name)}` is not defined in `{path}`", sid)
            if self._protected(name):
                self._fail(f"`{_name_text(name)}` is protected", sid)
            if name in self.env and self.env[name] is not module_env[name]:
                self._fail(f"`{_name_text(name)}` is already bound", sid)
        for name in names:
            self.env[name] = module_env[name]

    def app(self, fn: Any, args: tuple[Any, ...], kwargs: dict[str, Any],
            sid: int) -> AdValue | str:
        """Postfix application `f(args, \\name=value…)` lowered to one seam call, with
        dynamic juxtaposition: a callable head applies; a non-callable head with exactly
        one positional argument and no kwargs falls back to the paper product
        (`x(y+1)` is `x*(y+1)`); any other non-callable shape fails at the call's span.
        The fallback means identical source can read as product or application depending
        on what the head is bound to — accepted deliberately (docs/grammar.md).
        Kwargs pass through to Python callables as native keyword arguments
        (`\\py("math.isclose")(1, 2, \\rel_tol=0.5)`); user-defined functions reject
        them — their parameters are positional."""
        if callable(fn):
            if kwargs and isinstance(fn, AdFunction):
                self._fail("user-defined functions take positional arguments only", sid)
            try:
                result = fn(*args, **kwargs)
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
        if not kwargs and len(args) == 1:
            return self.mul(fn, args[0], sid)
        self._fail(f"{nshow(fn)} is not a function", sid)

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
        # Unary, so not _binop (which passes two operands) — same wrapping contract
        # though: a seam NumError becomes a spanned EvalError at this node's span.
        try:
            return nneg(a)
        except NumError as e:
            self._fail(e.args[0], sid)

    def out(self, v: AdValue | str, sid: int) -> str:
        result = f"= {nshow(v)}"
        self.outputs.append(result)
        return result
