"""Exact unit scales and dimensional arithmetic at the numeric boundary."""

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any


DIMENSIONLESS = (Fraction(0),) * 7
BASE_NAMES = ("metre", "kilogram", "second", "ampere", "kelvin", "mole", "candela")


@dataclass(frozen=True)
class UnitValue:
    name: str
    scale: Any
    dimensions: tuple[Fraction, ...]


@dataclass(frozen=True)
class Quantity:
    magnitude: Any
    dimensions: tuple[Fraction, ...]
    display_unit: UnitValue | None = field(default=None, compare=False)


def _runtime():
    from . import runtime
    return runtime


def parts(value):
    if isinstance(value, UnitValue):
        return value.scale, value.dimensions
    if isinstance(value, Quantity):
        return value.magnitude, value.dimensions
    return value, DIMENSIONLESS


def dimensions(value):
    from .tensor import TensorValue
    if isinstance(value, TensorValue):
        dims = [parts(item)[1] for item in value.items]
        if dims and any(d != dims[0] for d in dims):
            raise _runtime().NumError("tensor entries must have matching dimensions")
        return dims[0] if dims else DIMENSIONLESS
    return parts(value)[1]


def combine(a, b, sign=1):
    return tuple(x + sign * y for x, y in zip(a, b))


def power(dims, exponent):
    return tuple(x * exponent for x in dims)


def attach(magnitude, dims, display=None):
    from .tensor import TensorValue
    if isinstance(magnitude, TensorValue):
        return TensorValue(magnitude.shape, tuple(attach(v, dims, display) for v in magnitude.items))
    return Quantity(magnitude, dims, display) if dims != DIMENSIONLESS or display else magnitude


def strip(value):
    from .tensor import TensorValue
    dims = dimensions(value)
    if isinstance(value, TensorValue):
        return TensorValue(value.shape, tuple(parts(v)[0] for v in value.items)), dims
    return parts(value)


def matching(a, b):
    am, ad = parts(a)
    bm, bd = parts(b)
    if ad != bd:
        raise _runtime().NumError("operands must have matching dimensions")
    return am, bm, ad


def binary(op, a, b):
    r = _runtime()
    am, ad = parts(a)
    bm, bd = parts(b)
    r._reject_non_numeric(am, bm)
    if op in ("add", "sub", "mod"):
        am, bm, dims = matching(a, b)
    elif op in ("mul", "div"):
        dims = combine(ad, bd, 1 if op == "mul" else -1)
    else:
        if bd != DIMENSIONLESS:
            raise r.NumError("an exponent must be dimensionless")
        if ad != DIMENSIONLESS and (isinstance(bm, bool) or not isinstance(bm, int | Fraction)):
            raise r.NumError("a dimensioned base needs an exact rational exponent")
        dims = power(ad, Fraction(bm)) if ad != DIMENSIONLESS else DIMENSIONLESS
    return attach(getattr(r, "n" + op)(am, bm), dims)


def unary(value, operation):
    magnitude, dims = parts(value)
    return attach(operation(magnitude), dims)


def dimensionless(value, label):
    magnitude, dims = parts(value)
    if dims != DIMENSIONLESS:
        raise _runtime().NumError(f"{label} needs a dimensionless argument")
    return magnitude


def target(value):
    r = _runtime()
    if isinstance(value, UnitValue):
        return value
    if not isinstance(value, Quantity):
        raise r.NumError("conversion target must be a unit or scaled unit quantity")
    if r._is_inexact(value.magnitude) or r._is_complex(value.magnitude) or not r.ncompare("gt", value.magnitude, 0):
        raise r.NumError("unit scale must be positive, finite and exact")
    return UnitValue("", value.magnitude, value.dimensions)


def convert(value, unit):
    magnitude, dims = strip(value)
    chosen = target(unit)
    if dims != chosen.dimensions:
        raise _runtime().NumError("conversion requires matching dimensions")
    return attach(magnitude, dims, chosen)


def extract(value, unit):
    magnitude, dims = strip(value)
    chosen = target(unit)
    if dims != chosen.dimensions:
        raise _runtime().NumError("conversion requires matching dimensions")
    return _runtime().ndiv(magnitude, chosen.scale)


def make_unit(name, scale):
    from .lexer import Backslash, LexError, tokenize
    r = _runtime()
    if not isinstance(name, str):
        raise r.NumError("unit name must be a command name")
    try:
        tokens = tokenize("\\" + name)
        valid = len(tokens) == 2 and isinstance(tokens[0], Backslash) and tokens[0].name == name
    except LexError:
        valid = False
    if not valid or name in r.PRELUDE or name in r.RESERVED_NAMES:
        raise r.NumError("unit name must be a fresh command name")
    if isinstance(scale, UnitValue | Quantity):
        chosen = target(scale)
        magnitude, dims = chosen.scale, chosen.dimensions
    else:
        r._reject_non_numeric(scale)
        magnitude, dims = scale, DIMENSIONLESS
        if r._is_inexact(magnitude) or r._is_complex(magnitude) or not r.ncompare("gt", magnitude, 0):
            raise r.NumError("unit scale must be positive, finite and exact")
    return UnitValue(name, magnitude, dims)


def unit_text(dims):
    terms = []
    for name, exponent in zip(BASE_NAMES, dims):
        if exponent:
            suffix = "" if exponent == 1 else f"^({exponent})"
            terms.append("\\" + name + suffix)
    return "*".join(terms) or "1"


def show(value, render):
    if isinstance(value, UnitValue):
        return "\\" + value.name
    unit = value.display_unit
    magnitude = value.magnitude if unit is None else _runtime().ndiv(value.magnitude, unit.scale)
    suffix = unit_text(value.dimensions)
    if unit is not None:
        suffix = "\\" + unit.name if unit.name else f"({render(unit.scale)}*{suffix})"
    text = render(magnitude)
    if _runtime()._is_complex(magnitude):
        text = f"({text})"
    return f"{text}*{suffix}"


def catalogue():
    result = {}
    for index, name in enumerate(BASE_NAMES):
        dims = tuple(Fraction(int(i == index)) for i in range(7))
        result[name] = UnitValue(name, 1, dims)
    result["gram"] = UnitValue("gram", Fraction(1, 1000), result["kilogram"].dimensions)
    derived = {
        "radian": (0, 0, 0, 0, 0, 0, 0), "steradian": (0, 0, 0, 0, 0, 0, 0),
        "hertz": (0, 0, -1, 0, 0, 0, 0), "newton": (1, 1, -2, 0, 0, 0, 0),
        "pascal": (-1, 1, -2, 0, 0, 0, 0), "joule": (2, 1, -2, 0, 0, 0, 0),
        "watt": (2, 1, -3, 0, 0, 0, 0), "coulomb": (0, 0, 1, 1, 0, 0, 0),
        "volt": (2, 1, -3, -1, 0, 0, 0), "farad": (-2, -1, 4, 2, 0, 0, 0),
        "ohm": (2, 1, -3, -2, 0, 0, 0), "siemens": (-2, -1, 3, 2, 0, 0, 0),
        "weber": (2, 1, -2, -1, 0, 0, 0), "tesla": (0, 1, -2, -1, 0, 0, 0),
        "henry": (2, 1, -2, -2, 0, 0, 0), "lumen": (0, 0, 0, 0, 0, 0, 1),
        "lux": (-2, 0, 0, 0, 0, 0, 1), "becquerel": (0, 0, -1, 0, 0, 0, 0),
        "gray": (2, 0, -2, 0, 0, 0, 0), "sievert": (2, 0, -2, 0, 0, 0, 0),
        "katal": (0, 0, -1, 0, 0, 1, 0),
    }
    result.update({name: UnitValue(name, 1, tuple(map(Fraction, dims))) for name, dims in derived.items()})
    roots = ("metre", "gram", "second", "ampere", "mole", "candela", *derived)
    for prefix, exponent in (("kilo", 3), ("mega", 6), ("giga", 9), ("centi", -2),
                             ("milli", -3), ("micro", -6), ("nano", -9)):
        for root in roots:
            if prefix + root not in result:
                scale = Fraction(10) ** exponent * result[root].scale
                result[prefix + root] = UnitValue(prefix + root, scale, result[root].dimensions)
    return result
