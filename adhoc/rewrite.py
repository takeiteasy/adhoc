"""Symbolic rewriting over expression values: `\\simplify`, `\\expand`, `\\factor`, `\\solve`
(docs/symbolic.md).

An expression quote or a user function's body crosses to sympy, sympy rewrites it, and the
result crosses back as an expression quote. Free names stay symbols; a function's closure
supplies its numeric bindings. Only the numeric seam converts ad values to sympy
(`runtime.value_to_sympy`)."""

import os
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

import sympy

from .expression import ExpressionValue
from .span import Span
from .syntax import (
    BackslashRef, BinOp, BinOperator, Call, Node, NumLit, PowCall, Seq, UnaryOperator, UnOp,
    Var, is_short_name,
)


class RewriteError(Exception):
    pass


class _Timeout(BaseException):
    """Raised from the timer handler; not an `Exception`, so sympy's own handlers pass it on."""


DEFAULT_TIMEOUT = 5.0


def _timeout_seconds() -> float:
    text = os.environ.get("ADHOC_SYMBOLIC_TIMEOUT")
    if text is None:
        return DEFAULT_TIMEOUT
    try:
        return float(text)
    except ValueError:
        raise RewriteError(f"needs ADHOC_SYMBOLIC_TIMEOUT to be a number of seconds, got {text!r}") from None


@contextmanager
def time_limit() -> Iterator[None]:
    """Bounds the sympy work inside it. Unlimited where SIGALRM is unavailable, off the main
    thread, or when a timer is already running."""
    seconds = _timeout_seconds()
    if (seconds <= 0 or not hasattr(signal, "SIGALRM")
            or threading.current_thread() is not threading.main_thread()
            or signal.getitimer(signal.ITIMER_REAL)[0] > 0):
        yield
        return

    def expire(*_: Any) -> None:
        raise _Timeout

    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    except _Timeout:
        raise RewriteError(f"took longer than {seconds:g}s") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


_FUNCTIONS = {
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan, "asin": sympy.asin,
    "acos": sympy.acos, "atan": sympy.atan, "sinh": sympy.sinh, "cosh": sympy.cosh,
    "tanh": sympy.tanh, "asinh": sympy.asinh, "acosh": sympy.acosh, "atanh": sympy.atanh,
    "exp": sympy.exp, "ln": sympy.log, "sqrt": sympy.sqrt, "abs": sympy.Abs,
}
_NAMES = {sympy.sin: "sin", sympy.cos: "cos", sympy.tan: "tan", sympy.asin: "asin",
          sympy.acos: "acos", sympy.atan: "atan", sympy.sinh: "sinh", sympy.cosh: "cosh",
          sympy.tanh: "tanh", sympy.asinh: "asinh", sympy.acosh: "acosh",
          sympy.atanh: "atanh", sympy.exp: "exp", sympy.log: "ln", sympy.Abs: "abs"}
_CONSTANTS = {"pi": sympy.pi, "e": sympy.E, "i": sympy.I, "inf": sympy.oo}


@dataclass
class Bridge:
    """One rewrite's name table: which names are symbols, and how symbols map back to the
    source nodes that spelled them."""

    span: Span
    bound: frozenset[str] = frozenset()
    lookup: Callable[[str], Any] | None = None
    nodes: dict[sympy.Symbol, Node] = field(default_factory=dict)

    def symbol(self, name: str, node: Node) -> sympy.Symbol:
        symbol = sympy.Symbol(name)
        self.nodes.setdefault(symbol, node)
        return symbol

    def name(self, node: Var | BackslashRef) -> sympy.Expr:
        name = node.ch if isinstance(node, Var) else node.name
        if name not in self.bound:
            if self.lookup is not None:
                bound = self.lookup(name)
                if bound is not None:
                    return bound
            if name in _CONSTANTS:
                return _CONSTANTS[name]
        return self.symbol(name, node)

    def to_sympy(self, node: Node) -> sympy.Expr:
        match node:
            case NumLit(text=text):
                from .runtime import parse_literal, value_to_sympy
                return value_to_sympy(parse_literal(text))
            case Var() | BackslashRef():
                return self.name(node)
            case UnOp(op=UnaryOperator.NEG, operand=operand):
                return -self.to_sympy(operand)
            case BinOp(op=op, lhs=lhs, rhs=rhs) if op in _ARITHMETIC:
                return _ARITHMETIC[op](self.to_sympy(lhs), self.to_sympy(rhs))
            case PowCall(head=head, exponent=exponent, args=args, kwargs=()) if not (
                    isinstance(exponent, UnOp) and exponent.op is UnaryOperator.NEG):
                return self.to_sympy(Call(head=head, args=args, span=node.span)) \
                    ** self.to_sympy(exponent)
            case Call(head=BackslashRef(name="log"), args=(value,)):
                return sympy.log(self.to_sympy(value))
            case Call(head=BackslashRef(name="log"), args=(base, value)):
                return sympy.log(self.to_sympy(value), self.to_sympy(base))
            case Call(head=BackslashRef(name="root"), args=(value, index)):
                return sympy.root(self.to_sympy(value), self.to_sympy(index))
            case Call(head=BackslashRef(name=name), args=(arg,)) if name in _FUNCTIONS:
                return _FUNCTIONS[name](self.to_sympy(arg))
            case Call(head=Var() | BackslashRef() as head, args=args, kwargs=()):
                label = head.ch if isinstance(head, Var) else head.name
                return sympy.Function(label)(*(self.to_sympy(a) for a in args))
        raise RewriteError(f"cannot rewrite {_describe(node)}")

    def _atom(self, expr: sympy.Expr) -> Node:
        span = self.span
        if expr in self.nodes:
            return self.nodes[expr]
        if expr.is_Integer:
            text = str(abs(int(expr)))
            node: Node = NumLit(text=text, span=span)
            return UnOp(op=UnaryOperator.NEG, operand=node, span=span) if expr < 0 else node
        if expr.is_Rational:
            ratio = BinOp(op=BinOperator.DIV, lhs=NumLit(text=str(abs(expr.p)), span=span),
                          rhs=NumLit(text=str(expr.q), span=span), span=span)
            return UnOp(op=UnaryOperator.NEG, operand=ratio, span=span) if expr < 0 else ratio
        if expr.is_Float:
            text = repr(abs(float(expr)))
            node = NumLit(text=text if "e" in text else text + "e0", span=span)
            return UnOp(op=UnaryOperator.NEG, operand=node, span=span) if expr < 0 else node
        if expr is sympy.pi:
            return BackslashRef(name="pi", span=span, spelling="\\pi")
        if expr is sympy.E:
            return Var(ch="e", span=span, spelling="e")
        if expr is sympy.I:
            return Var(ch="i", span=span, spelling="i")
        if expr is sympy.oo:
            return BackslashRef(name="inf", span=span, spelling="\\inf")
        if isinstance(expr, sympy.Symbol):
            name = expr.name
            if is_short_name(name):
                return Var(ch=name, span=span, spelling=name)
            return BackslashRef(name=name, span=span, spelling=f"\\{name}")
        raise RewriteError(f"cannot express {expr} as an expression")

    def _call(self, name: str, *args: Node) -> Node:
        return Call(head=BackslashRef(name=name, span=self.span, spelling=f"\\{name}"),
                    args=args, span=self.span)

    def _binary(self, op: BinOperator, lhs: Node, rhs: Node) -> Node:
        return BinOp(op=op, lhs=lhs, rhs=rhs, span=self.span)

    def to_node(self, expr: sympy.Expr) -> Node:
        if expr.is_Atom:
            return self._atom(expr)
        if expr.is_Add:
            terms = expr.as_ordered_terms()
            node = self.to_node(terms[0])
            for term in terms[1:]:
                if term.could_extract_minus_sign():
                    node = self._binary(BinOperator.SUB, node, self.to_node(-term))
                else:
                    node = self._binary(BinOperator.ADD, node, self.to_node(term))
            return node
        if expr.is_Mul:
            if expr.could_extract_minus_sign():
                return UnOp(op=UnaryOperator.NEG, operand=self.to_node(-expr), span=self.span)
            numer, denom = sympy.fraction(expr)
            if denom != 1:
                return self._binary(BinOperator.DIV, self.to_node(numer), self.to_node(denom))
            factors = sympy.Mul.make_args(expr)
            node = self.to_node(factors[0])
            for factor in factors[1:]:
                node = self._binary(BinOperator.MUL, node, self.to_node(factor))
            return node
        if expr.is_Pow:
            base, exponent = expr.args
            if exponent == sympy.Rational(1, 2):
                return self._call("sqrt", self.to_node(base))
            if exponent.is_negative:
                return self._binary(BinOperator.DIV, NumLit(text="1", span=self.span),
                                    self.to_node(base ** -exponent))
            return self._binary(BinOperator.POW, self.to_node(base), self.to_node(exponent))
        if isinstance(expr, sympy.Function):
            if expr.func in _NAMES:
                return self._call(_NAMES[expr.func], *(self.to_node(a) for a in expr.args))
            if isinstance(expr.func, sympy.core.function.UndefinedFunction):
                symbol = self.nodes.get(sympy.Symbol(expr.func.__name__))
                head = symbol or self._atom(sympy.Symbol(expr.func.__name__))
                return Call(head=head, args=tuple(self.to_node(a) for a in expr.args),
                            span=self.span)
        raise RewriteError(f"cannot express {expr} as an expression")


_ARITHMETIC = {
    BinOperator.ADD: lambda a, b: a + b, BinOperator.SUB: lambda a, b: a - b,
    BinOperator.MUL: lambda a, b: a * b, BinOperator.DIV: lambda a, b: a / b,
    BinOperator.POW: lambda a, b: a ** b,
}


def _describe(node: Node) -> str:
    return type(node).__name__.lower() + " expressions"


@dataclass
class Source:
    """What a rewrite starts from: the sympy expression, its bridge, the quote's source
    text, and the parameter symbols when it came from a function."""

    expr: sympy.Expr
    bridge: Bridge
    source: str
    params: tuple[sympy.Symbol, ...] = ()


def _single_expression(node: Node) -> Node:
    if isinstance(node, Seq):
        if len(node.statements) != 1:
            raise RewriteError("cannot rewrite a function with several statements")
        node = node.statements[0]
    return node


def bridge_function(fn: Any) -> Source:
    node = _single_expression(fn.body.node)
    bridge = Bridge(node.span, frozenset(fn.params), _closure_lookup(fn.closure))
    for param in fn.params:
        bridge.symbol(param, Var(ch=param, span=node.span, spelling=param)
                      if is_short_name(param) else
                      BackslashRef(name=param, span=node.span, spelling=f"\\{param}"))
    expr = bridge.to_sympy(node)
    return Source(expr, bridge, fn.body.source, tuple(sympy.Symbol(p) for p in fn.params))


def _closure_lookup(closure: Any) -> Callable[[str], Any]:
    def lookup(name: str) -> Any:
        from .runtime import _MISSING, value_to_sympy, NumError
        value = closure._lookup(name)
        if value is _MISSING:
            return None
        try:
            return value_to_sympy(value)
        except NumError:
            return None
    return lookup


def bridge_value(value: Any) -> Source:
    from .runtime import AdFunction
    if isinstance(value, AdFunction):
        return bridge_function(value)
    if isinstance(value, ExpressionValue):
        if value.statement_body:
            raise RewriteError("needs an expression quote, not a statement quote")
        bridge = Bridge(value.node.span)
        return Source(bridge.to_sympy(value.node), bridge, value.source)
    raise RewriteError("needs an expression quote or a user-defined function")


def quote(expr: sympy.Expr, bridge: Bridge, source: str) -> ExpressionValue:
    return ExpressionValue(bridge.to_node(expr), source)


def rewrite(value: Any, operation: Callable[[sympy.Expr], sympy.Expr]) -> ExpressionValue:
    origin = bridge_value(value)
    with time_limit():
        result = operation(origin.expr)
    return quote(result, origin.bridge, origin.source)


def derivative(value: Any, unknown: Any = None, order: Any = 1) -> ExpressionValue:
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise RewriteError("needs the order to be a positive integer")
    origin = bridge_value(value)
    symbol = _unknown(origin, unknown)
    with time_limit():
        result = sympy.diff(origin.expr, symbol, order)
    return quote(result, origin.bridge, origin.source)


def solve(value: Any, unknown: Any = None) -> Any:
    """The solutions of `value = 0` over the complex numbers, as an ad set."""
    from .runtime import NumError, SetValue, _dedup, _sympy_to_ad
    origin = bridge_value(value)
    symbol = _unknown(origin, unknown)
    with time_limit():
        solutions = sympy.solveset(origin.expr, symbol, sympy.S.Complexes)
    if solutions is sympy.S.EmptySet:
        return SetValue(())
    if not isinstance(solutions, sympy.FiniteSet):
        if isinstance(solutions, sympy.ConditionSet):
            raise RewriteError("cannot solve this equation in closed form")
        raise RewriteError("has infinitely many solutions")
    items = []
    for solution in sorted(solutions, key=sympy.default_sort_key):
        if solution.free_symbols:
            items.append(quote(solution, origin.bridge, origin.source))
            continue
        try:
            items.append(_sympy_to_ad(solution, "sympy expression"))
        except NumError:
            items.append(quote(solution, origin.bridge, origin.source))
    return SetValue(_dedup(items))


def _unknown(origin: Source, unknown: Any) -> sympy.Symbol:
    if unknown is not None:
        if not isinstance(unknown, ExpressionValue) or not isinstance(
                unknown.node, Var | BackslashRef):
            raise RewriteError("the unknown must be a quoted name, like `(x)")
        return sympy.Symbol(unknown.node.ch if isinstance(unknown.node, Var)
                            else unknown.node.name)
    free = sorted(origin.expr.free_symbols, key=lambda s: s.name)
    if origin.params:
        if len(origin.params) != 1:
            raise RewriteError("needs the unknown when the function has several parameters")
        return origin.params[0]
    if len(free) != 1:
        if not free:
            raise RewriteError("has no unknown to solve for")
        names = ", ".join(s.name for s in free)
        raise RewriteError(f"needs the unknown when there are several free names: {names}")
    return free[0]
