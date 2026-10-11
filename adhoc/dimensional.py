"""Dimension validation and canonical magnitudes for symbolic operations."""

from dataclasses import fields
from fractions import Fraction

import sympy

from . import units
from .expression import ExpressionValue
from .rewrite import Bridge, RewriteError, _CONSTANTS, _FUNCTIONS
from .syntax import (BackslashRef, BinOp, BinOperator, Call, Equation, Node, NumLit,
                     PowCall, UnaryOperator, UnOp, Var)
from .tensor import ArrayValue


def annotations(value):
    from .rewrite import _quoted_name
    if value is None:
        return {}
    if not isinstance(value, ArrayValue):
        raise RewriteError("dimensions must be an array of quoted-name/unit pairs")
    result = {}
    for item in value.items:
        if not isinstance(item, ArrayValue) or len(item.items) != 2:
            raise RewriteError("dimensions must contain quoted-name/unit pairs")
        name = _quoted_name(item.items[0]).name
        unit = item.items[1]
        scalar_one = not isinstance(unit, bool) and isinstance(unit, int | Fraction) and unit == 1
        if not isinstance(unit, units.UnitValue | units.Quantity) and not scalar_one:
            raise RewriteError("a dimension annotation needs a unit, or 1 for dimensionless")
        if name in result:
            raise RewriteError("dimension annotations must have distinct names")
        result[name] = units.dimensions(unit)
    return result


def unit_node(dims, span):
    result = None
    for name, exponent in zip(units.BASE_NAMES, dims):
        if not exponent:
            continue
        node = BackslashRef(name=name, span=span)
        if exponent != 1:
            power = Bridge(span).to_node(sympy.Rational(exponent))
            node = BinOp(op=BinOperator.POW, lhs=node, rhs=power, span=span)
        result = node if result is None else BinOp(op=BinOperator.MUL, lhs=result, rhs=node, span=span)
    return result or NumLit(text="1", span=span)


def restore(expr, bridge, dims):
    node = bridge.to_node(expr)
    if dims != units.DIMENSIONLESS:
        node = BinOp(op=BinOperator.MUL, lhs=node, rhs=unit_node(dims, bridge.span), span=bridge.span)
    return node


def has_units(node, lookup=None):
    from .runtime import PRELUDE
    if isinstance(node, Var | BackslashRef):
        name = node.ch if isinstance(node, Var) else node.name
        value = lookup(name) if lookup else PRELUDE.get(name)
        if isinstance(value, units.Quantity | units.UnitValue):
            return True
    for field in fields(node):
        value = getattr(node, field.name)
        if isinstance(value, Node) and has_units(value, lookup):
            return True
        if isinstance(value, tuple) and any(has_units(v, lookup) for v in value if isinstance(v, Node)):
            return True
    return False


class DimensionBridge(Bridge):
    def __init__(self, span, declared, bound=frozenset(), lookup=None):
        super().__init__(span, bound, lookup)
        self.declared = declared
        self.result_dimensions = units.DIMENSIONLESS

    def to_sympy(self, node):
        magnitude, dims = self.measure(node)
        self.result_dimensions = dims
        return magnitude

    def measure(self, node):
        from .runtime import PRELUDE, NumError, parse_literal, value_to_sympy
        if isinstance(node, NumLit):
            return value_to_sympy(parse_literal(node.text)), units.DIMENSIONLESS
        if isinstance(node, Var | BackslashRef):
            name = node.ch if isinstance(node, Var) else node.name
            builtin = PRELUDE.get(name)
            if name in self.declared and (name in _CONSTANTS or isinstance(builtin, units.UnitValue)):
                if self.declared[name] != units.dimensions(builtin):
                    raise RewriteError(f"conflicting dimensions for {name}")
            resolved = name not in self.bound and name not in self.declared
            if resolved or isinstance(builtin, units.UnitValue) or name in _CONSTANTS:
                value = self.lookup(name) if self.lookup else builtin
                if isinstance(value, units.Quantity | units.UnitValue):
                    if name in self.declared and units.dimensions(value) != self.declared[name]:
                        raise RewriteError(f"conflicting dimensions for {name}")
                    magnitude, dims = units.parts(value)
                    return value_to_sympy(magnitude), dims
                if value is not None:
                    try:
                        return value_to_sympy(value), units.DIMENSIONLESS
                    except NumError:
                        pass
                if name in _CONSTANTS:
                    return _CONSTANTS[name], units.DIMENSIONLESS
            if name not in self.declared:
                raise RewriteError(f"missing dimension annotation for {name}")
            dims = self.declared[name]
            symbol = self.symbol(name, node)
            if dims != units.DIMENSIONLESS:
                self.nodes[symbol] = BinOp(op=BinOperator.DIV, lhs=node,
                                           rhs=unit_node(dims, node.span), span=node.span)
            return symbol, dims
        if isinstance(node, Equation):
            left, ld = self.measure(node.lhs)
            right, rd = self.measure(node.rhs)
            if ld != rd:
                raise RewriteError("equation sides must have matching dimensions")
            return left - right, ld
        if isinstance(node, UnOp) and node.op is UnaryOperator.NEG:
            value, dims = self.measure(node.operand)
            return -value, dims
        if isinstance(node, BinOp):
            a, ad = self.measure(node.lhs)
            b, bd = self.measure(node.rhs)
            if node.op in (BinOperator.ADD, BinOperator.SUB):
                if ad != bd:
                    raise RewriteError("operands must have matching dimensions")
                return (a + b if node.op is BinOperator.ADD else a - b), ad
            if node.op in (BinOperator.MUL, BinOperator.DIV):
                return (a * b if node.op is BinOperator.MUL else a / b), units.combine(ad, bd, 1 if node.op is BinOperator.MUL else -1)
            if node.op is BinOperator.POW:
                if bd != units.DIMENSIONLESS:
                    raise RewriteError("an exponent must be dimensionless")
                if ad != units.DIMENSIONLESS and b.is_Rational is not True:
                    raise RewriteError("a dimensioned base needs an exact rational exponent")
                return a ** b, units.power(ad, Fraction(b)) if ad != units.DIMENSIONLESS else ad
        if isinstance(node, PowCall):
            return self.measure(BinOp(op=BinOperator.POW,
                                     lhs=Call(head=node.head, args=node.args, kwargs=node.kwargs, span=node.span),
                                     rhs=node.exponent, span=node.span))
        if isinstance(node, Call) and isinstance(node.head, BackslashRef) and not node.kwargs:
            name = node.head.name
            args = [self.measure(arg) for arg in node.args]
            if name == "sqrt" and len(args) == 1:
                return sympy.sqrt(args[0][0]), units.power(args[0][1], Fraction(1, 2))
            if name == "root" and len(args) == 2:
                (a, ad), (b, bd) = args
                if bd != units.DIMENSIONLESS or not b.is_Integer or b < 1:
                    raise RewriteError("root needs a positive exact integer dimensionless index")
                return a ** (1 / b), units.power(ad, Fraction(1 / b))
            if name == "abs" and len(args) == 1:
                return sympy.Abs(args[0][0]), args[0][1]
            if any(dims != units.DIMENSIONLESS for _, dims in args):
                raise RewriteError(f"{name} needs dimensionless arguments")
            values = [value for value, _ in args]
            if name in _FUNCTIONS and len(values) == 1:
                return _FUNCTIONS[name](*values), units.DIMENSIONLESS
            if name == "log" and len(values) in (1, 2):
                return (sympy.log(values[0]) if len(values) == 1 else
                        sympy.log(values[1], values[0])), units.DIMENSIONLESS
        raise RewriteError("unsupported expression in dimensional symbolic operation")

    @property
    def metadata(self):
        return tuple(sorted(self.declared.items()))


def bridge(node, value=None, declared=None, bound=frozenset(), lookup=None):
    from .runtime import _CALL_ENGINE, PRELUDE
    if lookup is None:
        engine = _CALL_ENGINE.get()
        def lookup(name):
            found = engine._lookup(name) if engine else PRELUDE.get(name)
            return found if isinstance(found, units.UnitValue | units.Quantity) else None
    saved = dict(value.dimensions) if isinstance(value, ExpressionValue) else {}
    if declared is not None:
        for name, dims in declared.items():
            if name in saved and saved[name] != dims:
                raise RewriteError(f"conflicting dimensions for {name}")
        saved.update(declared)
    if saved or declared is not None or has_units(node, lookup):
        return DimensionBridge(node.span, saved, bound, lookup)
    return None
